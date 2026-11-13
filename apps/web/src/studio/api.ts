/** 研究ワークスペース文書 API クライアント（Offline Research Studio 用）。 */

export type ResearchDoc = {
  version: number;
  payload: Record<string, unknown>;
  updated_at: string | null;
  updated_by: string | null;
};

export type ProjectSummary = { id: string; title: string };

export type DebateMessage = {
  agent: string;
  kind: string;
  text: string;
  evidenceIds?: string[];
};

export type DebateResult = {
  messages: DebateMessage[];
  meta: {
    provider: string;
    model: string;
    prompt_version: string;
    latency_ms: number;
    messages: number;
  };
};

export type CritiqueItem = {
  cat: string;
  text: string;
  sug: string;
  evidenceIds: string[];
};

export type CritiqueResult = {
  items: CritiqueItem[];
  meta: {
    provider: string;
    model: string;
    prompt_version: string;
    latency_ms: number;
    items: number;
  };
};

export type CandidateItem = {
  type: string;
  text: string;
  vars: string[];
  evidenceIds: string[];
};

export type CandidateResult = {
  items: CandidateItem[];
  meta: {
    provider: string;
    model: string;
    prompt_version: string;
    latency_ms: number;
    items: number;
  };
};

export class StudioApiError extends Error {
  code: string;
  status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
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
  const isJson = (response.headers.get("content-type") ?? "").includes("application/json");
  if (!response.ok) {
    const body = isJson ? await response.json() : null;
    const error = body?.error ?? { code: "unknown", message: response.statusText };
    if (response.status === 401) {
      window.dispatchEvent(new Event("rihrp:unauthorized"));
    }
    throw new StudioApiError(response.status, error.code, error.message);
  }
  return (isJson ? await response.json() : await response.text()) as T;
}

export const studioHost = {
  async listProjects(signal?: AbortSignal): Promise<ProjectSummary[]> {
    const body = await request<{ projects: { id: string; title: string }[] }>("/api/projects", {
      signal,
    });
    return body.projects.map((project) => ({ id: project.id, title: project.title }));
  },

  async getDocument(id: string, signal?: AbortSignal): Promise<ResearchDoc> {
    return request<ResearchDoc>(`/api/projects/${encodeURIComponent(id)}/research`, { signal });
  },

  async saveDocument(
    id: string,
    expectedVersion: number,
    payload: unknown,
    signal?: AbortSignal,
  ): Promise<ResearchDoc> {
    return request<ResearchDoc>(`/api/projects/${encodeURIComponent(id)}/research`, {
      method: "PUT",
      body: JSON.stringify({ expected_version: expectedVersion, payload }),
      signal,
    });
  },

  async createProject(title: string, signal?: AbortSignal): Promise<ProjectSummary> {
    const body = await request<{ project: { id: string; title: string } }>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ title, summary: "" }),
      signal,
    });
    return { id: body.project.id, title: body.project.title };
  },

  async renameProject(id: string, title: string, signal?: AbortSignal): Promise<void> {
    await request(`/api/projects/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
      signal,
    });
  },

  async deleteProject(id: string, signal?: AbortSignal): Promise<void> {
    await request(`/api/projects/${encodeURIComponent(id)}`, { method: "DELETE", signal });
  },

  /** 03 討論の AI 支援（Phase 3 B PoC）。生成のみ・保存はしない。 */
  async generateDebate(id: string, signal?: AbortSignal): Promise<DebateResult> {
    return request<DebateResult>(`/api/projects/${encodeURIComponent(id)}/ai/debate`, {
      method: "POST",
      signal,
    });
  },

  /** 04 批判の AI 提案（Phase 3 C）。生成のみ・保存はしない。 */
  async generateCritiques(id: string, signal?: AbortSignal): Promise<CritiqueResult> {
    return request<CritiqueResult>(`/api/projects/${encodeURIComponent(id)}/ai/critiques`, {
      method: "POST",
      signal,
    });
  },

  /** 05 候補の AI 提案（Phase 3 C）。採点はしない。 */
  async generateCandidates(id: string, signal?: AbortSignal): Promise<CandidateResult> {
    return request<CandidateResult>(`/api/projects/${encodeURIComponent(id)}/ai/candidates`, {
      method: "POST",
      signal,
    });
  },
};
