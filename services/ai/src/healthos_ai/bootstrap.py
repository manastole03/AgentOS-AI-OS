import logging
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from healthos_ai.config import Settings
from healthos_ai.db.session import create_database_engine, create_session_factory
from healthos_ai.llm import LLMGateway
from healthos_ai.mcp import load_mcp_tools
from healthos_ai.memory import MemoryRepository
from healthos_ai.observability.audit import AuditLogger
from healthos_ai.orchestration.graph import AgentOrchestrator
from healthos_ai.queue import RunService
from healthos_ai.rag import KnowledgeRepository
from healthos_ai.security import DataCipher
from healthos_ai.teams.factory import TeamAgentFactory
from healthos_ai.tools import AgentMessageRepository, build_tools

logger = logging.getLogger(__name__)


@dataclass
class RuntimeResources:
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    llm: LLMGateway
    knowledge: KnowledgeRepository
    memories: MemoryRepository
    audit: AuditLogger
    orchestrator: AgentOrchestrator
    runs: RunService
    checkpointer_ready: bool
    cipher: DataCipher


@asynccontextmanager
async def build_runtime(settings: Settings) -> AsyncIterator[RuntimeResources]:
    engine = create_database_engine(settings.database_url.get_secret_value())
    sessions = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=True)
    cipher = DataCipher(settings.ai_data_encryption_key.get_secret_value())
    llm = LLMGateway(settings)
    knowledge = KnowledgeRepository(sessions, llm)
    memories = MemoryRepository(sessions, llm)
    audit = AuditLogger(sessions)
    message_repository = AgentMessageRepository(sessions, cipher)
    stack = AsyncExitStack()
    checkpointer: Any = None
    checkpointer_ready = False
    try:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            from langgraph.checkpoint.serde.encrypted import EncryptedSerializer

            os.environ["LANGGRAPH_AES_KEY"] = settings.langgraph_aes_key.get_secret_value()
            serde = EncryptedSerializer.from_pycryptodome_aes()
            checkpointer = await stack.enter_async_context(
                AsyncPostgresSaver.from_conn_string(settings.psycopg_database_url, serde=serde)
            )
            await checkpointer.setup()
            checkpointer_ready = True
        except Exception as exc:
            # Keep liveness up so Kubernetes can report dependency failure through readiness.
            logger.warning(
                "langgraph_checkpointer_unavailable", extra={"error_type": type(exc).__name__}
            )
        mcp_tools = await load_mcp_tools(settings)
        tools = build_tools(knowledge, memories, message_repository, audit)
        teams = TeamAgentFactory(settings, llm, tools, mcp_tools)
        orchestrator = AgentOrchestrator(
            settings, llm, teams, knowledge, memories, audit, checkpointer
        )
        runs = RunService(
            sessions,
            redis,
            cipher,
            audit,
            orchestrator,
            settings.queue_stream,
            settings.run_event_ttl_seconds,
        )
        yield RuntimeResources(
            engine,
            sessions,
            redis,
            llm,
            knowledge,
            memories,
            audit,
            orchestrator,
            runs,
            checkpointer_ready,
            cipher,
        )
    finally:
        await stack.aclose()
        await redis.aclose()
        await engine.dispose()
