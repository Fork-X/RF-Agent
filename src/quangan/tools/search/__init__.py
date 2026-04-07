"""
Search tools package.

Provides web search capabilities via Tavily API.
"""

from __future__ import annotations

from quangan.tools.search.tavily_search import definition, implementation


def create_search_tools():
    """Create search tool entries for agent registration."""
    return [(definition, implementation, True)]  # readonly=True
