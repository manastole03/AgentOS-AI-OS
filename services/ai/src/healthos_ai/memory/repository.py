import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from healthos_ai.db.models import LongTermMemory
from healthos_ai.llm import LLMGateway


@dataclass(frozen=True)
class MemoryHit:
    id: UUID
    team: str
    category: str
    content: str
    salience: float
    score: float
    created_at: datetime


class MemoryRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], llm: LLMGateway) -> None:
        self._sessions = sessions
        self._llm = llm

    async def remember(
        self,
        *,
        tenant_id: str,
        owner_user_id: UUID,
        team: str,
        category: str,
        content: str,
        salience: float = 1.0,
    ) -> LongTermMemory:
        digest = hashlib.sha256(content.strip().lower().encode()).hexdigest()
        vector = (await self._llm.embed([content]))[0]
        async with self._sessions() as session:
            memory = LongTermMemory(
                tenant_id=tenant_id,
                owner_user_id=owner_user_id,
                team=team,
                category=category,
                content=content,
                content_hash=digest,
                embedding=vector,
                salience=salience,
            )
            session.add(memory)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(LongTermMemory).where(
                        LongTermMemory.tenant_id == tenant_id,
                        LongTermMemory.owner_user_id == owner_user_id,
                        LongTermMemory.team == team,
                        LongTermMemory.content_hash == digest,
                    )
                )
                if existing is None:
                    raise
                memory = existing
            await session.refresh(memory)
            return memory

    async def search(
        self, *, tenant_id: str, owner_user_id: UUID, team: str, query: str, limit: int = 5
    ) -> list[MemoryHit]:
        vector = (await self._llm.embed([query]))[0]
        distance = LongTermMemory.embedding.cosine_distance(vector)
        now = datetime.now(UTC)
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(LongTermMemory, distance.label("distance"))
                    .where(
                        LongTermMemory.tenant_id == tenant_id,
                        LongTermMemory.owner_user_id == owner_user_id,
                        LongTermMemory.team == team,
                        or_(LongTermMemory.expires_at.is_(None), LongTermMemory.expires_at > now),
                    )
                    .order_by(distance)
                    .limit(min(limit, 20))
                )
            ).all()
            ids = [row.LongTermMemory.id for row in rows]
            if ids:
                await session.execute(
                    update(LongTermMemory)
                    .where(LongTermMemory.id.in_(ids))
                    .values(access_count=LongTermMemory.access_count + 1, last_accessed_at=now)
                )
                await session.commit()
        return [
            MemoryHit(
                row.LongTermMemory.id,
                row.LongTermMemory.team,
                row.LongTermMemory.category,
                row.LongTermMemory.content,
                row.LongTermMemory.salience,
                max(0.0, 1.0 - float(row.distance)),
                row.LongTermMemory.created_at,
            )
            for row in rows
        ]

    async def list_for_owner(
        self, *, tenant_id: str, owner_user_id: UUID, limit: int = 100
    ) -> list[LongTermMemory]:
        async with self._sessions() as session:
            return list(
                (
                    await session.scalars(
                        select(LongTermMemory)
                        .where(
                            LongTermMemory.tenant_id == tenant_id,
                            LongTermMemory.owner_user_id == owner_user_id,
                        )
                        .order_by(LongTermMemory.created_at.desc())
                        .limit(min(limit, 200))
                    )
                ).all()
            )

    async def delete(self, *, memory_id: UUID, tenant_id: str, owner_user_id: UUID) -> bool:
        async with self._sessions() as session:
            memory = await session.scalar(
                select(LongTermMemory).where(
                    LongTermMemory.id == memory_id,
                    LongTermMemory.tenant_id == tenant_id,
                    LongTermMemory.owner_user_id == owner_user_id,
                )
            )
            if memory is None:
                return False
            await session.delete(memory)
            await session.commit()
            return True
