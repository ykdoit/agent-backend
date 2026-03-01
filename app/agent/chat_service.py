"""
Chat Service - 聊天服务

职责：
- 处理聊天请求
- 管理消息历史注入
- 生成流式响应
- 生成会话标题

不包含：
- Agent 生命周期管理（由 AgentManager 负责）
"""
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
    """
    
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
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        流式聊天
        
        使用 AgentScope 官方的 stream_printing_messages 实现真正的流式输出。
        内部从 Redis 获取历史消息并注入 agent memory。
        
        Args:
            session_id: 会话 ID
            user_message: 当前用户消息
            user_context: 可选的用户上下文（user_id, user_name 等）
        
        Yields:
            OpenAI 兼容的 chat.completion.chunk 对象
        """
        from app.core.redis_manager import get_state_manager
        
        if not user_message:
            return
        
        # 获取或创建 Agent
        agent = await self._agent_manager.get_or_create_agent(session_id, user_context)
        
        # 注入历史消息到 agent memory（仅在首次，服务重启后恢复上下文）
        await self._inject_history(agent, session_id)
        
        # 创建用户消息
        user_msg = Msg(name="user", content=user_message, role="user")
        
        # 生成聊天 ID
        chat_id = f"chatcmpl-agent-{session_id[:8]}"
        is_first = True
        sent_content = ""  # 跟踪已发送的内容
        
        try:
            # 使用 AgentScope 官方的流式输出
            async for msg, last in stream_printing_messages(
                agents=[agent],
                coroutine_task=agent(user_msg)
            ):
                # 提取文本内容
                content = self._extract_content(msg)
                
                if content:
                    # 只发送新增部分
                    new_content = content[len(sent_content):]
                    if new_content:
                        sent_content = content
                        chunk = self._create_chunk(
                            chat_id=chat_id,
                            content=new_content,
                            is_first=is_first,
                            is_last=last,
                        )
                        is_first = False
                        yield chunk
        
        except Exception as e:
            logger.error(f"Agent stream error for session {session_id}: {e}")
            # 发送错误消息
            error_chunk = self._create_error_chunk(chat_id, str(e), is_first)
            yield error_chunk
    
    async def _inject_history(self, agent, session_id: str) -> None:
        """
        注入历史消息到 Agent Memory
        
        Args:
            agent: Agent 实例
            session_id: 会话 ID
        """
        # 如果 Agent memory 已有内容，跳过
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
        """
        从消息中提取文本内容
        
        Args:
            msg: AgentScope 消息对象
        
        Returns:
            提取的文本内容，如果没有则返回 None
        """
        if not hasattr(msg, 'content'):
            return None
        
        content = msg.content
        
        # 字符串类型
        if isinstance(content, str):
            return content
        
        # 列表类型（文本块列表）
        if isinstance(content, list):
            for block in content:
                # 字典类型块
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
                # 字符串类型块
                elif isinstance(block, str):
                    return block
        
        return None
    
    def _create_chunk(
        self,
        chat_id: str,
        content: str,
        is_first: bool,
        is_last: bool,
    ) -> ChatCompletionChunk:
        """
        创建流式响应块
        
        Args:
            chat_id: 聊天 ID
            content: 内容
            is_first: 是否是第一个块
            is_last: 是否是最后一个块
        
        Returns:
            ChatCompletionChunk 对象
        """
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
                    finish_reason="stop" if is_last else None,
                )
            ],
        )
    
    def _create_error_chunk(
        self,
        chat_id: str,
        error_message: str,
        is_first: bool,
    ) -> ChatCompletionChunk:
        """
        创建错误响应块
        
        Args:
            chat_id: 聊天 ID
            error_message: 错误消息
            is_first: 是否是第一个块
        
        Returns:
            ChatCompletionChunk 对象
        """
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
        """
        根据对话内容生成标题
        
        Args:
            user_message: 用户消息
            assistant_content: 助手回复内容
        
        Returns:
            生成的标题（不超过15个字）
        """
        # 取用户消息前100字符作为上下文
        context = user_message[:100]
        
        prompt = f"""请为以下对话生成一个简短的标题（不超过10个字），只返回标题本身，不要加引号或其他标点：

用户问题：{context}

标题："""
        
        try:
            # 使用 Agent 的模型生成标题
            response = await self._agent_manager._model(
                messages=[{"role": "user", "content": prompt}],
            )
            title = response.choices[0].message.content.strip()
            
            # 限制标题长度
            if len(title) > 15:
                title = title[:15] + "..."
            
            logger.info(f"Generated title: {title}")
            return title
        
        except Exception as e:
            logger.error(f"生成标题失败: {e}")
            # 降级为截取法
            return user_message[:15] + ("..." if len(user_message) > 15 else "")
