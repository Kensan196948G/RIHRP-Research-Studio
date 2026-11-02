import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ROLE_LABEL, canReview } from "../utils";

function NavIcon({ name }: { name: "home" | "audit" | "users" }) {
  const paths: Record<string, string> = {
    home: "M3 10.5 12 3l9 7.5V21H3V10.5Z",
    audit: "M5 3h14v18H5V3Zm3 5h8M8 12h8M8 16h5",
    users: "M8 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm8 0a3 3 0 1 0 0-6M2 21c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5m1-5.2c2.8.3 5 2.4 5 5.2",
  };
  return (
    <svg className="nav-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const onLogout = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">本文へ移動</a>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">RI</div>
          <div>
            <div className="brand-name">RIHRP Research Studio</div>
            <div className="brand-sub">根拠付きリサーチ</div>
          </div>
        </div>

        <nav className="nav" aria-label="メインナビゲーション">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? "is-active" : ""}`}>
            <NavIcon name="home" />
            <span className="nav-label">ダッシュボード</span>
          </NavLink>
          <NavLink to="/audit" className={({ isActive }) => `nav-link ${isActive ? "is-active" : ""}`}>
            <NavIcon name="audit" />
            <span className="nav-label">監査ログ</span>
          </NavLink>
          {user?.role === "admin" ? (
            <NavLink to="/users" className={({ isActive }) => `nav-link ${isActive ? "is-active" : ""}`}>
              <NavIcon name="users" />
              <span className="nav-label">利用者</span>
            </NavLink>
          ) : null}
        </nav>

        <div className="sidebar-foot">
          <div className="user-card">
            <div className="avatar" aria-hidden="true">{user?.name?.slice(0, 1) ?? "?"}</div>
            <div className="user-meta">
              <div className="user-name">{user?.name}</div>
              <div className="user-role">{user ? ROLE_LABEL[user.role] : ""}</div>
            </div>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onLogout} aria-label="ログアウト" title="ログアウト">
              <span className="logout-label">ログアウト</span>
              <span className="logout-glyph" aria-hidden="true">⎋</span>
            </button>
          </div>
        </div>
      </aside>

      <main className="main" id="main-content" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}

export function canSeeAudit(role: string | undefined): boolean {
  return canReview(role as never);
}
