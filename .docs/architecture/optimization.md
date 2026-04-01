# 架构优化建议

## 概述

本文档汇总 QuanGan 架构的优化建议，按优先级排序。每项建议包含当前状态分析、优化方向、预期收益和实施复杂度评估。

---

## 优化建议总览

| 优先级 | 领域 | 当前状态 | 建议 | 预期收益 |
|--------|------|----------|------|----------|
| 🔴 高 | 记忆检索效率 | 简单词级匹配 O(n) | 向量化存储 + 语义搜索 | 检索准确率 +40%，速度 10x |
| 🔴 高 | 安全性 | 无命令白名单 | 危险命令确认 + 文件访问限制 | 降低误操作风险 |
| 🔴 高 | 子 Agent 状态 | 无状态，每次新建 | 会话级复用 + 共享缓存 | 减少重复文件读取 |
| 🟡 中 | 上下文压缩 | 统一压缩策略 | 选择性压缩（代码高保留） | 关键信息保留率 +30% |
| 🟡 中 | 工具并发 | 顺序执行 | asyncio.gather 并行 | 多工具场景提速 50% |
| 🟡 中 | 错误处理 | 基础异常捕获 | 分级日志 + 重试机制 | 可观测性提升 |
| 🟢 低 | Skill 触发 | 简单子串匹配 | 条件触发 + 优先级 | 更精准的能力增强 |
| 🟢 低 | 会话存储 | JSON 全量存储 | SQLite / 增量存储 | 支持大会话 |

---

## 1. 记忆检索效率（高优）

### 当前状态

```python
# src/quangan/memory/tools.py

async def recall_impl(args: dict[str, Any]) -> str:
    query = args["query"].lower()
    query_words = query.split()  # 简单分词
    
    # O(n) 遍历 + 子串匹配
    relevant = [
        m for m in core.memories
        if any(kw in m.content.lower() for kw in query_words)
    ]
```

**问题：**
- 简单词级匹配，无法处理语义相似性
- 遍历整个记忆库，复杂度 O(n)
- 无法识别同义词（如"Python"和"py"）

### 优化建议

**方案 A：向量化存储 + 语义搜索**

```python
# 建议实现
from sentence_transformers import SentenceTransformer
import numpy as np

class VectorMemoryStore:
    def __init__(self):
        self.encoder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.memories: list[CoreMemoryItem] = []
        self.vectors: np.ndarray | None = None
    
    def add(self, memory: CoreMemoryItem):
        self.memories.append(memory)
        vector = self.encoder.encode(memory.content)
        if self.vectors is None:
            self.vectors = vector.reshape(1, -1)
        else:
            self.vectors = np.vstack([self.vectors, vector])
    
    def search(self, query: str, top_k: int = 5) -> list[CoreMemoryItem]:
        query_vec = self.encoder.encode(query)
        # 余弦相似度计算
        similarities = np.dot(self.vectors, query_vec) / (
            np.linalg.norm(self.vectors, axis=1) * np.linalg.norm(query_vec)
        )
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        return [self.memories[i] for i in top_indices]
```

**方案 B：倒排索引（轻量级）**

```python
from collections import defaultdict

class InvertedIndex:
    def __init__(self):
        self.index: dict[str, set[str]] = defaultdict(set)
        self.memories: dict[str, CoreMemoryItem] = {}
    
    def add(self, memory: CoreMemoryItem):
        self.memories[memory.id] = memory
        words = self._tokenize(memory.content)
        for word in words:
            self.index[word].add(memory.id)
    
    def search(self, query: str) -> list[CoreMemoryItem]:
        query_words = self._tokenize(query)
        # 交集查找
        result_ids = set.intersection(*[self.index[w] for w in query_words])
        return [self.memories[mid] for mid in result_ids]
```

### 实施建议

1. **第一阶段**：引入倒排索引，快速改善检索速度
2. **第二阶段**：引入向量检索，提升语义匹配能力
3. **可选**：使用轻量级向量库如 `faiss-cpu` 或 `chromadb`

---

## 2. 安全性（高优）

### 当前状态

- `execute_command` 有危险命令确认机制
- 但缺乏系统性的安全策略

### 优化建议

**A. 命令白名单/黑名单**

```python
DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+/",           # 根目录删除
    r">\s*/dev/",              # 设备文件写入
    r"curl.*\|\s*sh",          # 管道执行远程脚本
    r"wget.*\|\s*sh",
]

SAFE_COMMANDS = [
    r"^ls\s+",
    r"^cat\s+",
    r"^grep\s+",
    r"^git\s+(status|log|diff)",
]

def validate_command(cmd: str) -> tuple[bool, str]:
    """返回 (是否安全, 原因)"""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            return False, f"检测到危险命令模式: {pattern}"
    return True, ""
```

**B. 文件访问范围限制**

```python
class FileAccessController:
    def __init__(self, work_dir: str):
        self.work_dir = Path(work_dir).resolve()
        self.allowed_paths = [self.work_dir, Path.home() / ".config"]
    
    def is_allowed(self, file_path: str) -> bool:
        path = Path(file_path).resolve()
        return any(
            path == allowed or path.is_relative_to(allowed)
            for allowed in self.allowed_paths
        )
```

**C. 审计日志**

```python
import logging

audit_logger = logging.getLogger("quangan.audit")

def log_tool_call(tool_name: str, args: dict, result: str):
    audit_logger.info(
        f"Tool: {tool_name}, Args: {args}, Result: {result[:100]}"
    )
```

---

## 3. 子 Agent 状态（高优）

### 当前状态

```python
# 每次调用都创建新实例
async def coding_agent_handler(args: dict[str, Any]) -> str:
    coding_agent = create_coding_agent(client, CWD, callbacks)
    return await coding_agent.run(args["task"])
```

**问题：**
- 重复读取相同文件（如 `utils.py`）
- 无法利用之前的分析结果
- 每次都要重新理解项目结构

### 优化建议

**会话级复用 + 共享文件缓存**

```python
class AgentSession:
    """管理子 Agent 的会话级复用"""
    
    def __init__(self):
        self._coding_agent: Agent | None = None
        self._daily_agent: Agent | None = None
        self._file_cache: dict[str, str] = {}  # 文件内容缓存
    
    def get_coding_agent(self, client, cwd, callbacks) -> Agent:
        if self._coding_agent is None:
            self._coding_agent = create_coding_agent(client, cwd, callbacks)
            # 注入文件缓存
            self._coding_agent._file_cache = self._file_cache
        return self._coding_agent
    
    def invalidate_cache(self, file_path: str):
        """文件修改后使缓存失效"""
        self._file_cache.pop(file_path, None)

# 在 read_file 中使用缓存
async def read_file_with_cache(args: dict) -> str:
    path = args["file_path"]
    if path in file_cache:
        return file_cache[path]
    
    content = await actual_read_file(path)
    file_cache[path] = content
    return content
```

---

## 4. 上下文压缩（中优）

### 当前状态

统一压缩策略：保留最近 6 条消息，其余生成摘要。

**问题：**
- 代码内容可能被过度压缩
- 文件路径和关键修改可能丢失

### 优化建议

**选择性压缩 + 分层摘要**

```python
class SmartCompressor:
    def __init__(self):
        self.code_retention_rate = 0.8  # 代码内容高保留率
        self.text_retention_rate = 0.3  # 普通文本低保留率
    
    def should_compress(self, message: dict) -> bool:
        """判断消息是否应该被压缩"""
        content = message.get("content", "")
        
        # 包含代码块的消息，谨慎压缩
        if "```" in content:
            return len(content) > 2000  # 只有很长的代码才压缩
        
        # 包含文件路径的消息，保留
        if self._contains_file_paths(content):
            return False
        
        return True
    
    def compress_message(self, message: dict) -> str:
        """根据消息类型选择压缩策略"""
        content = message.get("content", "")
        
        if "```" in content:
            # 代码：保留签名和关键行
            return self._compress_code(content)
        elif message.get("role") == "tool":
            # 工具结果：提取关键信息
            return self._extract_key_info(content)
        else:
            # 普通文本：生成摘要
            return self._summarize_text(content)
```

---

## 5. 工具并发（中优）

### 当前状态

```python
# 顺序执行工具调用
for tool_call in result.tool_calls:
    tool_result = await self._execute_tool_call(tool_call)
    self._messages.append(tool_result)
```

### 优化建议

**无依赖工具并行执行**

```python
async def _execute_tool_calls_parallel(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
    """并行执行无依赖的工具调用"""
    
    # 分析依赖关系（简单实现：假设工具间无依赖）
    async def execute_single(tool_call: ToolCall) -> ToolResult:
        return await self._execute_tool_call(tool_call)
    
    # 并行执行
    results = await asyncio.gather(*[
        execute_single(tc) for tc in tool_calls
    ])
    
    return results
```

**适用场景：**
- 同时读取多个文件
- 同时搜索代码和验证语法
- 同时打开多个应用

---

## 6. 错误处理（中优）

### 当前状态

基础异常捕获，静默处理部分错误。

### 优化建议

**分级日志 + 重试机制**

```python
import structlog

logger = structlog.get_logger()

class RetryableTool:
    def __init__(self, max_retries: int = 3, backoff: float = 1.0):
        self.max_retries = max_retries
        self.backoff = backoff
    
    async def execute(self, tool_call: ToolCall) -> ToolResult:
        for attempt in range(self.max_retries):
            try:
                return await self._do_execute(tool_call)
            except TransientError as e:
                logger.warning(
                    "tool_transient_error",
                    tool=tool_call["function"]["name"],
                    attempt=attempt + 1,
                    error=str(e)
                )
                await asyncio.sleep(self.backoff * (2 ** attempt))
            except PermanentError as e:
                logger.error(
                    "tool_permanent_error",
                    tool=tool_call["function"]["name"],
                    error=str(e)
                )
                return ToolResult(
                    tool_call_id=tool_call["id"],
                    role="tool",
                    name=tool_call["function"]["name"],
                    content=f"工具执行失败: {e}",
                )
```

**降级策略**

```python
async def read_file_with_fallback(args: dict) -> str:
    """优先使用 ripgrep，失败时使用 Python 实现"""
    try:
        return await read_file_with_rg(args)
    except FileNotFoundError:
        return await read_file_with_python(args)
```

---

## 7. Skill 触发（低优）

### 当前状态

简单子串匹配，无优先级概念。

### 优化建议

**条件触发 + 优先级**

```python
@dataclass
class SkillTrigger:
    """高级触发条件"""
    keywords: list[str]                    # 关键词
    require_all: bool = False              # 是否需要全部匹配
    exclude_keywords: list[str] = None     # 排除词
    priority: int = 0                      # 优先级（高优先覆盖低优先）
    max_activations_per_session: int = 0   # 每会话最大激活次数（0=无限制）

class Skill:
    def should_trigger(self, message: str, context: dict) -> bool:
        """考虑上下文的触发判断"""
        # 基础关键词匹配
        if not self._keyword_match(message):
            return False
        
        # 排除词检查
        if self._has_exclude_words(message):
            return False
        
        # 激活次数限制
        if self._reached_activation_limit(context):
            return False
        
        return True
```

---

## 8. 会话存储（低优）

### 当前状态

JSON 全量存储，每次保存整个消息历史。

### 优化建议

**SQLite 存储 + 增量更新**

```python
import sqlite3

class SQLiteSessionStore:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self._init_schema()
    
    def _init_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                metadata TEXT,  -- JSON
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session 
            ON messages(session_id, created_at)
        """)
    
    def append(self, session_id: str, message: dict):
        """增量追加单条消息"""
        self.conn.execute(
            "INSERT INTO messages (session_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (session_id, message["role"], message.get("content"), 
             json.dumps({k: v for k, v in message.items() if k.startswith("_")}))
        )
        self.conn.commit()
    
    def load(self, session_id: str, limit: int = 1000) -> list[dict]:
        """分页加载消息"""
        cursor = self.conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
            (session_id, limit)
        )
        return [self._row_to_dict(row) for row in cursor.fetchall()]
```

**收益：**
- 支持超大会话（百万级消息）
- 增量保存，减少 I/O
- 支持消息搜索和统计

---

## 实施路线图

```
Phase 1 (近期) ──────────────────────────────────────────────
│
├── 安全性增强
│   ├── 命令白名单/黑名单
│   └── 文件访问范围限制
│
├── 错误处理改进
│   └── 分级日志系统
│
└── 子 Agent 缓存
    └── 文件内容缓存层

Phase 2 (中期) ──────────────────────────────────────────────
│
├── 记忆检索优化
│   ├── 倒排索引实现
│   └── 向量检索调研
│
├── 上下文压缩改进
│   └── 选择性压缩策略
│
└── 工具并发
    └── 无依赖工具并行执行

Phase 3 (远期) ──────────────────────────────────────────────
│
├── Skill 系统增强
│   └── 条件触发 + 优先级
│
└── 会话存储优化
    └── SQLite 迁移（可选）
```

---

## 相关文件

| 文件 | 当前实现 |
|------|----------|
| `src/quangan/memory/tools.py` | 记忆检索 |
| `src/quangan/agents/coding/tools/execute_command.py` | 命令执行安全 |
| `src/quangan/agent/agent.py` | 子 Agent 创建、工具执行 |
| `src/quangan/skills/models.py` | Skill 触发 |
| `src/quangan/cli/session_store.py` | 会话存储 |

---

## 交叉引用

- 记忆系统：[记忆系统架构](memory-system.md)
- 上下文压缩：[上下文压缩算法](context-compression.md)
- Skill 系统：[Skill系统设计](skill-system.md)
- 会话持久化：[会话持久化机制](session-persistence.md)
