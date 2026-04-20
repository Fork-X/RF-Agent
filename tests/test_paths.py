"""Tests for config/paths.py - project path resolution."""
from pathlib import Path


class TestGetProjectRoot:
    """Test get_project_root() function."""

    def test_returns_path_with_pyproject(self):
        """Normal: should find project root containing pyproject.toml."""
        from quangan.config.paths import get_project_root
        root = get_project_root()
        assert (root / "pyproject.toml").exists()

    def test_returns_path_object(self):
        """Normal: return type should be Path."""
        from quangan.config.paths import get_project_root
        assert isinstance(get_project_root(), Path)

    def test_cached_result(self):
        """Normal: repeated calls return same object (lru_cache)."""
        from quangan.config.paths import get_project_root
        assert get_project_root() is get_project_root()


class TestGetMemoryBaseDir:
    """Test get_memory_base_dir() function."""

    def test_returns_memory_dir(self):
        """Normal: should return .memory under project root."""
        from quangan.config.paths import get_memory_base_dir
        mem_dir = get_memory_base_dir()
        assert mem_dir.name == ".memory"
        assert mem_dir.exists()

    def test_creates_directory(self):
        """Normal: directory should exist after call."""
        from quangan.config.paths import get_memory_base_dir
        assert get_memory_base_dir().is_dir()


class TestGetSessionsDir:
    """Test get_sessions_dir() function."""

    def test_returns_sessions_dir(self):
        """Normal: should return .sessions under project root."""
        from quangan.config.paths import get_sessions_dir
        sess_dir = get_sessions_dir()
        assert sess_dir.name == ".sessions"


class TestGetEnvFile:
    """Test get_env_file() function."""

    def test_returns_env_path(self):
        """Normal: should return .env under project root."""
        from quangan.config.paths import get_env_file
        env = get_env_file()
        assert env.name == ".env"
