"""
run_applescript tool implementation.

Executes AppleScript for macOS automation.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="run_applescript",
    description="执行 AppleScript 脚本，用于 macOS 自动化操作。可控制系统、应用、UI 等。",
    parameters={
        "script": {
            "type": "string",
            "description": "AppleScript 代码",
        },
    },
    required=["script"],
)


def implementation(args: dict[str, Any]) -> str:
    """
    Execute AppleScript.

    Args:
        args: {
            "script": str,
        }

    Returns:
        Script output or error message
    """
    script = args["script"]

    # Write to temp file
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".applescript", delete=False
        ) as f:
            f.write(script)
            temp_path = f.name
    except Exception as e:
        return f"❌ 创建临时文件失败: {e}"

    try:
        result = subprocess.run(
            ["osascript", temp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            return stdout or "✅ AppleScript 执行成功"
        else:
            # Check for permission error
            if "1002" in stderr or "not allowed" in stderr.lower():
                return (
                    f"❌ 权限不足：需要辅助功能权限\n"
                    f"请在 系统偏好设置 > 安全性与隐私 > 隐私 > 辅助功能 中添加终端应用。\n"
                    f"错误: {stderr}"
                )
            return f"❌ AppleScript 执行失败:\n{stderr}"

    except subprocess.TimeoutExpired:
        return "⚠️ AppleScript 执行超时"
    except Exception as e:
        return f"❌ 执行失败: {e}"
    finally:
        # Cleanup temp file
        try:
            Path(temp_path).unlink()
        except Exception:
            pass
