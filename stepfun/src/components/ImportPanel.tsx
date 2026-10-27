import { useEffect, useRef, useState } from "react";
import type { KbRecord } from "../lib/api";
import { api } from "../lib/api";
import {
  buildChunks,
  parseJsonDocs,
  sha256,
  type Chunk,
  type SourceDoc,
} from "../lib/chunk";
import { useModel } from "../model/ModelContext";

type Stage =
  | "idle"
  | "chunking"
  | "loading-model"
  | "embedding"
  | "writing"
  | "refreshing"
  | "done"
  | "error";

interface Timings {
  chunk: number;
  embed: number;
  write: number;
  refresh: number;
  total: number;
}

const ZERO: Timings = { chunk: 0, embed: 0, write: 0, refresh: 0, total: 0 };

const STEPS: Array<{ key: Stage; label: string }> = [
  { key: "chunking", label: "解析与分块" },
  { key: "embedding", label: "本地向量化" },
  { key: "writing", label: "写入 seekdb" },
  { key: "refreshing", label: "刷新索引" },
];

function ms(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${Math.round(value)} ms`;
}

function stageIndex(stage: Stage): number {
  if (stage === "done") return 4;
  if (stage === "chunking") return 0;
  if (stage === "loading-model" || stage === "embedding") return 1;
  if (stage === "writing") return 2;
  if (stage === "refreshing") return 3;
  return -1;
}

export default function ImportPanel({
  kb,
  onImported,
}: {
  kb: KbRecord | null;
  onImported: () => Promise<void>;
}) {
  const model = useModel();
  const [docs, setDocs] = useState<SourceDoc[]>([]);
  const [stage, setStage] = useState<Stage>("idle");
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState(0);
  const [timings, setTimings] = useState<Timings>(ZERO);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [drag, setDrag] = useState(false);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const cancelRef = useRef(false);

  const dtypeMismatch =
    kb !== null && model.choice !== null && model.choice.dtype !== kb.dtype;

  // Staged docs and timings belong to the selected collection. Reset when the
  // user switches KB, otherwise an import started on A can be written into B.
  useEffect(() => {
    cancelRef.current = true;
    setDocs([]);
    setStage("idle");
    setDone(0);
    setTotal(0);
    setTimings(ZERO);
    setError(null);
    setCancelled(false);
  }, [kb?.id]);

  const parseFiles = async (files: FileList | File[]) => {
    setLoadingFiles(true);
    setError(null);
    try {
      const incoming: SourceDoc[] = [];
      for (const file of Array.from(files)) {
        const raw = await file.text();
        if (file.name.toLowerCase().endsWith(".json")) {
          incoming.push(...parseJsonDocs(raw, file.name));
        } else {
          const digest = await sha256(raw);
          incoming.push({
            id: `${file.name}-${digest.slice(0, 8)}`,
            title: file.name.replace(/\.[^.]+$/, ""),
            text: raw,
            source: file.name,
          });
        }
      }
      setDocs((previous) => [...previous, ...incoming]);
    } catch (parseError) {
      setError(String(parseError));
    } finally {
      setLoadingFiles(false);
    }
  };

  const loadSample = async () => {
    setLoadingFiles(true);
    setError(null);
    try {
      const response = await fetch("/corpus/sample.json");
      if (!response.ok) throw new Error(`示例语料加载失败：HTTP ${response.status}`);
      const list = (await response.json()) as SourceDoc[];
      setDocs(list);
    } catch (sampleError) {
      setError(String(sampleError));
    } finally {
      setLoadingFiles(false);
    }
  };

  const start = async () => {
    if (!kb || docs.length === 0 || running) return;
    if (dtypeMismatch) {
      setError(
        `当前知识库由 ${kb.dtype} 构建，当前编码器是 ${model.choice?.dtype}。` +
          "两种精度的向量不能混写；请新建知识库，或切回相同精度。",
      );
      setStage("error");
      return;
    }
    setRunning(true);
    cancelRef.current = false;
    setCancelled(false);
    setError(null);
    setDone(0);
    setTotal(0);
    setStage("chunking");
    const startedAt = performance.now();

    try {
      const chunks: Chunk[] = [];
      for (const doc of docs) {
        chunks.push(...(await buildChunks(doc, { size: 300, overlap: 50 })));
      }
      if (chunks.length === 0) throw new Error("没有解析出任何文本片段");

      // Length bucketing: sort by character length before batching so each
      // batch pads to a shorter max length. IDs/metadata are unaffected.
      const ordered = [...chunks].sort((a, b) => a.text.length - b.text.length);
      setTotal(ordered.length);
      const chunkMs = performance.now() - startedAt;

      setStage("loading-model");
      const choice = await model.ensure();

      let embedMs = 0;
      let writeMs = 0;
      const batchSize = 16;

      for (let offset = 0; offset < ordered.length; offset += batchSize) {
        if (cancelRef.current) break;
        const batch = ordered.slice(offset, offset + batchSize);

        setStage("embedding");
        const embedStarted = performance.now();
        const { vectors } = await model.embedDocs(
          batch.map((chunk) => chunk.text),
          batchSize,
        );
        embedMs += performance.now() - embedStarted;

        setStage("writing");
        const writeStarted = performance.now();
        await api.addDocs(
          kb.id,
          batch.map((chunk, index) => ({
            id: chunk.id,
            text: chunk.text,
            metadata: chunk.metadata,
            embedding: vectors[index],
          })),
          choice.dtype as "fp32" | "int8" | "fp16",
        );
        writeMs += performance.now() - writeStarted;

        setDone(Math.min(offset + batch.length, ordered.length));
        await new Promise((resolve) => window.setTimeout(resolve, 0));
      }

      const wasCancelled = cancelRef.current;
      setCancelled(wasCancelled);

      setStage("refreshing");
      const refreshStarted = performance.now();
      await api.refresh(kb.id);
      const refreshMs = performance.now() - refreshStarted;

      setTimings({
        chunk: chunkMs,
        embed: embedMs,
        write: writeMs,
        refresh: refreshMs,
        total: performance.now() - startedAt,
      });
      setStage("done");
      await onImported();
    } catch (importError) {
      setError(String(importError));
      setStage("error");
    } finally {
      setRunning(false);
    }
  };

  const totalChars = docs.reduce((sum, doc) => sum + doc.text.length, 0);
  const progress = total > 0 ? Math.min(100, (done / total) * 100) : 0;
  const activeStep = stageIndex(stage);

  if (!kb) {
    return (
      <div className="card px-6 py-10 text-center">
        <h2 className="serif text-xl">先建一个知识库</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[var(--color-muted)]">
          知识库对应 seekdb 里的一个 collection。左侧点“+”，输入名称即可创建；
          集合会同时建立 HNSW 向量索引和 IK 全文索引。
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
            导入 · {kb.name}
          </p>
          <h2 className="serif mt-1 text-2xl">把文档变成可检索的片段</h2>
          <p className="mt-1 text-[12.5px] text-[var(--color-muted)]">
            分块 300 字 / 重叠 50 字；向量在浏览器本地计算，原文、向量和元数据写入 seekdb。
          </p>
        </div>
        <div className="mono text-[11px] text-[var(--color-muted)]">
          collection {kb.id} · {kb.dtype} · {kb.dim}d
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
        <section className="card p-5">
          <div
            className="dropzone cursor-pointer px-6 py-8 text-center"
            data-active={drag}
            onClick={() => inputRef.current?.click()}
            onDragOver={(event) => {
              event.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDrag(false);
              if (event.dataTransfer.files.length > 0) {
                void parseFiles(event.dataTransfer.files);
              }
            }}
          >
            <p className="serif text-lg">拖入 .txt / .md / .json</p>
            <p className="mt-1 text-xs text-[var(--color-muted)]">
              或点击选择文件；JSON 支持数组或 {"{ documents: [...] }"} 结构
            </p>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".txt,.md,.markdown,.json"
              className="hidden"
              onChange={(event) => {
                if (event.target.files?.length) void parseFiles(event.target.files);
                event.target.value = "";
              }}
            />
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              className="btn btn-ghost text-xs"
              onClick={loadSample}
              disabled={loadingFiles || running}
            >
              加载示例语料（20 篇）
            </button>
            <button
              className="btn btn-ghost text-xs"
              onClick={() => {
                setDocs([]);
                setStage("idle");
                setDone(0);
                setTotal(0);
                setError(null);
                setCancelled(false);
              }}
              disabled={running || docs.length === 0}
            >
              清空
            </button>
            <span className="mono ml-auto text-[11px] text-[var(--color-muted)]">
              {docs.length} 篇 · {totalChars.toLocaleString()} 字
            </span>
          </div>

          {docs.length > 0 && (
            <ul className="mt-4 max-h-56 space-y-1 overflow-y-auto border-t border-[var(--color-line)] pt-3 text-[11.5px]">
              {docs.slice(0, 8).map((doc) => (
                <li key={doc.id} className="flex items-baseline justify-between gap-3">
                  <span className="truncate">{doc.title}</span>
                  <span className="mono shrink-0 text-[var(--color-muted)]">
                    {doc.text.length} 字
                  </span>
                </li>
              ))}
              {docs.length > 8 && (
                <li className="text-[var(--color-muted)]">
                  还有 {docs.length - 8} 篇…
                </li>
              )}
            </ul>
          )}
        </section>

        <section className="card flex flex-col p-5">
          <h3 className="text-sm font-semibold">导入</h3>
          <p className="mt-1 text-[11.5px] leading-5 text-[var(--color-muted)]">
            导入按 16 条一批：先 embedding，再写入，最后统一刷新 HNSW 索引。
            刷新前新片段可能查不到，这是 seekdb 的异步索引语义。
          </p>

          {dtypeMismatch && (
            <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] leading-5 text-[var(--color-warn)]">
              知识库由 <span className="mono">{kb.dtype}</span> 构建，当前编码器是{" "}
              <span className="mono">{model.choice?.dtype}</span>。
              两种精度的向量不能混写，导入已禁用。请新建一个同精度知识库，或切回{" "}
              <span className="mono">{kb.dtype}</span>。
            </p>
          )}

          <button
            className="btn btn-primary mt-4 justify-center"
            onClick={start}
            disabled={running || docs.length === 0 || dtypeMismatch}
          >
            {running ? "导入中…" : "开始导入"}
          </button>
          {running && (
            <button
              className="btn btn-ghost mt-2 justify-center text-xs"
              onClick={() => {
                cancelRef.current = true;
              }}
            >
              取消（保留已写入部分）
            </button>
          )}

          <div className="mt-5">
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${progress}%` }} />
            </div>
            <div className="mono mt-1 flex justify-between text-[10.5px] text-[var(--color-muted)]">
              <span>
                {stage === "loading-model"
                  ? `模型加载 ${model.progress}`
                  : stage === "done"
                    ? cancelled
                      ? "已取消（保留已写入部分）"
                      : "完成"
                    : stage === "error"
                      ? "失败"
                      : stage === "idle"
                        ? "等待"
                        : `${done}/${total || "?"}`}
              </span>
              <span>{Math.round(progress)}%</span>
            </div>
          </div>

          <ol className="mt-4 space-y-1.5 text-[11.5px]">
            {STEPS.map((step, index) => {
              const state =
                activeStep > index
                  ? "done"
                  : activeStep === index
                    ? "active"
                    : "idle";
              return (
                <li
                  key={step.key}
                  className={`flex items-center gap-2 ${
                    state === "idle" ? "text-[var(--color-muted)]" : ""
                  }`}
                >
                  <span
                    className={`inline-flex h-4 w-4 items-center justify-center rounded-full border text-[9px] ${
                      state === "done"
                        ? "border-[var(--color-accent)] bg-[var(--color-accent)] text-white"
                        : state === "active"
                          ? "border-[var(--color-accent)] text-[var(--color-accent)]"
                          : "border-[var(--color-line)]"
                    }`}
                  >
                    {state === "done" ? "✓" : index + 1}
                  </span>
                  {step.label}
                  {state === "active" && (
                    <span className="ml-auto text-[10px] text-[var(--color-muted)]">
                      进行中
                    </span>
                  )}
                </li>
              );
            })}
          </ol>

          {stage === "done" && (
            <dl className="mono mt-4 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-[var(--color-line)] pt-3 text-[10.5px]">
              <dt className="text-[var(--color-muted)]">分块</dt>
              <dd className="text-right">{ms(timings.chunk)}</dd>
              <dt className="text-[var(--color-muted)]">向量化</dt>
              <dd className="text-right">{ms(timings.embed)}</dd>
              <dt className="text-[var(--color-muted)]">写入</dt>
              <dd className="text-right">{ms(timings.write)}</dd>
              <dt className="text-[var(--color-muted)]">刷新</dt>
              <dd className="text-right">{ms(timings.refresh)}</dd>
              <dt className="font-semibold">合计</dt>
              <dd className="text-right font-semibold">{ms(timings.total)}</dd>
            </dl>
          )}

          {error && (
            <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-[11px] leading-5 text-[var(--color-danger)]">
              {error}
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
