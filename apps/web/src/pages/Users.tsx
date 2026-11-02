import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Role, User } from "../types";
import { ROLE_LABEL, formatDate } from "../utils";
import { EmptyState, ErrorBanner, Loading, Modal, useToast } from "../components/ui";

const ROLES: Role[] = ["editor", "reviewer", "viewer", "admin"];

export function UsersPage() {
  const toast = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ email: "", name: "", role: "editor" as Role, password: "" });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.users();
      setUsers(result.users);
    } catch (err) {
      setError(err instanceof Error ? err.message : "利用者の取得に失敗しました。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      await api.createUser(form);
      toast("利用者を作成しました。");
      setCreating(false);
      setForm({ email: "", name: "", role: "editor", password: "" });
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "作成に失敗しました。", "error");
    } finally {
      setBusy(false);
    }
  };

  const toggleActive = async (user: User) => {
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      toast(user.is_active ? "利用者を無効化しました。" : "利用者を有効化しました。");
      await load();
    } catch (err) {
      toast(err instanceof Error ? err.message : "更新に失敗しました。", "error");
    }
  };

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <h1 className="page-title">利用者管理</h1>
          <div className="page-desc">役割は admin / editor / reviewer / viewer の 4 種です。</div>
        </div>
        <div className="spacer" />
        <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>+ 利用者</button>
      </div>

      {error ? <ErrorBanner message={error} onRetry={() => void load()} /> : null}
      {loading ? (
        <Loading label="利用者を読み込んでいます…" />
      ) : users.length === 0 ? (
        <EmptyState title="利用者がいません" />
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>名前</th>
                <th>メール</th>
                <th>役割</th>
                <th>状態</th>
                <th>作成</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td style={{ fontWeight: 600 }}>{user.name}</td>
                  <td className="mono small">{user.email}</td>
                  <td>{ROLE_LABEL[user.role]}</td>
                  <td>{user.is_active ? <span className="badge badge-verified">有効</span> : <span className="badge badge-insufficient">無効</span>}</td>
                  <td className="muted small">{formatDate(user.created_at)}</td>
                  <td>
                    <button type="button" className="btn btn-sm" onClick={() => void toggleActive(user)}>
                      {user.is_active ? "無効化" : "有効化"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creating ? (
        <Modal
          title="利用者を作成"
          onClose={() => setCreating(false)}
          width={560}
          footer={
            <>
              <button type="button" className="btn" onClick={() => setCreating(false)}>キャンセル</button>
              <button type="submit" form="user-form" className="btn btn-primary" disabled={busy || !form.email || !form.name || form.password.length < 12}>
                {busy ? "作成中…" : "作成"}
              </button>
            </>
          }
        >
          <form id="user-form" onSubmit={onCreate}>
            <div className="field">
              <label htmlFor="user-email">メールアドレス</label>
              <input id="user-email" className="input" type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required />
            </div>
            <div className="form-row">
              <div className="field">
                <label htmlFor="user-name">名前</label>
                <input id="user-name" className="input" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required />
              </div>
              <div className="field">
                <label htmlFor="user-role">役割</label>
                <select id="user-role" className="select" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value as Role })}>
                  {ROLES.map((role) => <option key={role} value={role}>{ROLE_LABEL[role]}</option>)}
                </select>
              </div>
            </div>
            <div className="field">
              <label htmlFor="user-password">初期パスワード（12 文字以上）</label>
              <input id="user-password" className="input" type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} minLength={12} required />
            </div>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}
