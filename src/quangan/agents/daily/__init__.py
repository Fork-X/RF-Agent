"""
Daily Agent factory.

Creates a stateless Daily Agent instance for daily tasks.
"""

from __future__ import annotations

from collections.abc import Callable

from quangan.agent.agent import Agent, AgentConfig
from quangan.llm.types import ILLMClient
from quangan.skills import SkillLoader


def create_daily_agent(
    client: ILLMClient,
    callbacks: dict[str, Callable] | None = None,
    skill_loader: SkillLoader | None = None,
    skill_tags: list[str] | None = None,
) -> Agent:
    """
    Create a Daily Agent for daily tasks.

    The agent is stateless - create a new instance for each task.

    Args:
        client: LLM client instance
        callbacks: Optional callbacks:
            - on_tool_call: Called when a tool is invoked
            - on_tool_result: Called when a tool returns
        skill_loader: Optional skill loader for loading skills by tags
        skill_tags: Optional list of skill tags to enable for this agent

    Returns:
        Configured Agent instance with daily tools registered
    """
    system_prompt = """你是一个日常事务助手，负责帮助用户处理各种日常任务。

## 工作方式
直接使用工具或技能完成任务，不要让用户手动执行命令或脚本。

## 可用工具
1. open_app - 打开 macOS 应用程序
2. open_url - 打开网址或进行 Google 搜索
3. run_shell - 执行 shell 命令
4. run_applescript - 执行 AppleScript（用于 macOS 自动化）
5. browser_action - 浏览器自动化（Playwright）

## 🎵 音乐需求：优先使用网易云 ncm-cli

用户有任何音乐相关需求（播放/搜索/控制播放/歌单推荐等），**第一选择是激活 netease-music-assistant 的skill，并按指引进行操作**。

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
        skill_loader=skill_loader,
        skill_tags=skill_tags or [],
        enable_skill_triggers=True,
        enable_skill_tool=True,
    )

    agent = Agent(config)

    # Register daily tools from new tools package
    from quangan.tools import create_browser_tools, create_shell_tools
    from quangan.tools.system import open_app, open_url

    # Combine all tools needed for daily tasks
    # Note: 不注册 run_applescript，音乐相关任务必须通过 skill 系统处理
    tools = [
        (open_app.definition, open_app.implementation, False),
        (open_url.definition, open_url.implementation, False),
        *create_browser_tools(),
        *create_shell_tools(),
    ]

    for definition, implementation, readonly in tools:
        agent.register_tool(definition, implementation, readonly)

    return agent
