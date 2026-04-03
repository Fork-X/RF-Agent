"""
Filesystem tools for file operations.

Provides tools for reading, writing, editing, and listing files.
"""

from __future__ import annotations

from typing import Any, Callable

from quangan.tools.types import ToolDefinition

from .read_file import definition as read_file_def, implementation as read_file_impl
from .write_file import definition as write_file_def, implementation as write_file_impl
from .edit_file import definition as edit_file_def, implementation as edit_file_impl
from .list_directory import definition as list_dir_def, implementation as list_dir_impl


def create_filesystem_tools() -> list[tuple[ToolDefinition, Callable[[dict[str, Any]], Any], bool]]:
    """
    Create all filesystem tools.

    Returns:
        List of (definition, implementation, readonly) tuples
    """
    return [
        (read_file_def, read_file_impl, True),
        (write_file_def, write_file_impl, False),
        (edit_file_def, edit_file_impl, False),
        (list_dir_def, list_dir_impl, True),
    ]
