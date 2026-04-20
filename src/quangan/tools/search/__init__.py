"""
Search tools package.

Provides web search capabilities via Tavily API.
"""

from __future__ import annotations

from quangan.tools.search.tavily_search import definition, implementation
from quangan.tools.types import ToolRegistration


def create_search_tools() -> list[ToolRegistration]:
    """Create web search tool registrations.

    Returns:
        List of (definition, implementation, readonly) tuples.
    """
    return [(definition, implementation, True)]  # readonly=True
