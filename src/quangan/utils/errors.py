"""
项目级领域异常定义。

提供最小化的异常层次结构，使关键错误在日志和后续监控中具备可识别性。
当前以占位形式保留，为后续扩展（如错误分级、降级策略）预留基座。
"""

from __future__ import annotations


class QuanganError(Exception):
    """项目根异常。所有自定义异常均应继承自此基类。"""

    pass


class LLMError(QuanganError):
    """
    LLM API 调用相关错误。

    Attributes:
        status_code: 若由 HTTP 错误触发，可记录对应状态码；否则为 None。
    """

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class MemoryError(QuanganError):
    """记忆存储（Core / Life Memory）相关错误。"""

    pass
