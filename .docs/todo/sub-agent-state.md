# 子Agent状态管理优化

## 问题描述

当前子 Agent 调用存在重复初始化和 I/O 浪费问题：

1. **每次创建新实例**：`coding_agent_handler` / `daily_agent_handler` 每次调用都创建全新 Agent 实例 (`main.py:582-591`)

2. **重复文件读取**：同一会话内多次调用 Coding Agent 时，重复读取相同文件

3. **无分析结果复用**：子 Agent 无法利用前次调用的分析结果

4. **初始化开销可忽略**：Agent 实例化 <100ms，主要浪费在重复 I/O

```python
# main.py:582-591 每次调用创建新实例
async def coding_agent_handler(task: str) -> str:
    coding_agent = Agent(  # 每次新建
        llm_client=llm_client,
        tools=create_coding_tools(work_dir, confirm_fn),
        config=AgentConfig(...)
    )
    return await coding_agent.run(task)
```

---

## 方案对比

| 方案 | 技术选型 | 适用场景 | 实现难度 | 新增依赖 | 模块耦合 |
|------|----------|----------|----------|----------|----------|
| **方案1：文件读取缓存层** | dict + mtime 校验 | 频繁读取相同文件 | 低（半天） | 无 | 低 |
| 方案2：会话级子Agent复用 | 实例变量 | 需要历史上下文 | 中（1-2天） | 无 | 中 |
| 方案3：上下文摘要传递 | 系统提示注入 | 需要上下文但不累积 | 中（1天） | 无 | 中 |

---

### 方案 1：文件读取缓存层（推荐）

#### 设计思路

在 `read_file` 工具中添加内存缓存，使用文件修改时间 (mtime) 进行缓存失效判断。`write_file` / `edit_file` 写入时自动更新缓存。

#### 核心实现

```python
# coding/tools/file_cache.py
from pathlib import Path
from typing import Optional
import os

class FileCache:
    """文件内容缓存，生命周期跟随主 Agent 会话"""
    
    def __init__(self, max_size: int = 100):
        self._cache: dict[str, tuple[str, float]] = {}  # path -> (content, mtime)
        self._max_size = max_size
    
    def get(self, file_path: str) -> Optional[str]:
        """获取缓存内容，如果文件已修改则返回 None"""
        if file_path not in self._cache:
            return None
        
        content, cached_mtime = self._cache[file_path]
        try:
            current_mtime = os.path.getmtime(file_path)
            if current_mtime > cached_mtime:
                # 文件已修改，缓存失效
                del self._cache[file_path]
                return None
            return content
        except OSError:
            return None
    
    def set(self, file_path: str, content: str) -> None:
        """设置缓存"""
        if len(self._cache) >= self._max_size:
            # LRU 简化版：删除最旧的
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        
        try:
            mtime = os.path.getmtime(file_path)
            self._cache[file_path] = (content, mtime)
        except OSError:
            pass
    
    def invalidate(self, file_path: str) -> None:
        """手动失效缓存（写入后调用）"""
        self._cache.pop(file_path, None)
    
    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()

# 全局缓存实例（会话级）
_file_cache: Optional[FileCache] = None

def get_file_cache() -> FileCache:
    global _file_cache
    if _file_cache is None:
        _file_cache = FileCache()
    return _file_cache
```

**集成到工具：**

```python
# coding/tools/read_file.py
from .file_cache import get_file_cache

def read_file(file_path: str) -> str:
    cache = get_file_cache()
    
    # 尝试从缓存获取
    cached = cache.get(file_path)
    if cached is not None:
        return cached
    
    # 读取文件
    path = Path(file_path)
    if not path.exists():
        return f"文件不存在：{file_path}"
    
    content = path.read_text(encoding="utf-8")
    cache.set(file_path, content)
    return content

# coding/tools/write_file.py
from .file_cache import get_file_cache

def write_file(file_path: str, content: str) -> str:
    # ... 写入逻辑 ...
    
    # 更新缓存（写入后内容已知）
    cache = get_file_cache()
    cache.set(file_path, content)
    return "写入成功"
```

#### 缓存生命周期

```
主 Agent 启动
    ↓
创建 FileCache 实例
    ↓
调用 Coding Agent #1 → read_file → 缓存 miss → 读取 → 缓存
    ↓
调用 Coding Agent #2 → read_file → 缓存 hit → 直接返回
    ↓
调用 Coding Agent #3 → write_file → 更新缓存
    ↓
会话结束 → FileCache 销毁
```

#### 优点
- 实现简单，改动小
- 显著减少重复 I/O
- 自动处理缓存失效

#### 缺点
- 仅缓存文件内容，不缓存分析结果
- 内存占用随缓存文件数增长

---

### 方案 2：会话级子 Agent 复用

#### 设计思路

在 `main.py` 中维护 `_coding_agent` / `_daily_agent` 实例变量，复用已创建的子 Agent。

#### 核心实现

```python
# cli/main.py
class AgentSession:
    def __init__(self, llm_client: LLMClient, work_dir: str):
        self._llm_client = llm_client
        self._work_dir = work_dir
        self._coding_agent: Optional[Agent] = None
        self._daily_agent: Optional[Agent] = None
    
    def get_coding_agent(self, confirm_fn: Callable) -> Agent:
        if self._coding_agent is None:
            self._coding_agent = Agent(
                llm_client=self._llm_client,
                tools=create_coding_tools(self._work_dir, confirm_fn),
                config=AgentConfig(
                    system_prompt=CODING_SYSTEM_PROMPT,
                    max_turns=20,
                )
            )
        return self._coding_agent
    
    async def run_coding_task(self, task: str, confirm_fn: Callable) -> str:
        agent = self.get_coding_agent(confirm_fn)
        
        # 检查消息历史长度，必要时压缩
        if len(agent._messages) > 50:
            await agent.compress_history()
        
        return await agent.run(task)
```

#### 消息历史管理

```python
# agent/agent.py 添加方法
async def compress_history(self) -> None:
    """压缩历史消息，保留关键信息"""
    if len(self._messages) <= 10:
        return
    
    # 保留最近 10 条消息
    recent = self._messages[-10:]
    
    # 对旧消息生成摘要
    old_messages = self._messages[:-10]
    summary = await self._generate_summary(old_messages)
    
    # 重置消息，注入摘要
    self._messages = [
        {"role": "system", "content": f"[历史摘要] {summary}"},
        *recent
    ]
```

#### 优点
- 保留子 Agent 的消息历史
- 减少重复分析
- 支持跨调用上下文

#### 缺点
- 消息历史累积导致 token 增长
- 需要实现历史压缩机制
- main.py 重构较大

---

### 方案 3：上下文摘要传递

#### 设计思路

子 Agent 创建时，将主 Agent 最近 N 条相关消息的摘要注入子 Agent 的系统提示。

#### 核心实现

```python
# cli/main.py
def build_context_summary(messages: list[dict], max_items: int = 5) -> str:
    """从主 Agent 消息中提取上下文摘要"""
    relevant = []
    
    for msg in reversed(messages[-20:]):
        content = msg.get("content", "")
        
        # 提取文件操作相关信息
        if any(kw in content for kw in ["文件", "代码", "修改", "创建"]):
            relevant.append(content[:200])
        
        if len(relevant) >= max_items:
            break
    
    if not relevant:
        return ""
    
    return "相关上下文：\n" + "\n".join(f"- {r}" for r in relevant)

async def coding_agent_handler(
    task: str,
    main_messages: list[dict],
    confirm_fn: Callable
) -> str:
    context_summary = build_context_summary(main_messages)
    
    system_prompt = CODING_SYSTEM_PROMPT
    if context_summary:
        system_prompt += f"\n\n{context_summary}"
    
    coding_agent = Agent(
        llm_client=llm_client,
        tools=create_coding_tools(work_dir, confirm_fn),
        config=AgentConfig(system_prompt=system_prompt)
    )
    
    return await coding_agent.run(task)
```

#### 优点
- 子 Agent 有上下文但不累积状态
- 实现较简单
- 不改变现有 Agent 结构

#### 缺点
- 摘要可能丢失细节
- 额外的 token 消耗
- 需要定义"相关"规则

---

## 推荐方案

**推荐方案1（文件读取缓存层）**

理由：
1. **简单有效**：最小改动，最大收益
2. **风险低**：不改变 Agent 生命周期
3. **即时生效**：重复文件读取立即受益
4. **可组合**：不影响后续升级到方案2

---

## 实施计划

### 阶段 1：文件缓存（立即，半天）

1. 新建 `coding/tools/file_cache.py`，实现 `FileCache` 类
2. 修改 `coding/tools/read_file.py`：集成缓存读取
3. 修改 `coding/tools/write_file.py`：写入后更新缓存
4. 修改 `coding/tools/edit_file.py`：编辑后更新缓存
5. 在 `main.py` 会话结束时清理缓存

### 阶段 2：子 Agent 复用（中期，按需）

1. 重构 `main.py`，引入 `AgentSession` 类
2. 实现 Agent 消息历史压缩
3. 添加 token 使用监控

### 阶段 3：上下文传递（可选）

1. 实现上下文摘要生成
2. 修改子 Agent 系统提示模板

---

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `src/quangan/coding/tools/file_cache.py` | 新建，文件缓存实现 |
| `src/quangan/coding/tools/read_file.py` | 集成缓存读取 |
| `src/quangan/coding/tools/write_file.py` | 写入后更新缓存 |
| `src/quangan/coding/tools/edit_file.py` | 编辑后更新缓存 |
| `src/quangan/cli/main.py` | 会话结束清理缓存（阶段1）/ AgentSession（阶段2） |
| `src/quangan/agent/agent.py` | 添加 compress_history 方法（阶段2） |
