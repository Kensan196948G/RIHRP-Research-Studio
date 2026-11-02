import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { Claim, Project, Verdict } from "../types";
import { formatShortDate, VERDICT_HINT } from "../utils";
import { EmptyState, ErrorBanner, Loading, VerdictBadge } from "../components/ui";

const ORDER: Record<string, number> = { contradicted: 0, unverified: 1, insufficient: 2, verified: 3 };

const REASON_LABEL: Record<string, string> = {
  no_evidence: "根拠が未登録",
  quote_not_found: "引用が見つからない",
  evidence_tampered: "スナップショットが改竄されている",
  number_not_found: "数値が根拠に見つからない",
  no_anchor: "引用も数値も無い",
  quote_verified: "引用が実在",
  number_verified: "数値が実在",
};

export function VerificationPage() {
  const { projectId = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [projectResult, claimResult] = await Promise.all([api.project(projectId), api.claims(projectId)]);
      setProject(projectResult.project);
      setClaims(claimResult.claims);
    } catch (err) {
      setError(err instanceof Error ? err.message : "検証結果の取得に失敗しました。");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = useMemo(() => {
    const base: Record<string, number> = { verified: 0, unverified: 0, contradicted: 0, insufficient: 0, unchecked: 0 };
    for (const claim of claims) base[claim.last_verdict ?? "unchecked"] += 1;
    return base;
  }, [claims]);

  const sorted = useMemo(
    () => [...claims].sort((a, b) => (ORDER[a.last_verdict ?? "unchecked"] ?? 4) - (ORDER[b.last_verdict ?? "unchecked"] ?? 4)),
    [claims],
  );

  if (loading) {
    return (
      <div className="content">
        <Loading label="検証結果を読み込んでいます…" />
      </div>
    );
  }
  if (error || !project) {
    return (
      <div className="content">
        <ErrorBanner message={error ?? "テーマが見つかりません。"} onRetry={() => void load()} />
      </div>
    );
  }

  return (
    <div className="content">
      <div className="row" style={{ marginBottom: 8 }}>
        <Link to={`/projects/${project.id}?tab=claims`} className="small">← テーマの主張一覧に戻る</Link>
      </div>
      <div className="page-head">
        <div>
          <h1 className="page-title">検証結果</h1>
          <div className="page-desc">{project.title} — 主張ごとの判定理由と根拠の一致状況</div>
        </div>
        <div className="spacer" />
        <Link className="btn" to={`/projects/${project.id}?tab=claims`}>テーマで対応する</Link>
      </div>

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-label">検証済</div>
          <div className="stat-value" style={{ color: "var(--ok)" }}>{counts.verified}</div>
          <div className="stat-foot">引用または数値が実在</div>
        </div>
        <div className={`stat ${counts.unverified ? "is-warn" : ""}`}>
          <div className="stat-label">未検証</div>
          <div className="stat-value">{counts.unverified}</div>
          <div className="stat-foot">数値が根拠に見つからない</div>
        </div>
        <div className={`stat ${counts.contradicted ? "is-alert" : ""}`}>
          <div className="stat-label">矛盾</div>
          <div className="stat-value">{counts.contradicted}</div>
          <div className="stat-foot">承認が止まる項目</div>
        </div>
        <div className="stat">
          <div className="stat-label">根拠不足</div>
          <div className="stat-value">{counts.insufficient}</div>
          <div className="stat-foot">引用・数値のアンカーなし</div>
        </div>
      </div>

      {counts.contradicted > 0 ? (
        <div className="error-banner" role="alert">
          矛盾が {counts.contradicted} 件あります。このままではレポートを承認できません。根拠の引用または出典を修正し、再検証してください。
        </div>
      ) : null}

      {claims.length === 0 ? (
        <EmptyState title="主張がありません" description="テーマで主張と根拠を登録すると、ここに検証結果が表示されます。" />
      ) : (
        <div className="verification-list">
          {sorted.map((claim) => {
            const reasons = claim.last_details?.reasons ?? [];
            const numbers = claim.last_details?.numbers ?? [];
            return (
              <article className="verification-item" key={claim.id}>
                <div className="row" style={{ alignItems: "flex-start" }}>
                  <VerdictBadge verdict={claim.last_verdict} />
                  <span className="muted small">根拠 {claim.evidence_count}</span>
                  <span className="muted small">最終検証 {formatShortDate(claim.last_verified_at)}</span>
                  <div className="spacer" />
                  <Link className="btn btn-sm" to={`/projects/${project.id}?tab=claims`}>テーマで開く</Link>
                </div>
                <p className="verification-text">{claim.text}</p>
                {claim.last_verdict ? <p className="hint">{VERDICT_HINT[claim.last_verdict as Verdict]}</p> : <p className="hint">まだ検証していません。</p>}
                {reasons.length ? (
                  <div className="small muted">
                    理由: {reasons.map((reason) => REASON_LABEL[reason] ?? reason).join(" / ")}
                  </div>
                ) : null}
                {numbers.length ? (
                  <div className="row" style={{ gap: 6, marginTop: 6 }}>
                    {numbers.map((number) => (
                      <span key={number.value} className={`badge ${number.found ? "badge-verified" : "badge-contradicted"}`}>
                        {number.value} {number.found ? "実在" : "不一致"}
                      </span>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
