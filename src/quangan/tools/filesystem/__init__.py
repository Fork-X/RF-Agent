"""
Filesystem tools for file operations.

Provides tools for reading, writing, editing, and listing files.
"""

from __future__ import annotations

from quangan.tools.types import ToolRegistration

from .edit_file import definition as edit_file_def
from .edit_file import implementation as edit_file_impl
from .list_directory import definition as list_dir_def
from .list_directory import implementation as list_dir_impl
from .read_file import definition as read_file_def
from .read_file import implementation as read_file_impl
from .write_file import definition as write_file_def
from .write_file import implementation as write_file_impl


def create_filesystem_tools() -> list[ToolRegistration]:
    """Create filesystem tool registrations.

    Returns:
        List of (definition, implementation, readonly) tuples.
    """
    return [
        (read_file_def, read_file_impl, True),
        (write_file_def, write_file_impl, False),
        (edit_file_def, edit_file_impl, False),
        (list_dir_def, list_dir_impl, True),
    ]
