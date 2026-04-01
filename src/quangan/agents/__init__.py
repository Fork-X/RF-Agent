"""
Agents module.

Exports sub-agent factories.
"""

from quangan.agents.coding import create_coding_agent
from quangan.agents.daily import create_daily_agent

__all__ = [
    "create_coding_agent",
    "create_daily_agent",
]
