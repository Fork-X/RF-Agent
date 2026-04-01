# Skill 系统设计

## 概述

Skill 系统是 QuanGan 的扩展机制，允许通过 Markdown 文件定义可动态加载的"技能"。每个 Skill 包含特定的知识、指令和触发条件，当用户输入匹配触发条件时，Skill 的内容会自动注入到系统提示中，增强 Agent 在特定领域的能力。

---

## SkillLoader发现加载

### 三级搜索路径

```python
# src/quangan/skills/loader.py

DEFAULT_SKILL_PATHS = [
    # 项目级 skills（最高优先级）
    ".qoder/skills",
    "skills",
    # 用户级 skills
    "~/.config/quangan/skills",
]
```

### 搜索优先级

```
优先级: 高 ──────────────────────────────────────> 低

.qoder/skills/     →     skills/     →     ~/.config/quangan/skills/
   ├── python/              ├── git/             ├── custom/
   │   └── SKILL.md         │   └── SKILL.md     │   └── SKILL.md
   └── web-dev/             └── docker/
       └── SKILL.md             └── SKILL.md

同名 Skill：先加载的优先，后加载的忽略
```

### 文件发现模式

```python
def _find_skill_files(self, directory: Path) -> Iterator[Path]:
    """查找所有 Skill 文件"""
    for pattern in ["**/SKILL.md", "**/skill.md", "**/*.skill.md"]:
        yield from directory.glob(pattern)
```

支持的文件名：
- `SKILL.md`（推荐，大写）
- `skill.md`（小写兼容）
- `*.skill.md`（多 Skill 目录）

### 缓存机制

```python
def load_all(self, force_reload: bool = False) -> dict[str, Skill]:
    """
    加载所有 Skills。
    默认使用缓存，force_reload=True 时强制重新加载。
    """
    if self._skills and not force_reload:
        return dict(self._skills)  # 返回缓存
    
    self._skills = {}
    # ... 重新加载 ...
```

### 错误容错

```python
def _load_from_directory(self, directory: Path) -> None:
    for skill_file in self._find_skill_files(directory):
        try:
            skill = SkillParser.parse_file(skill_file)
            if skill.name in self._skills:
                continue  # 重复名称，跳过
            self._skills[skill.name] = skill
        except (SkillParseError, FileNotFoundError) as e:
            # 记录错误但继续加载其他 Skills
            self._load_errors.append((str(skill_file), str(e)))
```

---

## SkillParser解析

### YAML Frontmatter + Markdown 格式

```markdown
---
name: python-best-practices
description: Python 代码最佳实践指南
version: 1.0.0
author: ruifeng
tags:
  - python
  - coding
  - style
triggers:
  - python
  - py
  - 代码风格
---

# Python 最佳实践

## 命名规范

- 类名使用 PascalCase
- 函数和变量使用 snake_case
- 常量使用 UPPER_SNAKE_CASE

## 代码组织

1. 导入顺序：标准库 → 第三方 → 本地
2. 使用绝对导入优先于相对导入
3. 每个模块顶部添加 __all__
```

### 正则匹配 Frontmatter

```python
# src/quangan/skills/parser.py

FRONTMATTER_PATTERN = re.compile(
    r'^---\s*\n(.*?)\n---\s*\n(.*)$',
    re.DOTALL | re.MULTILINE
)
```

匹配示例：
```
---\s*\n      ← 开头 ---
(.*?)         ← 捕获 YAML 内容（非贪婪）
\n---\s*\n     ← 结束 ---
(.*)$         ← 捕获 Markdown 正文
```

### 手写YAML解析

为了**无外部依赖**，SkillParser 实现了简单的 YAML 解析器：

```python
@classmethod
def _parse_yaml(cls, yaml_str: str) -> dict[str, Any]:
    """
    简单 YAML 解析器，支持：
    - key: value（字符串、数字、布尔值）
    - key:
      - item1
      - item2（列表）
    """
    result: dict[str, Any] = {}
    lines = yaml_str.split('\n')
    current_key: str | None = None
    current_list: list[str] = []
    
    for line in lines:
        stripped = line.rstrip()
        
        if not stripped:
            continue
        
        # 列表项
        if stripped.startswith('- '):
            if current_key is not None:
                item = stripped[2:].strip()
                # 去除引号
                if (item.startswith('"') and item.endswith('"')) or \
                   (item.startswith("'") and item.endswith("'")):
                    item = item[1:-1]
                current_list.append(item)
            continue
        
        # 保存之前的列表
        if current_key is not None and current_list:
            result[current_key] = current_list
            current_list = []
        
        # 解析 key: value
        if ':' in stripped:
            colon_idx = stripped.index(':')
            key = stripped[:colon_idx].strip()
            value = stripped[colon_idx + 1:].strip()
            
            current_key = key
            
            if not value:
                current_list = []  # 可能是列表的开始
                continue
            
            result[key] = cls._parse_value(value)
    
    # 处理最后一个列表
    if current_key is not None and current_list:
        result[current_key] = current_list
    
    return result
```

### 必填字段验证

```python
# Parse YAML frontmatter manually
metadata = cls._parse_yaml(yaml_content)

# 验证必填字段
if 'name' not in metadata:
    raise SkillParseError("Missing required field 'name' in skill frontmatter")
if 'description' not in metadata:
    raise SkillParseError("Missing required field 'description' in skill frontmatter")
```

---

## Skill数据结构

### SkillMetadata

```python
@dataclass
class SkillMetadata:
    """Skill 元数据，从 YAML frontmatter 解析"""
    
    name: str                          # 唯一标识符
    description: str                   # 人类可读描述
    version: str = "1.0.0"             # 版本号
    author: str | None = None          # 作者
    tags: list[str] = field(default_factory=list)      # 分类标签
    triggers: list[str] = field(default_factory=list)  # 触发关键词
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "triggers": self.triggers,
        }
```

### Skill

```python
@dataclass
class Skill:
    """完整的 Skill 定义"""
    
    metadata: SkillMetadata    # 元数据
    content: str               # Markdown 正文（作为提示增强）
    file_path: str             # 源文件路径
    
    @property
    def name(self) -> str:
        return self.metadata.name
    
    @property
    def description(self) -> str:
        return self.metadata.description
    
    def should_trigger(self, message: str) -> bool:
        """检查消息是否触发此 Skill"""
        message_lower = message.lower()
        for trigger in self.metadata.triggers:
            if trigger.lower() in message_lower:
                return True
        return False
    
    def to_system_prompt(self) -> str:
        """生成系统提示增强内容"""
        lines = [
            f"## Skill: {self.metadata.name}",
            f"",
            f"{self.metadata.description}",
            f"",
            self.content,
        ]
        return "\n".join(lines)
```

---

## 触发机制

### should_trigger 子串匹配

```python
def should_trigger(self, message: str) -> bool:
    """
    检查消息是否应触发此 Skill。
    使用子串匹配（大小写不敏感）。
    """
    message_lower = message.lower()
    for trigger in self.metadata.triggers:
        if trigger.lower() in message_lower:
            return True
    return False
```

### 触发示例

| Skill | triggers | 用户输入 | 是否触发 |
|-------|----------|----------|----------|
| python | `["python", "py"]` | "帮我写个 python 脚本" | ✅ |
| python | `["python", "py"]` | "py 怎么读文件" | ✅ |
| git | `["git", "commit"]` | "git 怎么回退" | ✅ |
| git | `["git", "commit"]` | "如何提交代码" | ❌ |

### _check_skill_triggers 遍历

```python
def _check_skill_triggers(self, message: str) -> list[Skill]:
    """
    检查哪些 Skills 应该被触发。
    只返回未激活的 Skills。
    """
    if not self._enable_skill_triggers:
        return []
    
    triggered = []
    for skill in self._skills.values():
        if skill.should_trigger(message) and skill not in self._active_skills:
            triggered.append(skill)
    return triggered
```

### run() 前自动激活

```python
async def run(self, user_message: str, plan_only: bool = False) -> str:
    # 重置状态
    self._aborted = False
    self._cancel_event.clear()
    
    # 检查 Skill 触发
    if self._enable_skill_triggers:
        triggered_skills = self._check_skill_triggers(user_message)
        for skill in triggered_skills:
            self._active_skills.append(skill)
            self._inject_skill_prompt(skill)
            if self._verbose:
                print(f"✓ 自动激活 Skill: {skill.name}")
    
    # 添加用户消息
    self._messages.append({"role": "user", "content": user_message})
    
    # ... ReAct 循环 ...
```

---

## 提示注入方式

### to_system_prompt 格式化

```python
def to_system_prompt(self) -> str:
    """生成系统提示增强内容"""
    lines = [
        f"## Skill: {self.metadata.name}",
        f"",
        f"{self.metadata.description}",
        f"",
        self.content,
    ]
    return "\n".join(lines)
```

输出示例：
```markdown
## Skill: python-best-practices

Python 代码最佳实践指南

# Python 最佳实践

## 命名规范
- 类名使用 PascalCase
...
```

### _inject_skill_prompt 添加系统消息

```python
def _inject_skill_prompt(self, skill: Skill) -> None:
    """将 Skill 的系统提示注入消息历史"""
    skill_prompt = skill.to_system_prompt()
    self._messages.append({
        "role": "system",
        "content": f"[Skill 上下文 - {skill.name}]\n{skill_prompt}",
        "_skill": skill.name,  # 标记为 Skill 消息
    })
```

注入后的消息数组：
```
[0] {role: "system", content: "你是小枫..."}
[1] {role: "system", content: "[Skill 上下文 - python]...", _skill: "python"}
[2] {role: "user", content: "帮我写个 python 脚本"}
```

---

## Skill生命周期

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Skill 生命周期                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  初始化加载                                                                  │
│       │                                                                     │
│       ▼                                                                     │
│  ┌─────────────────────────────────────────┐                               │
│  │ Agent.__init__()                        │                               │
│  │ - 加载 config.skills                    │                               │
│  │ - 使用 skill_loader.load_all()          │                               │
│  │ - 缓存到 self._skills                   │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ 等待触发                                 │                               │
│  │ (Skill 在 self._skills 中，但未激活)     │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ run() 被调用                             │                               │
│  │ _check_skill_triggers(user_message)     │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│            ┌─────────┴─────────┐                                            │
│            ▼                   ▼                                            │
│        [匹配触发词]        [不匹配]                                          │
│            │                   │                                            │
│            ▼                   │                                            │
│  ┌───────────────────┐         │                                            │
│  │ 自动激活           │         │                                            │
│  │ - 加入 _active_    │         │                                            │
│  │   skills          │         │                                            │
│  │ - _inject_skill_ │         │                                            │
│  │   prompt()        │         │                                            │
│  └─────────┬─────────┘         │                                            │
│            │                   │                                            │
│            └─────────┬─────────┘                                            │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ ReAct 循环执行                          │                               │
│  │ Skill 内容在系统提示中生效              │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ 上下文压缩                              │                               │
│  │ - Skill 消息带 _skill 标记              │                               │
│  │ - 压缩时作为系统消息保留                │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ 会话结束 / 手动停用                     │                               │
│  │ - deactivate_skill(name)               │                               │
│  │ - 从 _active_skills 移除                │                               │
│  │ - 下次 run() 可重新触发                 │                               │
│  └─────────────────────────────────────────┘                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## CLI展示

### /skills 命令

```python
def handle_command(cmd: str, session: PromptSession) -> bool:
    if cmd == "/skills":
        skills = agent.list_skills()
        if skills:
            console.print("\n[bold cyan]已加载的 Skills:[/]")
            for skill in skills:
                active = "[green]●[/]" if skill in agent.get_active_skills() else "[dim]○[/]"
                console.print(f"  {active} [bold]{skill.name}[/] - {skill.description}")
                if skill.metadata.triggers:
                    triggers = ", ".join(skill.metadata.triggers[:5])
                    console.print(f"     [dim]触发词: {triggers}[/]")
        else:
            console.print("\n[yellow]暂无已加载的 Skills[/]")
        console.print()
        return True
```

### 展示示例

```
已加载的 Skills:
  ● python - Python 代码最佳实践指南
     触发词: python, py, 代码风格
  ○ git - Git 版本控制指南
     触发词: git, commit, branch
  ○ web-dev - Web 开发规范
     触发词: html, css, javascript
```

- `●` 表示已激活
- `○` 表示已加载但未激活

---

## 相关文件

| 文件 | 职责 |
|------|------|
| `src/quangan/skills/loader.py` | SkillLoader 类，发现和加载 Skills |
| `src/quangan/skills/parser.py` | SkillParser 类，解析 Markdown/YAML |
| `src/quangan/skills/models.py` | Skill 和 SkillMetadata 数据模型 |
| `src/quangan/agent/agent.py` | Agent 类，Skill 激活和提示注入 |
| `src/quangan/cli/main.py` | `/skills` 命令实现 |

---

## 交叉引用

- 系统总览：[系统架构总览](system-overview.md)
- ReAct 循环：[ReAct循环与任务管理](react-loop.md)
- Agent 实现：`src/quangan/agent/agent.py`
