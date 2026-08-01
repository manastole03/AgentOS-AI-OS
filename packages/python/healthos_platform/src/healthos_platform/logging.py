import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from typing import Any, cast

import structlog

from healthos_platform.config import LogFormat

SENSITIVE_KEY = re.compile(
    r"(authorization|cookie|token|secret|password|otp|email|phone|patient|prompt|content|body|key)",
    re.IGNORECASE,
)


def _redact(value: Any, key: str = "") -> Any:
    if SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): _redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _redact_sensitive_data(
    _logger: logging.Logger, _method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], _redact(event_dict))


def _drop_color_message(
    _logger: logging.Logger, _method_name: str, event_dict: MutableMapping[str, Any]
) -> Mapping[str, Any]:
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging(*, level: str, log_format: LogFormat) -> None:
    """Configure stdlib and structlog as one structured logging pipeline."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _drop_color_message,
        _redact_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if log_format == LogFormat.JSON:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper(), force=True)
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "healthos") -> structlog.stdlib.BoundLogger:
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))
