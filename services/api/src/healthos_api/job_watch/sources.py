from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import httpx

SUPPORTED_SOURCE_TYPES = {"greenhouse", "lever", "ashby"}


@dataclass(frozen=True)
class NormalizedSourceInput:
    source_type: str
    board_key: str
    company_name: str
    board_url: str


@dataclass(frozen=True)
class JobPostingRecord:
    source_type: str
    board_key: str
    external_job_id: str
    company_name: str
    title: str
    location: str | None
    job_url: str
    published_at: datetime | None
    remote_updated_at: datetime | None
    employment_type: str | None
    workplace_type: str | None
    description_text: str | None
    payload: dict[str, object]


class JobSourceError(RuntimeError):
    pass


def normalize_source_input(value: str) -> NormalizedSourceInput:
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return _normalize_compact_source(value)

    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query)

    if "greenhouse.io" in host:
        board_key = query.get("for", [None])[0] or (path_parts[0] if path_parts else None)
        if not board_key:
            raise ValueError(f"Unable to determine Greenhouse board token from {value}")
        return NormalizedSourceInput(
            source_type="greenhouse",
            board_key=board_key,
            company_name=_humanize_company_name(board_key),
            board_url=f"https://boards.greenhouse.io/{board_key}",
        )

    if "lever.co" in host:
        board_key = path_parts[0] if path_parts else None
        if not board_key:
            raise ValueError(f"Unable to determine Lever site from {value}")
        return NormalizedSourceInput(
            source_type="lever",
            board_key=board_key,
            company_name=_humanize_company_name(board_key),
            board_url=f"https://jobs.lever.co/{board_key}",
        )

    if "ashbyhq.com" in host:
        if path_parts[:3] == ["posting-api", "job-board"] and len(path_parts) >= 3:
            board_key = path_parts[2]
        else:
            board_key = path_parts[0] if path_parts else None
        if not board_key:
            raise ValueError(f"Unable to determine Ashby job board from {value}")
        return NormalizedSourceInput(
            source_type="ashby",
            board_key=board_key,
            company_name=_humanize_company_name(board_key),
            board_url=f"https://jobs.ashbyhq.com/{board_key}",
        )

    raise ValueError(
        "Unsupported source URL. Use a Greenhouse, Lever, or Ashby public job board URL."
    )


async def fetch_source_jobs(
    client: httpx.AsyncClient,
    *,
    source_type: str,
    board_key: str,
    company_name: str,
) -> list[JobPostingRecord]:
    if source_type == "greenhouse":
        return await _fetch_greenhouse(client, board_key=board_key, company_name=company_name)
    if source_type == "lever":
        return await _fetch_lever(client, board_key=board_key, company_name=company_name)
    if source_type == "ashby":
        return await _fetch_ashby(client, board_key=board_key, company_name=company_name)
    raise JobSourceError(f"Unsupported source type: {source_type}")


async def _fetch_greenhouse(
    client: httpx.AsyncClient, *, board_key: str, company_name: str
) -> list[JobPostingRecord]:
    response = await client.get(
        f"https://boards-api.greenhouse.io/v1/boards/{board_key}/jobs",
        params={"content": "true"},
    )
    response.raise_for_status()
    payload = response.json()
    jobs = payload.get("jobs", [])
    records: list[JobPostingRecord] = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        records.append(
            JobPostingRecord(
                source_type="greenhouse",
                board_key=board_key,
                external_job_id=str(item.get("id")),
                company_name=company_name,
                title=str(item.get("title", "")).strip(),
                location=_string_or_none(item.get("location"), key="name"),
                job_url=str(item.get("absolute_url", "")).strip(),
                published_at=_parse_datetime(item.get("updated_at")),
                remote_updated_at=_parse_datetime(item.get("updated_at")),
                employment_type=None,
                workplace_type=None,
                description_text=_clean_text(item.get("content")),
                payload=item,
            )
        )
    return [record for record in records if record.title and record.job_url]


async def _fetch_lever(
    client: httpx.AsyncClient, *, board_key: str, company_name: str
) -> list[JobPostingRecord]:
    items: list[dict[str, object]] = []
    skip = 0
    limit = 100
    while True:
        response = await client.get(
            f"https://api.lever.co/v0/postings/{board_key}",
            params={"mode": "json", "skip": skip, "limit": limit},
        )
        response.raise_for_status()
        page = response.json()
        if not isinstance(page, list) or not page:
            break
        items.extend(item for item in page if isinstance(item, dict))
        if len(page) < limit:
            break
        skip += limit

    records: list[JobPostingRecord] = []
    for item in items:
        categories = item.get("categories") if isinstance(item.get("categories"), dict) else {}
        records.append(
            JobPostingRecord(
                source_type="lever",
                board_key=board_key,
                external_job_id=str(item.get("id")),
                company_name=company_name,
                title=str(item.get("text", "")).strip(),
                location=_string_or_none(categories, key="location"),
                job_url=str(
                    item.get("hostedUrl") or item.get("applyUrl") or item.get("url") or ""
                ).strip(),
                published_at=_parse_datetime(item.get("createdAt")),
                remote_updated_at=_parse_datetime(item.get("updatedAt")),
                employment_type=_string_or_none(categories, key="commitment"),
                workplace_type=_string_or_none(categories, key="workplaceType"),
                description_text=_clean_text(
                    item.get("descriptionPlain") or item.get("description") or item.get("lists")
                ),
                payload=item,
            )
        )
    return [record for record in records if record.title and record.job_url]


async def _fetch_ashby(
    client: httpx.AsyncClient, *, board_key: str, company_name: str
) -> list[JobPostingRecord]:
    response = await client.get(f"https://api.ashbyhq.com/posting-api/job-board/{board_key}")
    response.raise_for_status()
    payload = response.json()
    jobs = payload.get("jobs", [])
    records: list[JobPostingRecord] = []
    for item in jobs:
        if not isinstance(item, dict):
            continue
        records.append(
            JobPostingRecord(
                source_type="ashby",
                board_key=board_key,
                external_job_id=str(
                    item.get("id") or item.get("jobPostingId") or item.get("jobUrl") or ""
                ),
                company_name=company_name,
                title=str(item.get("title", "")).strip(),
                location=_string_or_none(item, key="location"),
                job_url=str(item.get("jobUrl") or item.get("applyUrl") or "").strip(),
                published_at=_parse_datetime(item.get("publishedAt")),
                remote_updated_at=_parse_datetime(item.get("updatedAt") or item.get("publishedAt")),
                employment_type=_string_or_none(item, key="employmentType"),
                workplace_type=_string_or_none(item, key="workplaceType"),
                description_text=_clean_text(
                    item.get("descriptionPlain") or item.get("descriptionHtml")
                ),
                payload=item,
            )
        )
    return [record for record in records if record.title and record.job_url]


def _normalize_compact_source(value: str) -> NormalizedSourceInput:
    source_type, _, board_key = value.partition(":")
    source_type = source_type.strip().lower()
    board_key = board_key.strip()
    if source_type not in SUPPORTED_SOURCE_TYPES or not board_key:
        raise ValueError(
            "Use a supported public job board URL or a compact source like greenhouse:company."
        )
    if source_type == "greenhouse":
        board_url = f"https://boards.greenhouse.io/{board_key}"
    elif source_type == "lever":
        board_url = f"https://jobs.lever.co/{board_key}"
    else:
        board_url = f"https://jobs.ashbyhq.com/{board_key}"
    return NormalizedSourceInput(
        source_type=source_type,
        board_key=board_key,
        company_name=_humanize_company_name(board_key),
        board_url=board_url,
    )


def _humanize_company_name(board_key: str) -> str:
    label = re.sub(r"[_\-]+", " ", board_key).strip()
    return re.sub(r"\s+", " ", label).title()


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _string_or_none(value: object, *, key: str) -> str | None:
    if isinstance(value, dict):
        candidate = value.get(key)
        if candidate is None:
            return None
        return str(candidate).strip() or None
    return None


def _parse_datetime(value: object) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
