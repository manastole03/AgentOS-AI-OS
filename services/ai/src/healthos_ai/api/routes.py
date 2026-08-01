import asyncio
import hashlib
import hmac
import json
import secrets
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from healthos_ai.api.schemas import (
    ActionConfirmation,
    ActionProposalCreate,
    ActionProposalResponse,
    AgentCatalogEntry,
    DocumentCreate,
    DocumentResponse,
    MemoryCreate,
    MemoryResponse,
    RunRequest,
    RunResponse,
)
from healthos_ai.auth import CurrentIdentity
from healthos_ai.db.models import ActionProposal, AgentAuditEvent, AgentRun
from healthos_ai.queue import RunService
from healthos_ai.teams import TEAM_DEFINITIONS, allowed_teams

router = APIRouter(tags=["agent-os"])

# Actions that bind money, clinical intent, or coverage. Every one of these
# requires explicit human confirmation before execution — agents may only ever
# propose them. Keep in sync with the action_type pattern in api/schemas.py.
HIGH_RISK_ACTIONS = {
    "book",
    "reschedule",
    "cancel_appointment",
    "book_lab_order",
    "submit_claim",
    "appeal_claim",
    "submit_prior_authorization",
    "purchase_policy",
    "apply_for_policy",
    "redeem_loyalty_points",
    "draft_clinical_document",
    "draft_medical_codes",
    "draft_referral",
    "draft_prescription",
    "schedule_medication_reminders",
    "acknowledge_lab_result",
}


def proposal_payload_digest(action_type: str, arguments: dict[str, Any]) -> str:
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{action_type}:{canonical}".encode()).hexdigest()


def confirmation_token_digest(token: str, payload_digest: str) -> str:
    return hashlib.sha256(f"{token}:{payload_digest}".encode()).hexdigest()


def proposal_response(
    item: ActionProposal, confirmation_token: str | None = None
) -> ActionProposalResponse:
    return ActionProposalResponse(
        id=item.id,
        run_id=item.run_id,
        action_type=item.action_type,
        risk_level=item.risk_level,
        status=item.status,
        payload_digest=item.payload_digest,
        evidence=item.evidence,
        warnings=item.warnings,
        affected_resources=item.affected_resources,
        expires_at=item.expires_at,
        created_at=item.created_at,
        confirmation_token=confirmation_token,
    )


@router.get("/agents", response_model=list[AgentCatalogEntry])
async def catalog(request: Request, identity: CurrentIdentity) -> list[AgentCatalogEntry]:
    settings = request.app.state.settings
    return [
        AgentCatalogEntry(
            team=name,
            description=definition.description,
            model=getattr(settings, definition.model_setting),
            specialists=[item.name for item in definition.specialists],
        )
        for name, definition in TEAM_DEFINITIONS.items()
        if name in allowed_teams(identity.account_type)
    ]


@router.post("/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: RunRequest, request: Request, identity: CurrentIdentity
) -> RunResponse:
    service: RunService = request.app.state.runs
    try:
        run = await service.create(payload, identity)
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if payload.execution_mode.value == "async":
        await service.enqueue(run.id)
    else:
        try:
            run = await service.execute(run.id)
        except Exception as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Agent execution failed") from exc
    return service.response(run)


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: UUID, request: Request, identity: CurrentIdentity) -> RunResponse:
    service: RunService = request.app.state.runs
    run = await service.get_for_actor(run_id, identity)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")
    return service.response(run)


@router.post(
    "/action-proposals",
    response_model=ActionProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_action_proposal(
    payload: ActionProposalCreate, request: Request, identity: CurrentIdentity
) -> ActionProposalResponse:
    payload_digest = proposal_payload_digest(payload.action_type, payload.arguments)
    confirmation_token = secrets.token_urlsafe(32)
    token_hash = confirmation_token_digest(confirmation_token, payload_digest)
    now = datetime.now(UTC)
    async with request.app.state.sessions() as session:
        run = await session.scalar(
            select(AgentRun).where(
                AgentRun.id == payload.run_id,
                AgentRun.owner_user_id == identity.id,
                AgentRun.tenant_id == identity.tenant_id,
                AgentRun.status == "completed",
            )
        )
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Completed agent run not found")
        item = ActionProposal(
            run_id=run.id,
            owner_user_id=identity.id,
            tenant_id=identity.tenant_id,
            action_type=payload.action_type,
            risk_level="high" if payload.action_type in HIGH_RISK_ACTIONS else "medium",
            status="proposed",
            arguments_ciphertext=request.app.state.cipher.encrypt_json(payload.arguments),
            payload_digest=payload_digest,
            confirmation_token_hash=token_hash,
            evidence=[citation.model_dump(mode="json") for citation in payload.evidence],
            warnings=payload.warnings,
            affected_resources=payload.affected_resources,
            expires_at=now + timedelta(seconds=payload.expires_in_seconds),
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
    await request.app.state.audit.record(
        tenant_id=identity.tenant_id,
        run_id=payload.run_id,
        actor_user_id=identity.id,
        event_type="action.proposed",
        details={
            "proposal_id": str(item.id),
            "action_type": item.action_type,
            "risk_level": item.risk_level,
            "payload_digest": item.payload_digest,
        },
    )
    return proposal_response(item, confirmation_token)


@router.get("/action-proposals", response_model=list[ActionProposalResponse])
async def list_action_proposals(
    request: Request, identity: CurrentIdentity, proposal_status: str | None = None
) -> list[ActionProposalResponse]:
    async with request.app.state.sessions() as session:
        query = select(ActionProposal).where(
            ActionProposal.owner_user_id == identity.id,
            ActionProposal.tenant_id == identity.tenant_id,
        )
        if proposal_status:
            query = query.where(ActionProposal.status == proposal_status)
        items = (
            await session.scalars(query.order_by(ActionProposal.created_at.desc()).limit(100))
        ).all()
    return [proposal_response(item) for item in items]


@router.post(
    "/action-proposals/{proposal_id}/confirm",
    response_model=ActionProposalResponse,
)
async def confirm_action_proposal(
    proposal_id: UUID,
    payload: ActionConfirmation,
    request: Request,
    identity: CurrentIdentity,
) -> ActionProposalResponse:
    now = datetime.now(UTC)
    async with request.app.state.sessions() as session:
        item = await session.scalar(
            select(ActionProposal)
            .where(
                ActionProposal.id == proposal_id,
                ActionProposal.owner_user_id == identity.id,
                ActionProposal.tenant_id == identity.tenant_id,
            )
            .with_for_update()
        )
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Action proposal not found")
        if item.status != "proposed":
            raise HTTPException(status.HTTP_409_CONFLICT, "Action proposal is no longer pending")
        if item.expires_at <= now:
            item.status = "expired"
            await session.commit()
            raise HTTPException(status.HTTP_410_GONE, "Action proposal has expired")
        if not hmac.compare_digest(item.payload_digest, payload.payload_digest):
            raise HTTPException(status.HTTP_409_CONFLICT, "Proposal payload has changed")
        supplied_hash = confirmation_token_digest(
            payload.confirmation_token, payload.payload_digest
        )
        if not hmac.compare_digest(item.confirmation_token_hash, supplied_hash):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Confirmation token is invalid")
        item.status = "confirmed"
        item.confirmed_at = now
        # Destroy the reusable verifier as soon as it has been consumed.
        item.confirmation_token_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        await session.commit()
        await session.refresh(item)
    await request.app.state.audit.record(
        tenant_id=identity.tenant_id,
        run_id=item.run_id,
        actor_user_id=identity.id,
        event_type="action.confirmed",
        details={
            "proposal_id": str(item.id),
            "action_type": item.action_type,
            "payload_digest": item.payload_digest,
        },
    )
    return proposal_response(item)


@router.post(
    "/action-proposals/{proposal_id}/cancel",
    response_model=ActionProposalResponse,
)
async def cancel_action_proposal(
    proposal_id: UUID, request: Request, identity: CurrentIdentity
) -> ActionProposalResponse:
    async with request.app.state.sessions() as session:
        item = await session.scalar(
            select(ActionProposal)
            .where(
                ActionProposal.id == proposal_id,
                ActionProposal.owner_user_id == identity.id,
                ActionProposal.tenant_id == identity.tenant_id,
            )
            .with_for_update()
        )
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Action proposal not found")
        if item.status != "proposed":
            raise HTTPException(status.HTTP_409_CONFLICT, "Action proposal is no longer pending")
        item.status = "cancelled"
        item.cancelled_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(item)
    await request.app.state.audit.record(
        tenant_id=identity.tenant_id,
        run_id=item.run_id,
        actor_user_id=identity.id,
        event_type="action.cancelled",
        details={"proposal_id": str(item.id), "action_type": item.action_type},
    )
    return proposal_response(item)


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: UUID, request: Request, identity: CurrentIdentity
) -> StreamingResponse:
    service: RunService = request.app.state.runs
    if await service.get_for_actor(run_id, identity) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found")

    async def stream() -> AsyncIterator[str]:
        pubsub = request.app.state.redis.pubsub()
        await pubsub.subscribe(f"healthos:ai:run:{run_id}")
        try:
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if message:
                    yield f"data: {message['data']}\n\n"
                    if json.loads(message["data"])["status"] in {"completed", "failed"}:
                        break
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.1)
        finally:
            await pubsub.aclose()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def ingest_document(
    payload: DocumentCreate, request: Request, identity: CurrentIdentity
) -> DocumentResponse:
    if payload.team not in allowed_teams(identity.account_type):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Team is not authorized")
    document, duplicate = await request.app.state.knowledge.ingest(
        tenant_id=identity.tenant_id,
        owner_user_id=identity.id,
        team=payload.team.value,
        title=payload.title,
        content=payload.content,
        source_uri=str(payload.source_uri) if payload.source_uri else None,
        metadata=payload.metadata,
    )
    return DocumentResponse(id=document.id, chunk_count=document.chunk_count, duplicate=duplicate)


@router.post("/memories", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    payload: MemoryCreate, request: Request, identity: CurrentIdentity
) -> MemoryResponse:
    if payload.team not in allowed_teams(identity.account_type):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Team is not authorized")
    item = await request.app.state.memories.remember(
        tenant_id=identity.tenant_id,
        owner_user_id=identity.id,
        team=payload.team.value,
        category=payload.category,
        content=payload.content,
        salience=payload.salience,
    )
    return MemoryResponse(
        id=item.id,
        team=item.team,
        category=item.category,
        content=item.content,
        salience=item.salience,
        created_at=item.created_at,
    )


@router.get("/memories", response_model=list[MemoryResponse])
async def list_memories(request: Request, identity: CurrentIdentity) -> list[MemoryResponse]:
    items = await request.app.state.memories.list_for_owner(
        tenant_id=identity.tenant_id, owner_user_id=identity.id
    )
    return [
        MemoryResponse(
            id=item.id,
            team=item.team,
            category=item.category,
            content=item.content,
            salience=item.salience,
            created_at=item.created_at,
        )
        for item in items
    ]


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: UUID, request: Request, identity: CurrentIdentity) -> None:
    if not await request.app.state.memories.delete(
        memory_id=memory_id, tenant_id=identity.tenant_id, owner_user_id=identity.id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found")


@router.get("/audit")
async def audit_events(
    request: Request, identity: CurrentIdentity, limit: int = 100
) -> list[dict[str, Any]]:
    if not identity.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    async with request.app.state.sessions() as session:
        events = (
            await session.scalars(
                select(AgentAuditEvent)
                .order_by(AgentAuditEvent.created_at.desc())
                .limit(min(limit, 500))
            )
        ).all()
    return [
        {
            "id": str(item.id),
            "run_id": str(item.run_id) if item.run_id else None,
            "event_type": item.event_type,
            "team": item.team,
            "agent": item.agent,
            "tool_name": item.tool_name,
            "model_alias": item.model_alias,
            "success": item.success,
            "details": item.details,
            "previous_hash": item.previous_hash,
            "event_hash": item.event_hash,
            "created_at": item.created_at.isoformat(),
        }
        for item in events
    ]
