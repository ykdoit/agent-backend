"""
OpenAI 兼容聊天 API
"""
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.core.limiter import limiter
from loguru import logger
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any
import uuid
import asyncio
import json

from app.core.redis_manager import get_state_manager
from app.agent import AgentManager
from app.agent.chat_service import ChatService
from app.api.schemas import OpenAIChatRequest
from app.config import load_yaml_config

router = APIRouter(prefix="/v1", tags=["OpenAI Compatible"])

# 全局引用（由 main.py 设置）
_agent_manager: AgentManager | None = None
_chat_service: ChatService | None = None


def set_agent_manager(manager: AgentManager):
    """设置 AgentManager 引用"""
    global _agent_manager, _chat_service
    _agent_manager = manager
    _chat_service = ChatService(manager)


def _load_available_models() -> List[Dict[str, Any]]:
    """从配置文件加载可用模型列表"""
    yaml_config = load_yaml_config()
    models_config = yaml_config.get("available_models", [])

    if not models_config:
        # 兼容：如果没有配置，返回默认模型
        return [{
            "id": "glm-5",
            "object": "model",
            "created": 1700000000,
            "owned_by": "zai-org",
            "permission": [],
            "root": "GLM-5",
            "parent": None,
            "context": 204800,
            "output": 131072,
        }]

    # 转换为 OpenAI 格式
    return [
        {
            "id": model["id"],
            "object": "model",
            "created": 1700000000,
            "owned_by": "zai-org",
            "permission": [],
            "root": model["name"],
            "parent": None,
            "context": model.get("context", 204800),
            "output": model.get("output", 131072),
        }
        for model in models_config
    ]


# 支持的模型列表（从配置动态加载）
AVAILABLE_MODELS = _load_available_models()


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
@limiter.limit("10/minute")
async def openai_chat_completions(request: Request, body: OpenAIChatRequest):
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

    # 提取用户消息和模型
    user_message = body.message
    model = body.model  # 接收前端传来的模型 ID
    if not user_message and body.messages:
        for msg in reversed(body.messages):
            if msg.role == "user":
                user_message = msg.content
                break

    if not user_message:
        user_message = "请输入消息"

    # 生成或使用现有 session_id
    session_id = body.session_id or f"conv_{uuid.uuid4().hex[:12]}"
    
    # 确保会话存在
    if not state_manager.get_session(session_id):
        state_manager.create_session(session_id)
    
    # 存储用户消息
    state_manager.append_message(session_id, "user", user_message)
    
    # 更新会话元数据
    _update_session_meta(state_manager, session_id, user_message)
    
    # 用于跟踪已生成内容（_background_save 也会用到）
    _state = {"content": "", "saved": False}

    async def _watch_disconnect():
        """后台轮询客户端是否断开（仅日志，saving 由 _background_save 负责）"""
        while not await request.is_disconnected():
            await asyncio.sleep(0.5)
        logger.info(f"[Session {session_id}] Client disconnect detected by watcher, content_len={len(_state['content'])}")

    # 流式响应
    async def generate_stream() -> AsyncGenerator[str, None]:
        is_first_message = state_manager.get_message_count(session_id) <= 1

        # 启动断连监控任务
        disconnect_task = asyncio.create_task(_watch_disconnect())

        try:
            async for sse_line in _chat_service.chat_stream(session_id, user_message, model):
                # 先解析 content（在 yield 前），保证 _state["content"] 始终最新
                if sse_line.startswith("data: ") and not sse_line.startswith("data: [DONE]"):
                    try:
                        data_str = sse_line[6:].strip()
                        if data_str:
                            data = json.loads(data_str)
                            if data.get("choices") and data["choices"][0].get("delta", {}).get("content"):
                                _state["content"] += data["choices"][0]["delta"]["content"]
                    except json.JSONDecodeError:
                        pass

                yield sse_line

            # 流正常结束，存储完整助手响应
            if _state["content"] and not _state["saved"]:
                state_manager.append_message(session_id, "assistant", _state["content"])
                _state["saved"] = True
                logger.info(f"[Session {session_id}] Stored assistant message ({len(_state['content'])} chars)")

            # 异步生成标题（仅首条消息）
            if is_first_message and _state["content"]:
                asyncio.create_task(
                    _generate_and_update_title(_chat_service, state_manager, session_id, user_message, _state["content"])
                )

        except Exception as e:
            _state["saved"] = True  # 异常路径不让断连监控重复保存
            import traceback; logger.error(f"Stream error: {e}, type: {type(e)}"); logger.error(f"Traceback: {traceback.format_exc()}")
            yield f"data: {{\"error\": \"{e}\"}}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            disconnect_task.cancel()  # 正常结束时取消监控任务
    
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
