import hashlib

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis
from redis.exceptions import RedisError


async def enforce_rate_limit(
    request: Request,
    *,
    scope: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> None:
    redis: Redis = request.app.state.redis
    digest = hashlib.sha256(identifier.strip().lower().encode()).hexdigest()
    key = f"healthos:rate-limit:{scope}:{digest}"
    try:
        async with redis.pipeline(transaction=True) as pipeline:
            pipeline.incr(key)
            pipeline.expire(key, window_seconds, nx=True)
            count, _ = await pipeline.execute()
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
        ) from exc
    if int(count) > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(window_seconds)},
        )
