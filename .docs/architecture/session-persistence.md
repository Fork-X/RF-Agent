# 会话持久化机制

## 概述

QuanGan 支持跨会话状态保持，当用户退出 CLI 后重新进入，可以恢复之前的对话历史。会话文件按工作目录隔离，不同项目有独立的会话存储。

---

## 会话文件路径生成

### 哈希算法

```python
# src/quangan/cli/session_store.py

def get_session_file_path(cwd: str) -> Path:
    """
    获取工作目录对应的会话文件路径。
    使用 MD5(cwd)[:8] 哈希创建唯一文件名。
    """
    _ensure_sessions_dir()

    # 创建 cwd 的 MD5 哈希（取前8位）
    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]

    # 获取项目名称
    project_name = Path(cwd).name
    
    # 清理项目名称（只保留字母数字）
    safe_name = re.sub(r"[^a-zA-Z0-9]", "-", project_name)

    return SESSIONS_DIR / f"{safe_name}-{cwd_hash}.json"
```

### 路径示例

| 工作目录 | 生成的文件名 |
|----------|--------------|
| `/Users/ruifeng/Projects/my-app` | `my-app-a1b2c3d4.json` |
| `/home/user/workspace/quangan-py` | `quangan-py-e5f6g7h8.json` |
| `/Users/ruifeng/IdeaProjects/QUANGAN-py` | `QUANGAN-py-f6702367.json` |

### 存储位置

```
项目根目录/
├── .sessions/                    # 会话存储目录
│   ├── my-app-a1b2c3d4.json     # 项目 A 的会话
│   ├── quangan-py-e5f6g7h8.json # 项目 B 的会话
│   └── my-app-a1b2c3d4-archive-2026-03-30T10-30-00.json  # 归档文件
├── src/
├── .memory/
└── ...
```

---

## 会话保存策略

### 保存时机

```python
# src/quangan/cli/main.py

async def process_user_message(text: str, session: PromptSession) -> None:
    try:
        response = await agent.run(message_to_send, is_plan_mode)
        display.print_assistant_message(response)
        
        # 每次对话后自动保存
        save_session(CWD, agent.get_history())
        
    except AgentInterruptedError:
        # 中断时也保存
        save_session(CWD, agent.get_history())
        ...
    except Exception:
        # 异常时也保存
        save_session(CWD, agent.get_history())
        ...
```

### 消息过滤

```python
def save_session(cwd: str, messages: list[dict[str, Any]]) -> None:
    """
    保存会话到文件。
    过滤掉系统消息（但保留 _summary 标记的摘要消息）。
    """
    to_save = [
        msg for msg in messages
        if msg.get("role") != "system" or msg.get("_summary")
    ]

    file_path.write_text(
        json.dumps(to_save, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
```

**过滤规则：**
- ✅ 保留：`user`、`assistant`、`tool` 消息
- ✅ 保留：带有 `_summary` 标记的系统消息（压缩摘要）
- ❌ 排除：普通系统提示（如"你是小枫..."）
- ❌ 排除：带有 `_skill` 标记的系统消息

### 存储格式示例

```json
[
  {
    "role": "system",
    "content": "[历史对话摘要 - 已自动压缩]\n已读取 src/utils.py..."
  },
  {
    "role": "user",
    "content": "帮我修改 utils.py"
  },
  {
    "role": "assistant",
    "content": "我来帮你修改",
    "tool_calls": [
      {
        "id": "call_abc123",
        "type": "function",
        "function": {
          "name": "coding_agent",
          "arguments": "{\"task\": \"修改 utils.py...\"}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "call_abc123",
    "name": "coding_agent",
    "content": "已完成修改..."
  },
  {
    "role": "assistant",
    "content": "已完成修改，添加了 log_info() 函数..."
  }
]
```

---

## 会话恢复流程

### 启动时加载

```python
# src/quangan/cli/main.py

async def async_main() -> None:
    # ... 初始化 Agent ...
    
    # 加载之前的会话
    previous_messages = load_session(CWD)
    if previous_messages:
        agent.load_messages(previous_messages)
    
    # ... 显示欢迎信息 ...
    
    if previous_messages:
        user_count = sum(1 for m in previous_messages if m.get("role") == "user")
        display.print_system(f"已恢复上次会话（{user_count} 轮对话），输入 /clear 可重新开始")
```

### Agent.load_messages 实现

```python
# src/quangan/agent/agent.py

def load_messages(self, messages: list[dict[str, Any]]) -> None:
    """
    加载消息历史（用于会话恢复）。
    直接追加到现有消息数组。
    """
    self._messages.extend(messages)
```

### 恢复后的消息数组结构

```
加载后：
[0] {role: "system", content: "你是小枫..."}           ← 新系统提示
[1] {role: "system", content: "[历史摘要]...", _summary: True}  ← 恢复的消息
[2] {role: "user", content: "之前的提问"}              ← 恢复的消息
[3] {role: "assistant", content: "之前的回答"}         ← 恢复的消息
[4] {role: "user", content: "新的提问"}                ← 新消息
```

---

## 会话清空归档

### /clear 命令

```python
# src/quangan/cli/main.py

def handle_command(cmd: str, session: PromptSession) -> bool:
    if cmd == "/clear":
        agent.clear_history()
        archived = clear_session(CWD)  # 归档旧会话
        console.clear()
        display.print_header(config.model)
        if archived:
            display.print_system(f"📦 旧对话已归档：{archived}")
        display.print_system("已开启新对话")
        return True
```

### 归档实现

```python
def clear_session(cwd: str) -> str | None:
    """
    清空会话（通过归档）。
    将会话文件重命名为带时间戳的归档文件。
    """
    file_path = get_session_file_path(cwd)

    if not file_path.exists():
        return None

    # 创建带时间戳的归档文件名
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    archive_path = file_path.with_suffix(f"-archive-{timestamp}.json")

    # 重命名归档
    file_path.rename(archive_path)

    return archive_path.name
```

### 归档文件示例

```
.sessions/
├── my-app-a1b2c3d4.json                           ← 当前会话
├── my-app-a1b2c3d4-archive-2026-03-28T14-30-00.json  ← 第一次归档
├── my-app-a1b2c3d4-archive-2026-03-29T09-15-00.json  ← 第二次归档
└── my-app-a1b2c3d4-archive-2026-03-30T16-45-00.json  ← 第三次归档
```

---

## 跨会话状态保持表

### 保持的状态

| 状态类型 | 存储位置 | 说明 |
|----------|----------|------|
| **消息历史** | `.sessions/{project}-{hash}.json` | 用户与 Agent 的完整对话历史（过滤后） |
| **Core Memory** | `.memory/core-memory.json` | 长期记忆，跨所有会话共享 |
| **Life Memory** | `.memory/life/*.md` | 短期记忆，按日期归档 |

### 不保持的状态

| 状态类型 | 说明 |
|----------|------|
| **子 Agent 会话** | 子 Agent 是无状态的，每次新建实例 |
| **LLM 连接** | HTTP 客户端每次重新创建 |
| **Skill 激活状态** | Skill 在每次启动时重新加载和触发 |
| **Plan 模式状态** | `/plan` 或 `/exec` 模式不保存 |
| **Token 用量统计** | 每次启动重新开始计算 |

---

## 会话数据流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           会话数据流                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   新会话启动                                                                 │
│       │                                                                     │
│       ▼                                                                     │
│   ┌─────────────────┐                                                       │
│   │ load_session()  │                                                       │
│   │ 检查 .sessions/ │                                                       │
│   │ 是否存在文件    │                                                       │
│   └────────┬────────┘                                                       │
│            │                                                                │
│      ┌─────┴─────┐                                                          │
│      ▼           ▼                                                          │
│   [存在]      [不存在]                                                       │
│      │           │                                                          │
│      ▼           ▼                                                          │
│   ┌──────────┐ ┌──────────┐                                                │
│   │读取 JSON │ │空列表    │                                                │
│   │解析消息  │ │          │                                                │
│   └────┬─────┘ └────┬─────┘                                                │
│        │            │                                                       │
│        └────────────┘                                                       │
│               │                                                             │
│               ▼                                                             │
│   ┌─────────────────────┐                                                   │
│   │ agent.load_messages()│                                                  │
│   │ 追加到 _messages    │                                                   │
│   └─────────────────────┘                                                   │
│               │                                                             │
│               ▼                                                             │
│   ┌─────────────────────┐                                                   │
│   │     正常对话        │                                                   │
│   │  user ↔ agent ↔ LLM │                                                   │
│   └─────────────────────┘                                                   │
│               │                                                             │
│               ▼                                                             │
│   ┌─────────────────────┐     ┌─────────────────────┐                      │
│   │   save_session()    │────▶│  .sessions/xxx.json │                      │
│   │  每次对话后自动保存  │     │  (UTF-8, 带缩进)    │                      │
│   └─────────────────────┘     └─────────────────────┘                      │
│                                                                             │
│   ┌─────────────────────────────────────────────────────┐                  │
│   │                      /clear                         │                  │
│   │  agent.clear_history()  │  clear_session()          │                  │
│   │  清空消息历史           │  重命名为归档文件          │                  │
│   └─────────────────────────────────────────────────────┘                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 相关文件

| 文件 | 职责 |
|------|------|
| `src/quangan/cli/session_store.py` | 会话存储核心实现（save/load/clear） |
| `src/quangan/cli/main.py` | CLI 层调用，启动加载，对话后保存 |
| `src/quangan/agent/agent.py` | `load_messages()`、`clear_history()` 实现 |

---

## 交叉引用

- 系统总览：[系统架构总览](system-overview.md)
- 记忆系统：[记忆系统架构](memory-system.md)
- CLI 实现：`src/quangan/cli/main.py`
