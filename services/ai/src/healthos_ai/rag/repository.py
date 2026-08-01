import hashlib
import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from healthos_ai.db.models import KnowledgeChunk, KnowledgeDocument
from healthos_ai.llm import LLMGateway


def chunk_text(text: str, *, size: int = 1800, overlap: int = 200) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + size)
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


@dataclass(frozen=True)
class SearchHit:
    id: UUID
    document_id: UUID
    content: str
    score: float


class KnowledgeRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], llm: LLMGateway) -> None:
        self._sessions = sessions
        self._llm = llm

    async def ingest(
        self,
        *,
        tenant_id: str,
        owner_user_id: UUID,
        team: str,
        title: str,
        content: str,
        source_uri: str | None,
        metadata: dict[str, Any],
    ) -> tuple[KnowledgeDocument, bool]:
        digest = hashlib.sha256(content.encode()).hexdigest()
        async with self._sessions() as session:
            existing = await session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeDocument.team == team,
                    KnowledgeDocument.content_hash == digest,
                )
            )
            if existing:
                return existing, True
        chunks = chunk_text(content)
        embeddings = await self._llm.embed(chunks)
        async with self._sessions() as session:
            document = KnowledgeDocument(
                tenant_id=tenant_id,
                owner_user_id=owner_user_id,
                team=team,
                title=title,
                source_uri=source_uri,
                content_hash=digest,
                metadata_=metadata,
                chunk_count=len(chunks),
            )
            session.add(document)
            await session.flush()
            session.add_all(
                [
                    KnowledgeChunk(
                        document_id=document.id,
                        tenant_id=tenant_id,
                        team=team,
                        chunk_index=index,
                        content=value,
                        token_estimate=math.ceil(len(value) / 4),
                        embedding=embedding,
                    )
                    for index, (value, embedding) in enumerate(zip(chunks, embeddings, strict=True))
                ]
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.tenant_id == tenant_id,
                        KnowledgeDocument.team == team,
                        KnowledgeDocument.content_hash == digest,
                    )
                )
                if existing:
                    return existing, True
                raise
            await session.refresh(document)
            return document, False

    async def search(
        self, *, tenant_id: str, team: str, query: str, limit: int = 6
    ) -> list[SearchHit]:
        vector = (await self._llm.embed([query]))[0]
        distance = KnowledgeChunk.embedding.cosine_distance(vector)
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(KnowledgeChunk, distance.label("distance"))
                    .where(
                        KnowledgeChunk.tenant_id == tenant_id,
                        KnowledgeChunk.team.in_([team, "document_intelligence"]),
                    )
                    .order_by(distance)
                    .limit(min(limit, 20))
                )
            ).all()
        return [
            SearchHit(
                row.KnowledgeChunk.id,
                row.KnowledgeChunk.document_id,
                row.KnowledgeChunk.content,
                max(0.0, 1.0 - float(row.distance)),
            )
            for row in rows
        ]
