"""
Daily Agent tools collection.

Exports all daily tools and provides a factory function.
"""

from __future__ import annotations

from typing import Any, Callable

from quangan.tools.types import ToolDefinition

from . import open_app, open_url, run_shell, run_applescript, browser


def create_all_daily_tools() -> list[tuple[ToolDefinition, Callable[[dict[str, Any]], Any], bool]]:
    """
    Create all daily tools.

    Returns:
        List of (definition, implementation, readonly) tuples
    """
    return [
        (open_app.definition, open_app.implementation, False),
        (open_url.definition, open_url.implementation, False),
        (run_shell.definition, run_shell.implementation, False),
        (run_applescript.definition, run_applescript.implementation, False),
        (browser.definition, browser.implementation, False),
    ]


# Static list
ALL_DAILY_TOOLS: list[tuple[ToolDefinition, Callable[[dict[str, Any]], Any], bool]] = [
    (open_app.definition, open_app.implementation, False),
    (open_url.definition, open_url.implementation, False),
    (run_shell.definition, run_shell.implementation, False),
    (run_applescript.definition, run_applescript.implementation, False),
    (browser.definition, browser.implementation, False),
]
