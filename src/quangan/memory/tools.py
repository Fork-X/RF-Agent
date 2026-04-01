"""
Memory tool implementations.

Three tools for memory management:
- recall_memory: Search core memory and list recent life memories
- update_life_memory: Save session summary to life memory
- consolidate_core_memory: Analyze life memories and update core memory
"""

from __future__ import annotations

from typing import Any

from quangan.llm.types import ILLMClient
from quangan.memory.store import (
    CoreMemoryItem,
    append_life_memory,
    get_core_memory,
    get_recent_life_memories,
    save_core_memory,
)
from quangan.tools.types import ToolDefinition, make_tool_definition


# ─────────────────────────────────────────────────────────────────────────────
# Tool definitions
# ─────────────────────────────────────────────────────────────────────────────

recall_memory_def: ToolDefinition = make_tool_definition(
    name="recall_memory",
    description=(
        "检索小枫的记忆，包括核心长期记忆和最近的日常记忆摘要。"
        "当问题涉及具体项目、人物、过去的决定或用户偏好时主动调用；闲聊或简单问答无需调用。"
    ),
    parameters={
        "query": {
            "type": "string",
            "description": "要检索的关键词或问题描述",
        },
    },
    required=["query"],
)

update_life_memory_def: ToolDefinition = make_tool_definition(
    name="update_life_memory",
    description="将当前会话的核心内容保存到今日日常记忆文件中。",
    parameters={
        "summary": {
            "type": "string",
            "description": "本次会话的核心摘要（150字以内）",
        },
        "theme": {
            "type": "string",
            "description": "本次会话的主题词（3-8字，如'Agent开发'、'音乐播放调试'）",
        },
    },
    required=["summary", "theme"],
)

consolidate_core_memory_def: ToolDefinition = make_tool_definition(
    name="consolidate_core_memory",
    description=(
        "分析最近 14 天的日常记忆，识别重复出现的主题，自动更新核心长期记忆。"
        "当感知到某个主题反复出现时可主动调用。"
    ),
    parameters={},
)


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementation factory
# ─────────────────────────────────────────────────────────────────────────────


def create_memory_tool_impls(client: ILLMClient, cwd: str) -> dict[str, Any]:
    """
    Create memory tool implementations with LLM client and cwd context.

    Args:
        client: LLM client for consolidate operation
        cwd: Working directory for memory storage

    Returns:
        Dict of tool name -> implementation function
    """

    async def recall_impl(args: dict[str, Any]) -> str:
        """Recall memories by keyword search."""
        query = args["query"].lower()
        query_words = query.split()

        core = get_core_memory(cwd)

        # Keyword matching on core memory
        relevant = [
            m
            for m in core.memories
            if any(kw in m.content.lower() for kw in query_words)
        ]

        recent_life = get_recent_life_memories(cwd, 7)

        result = ""

        # Format core memory results
        if not core.memories:
            result += "## 核心记忆\n暂无核心记忆。\n\n"
        elif relevant:
            result += f"## 核心记忆（共 {len(core.memories)} 条，匹配 {len(relevant)} 条）\n"
            result += "\n".join(f"- [强度:{m.reinforce_count}] {m.content}" for m in relevant)
            result += "\n\n"
        else:
            result += f"## 核心记忆（无精确匹配，显示全部 {len(core.memories)} 条）\n"
            result += "\n".join(f"- {m.content}" for m in core.memories)
            result += "\n\n"

        # Format life memory results
        if recent_life:
            result += f"## 最近 7 天日常记忆（{len(recent_life)} 个文件）\n"
            result += "\n\n---\n\n".join(
                f"### {f.filename}\n{f.content[:400]}"
                for f in recent_life
            )
        else:
            result += "## 日常记忆\n暂无日常记忆记录。"

        return result

    async def update_life_impl(args: dict[str, Any]) -> str:
        """Update life memory with session summary."""
        summary = args["summary"]
        theme = args["theme"]

        filename = append_life_memory(cwd, theme, summary)
        return f"✅ 今日记忆已保存：{filename}"

    async def consolidate_impl() -> str:
        """Consolidate life memories into core memory."""
        recent_life = get_recent_life_memories(cwd, 14)

        if not recent_life:
            return "暂无日常记忆可供归纳。"

        current_core = get_core_memory(cwd)

        # Build prompt
        life_content = "\n\n".join(
            f"=== {f.filename} ===\n{f.content}" for f in recent_life
        )

        existing_core = (
            "\n".join(f"- [id:{m.id}] {m.content}" for m in current_core.memories)
            if current_core.memories
            else "（暂无）"
        )

        prompt = f"""## 最近 14 天的日常记忆：
{life_content}

## 现有核心记忆：
{existing_core}

## 任务：
分析日常记忆中重复出现的主题、事实、偏好，与现有核心记忆对比，输出更新后的核心记忆列表。
规则：
1. 现有核心记忆中有对应内容的，如有补充则更新描述，reinforceCount +1
2. 重复出现 2 次以上的新主题，添加为新核心记忆，reinforceCount 设为出现次数
3. 每条记忆用一句话概括，保持 id 不变（新增则生成简短英文 id）
4. 只输出 JSON，不要包裹 markdown 代码块，格式：
{{"memories":[{{"id":"xxx","content":"...","firstSeen":"YYYY-MM-DD","reinforceCount":N}}]}}"""

        try:
            import json
            import re

            result = await client.ask(prompt, "你是记忆整合助手，只输出纯 JSON，不加任何说明。")

            # Extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", result)
            if not json_match:
                return "❌ 无法解析 LLM 返回的记忆 JSON"

            parsed = json.loads(json_match.group())

            memories = [
                CoreMemoryItem(
                    id=m["id"],
                    content=m["content"],
                    first_seen=m["firstSeen"],
                    reinforce_count=m["reinforceCount"],
                )
                for m in parsed.get("memories", [])
            ]

            save_core_memory(cwd, CoreMemoryData(
                updated_at=datetime.now().strftime("%Y-%m-%d"),
                memories=memories,
            ))

            return f"✅ 核心记忆已更新，共 {len(memories)} 条"

        except Exception as e:
            return f"❌ 记忆整合失败: {e}"

    return {
        "recall_impl": recall_impl,
        "update_life_impl": update_life_impl,
        "consolidate_impl": consolidate_impl,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Imports
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime
