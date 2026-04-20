"""
Shared constants and utilities for command tools.

Refactor: [代码重复] 命令黑名单在 execute_command.py 和 run_shell.py 中重复定义，
提取到共享模块确保安全规则单一来源。
"""

from __future__ import annotations

# Refactor: [安全漏洞] 统一危险命令黑名单，确保安全规则不同步
BLOCKED_COMMANDS: tuple[str, ...] = (
    "sudo",
    "shutdown",
    "reboot",
    "mkfs",
    ":(){ :|:& };:",
)


def check_command_safety(command: str) -> str | None:
    """Check if a command contains blocked dangerous patterns.

    Args:
        command: Shell command string to check.

    Returns:
        Error message if command is blocked, None if safe.
    """
    cmd_lower = command.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked in cmd_lower:
            return f"❌ 命令被安全策略阻止: 包含危险操作 '{blocked}'"
    return None
