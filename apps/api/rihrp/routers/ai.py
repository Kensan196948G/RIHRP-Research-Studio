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
from ..models import ResearchDocument
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


@router.post("/projects/{project_id}/ai/debate")
def debate(
    project_id: str,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    """研究文書から討論の発言候補を作る（保存しない。採用は利用者）。"""
    project = get_project_or_404(db, project_id)
    doc = db.get(ResearchDocument, project.id)
    data = doc.payload if doc is not None and isinstance(doc.payload, dict) else {}
    if not isinstance(data.get("hypothesis"), str) or not data["hypothesis"].strip():
        raise ApiError(422, "validation_error", "研究仮説が未入力です。")
    llm.check_draft_rate(principal.user_id)
    messages, meta = llm.generate_debate(data)
    write_audit(
        db,
        actor_id=principal.user_id,
        action="ai.debate_requested",
        entity_type="project",
        entity_id=project.id,
        project_id=project_id,
        details={
            "provider": meta["provider"],
            "model": meta["model"],
            "prompt_version": meta["prompt_version"],
            "messages": meta["messages"],
            "latency_ms": meta["latency_ms"],
        },
    )
    db.commit()
    return {"messages": messages, "meta": meta}


@router.post("/projects/{project_id}/ai/critiques")
def critiques(
    project_id: str,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    """04 の批判候補を作る（保存しない。重要度は人間が決める）。"""
    project = get_project_or_404(db, project_id)
    doc = db.get(ResearchDocument, project.id)
    data = doc.payload if doc is not None and isinstance(doc.payload, dict) else {}
    if not isinstance(data.get("hypothesis"), str) or not data["hypothesis"].strip():
        raise ApiError(422, "validation_error", "研究仮説が未入力です。")
    llm.check_draft_rate(principal.user_id)
    items, meta = llm.generate_critiques(data)
    write_audit(
        db,
        actor_id=principal.user_id,
        action="ai.critique_requested",
        entity_type="project",
        entity_id=project.id,
        project_id=project_id,
        details={
            "provider": meta["provider"],
            "model": meta["model"],
            "prompt_version": meta["prompt_version"],
            "items": meta["items"],
            "latency_ms": meta["latency_ms"],
        },
    )
    db.commit()
    return {"items": items, "meta": meta}


@router.post("/projects/{project_id}/ai/candidates")
def candidates(
    project_id: str,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    """05 の候補を作る（保存しない。採点は採用後に既存ロジックで行う）。"""
    project = get_project_or_404(db, project_id)
    doc = db.get(ResearchDocument, project.id)
    data = doc.payload if doc is not None and isinstance(doc.payload, dict) else {}
    if not isinstance(data.get("hypothesis"), str) or not data["hypothesis"].strip():
        raise ApiError(422, "validation_error", "研究仮説が未入力です。")
    llm.check_draft_rate(principal.user_id)
    items, meta = llm.generate_candidates(data)
    write_audit(
        db,
        actor_id=principal.user_id,
        action="ai.candidate_requested",
        entity_type="project",
        entity_id=project.id,
        project_id=project_id,
        details={
            "provider": meta["provider"],
            "model": meta["model"],
            "prompt_version": meta["prompt_version"],
            "items": meta["items"],
            "latency_ms": meta["latency_ms"],
        },
    )
    db.commit()
    return {"items": items, "meta": meta}
