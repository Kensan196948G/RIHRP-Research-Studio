"""レポート・検証・レビュー・エクスポート API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from ..audit import write_audit
from ..auth import Principal, get_principal, require_editor, require_reviewer, require_verifier
from ..db import get_db
from ..errors import ApiError
from ..models import Claim, Report, ReportVerification, ReportVersion, Review, User, new_id
from ..schemas import (
    ReportContentIn,
    ReportIn,
    ReportSubmitIn,
    ReportUpdate,
    ReviewIn,
    content_to_dict,
)
from ..services import (
    collect_report_claim_ids,
    get_project_or_404,
    get_report_for_update,
    get_report_or_404,
    iso,
    lock_project,
    make_version,
    render_markdown,
    report_integrity,
    report_to_dict,
    seal_content,
    utcnow,
    verify_report_row,
)

router = APIRouter(prefix="/api", tags=["reports"])


def _latest_verification(db: OrmSession, report_id: str) -> ReportVerification | None:
    return db.execute(
        select(ReportVerification)
        .where(ReportVerification.report_id == report_id)
        .order_by(ReportVerification.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _reviews(db: OrmSession, report_id: str) -> list[tuple[Review, User | None]]:
    rows = db.execute(
        select(Review, User)
        .outerjoin(User, User.id == Review.reviewer_id)
        .where(Review.report_id == report_id)
        .order_by(Review.created_at.desc())
    ).all()
    return [(review, user) for review, user in rows]


def _report_full(db: OrmSession, report: Report) -> dict:
    submitter = db.get(User, report.submitted_by) if report.submitted_by else None
    payload = report_to_dict(
        report,
        latest_verification=_latest_verification(db, report.id),
        reviews=_reviews(db, report.id),
        submitted_by_name=submitter.name if submitter else None,
    )
    payload["integrity"] = report_integrity(db, report)
    return {"report": payload}


def _normalize_content(db: OrmSession, project_id: str, content: ReportContentIn) -> dict:
    payload = content_to_dict(content)
    for section in payload["sections"]:
        if not section["id"]:
            section["id"] = new_id()
        for paragraph in section["paragraphs"]:
            if not paragraph["id"]:
                paragraph["id"] = new_id()
    claim_ids = collect_report_claim_ids(payload)
    if claim_ids:
        known = set(
            db.execute(
                select(Claim.id).where(Claim.id.in_(claim_ids), Claim.project_id == project_id)
            ).scalars()
        )
        missing = [cid for cid in claim_ids if cid not in known]
        if missing:
            raise ApiError(
                422,
                "validation_error",
                "存在しない、または別テーマの主張が参照されています。",
                {"missing_claim_ids": missing},
            )
    return payload


@router.get("/projects/{project_id}/reports")
def list_reports(
    project_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    get_project_or_404(db, project_id)
    reports = list(
        db.execute(
            select(Report).where(Report.project_id == project_id).order_by(Report.updated_at.desc())
        ).scalars()
    )
    submitter_ids = {r.submitted_by for r in reports if r.submitted_by}
    submitters = (
        {
            user.id: user.name
            for user in db.execute(select(User).where(User.id.in_(submitter_ids))).scalars()
        }
        if submitter_ids
        else {}
    )
    items = []
    for report in reports:
        items.append(
            {
                "id": report.id,
                "title": report.title,
                "status": report.status,
                "version": report.version,
                "submitted_by_name": submitters.get(report.submitted_by or ""),
                "submitted_at": iso(report.submitted_at),
                "approved_at": iso(report.approved_at),
                "updated_at": iso(report.updated_at),
                "claim_count": len(collect_report_claim_ids(report.content or {})),
            }
        )
    return {"reports": items}


@router.post("/projects/{project_id}/reports", status_code=201)
def create_report(
    project_id: str,
    payload: ReportIn,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    lock_project(db, project_id)
    report = Report(
        project_id=project_id,
        title=payload.title.strip(),
        content={"sections": []},
        created_by=principal.user_id,
    )
    db.add(report)
    db.flush()
    make_version(db, report, actor_id=principal.user_id, note="initial")
    write_audit(
        db,
        actor_id=principal.user_id,
        action="report.created",
        entity_type="report",
        entity_id=report.id,
        project_id=project_id,
        details={"title": report.title},
    )
    db.commit()
    return _report_full(db, report)


@router.get("/reports/{report_id}")
def get_report(
    report_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    report = get_report_or_404(db, report_id)
    return _report_full(db, report)


@router.put("/reports/{report_id}")
def update_report(
    report_id: str,
    payload: ReportUpdate,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    report = get_report_or_404(db, report_id)
    lock_project(db, report.project_id)
    report = get_report_for_update(db, report_id)
    if payload.content is not None and payload.expected_version is None:
        raise ApiError(
            422,
            "validation_error",
            "内容を更新する場合は expected_version が必要です。",
        )
    if payload.expected_version is not None and payload.expected_version != report.version:
        raise ApiError(
            409,
            "version_conflict",
            "他の利用者が先に更新しました。最新の内容を読み込んでから保存してください。",
            {"current_version": report.version, "expected_version": payload.expected_version},
        )
    if report.status in {"in_review", "approved"}:
        raise ApiError(
            409,
            "report_locked",
            "レビュー中または承認済みのレポートは編集できません。",
            {"status": report.status},
        )
    content_changed = False
    if payload.title is not None:
        report.title = payload.title.strip()
    if payload.content is not None:
        # 主張削除（project ロック）とレポート保存を直列化する
        lock_project(db, report.project_id)
        report.content = _normalize_content(db, report.project_id, payload.content)
        content_changed = True
    if content_changed:
        report.version += 1
        make_version(db, report, actor_id=principal.user_id, note=payload.note)
    write_audit(
        db,
        actor_id=principal.user_id,
        action="report.updated",
        entity_type="report",
        entity_id=report.id,
        project_id=report.project_id,
        details={"version": report.version, "content_changed": content_changed},
    )
    db.commit()
    return _report_full(db, report)


@router.post("/reports/{report_id}/verify")
def verify_report(
    report_id: str,
    principal: Principal = Depends(require_verifier),
    db: OrmSession = Depends(get_db),
) -> dict:
    report = get_report_or_404(db, report_id)
    lock_project(db, report.project_id)
    report = get_report_for_update(db, report_id)
    summary = verify_report_row(db, report, actor_id=principal.user_id)
    db.commit()
    return {"summary": summary, **_report_full(db, report)}


@router.post("/reports/{report_id}/submit")
def submit_report(
    report_id: str,
    payload: ReportSubmitIn | None = None,
    principal: Principal = Depends(require_editor),
    db: OrmSession = Depends(get_db),
) -> dict:
    report = get_report_or_404(db, report_id)
    lock_project(db, report.project_id)
    report = get_report_for_update(db, report_id)
    if report.status not in {"draft", "changes_requested"}:
        raise ApiError(409, "invalid_state", "下書きまたは差し戻し状態のレポートだけ提出できます。")
    # AI 支援の申告は下げられない（一度でも AI 生成を含むと申告したら厳格側に固定する）。
    if payload is not None and payload.ai_assisted:
        report.ai_assisted = True
    claim_ids = collect_report_claim_ids(report.content or {})
    if claim_ids:
        known = set(
            db.execute(
                select(Claim.id).where(
                    Claim.id.in_(claim_ids), Claim.project_id == report.project_id
                )
            ).scalars()
        )
        missing = [claim_id for claim_id in claim_ids if claim_id not in known]
        if missing:
            raise ApiError(
                409,
                "invalid_report",
                "存在しない主張を参照しているため提出できません。",
                {"missing_claim_ids": missing},
            )
    has_text = any(
        (paragraph.get("text") or "").strip()
        for section in (report.content or {}).get("sections", [])
        for paragraph in section.get("paragraphs", [])
    )
    if not has_text:
        raise ApiError(422, "validation_error", "本文が空のレポートは提出できません。")
    report.status = "in_review"
    report.submitted_by = principal.user_id
    report.submitted_at = utcnow()
    write_audit(
        db,
        actor_id=principal.user_id,
        action="report.submitted",
        entity_type="report",
        entity_id=report.id,
        project_id=report.project_id,
        details={"version": report.version, "ai_assisted": report.ai_assisted},
    )
    db.commit()
    return _report_full(db, report)


@router.post("/reports/{report_id}/review")
def review_report(
    report_id: str,
    payload: ReviewIn,
    principal: Principal = Depends(require_reviewer),
    db: OrmSession = Depends(get_db),
) -> dict:
    report = get_report_or_404(db, report_id)
    lock_project(db, report.project_id)
    report = get_report_for_update(db, report_id)
    if report.status != "in_review":
        raise ApiError(409, "invalid_state", "レビュー中状態のレポートだけ審査できます。")

    if payload.decision == "approved":
        if report.submitted_by == principal.user_id:
            raise ApiError(403, "forbidden", "自分が提出したレポートは承認できません。")
        summary = verify_report_row(db, report, actor_id=principal.user_id)
        ai_insufficient = report.ai_assisted and summary["insufficient"] > 0
        if summary["contradicted"] > 0 or summary["missing_claim_ids"] or ai_insufficient:
            # 承認は拒否するが、検証結果（claim の判定・監査）は事実として残す。
            # ロールバックすると画面の判定が古いままになり、再検証の証跡も消える。
            db.commit()
            raise ApiError(
                409,
                "approval_blocked",
                (
                    "AI 支援レポートに根拠不足の主張があるため承認できません。"
                    if ai_insufficient and summary["contradicted"] == 0
                    else "矛盾または欠落した参照主張があるレポートは承認できません。"
                ),
                {
                    "contradicted": summary["contradicted"],
                    "insufficient": summary["insufficient"],
                    "ai_assisted": report.ai_assisted,
                    "missing_claim_ids": summary["missing_claim_ids"],
                    "issues": [
                        i
                        for i in summary["issues"]
                        if i["verdict"] == "contradicted"
                        or (report.ai_assisted and i["verdict"] == "insufficient")
                    ],
                },
            )
        report.status = "approved"
        report.approved_at = utcnow()
        comment = payload.comment.strip()
    else:
        comment = payload.comment.strip()
        if len(comment) < 10:
            raise ApiError(
                422, "validation_error", "差し戻しには 10 文字以上のコメントが必要です。"
            )
        report.status = "changes_requested"

    db.add(
        Review(
            report_id=report.id,
            version=report.version,
            reviewer_id=principal.user_id,
            decision=payload.decision,
            comment=comment,
        )
    )
    write_audit(
        db,
        actor_id=principal.user_id,
        action="report.reviewed",
        entity_type="report",
        entity_id=report.id,
        project_id=report.project_id,
        details={"decision": payload.decision, "version": report.version},
    )
    db.commit()
    return _report_full(db, report)


@router.get("/reports/{report_id}/versions")
def list_versions(
    report_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> dict:
    report = get_report_or_404(db, report_id)
    versions = list(
        db.execute(
            select(ReportVersion)
            .where(ReportVersion.report_id == report.id)
            .order_by(ReportVersion.version.desc())
        ).scalars()
    )
    return {
        "versions": [
            {
                "version": v.version,
                "seal_sha256": v.seal_sha256,
                "note": v.note,
                "created_at": iso(v.created_at),
                "created_by": v.created_by,
            }
            for v in versions
        ],
        "current": report.version,
        "current_seal": seal_content(report.content or {"sections": []}),
    }


@router.get("/reports/{report_id}/export")
def export_report(
    report_id: str,
    principal: Principal = Depends(get_principal),
    db: OrmSession = Depends(get_db),
) -> Response:
    report = get_report_or_404(db, report_id)
    markdown = render_markdown(db, report)
    filename = f"report-{report.id[:8]}-v{report.version}.md"
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
