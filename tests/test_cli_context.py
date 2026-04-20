"""Tests for cli/context.py - CLI state container."""
from pathlib import Path

from quangan.cli.context import CLIContext


class TestCLIContextCreation:
    """Test CLIContext initialization."""

    def test_required_fields(self):
        """Normal: creating with required fields."""
        ctx = CLIContext(
            config=None,
            client=None,
            agent=None,
            project_root=Path("/tmp"),
        )
        assert ctx.project_root == Path("/tmp")
        assert ctx.config is None

    def test_default_values(self):
        """Normal: default values for optional fields."""
        ctx = CLIContext(
            config=None, client=None, agent=None,
            project_root=Path("/tmp"),
        )
        assert ctx.is_plan_mode is False
        assert ctx.is_agent_running is False
        assert ctx.life_memory_update_count == 0
        assert ctx.model_max_tokens == 128_000
        assert ctx.current_spinner is None


class TestCLIContextMutation:
    """Test CLIContext state changes."""

    def test_toggle_plan_mode(self):
        """Normal: plan mode can be toggled."""
        ctx = CLIContext(
            config=None, client=None, agent=None,
            project_root=Path("/tmp"),
        )
        ctx.is_plan_mode = True
        assert ctx.is_plan_mode is True
        ctx.is_plan_mode = False
        assert ctx.is_plan_mode is False

    def test_agent_running_flag(self):
        """Normal: agent running flag tracks state."""
        ctx = CLIContext(
            config=None, client=None, agent=None,
            project_root=Path("/tmp"),
        )
        ctx.is_agent_running = True
        assert ctx.is_agent_running is True

    def test_update_config_and_client(self):
        """Normal: config and client can be swapped (provider switch)."""
        ctx = CLIContext(
            config="old_config", client="old_client", agent=None,
            project_root=Path("/tmp"),
        )
        ctx.config = "new_config"
        ctx.client = "new_client"
        assert ctx.config == "new_config"
        assert ctx.client == "new_client"

    def test_increment_memory_count(self):
        """Normal: memory update counter increments."""
        ctx = CLIContext(
            config=None, client=None, agent=None,
            project_root=Path("/tmp"),
        )
        ctx.life_memory_update_count += 1
        assert ctx.life_memory_update_count == 1
