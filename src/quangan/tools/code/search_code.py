"""
search_code tool implementation.

Recursive code search with regex support.
"""

from __future__ import annotations

import os  # Refactor: [可维护性] 修正 import 位置至文件顶部，符合 PEP 8
import re
from pathlib import Path
from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition

# Directories to skip
SKIP_DIRS = {
    "node_modules", "dist", ".git", ".next",
    "coverage", "__pycache__", ".venv", "venv", "build",
}

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="search_code",
    description=(
        "递归搜索代码文件。支持正则表达式和文件扩展名过滤。"
        "跳过 node_modules、.git、dist 等目录。"
    ),
    parameters={
        "pattern": {
            "type": "string",
            "description": "搜索模式（正则表达式或关键词）",
        },
        "dir_path": {
            "type": "string",
            "description": "搜索目录（默认当前目录）",
        },
        "file_ext": {
            "type": "string",
            "description": "文件扩展名过滤（如 .py, .ts），多个用逗号分隔",
        },
    },
    required=["pattern"],
)


def implementation(args: dict[str, Any]) -> str:
    """
    Recursive code search.

    Args:
        args: {
            "pattern": str,
            "dir_path": str | None,
            "file_ext": str | None,
        }

    Returns:
        Matching lines with file:line format
    """
    pattern = args["pattern"]
    dir_path = Path(args.get("dir_path", ".")).expanduser().resolve()
    file_ext = args.get("file_ext")

    if not dir_path.exists():
        return f"❌ 目录不存在: {dir_path}"

    if not dir_path.is_dir():
        return f"❌ 不是目录: {dir_path}"

    # Parse file extensions
    extensions: set[str] | None = None
    if file_ext:
        extensions = {ext.strip().lstrip(".") for ext in file_ext.split(",")}
        extensions = {f".{ext}" if not ext.startswith(".") else ext for ext in extensions}

    # Compile pattern
    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"❌ 无效的正则表达式: {e}"

    # Search
    results: list[str] = []
    match_count = 0

    try:
        for root, dirs, files in os.walk(dir_path):
            # Skip excluded directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for filename in files:
                # Filter by extension
                if extensions:
                    file_ext_lower = Path(filename).suffix.lower()
                    if file_ext_lower not in extensions:
                        continue

                file_path = Path(root) / filename

                # Skip binary files
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                # Search in file
                for line_num, line in enumerate(content.splitlines(), start=1):
                    if regex.search(line):
                        # Truncate long lines
                        display_line = line.strip()
                        if len(display_line) > 150:
                            display_line = display_line[:150] + "..."

                        rel_path = file_path.relative_to(dir_path)
                        results.append(f"{rel_path}:{line_num}: {display_line}")
                        match_count += 1

                        if len(results) >= 30:
                            break

                if len(results) >= 30:
                    break

            if len(results) >= 30:
                break

    except Exception as e:
        return f"❌ 搜索失败: {e}"

    if not results:
        return f"未找到匹配项: {pattern}"

    header = f"🔍 搜索结果: {pattern}\n目录: {dir_path}\n"
    if match_count > 30:
        footer = f"\n... 还有 {match_count - 30} 个结果未显示"
    else:
        footer = f"\n共 {match_count} 个匹配"

    return header + "\n".join(results) + footer

