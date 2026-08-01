import logging

from healthos_platform.logging import _redact_sensitive_data
from healthos_platform.rate_limit import DistributedRateLimitMiddleware, RequestBodyLimitMiddleware


def test_structured_log_redaction_removes_phi_and_credentials() -> None:
    event = {
        "event": "test",
        "authorization": "Bearer secret",
        "patient_id": "PAT123",
        "nested": {"email": "patient@example.com", "safe": "visible"},
    }
    result = _redact_sensitive_data(logging.getLogger(), "info", event)

    assert result["authorization"] == "[REDACTED]"
    assert result["patient_id"] == "[REDACTED]"
    assert result["nested"]["email"] == "[REDACTED]"
    assert result["nested"]["safe"] == "visible"


async def test_body_limit_counts_streamed_chunks_without_content_length() -> None:
    incoming = iter(
        [
            {"type": "http.request", "body": b"x" * 600, "more_body": True},
            {"type": "http.request", "body": b"y" * 600, "more_body": False},
        ]
    )
    sent: list[dict[str, object]] = []

    async def receive() -> dict[str, object]:
        return next(incoming)

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    async def consume_body(scope, receive, send) -> None:
        while (await receive()).get("more_body"):
            pass
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestBodyLimitMiddleware(consume_body, default_bytes=1_000)
    await middleware(
        {"type": "http", "path": "/api/test", "headers": []},
        receive,
        send,
    )

    assert sent[0]["status"] == 413


async def test_distributed_rate_limit_returns_retry_metadata() -> None:
    sent: list[dict[str, object]] = []

    class OverLimitRedis:
        async def eval(self, *_args):
            return 21, 45

    async def downstream(scope, receive, send) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    middleware = DistributedRateLimitMiddleware(
        downstream,
        redis=OverLimitRedis(),
        service_name="test",
    )
    await middleware(
        {
            "type": "http",
            "path": "/api/v1/auth/login/patient",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        },
        receive,
        send,
    )

    assert sent[0]["status"] == 429
    assert (b"retry-after", b"45") in sent[0]["headers"]
