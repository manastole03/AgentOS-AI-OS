import json
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from healthos_ai.api.schemas import RunRequest, RunResponse
from healthos_ai.auth import Identity
from healthos_ai.db.models import AgentRun
from healthos_ai.observability.audit import AuditLogger
from healthos_ai.observability.metrics import AI_RUN_DURATION, AI_RUNS
from healthos_ai.orchestration.context import RuntimeContext
from healthos_ai.orchestration.graph import AgentOrchestrator
from healthos_ai.security import DataCipher
from healthos_ai.teams import allowed_teams


class RunService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        redis: Redis,
        cipher: DataCipher,
        audit: AuditLogger,
        orchestrator: AgentOrchestrator,
        stream: str,
        event_ttl: int,
    ) -> None:
        self._sessions, self._redis, self._cipher = sessions, redis, cipher
        self._audit, self._orchestrator, self._stream = audit, orchestrator, stream
        self._event_ttl = event_ttl

    async def create(self, request: RunRequest, identity: Identity) -> AgentRun:
        permitted = {team.value for team in allowed_teams(identity.account_type)}
        if request.team and request.team.value not in permitted:
            raise PermissionError("Agent team is not authorized for this account type")
        run = AgentRun(
            id=uuid4(),
            thread_id=request.thread_id or uuid4(),
            owner_user_id=identity.id,
            tenant_id=identity.tenant_id,
            account_type=identity.account_type,
            status="queued",
            execution_mode=request.execution_mode.value,
            requested_team=request.team.value if request.team else None,
            collaborators=[],
            provider_preference=request.provider.value,
            memory_mode=request.memory_mode.value,
            input_ciphertext=self._cipher.encrypt(request.prompt),
            input_digest=self._cipher.digest(request.prompt),
        )
        async with self._sessions() as session:
            session.add(run)
            await session.commit()
            await session.refresh(run)
        await self._audit.record(
            tenant_id=identity.tenant_id,
            run_id=run.id,
            actor_user_id=identity.id,
            event_type="run.created",
            details={"execution_mode": run.execution_mode},
        )
        return run

    async def enqueue(self, run_id: UUID) -> None:
        await self._redis.xadd(
            self._stream, {"run_id": str(run_id)}, maxlen=100_000, approximate=True
        )
        await self.publish(run_id, "queued")

    async def execute(self, run_id: UUID) -> AgentRun:
        run = await self._load(run_id)
        if run.status == "completed":
            return run
        start = datetime.now(UTC)
        await self._set_status(run_id, "running", started_at=start)
        await self.publish(run_id, "running")
        permitted = tuple(team.value for team in allowed_teams(run.account_type))
        context = RuntimeContext(
            run_id=run.id,
            thread_id=run.thread_id,
            actor_user_id=run.owner_user_id,
            tenant_id=run.tenant_id,
            account_type=run.account_type,
            team=run.requested_team or permitted[0],
            allowed_teams=permitted,
            memory_mode=run.memory_mode,
        )
        try:
            result = cast(
                dict[str, Any],
                await self._orchestrator.graph.ainvoke(
                    {
                        "prompt": self._cipher.decrypt(run.input_ciphertext),
                        "requested_team": run.requested_team,
                        "provider": run.provider_preference,
                        "memory_mode": run.memory_mode,
                    },
                    context=context,
                    config={"configurable": {"thread_id": str(run.thread_id)}},
                ),
            )
            completed = datetime.now(UTC)
            async with self._sessions() as session:
                current = await session.get(AgentRun, run_id, with_for_update=True)
                if current is None:
                    raise LookupError("Run not found")
                current.status = "completed"
                current.selected_team = result["selected_team"]
                current.collaborators = result.get("collaborators", [])
                current.output_ciphertext = self._cipher.encrypt(result["final_response"])
                current.completed_at = completed
                await session.commit()
                await session.refresh(current)
            AI_RUNS.labels(current.status, current.selected_team or "unknown").inc()
            AI_RUN_DURATION.labels(current.selected_team or "unknown").observe(
                (completed - start).total_seconds()
            )
            await self.publish(run_id, "completed")
            await self._audit.record(
                tenant_id=run.tenant_id,
                run_id=run.id,
                actor_user_id=run.owner_user_id,
                event_type="run.completed",
                team=current.selected_team,
            )
            return current
        except Exception as exc:
            await self._set_status(
                run_id,
                "failed",
                completed_at=datetime.now(UTC),
                error_code=type(exc).__name__[:100],
            )
            AI_RUNS.labels("failed", run.requested_team or "unknown").inc()
            await self.publish(run_id, "failed")
            await self._audit.record(
                tenant_id=run.tenant_id,
                run_id=run.id,
                actor_user_id=run.owner_user_id,
                event_type="run.failed",
                success=False,
                details={"error_type": type(exc).__name__},
            )
            raise

    async def get_for_actor(self, run_id: UUID, identity: Identity) -> AgentRun | None:
        async with self._sessions() as session:
            query = select(AgentRun).where(AgentRun.id == run_id)
            if not identity.is_admin:
                query = query.where(
                    AgentRun.owner_user_id == identity.id, AgentRun.tenant_id == identity.tenant_id
                )
            return cast(AgentRun | None, await session.scalar(query))

    def response(self, run: AgentRun) -> RunResponse:
        return RunResponse(
            id=run.id,
            thread_id=run.thread_id,
            status=run.status,
            selected_team=run.selected_team,
            collaborators=run.collaborators,
            response=self._cipher.decrypt(run.output_ciphertext) if run.output_ciphertext else None,
            error_code=run.error_code,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )

    async def publish(self, run_id: UUID, status: str) -> None:
        channel = f"healthos:ai:run:{run_id}"
        await self._redis.publish(channel, json.dumps({"run_id": str(run_id), "status": status}))
        await self._redis.set(f"{channel}:status", status, ex=self._event_ttl)

    async def _load(self, run_id: UUID) -> AgentRun:
        async with self._sessions() as session:
            run = await session.get(AgentRun, run_id)
        if run is None:
            raise LookupError("Run not found")
        return run

    async def _set_status(self, run_id: UUID, status: str, **values: object) -> None:
        async with self._sessions() as session:
            run = await session.get(AgentRun, run_id, with_for_update=True)
            if run is None:
                raise LookupError("Run not found")
            run.status = status
            for key, value in values.items():
                setattr(run, key, value)
            await session.commit()
