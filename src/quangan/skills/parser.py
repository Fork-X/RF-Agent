"""
Skill parser for Markdown files with YAML frontmatter.

Parses SKILL.md files into Skill objects.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from quangan.utils.errors import SkillError

from .models import Skill, SkillMetadata


# Refactor: [设计缺陷] 让 SkillParseError 继承 SkillError，统一异常体系
class SkillParseError(SkillError):
    """Raised when a skill file cannot be parsed."""
    pass


class SkillParser:
    """
    Parser for Skill Markdown files.

    Skill files use YAML frontmatter format:
    ```markdown
    ---
    name: skill-name
    description: Skill description
    version: 1.0.0
    priority: 10
    triggers:
      - keyword1
      - keyword2
    tools:
      - tool1
      - tool2
    ---

    # Skill Content

    Markdown content here...
    ```
    """

    # Regex to match YAML frontmatter
    FRONTMATTER_PATTERN = re.compile(
        r'^---\s*\n(.*?)\n---\s*\n(.*)$',
        re.DOTALL | re.MULTILINE
    )

    @classmethod
    def parse_file(cls, file_path: str | Path) -> Skill:
        """
        Parse a Skill from a Markdown file.

        Args:
            file_path: Path to the SKILL.md file

        Returns:
            Parsed Skill object

        Raises:
            SkillParseError: If the file cannot be parsed
            FileNotFoundError: If the file does not exist
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Skill file not found: {file_path}")

        content = path.read_text(encoding='utf-8')
        return cls.parse_content(content, str(path.absolute()))

    @classmethod
    def parse_content(cls, content: str, file_path: str = "") -> Skill:
        """
        Parse a Skill from Markdown content string.

        Args:
            content: The Markdown content with YAML frontmatter
            file_path: Optional file path for reference

        Returns:
            Parsed Skill object

        Raises:
            SkillParseError: If the content cannot be parsed
        """
        match = cls.FRONTMATTER_PATTERN.match(content)

        if not match:
            raise SkillParseError(
                "Invalid skill format: missing or malformed YAML frontmatter. "
                "Expected format: ---\nname: ...\n---\ncontent"
            )

        yaml_content = match.group(1).strip()
        markdown_content = match.group(2).strip()

        try:
            metadata = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError as e:
            raise SkillParseError(f"YAML parse error: {e}") from e

        if not isinstance(metadata, dict):
            raise SkillParseError("Frontmatter must be a YAML mapping")

        # Validate required fields
        if 'name' not in metadata:
            raise SkillParseError("Missing required field 'name'")
        if 'description' not in metadata:
            raise SkillParseError("Missing required field 'description'")

        # Helper function to ensure list[str]
        def ensure_str_list(val) -> list[str]:
            if val is None:
                return []
            if isinstance(val, list):
                return [str(item) for item in val]
            if isinstance(val, str):
                return [item.strip() for item in val.split(',')]
            return [str(val)]

        # Build SkillMetadata
        skill_metadata = SkillMetadata(
            name=metadata['name'],
            description=metadata['description'],
            version=str(metadata.get('version', '1.0.0')),
            priority=int(metadata.get('priority', 0)),
            tags=ensure_str_list(metadata.get('tags')),
            triggers=ensure_str_list(metadata.get('triggers')),
            tools=ensure_str_list(metadata.get('tools')),
        )

        return Skill(
            metadata=skill_metadata,
            content=markdown_content,
            file_path=file_path,
        )
