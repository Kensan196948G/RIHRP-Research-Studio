import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { useAuth } from "./auth";
import { canReview } from "./utils";
import { AuditPage } from "./pages/Audit";
import { DashboardPage } from "./pages/Dashboard";
import { LoginPage } from "./pages/Login";
import { ProjectPage } from "./pages/Project";
import { ReportEditorPage } from "./pages/ReportEditor";
import { SettingsPage } from "./pages/Settings";
import { UsersPage } from "./pages/Users";
import { VerificationPage } from "./pages/Verification";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div style={{ padding: 40 }}>
        <Loading label="セッションを確認しています…" />
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

function RequireReviewer({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (!user || !canReview(user.role)) {
    return (
      <div style={{ padding: 40 }}>
        <div className="card">
          <h2>権限がありません</h2>
          <p className="muted">この画面はレビュアー以上のみ閲覧できます。</p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

function RequireAdmin({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user?.role !== "admin") {
    return (
      <div style={{ padding: 40 }}>
        <div className="card">
          <h2>権限がありません</h2>
          <p className="muted">この画面は管理者のみ閲覧できます。</p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="/projects/:projectId" element={<ProjectPage />} />
        <Route path="/projects/:projectId/verification" element={<VerificationPage />} />
        <Route path="/reports/:reportId" element={<ReportEditorPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route
          path="/audit"
          element={
            <RequireReviewer>
              <AuditPage />
            </RequireReviewer>
          }
        />
        <Route
          path="/users"
          element={
            <RequireAdmin>
              <UsersPage />
            </RequireAdmin>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
