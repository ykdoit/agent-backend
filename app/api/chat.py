"""
OpenAI 兼容聊天 API
"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger
from datetime import datetime
from typing import AsyncGenerator
import uuid
import asyncio

from app.core.redis_manager import get_state_manager
from app.agent import AgentManager
from app.api.schemas import OpenAIChatRequest

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])

# 全局 AgentManager 引用（由 main.py 设置）
_agent_manager: AgentManager | None = None


def set_agent_manager(manager: AgentManager):
    """设置 AgentManager 引用"""
    global _agent_manager
    _agent_manager = manager


# 支持的模型列表
AVAILABLE_MODELS = [
    {
        "id": "Pro/zai-org/GLM-4.7",
        "object": "model",
        "created": 1700000000,
        "owned_by": "zai-org",
        "permission": [],
        "root": "GLM-4.7",
        "parent": None,
    }
]


@router.get("/models")
async def list_models():
    """列出可用模型"""
    return {"object": "list", "data": AVAILABLE_MODELS}


@router.get("/models/{model_id:path}")
async def get_model(model_id: str):
    """获取模型详情"""
    for model in AVAILABLE_MODELS:
        if model["id"] == model_id:
            return model
    return {"error": {"message": f"Model '{model_id}' not found", "type": "invalid_request_error"}}


@router.post("/chat/completions")
async def openai_chat_completions(request: OpenAIChatRequest):
    """
    OpenAI 兼容流式接口
    
    请求方式：
    - 新版：{ "message": "xxx", "session_id": "xxx" }
    - 旧版：{ "messages": [...], "session_id": "xxx" }
    """
    agent_manager = _agent_manager
    if agent_manager is None:
        raise RuntimeError("AgentManager not initialized")
    
    state_manager = get_state_manager()
    
    # 提取用户消息
    user_message = request.message
    if not user_message and request.messages:
        for msg in reversed(request.messages):
            if msg.role == "user":
                user_message = msg.content
                break
    
    if not user_message:
        user_message = "请输入消息"
    
    # 生成或使用现有 session_id
    session_id = request.session_id or f"conv_{uuid.uuid4().hex[:12]}"
    
    # 确保会话存在
    if not state_manager.get_session(session_id):
        state_manager.create_session(session_id)
    
    # 存储用户消息
    state_manager.append_message(session_id, "user", user_message)
    
    # 更新会话元数据
    _update_session_meta(state_manager, session_id, user_message)
    
    # 流式响应
    async def generate_stream() -> AsyncGenerator[str, None]:
        chat_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
        assistant_content = ""
        is_first_message = state_manager.get_message_count(session_id) <= 1
        
        try:
            async for chunk in agent_manager.chat_stream(session_id, user_message):
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    assistant_content += content
                    yield f"data: {chunk.model_dump_json()}\n\n"
            
            # 存储助手响应
            state_manager.append_message(session_id, "assistant", assistant_content)
            logger.info(f"[Session {session_id}] Stored assistant message ({len(assistant_content)} chars)")
            
            # 异步生成标题（仅首条消息）
            if is_first_message:
                asyncio.create_task(
                    _generate_and_update_title(agent_manager, state_manager, session_id, user_message, assistant_content)
                )
            
            # 发送完成信号
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {{\"error\": \"{e}\"}}\n\n"
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def _update_session_meta(state_manager, session_id: str, user_message: str):
    """更新会话元数据"""
    session_key = f"SESSION_META:{session_id}"
    if state_manager.redis_client:
        if not state_manager.redis_client.exists(session_key):
            now = datetime.now().isoformat()
            title = user_message[:20] + ("..." if len(user_message) > 20 else "")
            state_manager.redis_client.hset(session_key, mapping={
                "title": title,
                "created_at": now,
                "updated_at": now
            })
        else:
            state_manager.redis_client.hset(session_key, "updated_at", datetime.now().isoformat())


async def _generate_and_update_title(
    agent_manager: AgentManager,
    state_manager,
    session_id: str,
    user_message: str,
    assistant_content: str
):
    """异步生成并更新会话标题"""
    try:
        title = await agent_manager.generate_title(user_message, assistant_content)
        state_manager.update_session_title(session_id, title)
        logger.info(f"[Session {session_id}] Title generated: {title}")
    except Exception as e:
        logger.error(f"[Session {session_id}] Failed to generate title: {e}")
