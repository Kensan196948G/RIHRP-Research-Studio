"""出典（根拠スナップショット）API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from ..audit import write_audit
from ..auth import Principal, get_principal, require_editor
from ..db import get_db
from ..errors import ApiError
from ..models import ClaimEvidence, Source
from ..schemas import SourceIn
from ..services import (
    get_project_or_404,
    get_source_or_404,
    iso,
    lock_project,
    sha256_text,
    source_to_dict,
    utcnow,
)

router = APIRouter(prefix="/api", tags=["sources"])


@router.get("/projects/{project_id}/sources")
def list_sources(
    project_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    get_project_or_404(db, project_id)
    sources = list(
        db.execute(
            select(Source).where(Source.project_id == project_id).order_by(Source.created_at.desc())
        ).scalars()
    )
    usage = (
        dict(
            db.execute(
                select(ClaimEvidence.source_id, func.count())
                .where(ClaimEvidence.source_id.in_([s.id for s in sources]))
                .group_by(ClaimEvidence.source_id)
            ).all()
        )
        if sources
        else {}
    )
    items = []
    for source in sources:
        item = source_to_dict(source)
        item.pop("content", None)
        item["used_by_claims"] = int(usage.get(source.id, 0))
        items.append(item)
    return {"sources": items}


@router.post("/projects/{project_id}/sources", status_code=201)
def create_source(
    project_id: str,
    payload: SourceIn,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    lock_project(db, project_id)
    digest = sha256_text(payload.content)
    existing = db.execute(
        select(Source).where(Source.project_id == project_id, Source.content_sha256 == digest)
    ).scalar_one_or_none()
    if existing is not None:
        raise ApiError(
            409,
            "conflict",
            "同じ内容の出典が既に登録されています。",
            {"source_id": existing.id},
        )
    source = Source(
        project_id=project_id,
        title=payload.title.strip(),
        kind=payload.kind,
        origin=payload.origin.strip(),
        content=payload.content,
        content_sha256=digest,
        created_by=principal.user_id,
    )
    db.add(source)
    try:
        db.flush()
        write_audit(
            db,
            actor_id=principal.user_id,
            action="source.created",
            entity_type="source",
            entity_id=source.id,
            project_id=project_id,
            details={"title": source.title, "kind": source.kind, "sha256": digest},
        )
        db.commit()
    except IntegrityError:
        # 事前チェックと commit の間に同じ内容が登録された場合（競合）
        db.rollback()
        raise ApiError(409, "conflict", "同じ内容の出典が既に登録されています。") from None
    return {"source": source_to_dict(source)}


@router.get("/sources/{source_id}")
def get_source(
    source_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    source = get_source_or_404(db, source_id)
    return {"source": source_to_dict(source)}


@router.delete("/sources/{source_id}")
def delete_source(
    source_id: str,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    source = db.execute(
        select(Source)
        .where(Source.id == source_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if source is None:
        raise ApiError(404, "not_found", "出典が見つかりません。")
    used = db.execute(
        select(func.count()).select_from(ClaimEvidence).where(ClaimEvidence.source_id == source_id)
    ).scalar_one()
    if used:
        raise ApiError(
            409,
            "source_in_use",
            "この出典は主張の根拠として使われています。先に根拠の紐付けを外してください。",
            {"used_by_claims": int(used)},
        )
    write_audit(
        db,
        actor_id=principal.user_id,
        action="source.deleted",
        entity_type="source",
        entity_id=source.id,
        project_id=source.project_id,
        details={"title": source.title, "sha256": source.content_sha256},
    )
    db.delete(source)
    db.commit()
    return {"ok": True, "deleted_at": iso(utcnow())}
