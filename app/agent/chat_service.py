"""
Chat Service - 聊天服务

职责：
- 处理聊天请求
- 管理消息历史注入
- 生成流式响应（含状态推送）
- 生成会话标题

不包含：
- Agent 生命周期管理（由 AgentManager 负责）
"""
import asyncio
import json
import time
from typing import AsyncGenerator

from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta
from agentscope.pipeline import stream_printing_messages
from agentscope.message import Msg
from loguru import logger

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent.manager import AgentManager


class ChatService:
    """
    聊天服务

    负责处理聊天相关的业务逻辑，包括：
    - 流式聊天响应
    - 历史消息注入
    - 会话标题生成
    - 状态推送（工具调用过程）
    """

    # Agent 执行超时时间（秒）
    AGENT_TIMEOUT = 300  # 5 分钟

    def __init__(self, agent_manager: "AgentManager"):
        """
        初始化聊天服务

        Args:
            agent_manager: Agent 管理器实例
        """
        self._agent_manager = agent_manager
    
    async def chat_stream(
        self,
        session_id: str,
        user_message: str,
        user_context: dict[str, str | None] | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天（带状态推送）
        
        使用 AgentScope 官方的 stream_printing_messages 实现真正的流式输出。
        同时监控工具调用，推送状态事件。
        
        Args:
            session_id: 会话 ID
            user_message: 当前用户消息
            user_context: 可选的用户上下文（user_id, user_name 等）
        
        Yields:
            SSE 格式字符串 (data: {...})
        """
        from app.core.redis_manager import get_state_manager
        
        if not user_message:
            return
        
        # 获取或创建 Agent
        agent = await self._agent_manager.get_or_create_agent(session_id, user_context)
        
        # 注入历史消息到 agent memory
        await self._inject_history(agent, session_id)
        
        # 创建用户消息
        user_msg = Msg(name="user", content=user_message, role="user")
        
        # 生成聊天 ID
        chat_id = f"chatcmpl-agent-{session_id[:8]}"
        is_first = True
        sent_content = ""
        tool_calls_seen = set()
        
        try:
            # 发送初始状态
            yield self._create_status_event("thinking", "💭 思考中...")

            # 创建消息队列
            queue = asyncio.Queue()
            agent.set_msg_queue_enabled(True, queue)

            # 启动agent任务（带超时保护）
            agent_task = asyncio.create_task(agent(user_msg))

            # 超时计时
            start_time = time.time()

            # 持续监听消息队列
            while True:
                # 检查总超时
                elapsed = time.time() - start_time
                if elapsed > self.AGENT_TIMEOUT:
                    logger.warning(f"[{session_id}] Agent execution timeout after {elapsed:.1f}s")
                    agent_task.cancel()
                    try:
                        await agent_task
                    except asyncio.CancelledError:
                        pass
                    error_chunk = self._create_error_chunk(chat_id, "执行超时，请稍后重试", is_first)
                    yield f"data: {error_chunk.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                try:
                    # 等待消息，超时检查任务是否完成
                    printing_msg = await asyncio.wait_for(queue.get(), timeout=0.5)

                    # 检查是否是结束信号
                    if isinstance(printing_msg, str):
                        continue

                    # 解析消息
                    try:
                        msg, last, _ = printing_msg
                    except (TypeError, ValueError) as e:
                        logger.warning(f"[{session_id}] Invalid message format: {e}")
                        continue

                    # 检测工具调用
                    tool_use_blocks = msg.get_content_blocks("tool_use")
                    for block in tool_use_blocks:
                        tool_name = block.get("name", "") if isinstance(block, dict) else ""
                        if tool_name and tool_name not in tool_calls_seen:
                            tool_calls_seen.add(tool_name)
                            yield self._create_status_event("tool_call", f"🔄 调用工具：{tool_name}")
                            logger.info(f"[{session_id}] Tool call: {tool_name}")

                    # 提取并推送文本内容
                    content = self._extract_content(msg)
                    if content:
                        # 情况1：增量更新（新内容以已发送内容开头）
                        if len(content) > len(sent_content) and content.startswith(sent_content):
                            new_content = content[len(sent_content):]
                            if new_content:
                                logger.debug(f"[{session_id}] Incremental content: +{len(new_content)} chars")
                                sent_content = content
                                chunk = self._create_chunk(chat_id, new_content, is_first)
                                is_first = False
                                yield f"data: {chunk.model_dump_json()}\n\n"
                        # 情况2：内容被完全替换（工具调用后的最终响应）
                        elif content != sent_content:
                            logger.info(f"[{session_id}] Content replaced, sending full content ({len(content)} chars)")
                            sent_content = content
                            chunk = self._create_chunk(chat_id, content, is_first)
                            is_first = False
                            yield f"data: {chunk.model_dump_json()}\n\n"
                        else:
                            logger.debug(f"[{session_id}] No new content to send")

                except asyncio.TimeoutError:
                    # 超时，检查agent任务是否完成或异常
                    if agent_task.done():
                        # 检查任务是否有异常
                        if agent_task.exception():
                            exc = agent_task.exception()
                            logger.error(f"[{session_id}] Agent task failed: {exc}")
                            error_chunk = self._create_error_chunk(chat_id, f"执行失败: {exc}", is_first)
                            yield f"data: {error_chunk.model_dump_json()}\n\n"
                            yield "data: [DONE]\n\n"
                            return

                        # 任务完成，处理剩余消息后退出
                        while not queue.empty():
                            try:
                                printing_msg = queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break

                            if isinstance(printing_msg, str):
                                continue

                            try:
                                msg, last, _ = printing_msg
                            except (TypeError, ValueError):
                                continue

                            # 检测工具调用
                            tool_use_blocks = msg.get_content_blocks("tool_use")
                            for block in tool_use_blocks:
                                tool_name = block.get("name", "") if isinstance(block, dict) else ""
                                if tool_name and tool_name not in tool_calls_seen:
                                    tool_calls_seen.add(tool_name)
                                    yield self._create_status_event("tool_call", f"🔄 调用工具：{tool_name}")
                                    logger.info(f"[{session_id}] Tool call: {tool_name}")

                            # 提取并推送文本内容
                            content = self._extract_content(msg)
                            if content and content != sent_content:
                                # 发送完整内容（可能是工具调用后的最终响应）
                                logger.info(f"[{session_id}] Final content: {len(content)} chars")
                                sent_content = content
                                chunk = self._create_chunk(chat_id, content, is_first)
                                is_first = False
                                yield f"data: {chunk.model_dump_json()}\n\n"

                        # 发送最终块（包含 finish_reason）
                        final_chunk = self._create_final_chunk(chat_id)
                        yield f"data: {final_chunk.model_dump_json()}\n\n"
                        logger.info(f"[{session_id}] Agent completed in {time.time() - start_time:.1f}s")
                        break

                except asyncio.CancelledError:
                    logger.info(f"[{session_id}] Stream cancelled by client")
                    agent_task.cancel()
                    raise

        except asyncio.CancelledError:
            # 客户端断开连接
            logger.info(f"[{session_id}] Client disconnected")
            raise

        except Exception as e:
            logger.error(f"Agent stream error for session {session_id}: {e}", exc_info=True)
            error_chunk = self._create_error_chunk(chat_id, str(e), is_first)
            yield f"data: {error_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"
    
    def _create_status_event(self, stage: str, text: str) -> str:
        """
        创建状态事件
        
        Args:
            stage: 阶段 (thinking, tool_call, completed)
            text: 状态文本（含 emoji）
        
        Returns:
            SSE 格式字符串
        """
        event = {
            "event": "status",
            "stage": stage,
            "text": text
        }
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    
    async def _inject_history(self, agent, session_id: str) -> None:
        """注入历史消息到 Agent Memory"""
        if (await agent.memory.size()) > 0:
            return
        
        from app.core.redis_manager import get_state_manager
        
        state_manager = get_state_manager()
        history_messages = state_manager.get_conversation_history(session_id, limit=10)
        
        for msg in history_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                memory_msg = Msg(name=role, content=content, role=role)
                await agent.memory.add(memory_msg)
        
        logger.info(f"Injected {len(history_messages)} history messages for session {session_id}")
    
    def _extract_content(self, msg) -> str | None:
        """从消息中提取文本内容，拼接所有 text block"""
        if not hasattr(msg, 'content'):
            return None

        content = msg.content

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            # 拼接所有 text block，而不是只返回第一个
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        text_parts.append(text)
                elif isinstance(block, str):
                    text_parts.append(block)

            return "".join(text_parts) if text_parts else None

        return None
    
    def _create_chunk(self, chat_id: str, content: str, is_first: bool) -> ChatCompletionChunk:
        """创建流式响应块（不包含 finish_reason）"""
        return ChatCompletionChunk(
            id=chat_id,
            object="chat.completion.chunk",
            created=int(time.time()),
            model=self._agent_manager._config.llm.model_name,
            choices=[
                Choice(
                    index=0,
                    delta=ChoiceDelta(
                        role="assistant" if is_first else None,
                        content=content,
                    ),
                    finish_reason=None,
                )
            ],
        )

    def _create_final_chunk(self, chat_id: str) -> ChatCompletionChunk:
        """创建最终响应块（仅包含 finish_reason）"""
        return ChatCompletionChunk(
            id=chat_id,
            object="chat.completion.chunk",
            created=int(time.time()),
            model=self._agent_manager._config.llm.model_name,
            choices=[
                Choice(
                    index=0,
                    delta=ChoiceDelta(
                        role=None,
                        content=None,
                    ),
                    finish_reason="stop",
                )
            ],
        )
    
    def _create_error_chunk(self, chat_id: str, error_message: str, is_first: bool) -> ChatCompletionChunk:
        """创建错误响应块"""
        return ChatCompletionChunk(
            id=chat_id,
            object="chat.completion.chunk",
            created=int(time.time()),
            model=self._agent_manager._config.llm.model_name,
            choices=[
                Choice(
                    index=0,
                    delta=ChoiceDelta(
                        role="assistant" if is_first else None,
                        content=f"处理失败: {error_message}",
                    ),
                    finish_reason="stop",
                )
            ],
        )
    
    async def generate_title(self, user_message: str, assistant_content: str) -> str:
        """根据对话内容生成标题"""
        context = user_message[:100]
        
        prompt = f"""请为以下对话生成一个简短的标题（不超过10个字），只返回标题本身，不要加引号或其他标点：

用户问题：{context}

标题："""
        
        try:
            response = await self._agent_manager._model(
                messages=[{"role": "user", "content": prompt}],
            )
            
            # ChatResponse.content 是 TextBlock 列表，需要提取 text 字段
            title = ""
            for block in response.content:
                if block.get("type") == "text":
                    title += block.get("text", "")
            
            title = title.strip()
            
            if len(title) > 15:
                title = title[:15] + "..."
            
            logger.info(f"Generated title: {title}")
            return title
        
        except Exception as e:
            logger.error(f"生成标题失败: {e}")
            return user_message[:15] + ("..." if len(user_message) > 15 else "")
