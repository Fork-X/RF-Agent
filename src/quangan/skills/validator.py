"""
Skill-tool dependency validator.

Refactor: [设计缺陷] 技能的 tools 字段虽在 models.py 中定义但从未被验证，
新增验证器在 Agent 初始化后检查技能声明的工具是否都已注册。
"""

from __future__ import annotations

from quangan.skills.models import Skill
from quangan.utils.logger import get_logger

logger = get_logger("skill_validator")


class SkillValidator:
    """Validates skill-tool dependency relationships.

    Checks that tools declared in skill metadata are actually
    registered in the agent's tool registry.
    """

    def __init__(self, registered_tools: set[str]) -> None:
        """Initialize with the set of registered tool names.

        Args:
            registered_tools: Set of tool names available in the agent.
        """
        self._registered_tools = registered_tools

    def validate(self, skill: Skill) -> list[str]:
        """Validate a single skill's tool dependencies.

        Args:
            skill: Skill to validate.

        Returns:
            List of missing tool names (empty if all present).
        """
        missing: list[str] = []
        for tool_name in skill.metadata.tools:
            if tool_name not in self._registered_tools:
                missing.append(tool_name)
        return missing

    def validate_all(self, skills: dict[str, Skill]) -> dict[str, list[str]]:
        """Validate all skills and return those with missing tools.

        Args:
            skills: Dictionary of skill_name -> Skill objects.

        Returns:
            Dictionary of skill_name -> list of missing tool names.
            Only skills with missing tools are included.
        """
        issues: dict[str, list[str]] = {}
        for name, skill in skills.items():
            missing = self.validate(skill)
            if missing:
                issues[name] = missing
                logger.warning(
                    "Skill '%s' declares tools %s but they are not registered",
                    name,
                    missing,
                )
        if not issues:
            logger.info("All skill-tool dependencies validated successfully")
        return issues
