export type Dtype = "fp32" | "int8" | "fp16";

export interface KbRecord {
  id: string;
  name: string;
  modelId: string;
  dim: number;
  dtype: Dtype;
  createdAt: string;
  count: number;
  missing?: boolean;
}

export interface Health {
  ok: boolean;
  mode: string;
  database: string;
  target: string;
  version?: string;
  error?: string;
  lastError?: string | null;
  hints?: string[];
  connectMs?: number;
}

export interface SearchHit {
  id: string;
  text: string;
  metadata: Record<string, unknown> | null;
  score: number;
  rank: number;
}

export interface SearchResponse {
  hits: SearchHit[];
  dbMs: number;
  traceId: string;
  degraded?: "vector-only";
  warning?: string;
}

export interface TraceEntry {
  sql: string;
  params?: unknown[];
  ms: number;
  rows?: number;
  error?: string;
}

export interface DocPayload {
  id: string;
  text: string;
  metadata?: Record<string, unknown>;
  embedding: number[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const text = await response.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!response.ok) {
    const message =
      data && typeof data === "object" && "message" in data
        ? String((data as { message: unknown }).message)
        : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return data as T;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<Health>("/api/health"),
  listKbs: () => request<{ kbs: KbRecord[] }>("/api/kbs"),
  createKb: (input: {
    name: string;
    modelId: string;
    dim: number;
    dtype: Dtype;
  }) => request<KbRecord>("/api/kbs", json(input)),
  deleteKb: (id: string) =>
    request<{ ok: boolean }>(`/api/kbs/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  addDocs: (id: string, docs: DocPayload[]) =>
    request<{ inserted: number; ms: number }>(
      `/api/kbs/${encodeURIComponent(id)}/docs`,
      json({ docs }),
    ),
  refresh: (id: string) =>
    request<{ ms: number; count: number }>(
      `/api/kbs/${encodeURIComponent(id)}/refresh`,
      json({}),
    ),
  search: (
    id: string,
    input: {
      query: string;
      embedding: number[];
      topK?: number;
      rankConstant?: number;
      rankWindowSize?: number;
    },
  ) =>
    request<SearchResponse>(
      `/api/kbs/${encodeURIComponent(id)}/search`,
      json(input),
    ),
  trace: (id: string) =>
    request<{ traceId: string; entries: TraceEntry[] }>(
      `/api/trace/${encodeURIComponent(id)}`,
    ),
  ddl: (id: string) =>
    request<{
      physicalTable: string;
      createTable: string;
      createManifest: string;
      indexes: Record<string, unknown>[];
    }>(`/api/kbs/${encodeURIComponent(id)}/ddl`),
};
