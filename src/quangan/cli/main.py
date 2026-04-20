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
from collections.abc import Callable
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

from quangan.agent.agent import Agent, AgentConfig, AgentInterruptedError
from quangan.agents.coding import create_coding_agent
from quangan.agents.daily import create_daily_agent
from quangan.cli import display
from quangan.cli.command_picker import start_command_picker

# Refactor: [可维护性] 命令处理逻辑已提取到 cli/commands.py
from quangan.cli.commands import handle_command
from quangan.cli.context import CLIContext
from quangan.cli.display import console
from quangan.cli.session_store import SESSIONS_DIR, load_session, save_session
from quangan.config.llm_config import (
    get_model_context_limit,
    load_config_from_env,
)
from quangan.config.paths import get_memory_base_dir, get_project_root
from quangan.llm.client import create_llm_client
from quangan.memory import create_memory_tools, get_core_memory
from quangan.skills import SkillLoader
from quangan.tools.types import ToolDefinition, make_tool_definition
from quangan.trace import TraceWriter
from quangan.utils.logger import get_logger, setup_logging

# ─────────────────────────────────────────────────────────────────────────────
# Environment file path
# ─────────────────────────────────────────────────────────────────────────────

# Refactor: [设计缺陷] 消除硬编码路径依赖
PROJECT_ROOT = get_project_root()
MEMORY_BASE_DIR = get_memory_base_dir()


logger = get_logger("cli")


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


async def update_life_memory_async(ctx: CLIContext) -> None:
    """Update life memory on context compression (fire-and-forget).

    Args:
        ctx: CLI context with client and agent access.
    """
    try:
        # Get recent non-archived messages
        history = [
            msg
            for msg in ctx.agent.get_history()
            if not msg.get("_archived") and msg.get("role") != "system"
        ]

        if not history:
            logger.debug("update_life_memory_async: no active history to summarize")
            return

        # Build summary prompt
        history_text = "\n\n".join(
            f"[{'用户' if m.get('role') == 'user' else 'Agent'}]: {str(m.get('content', ''))[:400]}"
            for m in history
        )

        summary = await ctx.client.ask(
            f"请将以下对话提炼为简洁的日常记忆摘要（150字以内）：\n\n{history_text}",
            "你是记忆整合助手，请用简洁中文生成摘要。",
        )

        theme = await ctx.client.ask(
            f"根据以下摘要，提取一个简短的主题词（3-8字）：\n\n{summary}",
            "只输出主题词，不要其他内容。",
        )

        from quangan.memory import append_life_memory

        filename = append_life_memory(str(MEMORY_BASE_DIR), theme.strip(), summary)
        ctx.life_memory_update_count += 1
        logger.info("Life memory saved: %s", filename)

        # Every 3 compressions, trigger consolidation
        if ctx.life_memory_update_count % 3 == 0:
            logger.info(
                "Triggering core memory consolidation (count=%d)",
                ctx.life_memory_update_count,
            )
            from quangan.memory import create_memory_tool_impls

            impls = create_memory_tool_impls(ctx.client, str(MEMORY_BASE_DIR))
            result = await impls["consolidate_impl"]()
            logger.info("Core memory consolidation result: %s", result)

    except Exception:
        # 原实现静默吞掉异常，导致记忆丢失且无任何观测。
        # 改为记录 ERROR 并带上堆栈，不影响主对话流程，但问题可追踪。
        logger.error("Life memory update failed", exc_info=True)


# Refactor: [可维护性] Provider 管理和命令处理已提取到 cli/commands.py


# ─────────────────────────────────────────────────────────────────────────────
# Message processing
# ─────────────────────────────────────────────────────────────────────────────


async def process_user_message(ctx: CLIContext, text: str, session: PromptSession) -> None:
    """Process user message and get agent response.

    Args:
        ctx: CLI execution context.
        text: User input text.
        session: prompt_toolkit session.
    """
    # Inject plan mode instructions if needed
    if ctx.is_plan_mode:
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

    ctx.is_agent_running = True

    with display.create_spinner("Agent 思考中... [dim](Esc 可中断)[/]") as spinner:
        ctx.current_spinner = spinner

        try:
            response = await ctx.agent.run(message_to_send, ctx.is_plan_mode)
            ctx.current_spinner = None

            display.print_assistant_message(response)

            # Show token usage
            usage = ctx.agent.get_token_usage()
            display.print_token_usage(usage.total, ctx.model_max_tokens)

            # Save session
            save_session(ctx.cwd, ctx.agent.get_history())

        except AgentInterruptedError:
            ctx.current_spinner = None
            display.print_system("⚡ 调用已中断，可以继续输入")

        except Exception as e:
            ctx.current_spinner = None
            display.print_error(f"调用失败: {e}")

        finally:
            ctx.is_agent_running = False


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────


# [Refactored] Task #9 - 从 async_main 提取
def _init_config() -> Any:
    """Load and validate LLM configuration from environment.

    Returns:
        LLMConfig instance.
    """
    return load_config_from_env()


# [Refactored] Task #9 - 从 async_main 提取
def _init_client(config: Any) -> Any:
    """Create the LLM client from configuration.

    Args:
        config: LLMConfig instance.

    Returns:
        LLM client instance.
    """
    return create_llm_client(config)


# [Refactored] Task #9 - 从 async_main 提取
def _load_core_memory(cwd: str) -> str:
    """Load core memories and build memory context string.

    Args:
        cwd: Current working directory (unused, reserved for future per-project memory).

    Returns:
        Formatted memory context string, empty if no memories.
    """
    core_memory = get_core_memory(str(MEMORY_BASE_DIR))
    if core_memory.memories:
        return "\n\n## 你的核心记忆\n" + "\n".join(
            f"- [强度:{m.reinforce_count}] {m.content}" for m in core_memory.memories
        )
    return ""


# [Refactored] Task #9 - 从 async_main 提取
def _build_system_prompt(cwd: str, memory_context: str) -> str:
    """Build the main agent system prompt.

    Args:
        cwd: Current working directory.
        memory_context: Pre-built memory context string.

    Returns:
        Formatted system prompt string.
    """
    return f"""你叫小枫，是芮枫的私人助理。

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

当前工作目录: {cwd}

## 记忆使用指南
你拥有 recall_memory 工具可以检索记忆，遇到以下情况时主动调用：
- 问题涉及具体项目、人物、过去的决定
- 芮枫说"之前"、"上次"、"你还记得"
- 需要了解芮枫偏好才能更好回答
闲聊、简单问答、纯技术问题无需检索记忆。{memory_context}"""


# [Refactored] Task #9 - 从 async_main 提取
# [HIGH-RISK] 包含多个回调闭包和复杂状态传递（skill_loader, trace_writer, display callbacks）
def _create_agent(
    client: Any,
    system_prompt: str,
    skill_loader: SkillLoader,
    trace_writer: TraceWriter,
) -> Agent:
    """Create and configure the main Agent with callbacks.

    Args:
        client: LLM client instance.
        system_prompt: Agent system prompt.
        skill_loader: Skill loader for dynamic skill discovery.
        trace_writer: Trace writer for logging.

    Returns:
        Configured Agent instance (compress callbacks set later).
    """
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
        on_compress=lambda before, after: display.print_system(
            f"♻️ 上下文已自动压缩（{before} → {after} 条消息）"
        ),
    )
    return Agent(agent_config)


# [Refactored] Task #9 - 从 async_main 提取
def _bind_compress_callback(agent: Agent, ctx: CLIContext) -> None:
    """Bind context-dependent compress callback to the agent.

    Args:
        agent: Agent instance to bind callback on.
        ctx: CLI context for life memory updates.
    """
    agent._on_compress_start = lambda: (
        console.print("[yellow]⏳ 上下文过长，正在压缩历史对话...[/]"),
        asyncio.create_task(update_life_memory_async(ctx)),
    )[1]


# [Refactored] Task #9 - 从 async_main 提取
# [HIGH-RISK] 子Agent handler 闭包捕获 ctx/skill_loader/trace_writer/session_holder 多个外部状态
def _register_sub_agents(
    agent: Agent,
    ctx: CLIContext,
    skill_loader: SkillLoader,
    trace_writer: TraceWriter,
    session_holder: list[PromptSession],
) -> None:
    """Register sub-agent tool handlers (coding & daily) on the main agent.

    Args:
        agent: Main agent to register tools on.
        ctx: CLI context for client/cwd access.
        skill_loader: Skill loader instance.
        trace_writer: Trace writer instance.
        session_holder: Mutable list holding the PromptSession (for lazy access).
    """
    sub_agent_callbacks: dict[str, Any] = {
        "on_tool_call": lambda name, args: display.print_tool_call(name, args),
        "on_tool_result": lambda name, result: display.print_tool_result(result),
    }

    async def coding_agent_handler(args: dict[str, Any]) -> str:
        coding = create_coding_agent(
            ctx.client,
            ctx.cwd,
            {**sub_agent_callbacks, "confirm": make_confirm_fn(session_holder[0])},
            skill_loader=skill_loader,
            skill_tags=["coding"],
            trace_writer=trace_writer,
        )
        return await coding.run(args["task"])

    async def daily_agent_handler(args: dict[str, Any]) -> str:
        daily = create_daily_agent(
            ctx.client,
            sub_agent_callbacks,
            skill_loader=skill_loader,
            skill_tags=["daily"],
            trace_writer=trace_writer,
        )
        return await daily.run(args["task"])

    agent.register_tool(coding_agent_def, coding_agent_handler)
    agent.register_tool(daily_agent_def, daily_agent_handler)


# [Refactored] Task #9 - 从 async_main 提取
def _register_memory_tools(agent: Agent, ctx: CLIContext) -> None:
    """Register memory tools (recall/store) on the main agent.

    Args:
        agent: Main agent to register tools on.
        ctx: CLI context for client access.
    """
    memory_tools = create_memory_tools(ctx.client, str(MEMORY_BASE_DIR))
    for definition, implementation, readonly in memory_tools:
        agent.register_tool(definition, implementation, readonly)


# [Refactored] Task #9 - 从 async_main 提取
def _restore_session(ctx: CLIContext) -> list[dict[str, Any]] | None:
    """Load and restore previous session messages.

    Args:
        ctx: CLI context.

    Returns:
        Previous messages list if restored, None otherwise.
    """
    previous_messages = load_session(ctx.cwd)
    if previous_messages:
        ctx.agent.load_messages(previous_messages)
    return previous_messages


# [Refactored] Task #9 - 从 async_main 提取
def _show_welcome(ctx: CLIContext, previous_messages: list[dict[str, Any]] | None) -> None:
    """Display welcome banner and session info.

    Args:
        ctx: CLI context.
        previous_messages: Restored session messages (if any).
    """
    display.print_header(ctx.config.model)
    display.print_system("小枫已就绪！芮枫有什么需要尽管说。")
    display.print_system(f"工作目录: {ctx.cwd}")
    display.print_system("子 Agent：💻 Coding Agent | 🌟 Daily Agent")

    loaded_skills = ctx.agent.list_skills()
    if loaded_skills:
        skill_names = ", ".join(s.name for s in loaded_skills)
        display.print_system(f"已加载 Skills: {skill_names}")

    if previous_messages:
        user_count = sum(1 for m in previous_messages if m.get("role") == "user")
        display.print_system(f"已恢复上次会话（{user_count} 轮对话），输入 /clear 可重新开始")

    display.print_system("输入消息开始对话，/help 查看命令\n")


# [Refactored] Task #9 - 从 async_main 提取
async def _run_repl_loop(ctx: CLIContext, session: PromptSession) -> None:
    """Run the main REPL (read-eval-print loop).

    Args:
        ctx: CLI context.
        session: prompt_toolkit PromptSession instance.
    """
    kb = KeyBindings()

    @kb.add("escape")
    def _escape(event: Any) -> None:
        if ctx.is_agent_running:
            ctx.agent.abort()

    while True:
        try:
            prompt = "[yellow][PLAN] >[/] " if ctx.is_plan_mode else "[green]>[/] "
            user_input = await session.prompt_async(prompt, key_bindings=kb)
            text = user_input.strip()

            if not text:
                continue

            if text.startswith("/"):
                if text == "/":

                    async def on_picker_done(cmd: str | None) -> None:
                        if cmd:
                            await handle_command(ctx, cmd, session)

                    await start_command_picker(on_picker_done)
                    continue
                await handle_command(ctx, text, session)
                continue

            display.print_user_message(text)
            await process_user_message(ctx, text, session)

        except KeyboardInterrupt:
            display.print_system("按 /exit 退出程序")
            continue

        except EOFError:
            display.print_divider()
            display.print_system("再见！👋")
            break


# [Refactored] Task #9 - 从 async_main 提取
def _create_cli_context(
    config: Any,
    client: Any,
    agent: Agent,
    max_tokens: int,
    cwd: str,
) -> CLIContext:
    """Create the CLIContext with all required fields.

    Args:
        config: LLMConfig instance.
        client: LLM client instance.
        agent: Configured Agent instance.
        max_tokens: Model context token limit.
        cwd: Current working directory.

    Returns:
        Initialized CLIContext.
    """
    return CLIContext(
        config=config,
        client=client,
        agent=agent,
        project_root=PROJECT_ROOT,
        model_max_tokens=max_tokens,
        cwd=cwd,
    )


async def async_main() -> None:
    """Main async entry point — orchestrates initialization and REPL startup."""
    # 1. 配置 & 客户端
    config = _init_config()
    client = _init_client(config)
    cwd = os.getcwd()

    # 2. 记忆 & 系统提示
    memory_context = _load_core_memory(cwd)
    system_prompt = _build_system_prompt(cwd, memory_context)

    # 3. Agent 创建
    skill_loader = SkillLoader(PROJECT_ROOT / "src" / "quangan" / "skills")
    trace_writer = TraceWriter(SESSIONS_DIR / "trace_record")
    agent = _create_agent(client, system_prompt, skill_loader, trace_writer)

    # 4. CLIContext 构建
    max_tokens = get_model_context_limit(config.model)
    ctx = _create_cli_context(config, client, agent, max_tokens, cwd)

    # 5. 绑定压缩回调
    _bind_compress_callback(agent, ctx)

    # 6. 注册工具（session 延迟绑定）
    session_holder: list[PromptSession] = []
    _register_sub_agents(agent, ctx, skill_loader, trace_writer, session_holder)
    _register_memory_tools(agent, ctx)

    # 7. 恢复会话 & 显示欢迎
    previous_messages = _restore_session(ctx)
    _show_welcome(ctx, previous_messages)

    # 8. 创建 PromptSession 并启动 REPL
    session = PromptSession()
    session_holder.append(session)
    await _run_repl_loop(ctx, session)


def main() -> None:
    """Main entry point."""
    # 初始化日志系统：文件 DEBUG，控制台默认 ERROR（可通过 QUANGAN_LOG_LEVEL 覆盖）
    setup_logging()
    logger.info("QuanGan starting...")

    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")


if __name__ == "__main__":
    main()
