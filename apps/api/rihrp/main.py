"""FastAPI アプリ生成。SPA は同一オリジンで配信する。"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import get_settings
from .db import SessionLocal
from .errors import error_body, install_error_handlers
from .request_context import request_id_var
from .routers import admin, auth, claims, health, projects, reports, research, sources
from .seed import seed_all

logger = logging.getLogger("rihrp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

# JSON 本文の上限。出典本文 1 MiB + メタデータを許容し、それ以上は 413 にする。
MAX_BODY_BYTES = 2 * 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    if settings.seed_demo and not settings.is_production:
        try:
            with SessionLocal() as db:
                seed_all(db)
        except Exception as exc:  # noqa: BLE001 - DB 未起動でもプロセスは起動し、readyz で知らせる
            logger.warning("demo seed skipped type=%s", type(exc).__name__)
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
    app.include_router(research.router)
    app.include_router(admin.router)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        token = request_id_var.set(uuid.uuid4().hex)
        try:
            return await _security_headers(request, call_next)
        finally:
            request_id_var.reset(token)

    async def _security_headers(request: Request, call_next):
        # 本文サイズの上限（出典 1 MiB + JSON 余裕）。巨大な本文での DoS を避ける。
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                too_large = int(content_length) > MAX_BODY_BYTES
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(
                    status_code=413,
                    content=error_body("payload_too_large", "リクエスト本文が大きすぎます。"),
                )
        elif request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and request.headers.get(
            "transfer-encoding"
        ):
            # 長さの分からない chunked 本文は、上限を確実に適用できないため拒否する。
            return JSONResponse(
                status_code=411,
                content=error_body("length_required", "Content-Length が必要です。"),
            )
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
        response.headers.setdefault("X-Request-Id", request_id_var.get())
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
