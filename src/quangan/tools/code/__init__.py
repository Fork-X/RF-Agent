"""
Code tools for code analysis and verification.

Provides tools for searching and verifying code.
"""

from __future__ import annotations

from typing import Any, Callable

from quangan.tools.types import ToolDefinition

from .search_code import definition as search_code_def, implementation as search_code_impl
from .verify_code import definition as verify_code_def, implementation as verify_code_impl


def create_code_tools() -> list[tuple[ToolDefinition, Callable[[dict[str, Any]], Any], bool]]:
    """
    Create all code tools.

    Returns:
        List of (definition, implementation, readonly) tuples
    """
    return [
        (search_code_def, search_code_impl, True),
        (verify_code_def, verify_code_impl, False),
    ]
