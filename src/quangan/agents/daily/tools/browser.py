"""
browser_action tool implementation.

Playwright-based browser automation with two connection modes:
1. CDP: Connect to existing Chrome via DevTools Protocol
2. Persistent: Headless browser with persistent profile

Actions:
- navigate: Go to URL
- click: Click element
- type: Type text into element
- press_key: Press keyboard key
- get_page_text: Extract page text
- get_elements: Find elements by selector
- wait_for: Wait for element/timeout
- close: Close browser
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from quangan.tools.types import ToolDefinition, make_tool_definition

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

CDP_ENDPOINT = "http://localhost:9222"
PROFILE_DIR = Path.home() / ".xiaoyu-browser-profile"

# ─────────────────────────────────────────────────────────────────────────────
# Module-level state (equivalent to TS module-level vars)
# ─────────────────────────────────────────────────────────────────────────────

_mode: Literal["cdp", "persistent", "unknown"] = "unknown"
_cdp_browser: Any = None  # Playwright Browser
_cdp_context: Any = None  # BrowserContext
_persistent_ctx: Any = None  # BrowserContext for persistent mode
_page: Any = None  # Page


# ─────────────────────────────────────────────────────────────────────────────
# Tool definition
# ─────────────────────────────────────────────────────────────────────────────

definition: ToolDefinition = make_tool_definition(
    name="browser_action",
    description="浏览器自动化操作。支持导航、点击、输入、截图等。优先连接已有浏览器，否则启动无头浏览器。",
    parameters={
        "action": {
            "type": "string",
            "description": "操作类型",
            "enum": ["navigate", "click", "type", "press_key", "get_page_text", "get_elements", "wait_for", "close"],
        },
        "url": {
            "type": "string",
            "description": "URL (navigate 操作)",
        },
        "selector": {
            "type": "string",
            "description": "CSS 选择器",
        },
        "text": {
            "type": "string",
            "description": "输入文本 (type 操作)",
        },
        "key": {
            "type": "string",
            "description": "按键名称 (press_key 操作)",
        },
        "timeout": {
            "type": "integer",
            "description": "超时时间（毫秒）",
        },
    },
    required=["action"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Browser management
# ─────────────────────────────────────────────────────────────────────────────


async def _ensure_context() -> tuple[Any, Any]:
    """
    Ensure browser context is available.

    Priority:
    1. CDP connection (existing browser)
    2. Persistent context (headless with profile)

    Returns:
        (context, page) tuple
    """
    global _mode, _cdp_browser, _cdp_context, _persistent_ctx, _page

    from playwright.async_api import async_playwright

    # Try CDP first
    if _mode == "unknown":
        try:
            pw = await async_playwright().start()
            _cdp_browser = await pw.chromium.connect_over_cdp(CDP_ENDPOINT)
            contexts = _cdp_browser.contexts
            if contexts:
                _cdp_context = contexts[0]
                pages = _cdp_context.pages
                _page = pages[0] if pages else await _cdp_context.new_page()
                _mode = "cdp"
            else:
                _cdp_context = await _cdp_browser.new_context()
                _page = await _cdp_context.new_page()
                _mode = "cdp"
        except Exception:
            # CDP failed, try persistent
            _mode = "persistent"

    # Persistent context
    if _mode == "persistent" and _persistent_ctx is None:
        pw = await async_playwright().start()
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        _persistent_ctx = await pw.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
        )
        _page = _persistent_ctx.pages[0] if _persistent_ctx.pages else await _persistent_ctx.new_page()

    if _mode == "cdp":
        return _cdp_context, _page
    return _persistent_ctx, _page


async def _get_page() -> Any:
    """Get or create a page."""
    global _page

    if _page is None:
        await _ensure_context()
    return _page


# ─────────────────────────────────────────────────────────────────────────────
# Action implementations
# ─────────────────────────────────────────────────────────────────────────────


async def _action_navigate(url: str) -> str:
    """Navigate to URL."""
    page = await _get_page()
    await page.goto(url)
    return f"✅ 已导航到: {url}"


async def _action_click(selector: str) -> str:
    """Click element."""
    page = await _get_page()
    await page.click(selector)
    return f"✅ 已点击: {selector}"


async def _action_type(selector: str, text: str) -> str:
    """Type text into element."""
    page = await _get_page()
    await page.fill(selector, text)
    return f"✅ 已输入: {text}"


async def _action_press_key(key: str) -> str:
    """Press keyboard key."""
    page = await _get_page()
    await page.keyboard.press(key)
    return f"✅ 已按下: {key}"


async def _action_get_page_text() -> str:
    """Extract page text content."""
    page = await _get_page()
    text = await page.evaluate("() => document.body.innerText")
    # Truncate long text
    if len(text) > 2000:
        text = text[:2000] + "...(已截断)"
    return f"📄 页面内容:\n{text}"


async def _action_get_elements(selector: str) -> str:
    """Find elements by selector."""
    page = await _get_page()
    elements = await page.query_selector_all(selector)

    results = []
    for i, el in enumerate(elements[:20]):  # Limit to 20
        text = await el.inner_text()
        tag = await el.evaluate("el => el.tagName")
        results.append(f"{i + 1}. <{tag}> {text[:100]}")

    if not results:
        return f"未找到元素: {selector}"

    return f"🔍 找到 {len(elements)} 个元素:\n" + "\n".join(results)


async def _action_wait_for(selector: str | None, timeout: int) -> str:
    """Wait for element or timeout."""
    page = await _get_page()

    if selector:
        await page.wait_for_selector(selector, timeout=timeout)
        return f"✅ 等待元素: {selector}"
    else:
        await page.wait_for_timeout(timeout)
        return f"✅ 等待 {timeout}ms"


async def _action_close() -> str:
    """Close browser."""
    global _mode, _cdp_browser, _cdp_context, _persistent_ctx, _page

    if _mode == "cdp" and _cdp_browser:
        await _cdp_browser.close()
    elif _mode == "persistent" and _persistent_ctx:
        await _persistent_ctx.close()

    _mode = "unknown"
    _cdp_browser = None
    _cdp_context = None
    _persistent_ctx = None
    _page = None

    return "✅ 浏览器已关闭"


# ─────────────────────────────────────────────────────────────────────────────
# Main implementation
# ─────────────────────────────────────────────────────────────────────────────


async def implementation(args: dict[str, Any]) -> str:
    """
    Execute browser action.

    Args:
        args: {
            "action": str,
            "url": str | None,
            "selector": str | None,
            "text": str | None,
            "key": str | None,
            "timeout": int | None,
        }

    Returns:
        Action result
    """
    action = args["action"]
    url = args.get("url")
    selector = args.get("selector")
    text = args.get("text")
    key = args.get("key")
    timeout = args.get("timeout", 5000)

    try:
        if action == "navigate":
            if not url:
                return "❌ navigate 操作需要 url 参数"
            return await _action_navigate(url)

        elif action == "click":
            if not selector:
                return "❌ click 操作需要 selector 参数"
            return await _action_click(selector)

        elif action == "type":
            if not selector or not text:
                return "❌ type 操作需要 selector 和 text 参数"
            return await _action_type(selector, text)

        elif action == "press_key":
            if not key:
                return "❌ press_key 操作需要 key 参数"
            return await _action_press_key(key)

        elif action == "get_page_text":
            return await _action_get_page_text()

        elif action == "get_elements":
            if not selector:
                return "❌ get_elements 操作需要 selector 参数"
            return await _action_get_elements(selector)

        elif action == "wait_for":
            return await _action_wait_for(selector, timeout)

        elif action == "close":
            return await _action_close()

        else:
            return f"❌ 未知操作: {action}"

    except Exception as e:
        return f"❌ 浏览器操作失败: {e}"
