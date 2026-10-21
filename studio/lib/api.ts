export type Freshness = {
  as_of_seq: number;
  latest_seq: number;
  pending: number;
  failed: number;
  is_current: boolean;
};

export type Fact = {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  status: string;
  confidence: number;
  valid_from: string | null;
  valid_to: string | null;
  recorded_at: string;
};

export type ScopeRow = { user_id: string; agent_id: string; namespace: string; applied_seq: number };

const TOKEN_KEY = "tensemem_token";
const USER_KEY = "tensemem_user";

export function getToken(): string {
  return typeof window === "undefined" ? "" : localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getUser(): string {
  return typeof window === "undefined" ? "studio-demo" : localStorage.getItem(USER_KEY) ?? "studio-demo";
}

export function setUser(user: string): void {
  localStorage.setItem(USER_KEY, user);
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("content-type", "application/json");
  const token = getToken();
  if (token) headers.set("authorization", `Bearer ${token}`);
  const response = await fetch(path, { ...init, headers });
  const raw = await response.text();
  let payload: (T & { error?: string }) | null = null;
  try {
    payload = raw ? (JSON.parse(raw) as T & { error?: string }) : null;
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(payload?.error ?? `${response.status} ${response.statusText}`);
  }
  return payload as T;
}

export const api = {
  scopes: () => req<{ scopes: ScopeRow[] }>("/v1/scopes"),
  stats: (user_id?: string) =>
    req<Record<string, unknown>>(`/v1/stats${user_id ? `?user_id=${encodeURIComponent(user_id)}` : ""}`),
  state: (user_id: string) =>
    req<{ values: Record<string, unknown>; facts: Fact[]; freshness: Freshness }>(
      `/v1/state?user_id=${encodeURIComponent(user_id)}`,
    ),
  history: (user_id: string, predicate = "") =>
    req<{ facts: Fact[]; freshness: Freshness }>(
      `/v1/history?user_id=${encodeURIComponent(user_id)}${predicate ? `&predicate=${encodeURIComponent(predicate)}` : ""}`,
    ),
  search: (user_id: string, query: string) =>
    req<{ hits: Array<Record<string, unknown>>; freshness: Freshness; debug: Array<Record<string, unknown>> }>(
      `/v1/search?user_id=${encodeURIComponent(user_id)}&query=${encodeURIComponent(query)}`,
    ),
  graph: (user_id: string) =>
    req<{ nodes: Array<Record<string, string>>; edges: Array<Record<string, string>> }>(
      `/v1/graph?user_id=${encodeURIComponent(user_id)}`,
    ),
  explain: (fact_id: string) => req<Record<string, unknown>>(`/v1/explain?fact_id=${encodeURIComponent(fact_id)}`),
  jobs: (user_id: string) =>
    req<{ jobs: Array<Record<string, unknown>> }>(`/v1/jobs?user_id=${encodeURIComponent(user_id)}`),
  retryJob: (id: string) =>
    req<Record<string, unknown>>("/v1/jobs:retry", { method: "POST", body: JSON.stringify({ id }) }),
  dismissJob: (id: string) =>
    req<Record<string, unknown>>("/v1/jobs:dismiss", { method: "POST", body: JSON.stringify({ id }) }),
  add: (user_id: string, text: string) =>
    req<Record<string, unknown>>("/v1/memories:add", { method: "POST", body: JSON.stringify({ user_id, text }) }),
  context: (user_id: string, query: string, include_history = false) =>
    req<Record<string, unknown>>("/v1/context", {
      method: "POST",
      body: JSON.stringify({ user_id, query, include_history }),
    }),
  correct: (fact_id: string, replacement?: string) =>
    req<Record<string, unknown>>("/v1/facts:correct", {
      method: "POST",
      body: JSON.stringify({ fact_id, replacement }),
    }),
  forget: (user_id: string) =>
    req<Record<string, unknown>>(`/v1/scopes/${encodeURIComponent(user_id)}`, { method: "DELETE" }),
  compare: (user_id: string, query: string, include_history = false) =>
    req<Record<string, unknown>>("/v1/insights/compare", {
      method: "POST",
      body: JSON.stringify({ user_id, query, include_history }),
    }),
  echo: (user_id: string, turns = 8) =>
    req<Record<string, unknown>>("/v1/insights/echo", { method: "POST", body: JSON.stringify({ user_id, turns }) }),
  actRisk: (user_id: string) =>
    req<Record<string, unknown>>(`/v1/insights/act-risk?user_id=${encodeURIComponent(user_id)}`),
  sample: () => req<Record<string, unknown>>("/v1/studio/sample", { method: "POST", body: "{}" }),
  keys: () => req<{ keys: Array<Record<string, unknown>> }>("/v1/ops/keys"),
  issueKey: (label: string) =>
    req<{ token: string; prefix: string }>("/v1/ops/keys", { method: "POST", body: JSON.stringify({ label }) }),
  revokeKey: (id: string) =>
    req<Record<string, unknown>>("/v1/ops/keys:revoke", { method: "POST", body: JSON.stringify({ id }) }),
  requests: () => req<{ requests: Array<Record<string, unknown>> }>("/v1/ops/requests"),
  provider: () =>
    req<{ llm: string; embedder: string; credentials?: Record<string, unknown> }>("/v1/ops/provider"),
  setProvider: (llm: string, embedder: string) =>
    req<Record<string, unknown>>("/v1/ops/provider", { method: "PUT", body: JSON.stringify({ llm, embedder }) }),
};
