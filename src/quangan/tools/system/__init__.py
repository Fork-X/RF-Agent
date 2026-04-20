"""
System tools for OS operations.

Provides tools for opening apps, URLs, and running AppleScript.
"""

from __future__ import annotations

from quangan.tools.types import ToolRegistration

from .open_app import (
    definition as open_app_def,
)
from .open_app import (
    implementation as open_app_impl,
)
from .open_url import (
    definition as open_url_def,
)
from .open_url import (
    implementation as open_url_impl,
)
from .run_applescript import (
    definition as run_applescript_def,
)
from .run_applescript import (
    implementation as run_applescript_impl,
)


def create_system_tools() -> list[ToolRegistration]:
    """Create system tool registrations for OS operations.

    Returns:
        List of (definition, implementation, readonly) tuples.
    """
    return [
        (open_app_def, open_app_impl, False),
        (open_url_def, open_url_impl, False),
        (run_applescript_def, run_applescript_impl, False),
    ]
