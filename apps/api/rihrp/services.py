"""業務ロジックとレスポンス整形。ルータから共通利用する。"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audit import write_audit
from .errors import ApiError
from .models import (
    AuditEvent,
    Claim,
    ClaimEvidence,
    Project,
    Report,
    ReportVerification,
    ReportVersion,
    Review,
    Source,
    User,
)
from .verify import EvidenceInput, normalize, sha256_text, verify_claim

VERDICT_LABELS = {
    "verified": "検証済",
    "unverified": "未検証",
    "contradicted": "矛盾",
    "insufficient": "根拠不足",
}


# ---------------------------------------------------------------- utilities
def utcnow() -> datetime:
    return datetime.now(UTC)


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def seal_content(content: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


# ---------------------------------------------------------------- lookups
def get_project_or_404(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise ApiError(404, "not_found", "テーマが見つかりません。")
    return project


def get_claim_or_404(db: Session, claim_id: str) -> Claim:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise ApiError(404, "not_found", "主張が見つかりません。")
    return claim


def get_source_or_404(db: Session, source_id: str) -> Source:
    source = db.get(Source, source_id)
    if source is None:
        raise ApiError(404, "not_found", "出典が見つかりません。")
    return source


def get_report_or_404(db: Session, report_id: str) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise ApiError(404, "not_found", "レポートが見つかりません。")
    return report


# ---------------------------------------------------------------- serializers
def user_to_dict(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": iso(user.created_at),
    }


def source_to_dict(source: Source, *, tampered: bool | None = None) -> dict[str, Any]:
    if tampered is None:
        tampered = sha256_text(source.content) != source.content_sha256
    return {
        "id": source.id,
        "project_id": source.project_id,
        "title": source.title,
        "kind": source.kind,
        "origin": source.origin,
        "content": source.content,
        "content_sha256": source.content_sha256,
        "tampered": tampered,
        "created_at": iso(source.created_at),
    }


def evidence_to_dict(evidence: ClaimEvidence, source: Source | None) -> dict[str, Any]:
    quote = evidence.quote
    found: bool | None = None
    if quote and source is not None:
        found = normalize(quote) in normalize(source.content)
    return {
        "id": evidence.id,
        "claim_id": evidence.claim_id,
        "source_id": evidence.source_id,
        "source_title": source.title if source else None,
        "source_origin": source.origin if source else None,
        "quote": quote,
        "note": evidence.note,
        "quote_found": found,
        "created_at": iso(evidence.created_at),
    }


def claim_to_dict(
    claim: Claim,
    evidences: list[tuple[ClaimEvidence, Source | None]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": claim.id,
        "project_id": claim.project_id,
        "text": claim.text,
        "last_verdict": claim.last_verdict,
        "last_verified_at": iso(claim.last_verified_at),
        "last_details": claim.last_details,
        "created_at": iso(claim.created_at),
        "updated_at": iso(claim.updated_at),
    }
    if evidences is not None:
        payload["evidence"] = [evidence_to_dict(e, s) for e, s in evidences]
        payload["evidence_count"] = len(evidences)
    return payload


def report_to_dict(
    report: Report,
    *,
    latest_verification: ReportVerification | None = None,
    reviews: list[tuple[Review, User | None]] | None = None,
    submitted_by_name: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": report.id,
        "project_id": report.project_id,
        "title": report.title,
        "content": report.content or {"sections": []},
        "status": report.status,
        "version": report.version,
        "submitted_by": report.submitted_by,
        "submitted_by_name": submitted_by_name,
        "submitted_at": iso(report.submitted_at),
        "approved_at": iso(report.approved_at),
        "created_at": iso(report.created_at),
        "updated_at": iso(report.updated_at),
    }
    if latest_verification is not None:
        payload["latest_verification"] = {
            "summary": latest_verification.summary,
            "version": latest_verification.version,
            "created_at": iso(latest_verification.created_at),
        }
    if reviews is not None:
        payload["reviews"] = [
            {
                "id": review.id,
                "decision": review.decision,
                "comment": review.comment,
                "version": review.version,
                "reviewer_name": user.name if user else None,
                "created_at": iso(review.created_at),
            }
            for review, user in reviews
        ]
    return payload


def audit_to_dict(event: AuditEvent, actor_name: str | None = None) -> dict[str, Any]:
    return {
        "id": event.id,
        "actor_id": event.actor_id,
        "actor_name": actor_name,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "project_id": event.project_id,
        "details": event.details,
        "created_at": iso(event.created_at),
    }


# ---------------------------------------------------------------- report integrity
def report_integrity(db: Session, report: Report) -> dict[str, Any]:
    """承認済みレポートの参照主張が、現在も同じ検証状態かを示す。

    承認時点の summary は履歴であり、その後の根拠変更で状態が変わり得る。
    画面はこの値で「再承認が必要」を警告する。
    """
    claim_ids = collect_report_claim_ids(report.content or {})
    counts = {"verified": 0, "unverified": 0, "contradicted": 0, "insufficient": 0, "unchecked": 0}
    if claim_ids:
        rows = db.execute(
            select(Claim.last_verdict).where(
                Claim.id.in_(claim_ids), Claim.project_id == report.project_id
            )
        ).scalars()
        for verdict in rows:
            counts[verdict or "unchecked"] += 1
    return {
        **counts,
        "referenced": len(claim_ids),
        "needs_reapproval": report.status == "approved"
        and (counts["contradicted"] > 0 or counts["unchecked"] > 0),
    }


# ---------------------------------------------------------------- project stats
def project_stats(db: Session, project_ids: list[str]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {
        pid: {
            "sources": 0,
            "claims": 0,
            "reports": 0,
            "verified": 0,
            "unverified": 0,
            "contradicted": 0,
            "insufficient": 0,
            "unchecked": 0,
            "review_pending": 0,
            "changes_requested": 0,
        }
        for pid in project_ids
    }
    if not project_ids:
        return stats

    for pid, count in db.execute(
        select(Source.project_id, func.count())
        .where(Source.project_id.in_(project_ids))
        .group_by(Source.project_id)
    ):
        stats[pid]["sources"] = int(count)

    for pid, verdict, count in db.execute(
        select(Claim.project_id, Claim.last_verdict, func.count())
        .where(Claim.project_id.in_(project_ids))
        .group_by(Claim.project_id, Claim.last_verdict)
    ):
        stats[pid]["claims"] += int(count)
        key = verdict or "unchecked"
        if key in stats[pid]:
            stats[pid][key] += int(count)

    for pid, status, count in db.execute(
        select(Report.project_id, Report.status, func.count())
        .where(Report.project_id.in_(project_ids))
        .group_by(Report.project_id, Report.status)
    ):
        stats[pid]["reports"] += int(count)
        if status == "in_review":
            stats[pid]["review_pending"] += int(count)
        if status == "changes_requested":
            stats[pid]["changes_requested"] += int(count)
    return stats


# ---------------------------------------------------------------- verification
def _load_evidence(db: Session, claim_id: str) -> list[tuple[ClaimEvidence, Source | None]]:
    rows = db.execute(
        select(ClaimEvidence, Source)
        .outerjoin(Source, Source.id == ClaimEvidence.source_id)
        .where(ClaimEvidence.claim_id == claim_id)
        .order_by(ClaimEvidence.created_at)
    ).all()
    return [(evidence, source) for evidence, source in rows]


def load_evidence_map(
    db: Session, claim_ids: list[str]
) -> dict[str, list[tuple[ClaimEvidence, Source | None]]]:
    """複数主張の根拠を 1 クエリでまとめて取得する（一覧・エクスポート用）。"""
    result: dict[str, list[tuple[ClaimEvidence, Source | None]]] = {cid: [] for cid in claim_ids}
    if not claim_ids:
        return result
    rows = db.execute(
        select(ClaimEvidence, Source)
        .outerjoin(Source, Source.id == ClaimEvidence.source_id)
        .where(ClaimEvidence.claim_id.in_(claim_ids))
        .order_by(ClaimEvidence.created_at)
    ).all()
    for evidence, source in rows:
        result.setdefault(evidence.claim_id, []).append((evidence, source))
    return result


def verify_claim_row(
    db: Session,
    claim: Claim,
    *,
    actor_id: str | None,
    evidence_rows: list[tuple[ClaimEvidence, Source | None]] | None = None,
) -> dict[str, Any]:
    rows = evidence_rows if evidence_rows is not None else _load_evidence(db, claim.id)
    evidence_inputs = [
        EvidenceInput(
            source_id=source.id,
            title=source.title,
            content=source.content,
            content_sha256=source.content_sha256,
            quote=evidence.quote,
        )
        for evidence, source in rows
        if source is not None
    ]
    result = verify_claim(claim.text, evidence_inputs)
    claim.last_verdict = result["verdict"]
    claim.last_verified_at = utcnow()
    claim.last_details = {"reasons": result["reasons"], **result["details"]}
    write_audit(
        db,
        actor_id=actor_id,
        action="claim.verified",
        entity_type="claim",
        entity_id=claim.id,
        project_id=claim.project_id,
        details={"verdict": result["verdict"], "reasons": result["reasons"]},
    )
    return result


def collect_report_claim_ids(content: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for section in content.get("sections", []):
        for paragraph in section.get("paragraphs", []):
            for claim_id in paragraph.get("claimIds", []):
                if claim_id not in ids:
                    ids.append(claim_id)
    return ids


def verify_report_row(db: Session, report: Report, *, actor_id: str | None) -> dict[str, Any]:
    claim_ids = collect_report_claim_ids(report.content or {})
    claims: list[Claim] = []
    if claim_ids:
        claims = list(
            db.execute(
                select(Claim).where(Claim.id.in_(claim_ids), Claim.project_id == report.project_id)
            ).scalars()
        )
    counts = {"verified": 0, "unverified": 0, "contradicted": 0, "insufficient": 0}
    issues: list[dict[str, Any]] = []
    evidence_map = load_evidence_map(db, [claim.id for claim in claims])
    for claim in claims:
        result = verify_claim_row(
            db, claim, actor_id=actor_id, evidence_rows=evidence_map.get(claim.id, [])
        )
        counts[result["verdict"]] += 1
        if result["verdict"] != "verified":
            issues.append(
                {
                    "claim_id": claim.id,
                    "verdict": result["verdict"],
                    "reasons": result["reasons"],
                    "text": claim.text,
                }
            )
    summary = {
        "total_claims": len(claims),
        "referenced_claim_ids": claim_ids,
        "missing_claim_ids": [cid for cid in claim_ids if cid not in {c.id for c in claims}],
        **counts,
        "issues": issues,
        "checked_at": iso(utcnow()),
    }
    db.add(
        ReportVerification(
            report_id=report.id,
            version=report.version,
            summary=summary,
            created_by=actor_id,
        )
    )
    write_audit(
        db,
        actor_id=actor_id,
        action="report.verified",
        entity_type="report",
        entity_id=report.id,
        project_id=report.project_id,
        details={"version": report.version, **{k: counts[k] for k in counts}},
    )
    return summary


# ---------------------------------------------------------------- versions
def make_version(
    db: Session, report: Report, *, actor_id: str | None, note: str = ""
) -> ReportVersion:
    version = ReportVersion(
        report_id=report.id,
        version=report.version,
        content=report.content or {"sections": []},
        seal_sha256=seal_content(report.content or {"sections": []}),
        created_by=actor_id,
        note=note[:300],
    )
    db.add(version)
    return version


# ---------------------------------------------------------------- export
def render_markdown(db: Session, report: Report) -> str:
    project = db.get(Project, report.project_id)
    # エクスポートに含めるのは、レポートが実際に参照している主張だけ。
    referenced_ids = collect_report_claim_ids(report.content or {})
    claims: dict[str, Claim] = {}
    if referenced_ids:
        claims = {
            claim.id: claim
            for claim in db.execute(
                select(Claim).where(
                    Claim.id.in_(referenced_ids), Claim.project_id == report.project_id
                )
            ).scalars()
        }
    evidence_by_claim = load_evidence_map(db, list(claims))
    lines: list[str] = []
    lines.append(f"# {report.title}")
    lines.append("")
    lines.append(f"- テーマ: {project.title if project else report.project_id}")
    lines.append(f"- 状態: {report.status} / 版: {report.version}")
    lines.append(f"- 生成: {iso(utcnow())}")
    lines.append(f"- 内容シール: {seal_content(report.content or {'sections': []})}")
    lines.append("")

    for section in (report.content or {}).get("sections", []):
        heading = section.get("heading") or "（無題セクション）"
        lines.append(f"## {heading}")
        lines.append("")
        for paragraph in section.get("paragraphs", []):
            text = (paragraph.get("text") or "").strip()
            if text:
                lines.append(text)
                lines.append("")
            claim_ids = paragraph.get("claimIds", [])
            if not claim_ids:
                continue
            for claim_id in claim_ids:
                claim = claims.get(claim_id)
                if claim is None:
                    lines.append(f"> [未登録の主張: {claim_id}]")
                    continue
                label = VERDICT_LABELS.get(claim.last_verdict or "", "未検証")
                lines.append(f"> [{label}] {claim.text}")
                for evidence, source in evidence_by_claim.get(claim_id, []):
                    if source is None:
                        continue
                    digest = source.content_sha256[:12]
                    quote = f"「{evidence.quote}」" if evidence.quote else "（引用なし）"
                    lines.append(f">  - {quote} — {source.title}（sha256: {digest}…）")
            lines.append("")

    lines.append("## 根拠付録")
    lines.append("")
    if not referenced_ids:
        lines.append("（参照された主張はありません）")
    for claim_id in referenced_ids:
        claim = claims.get(claim_id)
        if claim is None:
            lines.append(f"- [未登録の主張: {claim_id}]")
            continue
        label = VERDICT_LABELS.get(claim.last_verdict or "", "未検証")
        lines.append(f"- [{label}] {claim.text}")
        for evidence, source in evidence_by_claim.get(claim.id, []):
            if source is None:
                lines.append("  - （出典が削除されています）")
                continue
            lines.append(
                f"  - {source.title} / {source.kind}: {source.origin or '—'}"
                f" / sha256 {source.content_sha256}"
            )
            if evidence.quote:
                lines.append(f"    - 引用: {evidence.quote}")
    lines.append("")
    return "\n".join(lines)
