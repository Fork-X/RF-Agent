"""
Skill parser for Markdown files with YAML frontmatter.

Parses SKILL.md files into Skill objects.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .models import Skill, SkillMetadata


class SkillParseError(Exception):
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
    triggers:
      - keyword1
      - keyword2
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
        
        # Parse YAML frontmatter manually (simple parser, no external deps)
        metadata = cls._parse_yaml(yaml_content)
        
        # Validate required fields
        if 'name' not in metadata:
            raise SkillParseError("Missing required field 'name' in skill frontmatter")
        if 'description' not in metadata:
            raise SkillParseError("Missing required field 'description' in skill frontmatter")
        
        # Build SkillMetadata
        skill_metadata = SkillMetadata(
            name=metadata['name'],
            description=metadata['description'],
            version=metadata.get('version', '1.0.0'),
            author=metadata.get('author'),
            tags=cls._parse_list(metadata.get('tags', [])),
            triggers=cls._parse_list(metadata.get('triggers', [])),
        )
        
        return Skill(
            metadata=skill_metadata,
            content=markdown_content,
            file_path=file_path,
        )
    
    @classmethod
    def _parse_yaml(cls, yaml_str: str) -> dict[str, Any]:
        """
        Simple YAML parser for skill frontmatter.
        
        Supports:
        - key: value (strings, numbers, booleans)
        - key:
          - item1
          - item2 (lists)
        
        Args:
            yaml_str: YAML content string
            
        Returns:
            Dictionary of parsed values
        """
        result: dict[str, Any] = {}
        lines = yaml_str.split('\n')
        current_key: str | None = None
        current_list: list[str] = []
        
        for line in lines:
            stripped = line.rstrip()
            
            # Skip empty lines
            if not stripped:
                continue
            
            # Check if this is a list item
            if stripped.startswith('- '):
                if current_key is not None:
                    item = stripped[2:].strip()
                    # Remove quotes if present
                    if (item.startswith('"') and item.endswith('"')) or \
                       (item.startswith("'") and item.endswith("'")):
                        item = item[1:-1]
                    current_list.append(item)
                continue
            
            # If we were building a list, save it
            if current_key is not None and current_list:
                result[current_key] = current_list
                current_list = []
            
            # Parse key: value
            if ':' in stripped:
                # Split only on first colon
                colon_idx = stripped.index(':')
                key = stripped[:colon_idx].strip()
                value = stripped[colon_idx + 1:].strip()
                
                current_key = key
                
                # Empty value means this might be a list
                if not value:
                    current_list = []
                    continue
                
                # Parse value
                parsed_value = cls._parse_value(value)
                result[key] = parsed_value
        
        # Don't forget the last list
        if current_key is not None and current_list:
            result[current_key] = current_list
        
        return result
    
    @classmethod
    def _parse_value(cls, value: str) -> str | int | float | bool | None:
        """
        Parse a YAML value into appropriate Python type.
        
        Args:
            value: String value from YAML
            
        Returns:
            Parsed value
        """
        value = value.strip()
        
        # Remove quotes
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and item.endswith("'")):
            value = value[1:-1]
        
        # Boolean
        if value.lower() in ('true', 'yes', 'on'):
            return True
        if value.lower() in ('false', 'no', 'off'):
            return False
        
        # Null
        if value.lower() in ('null', '~', ''):
            return None
        
        # Integer
        try:
            return int(value)
        except ValueError:
            pass
        
        # Float
        try:
            return float(value)
        except ValueError:
            pass
        
        # String (default)
        return value
    
    @classmethod
    def _parse_list(cls, value: Any) -> list[str]:
        """
        Ensure value is a list of strings.
        
        Args:
            value: Any value (list, string, or None)
            
        Returns:
            List of strings
        """
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            # Handle comma-separated string
            return [item.strip() for item in value.split(',')]
        return [str(value)]
