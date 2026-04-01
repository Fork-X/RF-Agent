# 多Agent协作机制

## 概述

QuanGan 采用**主-从式多 Agent 架构**，主 Agent "小枫"作为中央协调器，根据任务类型动态创建并调用专业子 Agent 完成具体工作。这种设计实现了关注点分离，让每个 Agent 专注于特定领域。

---

## 主Agent "小枫"初始化过程

### 系统提示构建

```python
# src/quangan/cli/main.py

system_prompt = f"""你叫小枫，是芮枫的私人助理。

## 你是谁
你是芮枫一手打造的私人助理，小枫。性格聪明温柔，说话自然随和...

## 技能与工作方式
你内部有两个助手，可以通过工具调用完成不同类型的任务：
- coding_agent：处理代码相关任务（读写文件、执行命令、代码搜索等）
- daily_agent：处理日常任务（打开应用、网页搜索、系统命令等）

根据芮枫的需求分析任务类型并调用合适的助手完成。

## 记忆使用指南
你拥有 recall_memory 工具可以检索记忆...{memory_context}"""
```

系统提示包含三个关键部分：
1. **角色定义**：身份、性格、自我介绍方式
2. **子 Agent 职责声明**：明确 coding_agent 和 daily_agent 的功能边界
3. **Core Memory 注入**：将长期记忆以格式化文本嵌入系统提示

### AgentConfig配置

```python
agent_config = AgentConfig(
    client=client,                    # LLM 客户端实例
    system_prompt=system_prompt,      # 上述构建的系统提示
    max_iterations=50,                # 主 Agent 最大迭代次数
    skill_loader=skill_loader,        # Skill 加载器
    enable_skill_triggers=True,       # 启用 Skill 自动触发
    on_tool_call=...,                 # 工具调用回调（UI 显示）
    on_tool_result=...,               # 工具结果回调
    on_compress_start=...,            # 压缩开始回调（触发 Life Memory 更新）
    on_compress=...,                  # 压缩完成回调
)
```

---

## 子Agent动态创建

### 无状态设计原则

子 Agent 采用**无状态设计**，每次调用都创建全新实例：

```python
# src/quangan/cli/main.py

async def coding_agent_handler(args: dict[str, Any]) -> str:
    # 每次调用都创建新的 Coding Agent 实例
    coding_agent = create_coding_agent(client, CWD, {
        **sub_agent_callbacks,
        "confirm": make_confirm_fn(session),  # 危险操作确认回调
    })
    return await coding_agent.run(args["task"])

async def daily_agent_handler(args: dict[str, Any]) -> str:
    # 每次调用都创建新的 Daily Agent 实例
    daily_agent = create_daily_agent(client, sub_agent_callbacks)
    return await daily_agent.run(args["task"])
```

**设计原因**：
- 隔离性：子 Agent 之间的任务不会相互干扰
- 简洁性：无需管理子 Agent 生命周期和状态同步
- 安全性：每次从干净状态开始，避免历史消息污染

### 工厂模式实现

```python
# src/quangan/agents/coding/__init__.py

def create_coding_agent(
    client: ILLMClient,
    work_dir: str,
    callbacks: dict[str, Callable] | None = None,
) -> Agent:
    system_prompt = f"""你是一个专业的 Coding Agent，负责代码相关任务。

## 工作方式
你可以直接使用工具完成以下操作：
- 读取、创建、编辑文件
- 列出目录内容
- 执行 shell 命令
- 搜索代码
- 验证代码

## 注意事项
1. 修改代码后，使用 verify_code 检查是否有语法或类型错误
2. 使用 execute_command 时，危险操作会要求用户确认
3. 文件路径优先使用绝对路径

当前工作目录: {work_dir}"""

    config = AgentConfig(
        client=client,
        system_prompt=system_prompt,
        max_iterations=30,  # Coding Agent 迭代限制
        ...
    )
    
    agent = Agent(config)
    
    # 注册 Coding 专用工具
    from .tools import create_all_coding_tools
    tools = create_all_coding_tools(work_dir, confirm_fn)
    for definition, implementation, readonly in tools:
        agent.register_tool(definition, implementation, readonly)
    
    return agent
```

---

## 任务路由策略

### LLM智能决策（非硬编码）

任务路由不由代码硬编码，而是由 LLM 根据工具描述自主决策：

```python
# src/quangan/cli/main.py

coding_agent_def: ToolDefinition = make_tool_definition(
    name="coding_agent",
    description="调用 Coding Agent 完成代码相关任务，例如：阅读/修改/创建代码文件、执行命令、搜索代码、调试程序等",
    parameters={"task": {"type": "string", "description": "要完成的代码任务，请尽量详细描述需求和背景"}},
    required=["task"],
)

daily_agent_def: ToolDefinition = make_tool_definition(
    name="daily_agent",
    description="调用 Daily Agent 完成日常任务，例如：打开应用、打开网址/搜索、执行系统命令、回答知识性问题等",
    parameters={"task": {"type": "string", "description": "要完成的日常任务，请尽量详细描述需求"}},
    required=["task"],
)
```

LLM 根据 `description` 中的关键词判断任务类型：
- 包含"代码"、"文件"、"修改"、"调试" → 选择 `coding_agent`
- 包含"打开"、"搜索"、"播放"、"查询" → 选择 `daily_agent`

### 支持串行调用多个子Agent

主 Agent 可以在一次对话中串行调用多个子 Agent：

```
用户: "先帮我查一下 Python 装饰器的用法，然后在 utils.py 里添加一个计时装饰器"
    │
    ▼
主 Agent 第1轮: 调用 daily_agent("查 Python 装饰器用法")
    │
    ▼
主 Agent 第2轮: 基于查询结果，调用 coding_agent("在 utils.py 添加计时装饰器")
    │
    ▼
主 Agent 返回最终结果
```

---

## 各Agent工具集对比

| Agent | 最大迭代 | 工具列表 | 适用场景 |
|-------|----------|----------|----------|
| **主 Agent** | 50 | `coding_agent`, `daily_agent`, `recall_memory`, `update_life_memory`, `consolidate_core_memory` | 任务分析、路由决策、记忆管理 |
| **Coding Agent** | 30 | `read_file`, `write_file`, `edit_file`, `list_directory`, `execute_command`, `search_code`, `verify_code` | 代码读写、文件操作、命令执行、代码验证 |
| **Daily Agent** | 20 | `open_app`, `open_url`, `run_shell`, `run_applescript`, `browser_action` | 应用启动、网页浏览、系统自动化 |

### 工具详细说明

**Coding Agent 工具：**
- `read_file`: 读取文件内容，支持指定行范围
- `write_file`: 创建新文件或覆盖写入
- `edit_file`: 精确编辑（搜索替换）
- `list_directory`: 列出目录内容
- `execute_command`: 执行 shell 命令（危险操作需确认）
- `search_code`: 代码语义搜索
- `verify_code`: 语法和类型检查

**Daily Agent 工具：**
- `open_app`: 打开 macOS 应用程序
- `open_url`: 打开网址或 Google 搜索
- `run_shell`: 执行 shell 命令
- `run_applescript`: 执行 AppleScript（macOS 自动化）
- `browser_action`: 浏览器自动化（Playwright）

---

## Agent间通信实现

### 单向同步调用

```
┌─────────────┐     工具调用      ┌─────────────┐
│   主 Agent   │ ───────────────▶ │   子 Agent   │
│             │                  │             │
│             │ ◀─────────────── │             │
└─────────────┘   字符串结果      └─────────────┘
```

- **调用方式**：主 Agent 通过 `tool_call` 调用子 Agent handler
- **参数传递**：通过 `args["task"]` 传递任务描述字符串
- **结果返回**：子 Agent 返回结果字符串，主 Agent 继续推理

### 字符串序列化

所有通信通过字符串进行：

```python
# 主 Agent → 子 Agent
task_description = """
请修改 src/utils.py 文件：
1. 在文件末尾添加一个日志函数 log_info(message)
2. 使用标准 logging 模块
3. 添加类型注解
"""

# 子 Agent → 主 Agent
result = """
已完成修改：
- 在 src/utils.py 第 45 行添加了 log_info 函数
- 使用了 logging.getLogger(__name__)
- 添加了完整的类型注解和文档字符串
- verify_code 检查通过，无语法错误
"""
```

### 消息历史隔离

```
主 Agent 消息历史：
[system] 你是小枫...
[user] 帮我修改 utils.py
[assistant] 我来帮你修改（调用 coding_agent）
[tool] coding_agent 返回结果...
[assistant] 已完成修改...

子 Agent 消息历史（独立）：
[system] 你是 Coding Agent...
[user] 修改 utils.py，添加日志函数...
[assistant] 我来读取文件（调用 read_file）...
[tool] read_file 返回内容...
[assistant] 我来编辑文件（调用 edit_file）...
...
```

子 Agent 的消息历史完全隔离，不会污染主 Agent 的上下文。

### 不支持Agent间直接通信

- 子 Agent **不能**直接调用其他子 Agent
- 子 Agent **不能**访问主 Agent 的消息历史
- 所有跨 Agent 通信必须通过主 Agent 中转

---

## 系统提示差异化设计

### 主 Agent 系统提示特点

- **角色定位**：私人助理，语气自然随和
- **决策导向**：强调分析任务类型、选择合适工具
- **记忆集成**：注入 Core Memory，了解用户偏好
- **社交属性**：会闲聊、会问候、不过度列举能力

### Coding Agent 系统提示特点

- **专业定位**：代码专家，专注技术实现
- **操作导向**：明确列出可用工具及其用途
- **安全提醒**：强调 verify_code 和危险操作确认
- **工作目录**：明确告知当前工作目录

### Daily Agent 系统提示特点

- **实用定位**：日常助手，快速完成任务
- **示例丰富**：提供 ncm-cli 音乐命令示例
- **浏览器说明**：详细列出 browser_action 支持的操作
- **直接执行**：强调"直接使用工具完成，不要让用户手动执行"

---

## 相关文件

| 文件 | 职责 |
|------|------|
| `src/quangan/cli/main.py` | 主 Agent 初始化，子 Agent handler 注册 |
| `src/quangan/agents/coding/__init__.py` | Coding Agent 工厂函数 |
| `src/quangan/agents/daily/__init__.py` | Daily Agent 工厂函数 |
| `src/quangan/agents/coding/tools/` | Coding Agent 专用工具实现 |
| `src/quangan/agents/daily/tools/` | Daily Agent 专用工具实现 |
| `src/quangan/agent/agent.py` | Agent 基类，工具注册机制 |

---

## 交叉引用

- 系统总览：[系统架构总览](system-overview.md)
- ReAct 循环实现：[ReAct循环与任务管理](react-loop.md)
- 记忆系统：[记忆系统架构](memory-system.md)
