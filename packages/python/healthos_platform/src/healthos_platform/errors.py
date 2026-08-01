from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import trace

from healthos_platform.logging import get_logger

logger = get_logger("errors")


def _trace_id() -> str | None:
    context = trace.get_current_span().get_span_context()
    return f"{context.trace_id:032x}" if context.is_valid else None


def _problem(
    request: Request,
    status: int,
    title: str,
    detail: str,
    *,
    errors: list[dict[str, object]] | None = None,
    error_id: str | None = None,
) -> JSONResponse:
    error_id = error_id or str(uuid4())
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "error_id": error_id,
        "request_id": getattr(request.state, "request_id", None),
        "trace_id": _trace_id(),
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed"
        response = _problem(request, exc.status_code, "Request failed", detail)
        response.headers.update(exc.headers or {})
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "location": ".".join(str(part) for part in item["loc"]),
                "message": item["msg"],
                "type": item["type"],
            }
            for item in exc.errors()
        ]
        return _problem(
            request, 422, "Validation failed", "One or more fields are invalid", errors=errors
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        error_id = str(uuid4())
        logger.exception("unhandled_exception", error_id=error_id, error_type=type(exc).__name__)
        response = _problem(
            request,
            500,
            "Internal server error",
            "An unexpected error occurred. Contact support with the error ID.",
            error_id=error_id,
        )
        return response
