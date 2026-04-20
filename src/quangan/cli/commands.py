"""
CLI slash command handlers.

Refactor: [可维护性] 从 main.py 提取斜杠命令处理逻辑，实现关注点分离。
main.py 只保留 REPL 循环和初始化，命令处理在此独立模块中。
"""
from __future__ import annotations

import os
import re
import sys
from typing import TYPE_CHECKING, Any

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings

from quangan.cli import display
from quangan.cli.display import console
from quangan.cli.session_store import clear_session
from quangan.config.llm_config import (
    PROVIDERS,
    LLMConfig,
    get_model_context_limit,
)
from quangan.config.paths import get_memory_base_dir, get_project_root
from quangan.llm.client import create_llm_client
from quangan.memory import create_memory_tools

if TYPE_CHECKING:
    from quangan.cli.context import CLIContext

# Refactor: [设计缺陷] 消除硬编码路径依赖
PROJECT_ROOT = get_project_root()
ENV_FILE = PROJECT_ROOT / ".env"
MEMORY_BASE_DIR = get_memory_base_dir()


# ─────────────────────────────────────────────────────────────────────────────
# Provider utilities
# ─────────────────────────────────────────────────────────────────────────────


def is_valid_api_key(key: str | None) -> bool:
    """Check if an API key is valid (not a placeholder).

    Args:
        key: API key string to validate.

    Returns:
        True if key appears to be a real API key.
    """
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
    """Persist a key-value pair to .env file.

    Args:
        key: Environment variable name.
        value: Environment variable value.
    """
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


def switch_provider(ctx: CLIContext, name: str) -> None:
    """Switch to a different LLM provider.

    Args:
        ctx: CLI execution context.
        name: Provider name (e.g., 'openai', 'kimi').
    """
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

    ctx.config = LLMConfig(
        provider=name,
        api_key=api_key,
        base_url=preset.base_url,
        model=new_model,
        headers=preset.headers,
        protocol=preset.protocol,
    )

    ctx.client = create_llm_client(ctx.config)
    ctx.model_max_tokens = get_model_context_limit(ctx.config.model)
    ctx.agent.update_client(ctx.client)

    # Re-register memory tools (uses new client)
    memory_tools = create_memory_tools(ctx.client, str(MEMORY_BASE_DIR))
    for definition, implementation, readonly in memory_tools:
        ctx.agent.register_tool(definition, implementation, readonly)

    proto_label = " [Anthropic 协议]" if preset.protocol == "anthropic" else ""
    display.print_system(f"✅ 已切换至 {name}{proto_label} | 模型：{new_model}")


async def show_provider_picker(ctx: CLIContext, session: PromptSession) -> None:
    """Show interactive provider picker.

    Args:
        ctx: CLI execution context.
        session: prompt_toolkit session for interactive input.
    """
    # Build provider list
    provider_items: list[dict[str, Any]] = []

    for name, preset in PROVIDERS.items():
        prefix = name.replace("-", "_").upper()
        api_key = os.environ.get(f"{prefix}_API_KEY", "")
        provider_items.append(
            {
                "name": name,
                "model": os.environ.get(f"{prefix}_MODEL") or preset.default_model,
                "active": name == ctx.config.provider,
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
    from prompt_toolkit.layout import Layout, Window
    from prompt_toolkit.layout.controls import BufferControl

    buffer = Buffer()
    control = BufferControl(buffer=buffer)

    app: Application[Any] = Application(layout=Layout(Window(control)), key_bindings=kb)
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

            env_prefix = result_name.replace("-", "_").upper()
            os.environ[f"{env_prefix}_API_KEY"] = api_key_input
            persist_env(f"{env_prefix}_API_KEY", api_key_input)

            model_input = input(f"  模型名称 (回车使用默认 {p['model']}): ").strip()
            if model_input:
                os.environ[f"{env_prefix}_MODEL"] = model_input
                persist_env(f"{env_prefix}_MODEL", model_input)

            switch_provider(ctx, result_name)
            display.print_system("✅ 配置已保存到 .env")
        else:
            switch_provider(ctx, result_name)


# ─────────────────────────────────────────────────────────────────────────────
# Individual command handlers
# ─────────────────────────────────────────────────────────────────────────────


async def cmd_help(ctx: CLIContext) -> bool:
    """Display help information.

    Args:
        ctx: CLI execution context.

    Returns:
        True after displaying help.
    """
    display.print_help()
    return True


async def cmd_clear(ctx: CLIContext) -> bool:
    """Clear conversation history and start a new session.

    Args:
        ctx: CLI execution context.

    Returns:
        True after clearing.
    """
    ctx.agent.clear_history()
    archived = clear_session(ctx.cwd)
    console.clear()
    display.print_header(ctx.config.model)
    if archived:
        display.print_system(f"📦 旧对话已归档：{archived}")
    display.print_system("已开启新对话")
    return True


async def cmd_history(ctx: CLIContext) -> bool:
    """Display conversation history.

    Args:
        ctx: CLI execution context.

    Returns:
        True after displaying history.
    """
    display.print_history(ctx.agent.get_history())
    return True


async def cmd_tools(ctx: CLIContext) -> bool:
    """List all available tools.

    Args:
        ctx: CLI execution context.

    Returns:
        True after listing tools.
    """
    from quangan.tools.browser import create_browser_tools
    from quangan.tools.code import create_code_tools
    from quangan.tools.command import create_command_tools, create_shell_tools
    from quangan.tools.filesystem import create_filesystem_tools
    from quangan.tools.system import create_system_tools

    # Collect all tools
    coding_tools = (
        create_filesystem_tools() + create_code_tools() + create_command_tools("", None)
    )
    daily_tools = create_system_tools() + create_browser_tools() + create_shell_tools()

    tool_names = [f"  [coding] {t[0]['function']['name']}" for t in coding_tools] + [
        f"  [daily]  {t[0]['function']['name']}" for t in daily_tools
    ]
    display.print_tool_list(tool_names)
    return True


async def cmd_skills(ctx: CLIContext) -> bool:
    """List loaded skills.

    Args:
        ctx: CLI execution context.

    Returns:
        True after listing skills.
    """
    skills = ctx.agent.list_skills()
    if skills:
        console.print("\n[bold cyan]已加载的 Skills:[/]")
        for skill in skills:
            active = "[green]●[/]" if skill in ctx.agent.get_active_skills() else "[dim]○[/]"
            console.print(f"  {active} [bold]{skill.name}[/] - {skill.description}")
            if skill.metadata.triggers:
                triggers = ", ".join(skill.metadata.triggers[:5])
                console.print(f"     [dim]触发词: {triggers}[/]")
    else:
        console.print("\n[yellow]暂无已加载的 Skills[/]")
    console.print()
    return True


async def cmd_plan(ctx: CLIContext) -> bool:
    """Enter plan mode (read-only analysis).

    Args:
        ctx: CLI execution context.

    Returns:
        True after switching to plan mode.
    """
    ctx.is_plan_mode = True
    display.print_mode_switch(True)
    return True


async def cmd_exec(ctx: CLIContext) -> bool:
    """Exit plan mode, switch to execution mode.

    Args:
        ctx: CLI execution context.

    Returns:
        True after switching to execution mode.
    """
    ctx.is_plan_mode = False
    display.print_mode_switch(False)
    return True


async def cmd_provider(ctx: CLIContext, session: PromptSession) -> bool:
    """Show interactive provider picker.

    Args:
        ctx: CLI execution context.
        session: prompt_toolkit session.

    Returns:
        True after provider selection.
    """
    await show_provider_picker(ctx, session)
    return True


async def cmd_provider_switch(ctx: CLIContext, provider_name: str) -> bool:
    """Switch to a specific provider by name.

    Args:
        ctx: CLI execution context.
        provider_name: Target provider name.

    Returns:
        True after switching provider.
    """
    switch_provider(ctx, provider_name)
    return True


async def cmd_exit(ctx: CLIContext) -> bool:
    """Exit the program.

    Args:
        ctx: CLI execution context.

    Returns:
        Never returns (calls sys.exit).
    """
    display.print_divider()
    display.print_system("再见！👋")
    sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# Command dispatch
# ─────────────────────────────────────────────────────────────────────────────


async def handle_command(ctx: CLIContext, command: str, session: PromptSession) -> bool:
    """Handle a slash command.

    Refactor: [可维护性] 从 main.py 提取，实现命令处理与主循环分离。

    Args:
        ctx: CLI execution context.
        command: The slash command string (e.g., "/help", "/clear").
        session: prompt_toolkit session (needed for provider picker).

    Returns:
        True if the command was handled, False if unrecognized.
    """
    cmd = command.strip()

    if cmd == "/help":
        return await cmd_help(ctx)

    if cmd == "/clear":
        return await cmd_clear(ctx)

    if cmd == "/history":
        return await cmd_history(ctx)

    if cmd == "/tools":
        return await cmd_tools(ctx)

    if cmd == "/skills":
        return await cmd_skills(ctx)

    if cmd == "/plan":
        return await cmd_plan(ctx)

    if cmd == "/exec":
        return await cmd_exec(ctx)

    if cmd == "/provider":
        return await cmd_provider(ctx, session)

    if cmd in ("/exit", "/quit"):
        return await cmd_exit(ctx)

    if cmd.startswith("/provider "):
        provider_name = cmd[len("/provider ") :].strip()
        return await cmd_provider_switch(ctx, provider_name)

    display.print_error(f"未知命令: {cmd}，输入 /help 查看命令列表")
    return True
