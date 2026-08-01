import json
from pathlib import Path
from typing import Any

from healthos_ai.main import app as ai_app
from healthos_api.main import app as core_app


def normalized(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> None:
    destination = Path("docs/api")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "openapi-core.json").write_text(normalized(core_app.openapi()))
    (destination / "openapi-ai.json").write_text(normalized(ai_app.openapi()))


if __name__ == "__main__":
    main()
