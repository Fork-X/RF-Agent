"""
统一日志配置模块。

为整个项目提供零依赖的结构化日志支持：
- 控制台默认仅输出 ERROR 及以上，可通过环境变量 `QUANGAN_LOG_LEVEL` 覆盖
- 文件按日切割，保留最近 7 天，记录 DEBUG 及以上

使用方式：
    from quangan.utils.logger import get_logger
    logger = get_logger("agent")
    logger.info("Something happened")
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def setup_logging(
    name: str = "quangan",
    log_dir: str = ".logs",
    file_level: int = logging.DEBUG,
) -> logging.Logger:
    """
    配置应用全局日志。

    Args:
        name: 日志命名空间，默认 "quangan"。
        log_dir: 日志文件存放目录，默认项目根目录下的 `.logs/`。
        file_level: 文件日志级别，建议保持 DEBUG。

    Returns:
        配置好的 Logger 实例；重复调用会返回同一实例，避免重复添加 Handler。
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 控制台级别：默认 ERROR，可通过环境变量覆盖
    console_level_name = os.environ.get("QUANGAN_LOG_LEVEL", "ERROR").upper()
    console_level = getattr(logging, console_level_name, logging.ERROR)

    # 文件格式：带时间戳，便于按时间线追踪
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 控制台格式：精简，只保留级别与消息
    console_formatter = logging.Formatter("%(levelname)s: %(message)s")

    # 文件 Handler：按日切割，保留最近 7 天
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fh = TimedRotatingFileHandler(
        f"{log_dir}/{name}.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    fh.setLevel(file_level)
    fh.setFormatter(file_formatter)
    logger.addHandler(fh)

    # 控制台 Handler
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(console_level)
    ch.setFormatter(console_formatter)
    logger.addHandler(ch)

    return logger


def get_logger(suffix: str | None = None) -> logging.Logger:
    """
    获取项目内的统一 Logger。

    Args:
        suffix: 子模块后缀，例如 "agent"、"llm"、"memory"。
                最终 logger 名称为 "quangan.{suffix}"。

    Returns:
        对应的 logging.Logger 实例。
    """
    name = "quangan" if not suffix else f"quangan.{suffix}"
    return logging.getLogger(name)
