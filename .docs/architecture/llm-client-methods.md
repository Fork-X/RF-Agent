# QuanGan LLM 客户端方法设计

## 概述

QuanGan 的 LLM 客户端采用**分层抽象设计**，提供从简单到完整的多种调用方式，满足不同场景的需求。

```
┌─────────────────────────────────────────────────────────────┐
│                    ILLMClient 协议                          │
├─────────────────────────────────────────────────────────────┤
│  ask()        → 最简接口，单轮 Q&A                           │
│  chat()       → 标准接口，多轮对话                           │
│  chat_stream()→ 流式接口，实时输出                           │
│  agent_call() → 完整接口，工具调用 + 取消机制                │
└─────────────────────────────────────────────────────────────┘
```

---

## 方法对比

| 方法 | 输入 | 输出 | 核心用途 | 复杂度 |
|------|------|------|----------|--------|
| `ask(question, system_prompt)` | 简单字符串 | `str` | 单轮 Q&A 快捷方法 | ⭐ |
| `chat(messages, options)` | 消息列表 + 选项 | `str` | 标准多轮对话 | ⭐⭐ |
| `chat_stream(messages, options)` | 消息列表 + 选项 | `AsyncGenerator[str]` | 实时流式输出 | ⭐⭐⭐ |
| `agent_call(request)` | `AgentCallRequest` | `AgentCallResponse` | Agent 工具调用 | ⭐⭐⭐⭐ |

---

## 详细说明

### 1. `ask()` - 便捷单轮问答

**签名**：
```python
async def ask(self, question: str, system_prompt: str | None = None) -> str
```

**实现原理**：
```python
async def ask(self, question: str, system_prompt: str | None = None) -> str:
    messages: list[ChatMessage] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": question})
    return await self.chat(messages)
```

**应用场景**：
- 快速提问，无需构造消息列表
- 内部工具调用（如记忆整合、摘要生成）
- 简单的单轮任务

**使用示例**（`tools.py` 记忆整合）：
```python
result = await client.ask(
    prompt, 
    "你是记忆整合助手，只输出纯 JSON，不加任何说明。"
)
```

**设计意图**：
- 封装最简，一行代码完成单轮对话
- 隐藏消息列表构造细节
- 适合非对话类的一次性调用

---

### 2. `chat()` - 标准多轮对话

**签名**：
```python
async def chat(
    self, 
    messages: list[ChatMessage], 
    options: ChatOptions | None = None
) -> str
```

**应用场景**：
- 需要多轮上下文的多轮对话
- 需要自定义 temperature、max_tokens 等参数
- 上下文压缩时调用

**使用示例**（`agent.py` 上下文压缩）：
```python
summary = await self._client.chat([
    {"role": "system", "content": "你是一个对话摘要助手..."},
    {"role": "user", "content": f"请将以下对话历史压缩成简洁摘要..."},
])
```

**设计意图**：
- 标准接口，满足大多数对话需求
- 支持参数自定义（temperature、max_tokens、top_p）
- 返回纯文本，便于后续处理

---

### 3. `chat_stream()` - 流式输出

**签名**：
```python
async def chat_stream(
    self, 
    messages: list[ChatMessage], 
    options: ChatOptions | None = None
) -> AsyncGenerator[str, None]
```

**应用场景**：
- 需要实时显示生成内容的场景
- 长文本生成，提升用户体验
- 当前代码中**未使用**，为未来预留

**设计意图**：
- 支持 SSE (Server-Sent Events) 流式输出
- 逐字/逐句返回，提升交互体验
- 为后续 UI 优化预留接口

---

### 4. `agent_call()` - Agent 工具调用

**签名**：
```python
async def agent_call(self, req: AgentCallRequest) -> AgentCallResponse
```

**特殊能力**：
- 支持 **Function Calling / Tool Calling**
- 支持 **取消机制**（`cancel_event`）
- 返回 **完整响应结构**（消息 + 工具调用 + Token 用量）

**请求结构**：
```python
@dataclass
class AgentCallRequest:
    messages: list[dict[str, Any]]    # 消息历史
    tools: list[ToolDefinition] | None = None  # 可用工具
    cancel_event: asyncio.Event | None = None  # 取消事件
```

**响应结构**：
```python
@dataclass
class AgentCallResponse:
    message: dict[str, Any]           # 助手消息
    tool_calls: list[ToolCall] | None = None  # 工具调用请求
    usage: TokenUsage | None = None   # Token 用量统计
```

**应用场景**：
- Agent 主循环中的工具调用
- 需要判断是否需要调用工具的场景
- 需要统计 Token 用量的场景

**使用示例**（`agent.py` 主循环）：
```python
result = await self._client.agent_call(
    AgentCallRequest(
        messages=self._get_llm_messages(),
        tools=tools if tools else None,
        cancel_event=self._cancel_event,
    )
)

# 处理工具调用
if result.tool_calls and len(result.tool_calls) > 0:
    for tool_call in result.tool_calls:
        tool_result = await self._execute_tool_call(tool_call)
```

**设计意图**：
- 最完整的接口，支持 Agent 所需的所有功能
- 结构化输入输出，便于类型检查
- 支持中断控制（ESC 键取消）

---

## 设计原则

### 1. 分层抽象

```
ask (最简) → chat (标准) → chat_stream (流式) → agent_call (完整)
     ↑           ↑              ↑                    ↑
   便捷性      灵活性         实时性              功能性
```

- **`ask`**：封装到最简，一行代码完成单轮对话
- **`chat`**：标准接口，满足大多数对话需求
- **`chat_stream`**：流式输出，提升用户体验
- **`agent_call`**：完整功能，支持工具调用和取消

### 2. 职责分离

| 方法 | 职责 | 使用场景 |
|------|------|----------|
| `ask` | 内部工具、快捷调用 | 记忆整合、主题提取 |
| `chat` | 通用对话、摘要生成 | 上下文压缩 |
| `chat_stream` | 实时输出（预留） | 未来 UI 优化 |
| `agent_call` | Agent 核心循环 | 主对话循环 |

### 3. 协议统一

`ILLMClient` 协议定义统一接口，支持多协议实现：

```python
@runtime_checkable
class ILLMClient(Protocol):
    async def ask(self, question: str, system_prompt: str | None = None) -> str: ...
    async def chat(self, messages: list[ChatMessage], options: ChatOptions | None = None) -> str: ...
    async def chat_stream(self, messages: list[ChatMessage], options: ChatOptions | None = None) -> AsyncGenerator[str, None]: ...
    async def agent_call(self, req: AgentCallRequest) -> AgentCallResponse: ...
```

**实现类**：
- `LLMClient`：OpenAI 兼容协议（DashScope、Kimi、OpenAI）
- `AnthropicClient`：Anthropic Messages API

上层代码无需关心底层协议差异。

---

## 实际使用分布

```
src/quangan/
├── agent/agent.py
│   ├── chat()       → 上下文压缩摘要 (第 269-277 行)
│   └── agent_call() → Agent 主循环 (第 463-470 行)
│
├── memory/tools.py
│   └── ask()        → 记忆整合、主题提取 (第 138-146, 176 行)
│
└── llm/client.py
    └── 所有方法的实现定义
```

---

## 相关文件

| 文件 | 职责 |
|------|------|
| `src/quangan/llm/types.py` | 类型定义（ILLMClient 协议、数据类） |
| `src/quangan/llm/client.py` | LLMClient 实现（OpenAI 协议） |
| `src/quangan/llm/anthropic_client.py` | AnthropicClient 实现（Anthropic 协议） |
