import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { AuditEvent } from "../types";
import { auditActionLabel, formatDate } from "../utils";
import { EmptyState, ErrorBanner, Loading } from "../components/ui";



export function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.audit(200);
      setEvents(result.events);
    } catch (err) {
      setError(err instanceof Error ? err.message : "監査ログの取得に失敗しました。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!needle) return events;
    return events.filter((event) =>
      [event.action, event.actor_name ?? "", event.entity_type, event.entity_id, JSON.stringify(event.details)]
        .join(" ")
        .toLowerCase()
        .includes(needle),
    );
  }, [events, filter]);

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <h1 className="page-title">監査ログ</h1>
          <div className="page-desc">業務操作と同一トランザクションで追記された履歴です（更新・削除はできません）。</div>
        </div>
        <div className="spacer" />
        <input
          className="input"
          style={{ maxWidth: 280 }}
          placeholder="操作・実行者・対象で絞り込み"
          aria-label="監査ログの絞り込み"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        />
        <button type="button" className="btn" onClick={() => void load()}>再読み込み</button>
      </div>

      {error ? <ErrorBanner message={error} onRetry={() => void load()} /> : null}
      {loading ? (
        <Loading label="監査ログを読み込んでいます…" />
      ) : filtered.length === 0 ? (
        <EmptyState title="該当する履歴がありません" description="操作を行うと、ここに追記されます。" />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>時刻</th>
                <th>実行者</th>
                <th>操作</th>
                <th>対象</th>
                <th>詳細</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((event) => (
                <tr key={event.id}>
                  <td className="muted small nowrap">{formatDate(event.created_at)}</td>
                  <td>{event.actor_name ?? "—"}</td>
                  <td>
                    <div style={{ fontWeight: 600 }}>{auditActionLabel(event.action)}</div>
                    <div className="muted small mono">{event.action}</div>
                  </td>
                  <td className="small">
                    <div>{event.entity_type}</div>
                    <div className="muted mono">{event.entity_id || "—"}</div>
                  </td>
                  <td className="small mono" style={{ maxWidth: 380, wordBreak: "break-all" }}>
                    {Object.keys(event.details ?? {}).length ? JSON.stringify(event.details) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
