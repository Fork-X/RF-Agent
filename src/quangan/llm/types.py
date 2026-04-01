"""
LLM type definitions.

This module defines the types used for LLM communication, including:
- Message types (ChatMessage with metadata)
- Request/Response types
- ILLMClient Protocol (unified interface)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Literal, Protocol, Required, TypedDict, runtime_checkable

from quangan.tools.types import ToolCall, ToolDefinition


# ─────────────────────────────────────────────────────────────────────────────
# Message types
# ─────────────────────────────────────────────────────────────────────────────

MessageRole = Literal["system", "user", "assistant", "tool"]
"""Valid roles for chat messages."""


class ChatMessage(TypedDict, total=False):
    """
    A chat message with optional metadata.

    The _archived and _summary fields are internal metadata used for
    context management:
    - _archived: Message is excluded from LLM context but kept for /history
    - _summary: Message is a compression summary marker

    These fields are stripped before sending to the LLM.
    """

    role: Required[MessageRole]
    """The role of the message author."""

    content: Required[str]
    """The content of the message."""

    _archived: bool
    """If True, this message is excluded from LLM context but retained for history."""

    _summary: bool
    """If True, this is a compression summary marker."""

    tool_calls: list[dict[str, Any]]
    """For assistant messages, list of tool calls requested."""

    tool_call_id: str
    """For tool messages, the ID of the tool call this responds to."""

    name: str
    """For tool messages, the name of the tool."""


# ─────────────────────────────────────────────────────────────────────────────
# Chat options
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ChatOptions:
    """Optional parameters for chat completions."""

    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Agent call types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AgentCallRequest:
    """
    Request for an agent-style LLM call with tool support.

    Attributes:
        messages: List of messages in OpenAI format
        tools: Optional list of tool definitions
        cancel_event: Optional asyncio.Event for cancellation
    """

    messages: list[dict[str, Any]]
    tools: list[ToolDefinition] | None = None
    cancel_event: asyncio.Event | None = None


@dataclass
class TokenUsage:
    """Token usage statistics from an LLM call."""

    prompt: int = 0
    completion: int = 0
    total: int = 0


@dataclass
class AgentCallResponse:
    """
    Response from an agent-style LLM call.

    Attributes:
        message: The assistant message to add to history (OpenAI format)
        tool_calls: Optional list of tool calls extracted from the response
        usage: Optional token usage statistics
    """

    message: dict[str, Any]
    tool_calls: list[ToolCall] | None = None
    usage: TokenUsage | None = None


# ─────────────────────────────────────────────────────────────────────────────
# ILLMClient Protocol
# ─────────────────────────────────────────────────────────────────────────────


@runtime_checkable
class ILLMClient(Protocol):
    """
    Protocol defining the unified LLM client interface.

    This protocol enables structural subtyping - any class that implements
    these methods is considered a valid ILLMClient, regardless of inheritance.

    Implementations:
    - LLMClient: OpenAI-compatible protocol (dashscope, kimi, openai)
    - AnthropicClient: Anthropic Messages API protocol (kimi-code)
    """

    @property
    def config(self) -> "LLMConfig":
        """The configuration for this client."""
        ...

    async def chat(
        self, messages: list[ChatMessage], options: ChatOptions | None = None
    ) -> str:
        """
        Simple chat completion (non-streaming).

        Args:
            messages: List of chat messages
            options: Optional parameters

        Returns:
            The assistant's response text
        """
        ...

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
        ...

    async def agent_call(self, req: AgentCallRequest) -> AgentCallResponse:
        """
        Agent-style call with tool support and cancellation.

        This is the main method used by the Agent class.

        Args:
            req: The agent call request

        Returns:
            The agent call response
        """
        ...

    async def ask(self, question: str, system_prompt: str | None = None) -> str:
        """
        Convenience method for single-turn Q&A.

        Args:
            question: The user's question
            system_prompt: Optional system prompt

        Returns:
            The assistant's response
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# LLM Config (forward declaration, actual definition in config/llm_config.py)
# ─────────────────────────────────────────────────────────────────────────────

# This will be properly typed when imported from config.llm_config
# We use a protocol here to avoid circular imports
class LLMConfig(Protocol):
    """Protocol for LLM configuration (actual implementation in config.llm_config)."""

    provider: str
    api_key: str
    base_url: str
    model: str
    headers: dict[str, str] | None
    protocol: Literal["openai", "anthropic"] | None
