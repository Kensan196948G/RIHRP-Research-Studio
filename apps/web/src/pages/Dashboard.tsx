import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";
import type { AuditEvent, Project } from "../types";
import { useAuth } from "../auth";
import { auditActionLabel, canEdit, canReview, countUnresolved, formatShortDate, shortHash } from "../utils";
import { EmptyState, ErrorBanner, Loading, Modal, useToast } from "../components/ui";

function totalOf(projects: Project[], key: keyof Project["stats"]): number {
  return projects.reduce((sum, project) => sum + Number(project.stats[key] ?? 0), 0);
}

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [recent, setRecent] = useState<AuditEvent[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.projects();
      setProjects(result.projects);
    } catch (err) {
      setError(err instanceof Error ? err.message : "テーマの取得に失敗しました。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!user || !canReview(user.role)) return;
    let cancelled = false;
    api
      .audit(6)
      .then((result) => {
        if (!cancelled) setRecent(result.events);
      })
      .catch(() => {
        if (!cancelled) setRecent([]);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const filteredProjects = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return projects;
    return projects.filter((project) => `${project.title} ${project.summary}`.toLowerCase().includes(needle));
  }, [projects, query]);

  const totals = useMemo(
    () => ({
      projects: projects.length,
      unverified: totalOf(projects, "unverified"),
      contradicted: totalOf(projects, "contradicted"),
      reviewPending: totalOf(projects, "review_pending"),
      changesRequested: totalOf(projects, "changes_requested"),
      sources: totalOf(projects, "sources"),
      claims: totalOf(projects, "claims"),
    }),
    [projects],
  );

  const onCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    try {
      const result = await api.createProject(title.trim(), summary.trim());
      toast("テーマを作成しました。");
      setCreating(false);
      setTitle("");
      setSummary("");
      navigate(`/projects/${result.project.id}`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "作成に失敗しました。", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <h1 className="page-title">ダッシュボード</h1>
          <div className="page-desc">研究テーマの状態と、対応が必要な項目をまとめています。</div>
        </div>
        <div className="spacer" />
        <input
          className="input"
          style={{ maxWidth: 240 }}
          placeholder="テーマを検索"
          aria-label="テーマを検索"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        {canEdit(user?.role) ? (
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            + 新しいテーマ
          </button>
        ) : null}
      </div>

      {error ? <ErrorBanner message={error} onRetry={() => void load()} /> : null}

      <div className="stat-grid">
        <div className="stat">
          <div className="stat-label">テーマ</div>
          <div className="stat-value">{totals.projects}</div>
          <div className="stat-foot">出典 {totals.sources} 件 / 主張 {totals.claims} 件</div>
        </div>
        <div className={`stat ${totals.unverified ? "is-warn" : ""}`}>
          <div className="stat-label">未検証の主張</div>
          <div className="stat-value">{totals.unverified}</div>
          <div className="stat-foot">数値が根拠に見つからない主張</div>
        </div>
        <div className={`stat ${totals.contradicted ? "is-alert" : ""}`}>
          <div className="stat-label">矛盾</div>
          <div className="stat-value">{totals.contradicted}</div>
          <div className="stat-foot">引用不一致・スナップショット改竄</div>
        </div>
        <div className={`stat ${totals.reviewPending + totals.changesRequested ? "is-warn" : ""}`}>
          <div className="stat-label">レビュー待ち / 差し戻し</div>
          <div className="stat-value">{totals.reviewPending} / {totals.changesRequested}</div>
          <div className="stat-foot">承認者による確認が必要なレポート</div>
        </div>
      </div>

      <div className="dashboard-grid">
        <div>
      {loading ? (
        <Loading label="テーマを読み込んでいます…" />
      ) : projects.length === 0 ? (
        <EmptyState
          title="テーマがまだありません"
          description="最初の研究テーマを作成し、出典と主張を登録してください。"
          action={
            canEdit(user?.role) ? (
              <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
                テーマを作成
              </button>
            ) : undefined
          }
        />
      ) : filteredProjects.length === 0 ? (
        <EmptyState title="該当するテーマがありません" description="検索条件を変えてください。" />
      ) : (
        <>
        <div className="table-wrap dashboard-table">
          <table className="table table-fixed">
            <colgroup>
              <col style={{ width: "58%" }} />
              <col style={{ width: "13%" }} />
              <col style={{ width: "13%" }} />
              <col style={{ width: "16%" }} />
            </colgroup>
            <thead>
              <tr>
                <th>テーマ</th>
                <th>未検証</th>
                <th>矛盾</th>
                <th>更新</th>
              </tr>
            </thead>
            <tbody>
              {filteredProjects.map((project) => {
                const unresolved = countUnresolved(project.stats);
                return (
                  <tr
                    key={project.id}
                    className="row-link"
                    onClick={() => navigate(`/projects/${project.id}`)}
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") navigate(`/projects/${project.id}`);
                    }}
                  >
                    <td>
                      <div className="row-title" style={{ fontWeight: 600 }}>{project.title}</div>
                      <div className="muted small" style={{ maxWidth: "100%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {project.summary || "概要は未設定です。"}
                      </div>
                      <div className="muted small">
                        出典 {project.stats.sources} ・ 主張 {project.stats.claims}
                        {unresolved > 0 ? ` ・ 要対応 ${unresolved}` : ""}
                        {project.stats.review_pending > 0 ? ` ・ レビュー待ち ${project.stats.review_pending}` : ""}
                      </div>
                      <div className="muted small mono">#{shortHash(project.id)}</div>
                    </td>
                    <td className="num">{project.stats.unverified}</td>
                    <td className="num" style={{ color: project.stats.contradicted ? "var(--danger)" : undefined, fontWeight: project.stats.contradicted ? 700 : undefined }}>
                      {project.stats.contradicted}
                    </td>
                    <td className="muted small nowrap">{formatShortDate(project.updated_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div className="project-cards" aria-label="テーマ一覧">
          {filteredProjects.map((project) => (
            <button key={project.id} type="button" className="project-card" onClick={() => navigate(`/projects/${project.id}`)}>
              <div className="project-card-title">{project.title}</div>
              <div className="muted small">
                出典 {project.stats.sources} ・ 主張 {project.stats.claims} ・ 更新 {formatShortDate(project.updated_at)}
              </div>
              <div className="row" style={{ gap: 6, marginTop: 4 }}>
                <span className="badge badge-unverified">未検証 {project.stats.unverified}</span>
                <span className="badge badge-contradicted">矛盾 {project.stats.contradicted}</span>
                {project.stats.review_pending ? <span className="badge badge-in_review">レビュー {project.stats.review_pending}</span> : null}
              </div>
            </button>
          ))}
        </div>
        </>
      )}
        </div>

        <aside className="attention-rail" aria-label="要対応">
          <div className="card">
            <div className="card-head">
              <h2 className="card-title">要対応</h2>
              <span className="badge badge-unverified" style={{ marginLeft: "auto" }}>
                {totals.unverified + totals.contradicted + totals.reviewPending + totals.changesRequested} 件
              </span>
            </div>
            <div className="attention-list">
              <div className="attention-row">
                <span className="attention-dot attention-dot-warn" aria-hidden="true" />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600 }}>未検証の主張</div>
                  <div className="muted small">数値が根拠に見つからない</div>
                </div>
                <b>{totals.unverified}</b>
              </div>
              <div className="attention-row">
                <span className="attention-dot attention-dot-danger" aria-hidden="true" />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600 }}>矛盾</div>
                  <div className="muted small">承認が止まる項目</div>
                </div>
                <b style={{ color: totals.contradicted ? "var(--danger)" : undefined }}>{totals.contradicted}</b>
              </div>
              <div className="attention-row">
                <span className="attention-dot attention-dot-info" aria-hidden="true" />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600 }}>レビュー待ち</div>
                  <div className="muted small">承認または差し戻し</div>
                </div>
                <b>{totals.reviewPending}</b>
              </div>
              <div className="attention-row">
                <span className="attention-dot attention-dot-warn" aria-hidden="true" />
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600 }}>差し戻し</div>
                  <div className="muted small">修正後の再提出が必要</div>
                </div>
                <b>{totals.changesRequested}</b>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <h2 className="card-title" style={{ marginBottom: 8 }}>対応が必要なテーマ</h2>
            {projects.length === 0 ? (
              <p className="muted small">テーマがありません。</p>
            ) : (
              <div className="attention-list">
                {[...projects]
                  .sort((a, b) => {
                    const score = (p: Project) => p.stats.contradicted * 3 + p.stats.unverified + p.stats.review_pending * 2 + p.stats.changes_requested * 2;
                    return score(b) - score(a);
                  })
                  .slice(0, 5)
                  .map((project) => (
                    <button key={project.id} type="button" className="attention-project" onClick={() => navigate(`/projects/${project.id}`)}>
                      <span className="attention-project-title">{project.title}</span>
                      <span className="muted small">
                        未検証 {project.stats.unverified} / 矛盾 {project.stats.contradicted} / レビュー {project.stats.review_pending}
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </div>

          {canReview(user?.role) ? (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="card-head">
                <h2 className="card-title">最近の活動</h2>
                <Link to="/audit" className="small" style={{ marginLeft: "auto" }}>監査ログ</Link>
              </div>
              {recent.length === 0 ? (
                <p className="muted small">履歴がありません。</p>
              ) : (
                <ul className="list-reset stack" style={{ gap: 8 }}>
                  {recent.map((event) => (
                    <li key={event.id} className="small">
                      <div style={{ fontWeight: 600 }}>{auditActionLabel(event.action)}</div>
                      <div className="muted">{event.actor_name ?? "—"} / {formatShortDate(event.created_at)}</div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}

          <div className="card" style={{ marginTop: 12 }}>
            <h2 className="card-title" style={{ marginBottom: 6 }}>検証の考え方</h2>
            <p className="muted small">
              矛盾（contradicted）は承認を止めます。未検証・根拠不足は承認を止めませんが、件数を承認画面とエクスポートに残します。
            </p>
          </div>
        </aside>
      </div>

      {creating ? (
        <Modal title="新しいテーマ" onClose={() => setCreating(false)} width={620}>
          <form onSubmit={onCreate}>
            <div className="field">
              <label htmlFor="project-title">タイトル</label>
              <input id="project-title" className="input" value={title} onChange={(event) => setTitle(event.target.value)} maxLength={200} required />
            </div>
            <div className="field">
              <label htmlFor="project-summary">概要</label>
              <textarea id="project-summary" className="textarea" value={summary} onChange={(event) => setSummary(event.target.value)} maxLength={5000} />
              <span className="hint">調査の目的・範囲・意思決定に使う予定を書いておくと、レビューが速くなります。</span>
            </div>
            <div className="modal-foot">
              <button type="button" className="btn" onClick={() => setCreating(false)}>キャンセル</button>
              <button type="submit" className="btn btn-primary" disabled={busy || !title.trim()}>
                {busy ? "作成中…" : "作成"}
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
