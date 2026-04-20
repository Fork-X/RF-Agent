"""
Config module.

Exports LLM configuration types and functions.
"""

from quangan.config.llm_config import (
    MODEL_CONTEXT_LIMITS,
    PROVIDERS,
    LLMConfig,
    ProviderPreset,
    create_config,
    get_model_context_limit,
    load_config_from_env,
)
from quangan.config.paths import (
    get_env_file,
    get_memory_base_dir,
    get_project_root,
    get_sessions_dir,
)

__all__ = [
    "LLMConfig",
    "ProviderPreset",
    "PROVIDERS",
    "MODEL_CONTEXT_LIMITS",
    "load_config_from_env",
    "create_config",
    "get_model_context_limit",
    # Refactor: [设计缺陷] 统一路径管理函数
    "get_project_root",
    "get_memory_base_dir",
    "get_sessions_dir",
    "get_env_file",
]
