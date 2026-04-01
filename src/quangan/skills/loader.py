"""
Skill loader for discovering and loading skills from directories.

Scans skill directories and loads all valid SKILL.md files.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from .models import Skill
from .parser import SkillParser, SkillParseError


# Default skill search paths (in order of priority)
DEFAULT_SKILL_PATHS = [
    # Project-level skills (highest priority)
    ".qoder/skills",
    "skills",
    # User-level skills
    "~/.config/quangan/skills",
]


class SkillLoader:
    """
    Loader for discovering and loading skills from the filesystem.
    
    Searches for SKILL.md files in configured directories and parses them
    into Skill objects.
    
    Example:
        loader = SkillLoader()
        skills = loader.load_all()
        
        # Or with custom paths
        loader = SkillLoader(["./my-skills", "~/.quangan/skills"])
        skills = loader.load_all()
    """
    
    def __init__(self, search_paths: list[str] | None = None):
        """
        Initialize the skill loader.
        
        Args:
            search_paths: List of directories to search for skills.
                         If None, uses DEFAULT_SKILL_PATHS.
        """
        self.search_paths = search_paths or DEFAULT_SKILL_PATHS
        self._skills: dict[str, Skill] = {}
        self._load_errors: list[tuple[str, str]] = []
    
    def load_all(self, force_reload: bool = False) -> dict[str, Skill]:
        """
        Load all skills from search paths.
        
        Args:
            force_reload: If True, reload even if already loaded
            
        Returns:
            Dictionary mapping skill names to Skill objects
        """
        if self._skills and not force_reload:
            return dict(self._skills)
        
        self._skills = {}
        self._load_errors = []
        
        for path_str in self.search_paths:
            path = self._resolve_path(path_str)
            if path.exists() and path.is_dir():
                self._load_from_directory(path)
        
        return dict(self._skills)
    
    def load_skill(self, file_path: str | Path) -> Skill | None:
        """
        Load a single skill from a file.
        
        Args:
            file_path: Path to the SKILL.md file
            
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
    
    def _resolve_path(self, path_str: str) -> Path:
        """
        Resolve a path string to an absolute Path.
        
        Handles:
        - ~ (home directory expansion)
        - Relative paths (resolved from cwd)
        
        Args:
            path_str: Path string
            
        Returns:
            Resolved Path object
        """
        expanded = os.path.expanduser(path_str)
        return Path(expanded).absolute()
    
    def _load_from_directory(self, directory: Path) -> None:
        """
        Load all skills from a directory.
        
        Recursively searches for SKILL.md files.
        
        Args:
            directory: Directory to search
        """
        for skill_file in self._find_skill_files(directory):
            try:
                skill = SkillParser.parse_file(skill_file)
                if skill.name in self._skills:
                    # Duplicate skill name - use the first one (higher priority)
                    continue
                self._skills[skill.name] = skill
            except (SkillParseError, FileNotFoundError) as e:
                self._load_errors.append((str(skill_file), str(e)))
    
    def _find_skill_files(self, directory: Path) -> Iterator[Path]:
        """
        Find all skill files in a directory.
        
        Searches for:
        - SKILL.md (case-insensitive)
        - skill.md
        - Any .md file in skill directories
        
        Args:
            directory: Directory to search
            
        Yields:
            Path objects for skill files
        """
        if not directory.exists():
            return
        
        # Look for SKILL.md files
        for pattern in ["**/SKILL.md", "**/skill.md", "**/*.skill.md"]:
            yield from directory.glob(pattern)


def get_default_loader() -> SkillLoader:
    """
    Get the default skill loader with standard search paths.
    
    Returns:
        SkillLoader instance with default configuration
    """
    return SkillLoader()
