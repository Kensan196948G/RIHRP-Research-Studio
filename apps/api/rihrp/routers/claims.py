"""主張と根拠、検証 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from ..audit import write_audit
from ..auth import Principal, get_principal, require_editor, require_verifier
from ..db import get_db
from ..errors import ApiError
from ..models import Claim, ClaimEvidence, Report
from ..schemas import ClaimIn, ClaimPatch, EvidenceIn
from ..services import (
    _load_evidence,
    claim_to_dict,
    get_claim_or_404,
    get_project_or_404,
    get_source_or_404,
    lock_project,
    verify_claim_row,
)
from ..verify import normalize

router = APIRouter(prefix="/api", tags=["claims"])


def _claim_referenced_in_reports(db: OrmSession, claim_id: str) -> list[str]:
    report_ids: list[str] = []
    reports = db.execute(select(Report)).scalars()
    for report in reports:
        for section in (report.content or {}).get("sections", []):
            for paragraph in section.get("paragraphs", []):
                if claim_id in paragraph.get("claimIds", []):
                    report_ids.append(report.id)
                    break
    return report_ids


@router.get("/projects/{project_id}/claims")
def list_claims(
    project_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    get_project_or_404(db, project_id)
    claims = list(
        db.execute(
            select(Claim).where(Claim.project_id == project_id).order_by(Claim.created_at.desc())
        ).scalars()
    )
    evidence_counts: dict[str, int] = {}
    if claims:
        evidence_counts = dict(
            db.execute(
                select(ClaimEvidence.claim_id, func.count())
                .where(ClaimEvidence.claim_id.in_([claim.id for claim in claims]))
                .group_by(ClaimEvidence.claim_id)
            ).all()
        )
    return {
        "claims": [
            claim_to_dict(claim) | {"evidence_count": int(evidence_counts.get(claim.id, 0))}
            for claim in claims
        ]
    }


@router.post("/projects/{project_id}/claims", status_code=201)
def create_claim(
    project_id: str,
    payload: ClaimIn,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    get_project_or_404(db, project_id)
    claim = Claim(project_id=project_id, text=payload.text.strip(), created_by=principal.user_id)
    db.add(claim)
    db.flush()
    write_audit(
        db,
        actor_id=principal.user_id,
        action="claim.created",
        entity_type="claim",
        entity_id=claim.id,
        project_id=project_id,
        details={"text": claim.text[:200]},
    )
    db.commit()
    return {"claim": claim_to_dict(claim, [])}


@router.get("/claims/{claim_id}")
def get_claim(
    claim_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    claim = get_claim_or_404(db, claim_id)
    return {"claim": claim_to_dict(claim, _load_evidence(db, claim.id))}


@router.patch("/claims/{claim_id}")
def update_claim(
    claim_id: str,
    payload: ClaimPatch,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    claim = get_claim_or_404(db, claim_id)
    claim.text = payload.text.strip()
    claim.last_verdict = None
    claim.last_details = None
    claim.last_verified_at = None
    write_audit(
        db,
        actor_id=principal.user_id,
        action="claim.updated",
        entity_type="claim",
        entity_id=claim.id,
        project_id=claim.project_id,
    )
    db.commit()
    return {"claim": claim_to_dict(claim, _load_evidence(db, claim.id))}


@router.delete("/claims/{claim_id}")
def delete_claim(
    claim_id: str,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    claim = get_claim_or_404(db, claim_id)
    lock_project(db, claim.project_id)
    claim = db.execute(
        select(Claim).where(Claim.id == claim_id).with_for_update()
    ).scalar_one_or_none()
    if claim is None:
        raise ApiError(404, "not_found", "主張が見つかりません。")
    referenced = _claim_referenced_in_reports(db, claim.id)
    if referenced:
        raise ApiError(
            409,
            "claim_in_use",
            "この主張はレポートから参照されています。先にレポートから外してください。",
            {"report_ids": referenced},
        )
    write_audit(
        db,
        actor_id=principal.user_id,
        action="claim.deleted",
        entity_type="claim",
        entity_id=claim.id,
        project_id=claim.project_id,
        details={"text": claim.text[:200]},
    )
    db.delete(claim)
    db.commit()
    return {"ok": True}


@router.post("/claims/{claim_id}/evidence", status_code=201)
def add_evidence(
    claim_id: str,
    payload: EvidenceIn,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    claim = get_claim_or_404(db, claim_id)
    source = get_source_or_404(db, payload.source_id)
    if source.project_id != claim.project_id:
        raise ApiError(422, "validation_error", "出典と主張のテーマが一致しません。")
    quote = payload.quote.strip()
    if quote and normalize(quote) not in normalize(source.content):
        raise ApiError(
            422,
            "quote_not_found",
            "引用がこの出典のスナップショット内に見つかりません。",
            {"source_id": source.id},
        )
    duplicate = db.execute(
        select(ClaimEvidence).where(
            ClaimEvidence.claim_id == claim_id,
            ClaimEvidence.source_id == source.id,
            ClaimEvidence.quote == quote,
        )
    ).scalar_one_or_none()
    if duplicate is not None:
        raise ApiError(409, "conflict", "同じ根拠が既に登録されています。")
    evidence = ClaimEvidence(
        claim_id=claim_id,
        source_id=source.id,
        quote=quote,
        note=payload.note.strip(),
    )
    db.add(evidence)
    claim.last_verdict = None
    claim.last_details = None
    claim.last_verified_at = None
    try:
        db.flush()
        write_audit(
            db,
            actor_id=principal.user_id,
            action="evidence.created",
            entity_type="claim_evidence",
            entity_id=evidence.id,
            project_id=claim.project_id,
            details={"claim_id": claim.id, "source_id": source.id, "quote": quote[:120]},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "conflict", "同じ根拠が既に登録されています。") from None
    return {"evidence": claim_to_dict(claim, _load_evidence(db, claim.id))["evidence"]}


@router.delete("/claims/{claim_id}/evidence/{evidence_id}")
def delete_evidence(
    claim_id: str,
    evidence_id: str,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    claim = get_claim_or_404(db, claim_id)
    evidence = db.get(ClaimEvidence, evidence_id)
    if evidence is None or evidence.claim_id != claim_id:
        raise ApiError(404, "not_found", "根拠が見つかりません。")
    db.delete(evidence)
    claim.last_verdict = None
    claim.last_details = None
    claim.last_verified_at = None
    write_audit(
        db,
        actor_id=principal.user_id,
        action="evidence.deleted",
        entity_type="claim_evidence",
        entity_id=evidence_id,
        project_id=claim.project_id,
        details={"claim_id": claim.id},
    )
    db.commit()
    return {"ok": True}


@router.post("/claims/{claim_id}/verify")
def verify_claim_endpoint(
    claim_id: str,
    principal: Principal = Depends(require_verifier),
    db: OrmSession = Depends(get_db),
) -> dict:
    claim = get_claim_or_404(db, claim_id)
    result = verify_claim_row(db, claim, actor_id=principal.user_id)
    db.commit()
    return {"claim": claim_to_dict(claim, _load_evidence(db, claim.id)), "result": result}


@router.post("/projects/{project_id}/claims/verify")
def verify_project_claims(
    project_id: str,
    principal: Principal = Depends(require_verifier),
    db: OrmSession = Depends(get_db),
) -> dict:
    get_project_or_404(db, project_id)
    claims = list(
        db.execute(
            select(Claim).where(Claim.project_id == project_id).order_by(Claim.created_at)
        ).scalars()
    )
    results = []
    for claim in claims:
        result = verify_claim_row(db, claim, actor_id=principal.user_id)
        results.append(
            {"claim_id": claim.id, "verdict": result["verdict"], "reasons": result["reasons"]}
        )
    db.commit()
    return {"verified": len(results), "results": results}
