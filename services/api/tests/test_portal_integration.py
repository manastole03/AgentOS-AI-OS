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
def test_patient_portal_workflows() -> None:
    email = f"portal-{uuid4()}@example.com"
    password = "correct horse battery staple"
    with TestClient(app) as client:
        signup = client.post(
            "/api/v1/auth/signup/patient",
            json={
                "email": email,
                "password": password,
                "first_name": "Portal",
                "last_name": "Patient",
                "phone": "+1 555 0198",
            },
        )
        assert signup.status_code == 201
        verification = client.post(
            "/api/v1/auth/otp/verify",
            json={
                "email": email,
                "code": signup.json()["debug_code"],
                "purpose": "email_verification",
            },
        )
        assert verification.status_code == 200
        mobile_verification = client.post(
            "/api/v1/auth/otp/verify",
            json={
                "email": email,
                "code": signup.json()["debug_mobile_code"],
                "purpose": "mobile_verification",
            },
        )
        assert mobile_verification.status_code == 200
        login = client.post(
            "/api/v1/auth/login/patient", json={"email": email, "password": password}
        )
        assert login.status_code == 200
        csrf = client.cookies["healthos_csrf"]
        headers = {"X-CSRF-Token": csrf}

        created = client.post(
            "/api/v1/portal/resources/appointments",
            headers=headers,
            json={
                "title": "Annual wellness visit",
                "status": "scheduled",
                "data": {"location": "North clinic"},
            },
        )
        assert created.status_code == 201, created.text
        record_id = created.json()["id"]

        listed = client.get("/api/v1/portal/resources/appointments")
        assert listed.status_code == 200
        assert any(item["id"] == record_id for item in listed.json())

        updated = client.patch(
            f"/api/v1/portal/resources/appointments/{record_id}",
            headers=headers,
            json={"status": "completed"},
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "completed"

        notification = client.post(
            "/api/v1/portal/notifications",
            headers=headers,
            json={"title": "Visit reminder", "body": "Your appointment is tomorrow."},
        )
        assert notification.status_code == 201
        assert notification.json()["delivered_at"]

        document = client.post(
            "/api/v1/portal/documents",
            headers=headers,
            data={"category": "clinical"},
            files={"file": ("result.txt", b"Hemoglobin result: normal", "text/plain")},
        )
        assert document.status_code == 201, document.text
        assert "Hemoglobin" in document.json()["ocr_text"]
        document_id = document.json()["id"]
        download = client.get(f"/api/v1/portal/documents/{document_id}/content")
        assert download.status_code == 200
        assert download.content == b"Hemoglobin result: normal"

        payment = client.post(
            "/api/v1/portal/payments/intents",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"amount_cents": 2500, "currency": "usd", "description": "Visit copay"},
        )
        assert payment.status_code == 200, payment.text
        assert payment.json()["external_reference"].startswith("local_pi_")

        overview = client.get("/api/v1/portal/overview")
        assert overview.status_code == 200
        assert overview.json()["account_type"] == "patient"
        assert overview.json()["unread_notifications"] == 1

        forbidden = client.get("/api/v1/portal/resources/staff")
        assert forbidden.status_code == 403

        deleted = client.delete(f"/api/v1/portal/documents/{document_id}", headers=headers)
        assert deleted.status_code == 204
