"""ヘルスチェック。migration 未適用は readyz で 503 にする。"""

from __future__ import annotations

import logging

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from ..config import REPO_ROOT
from ..db import get_db

logger = logging.getLogger("rihrp.health")
router = APIRouter(tags=["health"])


def _expected_head() -> str | None:
    try:
        config = Config(str(REPO_ROOT / "infra/migrations/alembic.ini"))
        config.set_main_option("script_location", str(REPO_ROOT / "infra/migrations"))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception as exc:  # noqa: BLE001 - readiness は失敗を握りつぶして 503 にする
        logger.warning("failed to read alembic head type=%s", type(exc).__name__)
        return None


def _with_release(request: Request, body: dict[str, object]) -> dict[str, object]:
    identity = getattr(request.app.state, "release_identity", None)
    if identity is not None:
        body["release"] = identity
    return body


@router.get("/healthz")
def healthz(request: Request) -> dict[str, object]:
    return _with_release(request, {"status": "ok"})


@router.get("/readyz")
def readyz(request: Request, db: OrmSession = Depends(get_db)) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
        current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    except Exception as exc:  # noqa: BLE001
        logger.warning("readiness check failed type=%s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content=_with_release(
                request,
                {"status": "unavailable", "reason": "database_unreachable"},
            ),
        )

    head = _expected_head()
    if head is None:
        return JSONResponse(
            status_code=503,
            content=_with_release(
                request,
                {"status": "unavailable", "reason": "migration_metadata_unreadable"},
            ),
        )
    if current != head:
        return JSONResponse(
            status_code=503,
            content=_with_release(
                request,
                {
                    "status": "unavailable",
                    "reason": "migration_pending",
                    "current": current,
                    "head": head,
                },
            ),
        )
    return JSONResponse(
        status_code=200,
        content=_with_release(
            request,
            {"status": "ready", "migration": current},
        ),
    )
