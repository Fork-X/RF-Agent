# Session Store 优化方案

## 问题描述

当前 `session_store.py` 的文件命名策略只依赖 `cwd`（工作目录）：

```python
def get_session_file_path(cwd: str) -> Path:
    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
    project_name = Path(cwd).name
    safe_name = re.sub(r"[^a-zA-Z0-9]", "-", project_name)
    return SESSIONS_DIR / f"{safe_name}-{cwd_hash}.json"
```

**问题**：同一个工作目录永远对应同一个文件，无法支持多个独立的 session 对话。

---

## 方案对比

### 方案 1：Session ID 隔离（推荐）

#### 设计思路
为每个 CLI 实例生成唯一的 session ID，文件名包含 session ID。

#### 实现方式

```python
def get_session_file_path(cwd: str, session_id: str = "default") -> Path:
    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
    project_name = Path(cwd).name
    safe_name = re.sub(r"[^a-zA-Z0-9]", "-", project_name)
    return SESSIONS_DIR / f"{safe_name}-{cwd_hash}-{session_id}.json"
```

#### 使用方式

```bash
# 终端 1 - 任务 A
QUANGAN_SESSION_ID=task1 uv run quangan

# 终端 2 - 任务 B
QUANGAN_SESSION_ID=task2 uv run quangan

# 终端 3 - 默认 session
uv run quangan
```

#### 生成文件
```
.sessions/
├── QUANGAN-py-a1b2c3d4-default.json      # 默认 session
├── QUANGAN-py-a1b2c3d4-task1.json        # 任务 A
└── QUANGAN-py-a1b2c3d4-task2.json        # 任务 B
```

#### 优点
- 向后兼容（默认 session_id="default"）
- 灵活，用户可自定义 session 名称
- 实现简单，改动范围小

#### 缺点
- 需要用户手动设置环境变量
- session 管理依赖用户记忆

---

### 方案 2：列表选择（交互式）

#### 设计思路
启动时检测该 cwd 下的所有 session，让用户选择或创建新 session。

#### 实现方式

```python
def list_sessions(cwd: str) -> list[Path]:
    """列出该 cwd 下的所有 session 文件"""
    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
    project_name = Path(cwd).name
    safe_name = re.sub(r"[^a-zA-Z0-9]", "-", project_name)
    pattern = f"{safe_name}-{cwd_hash}*.json"
    return sorted(SESSIONS_DIR.glob(pattern))

def select_session(cwd: str) -> tuple[str, list[dict]]:
    """交互式选择 session"""
    sessions = list_sessions(cwd)
    
    if not sessions:
        return "default", []
    
    # 显示选项
    print("检测到以下会话：")
    print("0. [新建会话]")
    for i, s in enumerate(sessions, 1):
        print(f"{i}. {s.name}")
    
    # 用户选择
    choice = input("请选择 [0-N]: ").strip()
    if choice == "0":
        new_name = input("输入新会话名称（回车使用默认）: ").strip()
        return new_name or "default", []
    
    # 加载选中的 session
    idx = int(choice) - 1
    return sessions[idx].stem, load_session_by_path(sessions[idx])
```

#### 启动流程
```
$ uv run quangan

检测到以下会话：
0. [新建会话]
1. QUANGAN-py-a1b2c3d4-default.json
2. QUANGAN-py-a1b2c3d4-task1.json
3. QUANGAN-py-a1b2c3d4-archive-2026-03-30T10-00-00.json

请选择 [0-3]: 2
已加载会话: task1
```

#### 优点
- 用户体验好，可视化选择
- 自动发现所有相关 session
- 支持命名 session，便于识别

#### 缺点
- 启动时需要额外交互
- 实现复杂度较高
- 需要修改启动流程

---

### 方案 3：时间戳自动归档（简单）

#### 设计思路
每次启动自动将现有 session 归档，全新开始。

#### 实现方式

```python
def load_session(cwd: str, auto_archive: bool = False) -> list[dict[str, Any]]:
    file_path = get_session_file_path(cwd)
    
    if file_path.exists() and auto_archive:
        # 自动归档现有会话
        timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        archive_path = file_path.with_suffix(f"-archive-{timestamp}.json")
        file_path.rename(archive_path)
        print(f"旧会话已归档: {archive_path.name}")
        return []
    
    # 正常加载逻辑
    if not file_path.exists():
        return []
    
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, Exception):
        return []
```

#### 启动方式
```bash
# 添加 --new-session 参数新建会话
uv run quangan --new-session
```

#### 优点
- 实现最简单
- 不会丢失历史（自动归档）
- 明确区分不同会话

#### 缺点
- 无法同时运行多个活跃 session
- 需要手动切换参数
- 不适合需要同时参考多个 session 的场景

---

## 推荐方案

**首选方案 1（Session ID 隔离）**，理由：

1. **向后兼容**：默认 session_id="default"，不影响现有用户
2. **灵活性高**：用户可自由命名 session，适应不同工作流
3. **实现简单**：改动范围小，主要集中在 `session_store.py`
4. **可扩展**：未来可结合方案 2 做交互式选择

---

## 实施计划

### 阶段 1：基础实现（方案 1）

1. 修改 `session_store.py`：
   - 所有函数增加 `session_id` 参数（默认 "default"）
   - 修改文件名生成逻辑

2. 修改 `main.py`：
   - 启动时读取 `QUANGAN_SESSION_ID` 环境变量
   - 将 session_id 传递给所有 session_store 调用

3. 显示当前 session：
   - 在欢迎信息中显示当前 session ID
   - 便于用户确认

### 阶段 2：增强功能（可选）

1. 添加 `/sessions` 命令：
   - 列出当前 cwd 下的所有 session
   - 支持切换 session

2. 添加 `--session` 参数：
   - 命令行直接指定 session
   - 替代环境变量方式

### 阶段 3：交互式选择（可选）

1. 结合方案 2 的交互式选择
2. 在启动时提供 session 选择界面
3. 支持新建、加载、删除 session

---

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `src/quangan/cli/session_store.py` | 添加 session_id 参数，修改文件名生成 |
| `src/quangan/cli/main.py` | 读取环境变量，传递 session_id |
| `src/quangan/cli/display.py` | 显示当前 session 信息 |
