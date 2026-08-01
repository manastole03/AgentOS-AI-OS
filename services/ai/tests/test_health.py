from fastapi.testclient import TestClient

from healthos_ai.main import app


def test_liveness() -> None:
    with TestClient(app) as client:
        response = client.get("/ai/v1/health/live")

    assert response.status_code == 200
    assert response.json()["service"] == "healthos-ai"
