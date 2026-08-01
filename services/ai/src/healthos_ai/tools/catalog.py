from typing import Any

from langchain.tools import ToolRuntime, tool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from healthos_ai.db.models import AgentMessage
from healthos_ai.memory import MemoryRepository
from healthos_ai.observability.audit import AuditLogger, Timer
from healthos_ai.observability.metrics import AI_TOOL_CALLS
from healthos_ai.orchestration.context import RuntimeContext
from healthos_ai.rag import KnowledgeRepository
from healthos_ai.security import DataCipher


class AgentMessageRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], cipher: DataCipher) -> None:
        self._sessions, self._cipher = sessions, cipher

    async def send(self, context: RuntimeContext, recipient: str, message: str) -> None:
        if recipient not in context.allowed_teams:
            raise ValueError("Recipient team is not authorized for this actor")
        async with self._sessions() as session:
            session.add(
                AgentMessage(
                    run_id=context.run_id,
                    sender_team=context.team,
                    recipient_team=recipient,
                    message_ciphertext=self._cipher.encrypt(message),
                )
            )
            await session.commit()

    async def inbox(self, context: RuntimeContext) -> list[str]:
        async with self._sessions() as session:
            messages = (
                await session.scalars(
                    select(AgentMessage)
                    .where(
                        AgentMessage.run_id == context.run_id,
                        AgentMessage.recipient_team == context.team,
                    )
                    .order_by(AgentMessage.created_at)
                )
            ).all()
        return [
            f"From {item.sender_team}: {self._cipher.decrypt(item.message_ciphertext)}"
            for item in messages
        ]


def build_tools(
    knowledge: KnowledgeRepository,
    memories: MemoryRepository,
    messages: AgentMessageRepository,
    audit: AuditLogger,
) -> list[Any]:
    async def audited(name: str, runtime: ToolRuntime[RuntimeContext], operation: Any) -> Any:
        timer = Timer()
        try:
            value = await operation()
            AI_TOOL_CALLS.labels(name, "success").inc()
            await audit.record(
                tenant_id=runtime.context.tenant_id,
                run_id=runtime.context.run_id,
                actor_user_id=runtime.context.actor_user_id,
                event_type="tool.completed",
                team=runtime.context.team,
                tool_name=name,
                duration_ms=timer.milliseconds,
            )
            return value
        except Exception:
            AI_TOOL_CALLS.labels(name, "failure").inc()
            await audit.record(
                tenant_id=runtime.context.tenant_id,
                run_id=runtime.context.run_id,
                actor_user_id=runtime.context.actor_user_id,
                event_type="tool.failed",
                team=runtime.context.team,
                tool_name=name,
                duration_ms=timer.milliseconds,
                success=False,
            )
            raise

    @tool
    async def search_knowledge(query: str, runtime: ToolRuntime[RuntimeContext]) -> str:
        """Search authorized tenant knowledge and return cited source chunks."""

        async def operation() -> str:
            hits = await knowledge.search(
                tenant_id=runtime.context.tenant_id, team=runtime.context.team, query=query
            )
            return (
                "\n\n".join(f"[chunk:{hit.id} score:{hit.score:.3f}] {hit.content}" for hit in hits)
                or "No authorized knowledge found."
            )

        return str(await audited("search_knowledge", runtime, operation))

    @tool
    async def search_memory(query: str, runtime: ToolRuntime[RuntimeContext]) -> str:
        """Search the current user's long-term memory for the active team."""
        if runtime.context.memory_mode == "none":
            return "Memory access is disabled for this run."

        async def operation() -> str:
            hits = await memories.search(
                tenant_id=runtime.context.tenant_id,
                owner_user_id=runtime.context.actor_user_id,
                team=runtime.context.team,
                query=query,
            )
            return (
                "\n".join(f"[{hit.category}] {hit.content}" for hit in hits)
                or "No relevant memory found."
            )

        return str(await audited("search_memory", runtime, operation))

    @tool
    async def remember_fact(
        content: str, category: str, runtime: ToolRuntime[RuntimeContext]
    ) -> str:
        """Store a durable user-scoped fact only when explicit read/write memory is enabled."""
        if runtime.context.memory_mode != "read_write":
            return "Memory write denied: this run did not opt in to read/write memory."

        async def operation() -> str:
            memory = await memories.remember(
                tenant_id=runtime.context.tenant_id,
                owner_user_id=runtime.context.actor_user_id,
                team=runtime.context.team,
                category=category[:100],
                content=content[:4000],
            )
            return f"Stored memory {memory.id}."

        return str(await audited("remember_fact", runtime, operation))

    @tool
    async def send_team_message(
        recipient_team: str, message: str, runtime: ToolRuntime[RuntimeContext]
    ) -> str:
        """Send an encrypted, durable message to another authorized agent team in this run."""

        async def operation() -> str:
            await messages.send(runtime.context, recipient_team, message[:8000])
            return "Message delivered."

        return str(await audited("send_team_message", runtime, operation))

    @tool
    async def read_team_messages(runtime: ToolRuntime[RuntimeContext]) -> str:
        """Read messages addressed to this team in the current run."""

        async def operation() -> str:
            items = await messages.inbox(runtime.context)
            return "\n".join(items) or "No team messages."

        return str(await audited("read_team_messages", runtime, operation))

    return [search_knowledge, search_memory, remember_fact, send_team_message, read_team_messages]
