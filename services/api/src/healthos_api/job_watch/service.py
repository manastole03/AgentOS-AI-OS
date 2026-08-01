from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from healthos_api.config import Settings
from healthos_api.db.models import (
    JobWatchAlertDelivery,
    JobWatchPosting,
    JobWatchProfile,
    JobWatchSource,
    PortalNotification,
    User,
)
from healthos_api.integrations.notifications import NotificationDispatcher
from healthos_api.job_watch.schemas import JobWatchResponse, JobWatchSourceResponse, JobWatchUpdate
from healthos_api.job_watch.sources import (
    JobPostingRecord,
    fetch_source_jobs,
    normalize_source_input,
)

DEFAULT_JOB_WATCH_TITLES = [
    "Software Engineer",
    "Software Developer",
    "Software Development Engineer",
    "Software Engineer (SWE)",
    "Software Development Engineer (SDE)",
    "Application Engineer",
    "Full Stack Engineer",
    "Full Stack Developer",
    "Web Developer",
    "Web Application Developer",
    "Backend Engineer",
    "Backend Developer",
    "Frontend Engineer",
    "Frontend Developer",
]


@dataclass(frozen=True)
class ScanSummary:
    scanned_profiles: int = 0
    scanned_sources: int = 0
    new_alerts: int = 0


def build_job_watch_response(
    user: User,
    profile: JobWatchProfile | None,
) -> JobWatchResponse:
    if profile is None:
        return JobWatchResponse(
            enabled=False,
            email_enabled=True,
            destination_email=user.email,
            check_interval_minutes=5,
            titles=list(DEFAULT_JOB_WATCH_TITLES),
            sources=[],
            last_scanned_at=None,
        )
    return JobWatchResponse(
        enabled=profile.enabled,
        email_enabled=profile.email_enabled,
        destination_email=user.email,
        check_interval_minutes=profile.check_interval_minutes,
        titles=profile.titles,
        sources=[
            JobWatchSourceResponse(
                id=item.id,
                source_type=item.source_type,
                board_key=item.board_key,
                company_name=item.company_name,
                board_url=item.board_url,
                enabled=item.enabled,
                initial_sync_completed_at=item.initial_sync_completed_at,
                last_scanned_at=item.last_scanned_at,
                last_error_message=item.last_error_message,
            )
            for item in profile.sources
        ],
        last_scanned_at=profile.last_scanned_at,
    )


async def get_job_watch_profile(db: AsyncSession, user_id: UUID) -> JobWatchProfile | None:
    profile: JobWatchProfile | None = await db.scalar(
        select(JobWatchProfile)
        .options(selectinload(JobWatchProfile.sources))
        .where(JobWatchProfile.user_id == user_id)
    )
    return profile


async def update_job_watch_profile(
    db: AsyncSession,
    *,
    user: User,
    tenant_id: object,
    payload: JobWatchUpdate,
) -> JobWatchProfile:
    profile = await get_job_watch_profile(db, user.id)
    if profile is None:
        profile = JobWatchProfile(
            user_id=user.id,
            tenant_id=cast("UUID", tenant_id),
            titles=list(DEFAULT_JOB_WATCH_TITLES),
        )
        db.add(profile)
        await db.flush()

    if payload.enabled is not None:
        profile.enabled = payload.enabled
    if payload.email_enabled is not None:
        profile.email_enabled = payload.email_enabled
    if payload.check_interval_minutes is not None:
        profile.check_interval_minutes = payload.check_interval_minutes
    if payload.titles is not None:
        profile.titles = _dedupe_preserving_order(payload.titles)
    if payload.source_inputs is not None:
        normalized = [normalize_source_input(item) for item in payload.source_inputs]
        existing = {(item.source_type, item.board_key): item for item in profile.sources}
        next_sources: list[JobWatchSource] = []
        for item in normalized:
            source = existing.pop((item.source_type, item.board_key), None)
            if source is None:
                source = JobWatchSource(
                    source_type=item.source_type,
                    board_key=item.board_key,
                    company_name=item.company_name,
                    board_url=item.board_url,
                    enabled=True,
                )
            else:
                source.company_name = item.company_name
                source.board_url = item.board_url
                source.enabled = True
            next_sources.append(source)
        profile.sources = next_sources

    await db.commit()
    await db.refresh(profile)
    return cast(
        JobWatchProfile,
        await get_job_watch_profile(db, user.id),
    )


async def scan_all_job_watches(
    db: AsyncSession,
    *,
    settings: Settings,
    client: httpx.AsyncClient,
) -> ScanSummary:
    profiles = list(
        (
            await db.scalars(
                select(JobWatchProfile)
                .options(selectinload(JobWatchProfile.sources), selectinload(JobWatchProfile.user))
                .where(JobWatchProfile.enabled.is_(True), JobWatchProfile.email_enabled.is_(True))
            )
        ).all()
    )
    summary = ScanSummary(scanned_profiles=len(profiles))
    for profile in profiles:
        summary = await _scan_profile(
            db,
            settings=settings,
            client=client,
            profile=profile,
            summary=summary,
        )
    await db.commit()
    return summary


async def _scan_profile(
    db: AsyncSession,
    *,
    settings: Settings,
    client: httpx.AsyncClient,
    profile: JobWatchProfile,
    summary: ScanSummary,
) -> ScanSummary:
    now = datetime.now(UTC)
    if profile.last_scanned_at and now - profile.last_scanned_at < timedelta(
        minutes=profile.check_interval_minutes
    ):
        return summary

    dispatcher = NotificationDispatcher(settings, client)
    alerts = summary.new_alerts
    scanned_sources = summary.scanned_sources

    for source in [item for item in profile.sources if item.enabled]:
        scanned_sources += 1
        try:
            jobs = await fetch_source_jobs(
                client,
                source_type=source.source_type,
                board_key=source.board_key,
                company_name=source.company_name,
            )
            source.last_error_at = None
            source.last_error_message = None
            baseline_run = source.initial_sync_completed_at is None
            for job in jobs:
                posting = await _upsert_posting(db, source=source, job=job, seen_at=now)
                if baseline_run:
                    continue
                matched_title = match_job_title(job.title, profile.titles)
                if matched_title is None:
                    continue
                existing = await db.scalar(
                    select(JobWatchAlertDelivery).where(
                        JobWatchAlertDelivery.profile_id == profile.id,
                        JobWatchAlertDelivery.posting_id == posting.id,
                        JobWatchAlertDelivery.channel == "email",
                    )
                )
                if existing is not None:
                    continue
                status = "sent"
                error_message: str | None = None
                sent_at: datetime | None = None
                delivered_at: datetime | None = None
                try:
                    delivered = await dispatcher.dispatch(
                        channel="email",
                        email=profile.user.email,
                        title=f"New job match: {job.title} at {job.company_name}",
                        body=_email_body(job=job, matched_title=matched_title),
                    )
                    if delivered:
                        sent_at = now
                        delivered_at = now
                    else:
                        status = "configuration_required"
                except Exception as exc:  # noqa: BLE001
                    status = "failed"
                    error_message = str(exc)[:500]

                db.add(
                    PortalNotification(
                        tenant_id=profile.tenant_id,
                        recipient_user_id=profile.user_id,
                        channel="email",
                        severity="info",
                        title=f"New job match: {job.title}",
                        body=_notification_body(job=job, matched_title=matched_title),
                        action_url=job.job_url,
                        delivered_at=delivered_at,
                    )
                )
                db.add(
                    JobWatchAlertDelivery(
                        profile_id=profile.id,
                        posting_id=posting.id,
                        recipient_user_id=profile.user_id,
                        channel="email",
                        status=status,
                        matched_title=matched_title,
                        error_message=error_message,
                        sent_at=sent_at,
                    )
                )
                alerts += 1
            if baseline_run:
                source.initial_sync_completed_at = now
            source.last_scanned_at = now
        except Exception as exc:  # noqa: BLE001
            source.last_error_at = now
            source.last_error_message = str(exc)[:500]
    profile.last_scanned_at = now
    return ScanSummary(
        scanned_profiles=summary.scanned_profiles,
        scanned_sources=scanned_sources,
        new_alerts=alerts,
    )


async def _upsert_posting(
    db: AsyncSession,
    *,
    source: JobWatchSource,
    job: JobPostingRecord,
    seen_at: datetime,
) -> JobWatchPosting:
    posting = await db.scalar(
        select(JobWatchPosting).where(
            JobWatchPosting.source_type == source.source_type,
            JobWatchPosting.board_key == source.board_key,
            JobWatchPosting.external_job_id == job.external_job_id,
        )
    )
    if posting is None:
        posting = JobWatchPosting(
            source_type=job.source_type,
            board_key=job.board_key,
            external_job_id=job.external_job_id,
            company_name=job.company_name,
            title=job.title,
            location=job.location,
            job_url=job.job_url,
            published_at=job.published_at,
            remote_updated_at=job.remote_updated_at,
            employment_type=job.employment_type,
            workplace_type=job.workplace_type,
            description_text=job.description_text,
            payload=job.payload,
            last_seen_at=seen_at,
            is_active=True,
        )
        db.add(posting)
        await db.flush()
        return posting
    posting.company_name = job.company_name
    posting.title = job.title
    posting.location = job.location
    posting.job_url = job.job_url
    posting.published_at = job.published_at
    posting.remote_updated_at = job.remote_updated_at
    posting.employment_type = job.employment_type
    posting.workplace_type = job.workplace_type
    posting.description_text = job.description_text
    posting.payload = job.payload
    posting.last_seen_at = seen_at
    posting.is_active = True
    await db.flush()
    return posting


def match_job_title(title: str, targets: Iterable[str]) -> str | None:
    normalized_title = _normalize_title(title)
    for target in targets:
        normalized_target = _normalize_title(target)
        if normalized_target and normalized_target in normalized_title:
            return target
    return None


def _normalize_title(value: str) -> str:
    normalized = value.lower()
    replacements = {
        "front-end": "frontend",
        "front end": "frontend",
        "back-end": "backend",
        "back end": "backend",
        "full-stack": "fullstack",
        "full stack": "fullstack",
        "software development engineer": "sde",
        "software engineer (swe)": "software engineer swe",
        "software development engineer (sde)": "sde",
    }
    for original, replacement in replacements.items():
        normalized = normalized.replace(original, replacement)
    normalized = "".join(char if char.isalnum() or char.isspace() else " " for char in normalized)
    return " ".join(normalized.split())


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            result.append(item)
            seen.add(item)
    return result


def _notification_body(*, job: JobPostingRecord, matched_title: str) -> str:
    location = job.location or "Location not specified"
    return (
        f"Matched {matched_title}: {job.title} at {job.company_name} in {location}. "
        f"Open the posting to review and apply."
    )


def _email_body(*, job: JobPostingRecord, matched_title: str) -> str:
    location = job.location or "Location not specified"
    published = job.published_at.isoformat() if job.published_at else "unknown"
    return (
        f"HealthOS found a new matching job posting.\n\n"
        f"Matched title: {matched_title}\n"
        f"Job title: {job.title}\n"
        f"Company: {job.company_name}\n"
        f"Location: {location}\n"
        f"Published at: {published}\n"
        f"Apply URL: {job.job_url}\n"
    )
