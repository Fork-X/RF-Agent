"""
write_file tool implementation.

Creates or overwrites a file with content.
"""

from __future__ import annotations

from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition
from quangan.tools.utils import normalize_path

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="write_file",
    description="创建或覆盖文件。自动创建父目录。返回写入的行数和字节数。",
    parameters={
        "file_path": {
            "type": "string",
            "description": "要写入的文件路径（绝对路径或相对路径）",
        },
        "content": {
            "type": "string",
            "description": "要写入的内容",
        },
    },
    required=["file_path", "content"],
)


def implementation(args: dict[str, Any]) -> str:
    """
    Write content to a file.

    Args:
        args: {
            "file_path": str,
            "content": str,
        }

    Returns:
        Success message with stats, or error message
    """
    # Refactor: [代码重复] 使用共享工具函数，见 tools/utils.py
    file_path = normalize_path(args["file_path"])
    content = args["content"]

    try:
        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        file_path.write_text(content, encoding="utf-8")

        # Stats
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        if not content:
            lines = 0
        bytes_written = len(content.encode("utf-8"))

        return f"✅ 已写入 {file_path}\n   {lines} 行, {bytes_written} 字节"

    except Exception as e:
        return f"❌ 写入文件失败: {e}"
