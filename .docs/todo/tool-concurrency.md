# 工具并发执行

## 问题描述

当前工具调用严格串行执行，存在性能瓶颈：

1. **串行执行**：`agent.py:634-636` 中 `for tool_call in result.tool_calls` 逐个执行

2. **LLM 支持批量调用**：LLM 可在单次响应中返回多个 `tool_calls`（如同时读取多个文件）

3. **Readonly 工具可并发**：`read_file`、`list_directory`、`search_code` 等只读工具天然无副作用

4. **性能损失**：串行执行在多工具场景下性能损失约 40-60%

```python
# agent.py:634-636 当前串行实现
for tool_call in result.tool_calls:
    tool_result = await self._execute_tool_call(tool_call)
    self._messages.append(tool_result)
```

**示例场景**：

```
LLM 返回：
[read_file("a.py"), read_file("b.py"), read_file("c.py")]

当前串行：3 次 I/O，总耗时 ~300ms
并行执行：3 次 I/O 并发，总耗时 ~100ms
```

---

## 方案对比

| 方案 | 技术选型 | 适用场景 | 实现难度 | 新增依赖 | 模块耦合 |
|------|----------|----------|----------|----------|----------|
| **方案1：Readonly工具并行** | asyncio.gather | 批量只读操作 | 低（2-3小时） | 无 | 低 |
| 方案2：依赖分析并行 | DAG 执行 | 复杂工具链 | 中（2-3天） | 无 | 中 |
| 方案3：保持串行 | 无变更 | 简单场景 | 无 | 无 | 无 |

---

### 方案 1：Readonly 工具并行（推荐）

#### 设计思路

判断条件：若批次中所有 `tool_call` 对应的工具都是 `readonly=True`，则并行执行；否则退回串行执行。

#### 工具元数据扩展

```python
# tools/types.py
from dataclasses import dataclass
from typing import Callable, Awaitable

@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Awaitable[str]]
    readonly: bool = False  # 新增：是否为只读工具
    
    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
```

**标记只读工具：**

```python
# coding/tools/read_file.py
read_file_tool = ToolDefinition(
    name="read_file",
    description="读取文件内容",
    parameters={...},
    handler=read_file,
    readonly=True,  # 只读
)

# coding/tools/list_directory.py
list_directory_tool = ToolDefinition(
    name="list_directory",
    description="列出目录内容",
    parameters={...},
    handler=list_directory,
    readonly=True,  # 只读
)

# coding/tools/search_code.py
search_code_tool = ToolDefinition(
    name="search_code",
    description="搜索代码",
    parameters={...},
    handler=search_code,
    readonly=True,  # 只读
)

# coding/tools/write_file.py
write_file_tool = ToolDefinition(
    name="write_file",
    description="写入文件",
    parameters={...},
    handler=write_file,
    readonly=False,  # 有副作用
)
```

#### 并行执行逻辑

```python
# agent/agent.py
import asyncio

async def _execute_tool_calls(
    self, 
    tool_calls: list[ToolCall]
) -> list[dict]:
    """执行工具调用批次"""
    
    # 检查是否所有工具都是只读
    all_readonly = all(
        self._get_tool(tc.name).readonly 
        for tc in tool_calls
    )
    
    if all_readonly and len(tool_calls) > 1:
        # 并行执行
        return await self._execute_parallel(tool_calls)
    else:
        # 串行执行
        return await self._execute_sequential(tool_calls)

async def _execute_parallel(
    self, 
    tool_calls: list[ToolCall]
) -> list[dict]:
    """并行执行只读工具"""
    tasks = [
        self._execute_tool_call(tc) 
        for tc in tool_calls
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理异常
    tool_results = []
    for tc, result in zip(tool_calls, results):
        if isinstance(result, Exception):
            tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": f"执行失败: {result}"
            })
        else:
            tool_results.append(result)
    
    return tool_results

async def _execute_sequential(
    self, 
    tool_calls: list[ToolCall]
) -> list[dict]:
    """串行执行工具"""
    results = []
    for tc in tool_calls:
        result = await self._execute_tool_call(tc)
        results.append(result)
    return results
```

#### 主循环修改

```python
# agent/agent.py run() 方法
async def run(self, task: str) -> str:
    # ...
    while True:
        result = await self._call_llm()
        
        if result.tool_calls:
            # 批量执行工具调用
            tool_results = await self._execute_tool_calls(result.tool_calls)
            
            # 按原始顺序追加到消息
            for tool_result in tool_results:
                self._messages.append(tool_result)
        
        # ...
```

#### 优点
- 实现简单，风险低
- 只读工具无副作用，并行安全
- 性能提升明显（多文件读取场景）

#### 缺点
- 仅优化纯只读批次
- 混合调用仍需串行

---

### 方案 2：依赖分析并行

#### 设计思路

基于工具类型建立依赖规则，构建工具执行 DAG，并发执行无依赖的工具。

#### 依赖规则定义

```python
# tools/dependency.py
from dataclasses import dataclass
from enum import Enum

class ToolEffect(Enum):
    READ = "read"       # 只读
    WRITE = "write"     # 写入
    EXECUTE = "execute" # 执行命令

# 依赖规则：
# - READ → READ: 无依赖（可并行）
# - WRITE → READ: 有依赖（同一文件）
# - READ → WRITE: 无依赖
# - WRITE → WRITE: 有依赖（同一文件）
# - EXECUTE: 与所有其他有依赖

def analyze_dependencies(
    tool_calls: list[ToolCall]
) -> dict[str, set[str]]:
    """返回每个工具调用的依赖集"""
    effects = {}
    dependencies = {tc.id: set() for tc in tool_calls}
    
    for tc in tool_calls:
        effect, target = get_tool_effect(tc)
        effects[tc.id] = (effect, target)
    
    # 构建依赖图
    for i, tc1 in enumerate(tool_calls):
        for tc2 in tool_calls[:i]:
            if has_dependency(effects[tc2.id], effects[tc1.id]):
                dependencies[tc1.id].add(tc2.id)
    
    return dependencies
```

#### DAG 执行器

```python
# agent/dag_executor.py
import asyncio

async def execute_dag(
    tool_calls: list[ToolCall],
    dependencies: dict[str, set[str]],
    executor: Callable
) -> dict[str, Any]:
    """按依赖顺序并行执行"""
    results = {}
    completed = set()
    pending = {tc.id: tc for tc in tool_calls}
    
    while pending:
        # 找出可执行的工具（所有依赖已完成）
        ready = [
            tc for tc_id, tc in pending.items()
            if dependencies[tc_id].issubset(completed)
        ]
        
        if not ready:
            raise RuntimeError("循环依赖")
        
        # 并行执行
        tasks = {tc.id: executor(tc) for tc in ready}
        batch_results = await asyncio.gather(*tasks.values())
        
        # 更新状态
        for tc_id, result in zip(tasks.keys(), batch_results):
            results[tc_id] = result
            completed.add(tc_id)
            del pending[tc_id]
    
    return results
```

#### 优点
- 最大化并行度
- 自动处理复杂依赖

#### 缺点
- 实现复杂
- 依赖分析可能不完美
- 调试困难

---

### 方案 3：保持串行（维持现状）

#### 理由

- 当前性能可接受
- 串行简单可靠
- 工具调用以单个为主

#### 适用场景

- 大部分任务是单工具调用
- 多工具并发场景稀少
- 不愿承担并发复杂性

---

## 推荐方案

**推荐方案1（Readonly工具并行）**

理由：
1. **简洁实用**：改动小，效果明显
2. **安全可靠**：只读工具无副作用
3. **性能收益明确**：批量文件读取提速 2-3 倍
4. **可回退**：出问题可快速切回串行

---

## 实施计划

### 阶段 1：工具元数据扩展（立即，1小时）

1. 修改 `tools/types.py`：
   - `ToolDefinition` 添加 `readonly: bool = False`
2. 为所有只读工具添加标记：
   - `read_file`: readonly=True
   - `list_directory`: readonly=True
   - `search_code`: readonly=True
   - `verify_code`: readonly=True

### 阶段 2：并行执行实现（立即，1-2小时）

1. 修改 `agent/agent.py`：
   - 新增 `_execute_tool_calls` 方法
   - 新增 `_execute_parallel` 方法
   - 新增 `_execute_sequential` 方法
2. 修改 `run()` 方法：
   - 调用 `_execute_tool_calls` 替代循环

### 阶段 3：测试验证（立即，1小时）

1. 测试纯只读批次并行
2. 测试混合批次降级到串行
3. 测试单工具调用无影响
4. 测试异常处理

### 阶段 4：性能监控（可选）

1. 添加执行时间日志
2. 对比并行/串行性能
3. 收集真实场景数据

---

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `src/quangan/tools/types.py` | `ToolDefinition` 添加 `readonly` 字段 |
| `src/quangan/coding/tools/read_file.py` | 标记 readonly=True |
| `src/quangan/coding/tools/list_directory.py` | 标记 readonly=True |
| `src/quangan/coding/tools/search_code.py` | 标记 readonly=True |
| `src/quangan/coding/tools/verify_code.py` | 标记 readonly=True |
| `src/quangan/agent/agent.py` | 实现并行执行逻辑 |
