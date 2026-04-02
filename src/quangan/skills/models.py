"""
Skill data models.

Defines the data structures for representing Skills loaded from Markdown files.
"""

from __future__ import annotations

import re
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
        priority: Priority level, higher values take precedence (default: 0)
        tags: List of tags for categorization (optional)
        triggers: Keywords that trigger this skill (optional)
        tools: List of tools available for this skill (optional)
    """

    name: str
    description: str
    version: str = "1.0.0"
    priority: int = 0
    tags: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "priority": self.priority,
            "tags": self.tags,
            "triggers": self.triggers,
            "tools": self.tools,
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

    @staticmethod
    def _is_ascii(text: str) -> bool:
        """Check if text contains only ASCII characters."""
        return all(ord(c) < 128 for c in text)

    def should_trigger(self, message: str) -> bool:
        """
        Check if this skill should be triggered by a user message.

        Uses word boundary matching for ASCII triggers, and substring
        matching for non-ASCII (e.g., Chinese) triggers.

        Args:
            message: The user's input message

        Returns:
            True if any trigger keyword is found in the message
        """
        for trigger in self.metadata.triggers:
            if self._is_ascii(trigger):
                pattern = rf'\b{re.escape(trigger)}\b'
                if re.search(pattern, message, re.IGNORECASE):
                    return True
            else:
                if trigger.lower() in message.lower():
                    return True
        return False

    def get_trigger_score(self, message: str) -> int:
        """
        Calculate trigger score for ranking skills with same priority.

        Args:
            message: The user's input message

        Returns:
            Score based on number of trigger matches
        """
        score = 0
        for trigger in self.metadata.triggers:
            if self._is_ascii(trigger):
                pattern = rf'\b{re.escape(trigger)}\b'
                matches = re.findall(pattern, message, re.IGNORECASE)
                score += len(matches)
            else:
                if trigger.lower() in message.lower():
                    score += 1
        return score

    def to_system_prompt(self) -> str:
        """
        Generate a system prompt enhancement from this skill.

        Returns:
            Formatted skill content for injection into system prompt
        """
        lines = [
            f"## Skill: {self.metadata.name}",
            "",
            self.metadata.description,
        ]
        if self.metadata.tools:
            lines.append("")
            lines.append(f"可用工具: {', '.join(self.metadata.tools)}")
        lines.append("")
        lines.append(self.content)
        return "\n".join(lines)
