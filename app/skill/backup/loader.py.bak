"""
Skill Loader - 技能加载器

加载 Markdown 格式的技能文件
"""
import re
from typing import List, Dict, Optional
from pathlib import Path
from dataclasses import dataclass, field
from loguru import logger
import yaml


@dataclass
class SkillConfig:
    """Skill 配置"""
    name: str
    description: str
    system_prompt_patch: str = ""  # Markdown 正文作为指令


class SkillLoader:
    """Skill 加载器 - 解析 Markdown 格式的技能文件"""
    
    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
    
    def load_all_skills(self) -> Dict[str, SkillConfig]:
        """加载所有 Skill"""
        skills = {}
        
        for md_file in self.skills_dir.rglob("*.md"):
            try:
                skill = self.load_skill(md_file)
                if skill:
                    skills[skill.name] = skill
                    logger.info(f"Loaded skill: {skill.name}")
            except Exception as e:
                logger.error(f"Failed to load {md_file}: {e}")
        
        return skills
    
    def load_skill(self, md_file: Path) -> Optional[SkillConfig]:
  
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 提取 Front Matter
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)', content, re.DOTALL)
        if not match:
            logger.warning(f"Invalid skill file format: {md_file}")
            return None
        
        yaml_content = match.group(1)
        markdown_body = match.group(2).strip()
        
        try:
            front_matter = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            logger.error(f"YAML parse error in {md_file}: {e}")
            return None
        
        name = front_matter.get("name")
        description = front_matter.get("description", "")
        
        if not name:
            logger.warning(f"Skill missing 'name' in {md_file}")
            return None
        
        return SkillConfig(
            name=name,
            description=description,
            system_prompt_patch=markdown_body,
        )


class SkillRegistry:
    """Skill 注册中心"""
    
    def __init__(self, skills_dirs: List[str] = None):
        self._skills: Dict[str, SkillConfig] = {}
        
        if skills_dirs is None:
            from app.config import get_settings
            settings = get_settings()
            skills_dirs = settings.get_skills_dirs()
        
        for skills_dir in skills_dirs:
            self._load_from_dir(skills_dir)
    
    def _load_from_dir(self, skills_dir: str):
        """从目录加载"""
        loader = SkillLoader(skills_dir)
        skills = loader.load_all_skills()
        self._skills.update(skills)
    
    def get(self, name: str) -> Optional[SkillConfig]:
        """获取 Skill"""
        return self._skills.get(name)
    
    def match(self, user_input: str) -> Optional[SkillConfig]:
        """匹配 Skill（通过 description 关键词）"""
        user_input_lower = user_input.lower()
        for skill in self._skills.values():
            # 通过 description 中的关键词匹配
            if skill.description and skill.description.lower() in user_input_lower:
                return skill
        return None
    
    def list_all(self) -> List[Dict]:
        """列出所有 Skill"""
        return [
            {
                "name": skill.name,
                "description": skill.description,
            }
            for skill in self._skills.values()
        ]
    
    @property
    def skills(self) -> Dict[str, SkillConfig]:
        """获取所有 Skill"""
        return self._skills
    
    # 兼容旧接口
    @property
    def configs(self) -> Dict[str, SkillConfig]:
        """兼容旧接口: registry.configs"""
        return self._skills


# 全局实例
_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """获取 Skill 注册中心实例"""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry


# 兼容旧接口
def get_skill_config_registry() -> SkillRegistry:
    """兼容旧接口"""
    return get_skill_registry()


def load_skills(skills_dir: str, toolkit) -> List[Dict[str, str]]:
    """加载技能并注入 system_prompt_patch"""
    registry = get_skill_registry()
    return registry.list_all()


def get_all_skill_prompts() -> str:
    """获取所有 Skill 的 SOP 指令集，用于注入 Agent 系统提示词"""
    registry = get_skill_registry()
    prompts = []
    
    # 总目录，帮助 Agent 建立全局观
    if registry.skills:
        prompts.append("## 业务技能详细 SOP 指令集\n你必须根据用户意图严格遵守以下对应的业务规则。")
    
    for skill in registry.skills.values():
        if skill.system_prompt_patch:
            # 使用明确的边界标识
            block = (
                f"---\n"
                f"### 【技能：{skill.name}】\n"
                f"> {skill.description}\n\n"
                f"{skill.system_prompt_patch}\n"
                f"<!-- 技能 {skill.name} 结束 -->"
            )
            prompts.append(block)
    
    return "\n\n".join(prompts) if prompts else ""
