from fastapi.testclient import TestClient

from healthos_api.main import app


def test_liveness() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"]


def test_protected_profile_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_admin_signup_is_not_exposed() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/signup/admin", json={})

    assert response.status_code == 404
