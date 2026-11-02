export type ApiErrorShape = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
};

export class ApiError extends Error {
  code: string;
  status: number;
  details?: Record<string, unknown>;

  constructor(status: number, body: ApiErrorShape) {
    super(body.message);
    this.status = status;
    this.code = body.code;
    this.details = body.details;
  }
}

function csrfToken(): string {
  const entry = document.cookie.split("; ").find((item) => item.startsWith("rihrp_csrf="));
  return entry ? decodeURIComponent(entry.split("=").slice(1).join("=")) : "";
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (method !== "GET" && method !== "HEAD") headers.set("X-CSRF-Token", csrfToken());
  const response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 401) {
    window.dispatchEvent(new Event("rihrp:unauthorized"));
  }
  const isJson = (response.headers.get("content-type") ?? "").includes("application/json");
  if (!response.ok) {
    const body = isJson ? await response.json() : { error: { code: "unknown", message: response.statusText } };
    throw new ApiError(response.status, body.error ?? { code: "unknown", message: "エラーが発生しました。" });
  }
  if (!isJson) {
    return (await response.text()) as unknown as T;
  }
  return (await response.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ user: import("./types").User; csrf_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }),
  me: () => request<{ user: import("./types").User; csrf_token: string }>("/api/auth/me"),

  projects: () => request<{ projects: import("./types").Project[] }>("/api/projects"),
  project: (id: string) => request<{ project: import("./types").Project }>(`/api/projects/${id}`),
  createProject: (title: string, summary: string) =>
    request<{ project: import("./types").Project }>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ title, summary }),
    }),
  updateProject: (id: string, patch: Record<string, unknown>) =>
    request<{ project: import("./types").Project }>(`/api/projects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  sources: (projectId: string) => request<{ sources: import("./types").Source[] }>(`/api/projects/${projectId}/sources`),
  source: (id: string) => request<{ source: import("./types").Source }>(`/api/sources/${id}`),
  createSource: (projectId: string, payload: Record<string, unknown>) =>
    request<{ source: import("./types").Source }>(`/api/projects/${projectId}/sources`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteSource: (id: string) => request<{ ok: boolean }>(`/api/sources/${id}`, { method: "DELETE" }),

  claims: (projectId: string) => request<{ claims: import("./types").Claim[] }>(`/api/projects/${projectId}/claims`),
  claim: (id: string) => request<{ claim: import("./types").Claim }>(`/api/claims/${id}`),
  createClaim: (projectId: string, text: string) =>
    request<{ claim: import("./types").Claim }>(`/api/projects/${projectId}/claims`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  updateClaim: (id: string, text: string) =>
    request<{ claim: import("./types").Claim }>(`/api/claims/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ text }),
    }),
  deleteClaim: (id: string) => request<{ ok: boolean }>(`/api/claims/${id}`, { method: "DELETE" }),
  addEvidence: (claimId: string, payload: { source_id: string; quote: string; note: string }) =>
    request<{ evidence: import("./types").Evidence[] }>(`/api/claims/${claimId}/evidence`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  removeEvidence: (claimId: string, evidenceId: string) =>
    request<{ ok: boolean }>(`/api/claims/${claimId}/evidence/${evidenceId}`, { method: "DELETE" }),
  verifyClaim: (id: string) =>
    request<{ claim: import("./types").Claim; result: { verdict: string; reasons: string[] } }>(
      `/api/claims/${id}/verify`,
      { method: "POST" },
    ),
  verifyProjectClaims: (projectId: string) =>
    request<{ verified: number }>(`/api/projects/${projectId}/claims/verify`, { method: "POST" }),

  reports: (projectId: string) =>
    request<{ reports: { id: string; title: string; status: string; version: number; submitted_by_name: string | null; updated_at: string | null; claim_count: number }[] }>(
      `/api/projects/${projectId}/reports`,
    ),
  report: (id: string) => request<{ report: import("./types").Report }>(`/api/reports/${id}`),
  createReport: (projectId: string, title: string) =>
    request<{ report: import("./types").Report }>(`/api/projects/${projectId}/reports`, {
      method: "POST",
      body: JSON.stringify({ title }),
    }),
  saveReport: (id: string, payload: { title?: string; content?: import("./types").ReportContent; note?: string }) =>
    request<{ report: import("./types").Report }>(`/api/reports/${id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  verifyReport: (id: string) =>
    request<{ report: import("./types").Report; summary: import("./types").VerificationSummary }>(
      `/api/reports/${id}/verify`,
      { method: "POST" },
    ),
  submitReport: (id: string) =>
    request<{ report: import("./types").Report }>(`/api/reports/${id}/submit`, { method: "POST" }),
  reviewReport: (id: string, decision: "approved" | "changes_requested", comment: string) =>
    request<{ report: import("./types").Report }>(`/api/reports/${id}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, comment }),
    }),
  exportReportUrl: (id: string) => `/api/reports/${id}/export`,

  audit: (limit = 100) => request<{ events: import("./types").AuditEvent[] }>(`/api/audit?limit=${limit}`),
  users: () => request<{ users: import("./types").User[] }>("/api/users"),
  createUser: (payload: { email: string; name: string; role: string; password: string }) =>
    request<{ user: import("./types").User }>("/api/users", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateUser: (id: string, payload: Record<string, unknown>) =>
    request<{ user: import("./types").User }>(`/api/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
};
