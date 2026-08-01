from fastapi.testclient import TestClient

from healthos_api.main import app


def test_validation_errors_use_problem_details_without_echoing_input() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/signup/patient",
            json={"email": "not-an-email", "password": "short"},
        )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["title"] == "Validation failed"
    assert "not-an-email" not in response.text
    assert payload["request_id"]


def test_metrics_endpoint_exports_red_metrics() -> None:
    with TestClient(app) as client:
        client.get("/api/v1/health/live")
        response = client.get("/metrics")
    assert response.status_code == 200
    assert "healthos_http_requests_total" in response.text


def test_request_body_limit_rejects_oversized_json() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/auth/login/patient",
            content=b"x" * 2_100_000,
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 413
