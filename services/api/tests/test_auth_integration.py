import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from healthos_api.main import app

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION_TESTS") != "1",
    reason="PostgreSQL and Redis integration services are not running",
)
def test_patient_authentication_lifecycle() -> None:
    email = f"patient-{uuid4()}@example.com"
    password = "correct horse battery staple"

    with TestClient(app) as client:
        signup = client.post(
            "/api/v1/auth/signup/patient",
            json={
                "email": email,
                "password": password,
                "first_name": "Integration",
                "last_name": "Patient",
                "phone": "+1 555 0100",
            },
        )
        assert signup.status_code == 201, signup.text
        otp = signup.json()["debug_code"]
        assert otp and len(otp) == 6

        verification = client.post(
            "/api/v1/auth/otp/verify",
            json={
                "email": email,
                "code": otp,
                "purpose": "email_verification",
            },
        )
        assert verification.status_code == 200, verification.text
        mobile_verification = client.post(
            "/api/v1/auth/otp/verify",
            json={
                "email": email,
                "code": signup.json()["debug_mobile_code"],
                "purpose": "mobile_verification",
            },
        )
        assert mobile_verification.status_code == 200, mobile_verification.text

        login = client.post(
            "/api/v1/auth/login/patient",
            json={"email": email, "password": password},
        )
        assert login.status_code == 200, login.text
        assert login.json()["user"]["account_type"] == "patient"
        assert client.cookies.get("healthos_access")
        assert client.cookies.get("healthos_refresh")
        csrf = client.cookies.get("healthos_csrf")
        assert csrf

        profile = client.get("/api/v1/users/me")
        assert profile.status_code == 200, profile.text
        assert len(profile.json()["patient_id"]) == 15
        assert profile.json()["phone_verified"] is True

        update = client.patch(
            "/api/v1/users/me",
            headers={"X-CSRF-Token": csrf},
            json={"phone": "+1 555 0199"},
        )
        assert update.status_code == 200, update.text
        assert update.json()["phone"] == "+1 555 0199"

        refresh = client.post(
            "/api/v1/auth/refresh",
            headers={"X-CSRF-Token": csrf},
        )
        assert refresh.status_code == 200, refresh.text
        rotated_csrf = client.cookies.get("healthos_csrf")
        assert rotated_csrf

        sessions = client.get("/api/v1/auth/sessions")
        assert sessions.status_code == 200, sessions.text
        assert len(sessions.json()) == 1
        assert sessions.json()[0]["current"] is True

        logout = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": rotated_csrf},
        )
        assert logout.status_code == 200, logout.text
        assert client.get("/api/v1/users/me").status_code == 401
