"""
API 数据模型
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


# ============== Session Models ==============

class CreateSessionRequest(BaseModel):
    """创建会话请求"""
    title: Optional[str] = None
    user_id: Optional[str] = None


class SessionResponse(BaseModel):
    """会话响应"""
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    user_id: Optional[str] = None
    pinned: bool = False


class MessageResponse(BaseModel):
    """消息响应"""
    role: str
    content: str
    timestamp: str


class SessionDetailResponse(BaseModel):
    """会话详情响应"""
    id: str
    title: str
    created_at: str
    updated_at: str
    user_id: Optional[str] = None
    messages: List[MessageResponse] = []


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[SessionResponse]
    total: int


# ============== OpenAI Compatible Models ==============

class OpenAIMessage(BaseModel):
    """OpenAI 消息格式"""
    role: str
    content: str


class OpenAIChatRequest(BaseModel):
    """OpenAI Chat 请求"""
    model: str = "agent-default"
    messages: List[OpenAIMessage] = []
    stream: bool = True
    session_id: Optional[str] = None
    message: Optional[str] = None  # 新版：直接发送消息


class OpenAIChatChoice(BaseModel):
    """OpenAI Chat 选择项"""
    index: int = 0
    message: Optional[OpenAIMessage] = None
    finish_reason: Optional[str] = None


class OpenAIChatResponse(BaseModel):
    """OpenAI Chat 响应"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OpenAIChatChoice]
