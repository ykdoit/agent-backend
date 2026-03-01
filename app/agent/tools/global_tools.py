"""
Global Tools - 全局工具

所有技能共享的工具，如时间处理等。

职责：
- 定义全局工具函数
- 提供工具注册接口
- 不包含 Agent 管理逻辑
"""
import inspect
from typing import TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
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
    _wrapper.__name__ = func.__name__
    _wrapper.__qualname__ = func.__qualname__
    _wrapper.__doc__ = func.__doc__
    _wrapper.__module__ = func.__module__
    _wrapper.__annotations__ = func.__annotations__
    _wrapper.__wrapped__ = func
    orig_sig = inspect.signature(func)
    _wrapper.__signature__ = orig_sig.replace(return_annotation=ToolResponse)
    
    return _wrapper


def register_global_tools(toolkit: "Toolkit") -> None:
    """
    注册全局工具到 AgentScope Toolkit
    
    全局工具是所有技能共享的基础工具，如：
    - time_oracle：时间解析
    - get_system_time_context：获取系统时间上下文
    
    Args:
        toolkit: AgentScope Toolkit 实例
    """
    from app.utils.time_oracle import time_oracle, get_system_time_context
    
    # 创建全局工具组
    toolkit.create_tool_group(
        group_name="_global",
        description="全局工具，所有技能共享",
        active=True,
    )
    
    # 注册 time_oracle
    toolkit.register_tool_function(
        _wrap_as_tool_response(time_oracle),
        group_name="_global",
    )
    
    # 注册 get_system_time_context
    toolkit.register_tool_function(
        _wrap_as_tool_response(get_system_time_context),
        group_name="_global",
    )
    
    logger.info("Registered global tools: time_oracle, get_system_time_context")
