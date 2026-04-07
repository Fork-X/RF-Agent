# 新增 Tool + Skill 实施指南

## 概述

项目中新增一个能力的标准路径：**Tool（原子能力）+ Skill（策略指引）+ Agent 注册**。

- **Tool**：封装具体的 API 调用或操作逻辑，是最小可复用单元
- **Skill**：通过 SKILL.md 为 LLM 提供策略指引，控制何时、如何使用 Tool
- **Agent 注册**：将 Tool 挂载到目标 Agent，使其在对话中可用

---

## 实施步骤

### Step 1: 创建 Tool 模块

1. 新建目录和文件：
   - `src/quangan/tools/<category>/__init__.py`
   - `src/quangan/tools/<category>/<tool_name>.py`

2. Tool 实现文件模板（`<tool_name>.py`）：
   ```python
   from quangan.tools.types import make_tool_definition

   definition = make_tool_definition(
       name="tool_name",
       description="工具描述",
       parameters={...}  # JSON Schema 格式
   )

   async def implementation(params: dict) -> str:
       # 实现逻辑，返回字符串结果
       ...
   ```

3. `__init__.py` 导出工厂函数：
   ```python
   def create_<category>_tools():
       return [(definition, implementation, readonly)]
   ```
   - `readonly=True`：只读操作（如搜索），可在 Plan 模式使用
   - `readonly=False`：有副作用的操作（如写文件）

### Step 2: 创建 Skill 文件

1. 新建 `src/quangan/skills/<skill-name>/SKILL.md`

2. YAML frontmatter 必需字段：
   ```yaml
   ---
   name: skill-name
   description: 技能描述
   version: "1.0"
   priority: 50
   tags:
     - daily          # 决定哪个 Agent 加载
   triggers:
     - 触发词1
     - 触发词2
   tools:
     - tool_name      # 关联的 Tool 名称
   ---
   ```

3. **tags 与 Agent 的对应关系**：
   - `router` → 主 Agent（路由层）
   - `daily` → Daily Agent（执行层）
   - `coding` → Coding Agent

4. **triggers 匹配规则**：
   - 中文触发词：子串匹配
   - 英文触发词：单词边界匹配

5. Markdown 正文：编写 LLM 的策略指引（何时使用、如何组织结果等）

### Step 3: 集成注册

1. **更新 Tool 导出**：`src/quangan/tools/__init__.py`
   - 添加 `from .category import create_<category>_tools`
   - 在 `__all__` 或汇总函数中注册

2. **更新目标 Agent 工厂**（如 `src/quangan/agents/daily/__init__.py`）：
   - 调用 `create_<category>_tools()` 注册工具
   - 在 `system_prompt` 中添加能力说明

3. **更新环境变量**：如有新增 API Key，更新 `.env` 和 `.env.example`

### Step 4: 验证

```bash
# 1. Lint 检查
uv run ruff check

# 2. 验证 SkillLoader 加载 & 触发词匹配
python -c "
from quangan.skills.loader import SkillLoader
loader = SkillLoader()
skills = loader.load_all()
for s in skills:
    print(f'{s.name} -> tags={s.tags}, triggers={s.triggers}')
matched = loader.match('测试触发词')
print(f'Matched: {[s.name for s in matched]}')
"

# 3. CLI 端到端验证
uv run quangan
```

---

## 注意事项

- **SkillLoader 扫描路径**为 `src/quangan/skills/`，不是项目根目录的 `.skills/`
- **Skill 激活是静默的**，不会在日志中显示，除非开启 verbose 模式
- **Agent Loop 机制**：Tool 返回结果后 LLM 会继续推理，可通过 Skill 指引让 LLM 对结果做格式化总结
- **无需修改 Agent 核心代码**（`agent.py`），只需在 Agent 工厂中注册即可
- Tool 的 `readonly` 标记影响 Plan 模式下的可用性，搜索类工具务必设为 `True`

---

## 实例参考

本指南基于 Tavily 搜索技能接入实践提炼，以下文件可作为具体参考：

| 文件 | 说明 |
|------|------|
| `src/quangan/tools/search/tavily_search.py` | Tool 实现示例 |
| `src/quangan/tools/search/__init__.py` | Tool 工厂导出示例 |
| `src/quangan/skills/web-search/SKILL.md` | Skill 定义示例 |
| `src/quangan/agents/daily/__init__.py` | Agent 注册示例 |
