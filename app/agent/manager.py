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
from app.skill.loader import get_skill_registry
from app.agent.prompt_builder import PromptBuilder
from app.agent.tools import register_skill_tools, register_global_tools

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
        # Prepare client_kwargs with SSL verification enabled by default
        # Increase timeout to 120s for slow LLM responses
        _verify_ssl = os.getenv("VERIFY_SSL", "true").lower() != "false"
        client_kwargs = {
            "base_url": llm.base_url,
            "http_client": httpx.AsyncClient(verify=_verify_ssl, timeout=httpx.Timeout(120.0)),
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

        # Register global utility tools (time_oracle)
        register_global_tools(self._toolkit)

        # 初始化 Skill 注册中心（延迟加载）
        skill_registry = get_skill_registry()

        # 注册 skill 工具（read_skill）
        register_skill_tools(self._toolkit, skill_registry)

        # 获取技能列表
        self._skill_list = skill_registry.list_all()

        # Load MCP remote tools (must be after toolkit is created)
        await self._mcp_manager.setup(self._config.mcp, self._toolkit)

        # 获取工具描述 + 技能目录（不是正文）
        tool_prompt = self._toolkit.get_agent_skill_prompt() or ""
        skill_catalog = skill_registry.get_skill_catalog()
        self._prompt_builder.set_skill_catalog(f"{tool_prompt}\n\n{skill_catalog}")

        logger.info(
            "AgentManager initialised with %d skill(s), %d MCP tool(s), 2 global tool(s)",
            len(self._skill_list),
            self._mcp_manager.tool_count,
        )
        logger.info("Registered tools: %s", list(self._toolkit.tools))

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
                
                # 输出提示词信息
                logger.info(f"Creating agent for session {session_id}")
                logger.info(f"System prompt length: {len(sys_prompt)} chars (~{len(sys_prompt)//4} tokens)")

                # 同时在日志中输出完整提示词（可选，设置环境变量 DEBUG_PROMPT=1 启用）
                if os.getenv("DEBUG_PROMPT"):
                    logger.info(f"\n{'='*80}\nFULL SYSTEM PROMPT:\n{'='*80}\n{sys_prompt}\n{'='*80}")

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

async def get_agent_manager() -> AgentManager:
    """获取 AgentManager 单例实例（double-checked locking）"""
    global _agent_manager, _agent_manager_lock
    if _agent_manager is None:
        if _agent_manager_lock is None:
            _agent_manager_lock = asyncio.Lock()
        async with _agent_manager_lock:
            if _agent_manager is None:
                _agent_manager = AgentManager()
                await _agent_manager.initialize()
    return _agent_manager


# 全局实例
_agent_manager: AgentManager | None = None
_agent_manager_lock: asyncio.Lock | None = None
