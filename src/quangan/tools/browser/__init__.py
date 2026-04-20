"""
Browser tools for web automation.

Provides tools for browser automation using Playwright.
"""

from __future__ import annotations

from quangan.tools.types import ToolRegistration

from .browser import definition as browser_def
from .browser import implementation as browser_impl


def create_browser_tools() -> list[ToolRegistration]:
    """Create browser automation tool registrations.

    Returns:
        List of (definition, implementation, readonly) tuples.
    """
    return [
        (browser_def, browser_impl, False),
    ]
