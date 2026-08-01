import hashlib
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext, enforce_csrf, require_permissions
from healthos_api.db.dependencies import get_db
from healthos_api.db.models import (
    ApplicationDefinition,
    AuditEvent,
    ConsentGrant,
    Organization,
    OrganizationMembership,
    OutboxEvent,
    User,
    WorkflowInstance,
)
from healthos_api.platform.schemas import (
    AppManifest,
    ConsentCreate,
    ConsentResponse,
    DefinitionCreate,
    DefinitionResponse,
    OrganizationResponse,
    WorkflowResponse,
    WorkflowStart,
    WorkflowTransition,
)

router = APIRouter(tags=["application-platform"])


def definition_response(item: ApplicationDefinition) -> DefinitionResponse:
    return DefinitionResponse(
        id=item.id,
        tenant_id=item.tenant_id,
        kind=item.kind,
        key=item.key,
        version=item.version,
        status=item.status,
        account_types=item.account_types,
        locale=item.locale,
        schema_=item.schema,
        presentation=item.presentation,
        rules=item.rules,
        effective_at=item.effective_at,
        published_at=item.published_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def consent_response(item: ConsentGrant) -> ConsentResponse:
    return ConsentResponse.model_validate(item, from_attributes=True)


def _definition_actions(item: ApplicationDefinition, current: str, roles: set[str]) -> list[str]:
    states = item.schema.get("states", {})
    state = states.get(current, {}) if isinstance(states, dict) else {}
    transitions = state.get("transitions", []) if isinstance(state, dict) else []
    result: list[str] = []
    for transition in transitions:
        allowed = set(transition.get("roles", []))
        if not allowed or allowed.intersection(roles):
            result.append(str(transition.get("action", "")))
    return [action for action in result if action]


async def _published_definitions(
    db: AsyncSession, context: AuthContext, locale: str
) -> list[ApplicationDefinition]:
    now = datetime.now(UTC)
    rows = list(
        (
            await db.scalars(
                select(ApplicationDefinition)
                .where(
                    ApplicationDefinition.status == "published",
                    ApplicationDefinition.locale == locale,
                    or_(
                        ApplicationDefinition.tenant_id.is_(None),
                        ApplicationDefinition.tenant_id == context.tenant_id,
                    ),
                    or_(
                        ApplicationDefinition.effective_at.is_(None),
                        ApplicationDefinition.effective_at <= now,
                    ),
                )
                .order_by(
                    ApplicationDefinition.key,
                    ApplicationDefinition.tenant_id.desc().nullslast(),
                    ApplicationDefinition.version.desc(),
                )
            )
        ).all()
    )
    selected: dict[tuple[str, str], ApplicationDefinition] = {}
    for item in rows:
        if item.account_types and context.user.account_type.value not in item.account_types:
            continue
        selected.setdefault((item.kind, item.key), item)
    return list(selected.values())


@router.get("/app-manifest", response_model=AppManifest)
async def app_manifest(
    context: Annotated[AuthContext, Depends(require_permissions("portal:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    locale: str = Query("en-US", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$"),
) -> AppManifest:
    definitions = await _published_definitions(db, context, locale)
    grouped: dict[str, list[DefinitionResponse]] = {
        "module": [],
        "form": [],
        "dashboard": [],
        "workflow": [],
        "content": [],
    }
    for item in definitions:
        grouped[item.kind].append(definition_response(item))
    grouped["module"].sort(key=lambda item: int(item.presentation.get("position", 999)))
    fingerprint = "|".join(
        f"{item.kind}:{item.key}:{item.version}:{item.updated_at.isoformat()}"
        for item in sorted(definitions, key=lambda item: (item.kind, item.key))
    )
    version = hashlib.sha256(fingerprint.encode()).hexdigest()[:16] if fingerprint else "0"
    return AppManifest(
        tenant_id=context.tenant_id,
        account_type=context.user.account_type.value,
        locale=locale,
        generated_at=datetime.now(UTC),
        version=version or "0",
        modules=grouped["module"],
        forms=grouped["form"],
        dashboards=grouped["dashboard"],
        workflows=grouped["workflow"],
        content=grouped["content"],
    )


@router.get("/configuration", response_model=list[DefinitionResponse])
async def list_configuration(
    context: Annotated[AuthContext, Depends(require_permissions("system:admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    kind: str | None = None,
) -> list[DefinitionResponse]:
    query = select(ApplicationDefinition).where(
        or_(
            ApplicationDefinition.tenant_id.is_(None),
            ApplicationDefinition.tenant_id == context.tenant_id,
        )
    )
    if kind:
        query = query.where(ApplicationDefinition.kind == kind)
    items = (await db.scalars(query.order_by(ApplicationDefinition.updated_at.desc()))).all()
    return [definition_response(item) for item in items]


@router.post(
    "/configuration",
    response_model=DefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
async def create_configuration(
    payload: DefinitionCreate,
    context: Annotated[AuthContext, Depends(require_permissions("system:admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DefinitionResponse:
    requested_tenant = payload.tenant_id or context.tenant_id
    latest = await db.scalar(
        select(func.max(ApplicationDefinition.version)).where(
            ApplicationDefinition.tenant_id == requested_tenant,
            ApplicationDefinition.kind == payload.kind,
            ApplicationDefinition.key == payload.key,
        )
    )
    item = ApplicationDefinition(
        tenant_id=requested_tenant,
        kind=payload.kind,
        key=payload.key,
        version=int(latest or 0) + 1,
        status="draft",
        account_types=payload.account_types,
        locale=payload.locale,
        schema=payload.schema_,
        presentation=payload.presentation,
        rules=payload.rules,
        effective_at=payload.effective_at,
        created_by_user_id=context.user.id,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return definition_response(item)


@router.post(
    "/configuration/{definition_id}/publish",
    response_model=DefinitionResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def publish_configuration(
    definition_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("system:admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DefinitionResponse:
    item = await db.scalar(
        select(ApplicationDefinition)
        .where(ApplicationDefinition.id == definition_id)
        .with_for_update()
    )
    if item is None or item.tenant_id not in {None, context.tenant_id}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Definition not found")
    if item.status not in {"draft", "review"}:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only draft or reviewed definitions publish")
    now = datetime.now(UTC)
    previous = (
        await db.scalars(
            select(ApplicationDefinition).where(
                ApplicationDefinition.tenant_id == item.tenant_id,
                ApplicationDefinition.kind == item.kind,
                ApplicationDefinition.key == item.key,
                ApplicationDefinition.status == "published",
            )
        )
    ).all()
    for old in previous:
        old.status = "retired"
        item.supersedes_id = old.id
    item.status = "published"
    item.published_at = now
    item.effective_at = item.effective_at or now
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type="configuration.published",
            event_data={"definition_id": str(item.id), "key": item.key, "version": item.version},
        )
    )
    await db.commit()
    await db.refresh(item)
    return definition_response(item)


@router.get("/organizations", response_model=list[OrganizationResponse])
async def organizations(
    context: Annotated[AuthContext, Depends(require_permissions("portal:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrganizationResponse]:
    rows = (
        await db.execute(
            select(OrganizationMembership, Organization)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                OrganizationMembership.user_id == context.user.id,
                OrganizationMembership.status == "active",
            )
        )
    ).all()
    return [
        OrganizationResponse(
            id=org.id,
            slug=org.slug,
            legal_name=org.legal_name,
            organization_type=org.organization_type,
            status=org.status,
            role=membership.role,
            is_primary=membership.is_primary,
            permissions=membership.permissions,
        )
        for membership, org in rows
    ]


@router.get("/consents", response_model=list[ConsentResponse])
async def consents(
    context: Annotated[AuthContext, Depends(require_permissions("portal:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ConsentResponse]:
    if context.user.account_type.value != "patient":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Patients manage their consent grants")
    items = (
        await db.scalars(
            select(ConsentGrant)
            .where(ConsentGrant.patient_user_id == context.user.id)
            .order_by(ConsentGrant.created_at.desc())
        )
    ).all()
    return [consent_response(item) for item in items]


@router.post(
    "/consents",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
async def create_consent(
    payload: ConsentCreate,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsentResponse:
    if context.user.account_type.value != "patient":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Patients manage their consent grants")
    if payload.expires_at and payload.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Consent must expire in future")
    if payload.grantee_user_id and await db.get(User, payload.grantee_user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grantee user not found")
    if (
        payload.grantee_organization_id
        and await db.get(Organization, payload.grantee_organization_id) is None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Grantee organization not found")
    item = ConsentGrant(
        patient_user_id=context.user.id,
        grantee_user_id=payload.grantee_user_id,
        grantee_organization_id=payload.grantee_organization_id,
        purpose=payload.purpose,
        scopes=sorted(set(payload.scopes)),
        expires_at=payload.expires_at,
        provenance={"source": "patient_portal", "session_id": str(context.session.id)},
    )
    db.add(item)
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            subject_user_id=context.user.id,
            event_type="consent.granted",
            event_data={"consent_id": str(item.id), "scopes": item.scopes},
        )
    )
    await db.commit()
    await db.refresh(item)
    return consent_response(item)


@router.delete(
    "/consents/{consent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(enforce_csrf)],
)
async def revoke_consent(
    consent_id: UUID,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    item = await db.scalar(
        select(ConsentGrant)
        .where(
            ConsentGrant.id == consent_id,
            ConsentGrant.patient_user_id == context.user.id,
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consent not found")
    if item.status == "active":
        item.status = "revoked"
        item.revoked_at = datetime.now(UTC)
        db.add(
            AuditEvent(
                actor_user_id=context.user.id,
                subject_user_id=context.user.id,
                event_type="consent.revoked",
                event_data={"consent_id": str(item.id)},
            )
        )
        await db.commit()


@router.post(
    "/workflows",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_csrf)],
)
async def start_workflow(
    payload: WorkflowStart,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkflowResponse:
    definition = await db.scalar(
        select(ApplicationDefinition)
        .where(
            ApplicationDefinition.kind == "workflow",
            ApplicationDefinition.key == payload.definition_key,
            ApplicationDefinition.status == "published",
            or_(
                ApplicationDefinition.tenant_id.is_(None),
                ApplicationDefinition.tenant_id == context.tenant_id,
            ),
        )
        .order_by(
            ApplicationDefinition.tenant_id.desc().nullslast(), ApplicationDefinition.version.desc()
        )
    )
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Published workflow not found")
    initial = str(definition.schema.get("initial", "draft"))
    item = WorkflowInstance(
        tenant_id=context.tenant_id,
        definition_id=definition.id,
        definition_key=definition.key,
        definition_version=definition.version,
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        status=initial,
        context=payload.context,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    roles = {context.user.account_type.value, *(role.name for role in context.user.roles)}
    return WorkflowResponse(
        **{
            column: getattr(item, column)
            for column in (
                "id",
                "definition_key",
                "definition_version",
                "subject_type",
                "subject_id",
                "status",
                "version",
                "context",
                "created_at",
                "updated_at",
            )
        },
        available_actions=_definition_actions(definition, item.status, roles),
    )


@router.post(
    "/workflows/{workflow_id}/transitions",
    response_model=WorkflowResponse,
    dependencies=[Depends(enforce_csrf)],
)
async def transition_workflow(
    workflow_id: UUID,
    payload: WorkflowTransition,
    context: Annotated[AuthContext, Depends(require_permissions("portal:write"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkflowResponse:
    item = await db.scalar(
        select(WorkflowInstance)
        .where(WorkflowInstance.id == workflow_id, WorkflowInstance.tenant_id == context.tenant_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workflow not found")
    if item.version != payload.expected_version:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow version has changed")
    definition = await db.get(ApplicationDefinition, item.definition_id)
    if definition is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Workflow definition is unavailable")
    roles = {context.user.account_type.value, *(role.name for role in context.user.roles)}
    states: dict[str, Any] = definition.schema.get("states", {})
    transitions = states.get(item.status, {}).get("transitions", [])
    transition = next(
        (value for value in transitions if value.get("action") == payload.action), None
    )
    if transition is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Transition is not valid from current state")
    allowed = set(transition.get("roles", []))
    if allowed and not allowed.intersection(roles):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Role cannot perform this transition")
    previous = item.status
    item.status = str(transition["to"])
    item.version += 1
    db.add(
        OutboxEvent(
            tenant_id=context.tenant_id,
            aggregate_type="workflow",
            aggregate_id=item.id,
            event_type="workflow.transitioned",
            payload={"from": previous, "to": item.status, "action": payload.action},
        )
    )
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type="workflow.transitioned",
            event_data={
                "workflow_id": str(item.id),
                "from": previous,
                "to": item.status,
                "action": payload.action,
                "reason": payload.reason,
            },
        )
    )
    await db.commit()
    await db.refresh(item)
    return WorkflowResponse(
        **{
            column: getattr(item, column)
            for column in (
                "id",
                "definition_key",
                "definition_version",
                "subject_type",
                "subject_id",
                "status",
                "version",
                "context",
                "created_at",
                "updated_at",
            )
        },
        available_actions=_definition_actions(definition, item.status, roles),
    )
