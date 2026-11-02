import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, api } from "./api";
import type { User } from "./types";

/** 明示的にログアウトした直後は、Access による自動サインインを同一タブで繰り返さない。 */
const ACCESS_LOGOUT_KEY = "rihrp:logged_out";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  /** null=未確認 / true=Cloudflare Access ログインが有効 / false=無効（パスワードログインを使う） */
  accessEnabled: boolean | null;
  accessError: string | null;
  login: (email: string, password: string) => Promise<void>;
  accessLogin: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [accessEnabled, setAccessEnabled] = useState<boolean | null>(null);
  const [accessError, setAccessError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const bootstrap = async () => {
      try {
        const result = await api.me();
        if (!cancelled) setUser(result.user);
      } catch (meError) {
        if (cancelled) return;
        // セッション確認が 401（未ログイン）のときだけ Access 自動サインインを試す。
        // 500/503/ネットワーク障害では自動サインインせず、エラーとして扱う。
        if (!(meError instanceof ApiError && meError.status === 401)) {
          setAccessEnabled(null);
          setAccessError(
            meError instanceof Error ? meError.message : "セッションの確認に失敗しました。",
          );
          return;
        }
        if (window.sessionStorage.getItem(ACCESS_LOGOUT_KEY) === "1") {
          setAccessEnabled(true);
          return;
        }
        try {
          const result = await api.accessLogin();
          if (cancelled) return;
          setUser(result.user);
          setAccessEnabled(true);
        } catch (err) {
          if (cancelled) return;
          if (err instanceof ApiError && err.status === 404) {
            setAccessEnabled(false);
          } else {
            setAccessEnabled(true);
            setAccessError(err instanceof Error ? err.message : "自動サインインに失敗しました。");
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener("rihrp:unauthorized", onUnauthorized);
    return () => window.removeEventListener("rihrp:unauthorized", onUnauthorized);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password);
    window.sessionStorage.removeItem(ACCESS_LOGOUT_KEY);
    setUser(result.user);
  }, []);

  const accessLogin = useCallback(async () => {
    setAccessError(null);
    const result = await api.accessLogin();
    window.sessionStorage.removeItem(ACCESS_LOGOUT_KEY);
    setAccessEnabled(true);
    setUser(result.user);
  }, []);

  const logout = useCallback(async () => {
    window.sessionStorage.setItem(ACCESS_LOGOUT_KEY, "1");
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, loading, accessEnabled, accessError, login, accessLogin, logout }),
    [user, loading, accessEnabled, accessError, login, accessLogin, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
