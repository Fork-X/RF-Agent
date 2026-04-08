"""
execute_command tool implementation.

Executes shell commands with security guards:
- Hard blacklist for dangerous commands
- Path traversal detection for rm/mv/cp
- y/N confirmation for out-of-project operations
- Background mode for long-running processes
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Awaitable, Callable

from quangan.tools.types import ToolDefinition, make_tool_definition

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Hard blacklist: always reject these
BLOCKED = ["sudo", "shutdown", "reboot", "mkfs", ":(){ :|:& };:"]

# Dangerous operations that need path checking
DANGEROUS_OPS = ["rm", "rmdir", "mv", "cp"]


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────


def _extract_paths(cmd: str) -> list[str]:
    """Extract non-flag arguments as path candidates."""
    parts = cmd.strip().split()
    # Skip the command itself and all flags (words starting with -)
    return [p for p in parts[1:] if not p.startswith("-")]


def _has_outside_path(cmd: str, work_dir: str) -> tuple[bool, list[str]]:
    """
    Check if the command operates on paths outside the project directory.

    Returns:
        (outside: bool, outside_paths: list[str])
    """
    candidates = _extract_paths(cmd)
    outside_paths: list[str] = []

    work_path = Path(work_dir).resolve()

    for p in candidates:
        try:
            expanded_path = os.path.expanduser(p)  # 展开 ~ 为实际路径
            abs_path = Path(expanded_path).resolve()
        except Exception:
            continue

        # Path must equal work_dir or start with work_dir/
        if abs_path != work_path and not str(abs_path).startswith(str(work_path) + os.sep):
            outside_paths.append(str(abs_path))

    return len(outside_paths) > 0, outside_paths


def _is_dangerous_op(cmd: str) -> bool:
    """Check if the command is a dangerous operation (rm, mv, cp)."""
    first_word = cmd.strip().split()[0] if cmd.strip() else ""
    return first_word in DANGEROUS_OPS


# ─────────────────────────────────────────────────────────────────────────────
# Tool definition
# ─────────────────────────────────────────────────────────────────────────────

definition: ToolDefinition = make_tool_definition(
    name="execute_command",
    description="执行 shell 命令。短命令直接返回输出；启动服务等长驻进程请将 background 设为 true。",
    parameters={
        "command": {
            "type": "string",
            "description": "要执行的 shell 命令，例如: ls -la、npm run dev、python app.py",
        },
        "background": {
            "type": "boolean",
            "description": "是否后台运行。启动服务/项目时必须设为 true，否则会因超时误判为失败。默认 false。",
        },
    },
    required=["command"],
)


def create_implementation(
    work_dir: str,
    confirm_fn: Callable[[str], Awaitable[bool]] | None = None,
) -> Callable[[dict[str, Any]], Awaitable[str]]:
    """
    Factory function to create execute_command implementation with path safety guard.

    Args:
        work_dir: Project working directory for path boundary checks
        confirm_fn: Async callback for y/N confirmation when dangerous ops detected

    Returns:
        Tool implementation function
    """

    async def implementation(args: dict[str, Any]) -> str:
        cmd = args["command"].strip()
        background = args.get("background", False)

        # ── Hard blacklist check ──────────────────────────────────────
        for blocked in BLOCKED:
            if blocked in cmd:
                return f'🚫 拒绝执行危险命令: "{blocked}"'

        # ── Path traversal check for dangerous ops ────────────────────
        if _is_dangerous_op(cmd):
            outside, paths = _has_outside_path(cmd, work_dir)
            if outside:
                path_list = "\n".join(f"   • {p}" for p in paths)
                msg = f"⚠️  检测到操作路径超出项目目录\n   命令: {cmd}\n   越界路径:\n{path_list}"

                if confirm_fn:
                    ok = await confirm_fn(msg)
                    if not ok:
                        return "❌ 已取消：操作路径超出项目目录，用户拒绝执行"
                else:
                    return (
                        f"❌ 已拒绝：操作路径超出项目目录\n{path_list}\n"
                        f"   如需执行，请在终端手动运行。"
                    )

        # ── Background mode ────────────────────────────────────────────
        if background:
            try:
                # Detach process from parent
                process = subprocess.Popen(
                    ["sh", "-c", cmd],
                    cwd=work_dir,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return f"✅ 命令已在后台启动\n   PID: {process.pid}\n   命令: {cmd}"
            except Exception as e:
                return f"❌ 后台启动失败: {e}"

        # ── Sync execution ─────────────────────────────────────────────
        try:
            result = subprocess.run(
                ["sh", "-c", cmd],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=15,
            )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode == 0:
                return stdout or "(命令已执行，无输出)"
            else:
                # Exit code 1 with stdout: might be grep no match, etc.
                if result.returncode == 1 and stdout:
                    return stdout
                if result.returncode == 1 and not stdout:
                    return "(命令已执行，无匹配结果)"
                return f"命令执行失败 (退出码 {result.returncode}):\n{stderr}"

        except subprocess.TimeoutExpired:
            return (
                "⚠️ 命令执行超时（进程可能仍在运行中）\n"
                "提示：如果这是启动服务的命令，请将 background 参数设为 true"
            )
        except Exception as e:
            return f"❌ 命令执行失败: {e}"

    return implementation


# Default implementation without path guard (for backward compatibility)
implementation = create_implementation(os.getcwd())
