"""
Coding Agent factory.

Creates a stateless Coding Agent instance for code-related tasks.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from quangan.agent.agent import Agent, AgentConfig
from quangan.llm.types import ILLMClient
from quangan.tools.types import ToolDefinition


def create_coding_agent(
    client: ILLMClient,
    work_dir: str,
    callbacks: dict[str, Callable] | None = None,
) -> Agent:
    """
    Create a Coding Agent for code-related tasks.

    The agent is stateless - create a new instance for each task.

    Args:
        client: LLM client instance
        work_dir: Working directory for file operations and command execution
        callbacks: Optional callbacks:
            - on_tool_call: Called when a tool is invoked
            - on_tool_result: Called when a tool returns
            - confirm: Async callback for y/N confirmation (for execute_command safety)

    Returns:
        Configured Agent instance with coding tools registered
    """
    system_prompt = f"""你是一个专业的 Coding Agent，负责代码相关任务。

## 工作方式
你可以直接使用工具完成以下操作：
- 读取、创建、编辑文件
- 列出目录内容
- 执行 shell 命令
- 搜索代码
- 验证代码

## 注意事项
1. 修改代码后，使用 verify_code 检查是否有语法或类型错误
2. 使用 execute_command 时，危险操作（rm/mv/cp）如果涉及项目外路径，会要求用户确认
3. 文件路径优先使用绝对路径

当前工作目录: {work_dir}
"""

    config = AgentConfig(
        client=client,
        system_prompt=system_prompt,
        max_iterations=30,
        on_tool_call=callbacks.get("on_tool_call") if callbacks else None,
        on_tool_result=callbacks.get("on_tool_result") if callbacks else None,
    )

    agent = Agent(config)

    # Register coding tools from new tools package
    from quangan.tools import create_filesystem_tools, create_code_tools, create_command_tools

    confirm_fn = callbacks.get("confirm") if callbacks else None

    # Combine all tools needed for coding
    tools = [
        *create_filesystem_tools(),
        *create_code_tools(),
        *create_command_tools(work_dir, confirm_fn),
    ]

    for definition, implementation, readonly in tools:
        agent.register_tool(definition, implementation, readonly)

    return agent
