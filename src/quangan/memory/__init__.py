"""
Memory system package.

Exports:
- create_memory_tools: Factory for all memory tools
- Store functions for direct access
- Data types
"""

from __future__ import annotations

from typing import Any

from quangan.llm.types import ILLMClient
from quangan.tools.types import ToolDefinition

from .store import (
    MEMORY_BASE_DIR,
    CoreMemoryData,
    CoreMemoryItem,
    append_life_memory,
    get_core_memory,
    get_memory_dir,
    get_recent_life_memories,
)
from .tools import (
    consolidate_core_memory_def,
    create_memory_tool_impls,
    recall_memory_def,
    update_life_memory_def,
)


def create_memory_tools(
    client: ILLMClient, cwd: str
) -> list[tuple[ToolDefinition, Any, bool]]:
    """
    Create all memory tools for registration.

    Args:
        client: LLM client (needed for consolidate_core_memory)
        cwd: Working directory for memory storage

    Returns:
        List of (definition, implementation, readonly) tuples
    """
    impls = create_memory_tool_impls(client, cwd)

    return [
        (recall_memory_def, impls["recall_impl"], True),
        (update_life_memory_def, impls["update_life_impl"], False),
        (consolidate_core_memory_def, impls["consolidate_impl"], False),
    ]


__all__ = [
    # Factory
    "create_memory_tools",
    "create_memory_tool_impls",
    # Store functions
    "MEMORY_BASE_DIR",
    "get_core_memory",
    "get_memory_dir",
    "append_life_memory",
    "get_recent_life_memories",
    # Types
    "CoreMemoryData",
    "CoreMemoryItem",
    # Tool definitions
    "recall_memory_def",
    "update_life_memory_def",
    "consolidate_core_memory_def",
]
