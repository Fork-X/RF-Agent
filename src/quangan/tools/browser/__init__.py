"""
Browser tools for web automation.

Provides tools for browser automation using Playwright.
"""

from __future__ import annotations

from typing import Any, Callable

from quangan.tools.types import ToolDefinition

from .browser import definition as browser_def, implementation as browser_impl


def create_browser_tools() -> list[tuple[ToolDefinition, Callable[[dict[str, Any]], Any], bool]]:
    """
    Create all browser tools.

    Returns:
        List of (definition, implementation, readonly) tuples
    """
    return [
        (browser_def, browser_impl, False),
    ]
