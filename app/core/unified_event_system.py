"""
统一事件系统 - 合并 sse_protocol.py 和 event_system.py
实现 Anthropic 规范的四类事件：thought/call/interaction/message
支持 SSE 流式输出和事件路由
"""

import asyncio
import json
from typing import Dict, Any, Callable, List, Optional, AsyncGenerator
from datetime import datetime
from enum import Enum
import uuid
import logging

logger = logging.getLogger(__name__)


class EventType(Enum):
    """事件类型枚举"""
    WORKFLOW = "workflow"        # 工作流定义事件
    THOUGHT = "thought"          # 推理事件
    CALL = "call"               # 工具调用事件
    INTERACTION = "interaction"  # 用户交互事件
    MESSAGE = "message"         # 消息事件
    CONTROL = "control"         # 控制事件


class AgentState(Enum):
    """Agent 状态枚举"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PROCESSING = "processing"
    SUSPENDED = "suspended"
    RESUMING = "resuming"
    COMPLETED = "completed"
    ERROR = "error"


class Event:
    """统一事件类"""
    
    def __init__(self, event_type: EventType, data: Dict[str, Any],
                 session_id: str = None):
        self.id = f"evt_{uuid.uuid4().hex[:12]}"
        self.type = event_type
        self.data = data
        self.session_id = session_id
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "event": self.type.value,
            "id": self.id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            **self.data
        }
    
    def to_sse_format(self) -> str:
        """转换为 SSE 格式"""
        return f"data: {json.dumps(self.to_dict(), ensure_ascii=False)}\n\n"


class EventContext:
    """事件上下文 - 用于工具函数发送事件"""
    
    def __init__(self, session_id: str, yield_func: Callable = None):
        self.session_id = session_id
        self.yield_func = yield_func  # 用于流式输出的 yield 函数
        self.events_queue: List[Event] = []
    
    def create_thought_event(self, stage_id: str, detail: str, progress: int = 0) -> Event:
        """创建推理事件"""
        return Event(
            EventType.THOUGHT,
            {
                "stage_id": stage_id,
                "detail": detail,
                "progress": progress
            },
            session_id=self.session_id
        )
    
    def create_call_event(self, tool_name: str, parameters: Dict[str, Any], 
                         call_id: str = None) -> Event:
        """创建工具调用事件"""
        if not call_id:
            call_id = f"call_{uuid.uuid4().hex[:8]}"
        
        return Event(
            EventType.CALL,
            {
                "call_id": call_id,
                "tool_name": tool_name,
                "parameters": parameters
            },
            session_id=self.session_id
        )
    
    def emit_thought(self, stage_id: str, detail: str, progress: int = 0) -> str:
        """发送推理事件并返回 SSE 格式字符串"""
        event = self.create_thought_event(stage_id, detail, progress)
        return event.to_sse_format()
    
    def emit_call(self, tool_name: str, parameters: Dict[str, Any],
                  call_id: str = None) -> str:
        """发送工具调用事件并返回 SSE 格式字符串"""
        event = self.create_call_event(tool_name, parameters, call_id)
        return event.to_sse_format()


class EventManager:
    """统一事件管理器 - 替代 SSEEventManager"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.chat_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        self.state = AgentState.PROCESSING
        self.call_stack = []
        self.suspended_call_id = None
    
    def create_event(self, event_type: EventType, data: Dict[str, Any]) -> str:
        """创建 SSE 事件"""
        event = Event(event_type, data, session_id=self.session_id)
        event_data = event.to_dict()
        event_data["id"] = self.chat_id  # 使用统一的 chat_id
        return f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
    
    async def send_thought(self, stage_id: str, detail: str, 
                          progress: int = 0) -> AsyncGenerator[str, None]:
        """发送推理事件"""
        event = self.create_event(EventType.THOUGHT, {
            "stage_id": stage_id,
            "detail": detail,
            "progress": progress,
            "state": self.state.value
        })
        yield event
    
    async def send_call(self, tool_name: str, parameters: Dict[str, Any],
                       call_id: str = None) -> AsyncGenerator[str, None]:
        """发送工具调用事件"""
        if not call_id:
            call_id = f"call_{uuid.uuid4().hex[:8]}"
        
        self.call_stack.append({
            "id": call_id,
            "tool_name": tool_name,
            "parameters": parameters,
            "timestamp": datetime.now().isoformat()
        })
        
        event = self.create_event(EventType.CALL, {
            "call_id": call_id,
            "tool_name": tool_name,
            "parameters": parameters,
            "state": self.state.value
        })
        yield event
    
    async def send_interaction(self, interaction_type: str, payload: Dict[str, Any],
                              call_id: str = None) -> AsyncGenerator[str, None]:
        """发送交互事件（挂起 Agent）"""
        if not call_id and self.call_stack:
            call_id = self.call_stack[-1]["id"]
        
        self.state = AgentState.SUSPENDED
        self.suspended_call_id = call_id
        
        event = self.create_event(EventType.INTERACTION, {
            "type": interaction_type,
            "payload": payload,
            "call_id": call_id,
            "state": self.state.value
        })
        yield event
    
    async def send_message(self, content: str) -> AsyncGenerator[str, None]:
        """发送消息内容"""
        event = self.create_event(EventType.MESSAGE, {
            "content": content,
            "state": self.state.value
        })
        yield event
    
    async def send_completion(self) -> AsyncGenerator[str, None]:
        """发送完成事件"""
        self.state = AgentState.COMPLETED
        event = self.create_event(EventType.MESSAGE, {
            "content": "",
            "state": self.state.value,
            "finished": True
        })
        yield event
        yield "data: [DONE]\n\n"
    
    async def resume_from_interaction(self, call_id: str,
                                     user_response: Dict[str, Any]) -> AsyncGenerator[str, None]:
        """从交互中恢复执行"""
        if self.state == AgentState.SUSPENDED and self.suspended_call_id == call_id:
            self.state = AgentState.PROCESSING
            self.suspended_call_id = None
            
            yield self.create_event(EventType.THOUGHT, {
                "stage_id": "resuming",
                "detail": "收到用户反馈，继续执行...",
                "progress": 90,
                "state": self.state.value
            })
            
            yield self.create_event(EventType.MESSAGE, {
                "content": "已收到您的确认，正在继续处理...",
                "state": self.state.value
            })


# 事件管理器存储（使用 Redis 替代内存字典，但保留此接口以保持兼容性）
_event_managers: Dict[str, EventManager] = {}


def get_event_manager(session_id: str) -> EventManager:
    """获取或创建事件管理器"""
    if session_id not in _event_managers:
        _event_managers[session_id] = EventManager(session_id)
    return _event_managers[session_id]


def remove_event_manager(session_id: str):
    """清理事件管理器"""
    if session_id in _event_managers:
        del _event_managers[session_id]


# 导出兼容旧代码的接口
__all__ = [
    'EventType',
    'AgentState',
    'Event',
    'EventContext',
    'EventManager',
    'get_event_manager',
    'remove_event_manager'
]
