"""
Anthropic Messages API client.

This module provides AnthropicClient for providers that use the Anthropic
protocol (e.g., Kimi for Coding at api.kimi.com/coding/v1).

Key differences from OpenAI protocol:
- Endpoint: POST /messages (not /chat/completions)
- Auth: x-api-key header + anthropic-version header
- System: Top-level field, not in messages array
- Tools: tool_use/tool_result blocks instead of tool_calls
- Thinking: Explicit enable for reasoning models (k2p5, kimi-k2-thinking)
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from quangan.config.llm_config import LLMConfig
from quangan.llm._cancel_support import request_with_retry
from quangan.llm.types import (
    AgentCallRequest,
    AgentCallResponse,
    ChatMessage,
    ChatOptions,
    ILLMClient,
    TokenUsage,
)
from quangan.tools.types import ToolCall, ToolDefinition


class AnthropicClient(ILLMClient):
    """
    Anthropic Messages API client.

    Implements ILLMClient for providers using the Anthropic protocol.
    Handles message format conversion between OpenAI and Anthropic formats.
    """

    # Models that need thinking mode enabled
    THINKING_MODELS = ["k2p5", "kimi-k2-thinking", "kimi-k2p5"]

    def __init__(self, config: LLMConfig) -> None:
        """
        Initialize the client.

        Args:
            config: LLM configuration

        Raises:
            ValueError: If required config fields are missing
        """
        self._config = config
        self._validate_config()
        self._client = httpx.AsyncClient(timeout=float(config.timeout_seconds))

    def _validate_config(self) -> None:
        """Validate that required configuration fields are present."""
        if not self._config.api_key:
            raise ValueError("API Key 不能为空")
        if not self._config.base_url:
            raise ValueError("Base URL 不能为空")
        if not self._config.model:
            raise ValueError("模型名称不能为空")

    @property
    def config(self) -> LLMConfig:
        return self._config

    def _needs_thinking(self) -> bool:
        """Check if the current model needs thinking mode enabled."""
        return any(p in self._config.model for p in self.THINKING_MODELS)

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for Anthropic API requests."""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._config.api_key,
            "anthropic-version": "2023-06-01",
        }
        if self._config.headers:
            headers.update(self._config.headers)
        return headers

    def _convert_messages(self, raw_messages: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Convert OpenAI-format messages to Anthropic format.

        Returns a dict with:
        - system: Top-level system prompt string
        - messages: List of user/assistant/tool messages in Anthropic format
        """
        # Extract system messages
        system_parts = []
        for msg in raw_messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if isinstance(content, str):
                    system_parts.append(content)
                else:
                    system_parts.append(json.dumps(content))
        system = "\n\n".join(system_parts)

        # Convert non-system messages
        converted: list[dict[str, Any]] = []
        non_system = [m for m in raw_messages if m.get("role") != "system"]

        i = 0
        while i < len(non_system):
            msg = non_system[i]

            if msg.get("role") == "tool":
                # Collect consecutive tool results and merge into one user message
                tool_results: list[dict[str, Any]] = []
                while i < len(non_system) and non_system[i].get("role") == "tool":
                    tr = non_system[i]
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tr.get("tool_call_id", ""),
                        "content": tr.get("content", "") or "",
                    })
                    i += 1
                converted.append({"role": "user", "content": tool_results})

            elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                # Convert tool_calls to tool_use blocks
                content: list[dict[str, Any]] = []
                # Preserve text content if any
                if msg.get("content"):
                    content.append({"type": "text", "text": msg["content"]})

                for tc in msg["tool_calls"]:
                    input_data: dict[str, Any] = {}
                    try:
                        args_str = tc.get("function", {}).get("arguments", "{}")
                        input_data = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except json.JSONDecodeError:
                        pass

                    content.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", ""),
                        "input": input_data,
                    })
                converted.append({"role": "assistant", "content": content})
                i += 1

            else:
                # Regular text message
                content = msg.get("content", "") or ""
                converted.append({"role": msg.get("role", "user"), "content": content})
                i += 1

        # Filter empty messages (Anthropic requires first message to be user)
        filtered = [
            m for m in converted
            if isinstance(m.get("content"), str)
            and m["content"] != ""
            or isinstance(m.get("content"), list)
            and len(m["content"]) > 0
        ]

        return {"system": system, "messages": filtered}

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """Convert OpenAI tool definitions to Anthropic format."""
        return [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in tools
        ]

    def _extract_text(self, content: list[dict[str, Any]]) -> str:
        """Extract text from Anthropic response content blocks."""
        return "".join(
            block.get("text", "")
            for block in content
            if block.get("type") == "text"
        )

    def _extract_tool_calls(self, content: list[dict[str, Any]]) -> list[ToolCall] | None:
        """Extract tool_use blocks and convert to OpenAI tool_calls format."""
        uses = [block for block in content if block.get("type") == "tool_use"]
        if not uses:
            return None

        return [
            ToolCall(
                id=u.get("id", ""),
                type="function",
                function={
                    "name": u.get("name", ""),
                    "arguments": json.dumps(u.get("input", {})),
                },
            )
            for u in uses
        ]

    async def chat(
        self, messages: list[ChatMessage], options: ChatOptions | None = None
    ) -> str:
        """
        Simple non-streaming chat completion.

        Args:
            messages: List of chat messages
            options: Optional parameters

        Returns:
            The assistant's response text
        """
        converted = self._convert_messages(messages)  # type: ignore

        body: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": (options.max_tokens if options else None) or 8192,
            "messages": converted["messages"],
        }
        if converted["system"]:
            body["system"] = converted["system"]
        if self._needs_thinking():
            body["thinking"] = {"type": "enabled", "budgetTokens": 8000}

        response = await self._client.post(
            f"{self._config.base_url}/messages",
            headers=self._build_headers(),
            json=body,
        )

        if not response.is_success:
            error_text = response.text
            raise RuntimeError(f"API 调用失败: {response.status_code} - {error_text}")

        data = response.json()
        return self._extract_text(data.get("content", []))

    async def chat_stream(
        self, messages: list[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Streaming chat completion (Anthropic SSE format).

        Args:
            messages: List of chat messages
            options: Optional parameters

        Yields:
            Chunks of the assistant's response
        """
        converted = self._convert_messages(messages)  # type: ignore

        body: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": (options.max_tokens if options else None) or 8192,
            "stream": True,
            "messages": converted["messages"],
        }
        if converted["system"]:
            body["system"] = converted["system"]
        if self._needs_thinking():
            body["thinking"] = {"type": "enabled", "budgetTokens": 8000}

        async with self._client.stream(
            "POST",
            f"{self._config.base_url}/messages",
            headers=self._build_headers(),
            json=body,
        ) as response:
            if not response.is_success:
                await response.aread()
                raise RuntimeError(f"API 调用失败: {response.status_code}")

            buffer = ""
            async for line in response.aiter_lines():
                buffer += line
                if buffer.endswith("\n"):
                    lines = buffer.split("\n")
                    buffer = lines.pop()

                    for ln in lines:
                        ln = ln.strip()
                        if not ln.startswith("data: "):
                            continue
                        json_str = ln[6:]
                        if json_str == "[DONE]":
                            continue
                        try:
                            event = json.loads(json_str)
                            # Only yield text_delta, not thinking_delta
                            if (
                                event.get("type") == "content_block_delta"
                                and event.get("delta", {}).get("type") == "text_delta"
                            ):
                                text = event["delta"].get("text", "")
                                if text:
                                    yield text
                        except json.JSONDecodeError:
                            continue

    async def agent_call(self, req: AgentCallRequest) -> AgentCallResponse:
        """
        Agent-style call with tool support and cancellation.

        Converts between OpenAI and Anthropic formats internally.

        Args:
            req: The agent call request

        Returns:
            The agent call response (in OpenAI format)
        """
        # Check for cancellation
        if req.cancel_event and req.cancel_event.is_set():
            raise asyncio.CancelledError("Request cancelled")

        converted = self._convert_messages(req.messages)

        body: dict[str, Any] = {
            "model": self._config.model,
            "max_tokens": 32768,
            "messages": converted["messages"],
        }
        if converted["system"]:
            body["system"] = converted["system"]
        if req.tools:
            body["tools"] = self._convert_tools(req.tools)
        if self._needs_thinking():
            body["thinking"] = {"type": "enabled", "budgetTokens": 16000}

        # Refactor: [HIGH-RISK] HTTP阻塞期间无法响应ESC中断，改用双等待模式 + 重试策略
        headers = self._build_headers()
        url = f"{self._config.base_url}/messages"
        response = await request_with_retry(
            lambda: self._client.post(url, headers=headers, json=body),
            req.cancel_event,
            max_retries=self._config.max_retries,
            retry_status_codes=self._config.retry_status_codes,
        )

        if not response.is_success:
            error_text = response.text
            raise RuntimeError(f"API 调用失败: {response.status_code} - {error_text}")

        data = response.json()
        content_blocks: list[dict[str, Any]] = data.get("content", [])

        # Extract text
        text_content = self._extract_text(content_blocks)

        # Extract tool_calls
        tool_calls_raw = self._extract_tool_calls(content_blocks)

        # Build OpenAI-format assistant message
        message: dict[str, Any] = {
            "role": "assistant",
            "content": text_content or None,
        }
        if tool_calls_raw:
            message["tool_calls"] = tool_calls_raw

        # Extract usage (Anthropic uses input_tokens/output_tokens)
        usage_data = data.get("usage")
        usage: TokenUsage | None = None
        if usage_data:
            inp = usage_data.get("input_tokens", 0)
            out = usage_data.get("output_tokens", 0)
            usage = TokenUsage(prompt=inp, completion=out, total=inp + out)

        return AgentCallResponse(
            message=message,
            tool_calls=tool_calls_raw,
            usage=usage,
        )

    async def ask(self, question: str, system_prompt: str | None = None) -> str:
        """
        Convenience method for single-turn Q&A.

        Args:
            question: The user's question
            system_prompt: Optional system prompt

        Returns:
            The assistant's response
        """
        messages: list[ChatMessage] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": question})
        return await self.chat(messages)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
