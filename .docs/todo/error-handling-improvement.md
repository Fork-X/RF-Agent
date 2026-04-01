# 错误处理改进

## 问题描述

当前项目错误处理存在多个问题：

1. **无日志框架**：全项目无任何 logging 框架，`pyproject.toml` 未引入 logging/structlog/loguru

2. **静默失败**：
   - `_compress_context` 压缩失败静默返回（`agent.py:407-408`），上下文可能持续膨胀
   - `update_life_memory_async` 异常完全吞掉（`main.py:162-164`），记忆可能丢失

3. **无重试机制**：LLM API 调用无重试，网络抖动直接失败

4. **错误未分类**：所有 `Exception` 同等对待，无法差异化处理

```python
# agent.py:407-408 静默失败
async def _compress_context(self) -> None:
    try:
        # ... 压缩逻辑
    except Exception:
        return  # 静默失败，无日志！

# main.py:162-164 吞掉异常
try:
    await update_life_memory_async(memory_store, content)
except Exception:
    pass  # 记忆可能丢失！
```

---

## 方案对比

| 方案 | 技术选型 | 适用场景 | 实现难度 | 新增依赖 | 模块耦合 |
|------|----------|----------|----------|----------|----------|
| **方案1：基础日志系统** | Python logging | 所有场景（必做） | 低（2-3小时） | 无 | 低 |
| **方案2：LLM调用重试** | tenacity / 手写 | LLM 调用场景 | 低（2小时） | tenacity（可选） | 低 |
| 方案3：错误分级与降级 | 自定义异常类 | 高可用要求 | 中（1-2天） | 无 | 中 |

---

### 方案 1：基础日志系统（推荐立即执行）

#### 设计思路

使用 Python 内置 `logging` 模块，零新依赖，在关键位置添加结构化日志。

#### 核心实现

```python
# utils/logger.py
import logging
import sys
from pathlib import Path
from datetime import datetime

def setup_logger(
    name: str = "quangan",
    log_dir: str = ".logs",
    console_level: int = logging.WARNING,
    file_level: int = logging.DEBUG
) -> logging.Logger:
    """配置应用日志"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    # Console Handler (WARNING+)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(
        "%(levelname)s: %(message)s"
    ))
    logger.addHandler(console_handler)
    
    # File Handler (DEBUG+)
    Path(log_dir).mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(
        f"{log_dir}/quangan-{today}.log",
        encoding="utf-8"
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    ))
    logger.addHandler(file_handler)
    
    return logger

# 全局 logger 实例
logger = setup_logger()
```

#### 日志级别规范

| 级别 | 使用场景 |
|------|----------|
| DEBUG | 工具执行详情、消息流转 |
| INFO | 任务开始/完成、关键操作 |
| WARNING | 可恢复的问题、性能警告 |
| ERROR | 不可恢复错误、异常捕获 |

#### 关键位置日志注入

```python
# agent/agent.py
from utils.logger import logger

async def _execute_tool_call(self, tool_call: ToolCall) -> dict:
    logger.debug(f"执行工具: {tool_call.name}, 参数: {tool_call.arguments}")
    try:
        result = await self._run_tool(tool_call)
        logger.debug(f"工具完成: {tool_call.name}, 结果长度: {len(result)}")
        return result
    except Exception as e:
        logger.error(f"工具执行失败: {tool_call.name}, 错误: {e}")
        raise

async def _compress_context(self) -> None:
    logger.info("开始上下文压缩")
    try:
        # ... 压缩逻辑
        logger.info(f"上下文压缩完成, 消息数: {len(self._messages)}")
    except Exception as e:
        logger.error(f"上下文压缩失败: {e}")
        # 不再静默返回，而是记录并继续

# memory/tools.py
from utils.logger import logger

async def update_life_memory_async(store: MemoryStore, content: str) -> None:
    try:
        await store.add_life_memory(content)
        logger.info("Life Memory 更新成功")
    except Exception as e:
        logger.error(f"Life Memory 更新失败: {e}")
        # 可选：触发降级策略
```

#### 日志文件示例

```
2026-04-01 10:30:15 | INFO | quangan | 开始上下文压缩
2026-04-01 10:30:16 | DEBUG | quangan | 执行工具: read_file, 参数: {"path": "src/main.py"}
2026-04-01 10:30:16 | DEBUG | quangan | 工具完成: read_file, 结果长度: 2048
2026-04-01 10:30:17 | ERROR | quangan | 上下文压缩失败: LLM API timeout
```

#### 优点
- 零新依赖
- 问题可追溯
- 支持日志轮转

#### 缺点
- 需要在多处添加日志代码
- 日志文件需定期清理

---

### 方案 2：LLM 调用重试机制

#### 设计思路

为 LLM API 调用添加带指数退避的重试机制，区分可重试和不可重试错误。

#### 错误分类

| 错误类型 | HTTP 状态码 | 处理方式 |
|----------|-------------|----------|
| Rate Limit | 429 | 重试，等待 Retry-After |
| Server Error | 500/502/503 | 重试，指数退避 |
| Timeout | - | 重试，最多 3 次 |
| Auth Error | 401/403 | 不重试，立即失败 |
| Bad Request | 400 | 不重试，立即失败 |

#### 核心实现（手写版，无依赖）

```python
# llm/retry.py
import asyncio
from functools import wraps
from typing import TypeVar, Callable, Awaitable

T = TypeVar("T")

class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0  # 秒
    max_delay: float = 30.0
    exponential_base: float = 2.0

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

class LLMError(Exception):
    def __init__(self, message: str, status_code: int = None, retryable: bool = False):
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(message)

def with_retry(config: RetryConfig = None):
    """带重试的装饰器"""
    config = config or RetryConfig()
    
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_error = None
            
            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except LLMError as e:
                    last_error = e
                    
                    if not e.retryable:
                        raise
                    
                    if attempt < config.max_retries:
                        delay = min(
                            config.base_delay * (config.exponential_base ** attempt),
                            config.max_delay
                        )
                        logger.warning(
                            f"LLM 调用失败, {delay}秒后重试 "
                            f"(第{attempt+1}/{config.max_retries}次): {e.message}"
                        )
                        await asyncio.sleep(delay)
                except asyncio.TimeoutError:
                    last_error = LLMError("请求超时", retryable=True)
                    if attempt < config.max_retries:
                        await asyncio.sleep(config.base_delay)
            
            raise last_error
        
        return wrapper
    return decorator
```

#### 集成到 LLM Client

```python
# llm/client.py
from .retry import with_retry, LLMError, RETRYABLE_STATUS_CODES

class LLMClient:
    @with_retry()
    async def chat(self, messages: list[dict]) -> str:
        try:
            response = await self._http_client.post(
                self._endpoint,
                json={"messages": messages}
            )
            
            if response.status_code in RETRYABLE_STATUS_CODES:
                raise LLMError(
                    f"API 错误: {response.status_code}",
                    status_code=response.status_code,
                    retryable=True
                )
            
            if response.status_code >= 400:
                raise LLMError(
                    f"API 错误: {response.status_code}",
                    status_code=response.status_code,
                    retryable=False
                )
            
            return response.json()["choices"][0]["message"]["content"]
        
        except httpx.TimeoutException:
            raise LLMError("请求超时", retryable=True)
```

#### 优点
- 提高 API 调用稳定性
- 自动处理临时故障
- 零额外依赖（手写版）

#### 缺点
- 重试可能增加延迟
- 需要正确分类错误

---

### 方案 3：错误分级与降级策略

#### 设计思路

定义错误等级，为不同错误提供差异化的降级处理。

#### 错误等级定义

```python
# utils/errors.py
from enum import Enum
from dataclasses import dataclass

class ErrorSeverity(Enum):
    TRANSIENT = "transient"    # 可重试
    DEGRADED = "degraded"      # 降级处理
    PERMANENT = "permanent"    # 不可恢复

@dataclass
class AppError(Exception):
    message: str
    severity: ErrorSeverity
    context: dict = None
    
    def __str__(self):
        return f"[{self.severity.value}] {self.message}"

class CompressionError(AppError):
    """上下文压缩错误"""
    pass

class MemoryError(AppError):
    """记忆存储错误"""
    pass

class LLMError(AppError):
    """LLM 调用错误"""
    pass
```

#### 降级策略

```python
# agent/fallback.py

async def compress_with_fallback(agent: Agent) -> None:
    """带降级的上下文压缩"""
    try:
        await agent._compress_with_llm()
    except CompressionError as e:
        if e.severity == ErrorSeverity.DEGRADED:
            logger.warning(f"LLM 压缩失败，使用简单删除: {e.message}")
            agent._simple_trim_messages()  # 降级：直接删除旧消息
        else:
            raise

async def consolidate_with_fallback(store: MemoryStore) -> None:
    """带降级的记忆整合"""
    try:
        await store.consolidate_with_llm()
    except MemoryError as e:
        if e.severity == ErrorSeverity.DEGRADED:
            logger.warning(f"LLM 整合失败，跳过本次整合: {e.message}")
            # 降级：保留原 Core Memory，跳过整合
        else:
            raise
```

#### 降级策略表

| 操作 | 正常流程 | 降级策略 |
|------|----------|----------|
| 上下文压缩 | LLM 生成摘要 | 简单删除旧消息 |
| 记忆整合 | LLM 合并相似记忆 | 跳过整合 |
| Life Memory 更新 | 异步写入文件 | 写入失败队列，稍后重试 |
| Skill 触发 | 检查所有 Skill | 跳过失败的 Skill |

#### 优点
- 系统更健壮
- 明确的降级策略
- 错误可追溯

#### 缺点
- 实现复杂
- 需要为每个场景设计降级策略

---

## 推荐方案

**推荐路径：方案1（立即）→ 方案2（短期）→ 方案3（按需）**

1. **方案1 为必做项**：基础可观测性
2. **方案2 提高稳定性**：LLM API 是最常见的故障点
3. **方案3 按需实施**：高可用场景

---

## 实施计划

### 阶段 1：基础日志系统（立即，2-3小时）

1. 新建 `utils/logger.py`
2. 修改 `agent/agent.py`：
   - `_execute_tool_call` 添加日志
   - `_compress_context` 添加日志（移除静默返回）
3. 修改 `memory/tools.py`：
   - `update_life_memory_async` 添加日志
4. 修改 `cli/main.py`：
   - 启动时初始化 logger
5. 添加 `.logs/` 到 `.gitignore`

### 阶段 2：LLM 调用重试（短期，2小时）

1. 新建 `llm/retry.py`
2. 修改 `llm/client.py`：
   - 添加 `@with_retry()` 装饰器
3. 修改 `llm/anthropic_client.py`：
   - 同样添加重试机制
4. 配置化重试参数

### 阶段 3：错误分级（按需，1-2天）

1. 新建 `utils/errors.py`
2. 定义领域异常类
3. 修改关键模块使用分级异常
4. 实现降级策略

---

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `src/quangan/utils/logger.py` | 新建，日志配置 |
| `src/quangan/agent/agent.py` | 添加日志，移除静默失败 |
| `src/quangan/memory/tools.py` | 添加日志 |
| `src/quangan/cli/main.py` | 初始化 logger |
| `src/quangan/llm/retry.py` | 新建，重试机制 |
| `src/quangan/llm/client.py` | 添加重试装饰器 |
| `src/quangan/llm/anthropic_client.py` | 添加重试装饰器 |
| `src/quangan/utils/errors.py` | 新建，错误分级定义 |
| `.gitignore` | 添加 .logs/ |

