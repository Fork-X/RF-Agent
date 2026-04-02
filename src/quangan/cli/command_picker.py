"""
Command picker for '/' commands.

Provides an interactive TUI menu for selecting commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style


@dataclass
class CommandEntry:
    """A command entry in the picker."""

    cmd: str
    desc: str


# Available commands
PICKER_COMMANDS: list[CommandEntry] = [
    CommandEntry("/help", "显示帮助信息"),
    CommandEntry("/history", "查看会话历史"),
    CommandEntry("/clear", "归档当前对话，开启新对话"),
    CommandEntry("/tools", "查看已加载工具"),
    CommandEntry("/plan", "进入规划模式"),
    CommandEntry("/exec", "退出规划模式"),
    CommandEntry("/provider", "切换模型供应商"),
    CommandEntry("/exit", "退出程序"),
]


# Style for the picker
PICKER_STYLE = Style.from_dict(
    {
        "selected": "bold cyan",
        "normal": "",
        "dim": "dim",
    }
)


async def start_command_picker(on_done: Callable[[str | None], Any]) -> None:
    """
    Start an interactive command picker.

    Args:
        on_done: Callback when selection is made (receives command string or None)
    """
    selected_index = 0

    def get_text() -> list[tuple[str, str]]:
        """Generate formatted text for the picker."""
        lines: list[tuple[str, str]] = []

        lines.append(("", "  ↑↓ 选择  Enter 确认  Esc 取消\n"))

        for i, entry in enumerate(PICKER_COMMANDS):
            if i == selected_index:
                lines.append(("class:selected", f"  ▶ {entry.cmd}"))
                lines.append(("class:dim", f"  - {entry.desc}\n"))
            else:
                lines.append(("", f"    {entry.cmd}"))
                lines.append(("class:dim", f"  - {entry.desc}\n"))

        return lines

    control = FormattedTextControl(text=get_text, focusable=True)
    window = Window(content=control, height=len(PICKER_COMMANDS) + 1)
    layout = Layout(HSplit([window]))

    kb = KeyBindings()

    @kb.add("up")
    def up(event: Any) -> None:
        nonlocal selected_index
        selected_index = (selected_index - 1) % len(PICKER_COMMANDS)
        control.text = get_text()

    @kb.add("down")
    def down(event: Any) -> None:
        nonlocal selected_index
        selected_index = (selected_index + 1) % len(PICKER_COMMANDS)
        control.text = get_text()

    @kb.add("enter")
    def enter(event: Any) -> None:
        app.exit()
        on_done(PICKER_COMMANDS[selected_index].cmd)

    @kb.add("escape")
    def escape(event: Any) -> None:
        app.exit()
        on_done(None)

    app = Application(layout=layout, key_bindings=kb, style=PICKER_STYLE, full_screen=False)
    await app.run_async()
