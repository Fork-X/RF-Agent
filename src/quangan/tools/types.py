"""
Tool type definitions for Function Calling.

This module defines the types used for tool/function definitions and calls
in the OpenAI Function Calling format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Required, TypedDict


# ─────────────────────────────────────────────────────────────────────────────
# TypedDict definitions for JSON-serializable tool structures
# ─────────────────────────────────────────────────────────────────────────────


class ToolParameter(TypedDict, total=False):
    """Parameter definition in a tool's input schema."""

    type: Required[str]
    """The type of the parameter (e.g., 'string', 'number', 'boolean', 'array', 'object')."""

    description: str
    """Human-readable description of the parameter."""

    enum: list[str]
    """List of allowed values, if the parameter is an enum."""

    items: ToolParameter
    """For array types, defines the schema of each item."""

    properties: dict[str, ToolParameter]
    """For object types, defines the schema of each property."""

    required: list[str]
    """For object types, list of required property names."""


class ToolFunctionDef(TypedDict):
    """Function definition within a ToolDefinition."""

    name: str
    """The name of the function to be called."""

    description: str
    """Description of what the function does."""

    parameters: dict[str, Any]
    """Parameters schema as a JSON Schema object."""


class ToolDefinition(TypedDict):
    """
    Complete tool definition in OpenAI Function Calling format.

    Example:
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get the current weather",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "City name"}
                    },
                    "required": ["location"]
                }
            }
        }
    """

    type: Literal["function"]
    """Must be 'function'."""

    function: ToolFunctionDef
    """The function definition."""


class ToolCallFunction(TypedDict):
    """Function details in a tool call."""

    name: str
    """Name of the function being called."""

    arguments: str
    """JSON string of function arguments."""


class ToolCall(TypedDict):
    """
    A tool call returned by the LLM.

    Example:
        {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": "{\"location\": \"Beijing\"}"
            }
        }
    """

    id: str
    """Unique identifier for this tool call."""

    type: Literal["function"]
    """Must be 'function'."""

    function: ToolCallFunction
    """Function details."""


class ToolResult(TypedDict):
    """
    Result of a tool execution, to be added to the message history.

    Example:
        {
            "tool_call_id": "call_abc123",
            "role": "tool",
            "name": "get_weather",
            "content": "Temperature: 25°C, Sunny"
        }
    """

    tool_call_id: str
    """ID of the tool call this result corresponds to."""

    role: Literal["tool"]
    """Must be 'tool'."""

    name: str
    """Name of the tool that was executed."""

    content: str
    """The result of the tool execution."""


# ─────────────────────────────────────────────────────────────────────────────
# Type aliases
# ─────────────────────────────────────────────────────────────────────────────

ToolFunction = Callable[[dict[str, Any]], Awaitable[str] | str]
"""
Type alias for tool implementation functions.

Tool implementations can be either sync or async functions that take
a dictionary of arguments and return a string result.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses for internal use
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ToolRegistryEntry:
    """
    Internal registry entry for a registered tool.

    Attributes:
        definition: The tool definition (OpenAI format)
        implementation: The function that implements the tool
        readonly: If True, this tool can be used in Plan mode (read-only operations)
    """

    definition: ToolDefinition
    implementation: ToolFunction
    readonly: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────


def make_tool_definition(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> ToolDefinition:
    """
    Helper function to create a ToolDefinition with less boilerplate.

    Args:
        name: Function name
        description: Function description
        parameters: Parameter definitions (properties of an object)
        required: List of required parameter names

    Returns:
        A complete ToolDefinition
    """
    params: dict[str, Any] = {"type": "object", "properties": {}}
    if parameters:
        params["properties"] = parameters
    if required:
        params["required"] = required

    return ToolDefinition(
        type="function",
        function={
            "name": name,
            "description": description,
            "parameters": params,
        },
    )
