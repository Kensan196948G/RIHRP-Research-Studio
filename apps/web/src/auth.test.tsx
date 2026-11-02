import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./auth";
import type { User } from "./types";

const USER: User = {
  id: "u1",
  email: "editor@example.com",
  name: "editor",
  role: "editor",
  is_active: true,
  created_at: null,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function Probe() {
  const { user, loading, accessEnabled, accessError } = useAuth();
  if (loading) return <span>loading</span>;
  return (
    <span>
      {user?.email ?? "none"}|{String(accessEnabled)}|{accessError ?? ""}
    </span>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("AuthProvider", () => {
  it("auto signs in via Cloudflare Access when the session is absent", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) {
        return json({ error: { code: "unauthorized", message: "ログインが必要です。" } }, 401);
      }
      if (url.endsWith("/api/auth/access")) {
        return json({ user: USER, csrf_token: "csrf" });
      }
      return json({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    expect(await screen.findByText("editor@example.com|true|")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/access",
      expect.objectContaining({ credentials: "same-origin" }),
    );
  });

  it("falls back to the password form when Access login is disabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/api/auth/me")) {
          return json({ error: { code: "unauthorized", message: "ログインが必要です。" } }, 401);
        }
        if (url.endsWith("/api/auth/access")) {
          return json({ error: { code: "access_login_disabled", message: "無効です。" } }, 404);
        }
        return json({});
      }),
    );

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    expect(await screen.findByText("none|false|")).toBeInTheDocument();
  });

  it("skips auto sign-in immediately after an explicit logout", async () => {
    window.sessionStorage.setItem("rihrp:logged_out", "1");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) {
        return json({ error: { code: "unauthorized", message: "ログインが必要です。" } }, 401);
      }
      return json({ user: USER, csrf_token: "csrf" });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    expect(await screen.findByText("none|true|")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/api/auth/access"))).toBe(false);
  });
});

describe("AuthProvider error handling", () => {
  it("does not fall back to Access login when the session check fails with 500", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/api/auth/me")) {
        return json({ error: { code: "internal", message: "サーバーエラー" } }, 500);
      }
      if (url.endsWith("/api/auth/access")) {
        return json({ user: USER, csrf_token: "csrf" });
      }
      return json({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    expect(await screen.findByText("none|null|サーバーエラー")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith("/api/auth/access"))).toBe(
      false,
    );
  });
});
