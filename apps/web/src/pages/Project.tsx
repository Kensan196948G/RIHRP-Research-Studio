import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Claim, Project, Source } from "../types";
import { canEdit, canReview, claimCode, countUnresolved, formatShortDate, shortHash, VERDICT_HINT, VERDICT_LABEL } from "../utils";
import { EmptyState, ErrorBanner, Loading, Modal, ReportStatusBadge, useToast, VerdictBadge } from "../components/ui";

type Tab = "overview" | "sources" | "claims" | "reports";

interface ReportSummary {
  id: string;
  title: string;
  status: string;
  version: number;
  submitted_by_name: string | null;
  updated_at: string | null;
  claim_count: number;
}

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const { user } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = (searchParams.get("tab") as Tab | null) ?? "overview";

  const [project, setProject] = useState<Project | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sourceModal, setSourceModal] = useState(false);
  const [sourceDetail, setSourceDetail] = useState<Source | null>(null);
  const [claimModal, setClaimModal] = useState(false);
  const [claimDetail, setClaimDetail] = useState<Claim | null>(null);
  const [evidenceClaim, setEvidenceClaim] = useState<Claim | null>(null);
  const [reportModal, setReportModal] = useState(false);
  const [projectModal, setProjectModal] = useState(false);
  const [claimFilter, setClaimFilter] = useState("all");
  const [claimQuery, setClaimQuery] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [projectResult, sourceResult, claimResult, reportResult] = await Promise.all([
        api.project(projectId),
        api.sources(projectId),
        api.claims(projectId),
        api.reports(projectId),
      ]);
      setProject(projectResult.project);
      setSources(sourceResult.sources);
      setClaims(claimResult.claims);
      setReports(reportResult.reports);
    } catch (err) {
      setError(err instanceof Error ? err.message : "テーマの取得に失敗しました。");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const switchTab = (next: Tab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  const counts = useMemo(
    () => ({
      sources: sources.length,
      claims: claims.length,
      reports: reports.length,
    }),
    [sources, claims, reports],
  );

  const visibleClaims = claims.filter((claim) => {
    if (claimFilter === "unchecked" && claim.last_verdict !== null) return false;
    if (claimFilter !== "all" && claimFilter !== "unchecked" && claim.last_verdict !== claimFilter) return false;
    const needle = claimQuery.trim().toLowerCase();
    return !needle || claim.text.toLowerCase().includes(needle);
  });

  const nextActions = useMemo(() => {
    if (!project) return [];
    const items: string[] = [];
    if (sources.length === 0) items.push("出典を登録する（本文と SHA-256 が保存されます）");
    if (claims.length === 0) items.push("主張を作成し、出典と引用で根拠を結び付ける");
    if (project.stats.contradicted > 0) items.push(`矛盾 ${project.stats.contradicted} 件を解消する（承認が止まります）`);
    if (project.stats.unverified + project.stats.insufficient + project.stats.unchecked > 0) {
      items.push("未検証・根拠不足の主張を確認する");
    }
    if (reports.length === 0) items.push("レポートを作成し、主張を参照して組み立てる");
    if (project.stats.review_pending > 0) items.push("レビュー待ちのレポートを承認または差し戻す");
    if (items.length === 0) items.push("現在、対応が必要な項目はありません");
    return items;
  }, [project, sources.length, claims.length, reports.length]);

  const createSource = async (payload: Record<string, unknown>) => {
    setBusy(true);
    try {
      const result = await api.createSource(projectId, payload);
      toast(`出典を登録しました（sha256 ${shortHash(result.source.content_sha256)}）。`);
      setSourceModal(false);
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "出典の登録に失敗しました。", "error");
    } finally {
      setBusy(false);
    }
  };

  const createClaim = async (text: string) => {
    setBusy(true);
    try {
      await api.createClaim(projectId, text);
      toast("主張を作成しました。");
      setClaimModal(false);
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "主張の作成に失敗しました。", "error");
    } finally {
      setBusy(false);
    }
  };

  const addEvidence = async (claimId: string, payload: { source_id: string; quote: string; note: string }) => {
    setBusy(true);
    try {
      await api.addEvidence(claimId, payload);
      toast("根拠を紐付けました。");
      setEvidenceClaim(null);
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "根拠の追加に失敗しました。", "error");
    } finally {
      setBusy(false);
    }
  };

  const verifyClaim = async (claimId: string) => {
    try {
      const result = await api.verifyClaim(claimId);
      toast(`検証結果: ${VERDICT_LABEL[result.result.verdict as keyof typeof VERDICT_LABEL] ?? result.result.verdict}`);
      setClaimDetail(null);
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "検証に失敗しました。", "error");
    }
  };

  const verifyAll = async () => {
    setBusy(true);
    try {
      const result = await api.verifyProjectClaims(projectId);
      toast(`${result.verified} 件の主張を検証しました。`);
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "検証に失敗しました。", "error");
    } finally {
      setBusy(false);
    }
  };

  const removeSource = async (source: Source) => {
    if (!window.confirm(`「${source.title}」を削除しますか？ 根拠として使われている場合は削除できません。`)) return;
    try {
      await api.deleteSource(source.id);
      toast("出典を削除しました。");
      setSourceDetail(null);
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "削除に失敗しました。", "error");
    }
  };

  const removeClaim = async (claim: Claim) => {
    if (!window.confirm("この主張を削除しますか？ レポートから参照されている場合は削除できません。")) return;
    try {
      await api.deleteClaim(claim.id);
      toast("主張を削除しました。");
      setClaimDetail(null);
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "削除に失敗しました。", "error");
    }
  };

  const createReport = async (title: string) => {
    setBusy(true);
    try {
      const result = await api.createReport(projectId, title);
      toast("レポートを作成しました。");
      navigate(`/reports/${result.report.id}`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "レポートの作成に失敗しました。", "error");
      setBusy(false);
    }
  };

  const updateProject = async (payload: { title: string; summary: string; status: "active" | "archived" }) => {
    setBusy(true);
    try {
      await api.updateProject(projectId, payload);
      toast("テーマを更新しました。");
      setProjectModal(false);
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "更新に失敗しました。", "error");
    } finally {
      setBusy(false);
    }
  };

  const updateClaimText = async (claim: Claim, text: string) => {
    try {
      const result = await api.updateClaim(claim.id, text);
      setClaimDetail(result.claim);
      toast("主張を更新しました。再検証が必要です。");
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "更新に失敗しました。", "error");
    }
  };

  const openSourceDetail = async (source: Source) => {
    try {
      const result = await api.source(source.id);
      setSourceDetail(result.source);
    } catch (err) {
      toast(err instanceof Error ? err.message : "出典の取得に失敗しました。", "error");
    }
  };

  if (loading) {
    return (
      <div className="content">
        <Loading label="テーマを読み込んでいます…" />
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

  const editable = canEdit(user?.role);

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <div className="row" style={{ marginBottom: 4 }}>
            <span className="badge badge-kind">{project.status === "active" ? "進行中" : "アーカイブ"}</span>
            <span className="muted small mono">#{shortHash(project.id)}</span>
          </div>
          <h1 className="page-title">{project.title}</h1>
          <div className="page-desc">{project.summary || "概要は未設定です。"}</div>
        </div>
        <div className="spacer" />
        {editable ? (
          <>
            <button type="button" className="btn" onClick={() => setProjectModal(true)}>編集</button>
            <button type="button" className="btn" onClick={() => setClaimModal(true)}>+ 主張</button>
            <button type="button" className="btn btn-primary" onClick={() => setSourceModal(true)}>+ 出典</button>
          </>
        ) : null}
      </div>

      <div className="tabs" role="tablist" aria-label="テーマの表示切替">
        {([
          ["overview", "概要", null],
          ["sources", "出典", counts.sources],
          ["claims", "主張", counts.claims],
          ["reports", "レポート", counts.reports],
        ] as [Tab, string, number | null][]).map(([key, label, count]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            className={`tab ${tab === key ? "is-active" : ""}`}
            onClick={() => switchTab(key)}
            type="button"
          >
            {label}
            {count !== null ? <span className="count">{count}</span> : null}
          </button>
        ))}
      </div>

      {tab === "overview" ? (
        <>
          <div className="stat-grid">
            <div className="stat">
              <div className="stat-label">出典</div>
              <div className="stat-value">{project.stats.sources}</div>
              <div className="stat-foot">スナップショット固定済み</div>
            </div>
            <div className="stat">
              <div className="stat-label">主張</div>
              <div className="stat-value">{project.stats.claims}</div>
              <div className="stat-foot">要対応 {countUnresolved(project.stats)} 件</div>
            </div>
            <div className={`stat ${project.stats.contradicted ? "is-alert" : ""}`}>
              <div className="stat-label">矛盾</div>
              <div className="stat-value">{project.stats.contradicted}</div>
              <div className="stat-foot">承認は矛盾ゼロが条件</div>
            </div>
            <div className={`stat ${project.stats.unverified ? "is-warn" : ""}`}>
              <div className="stat-label">未検証</div>
              <div className="stat-value">{project.stats.unverified}</div>
              <div className="stat-foot">数値が根拠に見つからない</div>
            </div>
          </div>

          <div className="split-2">
            <div className="card">
              <div className="card-head"><h2 className="card-title">次にやること</h2></div>
              <ul className="list-reset stack" style={{ gap: 8 }}>
                {nextActions.map((item) => (
                  <li key={item} className="row" style={{ alignItems: "flex-start" }}>
                    <span aria-hidden="true" style={{ color: "var(--accent)", fontWeight: 700 }}>→</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="card">
              <div className="card-head"><h2 className="card-title">テーマ情報</h2></div>
              <dl className="kv">
                <dt>状態</dt><dd>{project.status === "active" ? "進行中" : "アーカイブ"}</dd>
                <dt>作成</dt><dd>{formatShortDate(project.created_at)}</dd>
                <dt>更新</dt><dd>{formatShortDate(project.updated_at)}</dd>
                <dt>検証済み</dt><dd>{project.stats.verified} 件</dd>
                <dt>根拠不足</dt><dd>{project.stats.insufficient} 件</dd>
                <dt>未検証（未実行）</dt><dd>{project.stats.unchecked} 件</dd>
                <dt>レビュー待ち</dt><dd>{project.stats.review_pending} 件</dd>
              </dl>
              {editable ? (
                <div className="row" style={{ marginTop: 12 }}>
                  <button type="button" className="btn btn-sm" onClick={() => void verifyAll()} disabled={busy || claims.length === 0}>
                    すべての主張を検証
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </>
      ) : null}

      {tab === "sources" ? (
        sources.length === 0 ? (
          <EmptyState
            title="出典がまだありません"
            description="URL・DOI・テキストを登録すると、本文スナップショットと SHA-256 が保存されます。"
            action={editable ? <button type="button" className="btn btn-primary" onClick={() => setSourceModal(true)}>出典を登録</button> : undefined}
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>タイトル</th>
                  <th>種別</th>
                  <th>識別子</th>
                  <th>SHA-256</th>
                  <th>参照</th>
                  <th>登録</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {sources.map((source) => (
                  <tr key={source.id}>
                    <td>
                      <button type="button" className="btn btn-ghost btn-sm" style={{ padding: 0, fontWeight: 600 }} onClick={() => void openSourceDetail(source)}>
                        {source.title}
                      </button>
                      {source.tampered ? <span className="badge badge-contradicted" style={{ marginLeft: 8 }}>改竄</span> : null}
                    </td>
                    <td><span className="badge badge-kind">{source.kind.toUpperCase()}</span></td>
                    <td className="small muted" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{source.origin || "—"}</td>
                    <td className="mono muted">{shortHash(source.content_sha256)}</td>
                    <td className="num">{source.used_by_claims ?? 0}</td>
                    <td className="muted small nowrap">{formatShortDate(source.created_at)}</td>
                    <td>
                      <div className="actions">
                        <button type="button" className="btn btn-sm" onClick={() => void openSourceDetail(source)}>詳細</button>
                        {editable ? <button type="button" className="btn btn-sm btn-danger" onClick={() => void removeSource(source)}>削除</button> : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : null}

      {tab === "claims" ? (
        claims.length === 0 ? (
          <EmptyState
            title="主張がまだありません"
            description="主張を作成し、出典の引用と結び付けて検証します。"
            action={editable ? <button type="button" className="btn btn-primary" onClick={() => setClaimModal(true)}>主張を作成</button> : undefined}
          />
        ) : (
          <>
            <div className="row" style={{ marginBottom: 10 }}>
              {editable ? (
                <button type="button" className="btn btn-sm" onClick={() => void verifyAll()} disabled={busy}>すべて検証</button>
              ) : null}
              <button type="button" className="btn btn-sm" onClick={() => navigate(`/projects/${projectId}/verification`)}>
                検証結果を開く
              </button>
              <span className="muted small">検証は決定論的です（引用の実在と数値の一致）。</span>
            </div>
            <div className="row" style={{ marginBottom: 10 }}>
              <select
                className="select"
                style={{ maxWidth: 180 }}
                aria-label="判定で絞り込み"
                value={claimFilter}
                onChange={(event) => setClaimFilter(event.target.value)}
              >
                <option value="all">すべての判定</option>
                <option value="verified">検証済</option>
                <option value="unverified">未検証</option>
                <option value="contradicted">矛盾</option>
                <option value="insufficient">根拠不足</option>
                <option value="unchecked">未検証（未実行）</option>
              </select>
              <input
                className="input"
                style={{ maxWidth: 260 }}
                placeholder="主張を検索"
                aria-label="主張を検索"
                value={claimQuery}
                onChange={(event) => setClaimQuery(event.target.value)}
              />
              <span className="muted small">{visibleClaims.length} / {claims.length} 件</span>
            </div>
            {visibleClaims.length === 0 ? (
              <EmptyState title="条件に一致する主張がありません" description="絞り込みを変えてください。" />
            ) : (
              <>
            <div className="table-wrap claims-table">
              <table className="table">
                <thead>
                  <tr>
                    <th>主張</th>
                    <th>判定</th>
                    <th>根拠</th>
                    <th>最終検証</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visibleClaims.map((claim) => (
                    <tr key={claim.id}>
                      <td style={{ maxWidth: 620 }}>
                        <div className="muted small mono">{claimCode(claim.id)}</div>
                        <div>{claim.text}</div>
                      </td>
                      <td><VerdictBadge verdict={claim.last_verdict} /></td>
                      <td className="num">{claim.evidence_count}</td>
                      <td className="muted small nowrap">{formatShortDate(claim.last_verified_at)}</td>
                      <td>
                        <div className="actions">
                          <button type="button" className="btn btn-sm" onClick={() => setClaimDetail(claim)}>詳細</button>
                          {editable ? (
                            <>
                              <button type="button" className="btn btn-sm" onClick={() => setEvidenceClaim(claim)}>根拠</button>
                              <button type="button" className="btn btn-sm" onClick={() => void verifyClaim(claim.id)}>検証</button>
                            </>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="claims-cards" aria-label="主張一覧">
              {visibleClaims.map((claim) => (
                <div key={claim.id} className="claim-card">
                  <div className="claim-card-text">{claim.text}</div>
                  <div className="row">
                    <VerdictBadge verdict={claim.last_verdict} />
                    <span className="muted small">根拠 {claim.evidence_count}</span>
                    <span className="muted small">最終検証 {formatShortDate(claim.last_verified_at)}</span>
                  </div>
                  <div className="row">
                    <button type="button" className="btn btn-sm" onClick={() => setClaimDetail(claim)}>詳細</button>
                    {editable ? (
                      <>
                        <button type="button" className="btn btn-sm" onClick={() => setEvidenceClaim(claim)}>根拠</button>
                        <button type="button" className="btn btn-sm" onClick={() => void verifyClaim(claim.id)}>検証</button>
                      </>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
              </>
            )}
          </>
        )
      ) : null}

      {tab === "reports" ? (
        reports.length === 0 ? (
          <EmptyState
            title="レポートがまだありません"
            description="セクションと段落に主張を参照させて、根拠付きのレポートを組み立てます。"
            action={editable ? <button type="button" className="btn btn-primary" onClick={() => setReportModal(true)}>レポートを作成</button> : undefined}
          />
        ) : (
          <>
            {editable ? (
              <div className="row" style={{ marginBottom: 10 }}>
                <button type="button" className="btn btn-primary btn-sm" onClick={() => setReportModal(true)}>+ レポート</button>
              </div>
            ) : null}
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>タイトル</th>
                    <th>状態</th>
                    <th>版</th>
                    <th>参照主張</th>
                    <th>提出者</th>
                    <th>更新</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {reports.map((report) => (
                    <tr key={report.id}>
                      <td style={{ fontWeight: 600 }}>{report.title}</td>
                      <td><ReportStatusBadge status={report.status} /></td>
                      <td className="num">v{report.version}</td>
                      <td className="num">{report.claim_count}</td>
                      <td className="muted small">{report.submitted_by_name ?? "—"}</td>
                      <td className="muted small nowrap">{formatShortDate(report.updated_at)}</td>
                      <td>
                        <button type="button" className="btn btn-sm" onClick={() => navigate(`/reports/${report.id}`)}>開く</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {canReview(user?.role) ? (
              <p className="hint" style={{ marginTop: 10 }}>
                レビュアーはレポートを開き、検証サマリを確認して承認または差し戻しできます。
              </p>
            ) : null}
          </>
        )
      ) : null}

      {sourceModal ? <SourceModal busy={busy} onClose={() => setSourceModal(false)} onSubmit={createSource} /> : null}
      {claimModal ? <ClaimModal busy={busy} onClose={() => setClaimModal(false)} onSubmit={createClaim} /> : null}
      {evidenceClaim ? (
        <EvidenceModal
          claim={evidenceClaim}
          sources={sources}
          busy={busy}
          onClose={() => setEvidenceClaim(null)}
          onSubmit={(payload) => void addEvidence(evidenceClaim.id, payload)}
        />
      ) : null}
      {reportModal ? <ReportModal busy={busy} onClose={() => setReportModal(false)} onSubmit={(title) => void createReport(title)} /> : null}
      {projectModal ? (
        <ProjectModal
          project={project}
          busy={busy}
          canDelete={user?.role === "admin"}
          onClose={() => setProjectModal(false)}
          onSubmit={updateProject}
          onDelete={async () => {
            if (!window.confirm("このテーマを削除しますか？ 出典・主張・レポートも削除されます。")) return;
            try {
              await api.deleteProject(project.id);
              toast("テーマを削除しました。");
              navigate("/");
            } catch (err) {
              toast(err instanceof Error ? err.message : "削除に失敗しました。", "error");
            }
          }}
        />
      ) : null}
      {claimDetail ? (
        <ClaimDetailModal
          claim={claimDetail}
          editable={editable}
          onClose={() => setClaimDetail(null)}
          onVerify={() => void verifyClaim(claimDetail.id)}
          onDelete={() => void removeClaim(claimDetail)}
          onUpdate={(text) => void updateClaimText(claimDetail, text)}
          onRemoveEvidence={async (evidenceId) => {
            try {
              await api.removeEvidence(claimDetail.id, evidenceId);
              toast("根拠を外しました。");
              const refreshed = await api.claim(claimDetail.id);
              setClaimDetail(refreshed.claim);
              await load();
            } catch (err) {
              toast(err instanceof Error ? err.message : "削除に失敗しました。", "error");
            }
          }}
        />
      ) : null}
      {sourceDetail ? (
        <SourceDetailModal source={sourceDetail} onClose={() => setSourceDetail(null)} onDelete={editable ? () => void removeSource(sourceDetail) : undefined} />
      ) : null}
    </div>
  );
}

function SourceModal({
  busy,
  onClose,
  onSubmit,
}: {
  busy: boolean;
  onClose: () => void;
  onSubmit: (payload: Record<string, unknown>) => void;
}) {
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("url");
  const [origin, setOrigin] = useState("");
  const [content, setContent] = useState("");
  return (
    <Modal
      title="出典を登録"
      onClose={onClose}
      width={760}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>キャンセル</button>
          <button type="submit" form="source-form" className="btn btn-primary" disabled={busy || !title.trim() || !content.trim()}>
            {busy ? "登録中…" : "登録"}
          </button>
        </>
      }
    >
      <form
        id="source-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ title, kind, origin, content });
        }}
      >
        <div className="form-row">
          <div className="field">
            <label htmlFor="source-title">タイトル</label>
            <input id="source-title" className="input" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={300} required />
          </div>
          <div className="field">
            <label htmlFor="source-kind">種別</label>
            <select id="source-kind" className="select" value={kind} onChange={(event) => setKind(event.target.value)}>
              <option value="url">URL</option>
              <option value="doi">DOI</option>
              <option value="text">テキスト</option>
            </select>
          </div>
        </div>
        <div className="field">
          <label htmlFor="source-origin">識別子（URL / DOI / 任意）</label>
          <input id="source-origin" className="input" value={origin} onChange={(event) => setOrigin(event.target.value)} maxLength={1000} />
        </div>
        <div className="field">
          <label htmlFor="source-content">本文（スナップショットとして保存）</label>
          <textarea id="source-content" className="textarea textarea-lg" value={content} onChange={(event) => setContent(event.target.value)} required />
          <span className="hint">本文は 1 MiB まで。登録時に SHA-256 を計算し、以後の改竄を検出します。</span>
        </div>
      </form>
    </Modal>
  );
}

function ClaimModal({ busy, onClose, onSubmit }: { busy: boolean; onClose: () => void; onSubmit: (text: string) => void }) {
  const [text, setText] = useState("");
  return (
    <Modal
      title="主張を作成"
      onClose={onClose}
      width={680}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>キャンセル</button>
          <button type="submit" form="claim-form" className="btn btn-primary" disabled={busy || text.trim().length < 10}>
            {busy ? "作成中…" : "作成"}
          </button>
        </>
      }
    >
      <form
        id="claim-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(text.trim());
        }}
      >
        <div className="field">
          <label htmlFor="claim-text">主張（10〜2000 文字）</label>
          <textarea id="claim-text" className="textarea" value={text} onChange={(event) => setText(event.target.value)} maxLength={2000} required />
          <span className="hint">数値を含めると、検証時に根拠との一致を確認できます。</span>
        </div>
      </form>
    </Modal>
  );
}

function EvidenceModal({
  claim,
  sources,
  busy,
  onClose,
  onSubmit,
}: {
  claim: Claim;
  sources: Source[];
  busy: boolean;
  onClose: () => void;
  onSubmit: (payload: { source_id: string; quote: string; note: string }) => void;
}) {
  const [sourceId, setSourceId] = useState(sources[0]?.id ?? "");
  const [quote, setQuote] = useState("");
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    if (!sourceId) {
      setPreview("");
      return;
    }
    api
      .source(sourceId)
      .then((result) => {
        if (!cancelled) setPreview(result.source.content ?? "");
      })
      .catch(() => {
        if (!cancelled) setPreview("");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceId]);

  return (
    <Modal
      title="根拠を紐付ける"
      onClose={onClose}
      width={760}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>キャンセル</button>
          <button type="submit" form="evidence-form" className="btn btn-primary" disabled={busy || !sourceId}>
            {busy ? "追加中…" : "根拠を追加"}
          </button>
        </>
      }
    >
      <div className="notice" style={{ marginBottom: 12 }}>{claim.text}</div>
      <form
        id="evidence-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ source_id: sourceId, quote, note });
        }}
      >
        <div className="field">
          <label htmlFor="evidence-source">出典</label>
          <select id="evidence-source" className="select" value={sourceId} onChange={(event) => setSourceId(event.target.value)}>
            {sources.map((source) => (
              <option key={source.id} value={source.id}>{source.title}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="evidence-quote">引用（本文にそのまま存在する必要があります）</label>
          <textarea id="evidence-quote" className="textarea" value={quote} onChange={(event) => setQuote(event.target.value)} maxLength={500} />
          <span className="hint">引用が空の場合は、主張内の数値が根拠本文に実在するかで判定します。</span>
        </div>
        <div className="field">
          <label htmlFor="evidence-note">メモ</label>
          <input id="evidence-note" className="input" value={note} onChange={(event) => setNote(event.target.value)} maxLength={1000} />
        </div>
        {preview ? (
          <details className="card" style={{ marginTop: 8 }}>
            <summary className="small muted" style={{ cursor: "pointer" }}>出典本文の先頭を確認</summary>
            <pre className="prewrap small" style={{ marginTop: 8, maxHeight: 180, overflow: "auto" }}>{preview.slice(0, 1200)}</pre>
          </details>
        ) : null}
      </form>
    </Modal>
  );
}

function ReportModal({ busy, onClose, onSubmit }: { busy: boolean; onClose: () => void; onSubmit: (title: string) => void }) {
  const [title, setTitle] = useState("");
  return (
    <Modal
      title="レポートを作成"
      onClose={onClose}
      width={560}
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>キャンセル</button>
          <button type="submit" form="report-form" className="btn btn-primary" disabled={busy || !title.trim()}>
            {busy ? "作成中…" : "作成"}
          </button>
        </>
      }
    >
      <form
        id="report-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(title.trim());
        }}
      >
        <div className="field">
          <label htmlFor="report-title">タイトル</label>
          <input id="report-title" className="input" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} required />
        </div>
      </form>
    </Modal>
  );
}

function ClaimDetailModal({
  claim,
  editable,
  onClose,
  onVerify,
  onDelete,
  onUpdate,
  onRemoveEvidence,
}: {
  claim: Claim;
  editable: boolean;
  onClose: () => void;
  onVerify: () => void;
  onDelete: () => void;
  onUpdate: (text: string) => void;
  onRemoveEvidence: (evidenceId: string) => void;
}) {
  const details = claim.last_details;
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(claim.text);

  useEffect(() => {
    setEditing(false);
    setEditText(claim.text);
  }, [claim.id, claim.text]);
  return (
    <Modal
      title="主張の詳細"
      onClose={onClose}
      width={760}
      footer={
        <>
          {editable ? <button type="button" className="btn btn-danger" onClick={onDelete}>削除</button> : null}
          <div className="spacer" />
          <button type="button" className="btn" onClick={onClose}>閉じる</button>
          {editable ? <button type="button" className="btn btn-primary" onClick={onVerify}>検証を実行</button> : null}
        </>
      }
    >
      <div className="row" style={{ marginBottom: 8 }}>
        <VerdictBadge verdict={claim.last_verdict} />
        <span className="muted small mono">{claimCode(claim.id)}</span>
        <span className="muted small">最終検証: {formatShortDate(claim.last_verified_at)}</span>
      </div>
      {editing ? (
        <div className="field">
          <textarea className="textarea" value={editText} onChange={(event) => setEditText(event.target.value)} maxLength={2000} />
          <div className="row" style={{ marginTop: 8 }}>
            <button type="button" className="btn btn-primary btn-sm" disabled={editText.trim().length < 10} onClick={() => onUpdate(editText.trim())}>
              保存
            </button>
            <button type="button" className="btn btn-sm" onClick={() => setEditing(false)}>キャンセル</button>
            <span className="hint">保存すると再検証が必要です。</span>
          </div>
        </div>
      ) : (
        <div className="row" style={{ marginBottom: 12, alignItems: "flex-start" }}>
          <p style={{ fontSize: 15, fontWeight: 600, margin: 0, flex: 1 }}>{claim.text}</p>
          {editable ? (
            <button type="button" className="btn btn-sm" onClick={() => setEditing(true)}>編集</button>
          ) : null}
        </div>
      )}
      {claim.last_verdict ? <p className="hint" style={{ marginBottom: 12 }}>{VERDICT_HINT[claim.last_verdict]}</p> : <p className="hint" style={{ marginBottom: 12 }}>まだ検証していません。</p>}

      <h3 style={{ fontSize: 13, marginBottom: 6 }}>根拠（{claim.evidence?.length ?? 0}）</h3>
      {(claim.evidence?.length ?? 0) === 0 ? (
        <p className="muted small">根拠が未登録です。出典と引用を紐付けてください。</p>
      ) : (
        <ul className="list-reset stack" style={{ gap: 8 }}>
          {claim.evidence?.map((evidence) => (
            <li key={evidence.id} className="card" style={{ padding: 12 }}>
              <div className="row">
                <b>{evidence.source_title ?? "（出典）"}</b>
                {evidence.quote_found === false ? <span className="badge badge-contradicted">引用が見つかりません</span> : null}
                {evidence.quote_found ? <span className="badge badge-verified">引用あり</span> : null}
                {editable ? (
                  <button type="button" className="btn btn-ghost btn-sm" style={{ marginLeft: "auto" }} onClick={() => onRemoveEvidence(evidence.id)}>
                    外す
                  </button>
                ) : null}
              </div>
              {evidence.quote ? <blockquote className="prewrap small" style={{ margin: "8px 0 0", paddingLeft: 10, borderLeft: "3px solid var(--accent-line)" }}>{evidence.quote}</blockquote> : <div className="muted small">引用なし</div>}
              {evidence.note ? <div className="muted small" style={{ marginTop: 4 }}>{evidence.note}</div> : null}
            </li>
          ))}
        </ul>
      )}

      {details ? (
        <div style={{ marginTop: 14 }}>
          <h3 style={{ fontSize: 13, marginBottom: 6 }}>検証の内訳</h3>
          <div className="small muted">理由: {details.reasons?.join(", ") || "—"}</div>
          {details.numbers?.length ? (
            <div className="small" style={{ marginTop: 6 }}>
              数値: {details.numbers.map((number) => `${number.value}${number.found ? "✓" : "✗"}`).join(" / ")}
            </div>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}

function SourceDetailModal({ source, onClose, onDelete }: { source: Source; onClose: () => void; onDelete?: () => void }) {
  return (
    <Modal
      title="出典の詳細"
      onClose={onClose}
      width={820}
      footer={
        <>
          {onDelete ? <button type="button" className="btn btn-danger" onClick={onDelete}>削除</button> : null}
          <div className="spacer" />
          <button type="button" className="btn" onClick={onClose}>閉じる</button>
        </>
      }
    >
      <dl className="kv" style={{ marginBottom: 12 }}>
        <dt>タイトル</dt><dd>{source.title}</dd>
        <dt>種別</dt><dd>{source.kind.toUpperCase()}</dd>
        <dt>識別子</dt><dd>{source.origin || "—"}</dd>
        <dt>SHA-256</dt><dd className="mono">{source.content_sha256}</dd>
        <dt>整合性</dt><dd>{source.tampered ? <span className="badge badge-contradicted">改竄を検出</span> : <span className="badge badge-verified">一致</span>}</dd>
      </dl>
      <h3 style={{ fontSize: 13, marginBottom: 6 }}>本文スナップショット</h3>
      <pre className="prewrap small" style={{ maxHeight: 320, overflow: "auto", background: "var(--surface-2)", padding: 12, borderRadius: 8, border: "1px solid var(--border)" }}>
        {source.content ?? "（本文は一覧では取得していません）"}
      </pre>
    </Modal>
  );
}


function ProjectModal({
  project,
  busy,
  canDelete,
  onClose,
  onSubmit,
  onDelete,
}: {
  project: Project;
  busy: boolean;
  canDelete: boolean;
  onClose: () => void;
  onSubmit: (payload: { title: string; summary: string; status: "active" | "archived" }) => void;
  onDelete: () => void;
}) {
  const [title, setTitle] = useState(project.title);
  const [summary, setSummary] = useState(project.summary);
  const [status, setStatus] = useState<"active" | "archived">(project.status);
  return (
    <Modal
      title="テーマを編集"
      onClose={onClose}
      width={620}
      footer={
        <>
          {canDelete ? <button type="button" className="btn btn-danger" onClick={onDelete}>テーマを削除</button> : null}
          <div className="spacer" />
          <button type="button" className="btn" onClick={onClose}>キャンセル</button>
          <button type="submit" form="project-edit-form" className="btn btn-primary" disabled={busy || !title.trim()}>
            {busy ? "保存中…" : "保存"}
          </button>
        </>
      }
    >
      <form
        id="project-edit-form"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ title: title.trim(), summary: summary.trim(), status });
        }}
      >
        <div className="field">
          <label htmlFor="project-edit-title">タイトル</label>
          <input id="project-edit-title" className="input" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} required />
        </div>
        <div className="field">
          <label htmlFor="project-edit-summary">概要</label>
          <textarea id="project-edit-summary" className="textarea" value={summary} onChange={(event) => setSummary(event.target.value)} maxLength={5000} />
        </div>
        <div className="field">
          <label htmlFor="project-edit-status">状態</label>
          <select id="project-edit-status" className="select" value={status} onChange={(event) => setStatus(event.target.value as "active" | "archived")}>
            <option value="active">進行中</option>
            <option value="archived">アーカイブ</option>
          </select>
        </div>
      </form>
    </Modal>
  );
}
