import { useCallback, useState } from "react";
import { api } from "../lib/api";
import { buildChunks, type SourceDoc } from "../lib/chunk";
import {
  disposeEmbedder,
  embed,
  loadEmbedder,
  MODEL_ID,
  QUERY_INSTRUCTION,
  type BackendDevice,
  type Dtype,
} from "../lib/embedder";
import { probeWebGPU } from "../lib/gpu";
import {
  jaccardAtK,
  kendallTau,
  mean,
  median,
  mrrAtK,
  ndcgAtK,
  p95,
  recallAtK,
  type Qrels,
} from "../lib/metrics";

declare global {
  interface Window {
    __BENCH_RESULT__?: unknown;
  }
}

interface BenchQuery {
  id: string;
  query: string;
  type: string;
  qrels: Qrels;
}

interface QueryResult {
  id: string;
  query: string;
  ranked: string[];
  queryEmbedMs: number;
  dbMs: number;
  totalMs: number;
  recall5: number;
  ndcg5: number;
  mrr10: number;
  jaccard10VsBaseline?: number;
  kendallVsBaseline?: number;
}

interface ConfigResult {
  id: string;
  device: BackendDevice;
  dtype: Dtype;
  kbId: string;
  loadMs: number;
  docEmbedMs: number;
  docsPerSecond: number;
  writeMs: number;
  refreshMs: number;
  queryEmbedMsMedian: number;
  queryEmbedMsP95: number;
  dbMsMedian: number;
  dbMsP95: number;
  totalMsMedian: number;
  totalMsP95: number;
  totalMsMax: number;
  warmupMs: number;
  firstAnswerMs: number;
  recall5: number;
  ndcg5: number;
  mrr10: number;
  jaccard10VsBaseline?: number;
  kendallVsBaseline?: number;
  perQuery: QueryResult[];
  error?: string;
}

const CONFIGS: Array<{ id: string; device: BackendDevice; dtype: Dtype }> = [
  { id: "fp32-wasm", device: "wasm", dtype: "fp32" },
  { id: "int8-wasm", device: "wasm", dtype: "int8" },
  { id: "fp32-webgpu", device: "webgpu", dtype: "fp32" },
  { id: "fp16-webgpu", device: "webgpu", dtype: "fp16" },
];

export default function BenchRun() {
  const [status, setStatus] = useState("等待运行");
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<ConfigResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  const runAll = useCallback(async () => {
    setRunning(true);
    setError(null);
    setResults([]);
    const collected: ConfigResult[] = [];
    let failure: string | null = null;

    try {
      setStatus("读取语料与查询集…");
      const corpus = (await fetch("/corpus/sample.json").then((response) =>
        response.json(),
      )) as SourceDoc[];
      const queries = (await fetch("/bench/queries.json").then((response) =>
        response.json(),
      )) as BenchQuery[];
      const probe = await probeWebGPU();

      const chunks = [];
      for (const doc of corpus) {
        chunks.push(...(await buildChunks(doc, { size: 300, overlap: 50 })));
      }

      const configs = CONFIGS.filter(
        (config) => config.device !== "webgpu" || probe.ok,
      );

      for (const config of configs) {
        setStatus(`运行 ${config.id}（${chunks.length} 个片段 / ${queries.length} 条查询）…`);
        const result = await runConfig(config, chunks, queries);
        collected.push(result);
        setResults([...collected]);
      }

      const baseline = collected.find((item) => item.id === "fp32-wasm");
      if (baseline) {
        for (const result of collected) {
          if (result.id === "fp32-wasm") {
            result.jaccard10VsBaseline = undefined;
            result.kendallVsBaseline = undefined;
            continue;
          }
          const pairs = result.perQuery
            .map((query) => {
              const base = baseline.perQuery.find((item) => item.id === query.id);
              if (!base) return null;
              return {
                jaccard: jaccardAtK(base.ranked, query.ranked, 10),
                kendall: kendallTau(base.ranked, query.ranked),
              };
            })
            .filter(
              (item): item is { jaccard: number; kendall: number } =>
                item !== null &&
                Number.isFinite(item.jaccard) &&
                Number.isFinite(item.kendall),
            );
          result.jaccard10VsBaseline = mean(pairs.map((item) => item.jaccard));
          result.kendallVsBaseline = mean(pairs.map((item) => item.kendall));
          for (const query of result.perQuery) {
            const base = baseline.perQuery.find((item) => item.id === query.id);
            if (!base) continue;
            query.jaccard10VsBaseline = jaccardAtK(base.ranked, query.ranked, 10);
            query.kendallVsBaseline = kendallTau(base.ranked, query.ranked);
          }
        }
      }

      window.__BENCH_RESULT__ = {
        results: collected,
        probe,
        corpusDocs: corpus.length,
        chunks: chunks.length,
        queries: queries.length,
        userAgent: navigator.userAgent,
        at: new Date().toISOString(),
      };
      setStatus("完成");
    } catch (runError) {
      failure = String(runError);
      setError(failure);
      setStatus("失败");
    } finally {
      setRunning(false);
      if (window.__BENCH_RESULT__ === undefined) {
        window.__BENCH_RESULT__ = { results: collected, error: failure };
      }
    }
  }, []);

  return (
    <main className="mx-auto max-w-6xl px-8 py-8">
      <header>
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
          Phase 4 · retrieval benchmark
        </p>
        <h1 className="serif mt-1 text-2xl">量化与后端的检索质量/延迟对照</h1>
        <p className="mt-2 max-w-3xl text-[13px] leading-6 text-[var(--color-muted)]">
          对同一份语料、同一组 20 条查询，分别用 fp32/wasm、int8/wasm、fp32/webgpu、
          fp16/webgpu 建库、刷新、检索，计算 Recall@5 / nDCG@5 / MRR@10，并给出相对
          FP32/WASM 的 Top-10 Jaccard 与 Kendall τ。每个配置使用独立 collection；
          warm-up 不计入文档/查询计时。
        </p>
      </header>

      <section className="mt-5 flex items-center gap-4">
        <button className="btn btn-primary" onClick={runAll} disabled={running}>
          {running ? "运行中…" : "运行全部配置"}
        </button>
        <span className="text-[12px] text-[var(--color-muted)]">{status}</span>
      </section>

      {error && (
        <p className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-[12px] text-[var(--color-danger)]">
          {error}
        </p>
      )}

      {results.length > 0 && (
        <section className="card mt-5 overflow-x-auto">
          <table className="w-full min-w-[1180px] text-left text-[12px]">
            <thead className="bg-[#f7f4ec] text-[10.5px] uppercase tracking-wide text-[var(--color-muted)]">
              <tr>
                <th className="px-4 py-2 font-medium">配置</th>
                <th className="px-4 py-2 text-right font-medium">加载 ms</th>
                <th className="px-4 py-2 text-right font-medium">预热 ms</th>
                <th className="px-4 py-2 text-right font-medium">首答 ms</th>
                <th className="px-4 py-2 text-right font-medium">docs/s</th>
                <th className="px-4 py-2 text-right font-medium">刷新 ms</th>
                <th className="px-4 py-2 text-right font-medium">查询嵌入 p50</th>
                <th className="px-4 py-2 text-right font-medium">seekdb p50</th>
                <th className="px-4 py-2 text-right font-medium">端到端 p50</th>
                <th className="px-4 py-2 text-right font-medium">p95</th>
                <th className="px-4 py-2 text-right font-medium">max</th>
                <th className="px-4 py-2 text-right font-medium">Recall@5</th>
                <th className="px-4 py-2 text-right font-medium">nDCG@5</th>
                <th className="px-4 py-2 text-right font-medium">MRR@10</th>
                <th className="px-4 py-2 text-right font-medium">Jaccard@10</th>
                <th className="px-4 py-2 text-right font-medium">Kendall τ</th>
              </tr>
            </thead>
            <tbody>
              {results.map((row) => (
                <tr key={row.id} className="border-t border-[var(--color-line)]">
                  <td className="px-4 py-2 font-medium">{row.id}</td>
                  <td className="mono px-4 py-2 text-right">{Math.round(row.loadMs)}</td>
                  <td className="mono px-4 py-2 text-right">{Math.round(row.warmupMs)}</td>
                  <td className="mono px-4 py-2 text-right">{Math.round(row.firstAnswerMs)}</td>
                  <td className="mono px-4 py-2 text-right">{row.docsPerSecond.toFixed(1)}</td>
                  <td className="mono px-4 py-2 text-right">{Math.round(row.refreshMs)}</td>
                  <td className="mono px-4 py-2 text-right">{row.queryEmbedMsMedian.toFixed(1)}</td>
                  <td className="mono px-4 py-2 text-right">{row.dbMsMedian.toFixed(1)}</td>
                  <td className="mono px-4 py-2 text-right">{row.totalMsMedian.toFixed(1)}</td>
                  <td className="mono px-4 py-2 text-right">{row.totalMsP95.toFixed(1)}</td>
                  <td className="mono px-4 py-2 text-right">{row.totalMsMax.toFixed(1)}</td>
                  <td className="mono px-4 py-2 text-right">{row.recall5.toFixed(3)}</td>
                  <td className="mono px-4 py-2 text-right">{row.ndcg5.toFixed(3)}</td>
                  <td className="mono px-4 py-2 text-right">{row.mrr10.toFixed(3)}</td>
                  <td className="mono px-4 py-2 text-right">
                    {row.jaccard10VsBaseline?.toFixed(3) ?? "基线"}
                  </td>
                  <td className="mono px-4 py-2 text-right">
                    {row.kendallVsBaseline?.toFixed(3) ?? "基线"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="card mt-5 px-5 py-4">
        <h2 className="text-sm font-semibold">原始 JSON</h2>
        <pre className="mt-2 max-h-80 overflow-auto rounded-lg bg-[#171b19] p-3 text-[10px] leading-4 text-[#d9e6df]">
          {JSON.stringify(results, null, 2)}
        </pre>
      </section>
    </main>
  );
}

async function runConfig(
  config: { id: string; device: BackendDevice; dtype: Dtype },
  chunks: Array<{ id: string; text: string; metadata: Record<string, unknown> }>,
  queries: BenchQuery[],
): Promise<ConfigResult> {
  const kb = await api.createKb({
    name: `bench-${config.id}-${Date.now()}`,
    modelId: MODEL_ID,
    dim: 512,
    dtype: config.dtype as "fp32" | "int8" | "fp16",
  });

  try {
    const loaded = await loadEmbedder({
      device: config.device,
      dtype: config.dtype,
    });

    // Warm-up is outside every timed window. WebGPU shader compilation and the
    // first allocation otherwise land inside the first document batch or the
    // first query, which is exactly the number this benchmark must not inflate.
    const warmupStarted = performance.now();
    await embed(["warm-up"], { batchSize: 1 });
    const warmupMs = performance.now() - warmupStarted;

    const ordered = [...chunks].sort((a, b) => a.text.length - b.text.length);

    const embedStarted = performance.now();
    const vectors: number[][] = [];
    const batchSize = 16;
    for (let offset = 0; offset < ordered.length; offset += batchSize) {
      const batch = ordered.slice(offset, offset + batchSize);
      const result = await embed(
        batch.map((chunk) => chunk.text),
        { batchSize },
      );
      vectors.push(...result.vectors);
    }
    const docEmbedMs = performance.now() - embedStarted;

    const writeStarted = performance.now();
    for (let offset = 0; offset < ordered.length; offset += batchSize) {
      const batch = ordered.slice(offset, offset + batchSize);
      await api.addDocs(
        kb.id,
        batch.map((chunk, index) => ({
          id: chunk.id,
          text: chunk.text,
          metadata: chunk.metadata,
          embedding: vectors[offset + index],
        })),
        config.dtype as "fp32" | "int8" | "fp16",
      );
    }
    const writeMs = performance.now() - writeStarted;

    const refreshStarted = performance.now();
    await api.refresh(kb.id);
    const refreshMs = performance.now() - refreshStarted;

    const perQuery: QueryResult[] = [];
    for (const query of queries) {
      const started = performance.now();
      const queryVector = await embed([`${QUERY_INSTRUCTION}${query.query}`], {
        batchSize: 1,
      });
      const queryEmbedMs = queryVector.ms;
      const searchResult = await api.search(kb.id, {
        query: query.query,
        embedding: queryVector.vectors[0],
        topK: 10,
      });
      const totalMs = performance.now() - started;
      const ranked = searchResult.hits
        .map((hit) => String(hit.metadata?.docId ?? ""))
        .filter(Boolean);

      perQuery.push({
        id: query.id,
        query: query.query,
        ranked,
        queryEmbedMs,
        dbMs: searchResult.dbMs,
        totalMs,
        recall5: recallAtK(ranked, query.qrels, 5),
        ndcg5: ndcgAtK(ranked, query.qrels, 5),
        mrr10: mrrAtK(ranked, query.qrels, 10),
      });
    }

    return {
      id: config.id,
      device: config.device,
      dtype: config.dtype,
      kbId: kb.id,
      loadMs: loaded.loadMs,
      docEmbedMs,
      docsPerSecond: ordered.length / (docEmbedMs / 1000),
      writeMs,
      refreshMs,
      warmupMs,
      firstAnswerMs:
        loaded.loadMs + warmupMs + (perQuery[0]?.totalMs ?? 0),
      queryEmbedMsMedian: median(perQuery.map((item) => item.queryEmbedMs)),
      queryEmbedMsP95: p95(perQuery.map((item) => item.queryEmbedMs)),
      dbMsMedian: median(perQuery.map((item) => item.dbMs)),
      dbMsP95: p95(perQuery.map((item) => item.dbMs)),
      totalMsMedian: median(perQuery.map((item) => item.totalMs)),
      totalMsP95: p95(perQuery.map((item) => item.totalMs)),
      totalMsMax: Math.max(...perQuery.map((item) => item.totalMs)),
      recall5: mean(perQuery.map((item) => item.recall5)),
      ndcg5: mean(perQuery.map((item) => item.ndcg5)),
      mrr10: mean(perQuery.map((item) => item.mrr10)),
      perQuery,
    };
  } finally {
    await api.deleteKb(kb.id).catch(() => undefined);
    await disposeEmbedder();
  }
}
