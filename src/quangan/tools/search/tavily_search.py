"""
tavily_search tool implementation.

Real-time web search via Tavily API.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from quangan.tools.types import ToolDefinition, make_tool_definition

# ─────────────────────────────────────────────────────────────────────────────
# Tool definition
# ─────────────────────────────────────────────────────────────────────────────

definition: ToolDefinition = make_tool_definition(
    name="tavily_search",
    description="实时网络搜索。调用 Tavily API 获取最新网络信息。",
    parameters={
        "query": {
            "type": "string",
            "description": "搜索关键词",
        },
        "max_results": {
            "type": "integer",
            "description": "最大返回结果数，默认 5",
        },
        "search_depth": {
            "type": "string",
            "description": "搜索深度，默认 basic",
            "enum": ["basic", "advanced"],
        },
    },
    required=["query"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Implementation
# ─────────────────────────────────────────────────────────────────────────────


async def implementation(args: dict[str, Any]) -> str:
    """
    Execute Tavily search.

    Args:
        args: {
            "query": str,
            "max_results": int | None,
            "search_depth": str | None,
        }

    Returns:
        Formatted search results in Markdown
    """
    query = args["query"]
    max_results = args.get("max_results", 5)
    search_depth = args.get("search_depth", "basic")

    # Get API key from environment
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "❌ 未配置 TAVILY_API_KEY 环境变量，请在 .env 文件中添加"

    # Build request payload
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": True,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            data = response.json()

        # Format results as Markdown
        output_parts: list[str] = []

        # Add answer summary if available
        if answer := data.get("answer"):
            output_parts.append(f"## 摘要\n{answer}\n")

        # Add search results
        output_parts.append("## 搜索结果\n")

        results = data.get("results", [])
        for i, result in enumerate(results, 1):
            title = result.get("title", "无标题")
            content = result.get("content", "")
            url = result.get("url", "")

            # Truncate content to 500 chars
            if len(content) > 500:
                content = content[:500] + "..."

            output_parts.append(f"### {i}. {title}\n{content}\n🔗 {url}\n")

        output = "\n".join(output_parts)

        # Truncate total output to 3000 chars
        if len(output) > 3000:
            output = output[:3000] + "\n...(已截断)"

        return output

    except httpx.TimeoutException:
        return "❌ 搜索请求超时"
    except httpx.HTTPStatusError as e:
        return f"❌ Tavily API 错误: {e.response.status_code}"
    except Exception as e:
        return f"❌ 搜索失败: {e}"
