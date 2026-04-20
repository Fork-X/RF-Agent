"""
Exception hierarchy for QuanGan.

Refactor: [设计缺陷] 原异常体系仅3个类型，无法精确捕获工具/技能/配置等错误，
扩展为6个具体异常类型，支持按异常类型精确处理。

Hierarchy:
    QuanganError (根异常)
    ├── LLMError          -- LLM 调用相关错误
    ├── ToolError          -- 工具执行错误
    ├── SkillError         -- 技能加载/解析/执行错误
    ├── QuanganMemoryError -- 记忆读写错误（避免与内置 MemoryError 冲突）
    ├── ConfigError        -- 配置加载/验证错误
    └── ValidationError    -- 输入/输出验证错误
"""

from __future__ import annotations

__all__ = [
    "QuanganError",
    "LLMError",
    "ToolError",
    "SkillError",
    "QuanganMemoryError",
    "ConfigError",
    "ValidationError",
]


class QuanganError(Exception):
    """项目根异常。所有自定义异常均应继承自此基类。"""

    pass


class LLMError(QuanganError):
    """LLM API 调用相关错误。

    Attributes:
        status_code: 若由 HTTP 错误触发，可记录对应状态码；否则为 None。
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# Refactor: [设计缺陷] 新增 ToolError，替代工具模块中的裸 Exception
class ToolError(QuanganError):
    """Tool execution error.

    Raised when a tool fails during execution.

    Attributes:
        tool_name: Name of the failed tool.
        error_code: Machine-readable error code for automated handling.
    """

    def __init__(
        self,
        message: str,
        tool_name: str = "",
        error_code: str = "TOOL_EXEC_ERROR",
    ) -> None:
        self.tool_name = tool_name
        self.error_code = error_code
        prefix = f"[{tool_name}] " if tool_name else ""
        super().__init__(f"{prefix}{message}")


# Refactor: [设计缺陷] 新增 SkillError，替代技能模块中的裸 Exception
class SkillError(QuanganError):
    """Skill loading, parsing or execution error.

    Attributes:
        skill_name: Name of the failed skill.
    """

    def __init__(self, message: str, skill_name: str = "") -> None:
        self.skill_name = skill_name
        prefix = f"[{skill_name}] " if skill_name else ""
        super().__init__(f"{prefix}{message}")


# Refactor: [设计缺陷] 重命名 MemoryError 为 QuanganMemoryError，避免与内置冲突
class QuanganMemoryError(QuanganError):
    """Memory read/write error.

    Named QuanganMemoryError to avoid conflict with built-in MemoryError.
    """

    pass


# Refactor: [设计缺陷] 新增 ConfigError，替代配置模块中的裸 Exception
class ConfigError(QuanganError):
    """Configuration loading or validation error."""

    pass


# Refactor: [设计缺陷] 新增 ValidationError，替代验证相关的裸 Exception
class ValidationError(QuanganError):
    """Input/output validation error."""

    pass
