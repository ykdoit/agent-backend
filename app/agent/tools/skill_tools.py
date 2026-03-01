"""
Skill Tools - 技能相关工具

提供技能详细内容读取功能，支持动态加载。

职责：
- 定义技能工具函数
- 提供工具注册接口
- 不包含 Agent 管理逻辑
"""
from typing import TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from app.skill.loader import SkillRegistry
    from agentscope.tool import Toolkit

from agentscope.message import TextBlock
from agentscope.tool import ToolResponse


def _wrap_as_tool_response(func):
    """
    包装普通函数，使其返回值为 ToolResponse
    
    Args:
        func: 原始函数
    
    Returns:
        包装后的异步函数
    """
    async def _wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        if isinstance(result, ToolResponse):
            return result
        return ToolResponse(content=[TextBlock(type="text", text=str(result))])
    
    # 保留原函数的元信息
    import inspect
    _wrapper.__name__ = func.__name__
    _wrapper.__qualname__ = func.__qualname__
    _wrapper.__doc__ = func.__doc__
    _wrapper.__module__ = func.__module__
    _wrapper.__annotations__ = func.__annotations__
    _wrapper.__wrapped__ = func
    orig_sig = inspect.signature(func)
    _wrapper.__signature__ = orig_sig.replace(return_annotation=ToolResponse)
    
    return _wrapper


def create_read_skill_tool(skill_registry: "SkillRegistry"):
    """
    创建 read_skill 工具函数
    
    Args:
        skill_registry: 技能注册中心
    
    Returns:
        read_skill 函数（已包装为 ToolResponse）
    """
    
    def read_skill(skill_name: str) -> str:
        """
        读取指定技能的详细指令
        
        当用户意图匹配某个技能时，必须先调用此工具读取详细指令。
        未读取技能详细内容前，禁止猜测执行步骤。
        
        Args:
            skill_name: 技能名称（如 'oa-leave', 'sales-plan-create'）
        
        Returns:
            技能的详细指令内容
        """
        content = skill_registry.load_skill_detail(skill_name)
        
        if content.startswith("错误："):
            logger.warning(f"read_skill failed: {skill_name}")
        else:
            logger.info(f"read_skill loaded: {skill_name}")
        
        return content
    
    # 包装为返回 ToolResponse
    return _wrap_as_tool_response(read_skill)


def create_list_skills_tool(skill_registry: "SkillRegistry"):
    """
    创建 list_available_skills 工具函数
    
    Args:
        skill_registry: 技能注册中心
    
    Returns:
        list_available_skills 函数（已包装为 ToolResponse）
    """
    
    def list_available_skills() -> str:
        """
        列出所有可用技能
        
        返回技能列表，包含技能名称和触发条件。
        
        Returns:
            可用技能列表
        """
        skills = skill_registry.list_all()
        
        if not skills:
            return "暂无可用技能。"
        
        result = "## 可用技能列表\n\n"
        result += "| 技能名称 | 触发条件 |\n"
        result += "|---------|----------|\n"
        
        for skill in sorted(skills, key=lambda s: s["name"]):
            result += f"| `{skill['name']}` | {skill['description']} |\n"
        
        return result
    
    # 包装为返回 ToolResponse
    return _wrap_as_tool_response(list_available_skills)


def register_skill_tools(toolkit: "Toolkit", skill_registry: "SkillRegistry") -> None:
    """
    注册技能相关工具到 AgentScope Toolkit
    
    注册的工具：
    - read_skill：读取指定技能的详细指令
    - list_available_skills：列出所有可用技能
    
    Args:
        toolkit: AgentScope Toolkit 实例
        skill_registry: 技能注册中心
    
    Example:
        >>> from app.skill.loader import get_skill_registry
        >>> from agentscope.tool import Toolkit
        >>> toolkit = Toolkit()
        >>> skill_registry = get_skill_registry()
        >>> register_skill_tools(toolkit, skill_registry)
    """
    # 创建工具函数
    read_skill = create_read_skill_tool(skill_registry)
    list_available_skills = create_list_skills_tool(skill_registry)
    
    # 创建 skill 工具组
    toolkit.create_tool_group(
        group_name="skill",
        description="技能管理工具，用于读取技能详细指令",
        active=True,
    )
    
    # 注册工具
    toolkit.register_tool_function(read_skill, group_name="skill")
    toolkit.register_tool_function(list_available_skills, group_name="skill")
    
    logger.info("Skill tools registered: read_skill, list_available_skills")
