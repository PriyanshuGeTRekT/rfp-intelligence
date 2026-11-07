"""FastAPI application.

Routes live under `/api` (search, ask, bids, jobs, runs). The brief's example endpoints
(`POST /index`, `GET /search?q=...&bid_id=...&top_k=5`, `POST /ask`) are also served at the
root. When the web app has been built (`web/dist`), it is served at `/`.

Security basics:
- `X-API-Key` on every API route except /health, compared in constant time, when
  RFP_API_KEY is set;
- a request-size cap checked against Content-Length;
- paths from requests are resolved inside the data directory, never outside it.
"""

import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from rfp_intel import __version__
from rfp_intel.agents.llm import LLM
from rfp_intel.api.context import AppContext, RuntimeFactory
from rfp_intel.api.routes import ask, bids, compare, runs, search
from rfp_intel.api.schemas import Health
from rfp_intel.config import Settings, get_settings
from rfp_intel.logs import get_logger
from rfp_intel.search.runtime import open_runtime

log = get_logger(__name__)
WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def require_api_key(request: Request, x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = request.app.state.context.settings.api_key
    if expected is None:
        return
    if x_api_key is None or not secrets.compare_digest(
        x_api_key.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")


def _api_router() -> APIRouter:
    router = APIRouter(dependencies=[Depends(require_api_key)])
    for module in (search, ask, bids, compare, runs):
        router.include_router(module.router)
    return router


def _brief_aliases() -> APIRouter:
    """The endpoints the brief names, at the paths it names."""
    router = APIRouter(dependencies=[Depends(require_api_key)], tags=["brief"])
    router.add_api_route("/index", bids.index, methods=["POST"])
    router.add_api_route("/search", search.search, methods=["GET"])
    router.add_api_route("/ask", ask.ask, methods=["POST"])
    return router


def _mount_web(app: FastAPI, dist: Path) -> None:
    """Serve the built single-page app; unknown non-API paths get index.html."""
    if not (dist / "index.html").exists():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "health")):
            raise HTTPException(status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        # index.html names the hashed bundles of the current build: revalidate it on every load,
        # or a browser keeps running the previous build's code after a deploy.
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})


def create_app(
    settings: Settings | None = None,
    runtime_factory: RuntimeFactory | None = None,
    llm: LLM | None = None,
    web_dist: Path | None = WEB_DIST,
) -> FastAPI:
    settings = settings or get_settings()
    ctx = AppContext(settings, runtime_factory or (lambda s: open_runtime(s)), llm)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        ctx.close()

    app = FastAPI(title="RFP Intelligence API", version=__version__, lifespan=lifespan)
    app.state.context = ctx
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

    @app.get("/health", tags=["health"])
    @app.get("/api/health", tags=["health"], include_in_schema=False)
    def health() -> Health:
        return Health(
            status="ok",
            version=__version__,
            llm_provider=settings.llm_provider,
            extract_model=settings.extract_model,
            reranker=ctx.reranker_loaded(),
        )

    app.include_router(_api_router(), prefix="/api")
    app.include_router(_brief_aliases())
    if web_dist is not None:
        _mount_web(app, web_dist)
    return app
