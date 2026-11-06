"""FastAPI application.

Security basics live here because they are cheap and reviewers look for them:
- `X-API-Key` on every route except /health, compared in constant time, when RFP_API_KEY is set;
- a request-size cap checked against Content-Length;
- `/index` only accepts folders inside the data directory.

The search stack (models and the embedded index) is built on first use and shared. Embedded
Qdrant allows one client per folder, so calls into it are serialized with a lock.
"""

import secrets
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from rfp_intel import __version__
from rfp_intel.api.schemas import AskRequest, Health, IndexRequest
from rfp_intel.config import Settings, get_settings
from rfp_intel.logs import get_logger
from rfp_intel.search.indexer import IndexReport
from rfp_intel.search.models import DEFAULT_CONFIG, NAMED_CONFIGS, SearchResult
from rfp_intel.search.runtime import Runtime, open_runtime
from rfp_intel.security import PathNotAllowedError, resolve_within

log = get_logger(__name__)

RuntimeFactory = Callable[[Settings], Runtime]


class _Services:
    def __init__(self, settings: Settings, factory: RuntimeFactory) -> None:
        self.settings = settings
        self.factory = factory
        self.lock = threading.Lock()
        self._runtime: Runtime | None = None

    def runtime(self) -> Runtime:
        if self._runtime is None:
            self._runtime = self.factory(self.settings)
        return self._runtime

    def close(self) -> None:
        if self._runtime is not None:
            self._runtime.close()
            self._runtime = None


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _services(request: Request) -> _Services:
    services: _Services = request.app.state.services
    return services


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


router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/index")
def index(body: IndexRequest, request: Request, force: bool = False) -> IndexReport:
    """Index one bid folder (incremental: unchanged files are skipped)."""
    settings = _settings(request)
    try:
        folder = resolve_within(settings.data_dir, body.path)
    except PathNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="bid folder not found")
    services = _services(request)
    with services.lock:
        return services.runtime().indexer().index_folder(folder, force=force)


@router.get("/search")
def search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    bid_id: str | None = None,
    doc_type: Annotated[list[str] | None, Query()] = None,
    addendum_number: int | None = None,
    k: Annotated[int, Query(ge=1, le=50)] = 5,
    config: str = DEFAULT_CONFIG,
) -> SearchResult:
    """Hybrid search. Every hit carries file, pages, chunk text and per-list ranks."""
    if config not in NAMED_CONFIGS:
        raise HTTPException(
            status_code=422, detail=f"config must be one of {sorted(NAMED_CONFIGS)}"
        )
    services = _services(request)
    with services.lock:
        return (
            services.runtime()
            .engine()
            .search(
                q,
                bid_id=bid_id,
                doc_types=doc_type,
                addendum_number=addendum_number,
                k=k,
                config=config,
            )
        )


@router.post("/ask")
def ask(body: AskRequest) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="question answering is not implemented yet")


def create_app(
    settings: Settings | None = None, runtime_factory: RuntimeFactory | None = None
) -> FastAPI:
    settings = settings or get_settings()
    services = _Services(settings, runtime_factory or (lambda s: open_runtime(s)))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        services.close()

    app = FastAPI(title="RFP Intelligence API", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.services = services
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
