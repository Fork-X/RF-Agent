"""
open_url tool implementation.

Opens URLs in default browser or performs web searches.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any

from quangan.tools.types import ToolDefinition, make_tool_definition

# URL pattern
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="open_url",
    description="打开网址或进行网页搜索。如果输入不是 URL，会自动进行 Google 搜索。",
    parameters={
        "url_or_query": {
            "type": "string",
            "description": "网址或搜索关键词",
        },
    },
    required=["url_or_query"],
)


def implementation(args: dict[str, Any]) -> str:
    """
    Open a URL or perform a web search.

    Args:
        args: {
            "url_or_query": str,
        }

    Returns:
        Success message
    """
    query = args["url_or_query"]

    # Check if it's a URL
    if URL_PATTERN.match(query):
        url = query
        action = "打开网址"
    else:
        # Treat as search query
        import urllib.parse

        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.google.com/search?q={encoded}"
        action = "搜索"

    try:
        subprocess.run(
            ["open", url],
            check=True,
            capture_output=True,
        )
        return f"✅ 已{action}: {query}"
    except subprocess.CalledProcessError as e:
        return f"❌ 打开失败: {e}"
    except Exception as e:
        return f"❌ 打开失败: {e}"
