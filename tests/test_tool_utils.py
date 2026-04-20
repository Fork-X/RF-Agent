"""Tests for tools/utils.py - shared tool utilities."""
from pathlib import Path

from quangan.tools.utils import (
    format_tool_error,
    normalize_path,
    validate_directory_exists,
    validate_file_exists,
)


class TestNormalizePath:
    """Test normalize_path() function."""

    def test_absolute_path(self):
        """Normal: absolute path stays absolute."""
        result = normalize_path("/tmp/test.py")
        assert result.is_absolute()

    def test_tilde_expansion(self):
        """Normal: ~ gets expanded to home directory."""
        result = normalize_path("~/test.py")
        assert "~" not in str(result)

    def test_returns_path_object(self):
        """Normal: returns Path instance."""
        assert isinstance(normalize_path("test.py"), Path)

    def test_resolves_relative(self):
        """Normal: relative paths get resolved."""
        result = normalize_path("./test.py")
        assert result.is_absolute()


class TestValidateFileExists:
    """Test validate_file_exists() function."""

    def test_existing_file_returns_none(self, tmp_path):
        """Normal: existing file passes validation."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert validate_file_exists(f) is None

    def test_nonexistent_returns_error(self, tmp_path):
        """Normal: missing file returns error."""
        result = validate_file_exists(tmp_path / "nope.txt")
        assert result is not None
        assert "不存在" in result

    def test_directory_returns_error(self, tmp_path):
        """Edge: directory is not a file."""
        result = validate_file_exists(tmp_path)
        assert result is not None
        assert "不是文件" in result


class TestValidateDirectoryExists:
    """Test validate_directory_exists() function."""

    def test_existing_dir_returns_none(self, tmp_path):
        """Normal: existing dir passes validation."""
        assert validate_directory_exists(tmp_path) is None

    def test_nonexistent_returns_error(self, tmp_path):
        """Normal: missing dir returns error."""
        result = validate_directory_exists(tmp_path / "nope")
        assert result is not None
        assert "不存在" in result

    def test_file_returns_error(self, tmp_path):
        """Edge: file is not a directory."""
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = validate_directory_exists(f)
        assert result is not None
        assert "不是目录" in result


class TestFormatToolError:
    """Test format_tool_error() function."""

    def test_format(self):
        """Normal: includes tool name and error message."""
        result = format_tool_error("read_file", ValueError("bad input"))
        assert "read_file" in result
        assert "bad input" in result
        assert "❌" in result
