# ReAct 循环推理与任务管理

## 概述

QuanGan 采用 **ReAct（Reasoning + Acting）** 循环作为核心推理机制。Agent 通过迭代执行"思考 → 行动 → 观察"的循环，逐步完成复杂任务。每次 LLM 调用称为一次"迭代"，直到任务完成或达到最大迭代次数。

---

## Agent.run() 完整状态机

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Agent.run() 状态机                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [开始]                                                                       │
│    │                                                                        │
│    ▼                                                                        │
│  ┌─────────────────────────────────┐                                       │
│  │ 1. 重置状态                      │                                       │
│  │    - _aborted = False           │                                       │
│  │    - _cancel_event.clear()      │                                       │
│  └───────────────┬─────────────────┘                                       │
│                  │                                                          │
│    ┌─────────────┴─────────────┐                                            │
│    ▼                           ▼                                            │
│  ┌─────────────────────────────────┐                                       │
│  │ 2. Skill 触发检查                │                                       │
│  │    - 遍历所有未激活 Skill        │                                       │
│  │    - 子串匹配触发词              │                                       │
│  │    - 激活匹配 Skill，注入提示    │                                       │
│  └───────────────┬─────────────────┘                                       │
│                  │                                                          │
│                  ▼                                                          │
│  ┌─────────────────────────────────┐                                       │
│  │ 3. 添加用户消息                  │                                       │
│  │    - messages.append(user_msg)  │                                       │
│  └───────────────┬─────────────────┘                                       │
│                  │                                                          │
│                  ▼                                                          │
│  ┌─────────────────────────────────┐                                       │
│  │ 4. WHILE 循环 (iteration < max) │◄─────────────────────────────┐       │
│  │                                 │                              │       │
│  │  ┌─────────────────────────┐   │                              │       │
│  │  │ 4.1 中断检查            │   │                              │       │
│  │  │  if _aborted: raise     │   │                              │       │
│  │  └───────────┬─────────────┘   │                              │       │
│  │              │                 │                              │       │
│  │              ▼                 │                              │       │
│  │  ┌─────────────────────────┐   │                              │       │
│  │  │ 4.2 构建 LLM 请求        │   │                              │       │
│  │  │  - _get_llm_messages()  │   │                              │       │
│  │  │  - _get_tool_defs()     │   │                              │       │
│  │  └───────────┬─────────────┘   │                              │       │
│  │              │                 │                              │       │
│  │              ▼                 │                              │       │
│  │  ┌─────────────────────────┐   │                              │       │
│  │  │ 4.3 agent_call()        │   │                              │       │
│  │  │  - HTTP 请求 LLM API    │   │                              │       │
│  │  │  - 支持取消事件         │   │                              │       │
│  │  └───────────┬─────────────┘   │                              │       │
│  │              │                 │                              │       │
│  │              ▼                 │                              │       │
│  │  ┌─────────────────────────┐   │                              │       │
│  │  │ 4.4 Token 检查/压缩      │   │                              │       │
│  │  │  if usage >= threshold: │   │                              │       │
│  │  │    await _compress()    │   │                              │       │
│  │  └───────────┬─────────────┘   │                              │       │
│  │              │                 │                              │       │
│  │              ▼                 │                              │       │
│  │  ┌─────────────────────────┐   │                              │       │
│  │  │ 4.5 添加 assistant 消息  │   │                              │       │
│  │  │  messages.append(result)│   │                              │       │
│  │  └───────────┬─────────────┘   │                              │       │
│  │              │                 │                              │       │
│  │              ▼                 │                              │       │
│  │  ┌─────────────────────────┐   │                              │       │
│  │  │ 4.6 有 tool_calls?      │   │                              │       │
│  │  │                         │   │                              │       │
│  │  │  YES: 执行工具          │───┼──────────────────────────────┘       │
│  │  │  - _execute_tool_call() │   │       (继续循环)                      │
│  │  │  - 添加 tool 结果       │   │                                      │
│  │  │  - continue             │───┘                                      │
│  │  │                         │                                          │
│  │  │  NO: 返回最终结果       │                                          │
│  │  │  - return content       │                                          │
│  │  │                         │                                          │
│  │  └─────────────────────────┘                                          │
│  │                                                                       │
│  └─────────────────────────────────┘                                    │
│                  │                                                        │
│                  ▼                                                        │
│  ┌─────────────────────────────────┐                                     │
│  │ 5. 达到最大迭代次数              │                                     │
│  │    raise AgentMaxIterationsError│                                     │
│  └─────────────────────────────────┘                                     │
│                  │                                                        │
│                  ▼                                                        │
│               [结束]                                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 工具调用链路七步骤

### 1. 消息准备 (_get_llm_messages)

```python
def _get_llm_messages(self) -> list[dict[str, Any]]:
    """
    策略（激进压缩）：
    - 找到最新的 _summary 标记消息
    - 包含该消息及之后的所有消息
    - 过滤掉 _archived 消息
    - 发送前剥离所有 _* 元数据
    """
    # 获取系统消息（排除 _summary 标记）
    system_msgs = [m for m in self._messages 
                   if m.get("role") == "system" and not m.get("_summary")]
    
    # 找到最新摘要位置
    last_summary_idx = -1
    for i in range(len(self._messages) - 1, -1, -1):
        if self._messages[i].get("_summary"):
            last_summary_idx = i
            break
    
    # 获取上下文消息
    if last_summary_idx >= 0:
        context_msgs = self._messages[last_summary_idx:]
    else:
        context_msgs = [m for m in self._messages 
                       if not m.get("_archived") and m.get("role") != "system"]
    
    # 剥离元数据
    result = []
    for msg in system_msgs + context_msgs:
        clean_msg = {k: v for k, v in msg.items() if not k.startswith("_")}
        result.append(clean_msg)
    
    return result
```

### 2. 工具定义构建

```python
def _get_tool_definitions(self, plan_only: bool = False) -> list[ToolDefinition]:
    """
    构建工具定义列表。
    plan_only=True 时只包含 readonly 工具（Plan 模式）
    """
    return [
        entry.definition
        for entry in self._tools.values()
        if not plan_only or entry.readonly
    ]
```

### 3. LLM 调用

```python
result = await self._client.agent_call(
    AgentCallRequest(
        messages=self._get_llm_messages(),
        tools=tools if tools else None,
        cancel_event=self._cancel_event,  # 用于中断
    )
)
```

### 4. 响应解析

```python
# 提取消息
message = result.message

# 提取工具调用
tool_calls_raw = message.get("tool_calls", [])
tool_calls = [
    ToolCall(
        id=tc["id"],
        type="function",
        function={
            "name": tc["function"]["name"],
            "arguments": tc["function"]["arguments"],
        },
    )
    for tc in tool_calls_raw
]

# 提取 Token 用量
usage = TokenUsage(
    prompt=usage_data.get("prompt_tokens", 0),
    completion=usage_data.get("completion_tokens", 0),
    total=usage_data.get("total_tokens", 0),
)
```

### 5. Token 检查

```python
if result.usage and result.usage.total >= self._compression_threshold:
    await self._compress_context()  # 触发上下文压缩
```

### 6. 消息历史更新

```python
# 添加 assistant 消息（包含 tool_calls）
self._messages.append(result.message)
```

### 7. 工具执行与反馈

```python
if result.tool_calls:
    for tool_call in result.tool_calls:
        tool_result = await self._execute_tool_call(tool_call)
        self._messages.append(tool_result)  # 添加 tool 结果到历史
    continue  # 继续下一轮迭代
else:
    return result.message.get("content", "")  # 返回最终结果
```

---

## 中断处理机制

### ESC 键中断流程

```
用户按 ESC
    │
    ▼
┌─────────────────────────────┐
│ prompt_toolkit key_binding  │
│ @kb.add("escape")           │
└───────────────┬─────────────┘
                │
                ▼
┌─────────────────────────────┐
│ if is_agent_running:        │
│   agent.abort()             │
└───────────────┬─────────────┘
                │
                ▼
┌─────────────────────────────┐
│ agent.abort() 内部：         │
│ - _aborted = True           │
│ - _cancel_event.set()       │
└───────────────┬─────────────┘
                │
    ┌───────────┴───────────┐
    ▼                       ▼
┌───────────────┐   ┌───────────────────┐
│ 双重检查点 1   │   │ 双重检查点 2      │
│ HTTP 请求取消  │   │ 循环头部检查      │
│               │   │                   │
│ client.post() │   │ if _aborted:      │
│ 前检查 cancel │   │   raise           │
│ _event        │   │   InterruptedError│
└───────────────┘   └───────────────────┘
```

### 代码实现

```python
# src/quangan/agent/agent.py

def abort(self) -> None:
    """
    中断运行中的 Agent。
    设置中断标志和取消事件，这将：
    1. 停止当前 HTTP 请求（通过 cancel_event）
    2. 在 run 循环中抛出 AgentInterruptedError
    """
    self._aborted = True
    self._cancel_event.set()

async def run(self, user_message: str, plan_only: bool = False) -> str:
    # ... 初始化 ...
    
    while iteration < self._max_iterations:
        # 检查点 2：循环头部检查
        if self._aborted:
            self._aborted = False
            raise AgentInterruptedError()
        
        iteration += 1
        
        # 清除取消事件，准备新的 HTTP 请求
        self._cancel_event.clear()
        
        try:
            # 检查点 1：HTTP 请求内部检查
            result = await self._client.agent_call(
                AgentCallRequest(
                    messages=self._get_llm_messages(),
                    tools=tools if tools else None,
                    cancel_event=self._cancel_event,  # 传递给客户端
                )
            )
        except asyncio.CancelledError:
            if self._aborted:
                self._aborted = False
                raise AgentInterruptedError()
            raise
```

---

## 最大迭代控制

| Agent 类型 | 最大迭代次数 | 说明 |
|------------|--------------|------|
| 主 Agent | 50 | 处理复杂多步骤任务，支持多次子 Agent 调用 |
| Coding Agent | 30 | 代码任务通常需要多轮文件读写和验证 |
| Daily Agent | 20 | 日常任务相对简单，快速完成 |

```python
# AgentConfig 默认值
@dataclass
class AgentConfig:
    max_iterations: int = 50  # 主 Agent 默认

# Coding Agent 配置
config = AgentConfig(
    max_iterations=30,  # 覆盖默认值
    ...
)

# Daily Agent 配置
config = AgentConfig(
    max_iterations=20,  # 覆盖默认值
    ...
)
```

---

## 错误处理策略

### 工具执行异常捕获

```python
async def _execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
    try:
        args = json.loads(tool_call["function"]["arguments"])
        result = entry.implementation(args)
        if inspect.isawaitable(result):
            result = await result
        
        return ToolResult(
            tool_call_id=tool_call["id"],
            role="tool",
            name=tool_name,
            content=str(result),
        )
    except Exception as e:
        # 捕获所有异常，返回错误信息
        return ToolResult(
            tool_call_id=tool_call["id"],
            role="tool",
            name=tool_name,
            content=f"工具执行失败: {e}",
        )
```

### LLM 自主重试

工具执行错误会作为消息返回给 LLM，LLM 可以：
- 分析错误原因
- 调整参数重新调用
- 改用其他工具
- 向用户说明失败原因

### 压缩失败静默

```python
async def _compress_context(self) -> None:
    try:
        summary = await self._client.chat(...)
    except Exception:
        return  # 静默失败，不中断主流程
```

---

## 自我修正场景

### 场景1：工具返回错误 → LLM 调整策略

```
[迭代 1]
Assistant: 调用 read_file("config.yaml")
Tool: 错误：文件不存在 config.yaml

[迭代 2]
Assistant: 调用 list_directory(".")
Tool: 返回目录列表，包含 "config.json"

[迭代 3]
Assistant: 调用 read_file("config.json")
Tool: 返回文件内容

[迭代 4]
Assistant: 成功读取配置，继续任务...
```

### 场景2：代码修改 → 验证 → 修正

```
[迭代 1]
Assistant: 调用 edit_file 修改 utils.py

[迭代 2]
Assistant: 调用 verify_code("utils.py")
Tool: 发现语法错误：第 15 行缺少冒号

[迭代 3]
Assistant: 调用 edit_file 修正第 15 行语法错误

[迭代 4]
Assistant: 调用 verify_code("utils.py")
Tool: 验证通过，无错误

[迭代 5]
Assistant: 代码修改完成并通过验证
```

### 场景3：信息不足 → 多次调用补充

```
用户："优化这个函数的性能"

[迭代 1]
Assistant: 调用 read_file("module.py", lines=[1, 50]) 读取函数定义

[迭代 2]
Assistant: 调用 search_code("调用这个函数的地方") 了解使用场景

[迭代 3]
Assistant: 调用 read_file("module.py", lines=[100, 150]) 读取相关代码

[迭代 4]
Assistant: 基于完整信息，调用 edit_file 进行优化
```

---

## Plan Mode（规划模式）

### 激活方式

用户输入 `/plan` 命令激活规划模式。

### 模式特点

```python
# src/quangan/cli/main.py

if is_plan_mode:
    message_to_send = f"""[当前处于规划模式，你只能使用只读工具分析代码，禁止修改任何文件]

请按以下步骤完成任务：
1. 使用只读工具（read_file、list_directory、search_code）充分分析相关代码和文件
2. 分析完成后，输出一份清晰的执行计划，格式如下：

📋 执行计划
Step 1: [具体操作描述]
Step 2: [具体操作描述]
...

注意：只输出计划，不要真正修改文件。

用户任务：{text}"""
```

### 工具限制

```python
def _get_tool_definitions(self, plan_only: bool = False) -> list[ToolDefinition]:
    return [
        entry.definition
        for entry in self._tools.values()
        if not plan_only or entry.readonly  # Plan 模式只读
    ]
```

### 只读工具标记

```python
# 注册工具时标记 readonly
agent.register_tool(
    definition=read_file_def,
    implementation=read_file_impl,
    readonly=True  # Plan 模式可用
)

agent.register_tool(
    definition=edit_file_def,
    implementation=edit_file_impl,
    readonly=False  # Plan 模式不可用
)
```

---

## 相关文件

| 文件 | 职责 |
|------|------|
| `src/quangan/agent/agent.py` | Agent 类，ReAct 循环核心实现 |
| `src/quangan/cli/main.py` | CLI 层，Plan 模式实现，中断绑定 |
| `src/quangan/llm/client.py` | LLM 客户端，支持取消事件 |
| `src/quangan/llm/types.py` | AgentCallRequest/AgentCallResponse 类型定义 |

---

## 交叉引用

- 系统总览：[系统架构总览](system-overview.md)
- 多 Agent 协作：[多Agent协作机制](multi-agent.md)
- 上下文压缩：[上下文压缩算法](context-compression.md)
