# Skill 触发机制改进

## 问题描述

当前 Skill 触发机制存在多个问题：

1. **纯子字符串匹配**：`should_trigger` (`models.py:76-90`) 使用 `trigger.lower() in message_lower`，无词边界检查

2. **误触发**："git" 会匹配 "digital"、"legitimate" 等不相关词

3. **无优先级排序**：多个 Skill 同时触发时按 dict 遍历顺序激活，行为不可预测

4. **无自动停用**：Skill 激活后系统消息持续占用 token，直到会话结束

5. **无激活限制**：无每会话激活次数限制，可能重复激活

```python
# models.py:76-90 当前实现
def should_trigger(self, message: str) -> bool:
    message_lower = message.lower()
    for trigger in self.triggers:
        if trigger.lower() in message_lower:  # 无词边界！
            return True
    return False
```

**误触发示例**：

```
用户输入: "这是一个 digital 时代"
触发词: "git"
结果: 误触发 Git 相关 Skill（因为 "digit" 包含 "git"）
```

---

## 方案对比

| 方案 | 技术选型 | 适用场景 | 实现难度 | 新增依赖 | 模块耦合 |
|------|----------|----------|----------|----------|----------|
| **方案1：词边界匹配+优先级** | re 模块 | 所有场景（推荐） | 低（1-2小时） | 无 | 低 |
| 方案2：条件触发系统 | YAML 扩展 | 复杂触发规则 | 中（半天-1天） | 无 | 中 |
| 方案3：自动停用机制 | TTL 管理 | token 敏感场景 | 中（半天） | 无 | 中 |

---

### 方案 1：词边界匹配 + 优先级（推荐）

#### 设计思路

1. 将 `trigger in message` 改为正则词边界匹配
2. 为 `SkillMetadata` 添加 `priority` 字段
3. 多 Skill 触发时按 priority 降序排列

#### 核心实现

**词边界匹配：**

```python
# skills/models.py
import re
from dataclasses import dataclass, field

@dataclass
class SkillMetadata:
    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    priority: int = 0  # 新增：优先级，数值越大越优先
    
    def should_trigger(self, message: str) -> bool:
        """检查消息是否触发该 Skill（使用词边界匹配）"""
        for trigger in self.triggers:
            # 转义特殊字符，添加词边界
            pattern = rf'\b{re.escape(trigger)}\b'
            if re.search(pattern, message, re.IGNORECASE):
                return True
        return False
    
    def get_trigger_score(self, message: str) -> int:
        """计算触发得分（用于排序）"""
        score = 0
        for trigger in self.triggers:
            pattern = rf'\b{re.escape(trigger)}\b'
            matches = re.findall(pattern, message, re.IGNORECASE)
            score += len(matches)
        return score
```

**优先级排序：**

```python
# agent/agent.py
def _check_skill_triggers(self, message: str) -> list[SkillMetadata]:
    """检查并返回触发的 Skills（按优先级排序）"""
    triggered = []
    
    for skill in self._available_skills.values():
        if skill.should_trigger(message):
            triggered.append(skill)
    
    # 按优先级降序排序，相同优先级按触发得分排序
    triggered.sort(
        key=lambda s: (s.priority, s.get_trigger_score(message)),
        reverse=True
    )
    
    return triggered

async def _process_message(self, message: str) -> None:
    triggered_skills = self._check_skill_triggers(message)
    
    for skill in triggered_skills:
        if skill.name not in self._active_skills:
            self._activate_skill(skill)
            # 可选：只激活最高优先级的一个
            # break
```

**YAML 优先级配置：**

```yaml
---
name: git-helper
description: Git 操作辅助
triggers:
  - git
  - commit
  - branch
priority: 10  # 高优先级
---
# Skill 内容...
```

#### 词边界匹配示例

| 输入 | 触发词 | 旧逻辑 | 新逻辑 |
|------|--------|--------|--------|
| "use git to commit" | git | ✅ | ✅ |
| "digital transformation" | git | ✅ (误触发) | ❌ |
| "legitimate concern" | git | ✅ (误触发) | ❌ |
| "Git is useful" | git | ✅ | ✅ |

#### 优点
- 消除子字符串误触发
- 可预测的激活顺序
- 实现简单，无新依赖

#### 缺点
- 正则匹配略慢（可忽略）
- 不支持复杂条件

---

### 方案 2：条件触发系统

#### 设计思路

扩展触发配置，支持排除词和上下文条件。

#### YAML 配置扩展

```yaml
---
name: git-helper
description: Git 操作辅助
triggers:
  - keyword: git
    exclude:          # 排除词
      - digital
      - legitimate
      - digit
    require_context: coding  # 上下文条件（可选）
  - keyword: commit
    require_all:      # 必须同时出现
      - git
      - message
priority: 10
---
```

#### 数据模型

```python
# skills/models.py
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TriggerRule:
    keyword: str
    exclude: list[str] = field(default_factory=list)
    require_all: list[str] = field(default_factory=list)
    require_context: Optional[str] = None

@dataclass
class SkillMetadata:
    name: str
    description: str
    triggers: list[TriggerRule] = field(default_factory=list)
    priority: int = 0
    
    def should_trigger(
        self, 
        message: str, 
        context: str = None
    ) -> bool:
        for rule in self.triggers:
            if self._check_rule(rule, message, context):
                return True
        return False
    
    def _check_rule(
        self, 
        rule: TriggerRule, 
        message: str, 
        context: str
    ) -> bool:
        message_lower = message.lower()
        
        # 关键词检查（词边界）
        pattern = rf'\b{re.escape(rule.keyword)}\b'
        if not re.search(pattern, message, re.IGNORECASE):
            return False
        
        # 排除词检查
        for exclude in rule.exclude:
            if exclude.lower() in message_lower:
                return False
        
        # 必须全匹配检查
        for required in rule.require_all:
            req_pattern = rf'\b{re.escape(required)}\b'
            if not re.search(req_pattern, message, re.IGNORECASE):
                return False
        
        # 上下文检查
        if rule.require_context and context != rule.require_context:
            return False
        
        return True
```

#### Parser 扩展

```python
# skills/parser.py
def parse_trigger(trigger_data) -> TriggerRule:
    """解析触发配置"""
    if isinstance(trigger_data, str):
        # 简单字符串格式
        return TriggerRule(keyword=trigger_data)
    elif isinstance(trigger_data, dict):
        # 完整配置格式
        return TriggerRule(
            keyword=trigger_data["keyword"],
            exclude=trigger_data.get("exclude", []),
            require_all=trigger_data.get("require_all", []),
            require_context=trigger_data.get("require_context"),
        )
```

#### 优点
- 精细控制触发条件
- 支持排除词
- 向后兼容简单格式

#### 缺点
- 配置复杂度增加
- Parser 需要扩展

---

### 方案 3：自动停用机制

#### 设计思路

Skill 激活后设置 TTL（按消息数或时间），超过后自动停用，从 `_active_skills` 和 `_messages` 中移除对应系统消息。

#### 核心实现

```python
# skills/models.py
@dataclass
class SkillMetadata:
    name: str
    description: str
    triggers: list[str] = field(default_factory=list)
    priority: int = 0
    ttl_messages: int = 20  # 激活后保持 20 条消息
    ttl_seconds: int = None  # 或按时间（可选）

# agent/agent.py
from dataclasses import dataclass
from time import time

@dataclass
class ActiveSkillState:
    skill: SkillMetadata
    activated_at: float
    message_count: int = 0

class Agent:
    def __init__(self, ...):
        self._active_skills: dict[str, ActiveSkillState] = {}
    
    def _activate_skill(self, skill: SkillMetadata) -> None:
        if skill.name in self._active_skills:
            return
        
        self._active_skills[skill.name] = ActiveSkillState(
            skill=skill,
            activated_at=time()
        )
        
        # 注入系统消息
        self._messages.insert(1, {
            "role": "system",
            "content": skill.system_prompt,
            "_skill_name": skill.name  # 标记来源
        })
    
    def _check_skill_ttl(self) -> None:
        """检查并停用过期的 Skills"""
        now = time()
        to_deactivate = []
        
        for name, state in self._active_skills.items():
            skill = state.skill
            expired = False
            
            # 按消息数检查
            if skill.ttl_messages and state.message_count >= skill.ttl_messages:
                expired = True
            
            # 按时间检查
            if skill.ttl_seconds and (now - state.activated_at) >= skill.ttl_seconds:
                expired = True
            
            if expired:
                to_deactivate.append(name)
        
        for name in to_deactivate:
            self._deactivate_skill(name)
    
    def _deactivate_skill(self, skill_name: str) -> None:
        """停用 Skill 并移除系统消息"""
        if skill_name not in self._active_skills:
            return
        
        del self._active_skills[skill_name]
        
        # 移除对应的系统消息
        self._messages = [
            m for m in self._messages
            if m.get("_skill_name") != skill_name
        ]
        
        logger.info(f"Skill 已停用: {skill_name}")
    
    async def _process_response(self, response: str) -> None:
        # 增加消息计数
        for state in self._active_skills.values():
            state.message_count += 1
        
        # 检查 TTL
        self._check_skill_ttl()
```

#### 优点
- 自动回收 token
- 减少无关 Skill 干扰
- 可配置 TTL

#### 缺点
- 可能过早停用仍需要的 Skill
- 增加状态管理复杂度

---

## 推荐方案

**推荐路径：方案1（立即）→ 方案2 + 方案3（中期按需）**

1. **方案1 为必做项**：解决误触发问题
2. **方案2 按需实施**：当 Skill 数量增多，需要复杂规则时
3. **方案3 按需实施**：当 token 成本敏感时

---

## 实施计划

### 阶段 1：词边界匹配 + 优先级（立即，1-2小时）

1. 修改 `skills/models.py`：
   - `should_trigger` 改用正则词边界匹配
   - 添加 `priority` 字段
   - 添加 `get_trigger_score` 方法
2. 修改 `skills/parser.py`：
   - 解析 YAML 中的 `priority` 字段
3. 修改 `agent/agent.py`：
   - `_check_skill_triggers` 返回按优先级排序的列表

### 阶段 2：条件触发系统（中期，按需）

1. 扩展 `skills/models.py`：
   - 新增 `TriggerRule` 数据类
   - 支持 exclude 和 require_all
2. 扩展 `skills/parser.py`：
   - 支持新的 YAML 配置格式
3. 更新现有 Skill 配置

### 阶段 3：自动停用机制（中期，按需）

1. 新增 `ActiveSkillState` 数据类
2. 实现 `_check_skill_ttl` 和 `_deactivate_skill`
3. 在消息处理后调用 TTL 检查

---

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `src/quangan/skills/models.py` | `should_trigger` 改用正则，添加 `priority` |
| `src/quangan/skills/parser.py` | 解析 `priority` 字段，扩展触发规则解析 |
| `src/quangan/agent/agent.py` | 触发排序，TTL 管理 |
| `.qoder/skills/*.md` | 更新 YAML frontmatter 添加 priority |
