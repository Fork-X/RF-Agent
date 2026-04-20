"""Tests for async_main initialization functions (Task #9).

Covers the independent init functions extracted from async_main().
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from quangan.cli.context import CLIContext

# ---------------------------------------------------------------------------
# _init_config
# ---------------------------------------------------------------------------


class TestInitConfig:
    """Test _init_config returns a valid LLMConfig."""

    @patch("quangan.cli.main.load_config_from_env")
    def test_init_config_returns_valid_config(self, mock_load):
        """Normal: _init_config delegates to load_config_from_env and returns result."""
        from quangan.cli.main import _init_config

        fake_config = MagicMock()
        fake_config.provider = "dashscope"
        fake_config.model = "qwen-test"
        mock_load.return_value = fake_config

        result = _init_config()
        assert result is fake_config
        mock_load.assert_called_once()

    @patch("quangan.cli.main.load_config_from_env")
    def test_init_config_has_provider(self, mock_load):
        """Normal: returned config has a provider attribute."""
        from quangan.cli.main import _init_config

        fake_config = MagicMock()
        fake_config.provider = "kimi"
        mock_load.return_value = fake_config

        config = _init_config()
        assert config.provider == "kimi"


# ---------------------------------------------------------------------------
# _init_client
# ---------------------------------------------------------------------------


class TestInitClient:
    """Test _init_client creates an LLM client."""

    @patch("quangan.cli.main.create_llm_client")
    def test_init_client_delegates(self, mock_create):
        """Normal: _init_client calls create_llm_client with the config."""
        from quangan.cli.main import _init_client

        fake_config = MagicMock()
        fake_client = MagicMock()
        mock_create.return_value = fake_client

        result = _init_client(fake_config)
        assert result is fake_client
        mock_create.assert_called_once_with(fake_config)


# ---------------------------------------------------------------------------
# _load_core_memory
# ---------------------------------------------------------------------------


class TestLoadCoreMemory:
    """Test _load_core_memory builds memory context strings."""

    @patch("quangan.cli.main.get_core_memory")
    def test_load_core_memory_with_no_memory(self, mock_get):
        """Edge: returns empty string when no memories exist."""
        from quangan.cli.main import _load_core_memory

        mock_data = MagicMock()
        mock_data.memories = []
        mock_get.return_value = mock_data

        result = _load_core_memory("/tmp")
        assert result == ""

    @patch("quangan.cli.main.get_core_memory")
    def test_load_core_memory_with_memories(self, mock_get):
        """Normal: returns formatted memory context when memories exist."""
        from quangan.cli.main import _load_core_memory

        mem_item = MagicMock()
        mem_item.reinforce_count = 3
        mem_item.content = "芮枫喜欢Python"
        mock_data = MagicMock()
        mock_data.memories = [mem_item]
        mock_get.return_value = mock_data

        result = _load_core_memory("/tmp")
        assert "核心记忆" in result
        assert "强度:3" in result
        assert "芮枫喜欢Python" in result


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------


class TestBuildSystemPrompt:
    """Test _build_system_prompt constructs a valid prompt."""

    def test_build_system_prompt_contains_required_sections(self):
        """Normal: prompt includes identity, skills, and memory guide sections."""
        from quangan.cli.main import _build_system_prompt

        prompt = _build_system_prompt("/home/test", "")
        assert "小枫" in prompt
        assert "芮枫" in prompt
        assert "coding_agent" in prompt
        assert "daily_agent" in prompt
        assert "recall_memory" in prompt
        assert "/home/test" in prompt

    def test_build_system_prompt_includes_memory_context(self):
        """Normal: memory_context is appended to the prompt."""
        from quangan.cli.main import _build_system_prompt

        memory = "\n\n## 你的核心记忆\n- [强度:5] 测试记忆"
        prompt = _build_system_prompt("/tmp", memory)
        assert "测试记忆" in prompt
        assert "强度:5" in prompt


# ---------------------------------------------------------------------------
# _create_cli_context
# ---------------------------------------------------------------------------


class TestCreateCLIContext:
    """Test _create_cli_context creates a properly populated context."""

    def test_create_cli_context_fields(self):
        """Normal: all fields are correctly assigned."""
        from quangan.cli.main import _create_cli_context

        fake_config = MagicMock()
        fake_client = MagicMock()
        fake_agent = MagicMock()

        ctx = _create_cli_context(fake_config, fake_client, fake_agent, 64000, "/work")
        assert ctx.config is fake_config
        assert ctx.client is fake_client
        assert ctx.agent is fake_agent
        assert ctx.model_max_tokens == 64000
        assert ctx.cwd == "/work"
        assert isinstance(ctx, CLIContext)

    def test_create_cli_context_defaults(self):
        """Normal: optional fields have correct defaults."""
        from quangan.cli.main import _create_cli_context

        ctx = _create_cli_context(None, None, None, 128000, "/tmp")
        assert ctx.is_plan_mode is False
        assert ctx.is_agent_running is False
        assert ctx.life_memory_update_count == 0
        assert ctx.current_spinner is None


# ---------------------------------------------------------------------------
# _register_memory_tools
# ---------------------------------------------------------------------------


class TestRegisterMemoryTools:
    """Test _register_memory_tools registers tools on agent."""

    @patch("quangan.cli.main.create_memory_tools")
    def test_register_memory_tools_calls_register(self, mock_create):
        """Normal: each memory tool is registered via agent.register_tool."""
        from quangan.cli.main import _register_memory_tools

        fake_def = MagicMock()
        fake_impl = MagicMock()
        mock_create.return_value = [(fake_def, fake_impl, True)]

        fake_agent = MagicMock()
        fake_ctx = MagicMock()

        _register_memory_tools(fake_agent, fake_ctx)
        fake_agent.register_tool.assert_called_once_with(fake_def, fake_impl, True)
