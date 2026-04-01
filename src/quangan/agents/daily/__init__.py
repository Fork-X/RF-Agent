"""
Daily Agent factory.

Creates a stateless Daily Agent instance for daily tasks.
"""

from __future__ import annotations

from typing import Callable

from quangan.agent.agent import Agent, AgentConfig
from quangan.llm.types import ILLMClient


def create_daily_agent(
    client: ILLMClient,
    callbacks: dict[str, Callable] | None = None,
) -> Agent:
    """
    Create a Daily Agent for daily tasks.

    The agent is stateless - create a new instance for each task.

    Args:
        client: LLM client instance
        callbacks: Optional callbacks:
            - on_tool_call: Called when a tool is invoked
            - on_tool_result: Called when a tool returns

    Returns:
        Configured Agent instance with daily tools registered
    """
    system_prompt = """你是一个日常事务助手，负责帮助用户处理各种日常任务。

## 工作方式
直接使用工具完成任务，不要让用户手动执行命令或脚本。

## 可用工具
1. open_app - 打开 macOS 应用程序
2. open_url - 打开网址或进行 Google 搜索
3. run_shell - 执行 shell 命令
4. run_applescript - 执行 AppleScript（用于 macOS 自动化）
5. browser_action - 浏览器自动化（Playwright）

## 音乐相关
如果涉及音乐播放，优先使用 ncm-cli 命令：
- `ncm play <歌曲名/歌手名>` - 播放音乐
- `ncm pause` - 暂停
- `ncm next` / `ncm prev` - 下一首/上一首

## 浏览器使用
browser_action 支持以下操作：
- navigate: 导航到 URL
- click: 点击元素
- type: 输入文本
- press_key: 按键
- get_page_text: 获取页面文本
- get_elements: 查找元素
- wait_for: 等待元素
- close: 关闭浏览器
"""

    config = AgentConfig(
        client=client,
        system_prompt=system_prompt,
        max_iterations=20,
        on_tool_call=callbacks.get("on_tool_call") if callbacks else None,
        on_tool_result=callbacks.get("on_tool_result") if callbacks else None,
    )

    agent = Agent(config)

    # Register daily tools
    from .tools import create_all_daily_tools

    tools = create_all_daily_tools()

    for definition, implementation, readonly in tools:
        agent.register_tool(definition, implementation, readonly)

    return agent
