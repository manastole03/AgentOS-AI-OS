from urllib.parse import urljoin

from fastapi import APIRouter, HTTPException, Request, Response, status
from httpx import AsyncClient, RequestError
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from healthos_gateway.config import get_settings

router = APIRouter()
FORWARDED_REQUEST_HEADERS = {
    "accept",
    "authorization",
    "content-type",
    "cookie",
    "x-request-id",
}
FORWARDED_RESPONSE_HEADERS = {
    "cache-control",
    "content-type",
    "location",
    "www-authenticate",
}


async def _proxy(request: Request, upstream_base: str, path: str) -> Response:
    client: AsyncClient = request.app.state.http_client
    url = urljoin(f"{upstream_base.rstrip('/')}/", path)
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() in FORWARDED_REQUEST_HEADERS
    }
    try:
        outgoing = client.build_request(
            method=request.method,
            url=url,
            params=request.query_params,
            headers=headers,
            content=await request.body(),
        )
        upstream = await client.send(outgoing, stream=path.endswith("/events"))
    except RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Upstream service is unavailable",
        ) from exc
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in FORWARDED_RESPONSE_HEADERS
    }
    if path.endswith("/events"):
        return StreamingResponse(
            upstream.aiter_raw(),
            status_code=upstream.status_code,
            headers=response_headers,
            background=BackgroundTask(upstream.aclose),
        )
    content = await upstream.aread()
    response = Response(
        content=content,
        status_code=upstream.status_code,
        headers=response_headers,
    )
    for cookie in upstream.headers.get_list("set-cookie"):
        response.headers.append("set-cookie", cookie)
    return response


@router.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_api(request: Request, path: str) -> Response:
    return await _proxy(request, str(get_settings().api_service_url), f"api/{path}")


@router.api_route("/ai/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_ai(request: Request, path: str) -> Response:
    return await _proxy(request, str(get_settings().ai_service_url), f"ai/{path}")
