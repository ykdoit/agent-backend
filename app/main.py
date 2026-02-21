"""
FastAPI Main Application

API接口说明：
- 会话管理: 创建会话、会话列表、会话详情
- 对话接口: OpenAI 兼容的流式接口 (/v1/chat/completions)
- 健康检查: 根路由、健康状态
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger

from app.config import get_settings
from app.agent import get_agent_manager, AgentManager
from app.core.redis_manager import get_state_manager
from app.api import sessions_router, chat_router, health_router
from app.api.health import set_agent_manager as health_set_agent_manager
from app.api.chat import set_agent_manager as chat_set_agent_manager

# 全局 AgentManager 实例
_agent_manager: AgentManager | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan"""
    global _agent_manager
    settings = get_settings()
    logger.info(f"Starting {settings.app_name}")
    
    # 初始化 Redis 状态管理器
    state_manager = get_state_manager()
    if state_manager.health_check():
        logger.info("Redis state manager initialized successfully")
    else:
        logger.warning("Redis connection failed, using fallback mode")
    
    # 初始化 AgentManager
    _agent_manager = await get_agent_manager()
    logger.info(f"AgentManager initialized with {len(_agent_manager.skill_list)} skills")
    
    # 设置 API 模块的 AgentManager 引用
    health_set_agent_manager(_agent_manager)
    chat_set_agent_manager(_agent_manager)
    
    yield
    
    # 关闭 AgentManager
    await _agent_manager.shutdown()
    logger.info("Shutting down application")


# FastAPI App
app = FastAPI(
    title="Enterprise Office Agent API",
    description="企业智能办公Agent API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(chat_router)


# ============== 启动入口 ==============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
