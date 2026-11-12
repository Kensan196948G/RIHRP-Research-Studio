"""AI 下書き API（生成のみ）。ADR-0006。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as OrmSession

from .. import llm
from ..audit import write_audit
from ..auth import Principal, require_editor
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..schemas import AiDraftIn
from ..services import get_project_or_404, get_source_or_404

router = APIRouter(prefix="/api", tags=["ai"])


@router.post("/projects/{project_id}/ai/draft-claims")
def draft_claims(
    project_id: str,
    payload: AiDraftIn,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    get_project_or_404(db, project_id)
    source = get_source_or_404(db, payload.source_id)
    if source.project_id != project_id:
        raise ApiError(422, "validation_error", "出典とテーマが一致しません。")
    settings = get_settings()
    if len(source.content) > settings.llm_max_source_chars:
        raise ApiError(
            413,
            "source_too_large",
            f"出典本文が長すぎます（上限 {settings.llm_max_source_chars} 文字）。",
        )
    llm.check_draft_rate(principal.user_id)
    candidates, meta = llm.draft_claims(source.content, max_claims=settings.llm_max_claims)
    write_audit(
        db,
        actor_id=principal.user_id,
        action="ai.draft_requested",
        entity_type="source",
        entity_id=source.id,
        project_id=project_id,
        details={
            "provider": meta["provider"],
            "model": meta["model"],
            "candidates": meta["candidates"],
            "valid": meta["valid"],
            "latency_ms": meta["latency_ms"],
        },
    )
    db.commit()
    return {"candidates": candidates, "meta": meta}
