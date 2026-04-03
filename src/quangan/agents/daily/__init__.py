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
直接使用工具或技能完成任务，不要让用户手动执行命令或脚本。

## 可用工具
1. open_app - 打开 macOS 应用程序
2. open_url - 打开网址或进行 Google 搜索
3. run_shell - 执行 shell 命令
4. run_applescript - 执行 AppleScript（用于 macOS 自动化）
5. browser_action - 浏览器自动化（Playwright）

## 🎵 音乐需求：优先使用网易云 ncm-cli

用户有任何音乐相关需求（播放/搜索/控制播放/歌单推荐等），**第一选择是通过 run_shell 调用 ncm-cli**。

### 执行前检查链（按顺序）
1. \`ncm-cli --version\` — 未安装则引导用户安装（npm install -g @music163/ncm-cli）
2. \`ncm-cli login --check\` — 未登录则执行 \`ncm-cli login --background\`
3. 直接按下方命令格式执行，**不要先跑 ncm-cli commands 探路**，格式已知见下

### 常用命令（直接使用，无需探索）

\`\`\`bash
# 搜索歌曲（必须用 --keyword，不能用位置参数）
ncm-cli search song --keyword "歌名" --userInput "搜索xxx"

# 播放单曲（需要搜索结果中的 id 和 originalId）
ncm-cli play --song --encrypted-id <32位hex> --original-id <数字>

# 播放歌单
ncm-cli play --playlist --encrypted-id <歌单id> --original-id <歌单id>

# 播放控制
ncm-cli pause
ncm-cli resume
ncm-cli next
ncm-cli prev

# 搜索歌单
ncm-cli search playlist --keyword "关键词" --userInput "搜索xxx"
\`\`\`

### 搜索 → 播放标准流程
1. \`ncm-cli search song --keyword "歌名" --userInput "播放xxx"\` — 获取 id 和 originalId
2. 取结果第一条（visible=true 的），用 \`ncm-cli play --song --encrypted-id <id> --original-id <originalId>\` 播放
3. **visible=false 的歌曲不可播放，跳过**

**只有在 ncm-cli 确实不可用时**，才考虑其他方式（URL Scheme、browser_action、AppleScript）。

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

    # Register daily tools from new tools package
    from quangan.tools import create_system_tools, create_browser_tools, create_shell_tools

    # Combine all tools needed for daily tasks
    tools = [
        *create_system_tools(),
        *create_browser_tools(),
        *create_shell_tools(),
    ]

    for definition, implementation, readonly in tools:
        agent.register_tool(definition, implementation, readonly)

    return agent
