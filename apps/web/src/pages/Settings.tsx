import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { ROLE_LABEL } from "../utils";
import { useToast } from "../components/ui";

export function SettingsPage() {
  const { user } = useAuth();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (next.length < 12) {
      toast("新しいパスワードは 12 文字以上にしてください。", "error");
      return;
    }
    if (next !== confirm) {
      toast("確認用パスワードが一致しません。", "error");
      return;
    }
    setBusy(true);
    try {
      await api.changePassword(current, next);
      setCurrent("");
      setNext("");
      setConfirm("");
      toast("パスワードを変更しました。");
    } catch (err) {
      toast(err instanceof Error ? err.message : "変更に失敗しました。", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="content">
      <div className="page-head">
        <div>
          <h1 className="page-title">設定</h1>
          <div className="page-desc">アカウント情報とパスワードを管理します。</div>
        </div>
      </div>

      <div className="split-2">
        <div className="card">
          <div className="card-head"><h2 className="card-title">アカウント</h2></div>
          <dl className="kv">
            <dt>名前</dt><dd>{user?.name}</dd>
            <dt>メール</dt><dd className="mono">{user?.email}</dd>
            <dt>役割</dt><dd>{user ? ROLE_LABEL[user.role] : "—"}</dd>
          </dl>
          {user?.role === "admin" ? (
            <p className="hint" style={{ marginTop: 10 }}>
              利用者の追加・無効化・役割変更は <Link to="/users">利用者</Link> から行えます。
            </p>
          ) : null}
        </div>

        <div className="card">
          <div className="card-head"><h2 className="card-title">パスワード変更</h2></div>
          <form onSubmit={submit}>
            <div className="field">
              <label htmlFor="current-password">現在のパスワード</label>
              <input id="current-password" className="input" type="password" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} required />
            </div>
            <div className="field">
              <label htmlFor="new-password">新しいパスワード（12 文字以上）</label>
              <input id="new-password" className="input" type="password" autoComplete="new-password" value={next} onChange={(event) => setNext(event.target.value)} minLength={12} required />
            </div>
            <div className="field">
              <label htmlFor="confirm-password">新しいパスワード（確認）</label>
              <input id="confirm-password" className="input" type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} minLength={12} required />
            </div>
            <button type="submit" className="btn btn-primary" disabled={busy || !current || !next || !confirm}>
              {busy ? "変更中…" : "パスワードを変更"}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
