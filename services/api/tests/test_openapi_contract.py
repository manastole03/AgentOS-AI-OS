from healthos_api.main import app


def test_openapi_contains_protected_portal_contracts() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/v1/portal/overview" in paths
    assert "/api/v1/portal/resources/{category}" in paths
    assert "/api/v1/portal/documents" in paths
    assert "/api/v1/portal/payments/intents" in paths
    assert "/api/v1/app-manifest" in paths
    assert "/api/v1/configuration" in paths
    assert "/api/v1/consents" in paths
    assert "/api/v1/users/me/job-watch" in paths
    assert "/api/v1/workflows/{workflow_id}/transitions" in paths
    assert schema["info"]["title"] == "HealthOS Core API"


def test_all_mutating_portal_operations_declare_success_responses() -> None:
    for path, methods in app.openapi()["paths"].items():
        if not path.startswith("/api/v1/portal"):
            continue
        for method, operation in methods.items():
            if method in {"post", "put", "patch", "delete"}:
                assert any(code.startswith("2") for code in operation["responses"]), (path, method)
