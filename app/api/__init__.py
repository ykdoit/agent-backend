"""
API 模块 - 路由和数据模型
"""
from app.api.schemas import (
    CreateSessionRequest,
    SessionResponse,
    SessionListResponse,
    MessageResponse,
    SessionDetailResponse,
    OpenAIMessage,
    OpenAIChatRequest,
    OpenAIChatChoice,
    OpenAIChatResponse,
)
from app.api.sessions import router as sessions_router
from app.api.chat import router as chat_router
from app.api.health import router as health_router

__all__ = [
    # Schemas
    "CreateSessionRequest",
    "SessionResponse",
    "SessionListResponse",
    "MessageResponse",
    "SessionDetailResponse",
    "OpenAIMessage",
    "OpenAIChatRequest",
    "OpenAIChatChoice",
    "OpenAIChatResponse",
    # Routers
    "sessions_router",
    "chat_router",
    "health_router",
]
