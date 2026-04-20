"""Tests for cli/commands.py - slash command handling."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from quangan.cli.context import CLIContext


def _make_ctx() -> CLIContext:
    """Create a minimal CLIContext for testing."""
    agent = MagicMock()
    agent.get_history.return_value = []
    agent.list_skills.return_value = []
    agent.get_active_skills.return_value = []
    agent.clear_history.return_value = None

    config = MagicMock()
    config.model = "test-model"
    config.provider = "test"

    return CLIContext(
        config=config,
        client=MagicMock(),
        agent=agent,
        project_root=Path("/tmp"),
        cwd="/tmp",
    )


class TestHandleCommand:
    """Test handle_command() dispatch."""

    @pytest.mark.asyncio
    async def test_help_command(self) -> None:
        """Normal: /help is recognized and returns True."""
        from quangan.cli.commands import handle_command

        ctx = _make_ctx()
        session = MagicMock()
        with patch("quangan.cli.commands.display") as mock_display:
            result = await handle_command(ctx, "/help", session)
        assert result is True
        mock_display.print_help.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_command_returns_true(self) -> None:
        """Edge: unknown command prints error but returns True."""
        from quangan.cli.commands import handle_command

        ctx = _make_ctx()
        session = MagicMock()
        with patch("quangan.cli.commands.display") as mock_display:
            result = await handle_command(ctx, "/nonexistent", session)
        assert result is True
        mock_display.print_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_command(self) -> None:
        """Normal: /clear clears history and returns True."""
        from quangan.cli.commands import handle_command

        ctx = _make_ctx()
        session = MagicMock()
        with (
            patch("quangan.cli.commands.display") as mock_display,  # noqa: F841
            patch("quangan.cli.commands.console"),
            patch("quangan.cli.commands.clear_session", return_value=None),
        ):
            result = await handle_command(ctx, "/clear", session)
        assert result is True
        ctx.agent.clear_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_history_command(self) -> None:
        """Normal: /history displays history."""
        from quangan.cli.commands import handle_command

        ctx = _make_ctx()
        session = MagicMock()
        with patch("quangan.cli.commands.display") as mock_display:
            result = await handle_command(ctx, "/history", session)
        assert result is True
        mock_display.print_history.assert_called_once()

    @pytest.mark.asyncio
    async def test_plan_command(self) -> None:
        """Normal: /plan enables plan mode."""
        from quangan.cli.commands import handle_command

        ctx = _make_ctx()
        session = MagicMock()
        with patch("quangan.cli.commands.display"):
            result = await handle_command(ctx, "/plan", session)
        assert result is True
        assert ctx.is_plan_mode is True

    @pytest.mark.asyncio
    async def test_exec_command(self) -> None:
        """Normal: /exec disables plan mode."""
        from quangan.cli.commands import handle_command

        ctx = _make_ctx()
        ctx.is_plan_mode = True
        session = MagicMock()
        with patch("quangan.cli.commands.display"):
            result = await handle_command(ctx, "/exec", session)
        assert result is True
        assert ctx.is_plan_mode is False

    @pytest.mark.asyncio
    async def test_skills_command(self) -> None:
        """Normal: /skills lists loaded skills."""
        from quangan.cli.commands import handle_command

        ctx = _make_ctx()
        session = MagicMock()
        with patch("quangan.cli.commands.console"):
            result = await handle_command(ctx, "/skills", session)
        assert result is True
        ctx.agent.list_skills.assert_called_once()

    @pytest.mark.asyncio
    async def test_exit_command(self) -> None:
        """Normal: /exit triggers sys.exit."""
        from quangan.cli.commands import handle_command

        ctx = _make_ctx()
        session = MagicMock()
        with (
            patch("quangan.cli.commands.display"),
            pytest.raises(SystemExit),
        ):
            await handle_command(ctx, "/exit", session)

    @pytest.mark.asyncio
    async def test_quit_command(self) -> None:
        """Normal: /quit triggers sys.exit (alias)."""
        from quangan.cli.commands import handle_command

        ctx = _make_ctx()
        session = MagicMock()
        with (
            patch("quangan.cli.commands.display"),
            pytest.raises(SystemExit),
        ):
            await handle_command(ctx, "/quit", session)


class TestCmdHelp:
    """Test cmd_help individually."""

    @pytest.mark.asyncio
    async def test_cmd_help_returns_true(self) -> None:
        from quangan.cli.commands import cmd_help

        ctx = _make_ctx()
        with patch("quangan.cli.commands.display") as mock_display:
            result = await cmd_help(ctx)
        assert result is True
        mock_display.print_help.assert_called_once()


class TestCmdPlanExec:
    """Test plan/exec mode toggles."""

    @pytest.mark.asyncio
    async def test_cmd_plan_sets_mode(self) -> None:
        from quangan.cli.commands import cmd_plan

        ctx = _make_ctx()
        with patch("quangan.cli.commands.display"):
            result = await cmd_plan(ctx)
        assert result is True
        assert ctx.is_plan_mode is True

    @pytest.mark.asyncio
    async def test_cmd_exec_clears_mode(self) -> None:
        from quangan.cli.commands import cmd_exec

        ctx = _make_ctx()
        ctx.is_plan_mode = True
        with patch("quangan.cli.commands.display"):
            result = await cmd_exec(ctx)
        assert result is True
        assert ctx.is_plan_mode is False


class TestIsValidApiKey:
    """Test is_valid_api_key utility."""

    def test_none_key(self) -> None:
        from quangan.cli.commands import is_valid_api_key

        assert is_valid_api_key(None) is False

    def test_short_key(self) -> None:
        from quangan.cli.commands import is_valid_api_key

        assert is_valid_api_key("abc") is False

    def test_repeated_chars(self) -> None:
        from quangan.cli.commands import is_valid_api_key

        assert is_valid_api_key("a" * 30) is False

    def test_placeholder_key(self) -> None:
        from quangan.cli.commands import is_valid_api_key

        assert is_valid_api_key("your_api_key_placeholder_here") is False

    def test_valid_key(self) -> None:
        from quangan.cli.commands import is_valid_api_key

        assert is_valid_api_key("sk-proj-abc123def456ghi789") is True
