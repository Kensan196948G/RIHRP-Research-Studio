import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

const DEMO_ACCOUNTS = [
  ["editor@rihrp.local", "リサーチャー"],
  ["reviewer@rihrp.local", "レビュアー"],
  ["admin@rihrp.local", "管理者"],
  ["viewer@rihrp.local", "閲覧者"],
];

export function LoginPage() {
  const { user, loading, login, accessEnabled, accessError, accessLogin } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("editor@rihrp.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const isLocal = ["localhost", "127.0.0.1", "192.168.0.185"].includes(window.location.hostname);

  if (!loading && user) {
    const target = (location.state as { from?: string } | null)?.from ?? "/";
    return <Navigate to={target} replace />;
  }

  const onAccessLogin = async () => {
    setError(null);
    setSubmitting(true);
    try {
      await accessLogin();
      const target = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(target, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Cloudflare Access でのサインインに失敗しました。");
    } finally {
      setSubmitting(false);
    }
  };

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      const target = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(target, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "ログインに失敗しました。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <aside className="login-aside">
        <div>
          <div className="brand" style={{ padding: 0, marginBottom: 18 }}>
            <div className="brand-mark" aria-hidden="true">RI</div>
            <div>
              <div className="brand-name" style={{ color: "#fff" }}>RIHRP Research Studio</div>
              <div className="brand-sub" style={{ color: "#9fb6c2" }}>根拠付きリサーチスタジオ</div>
            </div>
          </div>
          <h1>主張と根拠を、<br />たどれる形で残す。</h1>
          <p style={{ marginTop: 14 }}>
            出典はスナップショットと SHA-256 で固定し、主張は引用と数値で検証する。
            承認は矛盾ゼロを条件に、未検証の残数も隠さない。
          </p>
        </div>
        <div className="login-points">
          <div className="login-point"><span className="login-dot" /><span><b>根拠の固定</b> — 登録時の本文を内容アドレスで保存し、改竄を検出します。</span></div>
          <div className="login-point"><span className="login-dot" /><span><b>決定論的な検証</b> — 引用の実在と数値の一致を機械的に判定します。</span></div>
          <div className="login-point"><span className="login-dot" /><span><b>説明できる承認</b> — 矛盾は承認を止め、未検証は件数として表示します。</span></div>
        </div>
      </aside>

      <main className="login-main">
        <div className="login-card">
          <h2>ログイン</h2>
          <span className="hint">組織のアカウントでサインインしてください。</span>
          {loading ? (
            <div className="hint" role="status">Cloudflare Access で認証しています…</div>
          ) : null}
          {accessEnabled ? (
            <div className="access-box">
              <div className="muted">
                Cloudflare Access で認証済みの場合は、そのままサインインできます。
              </div>
              <button
                type="button"
                className="btn btn-primary"
                style={{ width: "100%", marginTop: 8 }}
                onClick={onAccessLogin}
                disabled={submitting || loading}
              >
                Cloudflare Access でサインイン
              </button>
              {accessError ? <div className="error-banner" role="alert">{accessError}</div> : null}
            </div>
          ) : null}
          {error ? <div className="error-banner" role="alert">{error}</div> : null}
          <form onSubmit={onSubmit} noValidate>
            <div className="field">
              <label htmlFor="email">メールアドレス</label>
              <input
                id="email"
                className="input"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="password">パスワード</label>
              <input
                id="password"
                className="input"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
            <button type="submit" className="btn btn-primary" style={{ width: "100%" }} disabled={submitting}>
              {submitting ? "サインイン中…" : "サインイン"}
            </button>
          </form>
          {isLocal ? (
            <div className="demo-box">
              <div style={{ fontWeight: 600, marginBottom: 6 }}>開発用アカウント（ローカルのみ表示）</div>
              <div className="muted">初期パスワードは環境変数 <code>RIHRP_SEED_PASSWORD</code> で設定します。</div>
              <ul className="list-reset" style={{ marginTop: 6 }}>
                {DEMO_ACCOUNTS.map(([address, role]) => (
                  <li key={address}><code>{address}</code> <span className="muted">/ {role}</span></li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </main>
    </div>
  );
}
