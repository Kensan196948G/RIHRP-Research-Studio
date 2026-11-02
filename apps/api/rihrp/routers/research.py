"""研究ワークスペース文書 API（プロトタイプの研究状態をサーバーに保存する）。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as OrmSession

from ..audit import write_audit
from ..auth import Principal, get_principal, require_editor
from ..db import get_db
from ..errors import ApiError
from ..models import ResearchDocument
from ..schemas import ResearchDocIn
from ..services import get_project_or_404, iso, lock_project, utcnow

router = APIRouter(prefix="/api/projects", tags=["research"])

MAX_DOCUMENT_BYTES = 1024 * 1024


def _document_payload(doc: ResearchDocument | None) -> dict:
    if doc is None:
        return {"version": 0, "payload": {}, "updated_at": None, "updated_by": None}
    return {
        "version": doc.version,
        "payload": doc.payload,
        "updated_at": iso(doc.updated_at),
        "updated_by": doc.updated_by,
    }


@router.get("/{project_id}/research")
def get_research_document(
    project_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    project = get_project_or_404(db, project_id)
    return _document_payload(db.get(ResearchDocument, project.id))


@router.put("/{project_id}/research")
def put_research_document(
    project_id: str,
    payload: ResearchDocIn,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    project = get_project_or_404(db, project_id)
    serialized = json.dumps(payload.payload, ensure_ascii=False)
    if len(serialized.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ApiError(
            413,
            "payload_too_large",
            "研究データが大きすぎます（1 MiB 以内にしてください）。",
        )

    # 同一テーマへの同時保存を直列化し、version の取り違えを防ぐ。
    lock_project(db, project.id)
    doc = db.get(ResearchDocument, project.id)
    current = doc.version if doc is not None else 0
    if payload.expected_version != current:
        raise ApiError(
            409,
            "version_conflict",
            "他の更新と競合しました。再読み込みしてください。",
            {"current_version": current},
        )

    created = doc is None
    if doc is None:
        doc = ResearchDocument(
            project_id=project.id,
            version=1,
            payload=payload.payload,
            updated_by=principal.user_id,
        )
        db.add(doc)
    else:
        doc.payload = payload.payload
        doc.version = current + 1
        doc.updated_by = principal.user_id
        doc.updated_at = utcnow()
    project.updated_at = utcnow()
    db.flush()
    write_audit(
        db,
        actor_id=principal.user_id,
        action="research.created" if created else "research.updated",
        entity_type="research_document",
        entity_id=project.id,
        project_id=project.id,
        details={"version": doc.version, "bytes": len(serialized.encode("utf-8"))},
    )
    db.commit()
    return _document_payload(doc)


@router.get("/{project_id}/research/meta")
def get_research_meta(
    project_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    """研究文書の版だけを返す軽量エンドポイント（保存状態の確認用）。"""
    project = get_project_or_404(db, project_id)
    doc = db.get(ResearchDocument, project.id)
    return {"version": doc.version if doc is not None else 0}
