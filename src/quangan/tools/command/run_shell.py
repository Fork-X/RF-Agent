"""
run_shell tool implementation.

Executes shell commands without path guard (for daily tasks).
"""

from __future__ import annotations

import subprocess
from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition

# Hard blacklist
BLOCKED = ["sudo", "shutdown", "reboot", "mkfs", ":(){ :|:& };:"]

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="run_shell",
    description="执行 shell 命令。适合执行系统命令、脚本等。",
    parameters={
        "command": {
            "type": "string",
            "description": "要执行的 shell 命令",
        },
    },
    required=["command"],
)


def implementation(args: dict[str, Any]) -> str:
    """
    Execute a shell command.

    Args:
        args: {
            "command": str,
        }

    Returns:
        Command output or error message
    """
    cmd = args["command"].strip()

    # Check blacklist
    for blocked in BLOCKED:
        if blocked in cmd:
            return f'🚫 拒绝执行危险命令: "{blocked}"'

    try:
        result = subprocess.run(
            ["sh", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=30,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            return stdout or "(命令已执行，无输出)"
        else:
            if result.returncode == 1 and stdout:
                return stdout
            return f"命令执行失败 (退出码 {result.returncode}):\n{stderr}"

    except subprocess.TimeoutExpired:
        return "⚠️ 命令执行超时（30秒）"
    except Exception as e:
        return f"❌ 命令执行失败: {e}"
