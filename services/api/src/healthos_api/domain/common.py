"""Shared primitives for the normalized domain routers.

Every domain router in this package builds on these helpers so that tenant
scoping, consent enforcement, PHI access logging, and audit writes behave
identically across clinical, scheduling, lab, and insurance surfaces.

Two rules the schema depends on and cannot enforce by itself:

* Longitudinal clinical reads are *consent* scoped, not tenant scoped. A record
  written at one hospital must remain visible to the patient and to any
  clinician holding a valid consent grant, so :func:`consent_scoped_patients`
  must be used instead of a plain ``tenant_id`` filter.
* Every read of patient data writes a :class:`PhiAccessEvent` in the same
  transaction. ``audit_events`` records writes only, so disclosure accounting is
  unbuildable without this.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from healthos_api.core.security import AuthContext
from healthos_api.db.models import (
    AccountType,
    AuditEvent,
    ConsentGrant,
    PhiAccessAction,
    PhiAccessEvent,
)

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50

#: HL7 v3 PurposeOfUse codes accepted by ``phi_access_events.purpose_of_use``.
PurposeOfUse = Literal["TREAT", "ETREAT", "HPAYMT", "HOPERAT", "PATRQT", "PUBHLTH", "RESEARCH"]


class DomainModel(BaseModel):
    """Base schema for domain payloads."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Page[T](BaseModel):
    """A single page of results plus the cursor needed to fetch the next."""

    items: list[T]
    total: int | None = None
    limit: int
    offset: int
    has_more: bool


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


async def pagination(
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Pagination:
    return Pagination(limit=limit, offset=offset)


PaginationDep = Annotated[Pagination, Depends(pagination)]


def paginate[T](items: list[T], page: Pagination, total: int | None = None) -> Page[T]:
    """Wrap an over-fetched result list into a :class:`Page`.

    Callers should query ``limit + 1`` rows so ``has_more`` is exact without a
    second COUNT round trip.
    """
    has_more = len(items) > page.limit
    return Page(
        items=items[: page.limit],
        total=total,
        limit=page.limit,
        offset=page.offset,
        has_more=has_more,
    )


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def forbidden(detail: str = "This role is not authorized") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def is_admin(context: AuthContext) -> bool:
    return context.user.account_type == AccountType.ADMIN


def is_patient(context: AuthContext) -> bool:
    return context.user.account_type == AccountType.PATIENT


def tenant_scoped[M](query: Select[tuple[M]], model: Any, context: AuthContext) -> Select[tuple[M]]:
    """Restrict an operational query to the caller's tenant.

    Admins see everything. Use this for *operational* tables (slots, invoices,
    service catalog). Longitudinal clinical tables must use
    :func:`consent_scoped_patients` instead — a tenant filter would hide a
    patient's own history the moment they are seen at a second organization.
    """
    if is_admin(context):
        return query
    return query.where(model.tenant_id == context.tenant_id)


def discovery_scoped[M](
    query: Select[tuple[M]], model: Any, context: AuthContext
) -> Select[tuple[M]]:
    """Scope a *discovery* surface: catalogs, marketplaces, and availability search.

    A patient's ``tenant_id`` is their own user id (the solo-account fallback in
    ``core.security``), so applying :func:`tenant_scoped` to a discovery query
    matches nothing and the patient sees an empty catalog — they could never
    find a provider, a lab test, or a plan. Discovery is inherently cross-tenant:
    the brief requires availability "with any doctor" and insurance options
    "aggregated from all participating aggregators".

    So: patients and admins search across every tenant; organizations
    (doctor / hospital / insurance) stay scoped to the capacity they own, because
    for them these same tables are an operational management surface.

    Writes and management reads must keep using :func:`tenant_scoped`.
    """
    if is_admin(context) or is_patient(context):
        return query
    return query.where(model.tenant_id == context.tenant_id)


def discovery_predicate(model: Any, context: AuthContext) -> Any | None:
    """The :func:`discovery_scoped` rule as a bare predicate.

    Some discovery queries are column projections rather than entity selects and
    cannot use the ``Select``-typed helper. Returns ``None`` when no filter
    applies.
    """
    if is_admin(context) or is_patient(context):
        return None
    return model.tenant_id == context.tenant_id


async def consent_scoped_patients(db: AsyncSession, context: AuthContext) -> set[UUID] | None:
    """Patient ids the caller may read longitudinal clinical data for.

    Returns ``None`` when the caller may read every patient (admin), otherwise
    the explicit allow-set: themselves (if a patient) plus every patient who has
    an active, unrevoked, unexpired consent grant naming this user or their
    organization.
    """
    if is_admin(context):
        return None

    allowed: set[UUID] = set()
    if is_patient(context):
        allowed.add(context.user.id)

    now = datetime.now(UTC)
    grants = await db.scalars(
        select(ConsentGrant).where(
            or_(
                ConsentGrant.grantee_user_id == context.user.id,
                ConsentGrant.grantee_organization_id == context.tenant_id,
            ),
            ConsentGrant.revoked_at.is_(None),
            or_(ConsentGrant.expires_at.is_(None), ConsentGrant.expires_at > now),
        )
    )
    for grant in grants:
        if grant.patient_user_id is not None:
            allowed.add(grant.patient_user_id)
    return allowed


async def assert_may_read_patient(
    db: AsyncSession, context: AuthContext, patient_user_id: UUID
) -> None:
    allowed = await consent_scoped_patients(db, context)
    if allowed is None or patient_user_id in allowed:
        return
    raise forbidden("No consent grant covers this patient")


def apply_patient_scope[M](
    query: Select[tuple[M]], model: Any, allowed: set[UUID] | None
) -> Select[tuple[M]]:
    if allowed is None:
        return query
    if not allowed:
        # An empty allow-set must return nothing, not everything.
        return query.where(model.patient_user_id.is_(None)).where(
            model.patient_user_id.is_not(None)
        )
    return query.where(model.patient_user_id.in_(allowed))


async def record_phi_access(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_id: UUID,
    resource_type: str,
    action: PhiAccessAction = PhiAccessAction.READ,
    purpose_of_use: PurposeOfUse = "TREAT",
    resource_id: UUID | None = None,
    result_count: int | None = None,
    request: Request | None = None,
    consent_grant_id: UUID | None = None,
) -> None:
    """Append a PHI access record. Must run in the same transaction as the read."""
    db.add(
        PhiAccessEvent(
            tenant_id=context.tenant_id,
            actor_user_id=context.user.id,
            patient_user_id=patient_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            purpose_of_use=purpose_of_use,
            consent_grant_id=consent_grant_id,
            request_id=(request.headers.get("x-request-id") if request else None),
            ip_address=(request.client.host if request and request.client else None),
            user_agent=(request.headers.get("user-agent") if request else None),
            result_count=result_count,
        )
    )


async def record_phi_access_many(
    db: AsyncSession,
    context: AuthContext,
    *,
    patient_user_ids: list[UUID],
    resource_type: str,
    request: Request | None = None,
    purpose_of_use: PurposeOfUse = "TREAT",
) -> None:
    """Log a list read that spanned several patients, one row per patient."""
    for patient_user_id in dict.fromkeys(patient_user_ids):
        await record_phi_access(
            db,
            context,
            patient_user_id=patient_user_id,
            resource_type=resource_type,
            purpose_of_use=purpose_of_use,
            request=request,
        )


async def write_audit(
    db: AsyncSession,
    context: AuthContext,
    *,
    event_type: str,
    subject_user_id: UUID | None = None,
    resource_id: UUID | None = None,
    event_data: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Append a hash-chained audit row.

    ``event_data`` is metadata only — never PHI bodies. The BEFORE-INSERT
    trigger seals each row into the chain, so these rows cannot be updated or
    deleted afterwards.
    """
    data: dict[str, Any] = dict(event_data or {})
    if resource_id is not None:
        data.setdefault("resource_id", str(resource_id))
    db.add(
        AuditEvent(
            actor_user_id=context.user.id,
            event_type=event_type,
            subject_user_id=subject_user_id,
            ip_address=(request.client.host if request and request.client else None),
            user_agent=(request.headers.get("user-agent") if request else None),
            event_data=data,
        )
    )


class StatusChange(DomainModel):
    """Payload for the state-machine transition endpoints."""

    status: str = Field(min_length=1, max_length=64)
    reason: str | None = Field(default=None, max_length=255)


def assert_transition(current: str, target: str, allowed: dict[str, set[str]]) -> None:
    """Reject an illegal state-machine transition with a 409."""
    if target not in allowed.get(current, set()):
        raise conflict(f"Cannot move from '{current}' to '{target}'")
