import asyncio
import logging
from uuid import UUID

from redis.exceptions import ResponseError

from healthos_ai.bootstrap import build_runtime
from healthos_ai.config import get_settings
from healthos_platform.logging import configure_logging

logger = logging.getLogger(__name__)


async def serve() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    consumer = f"worker-{id(asyncio.current_task())}"
    async with build_runtime(settings) as runtime:
        try:
            await runtime.redis.xgroup_create(
                settings.queue_stream, settings.queue_consumer_group, id="0", mkstream=True
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        while True:
            messages = await runtime.redis.xreadgroup(
                settings.queue_consumer_group,
                consumer,
                {settings.queue_stream: ">"},
                count=1,
                block=settings.queue_block_ms,
            )
            if not messages:
                claimed = await runtime.redis.xautoclaim(
                    settings.queue_stream,
                    settings.queue_consumer_group,
                    consumer,
                    min_idle_time=settings.queue_claim_idle_ms,
                    start_id="0-0",
                    count=1,
                )
                entries = claimed[1]
                messages = [(settings.queue_stream, entries)] if entries else []
            if not messages:
                continue
            for _stream, entries in messages:
                for message_id, fields in entries:
                    try:
                        await runtime.runs.execute(UUID(fields["run_id"]))
                    except Exception:
                        logger.exception("ai_run_failed", extra={"run_id": fields.get("run_id")})
                    finally:
                        await runtime.redis.xack(
                            settings.queue_stream, settings.queue_consumer_group, message_id
                        )


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
