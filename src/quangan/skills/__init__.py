"""
Skill system for QuanGan.

This module provides dynamic skill loading and registration capabilities,
allowing users to extend agent capabilities through declarative Markdown files.
"""

from .loader import SkillLoader
from .models import Skill, SkillMetadata
from .parser import SkillParser

__all__ = ["Skill", "SkillMetadata", "SkillParser", "SkillLoader"]
