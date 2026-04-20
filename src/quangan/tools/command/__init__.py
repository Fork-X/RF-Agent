"""
Command tools for shell execution.

Provides tools for executing shell commands with safety checks.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from quangan.tools.types import ToolRegistration

from .execute_command import create_implementation as create_exec_cmd_impl
from .execute_command import definition as exec_cmd_def
from .run_shell import definition as run_shell_def
from .run_shell import implementation as run_shell_impl


def create_command_tools(
    work_dir: str,
    confirm_fn: Callable[[str], Awaitable[bool]] | None = None,
) -> list[ToolRegistration]:
    """Create command tool registrations with work directory context.

    Args:
        work_dir: Working directory for path safety checks.
        confirm_fn: Async callback for y/N confirmation.

    Returns:
        List of (definition, implementation, readonly) tuples.
    """
    return [
        (exec_cmd_def, create_exec_cmd_impl(work_dir, confirm_fn), False),
        (run_shell_def, run_shell_impl, False),
    ]


def create_shell_tools() -> list[ToolRegistration]:
    """Create basic shell tool registrations without safety checks.

    Returns:
        List of (definition, implementation, readonly) tuples.
    """
    return [
        (run_shell_def, run_shell_impl, False),
    ]
