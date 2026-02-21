"""
Core 模块

提供 Agent 核心功能：
- redis_manager: Redis 状态管理
- unified_event_system: SSE 事件系统
"""

from .redis_manager import get_state_manager, get_state_machine, RedisStateManager
from .unified_event_system import Event, EventType, EventManager, EventContext

__all__ = [
    'get_state_manager',
    'get_state_machine',
    'RedisStateManager',
    'Event',
    'EventType',
    'EventManager',
    'EventContext',
]
