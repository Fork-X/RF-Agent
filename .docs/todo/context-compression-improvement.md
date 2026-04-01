# 上下文压缩改进

## 问题描述

当前上下文压缩策略存在多个问题：

1. **保留消息过少**：`KEEP_RECENT=6` 仅保留 ~1.7 轮对话，重要的前期讨论可能丢失

2. **硬截断丢信息**：500字硬截断可能丢失文件内容后半部分的关键信息

3. **阈值不适配**：`compression_threshold=16000` 对 8K 上下文模型（如 GPT-4）不适用

4. **无差异化压缩**：所有消息类型统一压缩策略，代码和文件路径可能被过度压缩

5. **静默失败**：压缩失败时静默返回（`agent.py:407-408`），可能导致上下文持续膨胀

```python
# agent.py 当前实现
KEEP_RECENT = 6  # 仅保留最近 6 条消息
MAX_CONTENT_LENGTH = 500  # 硬截断

async def _compress_context(self) -> None:
    try:
        # ... 压缩逻辑
    except Exception:
        return  # 静默失败！
```

---

## 方案对比

| 方案 | 技术选型 | 适用场景 | 实现难度 | 新增依赖 | 模块耦合 |
|------|----------|----------|----------|----------|----------|
| **方案1：模型自适应阈值** | 模型→窗口映射表 | 所有场景（必做） | 低（1小时） | 无 | 低 |
| 方案2：选择性压缩策略 | 消息优先级标记 | 代码密集型任务 | 中（1-2天） | 无 | 中 |
| 方案3：分层摘要 | L1/L2 双层结构 | 长期复杂任务 | 中（2-3天） | 无 | 高 |
| **方案4：关键信息提取器** | 正则提取 | 所有场景（推荐） | 低（半天） | 无 | 低 |

---

### 方案 1：模型自适应阈值（推荐立即执行）

#### 设计思路

根据 `LLMConfig` 中的模型名动态计算压缩阈值（模型上下文窗口 × 0.6）。

#### 核心实现

```python
# config/model_context.py
MODEL_CONTEXT_WINDOWS = {
    # OpenAI
    "gpt-4": 8192,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-3.5-turbo": 16385,
    
    # Anthropic
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,
    "claude-3-5-sonnet": 200000,
    
    # 其他
    "deepseek-chat": 64000,
    "qwen-max": 32000,
}

def get_context_window(model_name: str) -> int:
    """获取模型上下文窗口大小"""
    # 精确匹配
    if model_name in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model_name]
    
    # 前缀匹配
    for key, value in MODEL_CONTEXT_WINDOWS.items():
        if model_name.startswith(key):
            return value
    
    # 默认值
    return 8192

def get_compression_threshold(model_name: str) -> int:
    """计算压缩阈值（上下文窗口的 60%）"""
    window = get_context_window(model_name)
    return int(window * 0.6)
```

**集成到 AgentConfig：**

```python
# agent/agent.py
from config.model_context import get_compression_threshold

@dataclass
class AgentConfig:
    model_name: str = "gpt-4"
    compression_threshold: int = None  # 自动计算
    
    def __post_init__(self):
        if self.compression_threshold is None:
            self.compression_threshold = get_compression_threshold(self.model_name)
```

#### 优点
- 实现极简
- 自动适配不同模型
- 向后兼容

#### 缺点
- 需要维护模型映射表
- 新模型需手动添加

---

### 方案 2：选择性压缩策略（推荐中期）

#### 设计思路

为消息添加 `_priority` 元数据，根据优先级差异化处理。

#### 消息优先级定义

| 优先级 | 消息类型 | 压缩策略 |
|--------|----------|----------|
| high | 代码块、文件路径、错误信息 | 不压缩或截断到 2000 字 |
| medium | 普通对话、工具结果 | 截断到 500 字 |
| low | 闲聊、确认、重复内容 | 优先压缩/删除 |

#### 核心实现

```python
# agent/message_priority.py
import re

def classify_message_priority(content: str) -> str:
    """根据内容分类消息优先级"""
    # 高优先级：代码块
    if "```" in content:
        return "high"
    
    # 高优先级：文件路径
    if re.search(r'[/\\][\w\-\.]+\.(py|js|ts|go|rs|java|c|cpp|h)', content):
        return "high"
    
    # 高优先级：错误信息
    if any(kw in content.lower() for kw in ["error", "exception", "traceback", "failed"]):
        return "high"
    
    # 低优先级：确认消息
    if len(content) < 50 and any(kw in content for kw in ["好的", "收到", "ok", "done"]):
        return "low"
    
    return "medium"

def get_truncate_length(priority: str) -> int:
    """根据优先级返回截断长度"""
    return {"high": 2000, "medium": 500, "low": 100}[priority]
```

**修改压缩逻辑：**

```python
# agent/agent.py
async def _compress_context(self) -> None:
    # 按优先级分组
    high_priority = []
    medium_priority = []
    low_priority = []
    
    for msg in self._messages[:-KEEP_RECENT]:
        priority = classify_message_priority(msg.get("content", ""))
        if priority == "high":
            high_priority.append(msg)
        elif priority == "medium":
            medium_priority.append(msg)
        else:
            low_priority.append(msg)
    
    # 优先删除低优先级
    to_compress = low_priority + medium_priority + high_priority
    # ... 压缩逻辑
```

#### 优点
- 保护重要信息
- 提高压缩效率
- 可配置规则

#### 缺点
- 分类规则需要调优
- 增加处理复杂度

---

### 方案 3：分层摘要

#### 设计思路

维护两层摘要结构：
- **L1（任务目标和关键决定）**：永不丢弃
- **L2（步骤细节）**：可压缩

#### 核心实现

```python
# agent/context_layers.py
@dataclass
class ContextLayers:
    l1_summary: str = ""  # 任务目标、关键决定
    l2_summary: str = ""  # 步骤细节
    
    def to_system_message(self) -> str:
        parts = []
        if self.l1_summary:
            parts.append(f"[任务目标]\n{self.l1_summary}")
        if self.l2_summary:
            parts.append(f"[执行历史]\n{self.l2_summary}")
        return "\n\n".join(parts)

async def update_layers(
    layers: ContextLayers,
    messages: list[dict],
    llm_client: LLMClient
) -> ContextLayers:
    # 提取关键决定到 L1
    l1_prompt = """从以下对话中提取：
    1. 任务目标
    2. 关键技术决定
    3. 重要约束条件
    
    对话：{messages}"""
    
    layers.l1_summary = await llm_client.ask(l1_prompt.format(messages=messages))
    
    # 步骤细节到 L2（可被后续压缩）
    l2_prompt = """从以下对话中提取执行步骤摘要：{messages}"""
    layers.l2_summary = await llm_client.ask(l2_prompt.format(messages=messages))
    
    return layers
```

#### 优点
- 保留关键上下文
- 支持长期复杂任务
- 结构化信息管理

#### 缺点
- 实现复杂
- 需要 LLM 调用生成摘要
- Agent 结构大幅重构

---

### 方案 4：关键信息提取器（推荐立即执行）

#### 设计思路

压缩前先用正则提取文件路径、代码修改、错误信息等结构化信息，独立保存为 `structured_context`，附加在摘要后面。

#### 核心实现

```python
# agent/info_extractor.py
import re
from dataclasses import dataclass, field

@dataclass
class StructuredContext:
    file_paths: list[str] = field(default_factory=list)
    code_changes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    
    def to_string(self) -> str:
        parts = []
        if self.file_paths:
            parts.append("相关文件: " + ", ".join(set(self.file_paths)))
        if self.errors:
            parts.append("遇到的问题: " + "; ".join(self.errors[-3:]))
        if self.decisions:
            parts.append("关键决定: " + "; ".join(self.decisions[-3:]))
        return "\n".join(parts)

def extract_structured_info(content: str) -> StructuredContext:
    ctx = StructuredContext()
    
    # 提取文件路径
    file_pattern = r'[`\'"]?([/\\]?[\w\-\.]+[/\\][\w\-\./\\]+\.(py|js|ts|go|rs|java|c|cpp|h|md|json|yaml|toml))[`\'"]?'
    ctx.file_paths = re.findall(file_pattern, content)
    ctx.file_paths = [p[0] for p in ctx.file_paths]
    
    # 提取错误信息
    error_pattern = r'(Error|Exception|Failed|错误|失败)[:\s](.{10,100})'
    errors = re.findall(error_pattern, content, re.IGNORECASE)
    ctx.errors = [f"{e[0]}: {e[1]}" for e in errors]
    
    # 提取决定性语句
    decision_pattern = r'(决定|选择|使用|采用|改为)[：:\s](.{10,50})'
    decisions = re.findall(decision_pattern, content)
    ctx.decisions = [f"{d[0]}{d[1]}" for d in decisions]
    
    return ctx
```

**集成到压缩流程：**

```python
# agent/agent.py
async def _compress_context(self) -> None:
    old_messages = self._messages[:-KEEP_RECENT]
    
    # 提取结构化信息
    all_content = "\n".join(m.get("content", "") for m in old_messages)
    structured = extract_structured_info(all_content)
    
    # LLM 生成摘要
    summary = await self._generate_summary(old_messages)
    
    # 合并摘要和结构化信息
    compressed_content = f"{summary}\n\n[提取的关键信息]\n{structured.to_string()}"
    
    # 替换旧消息
    self._messages = [
        {"role": "system", "content": compressed_content},
        *self._messages[-KEEP_RECENT:]
    ]
```

#### 优点
- 保留结构化关键信息
- 实现简单，纯正则
- 与 LLM 摘要互补

#### 缺点
- 正则规则需要调优
- 可能提取噪音

---

## 推荐方案

**推荐路径：方案1 + 方案4（立即）→ 方案2（中期）**

1. **方案1**：解决阈值不适配问题，5分钟实现
2. **方案4**：保护关键信息不被压缩丢失
3. **方案2**：进一步优化压缩效果

---

## 实施计划

### 阶段 1：模型自适应阈值（立即，1小时）

1. 新建 `config/model_context.py`，添加模型映射表
2. 修改 `agent/agent.py` 的 `AgentConfig`：
   - 添加 `model_name` 字段
   - `compression_threshold` 改为自动计算

### 阶段 2：关键信息提取（立即，半天）

1. 新建 `agent/info_extractor.py`
2. 修改 `_compress_context`：
   - 压缩前调用 `extract_structured_info`
   - 摘要后附加结构化信息
3. 添加压缩失败日志（替代静默返回）

### 阶段 3：选择性压缩（中期，1-2天）

1. 新建 `agent/message_priority.py`
2. 修改 `_execute_tool_call`：为工具结果添加优先级标记
3. 修改 `_compress_context`：按优先级差异化处理

### 阶段 4：参数调优（持续）

1. `KEEP_RECENT` 改为可配置
2. 根据用户反馈调整分类规则
3. 添加压缩效果监控指标

---

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `src/quangan/config/model_context.py` | 新建，模型上下文窗口映射 |
| `src/quangan/config/llm_config.py` | 可选：添加 model_name 统一管理 |
| `src/quangan/agent/agent.py` | AgentConfig 自适应阈值，压缩逻辑改进 |
| `src/quangan/agent/info_extractor.py` | 新建，关键信息提取器 |
| `src/quangan/agent/message_priority.py` | 新建，消息优先级分类 |
