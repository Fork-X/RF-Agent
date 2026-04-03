"""
activate_skill tool implementation.

Activates a registered Skill by name, injecting its context into the current conversation.
This tool is designed for sub-agents to load execution-layer skills on demand.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from quangan.tools.types import ToolDefinition, make_tool_definition

if TYPE_CHECKING:
    from quangan.agent.agent import Agent

# Tool definition
definition: ToolDefinition = make_tool_definition(
    name="activate_skill",
    description="激活指定 Skill，将其完整指引注入当前上下文。用于需要特定 Skill 执行指引时调用。",
    parameters={
        "skill_name": {
            "type": "string",
            "description": "要激活的 Skill 名称",
        },
    },
    required=["skill_name"],
)


def create_implementation(agent: Agent) -> Callable[[dict[str, Any]], str]:
    """
    Factory function to create activate_skill implementation with agent context.

    Args:
        agent: Agent instance for skill activation

    Returns:
        Tool implementation function
    """

    def implementation(args: dict[str, Any]) -> str:
        skill_name = args["skill_name"]

        if agent.activate_skill(skill_name):
            return f"✅ 已激活 Skill: {skill_name}，其指引已注入上下文，请遵循执行。"

        available = ", ".join(agent._skills.keys())
        return f"❌ 未找到 Skill: {skill_name}。可用: {available}"

    return implementation
