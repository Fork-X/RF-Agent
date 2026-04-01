# 安全性增强

## 问题描述

当前系统存在多个安全漏洞和一致性问题：

1. **命令黑名单不足**：`execute_command.py` 仅有 4 个硬编码黑名单（sudo/shutdown/reboot/fork bomb），无法防止 shell 管道攻击

2. **路径越界漏洞（BUG）**：`write_file.py` 和 `edit_file.py` **无路径越界检查**，可写入项目外任意文件

3. **confirm_fn 不一致（BUG）**：`confirm_fn` 仅在 `coding_agent` 中传递，`daily_agent` 未传递

4. **无审计日志**：所有工具操作无记录，无法追溯问题

5. **符号链接绕过**：路径解析可被符号链接绕过

```python
# execute_command.py 当前黑名单（不充分）
DANGEROUS_COMMANDS = ["sudo", "shutdown", "reboot", ":(){ :|:& };:"]

# write_file.py 无路径检查（漏洞）
def write_file(file_path: str, content: str) -> str:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)  # 可写入任意位置！
```

---

## 方案对比

| 方案 | 技术选型 | 适用场景 | 实现难度 | 新增依赖 | 模块耦合 |
|------|----------|----------|----------|----------|----------|
| **方案1：基础安全加固** | Path.resolve + is_relative_to | 所有场景（必做） | 低（半天） | 无 | 低 |
| **方案2：审计日志系统** | Python logging | 生产环境 | 低（1天） | 无 | 低 |
| 方案3：沙箱隔离 | subprocess + resource.setrlimit | 多用户/不可信输入 | 高（3-5天） | 无 | 高 |

---

### 方案 1：基础安全加固（推荐立即执行）

#### 设计思路

1. 为文件写入工具添加路径越界检查
2. 修复 daily_agent 缺失 confirm_fn 的 BUG
3. 完善命令黑名单

#### 核心实现

**路径越界检查：**

```python
# coding/tools/write_file.py
from pathlib import Path

def validate_path(file_path: str, work_dir: str) -> tuple[bool, str]:
    """验证路径是否在工作目录内"""
    try:
        resolved = Path(file_path).resolve()
        work_resolved = Path(work_dir).resolve()
        
        # 检查符号链接
        if resolved.is_symlink():
            return False, "不允许写入符号链接"
        
        # 检查是否在工作目录内
        if not resolved.is_relative_to(work_resolved):
            return False, f"路径越界：{resolved} 不在 {work_resolved} 内"
        
        return True, ""
    except Exception as e:
        return False, f"路径验证失败：{e}"

def write_file(file_path: str, content: str, work_dir: str) -> str:
    valid, error = validate_path(file_path, work_dir)
    if not valid:
        return f"[安全拒绝] {error}"
    # ... 正常写入逻辑
```

**完善命令黑名单：**

```python
# coding/tools/execute_command.py
DANGEROUS_PATTERNS = [
    # 提权
    r"\bsudo\b", r"\bsu\b", r"\bdoas\b",
    # 系统破坏
    r"\bshutdown\b", r"\breboot\b", r"\bhalt\b",
    r"\brm\s+-rf\s+/", r"\bmkfs\b", r"\bdd\b.*of=/dev",
    # 管道攻击
    r"\bcurl\b.*\|\s*sh", r"\bwget\b.*\|\s*sh",
    r"\bcurl\b.*\|\s*bash", r"\bwget\b.*\|\s*bash",
    # Fork bomb
    r":\(\)\s*\{.*\}", r"\.\/\.:",
    # 危险重定向
    r">\s*/etc/", r">\s*/dev/",
]

def is_command_safe(command: str) -> tuple[bool, str]:
    import re
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"匹配危险模式：{pattern}"
    return True, ""
```

**修复 daily_agent confirm_fn：**

```python
# daily/__init__.py
def create_daily_agent_tools(work_dir: str, confirm_fn: Callable = None):
    # 确保 confirm_fn 被传递给需要确认的工具
    return [
        run_shell_tool(work_dir, confirm_fn),  # 修复：添加 confirm_fn
        # ...
    ]
```

#### 优点
- 修复关键安全漏洞
- 零新依赖
- 改动范围小，可快速部署

#### 缺点
- 仍依赖正则匹配，可能有绕过方式
- 无运行时监控

---

### 方案 2：审计日志系统

#### 设计思路

为所有工具执行添加结构化日志，便于问题追溯和安全审计。

#### 核心实现

```python
# utils/audit.py
import logging
import json
from datetime import datetime
from pathlib import Path

def setup_audit_logger(log_dir: str = ".logs") -> logging.Logger:
    Path(log_dir).mkdir(exist_ok=True)
    
    logger = logging.getLogger("quangan.audit")
    logger.setLevel(logging.INFO)
    
    # 文件 Handler
    today = datetime.now().strftime("%Y-%m-%d")
    handler = logging.FileHandler(
        f"{log_dir}/audit-{today}.log",
        encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(message)s"
    ))
    logger.addHandler(handler)
    
    return logger

def log_tool_execution(
    logger: logging.Logger,
    tool_name: str,
    params: dict,
    result: str,
    duration_ms: float,
    user_confirmed: bool = None
) -> None:
    record = {
        "tool": tool_name,
        "params": _sanitize_params(params),
        "result_preview": result[:200] if result else None,
        "duration_ms": round(duration_ms, 2),
        "confirmed": user_confirmed,
    }
    logger.info(json.dumps(record, ensure_ascii=False))

def _sanitize_params(params: dict) -> dict:
    """脱敏处理敏感参数"""
    sensitive_keys = ["password", "token", "secret", "key"]
    return {
        k: "***" if any(s in k.lower() for s in sensitive_keys) else v
        for k, v in params.items()
    }
```

**集成到 Agent：**

```python
# agent/agent.py
async def _execute_tool_call(self, tool_call: ToolCall) -> str:
    start = time.perf_counter()
    result = await self._run_tool(tool_call)
    duration = (time.perf_counter() - start) * 1000
    
    # 审计日志
    self._audit_logger.log_tool_execution(
        tool_name=tool_call.name,
        params=tool_call.arguments,
        result=result,
        duration_ms=duration
    )
    return result
```

#### 日志格式示例

```json
{"tool": "write_file", "params": {"file_path": "src/main.py"}, "result_preview": "文件已写入", "duration_ms": 12.5, "confirmed": true}
{"tool": "execute_command", "params": {"command": "ls -la"}, "result_preview": "total 48\ndrwxr-xr-x...", "duration_ms": 156.3, "confirmed": false}
```

#### 优点
- 完整的操作记录
- 支持问题追溯
- 零新依赖

#### 缺点
- 日志文件需要定期清理
- 敏感信息需要脱敏处理

---

### 方案 3：沙箱隔离（远期）

#### 设计思路

使用进程级隔离限制命令执行的资源和权限。

#### 核心实现

```python
# coding/tools/sandbox.py
import subprocess
import resource
import os

class SandboxConfig:
    max_cpu_time: int = 30        # 秒
    max_memory: int = 512 * 1024 * 1024  # 512MB
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    allowed_paths: list[str] = []

def run_sandboxed(
    command: str,
    work_dir: str,
    config: SandboxConfig = None
) -> tuple[int, str, str]:
    config = config or SandboxConfig()
    
    def set_limits():
        # CPU 时间限制
        resource.setrlimit(resource.RLIMIT_CPU, (config.max_cpu_time, config.max_cpu_time))
        # 内存限制
        resource.setrlimit(resource.RLIMIT_AS, (config.max_memory, config.max_memory))
        # 文件大小限制
        resource.setrlimit(resource.RLIMIT_FSIZE, (config.max_file_size, config.max_file_size))
    
    # 清理环境变量
    safe_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": work_dir,
        "LANG": "en_US.UTF-8",
    }
    
    proc = subprocess.run(
        command,
        shell=True,
        cwd=work_dir,
        env=safe_env,
        capture_output=True,
        timeout=config.max_cpu_time + 5,
        preexec_fn=set_limits
    )
    
    return proc.returncode, proc.stdout.decode(), proc.stderr.decode()
```

#### 优点
- 进程级资源隔离
- 防止资源耗尽攻击
- 限制文件系统访问

#### 缺点
- 实现复杂
- 可能影响正常功能
- 跨平台兼容性问题（macOS/Linux/Windows）

---

## 推荐方案

**推荐路径：方案1（立即）→ 方案2（短期）→ 方案3（远期按需）**

1. **方案1 为必做项**：修复已知安全漏洞
2. **方案2 增强可观测性**：为后续安全分析提供数据
3. **方案3 按需实施**：仅在多用户或不可信输入场景需要

---

## 实施计划

### 阶段 1：基础安全加固（立即，半天）

1. 在 `coding/tools/` 下新建 `security.py`，实现 `validate_path`
2. 修改 `write_file.py`：添加路径验证调用
3. 修改 `edit_file.py`：添加路径验证调用
4. 修改 `execute_command.py`：完善危险命令正则
5. 修改 `daily/__init__.py`：传递 `confirm_fn`
6. 修改 `main.py`：确保 daily_agent 创建时传递 confirm_fn

### 阶段 2：审计日志（短期，1天）

1. 新建 `utils/audit.py`
2. 修改 `agent/agent.py`：在 `_execute_tool_call` 中注入日志
3. 配置日志轮转策略
4. 添加 `.logs/` 到 `.gitignore`

### 阶段 3：沙箱隔离（远期，按需）

1. 评估沙箱需求场景
2. 实现跨平台沙箱抽象
3. 添加配置化的资源限制

---

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `src/quangan/coding/tools/write_file.py` | 添加路径越界检查 |
| `src/quangan/coding/tools/edit_file.py` | 添加路径越界检查 |
| `src/quangan/coding/tools/execute_command.py` | 完善危险命令黑名单 |
| `src/quangan/coding/tools/security.py` | 新建，路径验证工具函数 |
| `src/quangan/agents/daily/__init__.py` | 修复 confirm_fn 传递 |
| `src/quangan/cli/main.py` | 确保 daily_agent confirm_fn |
| `src/quangan/utils/audit.py` | 新建，审计日志模块 |
| `src/quangan/agent/agent.py` | 集成审计日志 |
