"""Agent manager: initialise agentscope, create and cache ReActAgent per session."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx
import agentscope
from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit

from app.config import AppConfig, get_app_config
from app.mcp import MCPManager
from app.skill.loader import load_skills, get_all_skill_prompts
from app.agent.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)

# 获取环境变量，默认为 yangkang
STAFF_DOMAIN = os.getenv("STAFF_DOMAIN", "yangkang")


class AgentManager:
    """Create, cache and manage ReActAgent instances (one per session) in memory."""

    def __init__(self, config: AppConfig = None) -> None:
        self._config = config or get_app_config()
        self._model: OpenAIChatModel | None = None
        self._formatter: OpenAIChatFormatter | None = None
        self._toolkit:  Toolkit | None = None
        self._prompt_builder = PromptBuilder()  # 提示词构建器
        # 保持Agent实例在内存中
        self._agents: dict[str, ReActAgent] = {}
        self._lock = asyncio.Lock()
        self._skill_list: list[dict[str, str]] = []
        self._mcp_manager = MCPManager()

    async def initialize(self) -> None:
        """Initialise agentscope runtime, model, toolkit, skills and MCP tools."""
        agentscope.init(project="agent-service", logging_level="INFO")

        llm = self._config.llm
        # Prepare client_kwargs with SSL verification disabled for local HTTPS
        # Increase timeout to 120s for slow LLM responses
        client_kwargs = {
            "base_url": llm.base_url,
            "http_client": httpx.AsyncClient(verify=False, timeout=httpx.Timeout(120.0)),
        }
        self._model = OpenAIChatModel(
            model_name=llm.model_name,
            api_key=llm.api_key or None,
            client_kwargs=client_kwargs,
            generate_kwargs={
                "temperature": llm.temperature,
                "max_tokens": llm.max_tokens,
            },
            stream_tool_parsing=True,
        )
        self._formatter = OpenAIChatFormatter()

        self._toolkit = Toolkit()
        
        # Register global utility tools (time_oracle) - before skill loading
        await self._register_global_tools()
        
        self._skill_list = load_skills(self._config.skills_dir, self._toolkit)

        # Load MCP remote tools (must be after toolkit is created)
        await self._mcp_manager.setup(self._config.mcp, self._toolkit)

        # 获取工具描述 + Skill 正文提示词
        tool_prompt = self._toolkit.get_agent_skill_prompt() or ""
        skill_prompts = get_all_skill_prompts()
        self._prompt_builder.set_skill_prompt(f"{tool_prompt}\n\n{skill_prompts}" if skill_prompts else tool_prompt)

        logger.info(
            "AgentManager initialised with %d skill(s), %d MCP tool(s), 2 global tool(s)",
            len(self._skill_list),
            self._mcp_manager.tool_count,
        )
        logger.info("Registered tools: %s", list(self._toolkit.tools))

    async def _register_global_tools(self) -> None:
        """注册全局工具，所有 Skill 共享。"""
        import inspect
        from agentscope.message import TextBlock
        from agentscope.tool import ToolResponse
        
        def _wrap_as_tool_response(func):
            """Wrap a plain function so that its return value is a ToolResponse."""
            async def _wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                if isinstance(result, ToolResponse):
                    return result
                return ToolResponse(content=[TextBlock(type="text", text=str(result))])
            
            _wrapper.__name__ = func.__name__
            _wrapper.__qualname__ = func.__qualname__
            _wrapper.__doc__ = func.__doc__
            _wrapper.__module__ = func.__module__
            _wrapper.__annotations__ = func.__annotations__
            _wrapper.__wrapped__ = func
            orig_sig = inspect.signature(func)
            _wrapper.__signature__ = orig_sig.replace(return_annotation=ToolResponse)
            return _wrapper
        
        # Import and register time_oracle as global tool
        from app.utils.time_oracle import time_oracle, get_system_time_context
        
        # 创建全局工具组
        self._toolkit.create_tool_group(
            group_name="_global",
            description="全局工具，所有技能共享",
            active=True,
        )
        
        self._toolkit.register_tool_function(
            _wrap_as_tool_response(time_oracle),
            group_name="_global",
        )
        self._toolkit.register_tool_function(
            _wrap_as_tool_response(get_system_time_context),
            group_name="_global",
        )
        
        logger.info("Registered global tools: time_oracle, get_system_time_context")

    async def shutdown(self) -> None:
        """Shutdown MCP connections and clean up resources."""
        await self._mcp_manager.shutdown()
        self._agents.clear()
        logger.info("AgentManager shutdown complete.")

    @property
    def skill_list(self) -> list[dict[str, str]]:
        return list(self._skill_list)

    async def get_or_create_agent(
        self,
        session_id: str,
        user_context: dict[str, str | None] | None = None,
    ) -> ReActAgent:
        """Get or create an agent for the session with user context.
        
        Args:
            session_id: The session identifier
            user_context: Optional user context containing user_id, user_name, staff_domain, etc.
        """
        async with self._lock:
            if session_id not in self._agents:
                # Build sys_prompt with user context
                staff_id = user_context.get("user_id") if user_context else None
                staff_domain = user_context.get("staff_domain") if user_context else None
                staff_name = user_context.get("user_name") if user_context else None
                sys_prompt = self._prompt_builder.build_with_defaults(
                    staff_id=staff_id,
                    staff_domain=staff_domain,
                    staff_name=staff_name,
                    default_domain=STAFF_DOMAIN,
                )
                
                agent = ReActAgent(
                    name=f"agent_{session_id[:8]}",
                    sys_prompt=sys_prompt,
                    model=self._model,  # type: ignore[arg-type]
                    formatter=self._formatter,  # type: ignore[arg-type]
                    toolkit=self._toolkit,
                    memory=InMemoryMemory(),
                    max_iters=10,
                )
                self._agents[session_id] = agent
                logger.info("Created agent for session %s with user %s", session_id, staff_domain or STAFF_DOMAIN)
            return self._agents[session_id]

    async def remove_agent(self, session_id: str) -> None:
        async with self._lock:
            self._agents.pop(session_id, None)

    async def chat_stream(
        self,
        session_id: str,
        user_message: str,
        user_context: dict[str, str | None] | None = None,
    ):
        """Stream chat via Agent using AgentScope's stream_printing_messages.
    
        使用 AgentScope 官方的 stream_printing_messages 实现真正的流式输出。
        内部从 Redis 获取历史消息并注入 agent memory。
    
        Args:
            session_id: Session ID for context
            user_message: 当前用户消息
            user_context: Optional user context containing user_id, user_name, etc.
    
        Yields:
            OpenAI-compatible chat.completion.chunk objects.
        """
        from openai.types.chat import ChatCompletionChunk
        from openai.types.chat.chat_completion_chunk import Choice, ChoiceDelta
        from agentscope.pipeline import stream_printing_messages
        from app.core.redis_manager import get_state_manager
    
        if not user_message:
            return
    
        # Get or create agent for this session
        agent = await self.get_or_create_agent(session_id, user_context)
        
        # 注入历史消息到 agent memory（仅在首次，服务重启后恢复上下文）
        if (await agent.memory.size()) == 0:
            state_manager = get_state_manager()
            history_messages = state_manager.get_conversation_history(session_id, limit=10)
            for msg in history_messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content:
                    memory_msg = Msg(name=role, content=content, role=role)
                    agent.memory.add(memory_msg)
    
        user_msg = Msg(name="user", content=user_message, role="user")
    
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
                content = None
                if hasattr(msg, 'content'):
                    if isinstance(msg.content, str):
                        content = msg.content
                    elif isinstance(msg.content, list):
                        # 处理文本块列表
                        for block in msg.content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                content = block.get("text", "")
                                break
                            elif isinstance(block, str):
                                content = block
                                break
                    
                if content:
                    # 只发送新增部分
                    new_content = content[len(sent_content):]
                    if new_content:
                        sent_content = content
                        chunk = ChatCompletionChunk(
                            id=chat_id,
                            object="chat.completion.chunk",
                            created=int(time.time()),
                            model=self._config.llm.model_name,
                            choices=[
                                Choice(
                                    index=0,
                                    delta=ChoiceDelta(
                                        role="assistant" if is_first else None,
                                        content=new_content,
                                    ),
                                    finish_reason="stop" if last else None,
                                )
                            ],
                        )
                        is_first = False
                        yield chunk
    
        except Exception as e:
            logger.error("Agent stream error for session %s: %s", session_id, e)
            # 发送错误消息
            error_chunk = ChatCompletionChunk(
                id=chat_id,
                object="chat.completion.chunk",
                created=int(time.time()),
                model=self._config.llm.model_name,
                choices=[
                    Choice(
                        index=0,
                        delta=ChoiceDelta(
                            role="assistant" if is_first else None,
                            content=f"处理失败: {e}",
                        ),
                        finish_reason="stop",
                    )
                ],
            )
            yield error_chunk

    async def generate_title(self, user_message: str, assistant_content: str) -> str:
        """根据对话内容生成标题"""
        # 取用户消息前50字符作为上下文
        context = user_message[:100]
        
        prompt = f"""请为以下对话生成一个简短的标题（不超过10个字），只返回标题本身，不要加引号或其他标点：

用户问题：{context}

标题："""

        try:
            # 使用同一个模型生成标题
            response = await self._model(
                messages=[{"role": "user", "content": prompt}],
            )
            title = response.choices[0].message.content.strip()
            # 限制标题长度
            if len(title) > 15:
                title = title[:15] + "..."
            return title
        except Exception as e:
            logger.error(f"生成标题失败: {e}")
            # 降级为截取法
            return user_message[:15] + ("..." if len(user_message) > 15 else "")


# 全局实例
_agent_manager: AgentManager | None = None


async def get_agent_manager() -> AgentManager:
    """获取 AgentManager 单例实例"""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AgentManager()
        await _agent_manager.initialize()
    return _agent_manager
