"""
CLI execution context container.

Refactor: [设计缺陷] cli/main.py 使用 8 个模块级全局变量在多函数间共享状态，
导致不可测试、并发不安全。引入 CLIContext 封装所有可变状态。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CLIContext:
    """Encapsulates all mutable state for the CLI session.

    Replaces module-level global variables to improve testability
    and make state flow explicit.

    Attributes:
        config: Current LLM configuration.
        client: Active LLM client instance.
        agent: Main agent instance.
        project_root: Project root directory path.
        model_max_tokens: Max token limit for current model.
        cwd: Current working directory string.
        is_plan_mode: Whether plan mode is active.
        is_agent_running: Whether agent is currently executing.
        current_spinner: Active spinner instance (if any).
        life_memory_update_count: Counter for life memory updates in session.
    """

    config: Any  # LLMConfig - use Any to avoid circular import
    client: Any  # ILLMClient
    agent: Any  # Agent
    project_root: Path
    model_max_tokens: int = 128_000
    cwd: str = ""
    is_plan_mode: bool = False
    is_agent_running: bool = False
    current_spinner: Any = None
    life_memory_update_count: int = 0
