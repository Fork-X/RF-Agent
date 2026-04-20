"""
Memory storage layer.

Provides file I/O for the two-layer memory architecture:
- CoreMemory: Long-term stable memories (JSON file)
- LifeMemory: Daily session summaries (markdown files in life/ subdirectory)

Memory directory is fixed at the QUANGAN-py project root, independent of CWD.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from quangan.config.paths import get_memory_base_dir

# Refactor: [设计缺陷] 消除硬编码路径依赖，改用统一路径解析
MEMORY_BASE_DIR = get_memory_base_dir()


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CoreMemoryItem:
    """A single core memory entry."""

    id: str
    content: str
    first_seen: str  # YYYY-MM-DD
    reinforce_count: int = 1


@dataclass
class CoreMemoryData:
    """Core memory data structure."""

    updated_at: str
    memories: list[CoreMemoryItem]


@dataclass
class LifeMemoryFile:
    """A life memory file entry."""

    filename: str
    date: str
    content: str


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────


def _today_str() -> str:
    """Get today's date as YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


def _extract_date_from_filename(filename: str) -> str:
    """Extract date from lifeMemory filename."""
    import re

    match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    return match.group(1) if match else _today_str()


# ─────────────────────────────────────────────────────────────────────────────
# Directory management
# ─────────────────────────────────────────────────────────────────────────────


def get_memory_dir(project_root: str | None = None) -> Path:
    """Get memory directory path, creating if needed.

    Refactor: [可维护性] 参数语义从 cwd 修正为 project_root，移除嵌套保护逻辑。

    Args:
        project_root: Project root directory. If None, uses auto-detected root.

    Returns:
        Path to .memory directory.
    """
    if project_root is None:
        return get_memory_base_dir()
    dir_path = Path(project_root) / ".memory"
    dir_path.mkdir(parents=True, exist_ok=True)
    life_dir = dir_path / "life"
    life_dir.mkdir(parents=True, exist_ok=True)
    return dir_path


# ─────────────────────────────────────────────────────────────────────────────
# CoreMemory operations
# ─────────────────────────────────────────────────────────────────────────────


def get_core_memory(cwd: str) -> CoreMemoryData:
    """
    Read core memory from file.

    Args:
        cwd: Working directory

    Returns:
        CoreMemoryData (empty if file doesn't exist)
    """
    file_path = get_memory_dir(cwd) / "core-memory.json"

    if not file_path.exists():
        return CoreMemoryData(updated_at=_today_str(), memories=[])

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        memories = [CoreMemoryItem(**m) for m in data.get("memories", [])]
        return CoreMemoryData(
            updated_at=data.get("updatedAt", _today_str()),
            memories=memories,
        )
    except (json.JSONDecodeError, KeyError):
        return CoreMemoryData(updated_at=_today_str(), memories=[])


def save_core_memory(cwd: str, data: CoreMemoryData) -> None:
    """
    Save core memory to file.

    Args:
        cwd: Working directory
        data: Core memory data to save
    """
    file_path = get_memory_dir(cwd) / "core-memory.json"

    json_data = {
        "updatedAt": data.updated_at,
        "memories": [asdict(m) for m in data.memories],
    }

    file_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# LifeMemory operations
# ─────────────────────────────────────────────────────────────────────────────


def append_life_memory(cwd: str, theme: str, summary: str) -> str:
    """
    Append a life memory entry.

    Args:
        cwd: Working directory
        theme: Short theme/title (3-8 characters)
        summary: Memory summary text

    Returns:
        Filename of created file
    """
    life_dir = get_memory_dir(cwd) / "life"

    # Generate filename
    import time

    short_id = base36_encode(int(time.time() * 1000))[-6:]
    date = _today_str()

    # Sanitize theme for filename
    import re

    safe_theme = re.sub(r'[/\\:*?"<>|\s]', "-", theme)
    safe_theme = re.sub(r"-+", "-", safe_theme)[:20]

    filename = f"lifeMemory-{safe_theme}-{date}-{short_id}.md"
    file_path = life_dir / filename

    # Write content
    content = f"# {theme}\n\n日期：{date}\n\n{summary}\n"
    file_path.write_text(content, encoding="utf-8")

    return filename


def get_recent_life_memories(cwd: str, days: int = 7) -> list[LifeMemoryFile]:
    """
    Get recent life memory files.

    Args:
        cwd: Working directory
        days: Number of days to look back

    Returns:
        List of LifeMemoryFile entries sorted by date
    """
    life_dir = get_memory_dir(cwd) / "life"

    if not life_dir.exists():
        return []

    # Calculate cutoff date
    from datetime import timedelta

    cutoff = datetime.now() - timedelta(days=days)

    result: list[LifeMemoryFile] = []

    for file_path in life_dir.iterdir():
        if not file_path.name.startswith("lifeMemory-") or not file_path.name.endswith(".md"):
            continue

        date_str = _extract_date_from_filename(file_path.name)
        try:
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue

        if file_date >= cutoff:
            result.append(
                LifeMemoryFile(
                    filename=file_path.name,
                    date=date_str,
                    content=file_path.read_text(encoding="utf-8"),
                )
            )

    # Sort by date
    result.sort(key=lambda x: x.date)
    return result


def base36_encode(num: int) -> str:
    """Encode an integer as base36 string."""
    if num == 0:
        return "0"

    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = []

    while num:
        result.append(chars[num % 36])
        num //= 36

    return "".join(reversed(result))
