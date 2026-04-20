"""
edit_file tool implementation.

Find and replace text in a file.
"""

from __future__ import annotations

from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition
from quangan.tools.utils import normalize_path, validate_file_exists

# Refactor: [可维护性] 提取硬编码数值为命名常量
MAX_DISPLAY_LENGTH = 50

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
    # Refactor: [代码重复] 使用共享工具函数，见 tools/utils.py
    file_path = normalize_path(args["file_path"])
    old_text = args["old_text"]
    new_text = args["new_text"]
    replace_all = args.get("replace_all", False)

    # Refactor: [代码重复] 使用共享工具函数，见 tools/utils.py
    error = validate_file_exists(file_path)
    if error:
        return error

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"❌ 读取文件失败: {e}"

    # Count matches
    match_count = content.count(old_text)

    if match_count == 0:
        return f"❌ 未找到匹配文本: {old_text[:MAX_DISPLAY_LENGTH]}..."

    if match_count > 1 and not replace_all:
        return (
            f"⚠️ 找到 {match_count} 处匹配，但 replace_all=false。\n"
            f"   如需替换所有匹配，请设置 replace_all=true。\n"
            f"   匹配位置预览:\n"
            f"   {old_text[:MAX_DISPLAY_LENGTH]}..."
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

    old_preview = old_text[:MAX_DISPLAY_LENGTH]
    new_preview = new_text[:MAX_DISPLAY_LENGTH]
    return (
        f"✅ 已在 {file_path} 中替换 {actual_replacements} 处\n"
        f'   "{old_preview}..." → "{new_preview}..."'
    )
