"""
Tools package for QuanGan.

This package provides all tools organized by category:
- filesystem: File operations (read, write, edit, list)
- code: Code analysis (search, verify)
- command: Shell execution
- system: OS operations (open app, open URL, AppleScript)
- browser: Web automation
- search: Web search via Tavily API
"""

from __future__ import annotations

from .browser import create_browser_tools
from .code import create_code_tools
from .command import create_command_tools, create_shell_tools
from .filesystem import create_filesystem_tools
from .search import create_search_tools
from .system import create_system_tools

__all__ = [
    "create_filesystem_tools",
    "create_code_tools",
    "create_command_tools",
    "create_shell_tools",
    "create_system_tools",
    "create_browser_tools",
    "create_search_tools",
]
