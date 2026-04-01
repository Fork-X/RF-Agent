"""
Coding Agent tools collection.

Exports all coding tools and provides a factory function.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from quangan.tools.types import ToolDefinition

from . import read_file, write_file, edit_file, list_directory
from . import execute_command, search_code, verify_code


def create_all_coding_tools(
    work_dir: str,
    confirm_fn: Callable[[str], Awaitable[bool]] | None = None,
) -> list[tuple[ToolDefinition, Callable[[dict[str, Any]], Any], bool]]:
    """
    Create all coding tools with work directory context.

    Args:
        work_dir: Working directory for path safety checks
        confirm_fn: Async callback for y/N confirmation

    Returns:
        List of (definition, implementation, readonly) tuples
    """
    return [
        (read_file.definition, read_file.implementation, True),
        (write_file.definition, write_file.implementation, False),
        (edit_file.definition, edit_file.implementation, False),
        (list_directory.definition, list_directory.implementation, True),
        (
            execute_command.definition,
            execute_command.create_implementation(work_dir, confirm_fn),
            False,
        ),
        (search_code.definition, search_code.implementation, True),
        (verify_code.definition, verify_code.implementation, False),
    ]


# Static list for backward compatibility (without path guard)
ALL_CODING_TOOLS: list[tuple[ToolDefinition, Callable[[dict[str, Any]], Any], bool]] = [
    (read_file.definition, read_file.implementation, True),
    (write_file.definition, write_file.implementation, False),
    (edit_file.definition, edit_file.implementation, False),
    (list_directory.definition, list_directory.implementation, True),
    (execute_command.definition, execute_command.implementation, False),
    (search_code.definition, search_code.implementation, True),
    (verify_code.definition, verify_code.implementation, False),
]
