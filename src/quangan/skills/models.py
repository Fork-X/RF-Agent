"""
Skill data models.

Defines the data structures for representing Skills loaded from Markdown files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillMetadata:
    """
    Metadata for a Skill, parsed from YAML frontmatter.
    
    Attributes:
        name: Unique identifier for the skill
        description: Human-readable description of what the skill does
        version: Skill version (default: "1.0.0")
        author: Skill author (optional)
        tags: List of tags for categorization (optional)
        triggers: Keywords that trigger this skill (optional)
    """
    
    name: str
    description: str
    version: str = "1.0.0"
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "tags": self.tags,
            "triggers": self.triggers,
        }


@dataclass
class Skill:
    """
    A complete Skill definition loaded from a Markdown file.
    
    A Skill consists of:
    - Metadata (from YAML frontmatter)
    - Content (the Markdown body, used as system prompt enhancement)
    - File path (source location)
    
    Attributes:
        metadata: Parsed metadata from frontmatter
        content: Markdown content (without frontmatter)
        file_path: Absolute path to the source file
    """
    
    metadata: SkillMetadata
    content: str
    file_path: str
    
    @property
    def name(self) -> str:
        """Get skill name from metadata."""
        return self.metadata.name
    
    @property
    def description(self) -> str:
        """Get skill description from metadata."""
        return self.metadata.description
    
    def should_trigger(self, message: str) -> bool:
        """
        Check if this skill should be triggered by a user message.
        
        Args:
            message: The user's input message
            
        Returns:
            True if any trigger keyword is found in the message
        """
        message_lower = message.lower()
        for trigger in self.metadata.triggers:
            if trigger.lower() in message_lower:
                return True
        return False
    
    def to_system_prompt(self) -> str:
        """
        Generate a system prompt enhancement from this skill.
        
        Returns:
            Formatted skill content for injection into system prompt
        """
        lines = [
            f"## Skill: {self.metadata.name}",
            f"",
            f"{self.metadata.description}",
            f"",
            self.content,
        ]
        return "\n".join(lines)
