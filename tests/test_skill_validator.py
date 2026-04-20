"""Tests for skills/validator.py - skill-tool dependency validation."""

from quangan.skills.models import Skill, SkillMetadata
from quangan.skills.validator import SkillValidator


def _make_skill(name: str, tools: list[str]) -> Skill:
    """Helper to create a Skill with specified tools."""
    metadata = SkillMetadata(
        name=name,
        description=f"Test skill {name}",
        version="1.0.0",
        priority=5,
        tags=["test"],
        triggers=["test"],
        tools=tools,
    )
    return Skill(metadata=metadata, content="Test content", file_path="/tmp/test/SKILL.md")


class TestSkillValidator:
    """Test SkillValidator class."""

    def test_all_tools_present(self):
        """Normal: skill with all tools registered passes."""
        validator = SkillValidator({"read_file", "write_file"})
        skill = _make_skill("test", ["read_file", "write_file"])
        assert validator.validate(skill) == []

    def test_missing_tool_detected(self):
        """Normal: missing tool is reported."""
        validator = SkillValidator({"read_file"})
        skill = _make_skill("test", ["read_file", "missing_tool"])
        missing = validator.validate(skill)
        assert "missing_tool" in missing
        assert "read_file" not in missing

    def test_empty_tools_passes(self):
        """Edge: skill with no tools always passes."""
        validator = SkillValidator({"read_file"})
        skill = _make_skill("test", [])
        assert validator.validate(skill) == []

    def test_empty_registry(self):
        """Edge: empty registry means all tools are missing."""
        validator = SkillValidator(set())
        skill = _make_skill("test", ["tool_a"])
        assert validator.validate(skill) == ["tool_a"]

    def test_validate_all_returns_only_issues(self):
        """Normal: validate_all only includes skills with problems."""
        validator = SkillValidator({"read_file"})
        skills = {
            "good": _make_skill("good", ["read_file"]),
            "bad": _make_skill("bad", ["missing"]),
        }
        issues = validator.validate_all(skills)
        assert "good" not in issues
        assert "bad" in issues
        assert "missing" in issues["bad"]

    def test_validate_all_empty_on_success(self):
        """Normal: returns empty dict when all valid."""
        validator = SkillValidator({"a", "b"})
        skills = {
            "s1": _make_skill("s1", ["a"]),
            "s2": _make_skill("s2", ["b"]),
        }
        assert validator.validate_all(skills) == {}
