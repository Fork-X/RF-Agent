"""
OpenAI-compatible LLM client.

This module provides:
- LLMClient: Universal client for OpenAI-compatible APIs
- create_llm_client: Factory function that routes by protocol
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from quangan.config.llm_config import LLMConfig
from quangan.llm.types import (
    AgentCallRequest,
    AgentCallResponse,
    ChatMessage,
    ChatOptions,
    ILLMClient,
    TokenUsage,
)
from quangan.tools.types import ToolCall


class LLMClient(ILLMClient):
    """
    Universal LLM client for OpenAI-compatible APIs.

    Supports any provider that implements the OpenAI chat completions protocol:
    - DashScope (阿里云百炼)
    - Kimi (Moonshot)
    - OpenAI
    - Custom endpoints
    """

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
        self._client = httpx.AsyncClient(timeout=120.0)

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

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for API requests."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._config.api_key}",
        }
        if self._config.headers:
            headers.update(self._config.headers)
        return headers

    async def chat(self, messages: list[ChatMessage], options: ChatOptions | None = None) -> str:
        """
        Simple non-streaming chat completion.

        Args:
            messages: List of chat messages
            options: Optional parameters

        Returns:
            The assistant's response text
        """
        url = f"{self._config.base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
        }
        if options:
            if options.temperature is not None:
                body["temperature"] = options.temperature
            if options.max_tokens:
                body["max_tokens"] = options.max_tokens
            if options.top_p:
                body["top_p"] = options.top_p

        response = await self._client.post(
            url,
            headers=self._build_headers(),
            json=body,
        )

        if not response.is_success:
            error_text = response.text
            raise RuntimeError(f"API 调用失败: {response.status_code} - {error_text}")

        data = response.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "")

    async def chat_stream(
        self, messages: list[ChatMessage], options: ChatOptions | None = None
    ) -> AsyncGenerator[str, None]:
        """
        Streaming chat completion.

        Args:
            messages: List of chat messages
            options: Optional parameters

        Yields:
            Chunks of the assistant's response
        """
        url = f"{self._config.base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "stream": True,
        }
        if options:
            if options.temperature is not None:
                body["temperature"] = options.temperature
            if options.max_tokens:
                body["max_tokens"] = options.max_tokens
            if options.top_p:
                body["top_p"] = options.top_p

        async with self._client.stream(
            "POST",
            url,
            headers=self._build_headers(),
            json=body,
        ) as response:
            if not response.is_success:
                error_text = await response.aread()
                raise RuntimeError(f"API 调用失败: {response.status_code} - {error_text}")

            buffer = ""
            async for line in response.aiter_lines():
                buffer += line
                if buffer.endswith("\n"):
                    lines = buffer.split("\n")
                    buffer = lines.pop()

                    for ln in lines:
                        ln = ln.strip()
                        if not ln or ln == "data: [DONE]":
                            continue
                        if ln.startswith("data: "):
                            try:
                                chunk = json.loads(ln[6:])
                                content = (
                                    chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                                )
                                if content:
                                    yield content
                            except json.JSONDecodeError:
                                continue

            # Process remaining buffer
            if buffer.strip():
                ln = buffer.strip()
                if ln.startswith("data: ") and ln != "data: [DONE]":
                    try:
                        chunk = json.loads(ln[6:])
                        content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        pass

    async def agent_call(self, req: AgentCallRequest) -> AgentCallResponse:
        """
        Agent-style call with tool support and cancellation.

        Args:
            req: The agent call request

        Returns:
            The agent call response
        """
        # Check for cancellation
        if req.cancel_event and req.cancel_event.is_set():
            raise asyncio.CancelledError("Request cancelled")

        url = f"{self._config.base_url}/chat/completions"
        body: dict[str, Any] = {
            "model": self._config.model,
            "messages": req.messages,
        }
        if req.tools and len(req.tools) > 0:
            body["tools"] = req.tools

        response = await self._client.post(
            url,
            headers=self._build_headers(),
            json=body,
        )

        # Check for cancellation after request
        if req.cancel_event and req.cancel_event.is_set():
            raise asyncio.CancelledError("Request cancelled")

        if not response.is_success:
            raise RuntimeError(f"API 调用失败: {response.status_code}")

        data = response.json()
        message = data.get("choices", [{}])[0].get("message", {})

        # Extract tool calls
        tool_calls_raw = message.get("tool_calls", [])
        tool_calls: list[ToolCall] | None = None
        if tool_calls_raw:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    type="function",
                    function={
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                )
                for tc in tool_calls_raw
            ]

        # Extract usage
        usage_data = data.get("usage")
        usage: TokenUsage | None = None
        if usage_data:
            usage = TokenUsage(
                prompt=usage_data.get("prompt_tokens", 0),
                completion=usage_data.get("completion_tokens", 0),
                total=usage_data.get("total_tokens", 0),
            )

        return AgentCallResponse(
            message=message,
            tool_calls=tool_calls,
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


# Backward compatibility alias
DashScopeClient = LLMClient


def create_llm_client(config: LLMConfig) -> ILLMClient:
    """
    Factory function to create an LLM client based on configuration.

    Routes to the appropriate client implementation based on the
    protocol field in the configuration.

    返回的 client 会被 LoggingClient 自动包装，从而统一获得：
    - DEBUG 级别请求/响应日志
    - ERROR 级别失败日志
    - 不引入自动重试，保持原始调用行为不变

    Args:
        config: LLM configuration

    Returns:
        An ILLMClient implementation
    """
    if config.protocol == "anthropic":
        # Lazy import to avoid circular dependency
        from quangan.llm.anthropic_client import AnthropicClient

        inner: ILLMClient = AnthropicClient(config)
    else:
        inner = LLMClient(config)

    # 统一包装可观测性日志，保持原始 client 零侵入
    from quangan.llm.wrapper import LoggingClient

    return LoggingClient(inner)
