"""
list_directory tool implementation.

Lists directory contents with directories first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition
from quangan.tools.utils import normalize_path, validate_directory_exists

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="list_directory",
    description="列出目录内容。目录排在前面，文件排在后面。显示文件大小。",
    parameters={
        "dir_path": {
            "type": "string",
            "description": "要列出的目录路径（默认当前目录）",
        },
    },
    required=[],
)


def implementation(args: dict[str, Any]) -> str:
    """
    List directory contents.

    Args:
        args: {
            "dir_path": str | None,
        }

    Returns:
        Formatted directory listing
    """
    # Refactor: [代码重复] 使用共享工具函数，见 tools/utils.py
    dir_path = normalize_path(args.get("dir_path", "."))

    # Refactor: [代码重复] 使用共享工具函数，见 tools/utils.py
    error = validate_directory_exists(dir_path)
    if error:
        return error

    try:
        entries = list(dir_path.iterdir())
    except PermissionError:
        return f"❌ 无权限访问目录: {dir_path}"
    except Exception as e:
        return f"❌ 读取目录失败: {e}"

    if not entries:
        return f"📁 {dir_path}\n(空目录)"

    # Sort: directories first, then files, alphabetically within each group
    def sort_key(e: Path) -> tuple[int, str]:
        is_dir = 0 if e.is_dir() else 1
        return (is_dir, e.name.lower())

    entries.sort(key=sort_key)

    # Format output
    lines = [f"📁 {dir_path}\n"]
    dir_count = 0
    file_count = 0

    for entry in entries:
        try:
            if entry.is_dir():
                lines.append(f"  📁 {entry.name}/")
                dir_count += 1
            else:
                size = entry.stat().st_size
                if size >= 1024 * 1024:
                    size_str = f"{size / (1024 * 1024):.1f}M"
                elif size >= 1024:
                    size_str = f"{size / 1024:.1f}K"
                else:
                    size_str = f"{size}B"
                lines.append(f"  📄 {entry.name} ({size_str})")
                file_count += 1
        except PermissionError:
            lines.append(f"  🔒 {entry.name} (无权限)")
            file_count += 1

    lines.append(f"\n{dir_count} 个目录, {file_count} 个文件")

    return "\n".join(lines)
