"""
Shared utility functions for tool implementations.

Refactor: [代码重复] 路径规范化和文件校验逻辑在 filesystem/ 4 个工具文件中重复出现，
提取到共享模块实现单一来源。
"""
from __future__ import annotations

from pathlib import Path


def normalize_path(path_str: str) -> Path:
    """Normalize a user-provided path string to an absolute Path.

    Handles ~ expansion and resolves to absolute path.

    Args:
        path_str: Raw path string from user input.

    Returns:
        Resolved absolute Path object.
    """
    return Path(path_str).expanduser().resolve()


def validate_file_exists(path: Path) -> str | None:
    """Validate that a path points to an existing file.

    Args:
        path: Path to validate.

    Returns:
        Error message string if validation fails, None if valid.
    """
    if not path.exists():
        return f"❌ 文件不存在: {path}"
    if not path.is_file():
        return f"❌ 不是文件: {path}"
    return None


def validate_directory_exists(path: Path) -> str | None:
    """Validate that a path points to an existing directory.

    Args:
        path: Path to validate.

    Returns:
        Error message string if validation fails, None if valid.
    """
    if not path.exists():
        return f"❌ 目录不存在: {path}"
    if not path.is_dir():
        return f"❌ 不是目录: {path}"
    return None


def format_tool_error(tool_name: str, error: Exception) -> str:
    """Format a tool execution error for user display.

    Args:
        tool_name: Name of the tool that failed.
        error: The exception that occurred.

    Returns:
        Formatted error message string.
    """
    return f"❌ [{tool_name}] 执行失败: {error}"
