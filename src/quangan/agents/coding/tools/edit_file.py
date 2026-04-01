"""
edit_file tool implementation.

Find and replace text in a file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="edit_file",
    description="在文件中查找并替换文本。old_text 必须完全匹配。使用 replace_all 替换所有匹配项。",
    parameters={
        "file_path": {
            "type": "string",
            "description": "要编辑的文件路径",
        },
        "old_text": {
            "type": "string",
            "description": "要查找的文本（必须完全匹配）",
        },
        "new_text": {
            "type": "string",
            "description": "替换后的文本",
        },
        "replace_all": {
            "type": "boolean",
            "description": "是否替换所有匹配项（默认 false）",
        },
    },
    required=["file_path", "old_text", "new_text"],
)


def implementation(args: dict[str, Any]) -> str:
    """
    Find and replace text in a file.

    Args:
        args: {
            "file_path": str,
            "old_text": str,
            "new_text": str,
            "replace_all": bool,
        }

    Returns:
        Success message with changes count, or error message
    """
    file_path = Path(args["file_path"]).expanduser().resolve()
    old_text = args["old_text"]
    new_text = args["new_text"]
    replace_all = args.get("replace_all", False)

    # Check if file exists
    if not file_path.exists():
        return f"❌ 文件不存在: {file_path}"

    if not file_path.is_file():
        return f"❌ 不是文件: {file_path}"

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"❌ 读取文件失败: {e}"

    # Count matches
    match_count = content.count(old_text)

    if match_count == 0:
        return f"❌ 未找到匹配文本: {old_text[:50]}..."

    if match_count > 1 and not replace_all:
        return (
            f"⚠️ 找到 {match_count} 处匹配，但 replace_all=false。\n"
            f"   如需替换所有匹配，请设置 replace_all=true。\n"
            f"   匹配位置预览:\n"
            f"   {old_text[:50]}..."
        )

    # Perform replacement
    if replace_all:
        new_content = content.replace(old_text, new_text)
        actual_replacements = match_count
    else:
        new_content = content.replace(old_text, new_text, 1)
        actual_replacements = 1

    # Write back
    try:
        file_path.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return f"❌ 写入文件失败: {e}"

    return f"✅ 已在 {file_path} 中替换 {actual_replacements} 处\n   \"{old_text[:40]}...\" → \"{new_text[:40]}...\""
