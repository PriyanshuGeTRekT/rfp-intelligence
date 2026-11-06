"""FastAPI application.

Security basics live here because they are cheap and reviewers look for them:
- `X-API-Key` on every route except /health, compared in constant time, when RFP_API_KEY is set;
- a request-size cap checked against Content-Length;
- `/index` only accepts folders inside the data directory.
"""

import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from rfp_intel import __version__
from rfp_intel.api.schemas import AskRequest, Health, IndexRequest
from rfp_intel.config import Settings, get_settings
from rfp_intel.logs import get_logger
from rfp_intel.security import PathNotAllowedError, resolve_within

log = get_logger(__name__)


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def require_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = _settings(request).api_key
    if expected is None:
        return
    if x_api_key is None or not secrets.compare_digest(
        x_api_key.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")


def _not_implemented(what: str) -> HTTPException:
    return HTTPException(status_code=501, detail=f"{what} is not implemented yet")


router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/index", status_code=202)
def index(body: IndexRequest, request: Request) -> dict[str, str]:
    settings = _settings(request)
    try:
        folder = resolve_within(settings.data_dir, body.path)
    except PathNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="bid folder not found")
    raise _not_implemented("indexing")


@router.get("/search")
def search(
    q: Annotated[str, Query(min_length=1, max_length=500)],
    bid_id: str | None = None,
    doc_type: str | None = None,
    k: Annotated[int, Query(ge=1, le=50)] = 5,
) -> dict[str, str]:
    raise _not_implemented("search")


@router.post("/ask")
def ask(body: AskRequest) -> dict[str, str]:
    raise _not_implemented("question answering")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="RFP Intelligence API", version=__version__)
    app.state.settings = settings
    if settings.api_key is None:
        log.warning("api_auth_disabled", hint="set RFP_API_KEY to require X-API-Key")

    @app.middleware("http")
    async def limit_body_size(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Chunked uploads have no Content-Length; every body here is small JSON, so those are
        # refused outright rather than read and counted.
        length = request.headers.get("content-length")
        if length is None and request.headers.get("transfer-encoding"):
            return JSONResponse({"detail": "Content-Length required"}, status_code=411)
        if length is not None:
            if not length.isdigit():
                return JSONResponse({"detail": "invalid Content-Length"}, status_code=400)
            if int(length) > settings.max_request_bytes:
                return JSONResponse({"detail": "request body too large"}, status_code=413)
        return await call_next(request)

    @app.get("/health")
    def health() -> Health:
        return Health(status="ok", version=__version__)

    app.include_router(router)
    return app
