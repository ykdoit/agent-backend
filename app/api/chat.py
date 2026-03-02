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
import json

from app.core.redis_manager import get_state_manager
from app.agent import AgentManager
from app.agent.chat_service import ChatService
from app.api.schemas import OpenAIChatRequest

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])

# 全局引用（由 main.py 设置）
_agent_manager: AgentManager | None = None
_chat_service: ChatService | None = None


def set_agent_manager(manager: AgentManager):
    """设置 AgentManager 引用"""
    global _agent_manager, _chat_service
    _agent_manager = manager
    _chat_service = ChatService(manager)


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
        assistant_content = ""
        is_first_message = state_manager.get_message_count(session_id) <= 1
        
        try:
            async for sse_line in _chat_service.chat_stream(session_id, user_message):
                # 直接透传 SSE 行
                yield sse_line
                
                # 从 message 事件中提取 content（用于存储）
                if sse_line.startswith("data: ") and not sse_line.startswith("data: [DONE]"):
                    try:
                        data_str = sse_line[6:].strip()
                        if data_str:
                            data = json.loads(data_str)
                            # 提取消息内容
                            if data.get("choices") and data["choices"][0].get("delta", {}).get("content"):
                                assistant_content += data["choices"][0]["delta"]["content"]
                    except json.JSONDecodeError:
                        pass
            
            # 存储助手响应
            if assistant_content:
                state_manager.append_message(session_id, "assistant", assistant_content)
                logger.info(f"[Session {session_id}] Stored assistant message ({len(assistant_content)} chars)")
            
            # 异步生成标题（仅首条消息）
            if is_first_message and assistant_content:
                asyncio.create_task(
                    _generate_and_update_title(_chat_service, state_manager, session_id, user_message, assistant_content)
                )
            
        except Exception as e:
            import traceback; logger.error(f"Stream error: {e}, type: {type(e)}"); logger.error(f"Traceback: {traceback.format_exc()}")
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
    chat_service: ChatService,
    state_manager,
    session_id: str,
    user_message: str,
    assistant_content: str
):
    """异步生成并更新会话标题"""
    try:
        title = await chat_service.generate_title(user_message, assistant_content)
        state_manager.update_session_title(session_id, title)
        logger.info(f"[Session {session_id}] Title generated: {title}")
    except Exception as e:
        logger.error(f"[Session {session_id}] Failed to generate title: {e}")
