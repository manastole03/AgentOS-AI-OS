from __future__ import annotations

import argparse
import asyncio

import httpx

from healthos_api.config import get_settings
from healthos_api.db.session import create_database_engine, create_session_factory
from healthos_api.job_watch.service import scan_all_job_watches


async def run(loop: bool) -> None:
    settings = get_settings()
    engine = create_database_engine(settings.database_url.get_secret_value())
    factory = create_session_factory(engine)
    timeout = httpx.Timeout(30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            while True:
                async with factory() as db:
                    summary = await scan_all_job_watches(db, settings=settings, client=client)
                print(  # noqa: T201
                    "job-watch scan complete:",
                    f"profiles={summary.scanned_profiles}",
                    f"sources={summary.scanned_sources}",
                    f"alerts={summary.new_alerts}",
                )
                if not loop:
                    break
                await asyncio.sleep(settings.job_watch_scan_interval_seconds)
        finally:
            await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan configured job watch sources")
    parser.add_argument("--loop", action="store_true", help="Run continuously every 5 minutes")
    args = parser.parse_args()
    asyncio.run(run(loop=args.loop))


if __name__ == "__main__":
    main()
