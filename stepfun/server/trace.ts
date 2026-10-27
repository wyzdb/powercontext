import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";

export interface TraceEntry {
  sql: string;
  params?: unknown[];
  ms: number;
  rows?: number;
  error?: string;
}

const scope = new AsyncLocalStorage<string>();
const traces = new Map<string, TraceEntry[]>();
const MAX_TRACES = 200;
const MAX_ENTRIES = 40;

export function createTraceId(): string {
  return randomUUID();
}

export async function withTrace<T>(
  traceId: string,
  fn: () => Promise<T>,
): Promise<T> {
  traces.set(traceId, []);
  prune();
  return scope.run(traceId, fn);
}

export function recordTrace(entry: TraceEntry): void {
  const traceId = scope.getStore();
  if (!traceId) return;
  const entries = traces.get(traceId);
  if (!entries) return;
  entries.push(entry);
  if (entries.length > MAX_ENTRIES) entries.shift();
}

export function getTrace(traceId: string): TraceEntry[] {
  return traces.get(traceId) ?? [];
}

function prune(): void {
  if (traces.size <= MAX_TRACES) return;
  const overflow = traces.size - MAX_TRACES;
  let removed = 0;
  for (const key of traces.keys()) {
    traces.delete(key);
    if (++removed >= overflow) break;
  }
}
