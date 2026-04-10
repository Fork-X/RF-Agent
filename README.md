# 项目定位

基于 Harness Agent 架构的个人智能助理系统。

从零搭建的多 Agent CLI 助手，具备代码操作、日常任务处理、记忆管理能力。不依赖框架，每一层逻辑透明可控；ReAct 循环驱动，Tool 赋能，Skill 注入策略。

---

## 核心特性

- **多 Agent 协作**：主 Agent 路由 + Coding/Daily 子 Agent 执行
- **Skill 策略注入**：Markdown 声明式策略，不改代码扩展行为
- **双层记忆系统**：Core Memory（长期）+ Life Memory（短期），强化计数机制
- **上下文智能压缩**：基于 token 阈值的滚动摘要压缩
- **会话持久化**：自动存档/恢复，跨会话连续对话
- **安全防护**：命令黑名单 + 路径遍历检测 + 用户确认
- **多 LLM 支持**：统一接口适配 DashScope/Kimi/OpenAI

---

## 系统架构

```
用户 CLI
  │
  ▼
主 Agent（路由决策）── Memory 系统 ── Skill（router 层）
  │
  ├─ Coding Agent ── 代码工具集 ── Skill（coding 层）
  ├─ Daily Agent ── 日常工具集 ── Skill（daily 层）
  └─ 直接回复（闲聊/问答）
```

---

## 核心模块

| 模块 | 职责 |
|------|------|
| Agent 引擎 | ReAct 循环驱动 LLM 自主决策和工具调用 |
| Tool 系统 | 三元组模式（定义/实现/权限），工厂函数按需组装 |
| Skill 系统 | YAML+Markdown 声明式策略，触发词匹配自动注入 |
| Memory 系统 | 双层记忆（Core JSON + Life Markdown），自动整合 |
| Context 管理 | Token 阈值触发压缩，摘要节点保持对话连贯 |
| 会话持久化 | Session JSON 自动存档/恢复，归档历史可追溯 |

---

## 已实现功能

### 代码能力（Coding Agent）
- 文件读写与编辑（read_file, write_file, edit_file）
- 代码搜索与验证（search_code, verify_code）
- 安全命令执行（execute_command，三层防护）

### 日常能力（Daily Agent）
- 网易云音乐控制（通过 ncm-cli：搜索/播放/队列管理/播控）
- 全网实时搜索（通过 Tavily API）
- 应用启动与网址打开
- 浏览器自动化（Playwright）

---

## 快速开始

### 环境要求
- Python >= 3.12
- uv（推荐）或 pip
- Node.js（可选，ncm-cli 音乐功能需要）

### 安装
```bash
git clone <repo-url>
cd RF-Agent
uv sync
# 可选：浏览器自动化
uv run playwright install chromium
```

### 配置
```bash
cp .env.example .env
```

需要配置的关键环境变量（至少配一个 LLM provider）：
- `LLM_PROVIDER` — 选择 LLM 提供商（dashscope/kimi/kimi-code/openai）
- `DASHSCOPE_API_KEY` — 阿里云 DashScope（Qwen 系列）
- `KIMI_API_KEY` — Moonshot Kimi
- `OPENAI_API_KEY` — OpenAI
- `TAVILY_API_KEY` — 网络搜索功能（可选）

### 启动
```bash
uv run quangan
```

---

## CLI 命令参考

| 命令 | 功能 |
|------|------|
| `/help` | 显示帮助 |
| `/clear` | 归档当前会话，开新对话 |
| `/history` | 查看对话历史 |
| `/tools` | 列出可用工具 |
| `/skills` | 列出已加载技能 |
| `/plan` | 进入规划模式（只读） |
| `/exec` | 退出规划模式 |
| `/provider` | 切换 LLM 提供商 |
| `/exit` | 退出 |

快捷键：`ESC` 中断当前执行

---

## 扩展指南

### 添加新 Tool

三步流程：
1. 在 `src/quangan/tools/<category>/` 创建模块，用 `make_tool_definition()` 定义工具
2. 在对应 `__init__.py` 的工厂函数中返回 `(definition, implementation, readonly)` 三元组
3. 在目标 Agent 工厂中注册

最简示例：
```python
from quangan.tools.types import make_tool_definition

definition = make_tool_definition(
    name="my_tool",
    description="工具描述",
    parameters={"input": {"type": "string", "description": "输入参数"}},
    required=["input"]
)

async def implementation(args: dict) -> str:
    return f"处理结果: {args['input']}"
```

### 创建新 Skill

在 `src/quangan/skills/` 下创建目录，编写 `SKILL.md`。SkillLoader 自动扫描加载。

SKILL.md 模板：
```yaml
---
name: my-skill
description: 技能描述
tags: [daily]        # 决定哪个 Agent 加载
triggers: [关键词]   # 用户输入匹配触发
tools: [tool_name]   # 可用工具
---
# 技能指引
当用户需要 XX 时，按以下步骤操作：
1. 第一步
2. 第二步
```

### 自定义 Agent

参考 `src/quangan/agents/coding/` 或 `daily/` 工厂模式：
1. 创建 Agent 配置
2. 注册工具
3. 在主 Agent 中注册为 Tool

关键参数：`skill_tags`（Skill 过滤）、`max_iterations`（迭代上限）

---

## 项目结构

```
src/quangan/
├── agent/          # Agent 核心引擎（ReAct 循环）
├── agents/         # 子 Agent 工厂
│   ├── coding/     # 代码任务 Agent
│   └── daily/      # 日常任务 Agent
├── cli/            # CLI 交互界面
├── config/         # LLM 配置管理
├── llm/            # LLM 客户端（OpenAI/Anthropic 协议）
├── memory/         # 双层记忆系统
├── skills/         # Skill 策略文件
│   ├── git-helper/
│   ├── music-player/
│   ├── netease-music-cli/
│   ├── python-code-review/
│   ├── web-search/
│   └── ...
└── tools/          # 工具系统
    ├── browser/    # 浏览器自动化
    ├── code/       # 代码分析
    ├── command/    # 命令执行
    ├── filesystem/ # 文件操作
    ├── search/     # 网络搜索
    └── system/     # 系统操作
```

---

## License

MIT
