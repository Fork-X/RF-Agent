"""
open_app tool implementation.

Opens macOS applications.
"""

from __future__ import annotations

import subprocess
from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="open_app",
    description="打开 macOS 应用程序。输入应用名称即可打开。",
    parameters={
        "app_name": {
            "type": "string",
            "description": "应用程序名称，例如: Safari、Finder、Visual Studio Code",
        },
    },
    required=["app_name"],
)


def implementation(args: dict[str, Any]) -> str:
    """
    Open a macOS application.

    Args:
        args: {
            "app_name": str,
        }

    Returns:
        Success or error message
    """
    app_name = args["app_name"]

    try:
        subprocess.run(
            ["open", "-a", app_name],
            check=True,
            capture_output=True,
            text=True,
        )
        return f"✅ 已打开应用: {app_name}"
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else "未知错误"
        return f"❌ 打开应用失败: {app_name}\n{stderr}"
    except Exception as e:
        return f"❌ 打开应用失败: {e}"
