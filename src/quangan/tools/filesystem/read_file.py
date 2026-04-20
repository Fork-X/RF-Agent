"""
read_file tool implementation.

Reads file content with optional line range support.
"""

from __future__ import annotations

from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition
from quangan.tools.utils import normalize_path, validate_file_exists

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="read_file",
    description="读取文件内容。支持指定行范围，适合查看大文件的局部内容。",
    parameters={
        "file_path": {
            "type": "string",
            "description": "要读取的文件路径（绝对路径或相对路径）",
        },
        "start_line": {
            "type": "integer",
            "description": "起始行号（可选，从 1 开始）",
        },
        "end_line": {
            "type": "integer",
            "description": "结束行号（可选）",
        },
    },
    required=["file_path"],
)


def implementation(args: dict[str, Any]) -> str:
    """
    Read file content with optional line range.

    Args:
        args: {
            "file_path": str,
            "start_line": int | None,
            "end_line": int | None,
        }

    Returns:
        File content with line numbers, or error message
    """
    # Refactor: [代码重复] 使用共享工具函数，见 tools/utils.py
    file_path = normalize_path(args["file_path"])
    start_line = args.get("start_line")
    end_line = args.get("end_line")

    # Refactor: [代码重复] 使用共享工具函数，见 tools/utils.py
    error = validate_file_exists(file_path)
    if error:
        return error

    # Try to read as text
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding="gbk")
        except UnicodeDecodeError:
            return "❌ 无法读取文件（非文本文件或编码不支持）"
    except Exception as e:
        return f"❌ 读取文件失败: {e}"

    lines = content.splitlines()

    # Apply line range
    if start_line is not None or end_line is not None:
        start = max(1, start_line or 1) - 1  # Convert to 0-indexed
        end = end_line or len(lines)
        lines = lines[start:end]

    # Format with line numbers
    line_num_start = (start_line or 1)
    result_lines = []
    for i, line in enumerate(lines):
        result_lines.append(f"{line_num_start + i:6d}\t{line}")

    if not result_lines:
        return "(文件为空)"

    result = "\n".join(result_lines)

    # Add file info header
    total_lines = len(content.splitlines())
    if start_line is not None or end_line is not None:
        header = f"📄 {file_path} (行 {start_line or 1}-{end_line or total_lines}/{total_lines})\n"
    else:
        header = f"📄 {file_path} ({total_lines} 行)\n"

    return header + result
