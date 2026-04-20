"""
Code tools for code analysis and verification.

Provides tools for searching and verifying code.
"""

from __future__ import annotations

from quangan.tools.types import ToolRegistration

from .search_code import definition as search_code_def
from .search_code import implementation as search_code_impl
from .verify_code import definition as verify_code_def
from .verify_code import implementation as verify_code_impl


def create_code_tools() -> list[ToolRegistration]:
    """Create code analysis tool registrations.

    Returns:
        List of (definition, implementation, readonly) tuples.
    """
    return [
        (search_code_def, search_code_impl, True),
        (verify_code_def, verify_code_impl, False),
    ]
