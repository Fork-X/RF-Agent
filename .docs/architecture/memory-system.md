# QuanGan 双层记忆系统架构

## 概述

QuanGan 采用**双层记忆架构**（Two-Layer Memory Architecture），模拟人类记忆的短期/长期分离机制，实现高效、持久的记忆管理。

```
┌─────────────────────────────────────────────────────────────┐
│                     Memory System                           │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Core Memory (核心长期记忆)                        │
│  ├─ 存储: .memory/core-memory.json                          │
│  ├─ 特点: 稳定、持久、经过提炼的事实/偏好                     │
│  ├─ 结构: {id, content, firstSeen, reinforceCount}          │
│  └─ 更新: 通过 consolidate_core_memory 工具定期整合         │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Life Memory (日常短期记忆)                        │
│  ├─ 存储: .memory/life/lifeMemory-{theme}-{date}-{id}.md   │
│  ├─ 特点: 临时、会话级别、自动归档                          │
│  ├─ 结构: Markdown 文件，按日期命名                         │
│  └─ 更新: 每次上下文压缩时自动创建                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Memory (核心长期记忆)

### 数据结构

```python
@dataclass
class CoreMemoryItem:
    id: str              # 唯一标识符（如 "user-preference", "project-goals"）
    content: str         # 记忆内容（一句话概括）
    first_seen: str      # 首次记录日期 YYYY-MM-DD
    reinforce_count: int # 强化次数（出现频率）
```

### 核心概念：Reinforce Count

`reinforce_count` 是 Core Memory 的核心设计：

- **含义**: 表示该记忆被"强化"的次数
- **作用**: 
  - 量化记忆的重要性和稳定性
  - 高频出现的记忆在检索时优先显示
  - 用于判断哪些记忆应该长期保留
- **更新规则**:
  - 已有记忆每次整合时 +1
  - 新主题出现 2 次以上才加入，初始值为出现次数

### 存储格式

```json
{
  "updatedAt": "2026-03-30",
  "memories": [
    {
      "id": "user-preference",
      "content": "用户偏好使用 Python 进行开发",
      "firstSeen": "2026-03-25",
      "reinforceCount": 5
    }
  ]
}
```

---

## Life Memory (日常短期记忆)

### 存储结构

```
.memory/
├── core-memory.json
└── life/
    ├── lifeMemory-Agent开发-2026-03-30-abc123.md
    ├── lifeMemory-音乐播放-2026-03-29-def456.md
    └── ...
```

### 文件格式

```markdown
# Agent开发

日期：2026-03-30

本次会话主要讨论了 Agent 的架构设计，包括工具注册、消息历史管理等核心功能...
```

### 创建时机

Life Memory 在**上下文压缩时自动创建**：

```python
# main.py
on_compress_start=lambda: (
    console.print("[yellow]⏳ 上下文过长，正在压缩历史对话...[/]"),
    asyncio.create_task(update_life_memory_async()),
)[1],
```

---

## 记忆生命周期

```
用户对话 → 上下文压缩 → 生成摘要 → 写入 Life Memory
                              ↓
                    每 3 次压缩触发整合
                              ↓
              LLM 分析 14 天 Life Memory
                              ↓
              提取重复主题 → 更新 Core Memory
```

### 整合流程

1. **收集**: 读取最近 14 天的 Life Memory 文件
2. **分析**: 调用 LLM 识别重复出现的主题/偏好/事实
3. **对比**: 与现有 Core Memory 对比
4. **更新**:
   - 已有记忆 → `reinforce_count += 1`
   - 新主题（出现 2 次以上）→ 添加为新记忆
   - 设置 `reinforce_count` = 出现次数

---

## 记忆工具

| 工具 | 类型 | 功能 | 使用场景 |
|------|------|------|----------|
| `recall_memory` | readonly | 检索 Core + 最近 7 天 Life Memory | 用户提到"之前"、"上次"、"你还记得"时 |
| `update_life_memory` | write | 手动保存会话摘要 | 用户要求保存当前讨论内容 |
| `consolidate_core_memory` | write | 手动触发 Core Memory 整合 | 感知到某个主题反复出现时 |

---

## 系统集成

### 系统提示注入

Core Memory 在 Agent 启动时注入系统提示：

```python
# main.py
init_core_memory = get_core_memory(str(MEMORY_BASE_DIR))
memory_context = ""
if init_core_memory.memories:
    memory_context = "\n\n## 你的核心记忆\n" + "\n".join(
        f"- [强度:{m.reinforce_count}] {m.content}"
        for m in init_core_memory.memories
    )
```

这使得 Agent 在每次对话开始时就能"记住"用户的重要信息和偏好。

### 检索逻辑

```python
async def recall_impl(args: dict[str, Any]) -> str:
    query = args["query"].lower()
    query_words = query.split()
    
    core = get_core_memory(cwd)
    
    # 关键词匹配 Core Memory
    relevant = [
        m for m in core.memories
        if any(kw in m.content.lower() for kw in query_words)
    ]
    
    recent_life = get_recent_life_memories(cwd, 7)
    
    # 返回格式化的记忆结果
    ...
```

---

## 设计亮点

1. **分层存储**
   - 短期记忆（Life）快速写入，无需加工
   - 长期记忆（Core）经过提炼，稳定可靠

2. **自动整合**
   - 无需手动管理，系统定期自动归纳
   - LLM 参与分析，提取真正重要的信息

3. **强化机制**
   - `reinforce_count` 量化记忆重要性
   - 高频记忆优先展示，低频记忆自然淘汰

4. **文件化存储**
   - 使用 JSON + Markdown，便于人工查看和编辑
   - 版本控制友好，可追溯历史

5. **触发式激活**
   - 仅在相关话题时检索记忆，避免干扰
   - 系统提示预加载，确保基础记忆随时可用

---

## 相关文件

| 文件 | 职责 |
|------|------|
| `src/quangan/memory/store.py` | 存储层，文件 I/O 操作 |
| `src/quangan/memory/tools.py` | 工具层，记忆工具实现 |
| `src/quangan/memory/__init__.py` | 接口层，统一导出 |
| `.memory/core-memory.json` | 核心记忆数据文件 |
| `.memory/life/*.md` | 日常记忆文件目录 |
