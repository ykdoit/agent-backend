"""
Redis 状态管理器 - 会话和对话历史存储
"""
import redis
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from loguru import logger
from enum import Enum


class AgentState(Enum):
    """Agent 状态枚举"""
    IDLE = "idle"
    PROCESSING = "processing"
    SUSPENDED = "suspended"
    RESUMING = "resuming"
    COMPLETED = "completed"
    ERROR = "error"


class DistributedLock:
    """基于 Redis 的分布式锁"""
    
    def __init__(self, redis_client: redis.Redis, lock_name: str, 
                 timeout: int = 10, retry_interval: float = 0.1):
        self.redis_client = redis_client
        self.lock_name = f"LOCK:{lock_name}"
        self.timeout = timeout
        self.retry_interval = retry_interval
        self.lock_token = str(json.dumps({"ts": datetime.now().isoformat()}))
        self._locked = False
    
    def acquire(self, blocking: bool = True, timeout: float = None) -> bool:
        """获取锁"""
        start_time = datetime.now().timestamp()
        
        while True:
            acquired = self.redis_client.set(
                self.lock_name, 
                self.lock_token, 
                nx=True,
                ex=self.timeout
            )
            
            if acquired:
                self._locked = True
                return True
            
            if not blocking:
                return False
            
            if timeout and (datetime.now().timestamp() - start_time) > timeout:
                return False
            
            import time
            time.sleep(self.retry_interval)
    
    def release(self) -> bool:
        """释放锁"""
        if not self._locked:
            return True
        
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        
        try:
            result = self.redis_client.eval(lua_script, 1, self.lock_name, self.lock_token)
            if result:
                self._locked = False
                return True
            return False
        except Exception as e:
            logger.error(f"释放锁异常: {e}")
            return False
    
    def __enter__(self):
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class RedisStateManager:
    """Redis 状态管理器 - 会话和对话历史"""
    
    def __init__(self, host: str = 'localhost', port: int = 6379, db: int = 0):
        """初始化 Redis 连接"""
        try:
            self.redis_client = redis.Redis(
                host=host, 
                port=port, 
                db=db, 
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            self.redis_client.ping()
            logger.info(f"Redis 连接成功: {host}:{port}")
        except Exception as e:
            logger.error(f"Redis 连接失败: {e}")
            self.redis_client = None
    
    def _get_session_key(self, session_id: str) -> str:
        return f"SESSION_STATE:{session_id}"
    
    def _get_dialog_key(self, session_id: str) -> str:
        return f"DIALOG_HISTORY:{session_id}"
    
    def _get_distributed_lock(self, lock_name: str) -> DistributedLock:
        """获取分布式锁"""
        return DistributedLock(self.redis_client, lock_name)
    
    # ==================== 会话管理 ====================
    
    def create_session(self, session_id: str, user_id: str = None) -> bool:
        """创建新会话"""
        if not self.redis_client:
            return False
        
        lock = self._get_distributed_lock(f"session:{session_id}")
        
        try:
            if lock.acquire(blocking=True, timeout=5):
                key = self._get_session_key(session_id)
                
                if self.redis_client.exists(key):
                    return True
                
                session_data = {
                    "session_id": session_id,
                    "user_id": user_id or f"user_{session_id}",
                    "created_at": datetime.now().isoformat(),
                    "last_active": datetime.now().isoformat(),
                    "status": "active"
                }
                
                self.redis_client.hset(key, mapping=session_data)
                self.redis_client.expire(key, 24 * 3600)
                return True
        except Exception as e:
            logger.error(f"创建会话失败: {e}")
            return False
        finally:
            lock.release()
        
        return False
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话状态"""
        if not self.redis_client:
            return None
        
        try:
            key = self._get_session_key(session_id)
            return self.redis_client.hgetall(key) or None
        except Exception as e:
            logger.error(f"获取会话失败: {e}")
            return None
    
    # ==================== 对话历史 ====================
    
    def append_message(self, session_id: str, role: str, content: str, metadata: Dict = None) -> bool:
        """追加对话消息"""
        if not self.redis_client:
            return False
        
        try:
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat()
            }
            
            if metadata:
                message["metadata"] = metadata
            
            key = self._get_dialog_key(session_id)
            
            self.redis_client.lpush(key, json.dumps(message, ensure_ascii=False))
            self.redis_client.ltrim(key, 0, 99)  # 保留最近 100 条
            self.redis_client.expire(key, 24 * 3600)
            
            return True
        except Exception as e:
            logger.error(f"添加消息失败: {e}")
            return False
    
    def get_conversation_history(self, session_id: str, limit: int = 10) -> List[Dict]:
        """获取对话历史（按时间正序）"""
        if not self.redis_client:
            return []
        
        try:
            key = self._get_dialog_key(session_id)
            # lpush 将新消息放在头部，所以需要反转顺序
            messages = self.redis_client.lrange(key, 0, limit - 1)
            return [json.loads(msg) for msg in reversed(messages)]
        except Exception as e:
            logger.error(f"获取对话历史失败: {e}")
            return []
    
    def clear_conversation(self, session_id: str) -> bool:
        """清除对话历史"""
        if not self.redis_client:
            return False
        
        try:
            key = self._get_dialog_key(session_id)
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"清除对话历史失败: {e}")
            return False
    
    def update_session_title(self, session_id: str, title: str) -> bool:
        """更新会话标题"""
        if not self.redis_client:
            return False
        
        try:
            session_key = f"SESSION_META:{session_id}"
            self.redis_client.hset(session_key, "title", title)
            self.redis_client.hset(session_key, "updated_at", datetime.now().isoformat())
            logger.info(f"[Session {session_id}] Title updated: {title}")
            return True
        except Exception as e:
            logger.error(f"更新会话标题失败: {e}")
            return False
    
    def get_message_count(self, session_id: str) -> int:
        """获取消息数量"""
        if not self.redis_client:
            return 0
        
        try:
            key = self._get_dialog_key(session_id)
            return self.redis_client.llen(key)
        except Exception as e:
            logger.error(f"获取消息数量失败: {e}")
            return 0
    
    # ==================== 健康检查 ====================
    
    def health_check(self) -> bool:
        """检查 Redis 连接"""
        if not self.redis_client:
            return False
        try:
            self.redis_client.ping()
            return True
        except:
            return False


# ==================== Agent 状态机 ====================

class AgentStateMachine:
    """Agent 状态机 - 管理 suspended/resume 状态"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.state_transitions = {
            AgentState.IDLE: [AgentState.PROCESSING],
            AgentState.PROCESSING: [AgentState.SUSPENDED, AgentState.COMPLETED, AgentState.ERROR],
            AgentState.SUSPENDED: [AgentState.RESUMING],
            AgentState.RESUMING: [AgentState.PROCESSING, AgentState.ERROR],
            AgentState.COMPLETED: [AgentState.IDLE],
            AgentState.ERROR: [AgentState.IDLE]
        }
    
    def _get_state_key(self, session_id: str) -> str:
        return f"AGENT_STATE:{session_id}"
    
    async def get_state(self, session_id: str) -> Optional[AgentState]:
        """获取当前状态"""
        if not self.redis:
            return None
        
        try:
            key = self._get_state_key(session_id)
            state_str = self.redis.hget(key, "state")
            if state_str:
                return AgentState(state_str)
            return AgentState.IDLE
        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return None
    
    async def set_state(self, session_id: str, state: AgentState, context: Dict = None) -> bool:
        """设置状态"""
        if not self.redis:
            return False
        
        try:
            key = self._get_state_key(session_id)
            data = {
                "state": state.value,
                "updated_at": datetime.now().isoformat()
            }
            if context:
                data["context"] = json.dumps(context)
            
            self.redis.hset(key, mapping=data)
            self.redis.expire(key, 24 * 3600)
            return True
        except Exception as e:
            logger.error(f"设置状态失败: {e}")
            return False
    
    def get_suspended_sessions(self) -> List[str]:
        """获取所有挂起的会话"""
        if not self.redis:
            return []
        
        try:
            sessions = []
            for key in self.redis.scan_iter(match="AGENT_STATE:*"):
                state = self.redis.hget(key, "state")
                if state == AgentState.SUSPENDED.value:
                    session_id = key.split(":")[-1]
                    sessions.append(session_id)
            return sessions
        except Exception as e:
            logger.error(f"获取挂起会话失败: {e}")
            return []


# ==================== 全局实例 ====================

_state_manager: RedisStateManager | None = None
_state_machine: AgentStateMachine | None = None


def get_state_manager() -> RedisStateManager:
    """获取全局状态管理器实例"""
    global _state_manager
    if _state_manager is None:
        _state_manager = RedisStateManager()
    return _state_manager


def get_state_machine() -> AgentStateMachine:
    """获取全局状态机实例"""
    global _state_machine
    if _state_machine is None:
        _state_machine = AgentStateMachine(get_state_manager().redis_client)
    return _state_machine
