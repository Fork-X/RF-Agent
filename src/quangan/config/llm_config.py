"""
LLM configuration management.

This module handles:
- Provider presets (dashscope, kimi, kimi-code, openai)
- Configuration loading from environment variables
- Model context limits
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv

from quangan.config.paths import get_env_file

# Refactor: [设计缺陷] 消除硬编码路径依赖
_ENV_FILE = get_env_file()
load_dotenv(_ENV_FILE)


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ProviderPreset:
    """Preset configuration for an LLM provider."""

    base_url: str
    default_model: str
    headers: dict[str, str] | None = None
    protocol: Literal["openai", "anthropic"] = "openai"


@dataclass
class LLMConfig:
    """
    Complete configuration for an LLM client.

    Attributes:
        provider: Provider identifier (e.g., 'dashscope', 'kimi', 'openai')
        api_key: API key for authentication
        base_url: Base URL for API calls
        model: Model name to use
        headers: Optional additional headers
        protocol: API protocol ('openai' or 'anthropic')
        timeout_seconds: HTTP request timeout in seconds
        max_retries: Maximum number of retry attempts
        retry_status_codes: HTTP status codes that trigger a retry
    """

    provider: str
    api_key: str
    base_url: str
    model: str
    headers: dict[str, str] | None = None
    protocol: Literal["openai", "anthropic"] = "openai"
    # Refactor: [可维护性] 添加可配置超时和重试参数，消除硬编码
    timeout_seconds: int = 120
    max_retries: int = 2
    retry_status_codes: tuple[int, ...] = (429, 500, 502, 503)


# ─────────────────────────────────────────────────────────────────────────────
# Provider presets
# ─────────────────────────────────────────────────────────────────────────────

PROVIDERS: dict[str, ProviderPreset] = {
    "dashscope": ProviderPreset(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen-plus",
    ),
    "kimi": ProviderPreset(
        base_url="https://api.moonshot.cn/v1",
        default_model="kimi-k2.5",
    ),
    "kimi-code": ProviderPreset(
        base_url="https://api.kimi.com/coding/v1",
        default_model="k2p5",
        headers={"User-Agent": "claude-code/0.1.0"},
        protocol="anthropic",
    ),
    "openai": ProviderPreset(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# Model context limits
# ─────────────────────────────────────────────────────────────────────────────

MODEL_CONTEXT_LIMITS: dict[str, int] = {
    # DashScope / 百炼
    "qwen3.5-plus": 1_000_000,
    "qwen-turbo": 1_000_000,
    "qwen-long": 10_000_000,
    "qwen-plus": 131_072,
    "qwen-max": 32_768,
    "qwen-max-longcontext": 28_672,
    # Kimi
    "k2p5": 262_144,
    "kimi-k2-thinking": 262_144,
    "kimi-k2.5": 256_000,
    "kimi-k2-turbo-preview": 256_000,
    "kimi-for-coding": 256_000,
    "moonshot-v1-8k": 8_192,
    "moonshot-v1-32k": 32_768,
    "moonshot-v1-128k": 128_000,
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
}


def get_model_context_limit(model: str) -> int:
    """Get context window size for a model.

    Refactor: [设计缺陷] 原前缀匹配可能匹配到错误的短前缀（如 'qwen' 匹配 'qwen-max-longcontext'），
    改为最长前缀匹配算法。

    Args:
        model: Model name string.

    Returns:
        Context window size in tokens.
    """
    # 精确匹配优先
    if model in MODEL_CONTEXT_LIMITS:
        return MODEL_CONTEXT_LIMITS[model]

    # 最长前缀匹配
    best_match = ""
    best_limit = 128_000  # 默认值
    for key, limit in MODEL_CONTEXT_LIMITS.items():
        if model.startswith(key) and len(key) > len(best_match):
            best_match = key
            best_limit = limit

    return best_limit


# ─────────────────────────────────────────────────────────────────────────────
# Configuration loading
# ─────────────────────────────────────────────────────────────────────────────


def load_config_from_env() -> LLMConfig:
    """
    Load LLM configuration from environment variables.

    Uses LLM_PROVIDER to select the provider (default: dashscope).
    Each provider's settings use a prefix convention:
    - DASHSCOPE_API_KEY, DASHSCOPE_MODEL, DASHSCOPE_BASE_URL
    - KIMI_API_KEY, KIMI_MODEL, KIMI_BASE_URL
    - KIMI_CODE_API_KEY, KIMI_CODE_MODEL, KIMI_CODE_BASE_URL
    - OPENAI_API_KEY, OPENAI_MODEL, OPENAI_BASE_URL

    Returns:
        LLMConfig with loaded settings
    """
    provider = os.environ.get("LLM_PROVIDER", "dashscope").lower()
    preset = PROVIDERS.get(provider, PROVIDERS["dashscope"])

    # Convert provider name to env var prefix (e.g., "kimi-code" -> "KIMI_CODE")
    prefix = provider.replace("-", "_").upper()

    return LLMConfig(
        provider=provider,
        api_key=os.environ.get(f"{prefix}_API_KEY", os.environ.get("DASHSCOPE_API_KEY", "")),
        base_url=os.environ.get(f"{prefix}_BASE_URL", preset.base_url),
        model=os.environ.get(f"{prefix}_MODEL", preset.default_model),
        headers=preset.headers,
        protocol=preset.protocol,
    )


def create_config(
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    provider: str = "dashscope",
) -> LLMConfig:
    """
    Manually create an LLM configuration.

    Args:
        api_key: API key for authentication
        model: Model name (uses provider default if not specified)
        base_url: Base URL (uses provider default if not specified)
        provider: Provider identifier

    Returns:
        LLMConfig with specified settings
    """
    preset = PROVIDERS.get(provider, PROVIDERS["dashscope"])

    return LLMConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url or preset.base_url,
        model=model or preset.default_model,
        headers=preset.headers,
        protocol=preset.protocol,
    )
