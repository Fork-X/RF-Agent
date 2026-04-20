"""
verify_code tool implementation.

Runs project-appropriate code verification.
For Python: ruff / mypy / py_compile
For TypeScript: tsc --noEmit
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="verify_code",
    description="运行项目代码验证。自动检测项目类型并选择合适的验证工具（ruff/mypy/tsc 等）。",
    parameters={
        "path": {
            "type": "string",
            "description": "要验证的路径（文件或目录，默认当前目录）",
        },
    },
    required=[],
)


def implementation(args: dict[str, Any]) -> str:
    """
    Run code verification based on project type.

    Args:
        args: {
            "path": str | None,
        }

    Returns:
        Verification results
    """
    target_path = Path(args.get("path", ".")).expanduser().resolve()

    if not target_path.exists():
        return f"❌ 路径不存在: {target_path}"

    # Detect project type
    has_pyproject = (target_path / "pyproject.toml").exists() if target_path.is_dir() else False
    has_setup_py = (target_path / "setup.py").exists() if target_path.is_dir() else False
    has_tsconfig = (target_path / "tsconfig.json").exists() if target_path.is_dir() else False
    has_package_json = (target_path / "package.json").exists() if target_path.is_dir() else False

    is_python_file = target_path.suffix == ".py" if target_path.is_file() else False
    is_ts_file = target_path.suffix in (".ts", ".tsx") if target_path.is_file() else False

    # Determine which tools to use
    tools_to_try: list[tuple[str, list[str], str]] = []

    if is_python_file or has_pyproject or has_setup_py:
        # Python project
        target = str(target_path)

        # Try ruff first
        tools_to_try.append(("ruff", ["ruff", "check", target], "Ruff lint"))

        # Try mypy
        tools_to_try.append(("mypy", ["mypy", "--no-error-summary", target], "Mypy type check"))

        # Fallback: py_compile
        if target_path.is_file() and target_path.suffix == ".py":
            tools_to_try.append((
                "py_compile",
                ["python", "-m", "py_compile", target],
                "Python syntax check",
            ))

    elif is_ts_file or has_tsconfig or has_package_json:
        # TypeScript project
        target = str(target_path)

        if has_tsconfig:
            tools_to_try.append(("tsc", ["npx", "tsc", "--noEmit"], "TypeScript type check"))

    else:
        # Unknown project type - try Python tools as fallback
        target = str(target_path)
        tools_to_try.append((
            "py_compile",
            ["python", "-m", "compileall", "-q", target],
            "Python syntax check",
        ))

    if not tools_to_try:
        return f"⚠️ 无法确定项目类型，跳过验证: {target_path}"

    # Run tools
    results: list[str] = []
    error_count = 0

    for _tool_name, cmd, description in tools_to_try:
        try:
            result = subprocess.run(
                cmd,
                cwd=str(target_path) if target_path.is_dir() else str(target_path.parent),
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                results.append(f"✅ {description}: 通过")
            else:
                error_count += 1
                output = result.stdout.strip() or result.stderr.strip()
                if output:
                    # Truncate long output
                    lines = output.split("\n")[:20]
                    output = "\n".join(lines)
                    if len(lines) > 20:
                        output += f"\n... 还有 {len(lines) - 20} 行"
                results.append(f"❌ {description}:\n{output}")

        except FileNotFoundError:
            # Tool not installed, skip
            continue
        except subprocess.TimeoutExpired:
            results.append(f"⚠️ {description}: 超时")
        except Exception as e:
            results.append(f"❌ {description}: {e}")

    if not results:
        return "⚠️ 未找到可用的验证工具\n建议安装: ruff (pip install ruff) 或 mypy"

    header = f"🔍 代码验证: {target_path}\n{'─' * 40}\n"
    return header + "\n\n".join(results)
