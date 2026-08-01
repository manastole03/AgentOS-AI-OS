import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from healthos_api.config import get_settings
from healthos_api.db.models import JobWatchAlertDelivery
from healthos_api.integrations.notifications import NotificationDispatcher
from healthos_api.job_watch.service import match_job_title, scan_all_job_watches
from healthos_api.job_watch.sources import JobPostingRecord, normalize_source_input
from healthos_api.main import app


def test_normalize_job_watch_source_urls() -> None:
    greenhouse = normalize_source_input("https://boards.greenhouse.io/openai")
    assert greenhouse.source_type == "greenhouse"
    assert greenhouse.board_key == "openai"

    lever = normalize_source_input("https://jobs.lever.co/exampleco")
    assert lever.source_type == "lever"
    assert lever.board_key == "exampleco"

    ashby = normalize_source_input("https://jobs.ashbyhq.com/posthog")
    assert ashby.source_type == "ashby"
    assert ashby.board_key == "posthog"


def test_title_matching_handles_common_engineering_variants() -> None:
    assert (
        match_job_title("Senior Front-End Engineer", ["Frontend Engineer"]) == "Frontend Engineer"
    )
    assert match_job_title("Staff Backend Developer", ["Backend Developer"]) == "Backend Developer"
    assert match_job_title("Software Development Engineer II", ["Software Development Engineer"])
    assert match_job_title("Product Manager", ["Software Engineer"]) is None


@pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="PostgreSQL and Redis integration services are not running",
)
@pytest.mark.integration
def test_job_watch_profile_and_scanner(monkeypatch: pytest.MonkeyPatch) -> None:
    email = f"watch-{uuid4()}@example.com"
    password = "correct horse battery staple"
    job_versions = [
        [
            JobPostingRecord(
                source_type="greenhouse",
                board_key="openai",
                external_job_id="1",
                company_name="Openai",
                title="Software Engineer, Platform",
                location="San Francisco, CA",
                job_url="https://boards.greenhouse.io/openai/jobs/1",
                published_at=datetime.now(UTC),
                remote_updated_at=datetime.now(UTC),
                employment_type=None,
                workplace_type=None,
                description_text="Platform team",
                payload={},
            )
        ],
        [
            JobPostingRecord(
                source_type="greenhouse",
                board_key="openai",
                external_job_id="1",
                company_name="Openai",
                title="Software Engineer, Platform",
                location="San Francisco, CA",
                job_url="https://boards.greenhouse.io/openai/jobs/1",
                published_at=datetime.now(UTC),
                remote_updated_at=datetime.now(UTC),
                employment_type=None,
                workplace_type=None,
                description_text="Platform team",
                payload={},
            ),
            JobPostingRecord(
                source_type="greenhouse",
                board_key="openai",
                external_job_id="2",
                company_name="Openai",
                title="Backend Engineer, Inference",
                location="Remote",
                job_url="https://boards.greenhouse.io/openai/jobs/2",
                published_at=datetime.now(UTC),
                remote_updated_at=datetime.now(UTC),
                employment_type=None,
                workplace_type="Remote",
                description_text="Inference",
                payload={},
            ),
        ],
    ]

    async def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
        return job_versions.pop(0)

    async def fake_dispatch(self, *, channel: str, email: str, title: str, body: str) -> bool:
        assert channel == "email"
        assert email == email_address
        assert "New job match" in title
        assert body
        return True

    monkeypatch.setattr("healthos_api.job_watch.service.fetch_source_jobs", fake_fetch)
    email_address = email
    monkeypatch.setattr(NotificationDispatcher, "dispatch", fake_dispatch)

    with TestClient(app) as client:
        signup = client.post(
            "/api/v1/auth/signup/patient",
            json={
                "email": email,
                "password": password,
                "first_name": "Job",
                "last_name": "Watcher",
                "phone": "+1 555 0197",
            },
        )
        assert signup.status_code == 201, signup.text
        assert (
            client.post(
                "/api/v1/auth/otp/verify",
                json={
                    "email": email,
                    "code": signup.json()["debug_code"],
                    "purpose": "email_verification",
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/auth/otp/verify",
                json={
                    "email": email,
                    "code": signup.json()["debug_mobile_code"],
                    "purpose": "mobile_verification",
                },
            ).status_code
            == 200
        )
        login = client.post(
            "/api/v1/auth/login/patient",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, login.text
        csrf = client.cookies["healthos_csrf"]

        default_watch = client.get("/api/v1/users/me/job-watch")
        assert default_watch.status_code == 200, default_watch.text
        assert "Software Engineer" in default_watch.json()["titles"]

        update = client.patch(
            "/api/v1/users/me/job-watch",
            headers={"X-CSRF-Token": csrf},
            json={
                "enabled": True,
                "titles": ["Software Engineer", "Backend Engineer"],
                "source_inputs": ["https://boards.greenhouse.io/openai"],
            },
        )
        assert update.status_code == 200, update.text
        assert update.json()["sources"][0]["source_type"] == "greenhouse"

        async def run_scan() -> tuple[int, int, int]:
            settings = get_settings()
            async with httpx.AsyncClient() as async_client:
                async with app.state.session_factory() as db:
                    first = await scan_all_job_watches(db, settings=settings, client=async_client)
                async with app.state.session_factory() as db:
                    second = await scan_all_job_watches(db, settings=settings, client=async_client)
                async with app.state.session_factory() as db:
                    deliveries = await db.scalar(
                        select(func.count()).select_from(JobWatchAlertDelivery)
                    )
                return first.new_alerts, second.new_alerts, int(deliveries or 0)

        first_alerts, second_alerts, deliveries = asyncio.run(run_scan())

        assert first_alerts == 0
        assert second_alerts == 1
        assert deliveries == 1

        notifications = client.get("/api/v1/portal/notifications")
        assert notifications.status_code == 200, notifications.text
        assert any("New job match" in item["title"] for item in notifications.json())
