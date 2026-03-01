"""
Agent Tools - 工具模块

提供各种工具的注册功能，遵循单一职责原则：
- manager.py：Agent 管理器（协调者）
- tools/：工具定义（不包含管理逻辑）
"""

from app.agent.tools.skill_tools import register_skill_tools
from app.agent.tools.global_tools import register_global_tools

__all__ = [
    "register_skill_tools",
    "register_global_tools",
]
