"""
CLI display utilities.

Provides terminal output formatting using rich library.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Generator

from rich.console import Console
from rich.status import Status
from rich.text import Text

# Global console instance
console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Basic output functions
# ─────────────────────────────────────────────────────────────────────────────


def print_header(model: str) -> None:
    """Print welcome header."""
    console.print()
    console.print("[bold cyan]╔═══════════════════════════════════════╗[/]")
    console.print("[bold cyan]║[/] [bold magenta]小枫 - 芮枫的私人助理[/]            [bold cyan]║[/]")
    console.print("[bold cyan]║[/] [dim]RF Agent CLI v1.0[/]             [bold cyan]║[/]")
    console.print(f"[bold cyan]║[/] [dim]模型: {model:<27}[/] [bold cyan]║[/]")
    console.print("[bold cyan]╚═══════════════════════════════════════╝[/]")
    console.print()


def print_system(msg: str) -> None:
    """Print system message."""
    console.print(f"[dim]\\[System][/] {msg}")


def print_error(msg: str) -> None:
    """Print error message."""
    console.print(f"[red]❌ {msg}[/]")


def print_divider() -> None:
    """Print a horizontal divider."""
    console.print("[dim]────────────────────────────────────────[/]")


# ─────────────────────────────────────────────────────────────────────────────
# Message output
# ─────────────────────────────────────────────────────────────────────────────


def print_user_message(content: str) -> None:
    """Print user message."""
    console.print()
    console.print(f"[green]You[/] [dim]>[/] {content}")


def print_assistant_message(content: str) -> None:
    """Print assistant message."""
    console.print()
    # Handle multiline content
    lines = content.split("\n")
    if len(lines) == 1:
        console.print(f"[magenta]小枫[/] [dim]>[/] {content}")
    else:
        console.print(f"[magenta]小枫[/] [dim]>[/]")
        console.print(content)


# ─────────────────────────────────────────────────────────────────────────────
# Tool output
# ─────────────────────────────────────────────────────────────────────────────


def print_tool_call(name: str, args: dict[str, Any]) -> None:
    """Print tool call information."""
    console.print()
    console.print(f"[yellow]🔧 调用工具:[/] [bold]{name}[/]")

    # Format args as indented JSON
    args_str = json.dumps(args, ensure_ascii=False, indent=2)
    for line in args_str.split("\n"):
        console.print(f"[dim]    {line}[/]")


def print_tool_result(result: str) -> None:
    """Print tool result."""
    # Truncate long results
    if len(result) > 400:
        display = result[:400] + "..."
    else:
        display = result

    console.print(f"[blue]📤 结果:[/] {display}")


# ─────────────────────────────────────────────────────────────────────────────
# Token usage
# ─────────────────────────────────────────────────────────────────────────────


def print_token_usage(used: int, max_limit: int) -> None:
    """Print token usage progress bar."""
    percentage = min(used / max_limit * 100, 100)

    # Choose color based on percentage
    if percentage < 50:
        color = "green"
    elif percentage < 80:
        color = "yellow"
    else:
        color = "red"

    # Create progress bar
    bar_width = 20
    filled = int(percentage / 100 * bar_width)
    bar = "█" * filled + "░" * (bar_width - filled)

    console.print(
        f"[dim]Token 用量:[/] [{color}]{bar}[/{color}] "
        f"[dim]{used:,}/{max_limit:,} ({percentage:.1f}%)[/]"
    )


# ─────────────────────────────────────────────────────────────────────────────
# History display
# ─────────────────────────────────────────────────────────────────────────────


def print_history(messages: list[dict[str, Any]]) -> None:
    """Print message history."""
    console.print()
    console.print("[bold]📜 对话历史[/]")
    print_divider()

    for i, msg in enumerate(messages, 1):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        archived = msg.get("_archived", False)
        summary = msg.get("_summary", False)

        # Skip archived messages (but show summary markers)
        if archived and not summary:
            continue

        # Format role
        if role == "system":
            role_display = "[dim]\\[system][/]"
            if summary:
                role_display = "[dim]\\[summary][/]"
        elif role == "user":
            role_display = "[green]\\[user][/]"
        elif role == "assistant":
            role_display = "[magenta]\\[assistant][/]"
        elif role == "tool":
            role_display = "[blue]\\[tool][/]"
        else:
            role_display = f"[dim]\\[{role}][/]"

        # Truncate long content
        if isinstance(content, str):
            display_content = content[:200] + "..." if len(content) > 200 else content
        else:
            display_content = str(content)[:200]

        console.print(f"{i:3d}. {role_display} {display_content}")

    print_divider()


# ─────────────────────────────────────────────────────────────────────────────
# Tool list
# ─────────────────────────────────────────────────────────────────────────────


def print_tool_list(tools: list[str]) -> None:
    """Print list of available tools."""
    console.print()
    console.print("[bold]🔧 可用工具[/]")
    print_divider()

    for tool in tools:
        console.print(f"  {tool}")

    print_divider()


# ─────────────────────────────────────────────────────────────────────────────
# Mode switches
# ─────────────────────────────────────────────────────────────────────────────


def print_mode_switch(plan_mode: bool) -> None:
    """Print mode switch notification."""
    if plan_mode:
        console.print("[yellow]📋 已进入规划模式（只分析不执行）[/]")
    else:
        console.print("[green]⚡ 已进入执行模式[/]")


def print_help() -> None:
    """Print help message."""
    console.print()
    console.print("[bold]📖 命令列表[/]")
    print_divider()
    console.print("  [cyan]/help[/]      显示帮助信息")
    console.print("  [cyan]/history[/]   查看会话历史")
    console.print("  [cyan]/clear[/]     归档当前对话，开启新对话")
    console.print("  [cyan]/tools[/]     查看已加载工具")
    console.print("  [cyan]/skills[/]    查看已加载 Skills")
    console.print("  [cyan]/plan[/]      进入规划模式（只分析不执行）")
    console.print("  [cyan]/exec[/]      退出规划模式，切回执行")
    console.print("  [cyan]/provider[/]  切换模型供应商")
    console.print("  [cyan]/exit[/]      退出程序")
    print_divider()
    console.print("[dim]💡 输入消息开始对话，按 ESC 可中断 Agent 思考[/]")
    console.print("[dim]💡 Skills 会在检测到触发词时自动激活[/]")


# ─────────────────────────────────────────────────────────────────────────────
# Spinner
# ─────────────────────────────────────────────────────────────────────────────


@contextmanager
def create_spinner(text: str) -> Generator[Status, None, None]:
    """Create a loading spinner."""
    with console.status(f"[cyan]{text}[/]", spinner="dots") as status:
        yield status
