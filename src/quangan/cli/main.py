"""
QuanGan CLI main entry point.

This is the main orchestrator that:
- Initializes LLM client and configuration
- Creates the main Agent "小枫" with sub-agents as tools
- Runs the REPL loop with prompt_toolkit
- Handles commands, provider switching, and memory integration
"""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

from quangan.agent.agent import Agent, AgentConfig, AgentInterruptedError
from quangan.agents.coding import create_coding_agent
from quangan.agents.daily import create_daily_agent
from quangan.cli import display
from quangan.cli.command_picker import start_command_picker
from quangan.cli.display import console
from quangan.cli.session_store import SESSIONS_DIR, clear_session, load_session, save_session
from quangan.config.llm_config import (
    PROVIDERS,
    LLMConfig,
    get_model_context_limit,
    load_config_from_env,
)
from quangan.llm.client import create_llm_client
from quangan.memory import MEMORY_BASE_DIR, create_memory_tools, get_core_memory
from quangan.skills import SkillLoader
from quangan.tools.types import ToolDefinition, make_tool_definition
from quangan.trace import TraceWriter

# ─────────────────────────────────────────────────────────────────────────────
# Environment file path
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


# ─────────────────────────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────────────────────────

# These are module-level to allow access from keypress handlers
config: LLMConfig
client: Any
agent: Agent
MODEL_MAX_TOKENS: int
CWD: str
is_plan_mode = False
is_agent_running = False
current_spinner: Any = None
_life_memory_update_count = 0


# ─────────────────────────────────────────────────────────────────────────────
# Tool definitions for sub-agents
# ─────────────────────────────────────────────────────────────────────────────

coding_agent_def: ToolDefinition = make_tool_definition(
    name="coding_agent",
    description=(
        "调用 Coding Agent 完成代码相关任务，"
        "例如：阅读/修改/创建代码文件、执行命令、搜索代码、调试程序等"
    ),
    parameters={
        "task": {
            "type": "string",
            "description": "用户的原始代码需求，保留用户原话和背景，不要自行规划实现步骤",
        },
    },
    required=["task"],
)

daily_agent_def: ToolDefinition = make_tool_definition(
    name="daily_agent",
    description=(
        "调用 Daily Agent 完成日常任务，"
        "例如：打开应用、打开网址/搜索、执行系统命令、回答知识性问题等"
    ),
    parameters={
        "task": {
            "type": "string",
            "description": "用户的原始需求，保留用户原话，不要自行规划实现方式",
        },
    },
    required=["task"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Confirmation callback for execute_command safety
# ─────────────────────────────────────────────────────────────────────────────


def make_confirm_fn(session: PromptSession) -> Callable[[str], Any]:
    """Create confirmation callback for path safety checks."""

    async def confirm_fn(msg: str) -> bool:
        display.print_system(f"⚠️ 安全确认\n{msg}\n确认执行？ [y/N]")
        # Use sync confirm since we're in a complex state
        result = input("[y/N] ").strip().lower()
        return result in ("y", "yes")

    return confirm_fn


# ─────────────────────────────────────────────────────────────────────────────
# Memory integration
# ─────────────────────────────────────────────────────────────────────────────


async def update_life_memory_async() -> None:
    """Update life memory on context compression (fire-and-forget)."""
    global _life_memory_update_count

    try:
        # Get recent non-archived messages
        history = [
            msg
            for msg in agent.get_history()
            if not msg.get("_archived") and msg.get("role") != "system"
        ]

        if not history:
            return

        # Build summary prompt
        history_text = "\n\n".join(
            f"[{'用户' if m.get('role') == 'user' else 'Agent'}]: {str(m.get('content', ''))[:400]}"
            for m in history
        )

        summary = await client.ask(
            f"请将以下对话提炼为简洁的日常记忆摘要（150字以内）：\n\n{history_text}",
            "你是记忆整合助手，请用简洁中文生成摘要。",
        )

        theme = await client.ask(
            f"根据以下摘要，提取一个简短的主题词（3-8字）：\n\n{summary}",
            "只输出主题词，不要其他内容。",
        )

        from quangan.memory import append_life_memory

        append_life_memory(str(MEMORY_BASE_DIR), theme.strip(), summary)

        _life_memory_update_count += 1

        # Every 3 compressions, trigger consolidation
        if _life_memory_update_count % 3 == 0:
            from quangan.memory import create_memory_tool_impls

            impls = create_memory_tool_impls(client, str(MEMORY_BASE_DIR))
            await impls["consolidate_impl"]()

    except Exception:
        # Silent failure
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Provider management
# ─────────────────────────────────────────────────────────────────────────────


def is_valid_api_key(key: str | None) -> bool:
    """Check if an API key is valid (not a placeholder)."""
    if not key:
        return False
    if len(key) < 20:
        return False
    if re.match(r"^(.)\1+$", key):
        return False
    if re.search(r"your[_-]?", key, re.IGNORECASE):
        return False
    return True


def persist_env(key: str, value: str) -> None:
    """Persist a key-value pair to .env file."""
    try:
        content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
        line = f"{key}={value}"
        pattern = re.compile(f"^{key}=.*$", re.MULTILINE)

        if pattern.search(content):
            content = pattern.sub(line, content)
        else:
            content = content.rstrip("\n") + f"\n{line}\n"

        ENV_FILE.write_text(content, encoding="utf-8")
    except Exception:
        pass


def switch_provider(name: str) -> None:
    """Switch to a different LLM provider."""
    global config, client, MODEL_MAX_TOKENS

    preset = PROVIDERS.get(name)
    if not preset:
        display.print_error(f"未知供应商: {name}")
        return

    prefix = name.replace("-", "_").upper()
    api_key = os.environ.get(f"{prefix}_API_KEY", "")

    if not is_valid_api_key(api_key):
        display.print_error(f"{name} 未配置有效 API Key")
        return

    new_model = os.environ.get(f"{prefix}_MODEL") or preset.default_model

    config = LLMConfig(
        provider=name,
        api_key=api_key,
        base_url=preset.base_url,
        model=new_model,
        headers=preset.headers,
        protocol=preset.protocol,
    )

    client = create_llm_client(config)
    MODEL_MAX_TOKENS = get_model_context_limit(config.model)
    agent.update_client(client)

    # Re-register memory tools (uses new client)
    memory_tools = create_memory_tools(client, str(MEMORY_BASE_DIR))
    for definition, implementation, readonly in memory_tools:
        agent.register_tool(definition, implementation, readonly)

    proto_label = " [Anthropic 协议]" if preset.protocol == "anthropic" else ""
    display.print_system(f"✅ 已切换至 {name}{proto_label} | 模型：{new_model}")


async def show_provider_picker(session: PromptSession) -> None:
    """Show interactive provider picker."""
    # Build provider list
    provider_items = []

    for name, preset in PROVIDERS.items():
        prefix = name.replace("-", "_").upper()
        api_key = os.environ.get(f"{prefix}_API_KEY", "")
        provider_items.append(
            {
                "name": name,
                "model": os.environ.get(f"{prefix}_MODEL") or preset.default_model,
                "active": name == config.provider,
                "configured": is_valid_api_key(api_key),
                "preset": preset,
            }
        )

    selected = 0

    def render() -> None:
        console.print("[dim]  ↑↓ 选择  Enter 确认  Esc 取消[/]")
        for i, p in enumerate(provider_items):
            prefix = "[cyan]  ▶ [/]" if i == selected else "     "
            dot = "[green] ●[/]" if p["active"] else "  "
            badge = "[yellow] [未配置][/]" if not p["configured"] else ""
            name_str = f"{p['name']:<12}"

            if i == selected:
                console.print(f"{prefix}{dot} [bold cyan]{name_str}[/]{p['model']}{badge}")
            elif p["configured"]:
                console.print(f"{prefix}{dot} [dim]{name_str}{p['model']}[/]")
            else:
                console.print(f"{prefix}{dot} [dim]{name_str}{p['model']}[/][dim]{badge}[/]")

    console.print()
    render()

    # Use prompt_toolkit key handling
    kb = KeyBindings()

    done = False
    result_name: str | None = None

    @kb.add("up")
    def up(event: Any) -> None:
        nonlocal selected
        selected = (selected - 1) % len(provider_items)
        console.print(f"\033[{len(provider_items) + 1}A\033[J")
        render()

    @kb.add("down")
    def down(event: Any) -> None:
        nonlocal selected
        selected = (selected + 1) % len(provider_items)
        console.print(f"\033[{len(provider_items) + 1}A\033[J")
        render()

    @kb.add("enter")
    def enter(event: Any) -> None:
        nonlocal done, result_name
        result_name = provider_items[selected]["name"]
        done = True
        event.app.exit()

    @kb.add("escape")
    def escape(event: Any) -> None:
        nonlocal done
        done = True
        event.app.exit()

    # Create a simple app for key handling
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.controls import BufferControl

    buffer = Buffer()
    control = BufferControl(buffer=buffer)
    from prompt_toolkit.layout import Window

    app = Application(layout=Layout(Window(control)), key_bindings=kb)
    await app.run_async()

    # Clear the menu
    console.print(f"\033[{len(provider_items) + 2}A\033[J", end="")

    if result_name:
        p = provider_items[selected]
        if not p["configured"]:
            # Prompt for API key
            console.print(f"[yellow]🔑 配置 {result_name}[/]")
            api_key_input = input("  API Key > ").strip()
            if not api_key_input:
                display.print_system("已取消")
                return

            prefix = result_name.replace("-", "_").upper()
            os.environ[f"{prefix}_API_KEY"] = api_key_input
            persist_env(f"{prefix}_API_KEY", api_key_input)

            model_input = input(f"  模型名称 (回车使用默认 {p['model']}): ").strip()
            if model_input:
                os.environ[f"{prefix}_MODEL"] = model_input
                persist_env(f"{prefix}_MODEL", model_input)

            switch_provider(result_name)
            display.print_system("✅ 配置已保存到 .env")
        else:
            switch_provider(result_name)


# ─────────────────────────────────────────────────────────────────────────────
# Command handling
# ─────────────────────────────────────────────────────────────────────────────


async def handle_command(cmd: str, session: PromptSession) -> bool:
    """Handle a slash command. Returns True if handled."""
    global is_plan_mode

    cmd = cmd.strip()

    if cmd == "/help":
        display.print_help()
        return True

    if cmd == "/clear":
        agent.clear_history()
        archived = clear_session(CWD)
        console.clear()
        display.print_header(config.model)
        if archived:
            display.print_system(f"📦 旧对话已归档：{archived}")
        display.print_system("已开启新对话")
        return True

    if cmd == "/history":
        display.print_history(agent.get_history())
        return True

    if cmd == "/tools":
        from quangan.tools.browser import create_browser_tools
        from quangan.tools.code import create_code_tools
        from quangan.tools.command import create_command_tools, create_shell_tools
        from quangan.tools.filesystem import create_filesystem_tools
        from quangan.tools.system import create_system_tools

        # Collect all tools
        coding_tools = (
            create_filesystem_tools()
            + create_code_tools()
            + create_command_tools("", None)
        )
        daily_tools = (
            create_system_tools()
            + create_browser_tools()
            + create_shell_tools()
        )

        tool_names = [f"  [coding] {t[0]['function']['name']}" for t in coding_tools] + [
            f"  [daily]  {t[0]['function']['name']}" for t in daily_tools
        ]
        display.print_tool_list(tool_names)
        return True

    if cmd == "/skills":
        skills = agent.list_skills()
        if skills:
            console.print("\n[bold cyan]已加载的 Skills:[/]")
            for skill in skills:
                active = "[green]●[/]" if skill in agent.get_active_skills() else "[dim]○[/]"
                console.print(f"  {active} [bold]{skill.name}[/] - {skill.description}")
                if skill.metadata.triggers:
                    triggers = ", ".join(skill.metadata.triggers[:5])
                    console.print(f"     [dim]触发词: {triggers}[/]")
        else:
            console.print("\n[yellow]暂无已加载的 Skills[/]")
        console.print()
        return True

    if cmd == "/plan":
        is_plan_mode = True
        display.print_mode_switch(True)
        return True

    if cmd == "/exec":
        is_plan_mode = False
        display.print_mode_switch(False)
        return True

    if cmd == "/provider":
        await show_provider_picker(session)
        return True

    if cmd in ("/exit", "/quit"):
        display.print_divider()
        display.print_system("再见！👋")
        import sys

        sys.exit(0)

    if cmd.startswith("/provider "):
        switch_provider(cmd[len("/provider ") :].strip())
        return True

    display.print_error(f"未知命令: {cmd}，输入 /help 查看命令列表")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Message processing
# ─────────────────────────────────────────────────────────────────────────────


async def process_user_message(text: str, session: PromptSession) -> None:
    """Process user message and get agent response."""
    global is_agent_running, current_spinner

    # Inject plan mode instructions if needed
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
    else:
        message_to_send = text

    is_agent_running = True

    with display.create_spinner("Agent 思考中... [dim](Esc 可中断)[/]") as spinner:
        current_spinner = spinner

        try:
            response = await agent.run(message_to_send, is_plan_mode)
            current_spinner = None

            display.print_assistant_message(response)

            # Show token usage
            usage = agent.get_token_usage()
            display.print_token_usage(usage.total, MODEL_MAX_TOKENS)

            # Save session
            save_session(CWD, agent.get_history())

        except AgentInterruptedError:
            current_spinner = None
            display.print_system("⚡ 调用已中断，可以继续输入")

        except Exception as e:
            current_spinner = None
            display.print_error(f"调用失败: {e}")

        finally:
            is_agent_running = False


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────


async def async_main() -> None:
    """Async main entry point."""
    global config, client, agent, MODEL_MAX_TOKENS, CWD

    # Load configuration
    config = load_config_from_env()
    client = create_llm_client(config)
    MODEL_MAX_TOKENS = get_model_context_limit(config.model)
    CWD = os.getcwd()

    # Load core memory
    init_core_memory = get_core_memory(str(MEMORY_BASE_DIR))
    memory_context = ""
    if init_core_memory.memories:
        memory_context = "\n\n## 你的核心记忆\n" + "\n".join(
            f"- [强度:{m.reinforce_count}] {m.content}" for m in init_core_memory.memories
        )

    # Create main agent "小枫"
    system_prompt = f"""你叫小枫，是芮枫的私人助理。

## 你是谁
你是芮枫一手打造的私人助理，小枫。性格聪明温柔，说话自然随和，内容绝对真实，不会编造事实。
平日负责帮芮枫处理各种事务——无论是技术问题、日常操作、信息查询还是随手聊几句，都能应对。

## 如何介绍自己
如果芮枫或其他人问你是谁，这样回答（语气自然随意）：
——"我是小枫，芮枫的私人助理。平时处理各种大小事，不管是查个东西、操控电脑还是聚在这儿聊天，都行。"
不要大段列举自己会什么工具或能力，那样会很生硬。

## 技能与工作方式
你内部有两个助手，可以通过工具调用完成不同类型的任务：
- coding_agent：处理代码相关任务（读写文件、执行命令、代码搜索等）
- daily_agent：处理日常任务（播放音乐、打开应用、网页搜索、系统命令、知识问答等）

调用助手时，直接传递用户的原始需求，不要自行规划实现步骤或指定技术方案。
助手内部有专业的 Skill 指引，会自行决定最佳执行方式

当前工作目录: {CWD}

## 记忆使用指南
你拥有 recall_memory 工具可以检索记忆，遇到以下情况时主动调用：
- 问题涉及具体项目、人物、过去的决定
- 芮枫说"之前"、"上次"、"你还记得"
- 需要了解芮枫偏好才能更好回答
闲聊、简单问答、纯技术问题无需检索记忆。{memory_context}"""

    # Callbacks for sub-agents
    sub_agent_callbacks = {
        "on_tool_call": lambda name, args: display.print_tool_call(name, args),
        "on_tool_result": lambda name, result: display.print_tool_result(result),
    }

    # Initialize skill loader with absolute paths
    skill_loader = SkillLoader(PROJECT_ROOT / "src" / "quangan" / "skills")

    # Initialize trace writer
    trace_writer = TraceWriter(SESSIONS_DIR / "trace_record")

    agent_config = AgentConfig(
        client=client,
        system_prompt=system_prompt,
        max_iterations=20,
        skill_loader=skill_loader,
        skill_tags=["router"],
        enable_skill_triggers=True,
        trace_writer=trace_writer,
        on_tool_call=lambda name, args: (
            display.print_tool_call("💻 Coding Agent ← 路由到", {"task": args.get("task")})
            if name == "coding_agent"
            else display.print_tool_call("🌟 Daily Agent ← 路由到", {"task": args.get("task")})
            if name == "daily_agent"
            else display.print_tool_call(name, args)
        ),
        on_tool_result=lambda name, result: display.print_tool_result(result),
        on_compress_start=lambda: (
            console.print("[yellow]⏳ 上下文过长，正在压缩历史对话...[/]"),
            asyncio.create_task(update_life_memory_async()),
        )[1],
        on_compress=lambda before, after: display.print_system(
            f"♻️ 上下文已自动压缩（{before} → {after} 条消息）"
        ),
    )

    agent = Agent(agent_config)

    # Register sub-agent tools
    async def coding_agent_handler(args: dict[str, Any]) -> str:
        coding_agent = create_coding_agent(
            client,
            CWD,
            {
                **sub_agent_callbacks,
                "confirm": make_confirm_fn(session),
            },
            skill_loader=skill_loader,
            skill_tags=["coding"],
            trace_writer=trace_writer,
        )
        return await coding_agent.run(args["task"])

    async def daily_agent_handler(args: dict[str, Any]) -> str:
        daily_agent = create_daily_agent(
            client,
            sub_agent_callbacks,
            skill_loader=skill_loader,
            skill_tags=["daily"],
            trace_writer=trace_writer,
        )
        return await daily_agent.run(args["task"])

    agent.register_tool(coding_agent_def, coding_agent_handler)
    agent.register_tool(daily_agent_def, daily_agent_handler)

    # Register memory tools
    memory_tools = create_memory_tools(client, str(MEMORY_BASE_DIR))
    for definition, implementation, readonly in memory_tools:
        agent.register_tool(definition, implementation, readonly)

    # Load previous session
    previous_messages = load_session(CWD)
    if previous_messages:
        agent.load_messages(previous_messages)

    # Print welcome
    display.print_header(config.model)
    display.print_system("小枫已就绪！芮枫有什么需要尽管说。")
    display.print_system(f"工作目录: {CWD}")
    display.print_system("子 Agent：💻 Coding Agent | 🌟 Daily Agent")

    # Show loaded skills
    loaded_skills = agent.list_skills()
    if loaded_skills:
        skill_names = ", ".join(s.name for s in loaded_skills)
        display.print_system(f"已加载 Skills: {skill_names}")

    if previous_messages:
        user_count = sum(1 for m in previous_messages if m.get("role") == "user")
        display.print_system(f"已恢复上次会话（{user_count} 轮对话），输入 /clear 可重新开始")

    display.print_system("输入消息开始对话，/help 查看命令\n")

    # Create prompt session
    session = PromptSession()

    # Setup key bindings
    kb = KeyBindings()

    @kb.add("escape")
    def escape(event: Any) -> None:
        if is_agent_running:
            agent.abort()

    # Main loop
    while True:
        try:
            # Build prompt
            if is_plan_mode:
                prompt = "[yellow][PLAN] >[/] "
            else:
                prompt = "[green]>[/] "

            # Get input
            user_input = await session.prompt_async(prompt, key_bindings=kb)
            text = user_input.strip()

            if not text:
                continue

            # Check for slash command
            if text.startswith("/"):
                # Handle command picker for just "/"
                if text == "/":

                    async def on_picker_done(cmd: str | None) -> None:
                        if cmd:
                            await handle_command(cmd, session)

                    await start_command_picker(on_picker_done)
                    continue
                await handle_command(text, session)
                continue

            # Print user message
            display.print_user_message(text)

            # Process message
            await process_user_message(text, session)

        except KeyboardInterrupt:
            display.print_system("按 /exit 退出程序")
            continue

        except EOFError:
            display.print_divider()
            display.print_system("再见！👋")
            break


def main() -> None:
    """Main entry point."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
