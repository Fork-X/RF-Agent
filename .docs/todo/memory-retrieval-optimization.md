# 记忆检索效率优化

## 问题描述

当前记忆检索实现存在以下性能和功能瓶颈：

1. **简单词级匹配**：`recall_impl` (`tools.py:87-127`) 使用 `any(kw in m.content.lower() for kw in query_words)`，无法处理同义词和语义相似性

2. **O(n) 线性扫描**：Core Memory 无索引结构，每次检索都遍历全部记忆

3. **文件系统扫描**：Life Memory 每次调用都执行 `iterdir` (`store.py:212`)，I/O 开销大

4. **无依赖支持**：`pyproject.toml` 未引入任何向量/搜索库

```python
# 当前实现 (tools.py:87-127)
def recall_impl(query: str, memory_store: MemoryStore) -> str:
    query_words = query.lower().split()
    matches = []
    for m in memory_store.core_memories:
        if any(kw in m.content.lower() for kw in query_words):
            matches.append(m)
    # Life Memory 每次都扫描文件系统...
```

---

## 方案对比

| 方案 | 技术选型 | 适用场景 | 实现难度 | 新增依赖 | 模块耦合 |
|------|----------|----------|----------|----------|----------|
| **方案1：倒排索引** | collections.defaultdict | 记忆量 <1000 条 | 低（1-2天） | 无 | 低 |
| 方案2：轻量向量检索 | chromadb + 内置 embedding | 记忆量 1000+ 条 | 中（3-5天） | chromadb (~50MB) | 中 |
| 方案3：LLM辅助检索 | 现有 LLM client | 记忆量少但需高精度 | 低（半天） | 无 | 低 |

---

### 方案 1：倒排索引（推荐初期）

#### 设计思路

为 `CoreMemoryItem` 构建词→记忆ID的倒排索引，支持 intersection（AND）/ union（OR）查询。

#### 核心实现

```python
# memory/index.py
from collections import defaultdict
from typing import Set

class InvertedIndex:
    def __init__(self):
        self._index: dict[str, Set[str]] = defaultdict(set)
        self._docs: dict[str, str] = {}  # id -> content
    
    def add(self, doc_id: str, content: str) -> None:
        tokens = self._tokenize(content)
        for token in tokens:
            self._index[token].add(doc_id)
        self._docs[doc_id] = content
    
    def search(self, query: str, mode: str = "or") -> list[str]:
        tokens = self._tokenize(query)
        if not tokens:
            return []
        
        result_sets = [self._index.get(t, set()) for t in tokens]
        if mode == "and":
            result = set.intersection(*result_sets) if result_sets else set()
        else:
            result = set.union(*result_sets) if result_sets else set()
        return list(result)
    
    def _tokenize(self, text: str) -> list[str]:
        # 简单分词：小写 + 空格分割 + 去停用词
        return [w for w in text.lower().split() if len(w) > 1]
```

#### 集成方式

```python
# memory/store.py 修改
class MemoryStore:
    def __init__(self, cwd: str):
        self._index = InvertedIndex()
        # 初始化时构建索引
        for m in self.core_memories:
            self._index.add(m.id, m.content)
    
    def add_core_memory(self, item: CoreMemoryItem) -> None:
        # 写入时同步更新索引
        self._index.add(item.id, item.content)
```

#### 优点
- 零新依赖，纯 Python 实现
- 查询复杂度 O(k)，k 为查询词数
- 支持布尔查询（AND/OR）

#### 缺点
- 无语义理解能力
- 内存占用随记忆量线性增长

---

### 方案 2：轻量向量检索（推荐中期）

#### 设计思路

使用 chromadb 本地嵌入式向量数据库，支持语义相似性检索。

#### 核心实现

```python
# memory/vector_store.py
import chromadb

class VectorMemoryStore:
    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name="memories",
            metadata={"hnsw:space": "cosine"}
        )
    
    def add(self, doc_id: str, content: str, metadata: dict = None) -> None:
        self._collection.add(
            ids=[doc_id],
            documents=[content],
            metadatas=[metadata or {}]
        )
    
    def search(self, query: str, top_k: int = 5) -> list[dict]:
        results = self._collection.query(
            query_texts=[query],
            n_results=top_k
        )
        return [
            {"id": id, "content": doc, "score": score}
            for id, doc, score in zip(
                results["ids"][0],
                results["documents"][0],
                results["distances"][0]
            )
        ]
```

#### 优点
- 语义检索，理解同义词和相似概念
- 内置 embedding 模型，无需额外配置
- 持久化存储，重启不丢失

#### 缺点
- 新增 ~50MB 依赖
- 首次加载有冷启动延迟
- 需要重构现有存储逻辑

---

### 方案 3：LLM 辅助检索

#### 设计思路

将检索任务转化为 LLM 判断，利用现有 LLM client 进行语义理解。

#### 核心实现

```python
# memory/tools.py 修改
async def recall_with_llm(
    query: str, 
    memories: list[CoreMemoryItem],
    llm_client: LLMClient
) -> list[CoreMemoryItem]:
    # 构造检索 prompt
    memory_list = "\n".join([
        f"[{i}] {m.content[:200]}" 
        for i, m in enumerate(memories)
    ])
    
    prompt = f"""从以下记忆中选出与查询最相关的项（返回序号）：

查询：{query}

记忆列表：
{memory_list}

返回格式：[0, 2, 5]（最相关的序号列表）"""

    response = await llm_client.ask(prompt)
    indices = json.loads(response)
    return [memories[i] for i in indices if i < len(memories)]
```

#### 优点
- 最高的语义理解能力
- 无新依赖
- 实现极简

#### 缺点
- 每次检索消耗 LLM token
- 响应延迟 ~1-2s
- 记忆量大时 prompt 过长

---

## 推荐方案

**推荐路径：方案1 → 方案2（渐进式升级）**

1. **立即实施方案1**：倒排索引零依赖，快速解决 O(n) 扫描问题
2. **中期升级方案2**：当记忆量突破 1000 条或用户反馈检索不准确时，引入向量检索
3. **方案3作为补充**：特定场景（如复杂语义查询）可组合使用

---

## 实施计划

### 阶段 1：倒排索引（立即）

1. 新建 `memory/index.py`，实现 `InvertedIndex` 类
2. 修改 `memory/store.py`：
   - `MemoryStore.__init__` 中初始化索引
   - `add_core_memory` 中同步更新索引
3. 修改 `memory/tools.py`：
   - `recall_impl` 改用索引查询
4. 为 Life Memory 添加文件列表缓存（避免重复 iterdir）

### 阶段 2：向量检索（中期）

1. 在 `pyproject.toml` 添加 chromadb 依赖
2. 新建 `memory/vector_store.py`
3. 实现索引与向量检索的混合策略：
   - 倒排索引快速过滤
   - 向量检索精排

### 阶段 3：优化调优（远期）

1. 添加检索结果缓存（LRU）
2. 实现增量索引更新
3. 支持自定义 embedding 模型

---

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `src/quangan/memory/index.py` | 新建，实现倒排索引 |
| `src/quangan/memory/store.py` | 集成索引，添加文件缓存 |
| `src/quangan/memory/tools.py` | `recall_impl` 使用索引查询 |
| `pyproject.toml` | 中期添加 chromadb 依赖 |
