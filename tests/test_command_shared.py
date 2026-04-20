"""Tests for tools/command/_shared.py - command safety checking."""


from quangan.tools.command._shared import BLOCKED_COMMANDS, check_command_safety


class TestBlockedCommands:
    """Test BLOCKED_COMMANDS constant."""

    def test_is_tuple(self):
        """Normal: should be an immutable tuple."""
        assert isinstance(BLOCKED_COMMANDS, tuple)

    def test_contains_common_dangerous_commands(self):
        """Normal: should include common dangerous patterns."""
        dangerous = {"sudo", "shutdown", "reboot", "mkfs"}
        for cmd in dangerous:
            assert cmd in BLOCKED_COMMANDS, f"'{cmd}' should be in BLOCKED_COMMANDS"

    def test_contains_fork_bomb(self):
        """Normal: should block fork bomb pattern."""
        assert ":(){ :|:& };:" in BLOCKED_COMMANDS

    def test_non_empty(self):
        """Normal: should have at least one blocked command."""
        assert len(BLOCKED_COMMANDS) > 0


class TestCheckCommandSafety:
    """Test check_command_safety() function."""

    def test_safe_command_returns_none(self):
        """Normal: safe commands should pass."""
        assert check_command_safety("ls -la") is None
        assert check_command_safety("echo hello") is None
        assert check_command_safety("python script.py") is None

    def test_blocked_command_returns_error(self):
        """Normal: dangerous commands should be blocked."""
        result = check_command_safety("sudo rm -rf /")
        assert result is not None
        assert "❌" in result

    def test_shutdown_blocked(self):
        """Normal: shutdown should be blocked."""
        result = check_command_safety("shutdown -h now")
        assert result is not None
        assert "shutdown" in result

    def test_reboot_blocked(self):
        """Normal: reboot should be blocked."""
        result = check_command_safety("reboot")
        assert result is not None

    def test_mkfs_blocked(self):
        """Normal: mkfs should be blocked."""
        result = check_command_safety("mkfs.ext4 /dev/sda1")
        assert result is not None

    def test_case_insensitive(self):
        """Edge: should check regardless of case."""
        result = check_command_safety("SUDO apt install")
        assert result is not None

    def test_empty_command(self):
        """Edge: empty string should be safe."""
        assert check_command_safety("") is None

    def test_whitespace_command(self):
        """Edge: whitespace-only should be safe."""
        assert check_command_safety("   ") is None

    def test_error_message_format(self):
        """Normal: error message should contain the blocked pattern."""
        result = check_command_safety("sudo ls")
        assert result is not None
        assert "sudo" in result
        assert "❌" in result
