"""
Skill Loader - 技能加载器（支持动态加载）

特性：
- 初始化时只加载元数据（name + description）
- 正文内容延迟加载（调用 load_skill_detail 时）
- 兼容 OpenClaw 的 SKILL.md 规范
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
    system_prompt_patch: str = ""  # Markdown 正文（延迟加载）
    is_loaded: bool = False  # 正文是否已加载
    file_path: str = ""  # 文件路径，用于延迟加载
    
    def __repr__(self):
        return f"SkillConfig(name={self.name}, loaded={self.is_loaded})"


class SkillLoader:
    """Skill 加载器 - 支持 OpenClaw SKILL.md 规范"""
    
    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)
    
    def load_all_skills(self, load_body: bool = False) -> Dict[str, SkillConfig]:
        """
        加载所有 Skill
        
        Args:
            load_body: 是否立即加载正文（默认 False，延迟加载）
        
        Returns:
            技能字典 {name: SkillConfig}
        """
        skills = {}
        
        # 只扫描 SKILL.md 文件（OpenClaw 规范）
        for md_file in self.skills_dir.rglob("SKILL.md"):
            try:
                skill = self.load_skill(md_file, load_body=load_body)
                if skill:
                    skills[skill.name] = skill
                    logger.info(f"Loaded skill metadata: {skill.name}")
            except Exception as e:
                logger.error(f"Failed to load {md_file}: {e}")
        
        return skills
    
    def load_skill(self, md_file: Path, load_body: bool = False) -> Optional[SkillConfig]:
        """
        加载单个 Skill
        
        Args:
            md_file: SKILL.md 文件路径
            load_body: 是否加载正文
        """
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
            system_prompt_patch=markdown_body if load_body else "",
            is_loaded=load_body,
            file_path=str(md_file),
        )
    
    def load_skill_body(self, skill: SkillConfig) -> str:
        """
        延迟加载技能正文
        
        Args:
            skill: 技能配置对象
        
        Returns:
            技能正文内容
        """
        if skill.is_loaded:
            return skill.system_prompt_patch
        
        if not skill.file_path:
            logger.error(f"Skill {skill.name} has no file_path")
            return ""
        
        try:
            with open(skill.file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            match = re.match(r'^---\s*\n.*?\n---\s*\n(.*)', content, re.DOTALL)
            if match:
                skill.system_prompt_patch = match.group(1).strip()
                skill.is_loaded = True
                logger.info(f"Loaded skill body: {skill.name}")
            
            return skill.system_prompt_patch
        except Exception as e:
            logger.error(f"Failed to load skill body for {skill.name}: {e}")
            return ""


class SkillRegistry:
    """Skill 注册中心 - 管理技能目录和延迟加载"""
    
    def __init__(self, skills_dirs: List[str] = None):
        self._skills: Dict[str, SkillConfig] = {}
        self._loader: Optional[SkillLoader] = None
        
        if skills_dirs is None:
            from app.config import get_settings
            settings = get_settings()
            skills_dirs = settings.get_skills_dirs()
        
        for skills_dir in skills_dirs:
            self._load_from_dir(skills_dir)
    
    def _load_from_dir(self, skills_dir: str):
        """从目录加载技能元数据"""
        self._loader = SkillLoader(skills_dir)
        skills = self._loader.load_all_skills(load_body=False)
        self._skills.update(skills)
        logger.info(f"Loaded {len(skills)} skills from {skills_dir}")
    
    def get(self, name: str) -> Optional[SkillConfig]:
        """获取 Skill 元数据"""
        return self._skills.get(name)
    
    def match(self, user_input: str) -> Optional[SkillConfig]:
        """匹配 Skill（通过 description 关键词）"""
        user_input_lower = user_input.lower()
        for skill in self._skills.values():
            if skill.description and skill.description.lower() in user_input_lower:
                return skill
        return None
    
    def get_skill_catalog(self) -> str:
        """
        获取技能目录（用于注入系统提示词）
        只包含 name + description，不包含正文
        """
        if not self._skills:
            return "## 可用技能\n\n暂无可用技能。"
        
        catalog = "## 可用技能\n\n"
        catalog += "以下技能可供使用。当用户意图匹配时，**必须先调用 `read_skill` 工具**读取详细指令。\n\n"
        catalog += "| 技能名称 | 触发条件 |\n"
        catalog += "|---------|----------|\n"
        
        for skill in sorted(self._skills.values(), key=lambda s: s.name):
            catalog += f"| `{skill.name}` | {skill.description} |\n"
        
        return catalog
    
    def load_skill_detail(self, name: str) -> str:
        """
        加载指定技能的详细内容
        
        Args:
            name: 技能名称
        
        Returns:
            技能详细指令（正文）
        """
        skill = self._skills.get(name)
        if not skill:
            logger.warning(f"Skill not found: {name}")
            return f"错误：未找到技能 '{name}'"
        
        if not self._loader:
            logger.error("SkillLoader not initialized")
            return "错误：技能加载器未初始化"
        
        return self._loader.load_skill_body(skill)
    
    def list_all(self) -> List[Dict]:
        """列出所有 Skill（仅元数据）"""
        return [
            {
                "name": skill.name,
                "description": skill.description,
                "loaded": skill.is_loaded,
            }
            for skill in self._skills.values()
        ]
    
    def load_skill_detail(self, name: str) -> str:
        """
        加载指定技能的详细内容（延迟加载）
        
        Args:
            name: 技能名称
        
        Returns:
            技能详细指令（正文）
        """
        skill = self._skills.get(name)
        if not skill:
            logger.warning(f"Skill not found: {name}")
            return f"错误：未找到技能 '{name}'"
        
        if not self._loader:
            logger.error("SkillLoader not initialized")
            return "错误：技能加载器未初始化"
        
        body = self._loader.load_skill_body(skill)
        
        if not body:
            return f"错误：技能 '{name}' 内容为空"
        
        return body
    
    @property
    def skills(self) -> Dict[str, SkillConfig]:
        """获取所有 Skill"""
        return self._skills
    
    # 兼容旧接口
    @property
    def configs(self) -> Dict[str, SkillConfig]:
        """兼容旧接口"""
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
    """加载技能（兼容旧接口）"""
    registry = get_skill_registry()
    return registry.list_all()


def get_all_skill_prompts() -> str:
    """
    获取所有 Skill 的提示词（兼容旧接口）
    
    ⚠️ 注意：此方法会加载所有正文，不推荐使用
    建议使用 get_skill_registry().get_skill_catalog() 代替
    """
    registry = get_skill_registry()
    logger.warning(
        "get_all_skill_prompts() loads all skill bodies. "
        "Consider using get_skill_catalog() for better token efficiency."
    )
    
    prompts = []
    for skill in registry.skills.values():
        body = registry.load_skill_detail(skill.name)
        if body:
            block = (
                f"---\n"
                f"### 【技能：{skill.name}】\n"
                f"> {skill.description}\n\n"
                f"{body}\n"
            )
            prompts.append(block)
    
    return "\n\n".join(prompts) if prompts else ""
