"""
Session persistence.

Saves and loads conversation history per project.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

# Sessions directory
SESSIONS_DIR = Path(__file__).resolve().parents[3] / ".sessions"


def _ensure_sessions_dir() -> None:
    """Ensure sessions directory exists."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def get_session_file_path(cwd: str) -> Path:
    """
    Get session file path for a working directory.

    Uses MD5 hash of cwd to create unique filename.

    Args:
        cwd: Working directory path

    Returns:
        Path to session file
    """
    _ensure_sessions_dir()

    # Create hash from cwd
    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]

    # Get project name
    project_name = Path(cwd).name
    # Sanitize project name
    import re

    safe_name = re.sub(r"[^a-zA-Z0-9]", "-", project_name)

    return SESSIONS_DIR / f"{safe_name}-{cwd_hash}.json"


def load_session(cwd: str) -> list[dict[str, Any]]:
    """
    Load session from file.

    Args:
        cwd: Working directory path

    Returns:
        List of messages (empty if no session)
    """
    file_path = get_session_file_path(cwd)

    if not file_path.exists():
        return []

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, Exception):
        return []


def save_session(cwd: str, messages: list[dict[str, Any]]) -> None:
    """
    Save session to file.

    Filters out system messages (except _summary markers).

    Args:
        cwd: Working directory path
        messages: Message history to save
    """
    _ensure_sessions_dir()
    file_path = get_session_file_path(cwd)

    # Filter: remove system messages unless they have _summary
    to_save = [msg for msg in messages if msg.get("role") != "system" or msg.get("_summary")]

    file_path.write_text(json.dumps(to_save, indent=2, ensure_ascii=False), encoding="utf-8")


def clear_session(cwd: str) -> str | None:
    """
    Clear session by archiving it.

    Args:
        cwd: Working directory path

    Returns:
        Archived filename if session existed, None otherwise
    """
    file_path = get_session_file_path(cwd)

    if not file_path.exists():
        return None

    # Create archive filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    archive_path = file_path.with_name(f"{file_path.stem}-archive-{timestamp}.json")

    # Rename to archive
    file_path.rename(archive_path)

    return archive_path.name
