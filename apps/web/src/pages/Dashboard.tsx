import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { Project } from "../types";
import { useAuth } from "../auth";
import { canEdit, countUnresolved, formatShortDate, shortHash } from "../utils";
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
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>テーマ</th>
                <th>出典</th>
                <th>主張</th>
                <th>未検証</th>
                <th>矛盾</th>
                <th>レビュー待ち</th>
                <th>更新</th>
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => {
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
                      <div className="muted small" style={{ maxWidth: 520, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {project.summary || "概要は未設定です。"}
                      </div>
                      <div className="muted small mono">#{shortHash(project.id)}</div>
                    </td>
                    <td className="num">{project.stats.sources}</td>
                    <td className="num">
                      {project.stats.claims}
                      {unresolved > 0 ? <span className="muted small">（要対応 {unresolved}）</span> : null}
                    </td>
                    <td className="num">{project.stats.unverified}</td>
                    <td className="num" style={{ color: project.stats.contradicted ? "var(--danger)" : undefined, fontWeight: project.stats.contradicted ? 700 : undefined }}>
                      {project.stats.contradicted}
                    </td>
                    <td className="num">{project.stats.review_pending}</td>
                    <td className="muted small nowrap">{formatShortDate(project.updated_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

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
