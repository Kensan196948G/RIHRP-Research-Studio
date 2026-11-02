import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import type { Claim, Report, ReportContent, VerificationSummary } from "../types";
import { canEdit, canReview, formatDate, VERDICT_LABEL } from "../utils";
import { ErrorBanner, Loading, ReportStatusBadge, useToast, VerdictBadge } from "../components/ui";

function newSection(): ReportContent["sections"][number] {
  return { id: crypto.randomUUID(), heading: "", paragraphs: [{ id: crypto.randomUUID(), text: "", claimIds: [] }] };
}

export function ReportEditorPage() {
  const { reportId = "" } = useParams();
  const { user } = useAuth();
  const toast = useToast();

  const [report, setReport] = useState<Report | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [draft, setDraft] = useState<ReportContent>({ sections: [] });
  const [dirty, setDirty] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [summary, setSummary] = useState<VerificationSummary | null>(null);
  const [comment, setComment] = useState("");
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [selectedClaimId, setSelectedClaimId] = useState<string | null>(null);
  const [selectedClaimDetail, setSelectedClaimDetail] = useState<Claim | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.report(reportId);
      setReport(result.report);
      setTitle(result.report.title);
      setDraft(result.report.content);
      setSummary(result.report.latest_verification?.summary ?? null);
      setDirty(false);
      const claimResult = await api.claims(result.report.project_id);
      setClaims(claimResult.claims);
    } catch (err) {
      setError(err instanceof Error ? err.message : "レポートの取得に失敗しました。");
    } finally {
      setLoading(false);
    }
  }, [reportId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedClaimId) {
      setSelectedClaimDetail(null);
      return;
    }
    let cancelled = false;
    api
      .claim(selectedClaimId)
      .then((result) => {
        if (!cancelled) setSelectedClaimDetail(result.claim);
      })
      .catch(() => {
        if (!cancelled) setSelectedClaimDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedClaimId, claims]);

  const locked = Boolean(report && (report.status === "in_review" || report.status === "approved"));
  const editable = canEdit(user?.role) && !locked;
  const canVerify = user?.role === "editor" || user?.role === "reviewer" || user?.role === "admin";

  const claimMap = useMemo(() => new Map(claims.map((claim) => [claim.id, claim])), [claims]);

  const refreshClaims = useCallback(async (projectId: string) => {
    const claimResult = await api.claims(projectId);
    setClaims(claimResult.claims);
  }, []);

  const updateSection = (index: number, patch: Partial<ReportContent["sections"][number]>) => {
    setDraft((current) => {
      const sections = current.sections.map((section, si) => (si === index ? { ...section, ...patch } : section));
      return { sections };
    });
    setDirty(true);
  };

  const updateParagraph = (si: number, pi: number, patch: Partial<ReportContent["sections"][number]["paragraphs"][number]>) => {
    setDraft((current) => {
      const sections = current.sections.map((section, index) => {
        if (index !== si) return section;
        return {
          ...section,
          paragraphs: section.paragraphs.map((paragraph, pindex) => (pindex === pi ? { ...paragraph, ...patch } : paragraph)),
        };
      });
      return { sections };
    });
    setDirty(true);
  };

  const addSection = () => {
    setDraft((current) => ({ sections: [...current.sections, newSection()] }));
    setDirty(true);
  };

  const removeSection = (index: number) => {
    if (!window.confirm("このセクションを削除しますか？")) return;
    setDraft((current) => ({ sections: current.sections.filter((_, si) => si !== index) }));
    setDirty(true);
  };

  const addParagraph = (si: number) => {
    setDraft((current) => ({
      sections: current.sections.map((section, index) =>
        index === si
          ? { ...section, paragraphs: [...section.paragraphs, { id: crypto.randomUUID(), text: "", claimIds: [] }] }
          : section,
      ),
    }));
    setDirty(true);
  };

  const removeParagraph = (si: number, pi: number) => {
    setDraft((current) => ({
      sections: current.sections.map((section, index) =>
        index === si ? { ...section, paragraphs: section.paragraphs.filter((_, pindex) => pindex !== pi) } : section,
      ),
    }));
    setDirty(true);
  };

  const toggleClaim = (si: number, pi: number, claimId: string) => {
    setDraft((current) => ({
      sections: current.sections.map((section, index) => {
        if (index !== si) return section;
        return {
          ...section,
          paragraphs: section.paragraphs.map((paragraph, pindex) => {
            if (pindex !== pi) return paragraph;
            const exists = paragraph.claimIds.includes(claimId);
            return { ...paragraph, claimIds: exists ? paragraph.claimIds.filter((id) => id !== claimId) : [...paragraph.claimIds, claimId] };
          }),
        };
      }),
    }));
    setDirty(true);
  };

  const addClaimToSelected = (claimId: string) => {
    if (!selected) {
      toast("先に段落を選択してください（本文をクリック）。", "error");
      return;
    }
    const [si, pi] = selected.split("-").map(Number);
    const paragraph = draft.sections[si]?.paragraphs[pi];
    if (!paragraph) return;
    if (paragraph.claimIds.includes(claimId)) {
      toast("この段落には既に参照されています。");
      return;
    }
    toggleClaim(si, pi, claimId);
    toast("主張を段落に追加しました。");
  };

  const onSave = async () => {
    if (!report) return;
    setBusy("save");
    try {
      const result = await api.saveReport(report.id, { title, content: draft, note: "UI 保存" });
      setReport(result.report);
      setDraft(result.report.content);
      setDirty(false);
      setSavedAt(new Date().toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" }));
      toast("保存しました。");
      await refreshClaims(result.report.project_id);
    } catch (err) {
      toast(err instanceof Error ? err.message : "保存に失敗しました。", "error");
    } finally {
      setBusy(null);
    }
  };

  const onVerify = async () => {
    if (!report) return;
    if (dirty) {
      toast("先に保存してください（未保存の変更は検証されません）。", "error");
      return;
    }
    setBusy("verify");
    try {
      const result = await api.verifyReport(report.id);
      setReport(result.report);
      setSummary(result.summary);
      await refreshClaims(result.report.project_id);
      toast(
        `検証完了: 検証済 ${result.summary.verified} / 未検証 ${result.summary.unverified} / 矛盾 ${result.summary.contradicted} / 根拠不足 ${result.summary.insufficient}`,
        result.summary.contradicted ? "error" : "info",
      );
    } catch (err) {
      toast(err instanceof Error ? err.message : "検証に失敗しました。", "error");
    } finally {
      setBusy(null);
    }
  };

  const onSubmit = async () => {
    if (!report) return;
    if (dirty) {
      toast("先に保存してください。", "error");
      return;
    }
    if (!window.confirm("この内容でレビューに提出しますか？提出後は承認まで編集できません。")) return;
    setBusy("submit");
    try {
      const result = await api.submitReport(report.id);
      setReport(result.report);
      toast("レビューに提出しました。");
    } catch (err) {
      toast(err instanceof Error ? err.message : "提出に失敗しました。", "error");
    } finally {
      setBusy(null);
    }
  };

  const onReview = async (decision: "approved" | "changes_requested") => {
    if (!report) return;
    setBusy(decision);
    setReviewError(null);
    try {
      const result = await api.reviewReport(report.id, decision, comment);
      setReport(result.report);
      setComment("");
      toast(decision === "approved" ? "承認しました。" : "差し戻しました。");
    } catch (err) {
      if (err instanceof ApiError && err.code === "approval_blocked") {
        const details = err.details as { contradicted?: number; issues?: { text?: string }[] } | undefined;
        const issues = (details?.issues ?? []).map((issue) => issue.text).filter(Boolean).join(" / ");
        setReviewError(`矛盾が ${details?.contradicted ?? 0} 件あるため承認できません。${issues ? ` 対象: ${issues}` : ""}`);
      } else {
        setReviewError(err instanceof Error ? err.message : "レビューに失敗しました。");
      }
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return (
      <div className="content">
        <Loading label="レポートを読み込んでいます…" />
      </div>
    );
  }
  if (error || !report) {
    return (
      <div className="content">
        <ErrorBanner message={error ?? "レポートが見つかりません。"} onRetry={() => void load()} />
      </div>
    );
  }

  const latestReview = report.reviews?.[0];
  const summaryView = summary ?? report.latest_verification?.summary ?? null;

  return (
    <div className="content">
      <div className="row" style={{ marginBottom: 8 }}>
        <Link to={`/projects/${report.project_id}?tab=reports`} className="small">← テーマに戻る</Link>
      </div>

      <div className="editor-toolbar">
        {editable ? (
          <input
            className="input"
            style={{ maxWidth: 460, fontWeight: 650 }}
            value={title}
            aria-label="レポートタイトル"
            onChange={(event) => {
              setTitle(event.target.value);
              setDirty(true);
            }}
            maxLength={200}
          />
        ) : (
          <h1 className="page-title" style={{ fontSize: 19 }}>{report.title}</h1>
        )}
        <ReportStatusBadge status={report.status} />
        <span className="muted small">v{report.version}</span>
        {dirty ? (
          <span className="badge badge-unverified">未保存</span>
        ) : savedAt ? (
          <span className="muted small">保存済み {savedAt}</span>
        ) : null}
        {summaryView ? (
          <>
            <span className="badge badge-verified">検証済 {summaryView.verified}</span>
            {summaryView.unverified ? <span className="badge badge-unverified">未検証 {summaryView.unverified}</span> : null}
            {summaryView.contradicted ? <span className="badge badge-contradicted">矛盾 {summaryView.contradicted}</span> : null}
          </>
        ) : null}
        <div className="spacer" />
        <a className="btn btn-sm" href={api.exportReportUrl(report.id)} download>Markdown</a>
        {canVerify ? (
          <button type="button" className="btn btn-sm" onClick={() => void onVerify()} disabled={busy !== null}>
            {busy === "verify" ? "検証中…" : "検証"}
          </button>
        ) : null}
        {editable ? (
          <>
            <button type="button" className="btn btn-sm" onClick={() => void onSave()} disabled={busy !== null || !dirty}>
              {busy === "save" ? "保存中…" : "保存"}
            </button>
            <button type="button" className="btn btn-primary btn-sm" onClick={() => void onSubmit()} disabled={busy !== null || dirty}>
              提出
            </button>
          </>
        ) : null}
      </div>

      {locked ? (
        <div className="notice">
          {report.status === "approved"
            ? "このレポートは承認済みです。内容を変える場合は新しいレポートを作成してください。"
            : "レビュー中のため編集できません。承認または差し戻しを待ってください。"}
        </div>
      ) : null}
      {report.status === "approved" && report.integrity?.needs_reapproval ? (
        <div className="error-banner" role="alert">
          承認後に根拠の状態が変わり、矛盾が {report.integrity.contradicted} 件あります。この承認は現在の内容を保証しません。再検証と再承認が必要です。
        </div>
      ) : null}
      {report.status === "approved" && report.integrity && !report.integrity.needs_reapproval && report.integrity.unverified + report.integrity.insufficient > 0 ? (
        <div className="notice notice-warn">
          承認時点の検証は通過していますが、現在は未検証 {report.integrity.unverified} 件・根拠不足 {report.integrity.insufficient} 件です。内容の変更があれば再承認してください。
        </div>
      ) : null}
      {report.status === "changes_requested" && latestReview?.decision === "changes_requested" ? (
        <div className="notice notice-warn">
          差し戻しコメント（{latestReview.reviewer_name ?? "レビュアー"} / v{latestReview.version}）: {latestReview.comment}
        </div>
      ) : null}

      <div className="report-layout">
        <div>
          {draft.sections.length === 0 ? (
            <div className="empty">
              <div className="empty-title">セクションがありません</div>
              <div className="small">セクションを追加し、段落に主張を参照させてください。</div>
              {editable ? <button type="button" className="btn btn-primary" onClick={addSection}>セクションを追加</button> : null}
            </div>
          ) : null}

          {draft.sections.map((section, si) => (
            <div className="section-block" key={section.id}>
              <div className="section-head">
                <input
                  value={section.heading}
                  placeholder={`セクション ${si + 1} の見出し`}
                  aria-label={`セクション ${si + 1} の見出し`}
                  disabled={!editable}
                  onChange={(event) => updateSection(si, { heading: event.target.value })}
                  maxLength={300}
                />
                {editable ? (
                  <button type="button" className="btn btn-ghost btn-sm" onClick={() => removeSection(si)}>削除</button>
                ) : null}
              </div>
              <div className="section-body">
                {section.paragraphs.map((paragraph, pi) => {
                  const key = `${si}-${pi}`;
                  return (
                    <div className={`paragraph-block ${selected === key ? "is-selected" : ""}`} key={paragraph.id}>
                      <div className="paragraph-head">
                        <span className="muted small">段落 {pi + 1}</span>
                        <div className="spacer" />
                        {editable ? (
                          <button type="button" className="btn btn-ghost btn-sm" onClick={() => removeParagraph(si, pi)}>段落を削除</button>
                        ) : null}
                      </div>
                      <textarea
                        className="paragraph-text"
                        value={paragraph.text}
                        placeholder="本文を入力…"
                        aria-label={`段落 ${pi + 1} の本文`}
                        disabled={!editable}
                        onFocus={() => setSelected(key)}
                        onChange={(event) => updateParagraph(si, pi, { text: event.target.value })}
                      />
                      <div className="chips">
                        {paragraph.claimIds.length === 0 ? <span className="muted small">参照中の主張はありません</span> : null}
                        {paragraph.claimIds.map((claimId) => {
                          const claim = claimMap.get(claimId);
                          return (
                            <span className="chip" key={claimId} title={claim?.text ?? claimId}>
                              <button
                                type="button"
                                className="chip-select"
                                onClick={() => setSelectedClaimId(claimId)}
                                aria-label={`根拠パネルで開く: ${claim?.text ?? claimId}`}
                              >
                                <VerdictBadge verdict={claim?.last_verdict ?? null} />
                                <span className="chip-text">{claim ? claim.text : claimId}</span>
                              </button>
                              {editable ? (
                                <button type="button" aria-label="参照を外す" onClick={() => toggleClaim(si, pi, claimId)}>×</button>
                              ) : null}
                            </span>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
                {editable ? (
                  <button type="button" className="btn btn-sm" onClick={() => addParagraph(si)}>+ 段落</button>
                ) : null}
              </div>
            </div>
          ))}

          {editable ? (
            <button type="button" className="btn" onClick={addSection}>+ セクションを追加</button>
          ) : null}
        </div>

        <aside className="claim-panel">
          <div className="card">
            <div className="card-head">
              <h2 className="card-title">検証サマリ</h2>
              {summaryView ? <span className="muted small">{formatDate(summaryView.checked_at)}</span> : null}
            </div>
            {summaryView ? (
              <>
                <div className="summary-grid">
                  <div className="summary-cell"><b>{summaryView.verified}</b><span>検証済</span></div>
                  <div className="summary-cell"><b style={{ color: "var(--warn)" }}>{summaryView.unverified}</b><span>未検証</span></div>
                  <div className="summary-cell"><b style={{ color: "var(--danger)" }}>{summaryView.contradicted}</b><span>矛盾</span></div>
                  <div className="summary-cell"><b>{summaryView.insufficient}</b><span>根拠不足</span></div>
                </div>
                <p className="hint" style={{ marginTop: 8 }}>
                  参照している主張 {summaryView.total_claims} 件を検証しました。矛盾が 1 件でもあると承認できません。
                </p>
                {summaryView.issues.length ? (
                  <ul className="list-reset small" style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                    {summaryView.issues.map((issue) => (
                      <li key={issue.claim_id}>
                        <span className={`badge badge-${issue.verdict}`}>{VERDICT_LABEL[issue.verdict]}</span>{" "}
                        {issue.text}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : (
              <p className="muted small">まだ検証していません。「検証」を実行してください。</p>
            )}
          </div>

          {selectedClaimDetail ? (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="card-head">
                <h2 className="card-title">選択中のクレーム</h2>
                <div className="spacer" />
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setSelectedClaimId(null)} aria-label="クレーム詳細を閉じる">×</button>
              </div>
              <p className="small" style={{ fontWeight: 600 }}>{selectedClaimDetail.text}</p>
              <div className="row" style={{ margin: "6px 0 8px" }}>
                <VerdictBadge verdict={selectedClaimDetail.last_verdict} />
                <span className="muted small">根拠 {selectedClaimDetail.evidence?.length ?? 0}</span>
              </div>
              {(selectedClaimDetail.evidence?.length ?? 0) === 0 ? (
                <p className="muted small">根拠が未登録です。</p>
              ) : (
                <ul className="list-reset stack" style={{ gap: 8 }}>
                  {selectedClaimDetail.evidence?.map((evidence) => (
                    <li key={evidence.id} className="small">
                      <div className="row">
                        <b>{evidence.source_title ?? "（出典）"}</b>
                        {evidence.quote_found === false ? <span className="badge badge-contradicted">引用なし</span> : null}
                      </div>
                      {evidence.quote ? (
                        <blockquote className="prewrap" style={{ margin: "6px 0 0", paddingLeft: 8, borderLeft: "2px solid var(--accent-line)", color: "var(--muted)" }}>
                          {evidence.quote}
                        </blockquote>
                      ) : null}
                      {evidence.note ? <div className="muted" style={{ marginTop: 4 }}>{evidence.note}</div> : null}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}

          <div className="card" style={{ marginTop: 12 }}>
            <div className="card-head">
              <h2 className="card-title">主張を段落に追加</h2>
            </div>
            <p className="hint" style={{ marginBottom: 8 }}>
              {selected ? `選択中の段落: ${selected.replace("-", " / ")}` : "本文をクリックして段落を選択してください。"}
            </p>
            {claims.length === 0 ? (
              <p className="muted small">このテーマには主張がありません。</p>
            ) : (
              <div className="claim-list">
                {claims.map((claim) => (
                  <button
                    key={claim.id}
                    type="button"
                    className="claim-item"
                    disabled={!editable}
                    onClick={() => addClaimToSelected(claim.id)}
                  >
                    <span className="claim-text">{claim.text}</span>
                    <span className="row">
                      <VerdictBadge verdict={claim.last_verdict} />
                      <span className="muted small">根拠 {claim.evidence_count}</span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h2 className="card-title" style={{ marginBottom: 6 }}>版とシール</h2>
            <div className="small muted">現在 v{report.version}</div>
            <div className="small muted">提出: {report.submitted_by_name ?? "—"} / {formatDate(report.submitted_at)}</div>
            <div className="small muted">承認: {formatDate(report.approved_at)}</div>
            <a className="small" href={`/api/reports/${report.id}/versions`} target="_blank" rel="noreferrer">版一覧（JSON）</a>
          </div>

          {report.reviews?.length ? (
            <div className="card" style={{ marginTop: 12 }}>
              <h2 className="card-title" style={{ marginBottom: 6 }}>レビュー履歴</h2>
              <ul className="list-reset stack" style={{ gap: 8 }}>
                {report.reviews.map((review) => (
                  <li key={review.id} className="small">
                    <span className={`badge badge-${review.decision === "approved" ? "approved" : "changes_requested"}`}>
                      {review.decision === "approved" ? "承認" : "差し戻し"}
                    </span>{" "}
                    {review.reviewer_name ?? "レビュアー"} / v{review.version}
                    <div className="muted">{review.comment || "（コメントなし）"}</div>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </aside>
      </div>

      {canReview(user?.role) && report.status === "in_review" ? (
        <div className="review-box">
          <h2 className="card-title" style={{ marginBottom: 8 }}>レビュー</h2>
          {reviewError ? <div className="error-banner" role="alert">{reviewError}</div> : null}
          <div className="field">
            <label htmlFor="review-comment">コメント（差し戻しは 10 文字以上）</label>
            <textarea id="review-comment" className="textarea" value={comment} onChange={(event) => setComment(event.target.value)} />
          </div>
          <div className="row">
            <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => void onReview("approved")}>
              {busy === "approved" ? "承認中…" : "承認"}
            </button>
            <button type="button" className="btn btn-danger" disabled={busy !== null || comment.trim().length < 10} onClick={() => void onReview("changes_requested")}>
              {busy === "changes_requested" ? "差し戻し中…" : "差し戻す"}
            </button>
            <span className="hint">提出者本人は承認できません。承認時に検証を再実行します。</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
