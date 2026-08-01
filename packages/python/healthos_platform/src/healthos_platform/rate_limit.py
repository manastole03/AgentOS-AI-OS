import hashlib
import json
import time
from collections.abc import Awaitable
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


class DistributedRateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        redis: Redis | None = None,
        service_name: str,
        default_limit: int = 300,
        window_seconds: int = 60,
    ) -> None:
        self.app, self.redis, self.service_name = app, redis, service_name
        self.default_limit, self.window_seconds = default_limit, window_seconds

    def limit_for(self, path: str) -> int:
        if any(item in path for item in ("/auth/login", "/auth/signup", "/auth/otp", "/password/")):
            return 20
        if path.endswith("/ai/v1/runs"):
            return 20
        if "/documents" in path:
            return 60
        return self.default_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(("/health", "/metrics")):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        forwarded = headers.get("x-forwarded-for", "").split(",")[0].strip()
        client = forwarded or (scope.get("client") or ("unknown", 0))[0]
        limit = self.limit_for(scope["path"])
        window = int(time.time()) // self.window_seconds
        digest = hashlib.sha256(f"{client}:{scope['path'].split('/')[1:3]}".encode()).hexdigest()
        key = f"healthos:edge-rate:{self.service_name}:{window}:{digest}"
        try:
            redis = self.redis or scope["app"].state.redis
            result = await cast(Awaitable[Any], redis.eval(LUA, 1, key, str(self.window_seconds)))
            current, ttl = cast(tuple[int, int], result)
        except RedisError:
            await self.app(scope, receive, send)
            return
        remaining = max(0, limit - int(current))
        if int(current) > limit:
            body = json.dumps(
                {
                    "type": "about:blank",
                    "title": "Too many requests",
                    "status": 429,
                    "detail": "Rate limit exceeded",
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/problem+json"),
                        (b"retry-after", str(max(1, int(ttl))).encode()),
                        (b"x-ratelimit-limit", str(limit).encode()),
                        (b"x-ratelimit-remaining", b"0"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_limits(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["X-RateLimit-Limit"] = str(limit)
                response_headers["X-RateLimit-Remaining"] = str(remaining)
            await send(message)

        await self.app(scope, receive, send_with_limits)


class RequestBodyLimitMiddleware:
    def __init__(
        self, app: ASGIApp, *, default_bytes: int = 2_097_152, document_bytes: int = 11_010_048
    ) -> None:
        self.app, self.default_bytes, self.document_bytes = app, default_bytes, document_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        maximum = self.document_bytes if "/documents" in scope["path"] else self.default_bytes
        content_length = Headers(scope=scope).get("content-length")
        try:
            too_large = bool(content_length and int(content_length) > maximum)
        except ValueError:
            too_large = True
        if too_large:
            await self._reject(send)
            return

        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > maximum:
                    raise _PayloadTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _PayloadTooLarge:
            await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = b'{"type":"about:blank","title":"Payload too large","status":413}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/problem+json")],
            }
        )
        await send({"type": "http.response.body", "body": body})


class _PayloadTooLarge(Exception):
    pass
