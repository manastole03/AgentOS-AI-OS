from time import monotonic
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from healthos_ai.db.models import AgentAuditEvent


class AuditLogger:
    """Append-only metadata audit trail. Prompt and tool arguments are never logged."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def record(
        self,
        *,
        tenant_id: str,
        event_type: str,
        run_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        team: str | None = None,
        agent: str | None = None,
        tool_name: str | None = None,
        model_alias: str | None = None,
        duration_ms: float | None = None,
        success: bool = True,
        details: dict[str, Any] | None = None,
    ) -> None:
        async with self._sessions() as session:
            session.add(
                AgentAuditEvent(
                    run_id=run_id,
                    actor_user_id=actor_user_id,
                    tenant_id=tenant_id,
                    event_type=event_type,
                    team=team,
                    agent=agent,
                    tool_name=tool_name,
                    model_alias=model_alias,
                    duration_ms=duration_ms,
                    success=success,
                    details=details or {},
                )
            )
            await session.commit()


class Timer:
    def __init__(self) -> None:
        self._start = monotonic()

    @property
    def milliseconds(self) -> float:
        return (monotonic() - self._start) * 1000
