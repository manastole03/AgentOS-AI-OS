import asyncio
import os
import sys

import httpx

from healthos_ai.evaluation import ROUTING_CASES


async def main() -> int:
    base_url = os.environ.get("HEALTHOS_URL", "http://localhost:8080")
    token = os.environ.get("ACCESS_TOKEN", "")
    if not token:
        print("ACCESS_TOKEN is required", file=sys.stderr)
        return 2
    failures: list[str] = []
    async with httpx.AsyncClient(base_url=base_url, timeout=180) as client:
        for case in ROUTING_CASES:
            response = await client.post(
                "/ai/v1/runs",
                headers={"Authorization": f"Bearer {token}"},
                json={"prompt": case.prompt, "execution_mode": "sync", "memory_mode": "none"},
            )
            if response.status_code != 201:
                failures.append(f"{case.name}: HTTP {response.status_code}")
                continue
            result = response.json()
            if result.get("selected_team") != case.expected_team.value:
                actual_team = result.get("selected_team")
                failures.append(
                    f"{case.name}: expected {case.expected_team.value}, got {actual_team}"
                )
            if not result.get("response"):
                failures.append(f"{case.name}: empty response")
    for failure in failures:
        print(failure, file=sys.stderr)
    print(
        f"Agent evaluation: {len(ROUTING_CASES) - len(failures)}/{len(ROUTING_CASES)} checks passed"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
