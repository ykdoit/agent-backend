"""
会话管理 API
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from loguru import logger
from datetime import datetime
from typing import Optional
import uuid

from app.core.redis_manager import get_state_manager
from app.api.schemas import (
    CreateSessionRequest,
    SessionResponse,
    SessionListResponse,
)

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post("", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest):
    """
    创建新会话
    
    创建一个新的对话会话，用于管理多轮对话
    """
    state_manager = get_state_manager()
    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    
    # 创建会话到 Redis
    state_manager.create_session(session_id, request.user_id)

    # 更新会话元数据
    session_key = f"SESSION_META:{session_id}"
    session_meta = {
        "title": request.title or "新对话",
        "created_at": now,
        "updated_at": now,
        "pinned": "0"
    }
    
    # 使用 Redis hash 存储会话元数据
    if state_manager.redis_client:
        state_manager.redis_client.hset(session_key, mapping=session_meta)
        state_manager.redis_client.expire(session_key, 24 * 3600)
    
    logger.info(f"Created session: {session_id}")
    
    return SessionResponse(
        session_id=session_id,
        title=session_meta["title"],
        created_at=now,
        updated_at=now,
        message_count=0
    )


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    user_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
):
    """
    获取会话列表
    
    分页获取用户的会话列表，按更新时间倒序排列
    """
    state_manager = get_state_manager()
    
    # 从 Redis 获取所有会话
    sessions = []
    if state_manager.redis_client:
        # 扫描所有会话元数据
        pattern = "SESSION_META:*"
        for key in state_manager.redis_client.scan_iter(match=pattern):
            session_id = key.split(":")[-1]
            meta = state_manager.redis_client.hgetall(key)
            
            # 获取会话状态
            session_data = state_manager.get_session(session_id)
            if session_data:
                # 用户筛选
                if user_id and session_data.get("user_id") != user_id:
                    continue
                
                # 获取消息数量
                dialog_key = f"DIALOG_HISTORY:{session_id}"
                message_count = state_manager.redis_client.llen(dialog_key)
                
                sessions.append({
                    "session_id": session_id,
                    "title": meta.get("title", "新对话"),
                    "created_at": meta.get("created_at", ""),
                    "updated_at": meta.get("updated_at", ""),
                    "message_count": message_count,
                    "pinned": meta.get("pinned") == "1"
                })

    # 排序（置顶优先，然后按更新时间倒序）
    sessions.sort(key=lambda x: (not x["pinned"], x["updated_at"]), reverse=False)
    sessions.sort(key=lambda x: x["pinned"], reverse=True)
    
    # 分页
    total = len(sessions)
    start = (page - 1) * page_size
    end = start + page_size
    sessions_page = sessions[start:end]
    
    # 构建响应
    session_responses = [
        SessionResponse(
            session_id=s["session_id"],
            title=s["title"],
            created_at=s["created_at"],
            updated_at=s["updated_at"],
            message_count=s["message_count"],
            pinned=s.get("pinned", False)
        )
        for s in sessions_page
    ]
    
    return SessionListResponse(
        sessions=session_responses,
        total=total
    )


@router.get("/{session_id}")
async def get_session(session_id: str):
    """
    获取会话详情
    
    获取会话信息和该会话下的所有消息
    """
    state_manager = get_state_manager()
    
    # 从 Redis 获取会话
    session_data = state_manager.get_session(session_id)
    if not session_data:
        return {"error": "Session not found"}
    
    # 获取会话元数据
    session_key = f"SESSION_META:{session_id}"
    meta = {}
    if state_manager.redis_client:
        meta = state_manager.redis_client.hgetall(session_key)
    
    # 获取对话历史
    messages = state_manager.get_conversation_history(session_id, limit=100)
    
    # 构建消息响应
    message_responses = []
    for i, m in enumerate(messages):
        message_responses.append({
            "message_id": m.get("message_id", f"msg-{session_id[:8]}-{i}"),
            "role": m["role"],
            "content": m["content"],
            "created_at": m.get("timestamp", meta.get("created_at", ""))
        })
    
    return {
        "session_id": session_id,
        "title": meta.get("title", "新对话"),
        "created_at": meta.get("created_at", ""),
        "updated_at": meta.get("updated_at", ""),
        "messages": message_responses
    }


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """
    删除会话
    
    删除指定会话及其所有消息
    """
    state_manager = get_state_manager()
    
    # 检查会话是否存在
    session_data = state_manager.get_session(session_id)
    if session_data:
        # 清除对话历史
        state_manager.clear_conversation(session_id)
        
        # 删除会话元数据
        session_key = f"SESSION_META:{session_id}"
        if state_manager.redis_client:
            state_manager.redis_client.delete(session_key)
            # 删除会话状态
            state_key = f"SESSION_STATE:{session_id}"
            state_manager.redis_client.delete(state_key)
        
        logger.info(f"Deleted session: {session_id}")
        return {"success": True, "message": "Session deleted"}
    
    return {"success": False, "message": "Session not found"}


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    title: Optional[str] = Query(None),
    pinned: Optional[bool] = Query(None)
):
    """
    更新会话

    更新会话标题、置顶状态等信息
    """
    state_manager = get_state_manager()

    # 检查会话是否存在
    session_data = state_manager.get_session(session_id)
    if not session_data:
        return {"error": "Session not found"}

    # 更新会话元数据
    session_key = f"SESSION_META:{session_id}"
    if state_manager.redis_client:
        if title:
            state_manager.redis_client.hset(session_key, "title", title)
        if pinned is not None:
            state_manager.redis_client.hset(session_key, "pinned", "1" if pinned else "0")
        state_manager.redis_client.hset(session_key, "updated_at", datetime.now().isoformat())

        # 获取更新后的元数据
        meta = state_manager.redis_client.hgetall(session_key)

        # 获取消息数量
        dialog_key = f"DIALOG_HISTORY:{session_id}"
        message_count = state_manager.redis_client.llen(dialog_key)

        return SessionResponse(
            session_id=session_id,
            title=meta.get("title", "新对话"),
            created_at=meta.get("created_at", ""),
            updated_at=meta.get("updated_at", ""),
            message_count=message_count,
            pinned=meta.get("pinned") == "1"
        )

    return {"error": "Redis not available"}
