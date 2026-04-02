"""
Skill loader for discovering and loading skills from a directory.

Recursively scans a skills directory and loads all valid .md skill files.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from .models import Skill
from .parser import SkillParseError, SkillParser


class SkillLoader:
    """
    Loader for discovering and loading skills from the filesystem.

    Recursively searches for .md files in the configured skills directory
    and parses them into Skill objects.

    Example:
        loader = SkillLoader(".skills")
        skills = loader.load_all()

        # Or with custom directory
        loader = SkillLoader("/path/to/my-skills")
        skills = loader.load_all()
    """

    def __init__(self, skills_dir: str | Path = ".skills"):
        """
        Initialize the skill loader.

        Args:
            skills_dir: Directory to search for skills. Default: ".skills"
        """
        self.skills_dir = Path(skills_dir).absolute()
        self._skills: dict[str, Skill] = {}
        self._load_errors: list[tuple[str, str]] = []

    def _find_skill_files(self) -> Iterator[Path]:
        """
        Recursively find all skill files in the skills directory.

        Yields:
            Path objects for SKILL.md files found in skills_dir
        """
        if self.skills_dir.exists():
            yield from self.skills_dir.rglob("SKILL.md")

    def load_all(self, force_reload: bool = False) -> dict[str, Skill]:
        """
        Load all skills from the skills directory.

        Args:
            force_reload: If True, reload even if already loaded

        Returns:
            Dictionary mapping skill names to Skill objects
        """
        if self._skills and not force_reload:
            return dict(self._skills)

        self._skills = {}
        self._load_errors = []

        for skill_file in self._find_skill_files():
            try:
                skill = SkillParser.parse_file(skill_file)
                if skill.name not in self._skills:
                    self._skills[skill.name] = skill
            except (SkillParseError, FileNotFoundError) as e:
                self._load_errors.append((str(skill_file), str(e)))

        return dict(self._skills)

    def load_skill(self, file_path: str | Path) -> Skill | None:
        """
        Load a single skill from a file.

        Args:
            file_path: Path to the skill .md file

        Returns:
            Loaded Skill or None if parsing failed
        """
        try:
            skill = SkillParser.parse_file(file_path)
            self._skills[skill.name] = skill
            return skill
        except (SkillParseError, FileNotFoundError) as e:
            self._load_errors.append((str(file_path), str(e)))
            return None

    def get_skill(self, name: str) -> Skill | None:
        """
        Get a loaded skill by name.

        Args:
            name: Skill name

        Returns:
            Skill object or None if not found
        """
        return self._skills.get(name)

    def find_triggered_skills(self, message: str) -> list[Skill]:
        """
        Find all skills that should be triggered by a message.

        Args:
            message: User input message

        Returns:
            List of triggered skills (may be empty)
        """
        triggered = []
        for skill in self._skills.values():
            if skill.should_trigger(message):
                triggered.append(skill)
        return triggered

    def list_skills(self) -> list[Skill]:
        """
        Get a list of all loaded skills.

        Returns:
            List of Skill objects
        """
        return list(self._skills.values())

    def get_errors(self) -> list[tuple[str, str]]:
        """
        Get list of errors that occurred during loading.

        Returns:
            List of (path, error_message) tuples
        """
        return list(self._load_errors)
