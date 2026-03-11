"""
会话管理 API
"""
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from app.core.limiter import limiter
from loguru import logger
from datetime import datetime
from typing import Optional
import uuid

from app.core.redis_manager import get_state_manager
from app.api.schemas import (
    CreateSessionRequest,
    SessionResponse,
    SessionListResponse,
    SearchMessageSnippet,
    SearchSessionResult,
    SearchResponse,
)
import time
import json

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.post("", response_model=SessionResponse)
@limiter.limit("30/minute")
async def create_session(request: Request, body: CreateSessionRequest):
    """
    创建新会话

    创建一个新的对话会话，用于管理多轮对话
    """
    state_manager = get_state_manager()
    session_id = str(uuid.uuid4())
    now = datetime.now().isoformat()

    # 创建会话到 Redis
    state_manager.create_session(session_id, body.user_id)

    # 更新会话元数据
    session_key = f"SESSION_META:{session_id}"
    session_meta = {
        "title": body.title or "新对话",
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


@router.get("/search", response_model=SearchResponse)
async def search_sessions(
    q: str = Query(..., min_length=1, description="Search query"),
    user_id: Optional[str] = None
):
    """
    搜索会话
    
    搜索会话标题和消息内容，返回匹配的会话及消息片段
    """
    state_manager = get_state_manager()
    start_time = time.time()
    timeout = 3.0  # 3秒超时
    truncated = False
    results = []
    keyword = q.lower()
    
    if not state_manager.redis_client:
        return SearchResponse(
            results=[],
            total=0,
            query=q,
            truncated=False
        )
    
    # 使用 SCAN 命令分批扫描 SESSION_META:* 键
    cursor = 0
    session_ids = []
    
    while True:
        cursor, keys = state_manager.redis_client.scan(
            cursor=cursor,
            match="SESSION_META:*",
            count=100
        )
        session_ids.extend([key.split(":")[-1] for key in keys])
        
        # 如果超时或扫描完成，退出
        if cursor == 0 or time.time() - start_time > timeout:
            if cursor != 0:
                truncated = True
            break
    
    # 搜索每个会话
    for session_id in session_ids:
        # 检查是否超时
        if time.time() - start_time > timeout:
            truncated = True
            break
        
        # 获取会话元数据
        session_key = f"SESSION_META:{session_id}"
        meta = state_manager.redis_client.hgetall(session_key)
        title = meta.get("title", "新对话")
        updated_at = meta.get("updated_at", "")
        
        # 检查标题匹配
        title_matched = keyword in title.lower()
        matched_messages = []
        
        # 扫描消息历史
        dialog_key = f"DIALOG_HISTORY:{session_id}"
        messages = state_manager.redis_client.lrange(dialog_key, 0, -1)
        
        for msg_json in messages:
            # 检查是否超时
            if time.time() - start_time > timeout:
                truncated = True
                break
            
            try:
                msg = json.loads(msg_json)
                content = msg.get("content", "")
                role = msg.get("role", "")
                timestamp = msg.get("timestamp", "")
                
                # 检查内容匹配
                if keyword in content.lower():
                    # 提取片段（60字符前后）
                    idx = content.lower().find(keyword)
                    start_idx = max(0, idx - 60)
                    end_idx = min(len(content), idx + len(keyword) + 60)
                    snippet = content[start_idx:end_idx]
                    
                    # 如果不是从头开始，添加省略号
                    if start_idx > 0:
                        snippet = "..." + snippet
                    if end_idx < len(content):
                        snippet = snippet + "..."
                    
                    matched_messages.append(
                        SearchMessageSnippet(
                            role=role,
                            snippet=snippet,
                            timestamp=timestamp
                        )
                    )
                    
                    # 最多2个片段
                    if len(matched_messages) >= 2:
                        break
            except (json.JSONDecodeError, Exception):
                continue
        
        # 如果有匹配（标题或内容），添加到结果
        if title_matched or matched_messages:
            results.append(
                SearchSessionResult(
                    session_id=session_id,
                    title=title,
                    updated_at=updated_at,
                    matched_messages=matched_messages
                )
            )
        
        # 最多20个结果
        if len(results) >= 20:
            break
    
    # 按 updated_at 降序排序
    results.sort(key=lambda x: x.updated_at, reverse=True)
    
    return SearchResponse(
        results=results,
        total=len(results),
        query=q,
        truncated=truncated
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
