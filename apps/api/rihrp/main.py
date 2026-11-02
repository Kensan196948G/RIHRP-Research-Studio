"""FastAPI アプリ生成。SPA は同一オリジンで配信する。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import get_settings
from .db import SessionLocal
from .errors import error_body, install_error_handlers
from .routers import admin, auth, claims, health, projects, reports, sources
from .seed import seed_all

logger = logging.getLogger("rihrp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.seed_demo and not settings.is_production:
        try:
            with SessionLocal() as db:
                seed_all(db)
        except Exception:  # noqa: BLE001 - DB 未起動でもプロセスは起動し、readyz で知らせる
            logger.warning("demo seed skipped (database not ready)", exc_info=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="RIHRP Research Studio API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    install_error_handlers(app)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(sources.router)
    app.include_router(claims.router)
    app.include_router(reports.router)
    app.include_router(admin.router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'",
            )
        return response

    dist: Path = get_settings().web_dist
    assets_dir = dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith(("api/", "healthz", "readyz")):
            return JSONResponse(
                status_code=404, content=error_body("not_found", "エンドポイントが見つかりません。")
            )
        index = dist / "index.html"
        if not index.is_file():
            return JSONResponse(
                status_code=503,
                content=error_body("web_not_built", "Web のビルド成果物がありません。"),
            )
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            candidate = index
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)

    return app


app = create_app()
