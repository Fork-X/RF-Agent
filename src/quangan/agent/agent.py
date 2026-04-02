"""
Agent core implementation.

This module provides the base Agent class that implements:
- Tool registration with readonly flag for Plan mode
- Message history management with _archived/_summary metadata
- Context compression with rolling summary
- Interrupt control via asyncio.Event (AbortController equivalent)
- Function calling loop with tool execution
"""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from quangan.llm.types import (
    AgentCallRequest,
    ILLMClient,
    TokenUsage,
)
from quangan.skills import Skill, SkillLoader
from quangan.tools.types import ToolCall, ToolDefinition, ToolRegistryEntry, ToolResult

# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────


class AgentInterruptedError(Exception):
    """Raised when the agent is interrupted by user (ESC key)."""

    def __init__(self, message: str = "⚡ 已中断"):
        super().__init__(message)


class AgentMaxIterationsError(Exception):
    """Raised when the agent reaches maximum iterations."""

    def __init__(self, max_iterations: int):
        super().__init__(f"达到最大迭代次数 ({max_iterations})")


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AgentConfig:
    """
    Configuration for Agent initialization.

    Attributes:
        client: LLM client instance
        system_prompt: Optional system prompt
        max_iterations: Maximum tool calling iterations (default: 50)
        verbose: Enable verbose logging
        on_tool_call: Callback when a tool is called
        on_tool_result: Callback when a tool returns a result
        compression_threshold: Token threshold for context compression (default: 16000)
        on_compress: Callback after compression completes
        on_compress_start: Async callback before compression starts
        skills: List of skills to enable (optional)
        skill_loader: SkillLoader for dynamic skill discovery (optional)
        enable_skill_triggers: Whether to auto-activate skills based on triggers (default: True)
    """

    client: ILLMClient
    system_prompt: str | None = None
    max_iterations: int = 50
    verbose: bool = False
    on_tool_call: Callable[[str, dict[str, Any]], None] | None = None
    on_tool_result: Callable[[str, str], None] | None = None
    compression_threshold: int = 16_000
    on_compress: Callable[[int, int], None] | None = None
    on_compress_start: Callable[[], None] | Callable[[], Any] | None = None
    skills: list[Skill] = field(default_factory=list)
    skill_loader: SkillLoader | None = None
    enable_skill_triggers: bool = True


# ─────────────────────────────────────────────────────────────────────────────
# Agent Class
# ─────────────────────────────────────────────────────────────────────────────


class Agent:
    """
    Stateful agent orchestrator for agentic loops.

    Key features:
    - Single message array with _archived/_summary metadata
    - Tool registry with readonly flag for Plan mode
    - Context compression triggered by token threshold
    - Interrupt support via asyncio.Event

    Usage:
        agent = Agent(config)
        agent.register_tool(definition, implementation, readonly=False)
        response = await agent.run("Hello!")
    """

    def __init__(self, config: AgentConfig) -> None:
        """Initialize the agent with configuration."""
        self._client = config.client
        self._max_iterations = config.max_iterations
        self._verbose = config.verbose
        self._on_tool_call = config.on_tool_call
        self._on_tool_result = config.on_tool_result
        self._compression_threshold = config.compression_threshold
        self._on_compress = config.on_compress
        self._on_compress_start = config.on_compress_start

        # Tool registry: name -> ToolRegistryEntry
        self._tools: dict[str, ToolRegistryEntry] = {}

        # Message history: single array with metadata
        self._messages: list[dict[str, Any]] = []

        # Token usage tracking
        self._last_token_usage = TokenUsage()

        # Interrupt control
        self._aborted = False
        self._cancel_event = asyncio.Event()

        # Skill system
        self._skills: dict[str, Skill] = {}
        self._skill_loader = config.skill_loader
        self._enable_skill_triggers = config.enable_skill_triggers
        self._active_skills: list[Skill] = []

        # Load initial skills
        for skill in config.skills:
            self._skills[skill.name] = skill

        # Load skills from skill loader if provided
        if self._skill_loader:
            loaded_skills = self._skill_loader.load_all()
            for name, skill in loaded_skills.items():
                if name not in self._skills:
                    self._skills[name] = skill

        # Add system prompt if provided
        if config.system_prompt:
            self._messages.append({"role": "system", "content": config.system_prompt})

    # ─────────────────────────────────────────────────────────────────────────
    # Tool Registration
    # ─────────────────────────────────────────────────────────────────────────

    def register_tool(
        self,
        definition: ToolDefinition,
        implementation: Callable[[dict[str, Any]], Any],
        readonly: bool = False,
    ) -> None:
        """
        Register a tool with the agent.

        Args:
            definition: Tool definition in OpenAI format
            implementation: Function that implements the tool (sync or async)
            readonly: If True, tool can be used in Plan mode (read-only operations)
        """
        name = definition["function"]["name"]
        self._tools[name] = ToolRegistryEntry(
            definition=definition,
            implementation=implementation,
            readonly=readonly,
        )

        if self._verbose:
            print(f"✓ 已注册工具: {name}")

    def update_client(self, new_client: ILLMClient) -> None:
        """Replace the LLM client (used by /provider command)."""
        self._client = new_client

    # ─────────────────────────────────────────────────────────────────────────
    # Skill Management
    # ─────────────────────────────────────────────────────────────────────────

    def register_skill(self, skill: Skill) -> None:
        """
        Register a skill with the agent.

        Args:
            skill: Skill object to register
        """
        self._skills[skill.name] = skill
        if self._verbose:
            print(f"✓ 已注册 Skill: {skill.name}")

    def activate_skill(self, skill_name: str) -> bool:
        """
        Manually activate a skill by name.

        Args:
            skill_name: Name of the skill to activate

        Returns:
            True if skill was found and activated
        """
        skill = self._skills.get(skill_name)
        if not skill:
            return False

        if skill not in self._active_skills:
            self._active_skills.append(skill)
            self._inject_skill_prompt(skill)
            if self._verbose:
                print(f"✓ 已激活 Skill: {skill_name}")
        return True

    def deactivate_skill(self, skill_name: str) -> bool:
        """
        Deactivate an active skill.

        Args:
            skill_name: Name of the skill to deactivate

        Returns:
            True if skill was found and deactivated
        """
        for i, skill in enumerate(self._active_skills):
            if skill.name == skill_name:
                self._active_skills.pop(i)
                if self._verbose:
                    print(f"✓ 已停用 Skill: {skill_name}")
                return True
        return False

    def _inject_skill_prompt(self, skill: Skill) -> None:
        """
        Inject a skill's system prompt into the message history.

        Args:
            skill: Skill to inject
        """
        skill_prompt = skill.to_system_prompt()
        self._messages.append({
            "role": "system",
            "content": f"[Skill 上下文 - {skill.name}]\n{skill_prompt}",
            "_skill": skill.name,
        })

    def _check_skill_triggers(self, message: str) -> list[Skill]:
        """
        Check if any skills should be triggered by a message.

        Args:
            message: User input message

        Returns:
            List of triggered skills
        """
        if not self._enable_skill_triggers:
            return []

        triggered = []
        for skill in self._skills.values():
            if skill.should_trigger(message) and skill not in self._active_skills:
                triggered.append(skill)

        # 按 priority 降序，同优先级按触发匹配数排序
        triggered.sort(
            key=lambda s: (s.metadata.priority, s.get_trigger_score(message)),
            reverse=True
        )
        return triggered

    def list_skills(self) -> list[Skill]:
        """
        Get a list of all registered skills.

        Returns:
            List of Skill objects
        """
        return list(self._skills.values())

    def get_active_skills(self) -> list[Skill]:
        """
        Get a list of currently active skills.

        Returns:
            List of active Skill objects
        """
        return list(self._active_skills)

    # ─────────────────────────────────────────────────────────────────────────
    # Message Management
    # ─────────────────────────────────────────────────────────────────────────

    def _get_llm_messages(self) -> list[dict[str, Any]]:
        """
        Derive LLM context from messages array.

        Strategy (aggressive):
        - Find the latest _summary message
        - Include it + all messages after it
        - Strip _archived/_summary metadata before sending to LLM

        Returns:
            Clean message list for API call
        """
        # Get system messages (excluding _summary markers)
        system_msgs = [
            m for m in self._messages
            if m.get("role") == "system" and not m.get("_summary")
        ]

        # Find latest summary position
        last_summary_idx = -1
        for i in range(len(self._messages) - 1, -1, -1):
            if self._messages[i].get("_summary"):
                last_summary_idx = i
                break

        # Get context messages
        if last_summary_idx >= 0:
            # Use summary + all messages after it
            context_msgs = self._messages[last_summary_idx:]
        else:
            # No summary: filter out archived messages
            context_msgs = [
                m for m in self._messages
                if not m.get("_archived") and m.get("role") != "system"
            ]

        # Combine and strip metadata
        result = []
        for msg in system_msgs + context_msgs:
            clean_msg = {k: v for k, v in msg.items() if not k.startswith("_")}
            result.append(clean_msg)

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Context Compression
    # ─────────────────────────────────────────────────────────────────────────

    async def _compress_context(self) -> None:
        """
        Compress old messages using rolling summary.

        Strategy:
        - Keep last 6 active messages (~3 conversation rounds)
        - LLM generates summary of older messages
        - Mark old messages with _archived=True
        - Insert _summary=True marker node
        """
        KEEP_RECENT = 6

        # Count active non-system messages
        active = [
            m for m in self._messages
            if not m.get("_archived") and m.get("role") != "system"
        ]
        if len(active) <= KEEP_RECENT:
            return

        # 待压缩：从头到倒数第6条（不含倒数第6条）
        to_compress = active[:-KEEP_RECENT]
        # 保持活跃：从倒数第6条到末尾（含倒数第6条）
        to_keep = active[-KEEP_RECENT:]
        before_count = len(self._messages)

        # Notify external: compression starting (supports async)
        if self._on_compress_start:
            result = self._on_compress_start()
            if inspect.isawaitable(result):
                await result

        # Build summary prompt 构建摘要提示
        summary_parts = []
        for m in to_compress:
            role = m.get("role", "")
            if role == "user":
                role_label = "用户"
            elif role == "assistant":
                role_label = "Agent"
            else:
                role_label = "工具"

            content = m.get("content", "")
            if isinstance(content, str):
                # TODO: 粗暴地截取前500字，可实现更优雅的压缩策略
                text = content[:500]
            else:
                text = json.dumps(content)[:500]

            summary_parts.append(f"[{role_label}]: {text}")

        summary_prompt = "\n\n".join(summary_parts)

        # Call LLM for summary
        try:
            summary = await self._client.chat(
                [
                    {
                        "role": "system",
                        "content": "你是一个对话摘要助手，擅长从编程对话中提炼关键信息。",
                    },
                    {
                        "role": "user",
                        "content": (
                            "请将以下对话历史压缩成简洁摘要（200字以内），"
                            "重点保留：已读过的文件路径、做过的代码修改、重要结论。"
                            f"\n\n{summary_prompt}"
                        ),
                    },
                ]
            )
        except Exception:
            return

        if not summary:
            return

        # Build summary marker node
        summary_msg: dict[str, Any] = {
            "role": "system",
            "content": f"[历史对话摘要 - 已自动压缩]\n{summary}",
            "_summary": True,
        }

        # Rebuild messages array: archive old, insert summary 重建消息数组
        to_compress_set = set(id(m) for m in to_compress)
        first_keep_ref = to_keep[0] if to_keep else None

        new_messages: list[dict[str, Any]] = []
        summary_inserted = False

        for msg in self._messages:
            # Insert summary before first kept message 在第一条保留消息前插入摘要
            if not summary_inserted and first_keep_ref is not None and msg is first_keep_ref:
                new_messages.append(summary_msg)
                summary_inserted = True

            # Archive old messages
            if id(msg) in to_compress_set:
                new_messages.append({**msg, "_archived": True})
            else:
                new_messages.append(msg)

        self._messages = new_messages

        after_count = len([m for m in self._messages if not m.get("_archived")])

        if self._on_compress:
            self._on_compress(before_count, after_count)

        if self._verbose:
            print(f"\n♻️  上下文已压缩: {before_count} → {after_count} 条有效消息")

    # ─────────────────────────────────────────────────────────────────────────
    # Tool Execution
    # ─────────────────────────────────────────────────────────────────────────

    def _get_tool_definitions(self, plan_only: bool = False) -> list[ToolDefinition]:
        """
        Get tool definitions for API call.

        Args:
            plan_only: If True, only include readonly tools

        Returns:
            List of tool definitions
        """
        return [
            entry.definition
            for entry in self._tools.values()
            if not plan_only or entry.readonly
        ]

    async def _execute_tool_call(self, tool_call: ToolCall) -> ToolResult:
        """
        Execute a tool call.

        Args:
            tool_call: The tool call to execute

        Returns:
            Tool result to add to message history
        """
        tool_name = tool_call["function"]["name"]
        entry = self._tools.get(tool_name)

        if not entry:
            return ToolResult(
                tool_call_id=tool_call["id"],
                role="tool",
                name=tool_name,
                content=f"错误：未找到工具 {tool_name}",
            )

        try:
            args = json.loads(tool_call["function"]["arguments"])

            if self._verbose:
                print(f"\n🔧 调用工具: {tool_name}")
                print("📥 参数:", args)

            if self._on_tool_call:
                self._on_tool_call(tool_name, args)

            # Execute tool (support both sync and async)
            result = entry.implementation(args)
            if inspect.isawaitable(result):
                result = await result

            if self._verbose:
                print("📤 结果:", result[:200] if isinstance(result, str) else result)

            if self._on_tool_result:
                self._on_tool_result(tool_name, str(result))

            return ToolResult(
                tool_call_id=tool_call["id"],
                role="tool",
                name=tool_name,
                content=str(result),
            )

        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call["id"],
                role="tool",
                name=tool_name,
                content=f"工具执行失败: {e}",
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Interrupt Control
    # ─────────────────────────────────────────────────────────────────────────

    def abort(self) -> None:
        """
        Interrupt the running agent.

        Sets the abort flag and cancel event, which will:
        1. Stop the current HTTP request (via cancel_event)
        2. Raise AgentInterruptedError in the run loop
        """
        self._aborted = True
        self._cancel_event.set()

    # ─────────────────────────────────────────────────────────────────────────
    # Main Run Loop
    # ─────────────────────────────────────────────────────────────────────────

    async def run(self, user_message: str, plan_only: bool = False) -> str:
        """
        Run the agent with a user message.

        This is the main entry point for agent interaction. It:
        1. Adds the user message to history
        2. Calls the LLM with tools
        3. Executes any tool calls
        4. Loops until no more tool calls
        5. Returns the final response

        Args:
            user_message: The user's input
            plan_only: If True, only use readonly tools (Plan mode)

        Returns:
            The agent's final response

        Raises:
            AgentInterruptedError: If the agent was interrupted
            AgentMaxIterationsError: If max iterations reached
        """
        # Reset state for this run
        self._aborted = False
        self._cancel_event.clear()

        # Check for skill triggers before adding user message
        if self._enable_skill_triggers:
            triggered_skills = self._check_skill_triggers(user_message)
            for skill in triggered_skills:
                self._active_skills.append(skill)
                self._inject_skill_prompt(skill)
                if self._verbose:
                    print(f"✓ 自动激活 Skill: {skill.name}")

        # Add user message to history
        self._messages.append({"role": "user", "content": user_message})

        iteration = 0

        while iteration < self._max_iterations:
            # Check abort at loop start
            if self._aborted:
                self._aborted = False
                raise AgentInterruptedError()

            iteration += 1

            if self._verbose:
                print(f"\n━━━━ 迭代 {iteration} ━━━━")

            # Build request
            tools = self._get_tool_definitions(plan_only)
            self._cancel_event.clear()

            # Call LLM
            try:
                result = await self._client.agent_call(
                    AgentCallRequest(
                        messages=self._get_llm_messages(),
                        tools=tools if tools else None,
                        cancel_event=self._cancel_event,
                    )
                )
            except asyncio.CancelledError:
                if self._aborted:
                    self._aborted = False
                    raise AgentInterruptedError() from None
                raise
            except AgentInterruptedError:
                raise

            # Update token usage
            if result.usage:
                self._last_token_usage = result.usage

                # Check for compression trigger
                if self._last_token_usage.total >= self._compression_threshold:
                    await self._compress_context()

            # Add assistant message to history
            self._messages.append(result.message)

            # Check for tool calls
            if result.tool_calls and len(result.tool_calls) > 0:
                if self._verbose:
                    print(f"💡 模型请求调用 {len(result.tool_calls)} 个工具")

                # Execute all tool calls
                for tool_call in result.tool_calls:
                    tool_result = await self._execute_tool_call(tool_call)
                    self._messages.append(tool_result)  # type: ignore

                # Continue loop
                continue

            # No tool calls: return final response
            if self._verbose:
                print("\n✅ Agent 执行完成")

            content = result.message.get("content", "")
            return content if isinstance(content, str) else ""

        raise AgentMaxIterationsError(self._max_iterations)

    # ─────────────────────────────────────────────────────────────────────────
    # Public Accessors
    # ─────────────────────────────────────────────────────────────────────────

    def load_messages(self, messages: list[dict[str, Any]]) -> None:
        """Load message history (for session restoration)."""
        self._messages.extend(messages)

    def get_token_usage(self) -> TokenUsage:
        """Get the last token usage statistics."""
        return TokenUsage(
            prompt=self._last_token_usage.prompt,
            completion=self._last_token_usage.completion,
            total=self._last_token_usage.total,
        )

    def get_history(self) -> list[dict[str, Any]]:
        """Get complete message history (including archived)."""
        return list(self._messages)

    def clear_history(self) -> None:
        """Clear message history (preserve system prompt)."""
        system_messages = [
            m for m in self._messages
            if m.get("role") == "system" and not m.get("_summary")
        ]
        self._messages = system_messages
