# 上下文压缩算法

## 概述

QuanGan 采用**滚动摘要**机制进行上下文压缩，当 Token 用量超过阈值时，自动将旧消息压缩成摘要，既保持上下文窗口可控，又保留关键信息。压缩过程还会触发 Life Memory 的自动更新，实现对话历史的持久化存储。

---

## 压缩触发条件

```python
# src/quangan/agent/agent.py

# 每次 LLM 调用后检查 Token 用量
if result.usage and result.usage.total >= self._compression_threshold:
    await self._compress_context()
```

### 配置参数

```python
@dataclass
class AgentConfig:
    compression_threshold: int = 16_000  # 默认触发阈值
```

| 模型 | 上下文上限 | 建议阈值 | 说明 |
|------|-----------|----------|------|
| GPT-4 | 128K | 16,000 | 预留 12% 余量 |
| Claude 3 | 200K | 16,000 | 保守策略 |
| 国产模型 | 8K-32K | 6,000-12,000 | 根据实际调整 |

---

## 压缩策略详解

### KEEP_RECENT 策略

```python
KEEP_RECENT = 6  # 保留最近 6 条非系统消息（约 3 轮对话）
```

保留的消息包括：
- 用户输入
- Assistant 响应
- Tool 执行结果

这些消息保持完整，确保短期上下文连贯性。

### 消息分类

```python
# 统计活跃非系统消息
active = [
    m for m in self._messages
    if not m.get("_archived") and m.get("role") != "system"
]

if len(active) <= KEEP_RECENT:
    return  # 消息太少，无需压缩

to_compress = active[:-KEEP_RECENT]   # 需要压缩的旧消息
to_keep = active[-KEEP_RECENT:]       # 保留的近期消息
```

### 压缩前 vs 压缩后

```
压缩前消息数组：
[system] 系统提示
[user] 问题1
[assistant] 回答1
[tool] 结果1
[user] 问题2
[assistant] 回答2  ← to_keep 开始
[tool] 结果2
[user] 问题3
[assistant] 回答3
[user] 问题4       ← to_compress 结束

压缩后消息数组：
[system] 系统提示
[system] [历史对话摘要 - 已自动压缩]  ← 新增摘要节点
[user] 问题2      ← 标记 _archived=True
[assistant] 回答2  ← 标记 _archived=True
[tool] 结果2      ← 标记 _archived=True
[user] 问题3      ← 保留（to_keep）
[assistant] 回答3  ← 保留（to_keep）
[user] 问题4      ← 保留（to_keep）
```

---

## LLM生成摘要流程

### 构建摘要提示

```python
summary_parts = []
for m in to_compress:
    role = m.get("role", "")
    if role == "user":
        role_label = "用户"
    elif role == "assistant":
        role_label = "Agent"
    else:
        role_label = "工具"

    content = m.get("content", "")
    if isinstance(content, str):
        text = content[:500]  # 截断到 500 字符
    else:
        text = json.dumps(content)[:500]

    summary_parts.append(f"[{role_label}]: {text}")

summary_prompt = "\n\n".join(summary_parts)
```

### 调用摘要助手

```python
summary = await self._client.chat(
    [
        {"role": "system", "content": "你是一个对话摘要助手，擅长从编程对话中提炼关键信息。"},
        {
            "role": "user",
            "content": f"""请将以下对话历史压缩成简洁摘要（200字以内），重点保留：
- 已读过的文件路径
- 做过的代码修改
- 重要结论

{summary_prompt}""",
        },
    ]
)
```

### 摘要示例

**原始对话（约 3000 字）：**
```
用户：帮我看看 src/utils.py 这个文件
Agent：好的，我来读取文件内容（调用 read_file）
[返回 100 行代码]
用户：在第 30 行添加一个日志函数
Agent：我来修改（调用 edit_file）
[修改结果]
Agent：验证一下（调用 verify_code）
[验证通过]
用户：再帮我创建一个新文件 src/config.py
...
```

**生成的摘要（约 150 字）：**
```
已读取 src/utils.py，在第 30 行添加了 log_info() 日志函数，
使用标准 logging 模块，验证通过。创建了 src/config.py，
定义了 Config 类用于配置管理。用户偏好使用类型注解。
```

---

## 消息数组重建过程

### 构建摘要标记节点

```python
summary_msg: dict[str, Any] = {
    "role": "system",
    "content": f"[历史对话摘要 - 已自动压缩]\n{summary}",
    "_summary": True,  # 标记为摘要节点
}
```

### 使用 Python 对象 ID 追踪

```python
# 使用 id() 追踪消息对象，确保精确匹配
to_compress_set = set(id(m) for m in to_compress)
first_keep_ref = to_keep[0] if to_keep else None

new_messages: list[dict[str, Any]] = []
summary_inserted = False

for msg in self._messages:
    # 在第一个保留消息前插入摘要
    if not summary_inserted and first_keep_ref is not None and msg is first_keep_ref:
        new_messages.append(summary_msg)
        summary_inserted = True

    # 旧消息标记为已归档
    if id(msg) in to_compress_set:
        new_messages.append({**msg, "_archived": True})
    else:
        new_messages.append(msg)
```

### 元数据标记说明

| 标记 | 含义 | 用途 |
|------|------|------|
| `_summary` | 摘要节点 | `_get_llm_messages()` 识别压缩点 |
| `_archived` | 已归档 | 从 LLM 上下文中排除 |
| `_skill` | Skill 提示 | 压缩时保留的系统消息 |

---

## _get_llm_messages()过滤机制

### 过滤逻辑

```python
def _get_llm_messages(self) -> list[dict[str, Any]]:
    # 1. 获取系统消息（排除 _summary 标记）
    system_msgs = [
        m for m in self._messages
        if m.get("role") == "system" and not m.get("_summary")
    ]

    # 2. 找到最新摘要位置
    last_summary_idx = -1
    for i in range(len(self._messages) - 1, -1, -1):
        if self._messages[i].get("_summary"):
            last_summary_idx = i
            break

    # 3. 获取上下文消息
    if last_summary_idx >= 0:
        # 有摘要：摘要 + 之后所有消息
        context_msgs = self._messages[last_summary_idx:]
    else:
        # 无摘要：所有非归档消息
        context_msgs = [
            m for m in self._messages
            if not m.get("_archived") and m.get("role") != "system"
        ]

    # 4. 剥离元数据后返回
    result = []
    for msg in system_msgs + context_msgs:
        clean_msg = {k: v for k, v in msg.items() if not k.startswith("_")}
        result.append(clean_msg)

    return result
```

### 过滤示例

```
完整消息数组：
[0]  {role: "system", content: "你是小枫..."}
[1]  {role: "system", content: "[Skill...", _skill: "python"}
[2]  {role: "system", content: "[历史摘要]...", _summary: True}
[3]  {role: "user", content: "问题1", _archived: True}
[4]  {role: "assistant", content: "回答1", _archived: True}
[5]  {role: "user", content: "问题2"}
[6]  {role: "assistant", content: "回答2"}

_get_llm_messages() 返回：
[0]  {role: "system", content: "你是小枫..."}
[1]  {role: "system", content: "[Skill..."}  ← _skill 保留，但剥离标记
[2]  {role: "system", content: "[历史摘要]..."}  ← _summary 保留，但剥离标记
[5]  {role: "user", content: "问题2"}
[6]  {role: "assistant", content: "回答2"}

排除：
- [3], [4]：_archived=True
```

---

## 压缩与Life Memory联动

### 回调触发

```python
# src/quangan/cli/main.py

agent_config = AgentConfig(
    on_compress_start=lambda: (
        console.print("[yellow]⏳ 上下文过长，正在压缩历史对话...[/]"),
        asyncio.create_task(update_life_memory_async()),  # 触发 Life Memory 更新
    )[1],
    on_compress=lambda before, after: display.print_system(
        f"♻️ 上下文已自动压缩（{before} → {after} 条消息）"
    ),
)
```

### 异步 Fire-and-Forget

```python
async def update_life_memory_async() -> None:
    """在上下文压缩时异步更新 Life Memory"""
    global _life_memory_update_count
    
    try:
        # 获取近期非归档消息
        history = [
            msg for msg in agent.get_history()
            if not msg.get("_archived") and msg.get("role") != "system"
        ]
        
        if not history:
            return
        
        # 生成摘要
        history_text = "\n\n".join(
            f"[{'用户' if m.get('role') == 'user' else 'Agent'}]: {str(m.get('content', ''))[:400]}"
            for m in history
        )
        
        summary = await client.ask(
            f"请将以下对话提炼为简洁的日常记忆摘要（150字以内）：\n\n{history_text}",
            "你是记忆整合助手，请用简洁中文生成摘要。",
        )
        
        # 提取主题词
        theme = await client.ask(
            f"根据以下摘要，提取一个简短的主题词（3-8字）：\n\n{summary}",
            "只输出主题词，不要其他内容。",
        )
        
        # 保存到 Life Memory
        append_life_memory(str(MEMORY_BASE_DIR), theme.strip(), summary)
        
        _life_memory_update_count += 1
        
        # 每 3 次压缩触发 Core Memory 整合
        if _life_memory_update_count % 3 == 0:
            await consolidate_impl()
            
    except Exception:
        pass  # 静默失败
```

### 两次 LLM 调用

1. **生成摘要**：将近期对话提炼为 150 字摘要
2. **提取主题**：从摘要中提取 3-8 字主题词

### 整合触发

```
压缩次数: 1    2    3    4    5    6    ...
          │    │    │    │    │    │
          ▼    ▼    ▼    ▼    ▼    ▼
         Life Life Core Life Life Core ...
         Mem  Mem  Mem  Mem  Mem  Mem
```

---

## 压缩流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           上下文压缩流程                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [触发]                                                                      │
│    │                                                                        │
│    ▼                                                                        │
│  ┌─────────────────────────────────────────┐                               │
│  │ Token 用量 >= threshold (16000)         │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ on_compress_start 回调                   │                               │
│  │ - 显示压缩提示                           │                               │
│  │ - 触发 update_life_memory_async()       │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ 分类消息                                │                               │
│  │ - active = 非归档 && 非系统             │                               │
│  │ - to_compress = active[:-6]             │                               │
│  │ - to_keep = active[-6:]                 │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ 构建摘要提示                            │                               │
│  │ - 角色标签中文化                        │                               │
│  │ - 内容截断 500 字                       │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ LLM 生成摘要                            │                               │
│  │ - 系统提示：对话摘要助手                │                               │
│  │ - 限制：200 字以内                      │                               │
│  │ - 重点：文件路径、代码修改、结论        │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ 重建消息数组                            │                               │
│  │ - 创建 summary_msg (_summary=True)      │                               │
│  │ - 使用 id() 追踪消息对象                │                               │
│  │ - 在 to_keep[0] 前插入摘要              │                               │
│  │ - to_compress 消息标记 _archived=True   │                               │
│  └───────────────────┬─────────────────────┘                               │
│                      │                                                      │
│                      ▼                                                      │
│  ┌─────────────────────────────────────────┐                               │
│  │ on_compress 回调                         │                               │
│  │ - 显示压缩结果：before → after          │                               │
│  └─────────────────────────────────────────┘                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 相关文件

| 文件 | 职责 |
|------|------|
| `src/quangan/agent/agent.py` | `_compress_context()` 实现，`_get_llm_messages()` 过滤逻辑 |
| `src/quangan/cli/main.py` | `update_life_memory_async()`，压缩回调配置 |
| `src/quangan/memory/store.py` | `append_life_memory()` 存储实现 |
| `src/quangan/memory/tools.py` | `consolidate_impl()` Core Memory 整合 |

---

## 交叉引用

- 记忆系统详解：[记忆系统架构](memory-system.md)
- ReAct 循环：[ReAct循环与任务管理](react-loop.md)
- 系统总览：[系统架构总览](system-overview.md)
