"""
WebSocket 管理器

职责：
- 管理前端 WebSocket 长连接
- 当 backend_save 完成时，推送 session_updated 事件给前端
- 前端收到后立即刷新该会话消息，无需轮询
"""
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter(tags=["WebSocket"])


class WSManager:
    """WebSocket 连接管理器（全局单例）"""

    def __init__(self):
        # session_id → set of connected WebSockets
        # 一个 session 可能有多个标签页连接
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)
        logger.debug(f"WebSocket connected, total={len(self._connections)}")

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)
        logger.debug(f"WebSocket disconnected, total={len(self._connections)}")

    async def notify_session_updated(self, session_id: str):
        """通知所有客户端某个会话的消息已更新"""
        if not self._connections:
            return

        message = json.dumps({"type": "session_updated", "session_id": session_id})
        dead = set()

        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)

        # 清理断开的连接
        self._connections -= dead
        if dead:
            logger.debug(f"Cleaned {len(dead)} dead WebSocket connections")


# 全局单例
ws_manager = WSManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # 保持连接活跃，接收 ping（浏览器不发消息也 ok）
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception as e:
        logger.debug(f"WebSocket error: {e}")
        ws_manager.disconnect(ws)
