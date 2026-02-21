"""
Skill Module - 技能加载模块
"""
from app.skill.loader import (
    SkillConfig,
    SkillLoader,
    SkillRegistry,
    get_skill_registry,
    get_skill_config_registry,  # 兼容旧接口
    load_skills,
    get_all_skill_prompts,
)

__all__ = [
    "SkillConfig",
    "SkillLoader",
    "SkillRegistry",
    "get_skill_registry",
    "get_skill_config_registry",
    "load_skills",
    "get_all_skill_prompts",
]
