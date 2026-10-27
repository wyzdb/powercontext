import { useEffect, useState, type FormEvent } from "react";
import type { KbRecord, SearchResponse } from "../lib/api";
import { api } from "../lib/api";
import { useModel } from "../model/ModelContext";
import ResultCard from "./ResultCard";
import TraceDrawer from "./TraceDrawer";

const EXAMPLES = [
  "为什么小批量 GPU 推理不一定快？",
  "都江堰 鱼嘴 作用",
  "HNSW 的 m 参数",
  "怎样避免马拉松撞墙",
];

interface Timings {
  embed: number;
  db: number;
  total: number;
}

export default function SearchPanel({ kb }: { kb: KbRecord | null }) {
  const model = useModel();
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(10);
  const [searching, setSearching] = useState(false);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [timings, setTimings] = useState<Timings | null>(null);
  const [traceId, setTraceId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setResponse(null);
    setTimings(null);
    setTraceId(null);
    setError(null);
  }, [kb?.id]);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!kb || !query.trim() || searching) return;
    setSearching(true);
    setError(null);
    setTraceId(null);
    const startedAt = performance.now();
    try {
      const embedded = await model.embedQuery(query.trim());
      const result = await api.search(kb.id, {
        query: query.trim(),
        embedding: embedded.vector,
        topK,
        rankConstant: 60,
        rankWindowSize: 50,
      });
      setResponse(result);
      setTimings({
        embed: embedded.ms,
        db: result.dbMs,
        total: performance.now() - startedAt,
      });
    } catch (searchError) {
      setError(String(searchError));
    } finally {
      setSearching(false);
    }
  };

  if (!kb) {
    return (
      <div className="card px-6 py-10 text-center">
        <h2 className="serif text-xl">还没有可检索的知识库</h2>
        <p className="mt-2 text-sm text-[var(--color-muted)]">
          先在左侧创建一个，再导入几篇文档。
        </p>
      </div>
    );
  }

  const dtypeMismatch =
    model.choice !== null && model.choice.dtype !== kb.dtype;

  return (
    <div className="space-y-5">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
          检索 · {kb.name}
        </p>
        <h2 className="serif mt-1 text-2xl">问一个具体的问题</h2>
        <p className="mt-1 text-[12.5px] text-[var(--color-muted)]">
          查询向量在浏览器本地生成；seekdb 用一条{" "}
          <span className="mono">DBMS_HYBRID_SEARCH</span> SQL 完成全文 + 向量 +
          RRF。
        </p>
      </div>

      <form className="card p-4" onSubmit={submit}>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="例如：为什么小批量 GPU 推理不一定快？"
            className="min-w-0 flex-1 rounded-lg border border-[var(--color-line)] bg-white px-4 py-3 text-[14px] outline-none focus:border-[var(--color-accent)]"
          />
          <div className="flex items-center gap-2">
            <select
              value={topK}
              onChange={(event) => setTopK(Number(event.target.value))}
              className="rounded-lg border border-[var(--color-line)] bg-white px-2 py-3 text-xs outline-none"
              title="返回条数"
            >
              {[5, 10, 20].map((value) => (
                <option key={value} value={value}>
                  top {value}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className="btn btn-primary px-5 py-3"
              disabled={searching || !query.trim()}
            >
              {searching ? "检索中…" : "检索"}
            </button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[10.5px] text-[var(--color-muted)]">试试：</span>
          {EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              className="rounded-full border border-[var(--color-line)] px-2.5 py-1 text-[10.5px] text-[var(--color-muted)] hover:border-[var(--color-accent)] hover:text-[var(--color-accent)]"
              onClick={() => setQuery(example)}
            >
              {example}
            </button>
          ))}
        </div>
      </form>

      {dtypeMismatch && (
        <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11.5px] leading-5 text-[var(--color-warn)]">
          这个知识库由 <span className="mono">{kb.dtype}</span> 编码器构建，当前查询编码器是{" "}
          <span className="mono">{model.choice?.dtype}</span>。FP16 与 FP32
          的向量几乎一致，INT8 则会产生可测的质量差异；做质量对比时请在相同
          dtype 下重建知识库。
        </p>
      )}

      {model.status === "loading" && (
        <p className="text-[11px] text-[var(--color-muted)]">
          模型加载中：{model.progress || "初始化 WebGPU/WASM"}。首次检索会等待模型就绪。
        </p>
      )}

      {error && (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-[11.5px] leading-5 text-[var(--color-danger)]">
          {error}
        </p>
      )}

      {response && (
        <section className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold">
              {response.hits.length} 条结果
              <span className="ml-2 font-normal text-[var(--color-muted)]">
                RRF k=60 · window 50
              </span>
            </h3>
            <div className="mono flex items-center gap-4 text-[11px] text-[var(--color-muted)]">
              {timings && (
                <>
                  <span>embed {timings.embed.toFixed(1)} ms</span>
                  <span>seekdb {timings.db.toFixed(1)} ms</span>
                  <span className="text-[var(--color-ink)]">
                    端到端 {timings.total.toFixed(1)} ms
                  </span>
                </>
              )}
              <button
                className="btn btn-ghost py-1 text-[10.5px]"
                onClick={() => setTraceId(response.traceId)}
              >
                查看 SQL
              </button>
            </div>
          </div>

          {response.warning && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-[var(--color-warn)]">
              {response.warning}
            </p>
          )}

          {response.hits.length === 0 ? (
            <p className="card px-5 py-8 text-center text-sm text-[var(--color-muted)]">
              没有命中。换一种问法，或确认文档已经刷新完成。
            </p>
          ) : (
            <div className="space-y-2.5">
              {response.hits.map((hit) => (
                <ResultCard key={hit.id} hit={hit} query={query} />
              ))}
            </div>
          )}
        </section>
      )}

      <TraceDrawer traceId={traceId} onClose={() => setTraceId(null)} />
    </div>
  );
}
