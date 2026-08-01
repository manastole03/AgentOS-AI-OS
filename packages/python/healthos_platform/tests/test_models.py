from healthos_platform.models import HealthResponse


def test_health_response_defaults() -> None:
    response = HealthResponse(service="test", status="ok", version="0.1.0")

    assert response.status == "ok"
    assert response.checks == {}
