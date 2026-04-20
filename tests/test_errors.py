"""Tests for utils/errors.py - exception hierarchy."""

from __future__ import annotations

import builtins

import pytest

from quangan.utils.errors import (
    ConfigError,
    LLMError,
    QuanganError,
    QuanganMemoryError,
    SkillError,
    ToolError,
    ValidationError,
)

# Reference to built-in MemoryError for test clarity
_BuiltinMemoryError = builtins.MemoryError


class TestExceptionHierarchy:
    """Test all custom exceptions inherit from QuanganError."""

    def test_llm_error_is_quangan_error(self) -> None:
        assert issubclass(LLMError, QuanganError)

    def test_tool_error_is_quangan_error(self) -> None:
        assert issubclass(ToolError, QuanganError)

    def test_skill_error_is_quangan_error(self) -> None:
        assert issubclass(SkillError, QuanganError)

    def test_memory_error_is_quangan_error(self) -> None:
        assert issubclass(QuanganMemoryError, QuanganError)

    def test_config_error_is_quangan_error(self) -> None:
        assert issubclass(ConfigError, QuanganError)

    def test_validation_error_is_quangan_error(self) -> None:
        assert issubclass(ValidationError, QuanganError)


class TestToolError:
    """Test ToolError attributes and formatting."""

    def test_with_tool_name(self) -> None:
        err = ToolError("file not found", tool_name="read_file")
        assert err.tool_name == "read_file"
        assert err.error_code == "TOOL_EXEC_ERROR"
        assert "[read_file]" in str(err)

    def test_with_custom_error_code(self) -> None:
        err = ToolError("timeout", tool_name="cmd", error_code="TIMEOUT")
        assert err.error_code == "TIMEOUT"

    def test_without_tool_name(self) -> None:
        err = ToolError("generic error")
        assert err.tool_name == ""
        assert "generic error" in str(err)

    def test_catch_as_quangan_error(self) -> None:
        with pytest.raises(QuanganError):
            raise ToolError("test", tool_name="test_tool")


class TestSkillError:
    """Test SkillError attributes."""

    def test_with_skill_name(self) -> None:
        err = SkillError("parse failed", skill_name="music-player")
        assert err.skill_name == "music-player"
        assert "[music-player]" in str(err)

    def test_without_skill_name(self) -> None:
        err = SkillError("generic")
        assert err.skill_name == ""

    def test_skill_parse_error_is_skill_error(self) -> None:
        """Verify SkillParseError inherits from SkillError."""
        from quangan.skills.parser import SkillParseError

        assert issubclass(SkillParseError, SkillError)
        assert issubclass(SkillParseError, QuanganError)


class TestLLMError:
    """Test existing LLMError still works."""

    def test_basic(self) -> None:
        err = LLMError("API error")
        assert isinstance(err, QuanganError)
        assert str(err) == "API error"

    def test_has_status_code(self) -> None:
        """Verify LLMError retains status_code attribute."""
        err = LLMError("API error", status_code=429)
        assert err.status_code == 429
        assert isinstance(err, QuanganError)

    def test_status_code_default_none(self) -> None:
        err = LLMError("fail")
        assert err.status_code is None


class TestQuanganMemoryError:
    """Test QuanganMemoryError does not conflict with built-in MemoryError."""

    def test_not_builtin_memory_error(self) -> None:
        assert not issubclass(QuanganMemoryError, _BuiltinMemoryError)

    def test_catch_as_quangan_error(self) -> None:
        with pytest.raises(QuanganError):
            raise QuanganMemoryError("store failed")

