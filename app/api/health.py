"""
基础 API：健康检查、技能列表、状态管理
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from loguru import logger
from typing import Optional
import json

from app.core.redis_manager import get_state_manager, get_state_machine, AgentState as StateMachineState
from app.agent import get_agent_manager, AgentManager

router = APIRouter(tags=["Health"])

# 全局 AgentManager 引用（由 main.py 设置）
_agent_manager: AgentManager | None = None


def set_agent_manager(manager: AgentManager):
    """设置 AgentManager 引用"""
    global _agent_manager
    _agent_manager = manager


@router.get("/")
async def root():
    """根路由"""
    return {
        "name": "Enterprise Office Agent API",
        "version": "1.0.0",
        "status": "running"
    }


@router.get("/health")
async def health():
    """健康检查"""
    return {"status": "healthy"}


@router.get("/skills", tags=["Skills"])
async def list_skills():
    """
    获取所有可用的 Skills
    
    返回每个 skill 的名称、描述、触发词
    """
    if _agent_manager is None:
        return []
    return _agent_manager.skill_list


# ============== 状态管理 API ==============

@router.get("/sessions/{session_id}/state", tags=["State Management"])
async def get_session_state(session_id: str):
    """
    获取会话状态
    
    返回当前会话的状态信息
    """
    state_machine = get_state_machine()
    state = await state_machine.get_state(session_id)
    
    # 获取挂起的上下文（如果有）
    suspended_context = None
    if state == StateMachineState.SUSPENDED:
        redis_client = get_state_manager().redis_client
        if redis_client:
            context_key = f"AGENT_CONTEXT:{session_id}"
            context_data = redis_client.hgetall(context_key)
            if context_data:
                try:
                    suspended_context = json.loads(context_data.get("data", "{}"))
                except json.JSONDecodeError:
                    pass
    
    return {
        "session_id": session_id,
        "state": state.value if state else "unknown",
        "suspended_context": suspended_context
    }


@router.get("/sessions/suspended", tags=["State Management"])
async def list_suspended_sessions():
    """获取所有挂起的会话列表"""
    state_machine = get_state_machine()
    suspended = state_machine.get_suspended_sessions()
    
    return {
        "suspended_sessions": suspended,
        "count": len(suspended)
    }
