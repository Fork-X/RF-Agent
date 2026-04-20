"""
Unified project path resolution.

Refactor: [设计缺陷] 消除 3 处 Path(__file__).parents[3] 硬编码路径依赖，
统一为基于标记文件（pyproject.toml/.git）的项目根目录发现机制。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """Discover project root by searching for pyproject.toml or .git.

    Walks up from this file's location until a marker file is found.
    Result is cached for the process lifetime.

    Returns:
        Path to the project root directory.

    Raises:
        FileNotFoundError: If no marker file is found.
    """
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "pyproject.toml").exists() or (current / ".git").exists():
            return current
        current = current.parent
    raise FileNotFoundError(
        "Cannot locate project root (no pyproject.toml or .git found)"
    )


def get_memory_base_dir() -> Path:
    """Get the .memory directory path under project root.

    Returns:
        Path to .memory directory (created if needed).
    """
    memory_dir = get_project_root() / ".memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


def get_sessions_dir() -> Path:
    """Get the .sessions directory path under project root.

    Returns:
        Path to .sessions directory (created if needed).
    """
    sessions_dir = get_project_root() / ".sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


def get_env_file() -> Path:
    """Get .env file path under project root.

    Returns:
        Path to .env file.
    """
    return get_project_root() / ".env"
