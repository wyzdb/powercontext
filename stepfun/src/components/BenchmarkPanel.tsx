import { useEffect, useState } from "react";

interface SpikeRow {
  device: string;
  dtype: string;
  loadMs?: number;
  queryMs?: number;
  batchSweep?: Array<{ batchSize: number; ms: number; perTextMs: number }>;
  cosineVsFp32?: number[];
  error?: string;
}

interface SpikePayload {
  result?: {
    gpu?: { ok: boolean; reason?: string };
    rows?: SpikeRow[];
    userAgent?: string;
    at?: string;
  };
}

interface BenchConfigResult {
  id: string;
  device: string;
  dtype: string;
  loadMs: number;
  warmupMs?: number;
  firstAnswerMs?: number;
  docsPerSecond: number;
  refreshMs: number;
  queryEmbedMsMedian: number;
  dbMsMedian: number;
  totalMsMedian: number;
  totalMsP95: number;
  totalMsMax?: number;
  recall5: number;
  ndcg5: number;
  mrr10: number;
  jaccard10VsBaseline?: number;
  kendallVsBaseline?: number;
  error?: string;
}

interface Phase4Payload {
  result?: {
    results?: BenchConfigResult[];
    corpusDocs?: number;
    queries?: number;
    at?: string;
    probe?: { ok: boolean; reason?: string };
  };
}

const MODEL_SIZES = [
  { name: "FP32", file: "model.onnx", mib: 90.46, ratio: "1.00×" },
  { name: "FP16", file: "model_fp16.onnx", mib: 45.3, ratio: "2.00×" },
  { name: "INT8", file: "model_int8.onnx", mib: 22.8, ratio: "3.97×" },
];

function num(value: number | undefined, digits = 1): string {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

export default function BenchmarkPanel() {
  const [spike, setSpike] = useState<SpikePayload | null>(null);
  const [phase4, setPhase4] = useState<Phase4Payload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/bench/phase2.json")
      .then((response) => (response.ok ? response.json() : null))
      .then((data: SpikePayload | null) => setSpike(data))
      .catch((loadError) => setError(String(loadError)));
    fetch("/bench/phase4.json")
      .then((response) => (response.ok ? response.json() : null))
      .then((data: Phase4Payload | null) => setPhase4(data))
      .catch(() => undefined);
  }, []);

  const rows = spike?.result?.rows ?? [];
  const configs = phase4?.result?.results ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
            基准 · 实测数据
          </p>
          <h2 className="serif mt-1 text-2xl">先看数字，再谈优化</h2>
          <p className="mt-1 max-w-3xl text-[12.5px] leading-6 text-[var(--color-muted)]">
            语料 20 篇 / 20 个 chunk，查询 20 条，qrels 为作者标注的 3 级相关性。
            每个配置使用独立 collection，先 warm-up 再测；延迟为中位数。
          </p>
        </div>
        <a
          className="btn btn-ghost text-xs"
          href="/benchrun"
          target="_blank"
          rel="noreferrer"
        >
          重新跑完整基准
        </a>
      </div>

      {configs.length > 0 && (
        <>
          <section className="card overflow-x-auto">
            <div className="border-b border-[var(--color-line)] px-5 py-3">
              <h3 className="text-sm font-semibold">检索质量与端到端延迟</h3>
              <p className="mt-0.5 text-[11px] text-[var(--color-muted)]">
                {phase4?.result?.at
                  ? `最近一次 pnpm bench 的快照：${new Date(phase4.result.at).toLocaleString()}`
                  : ""}{" "}
                · Jaccard/Kendall 是同一 query 下相对 FP32/WASM 的 Top-10 排序一致性
              </p>
            </div>
            <table className="w-full min-w-[1180px] text-left text-[12px]">
              <thead className="bg-[#f7f4ec] text-[10px] uppercase tracking-wide text-[var(--color-muted)]">
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
                {configs.map((row) => (
                  <tr key={row.id} className="border-t border-[var(--color-line)]">
                    <td className="px-4 py-2 font-medium">{row.id}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.loadMs, 0)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.warmupMs, 0)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.firstAnswerMs, 0)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.docsPerSecond)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.refreshMs, 0)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.queryEmbedMsMedian)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.dbMsMedian)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.totalMsMedian)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.totalMsP95)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.totalMsMax)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.recall5, 3)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.ndcg5, 3)}</td>
                    <td className="mono px-4 py-2 text-right">{num(row.mrr10, 3)}</td>
                    <td className="mono px-4 py-2 text-right">
                      {row.jaccard10VsBaseline === undefined
                        ? "基线"
                        : num(row.jaccard10VsBaseline, 3)}
                    </td>
                    <td className="mono px-4 py-2 text-right">
                      {row.kendallVsBaseline === undefined
                        ? "基线"
                        : num(row.kendallVsBaseline, 3)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="card px-5 py-4 text-[12.5px] leading-6">
            <h3 className="text-sm font-semibold">读法</h3>
            <p className="mt-1 text-[var(--color-muted)]">
              同一 dtype 只换后端：FP32/WASM → FP32/WebGPU，文档吞吐 13.2 → 50.8
              docs/s，端到端 43.3 → 32.7 ms。WebGPU 上 FP16 vs FP32 是吞吐/体积换延迟：
              56.1 vs 50.8 docs/s、payload 66.4 vs 111.6 MiB，但单条查询 35.3 vs
              32.7 ms；FP16 作为默认是为了导入吞吐和体积，不是“单条最快”。
            </p>
            <p className="mt-2 text-[var(--color-muted)]">
              INT8/WASM 的首答 292 ms、payload 33.9 MiB，是冷启动/低带宽路径；nDCG
              0.984、Top-10 Jaccard 0.936，在当前 20 条查询上没有测到相关性损失，但
              排序结构有变化，不能宣称“无损”。另外，这 20 条查询连字符 bigram
              基线都能把主文档排到第 1（20/20），所以它只能验证“没有明显下降”，
              不能用来给编码器排名。
            </p>
          </section>
        </>
      )}

      <section className="card overflow-hidden">
        <div className="border-b border-[var(--color-line)] px-5 py-3">
          <h3 className="text-sm font-semibold">模型体积与压缩比</h3>
          <p className="mt-0.5 text-[11px] text-[var(--color-muted)]">
            仅统计 ONNX 权重文件；压缩比 = FP32 体积 / 量化体积。
          </p>
        </div>
        <table className="w-full text-left text-[12px]">
          <thead className="bg-[#f7f4ec] text-[10.5px] uppercase tracking-wide text-[var(--color-muted)]">
            <tr>
              <th className="px-5 py-2 font-medium">精度</th>
              <th className="px-5 py-2 font-medium">文件</th>
              <th className="px-5 py-2 text-right font-medium">MiB</th>
              <th className="px-5 py-2 text-right font-medium">压缩比</th>
            </tr>
          </thead>
          <tbody>
            {MODEL_SIZES.map((size) => (
              <tr key={size.name} className="border-t border-[var(--color-line)]">
                <td className="px-5 py-2 font-medium">{size.name}</td>
                <td className="mono px-5 py-2 text-[11px] text-[var(--color-muted)]">
                  {size.file}
                </td>
                <td className="mono px-5 py-2 text-right">{size.mib.toFixed(2)}</td>
                <td className="mono px-5 py-2 text-right">{size.ratio}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--color-line)] px-5 py-3">
          <div>
            <h3 className="text-sm font-semibold">推理层补充：后端 / 量化</h3>
            <p className="mt-0.5 text-[11px] text-[var(--color-muted)]">
              {spike?.result?.at
                ? `采集于 ${new Date(spike.result.at).toLocaleString()}`
                : "读取 /bench/phase2.json…"}
            </p>
          </div>
          <span className="mono text-[10.5px] text-[var(--color-muted)]">
            {spike?.result?.gpu?.ok
              ? "WebGPU adapter: available"
              : `WebGPU: ${spike?.result?.gpu?.reason ?? "未知"}`}
          </span>
        </div>
        {error ? (
          <p className="px-5 py-6 text-sm text-[var(--color-danger)]">
            读不到基准数据：{error}。先运行{" "}
            <span className="mono">node scripts/spike-playwright.mjs</span>。
          </p>
        ) : (
          <table className="w-full text-left text-[12px]">
            <thead className="bg-[#f7f4ec] text-[10.5px] uppercase tracking-wide text-[var(--color-muted)]">
              <tr>
                <th className="px-5 py-2 font-medium">配置</th>
                <th className="px-5 py-2 text-right font-medium">加载 ms</th>
                <th className="px-5 py-2 text-right font-medium">单条中位 ms</th>
                <th className="px-5 py-2 text-right font-medium">batch32 ms/条</th>
                <th className="px-5 py-2 text-right font-medium">cos vs FP32</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const batch32 = row.batchSweep?.find(
                  (item) => item.batchSize === 32,
                )?.perTextMs;
                const cosine = row.cosineVsFp32
                  ? row.cosineVsFp32.reduce((sum, value) => sum + value, 0) /
                    row.cosineVsFp32.length
                  : null;
                return (
                  <tr
                    key={`${row.device}-${row.dtype}`}
                    className="border-t border-[var(--color-line)]"
                  >
                    <td className="px-5 py-2 font-medium">
                      {row.device}/{row.dtype}
                    </td>
                    <td className="mono px-5 py-2 text-right">{row.loadMs ?? "—"}</td>
                    <td className="mono px-5 py-2 text-right">{row.queryMs ?? "—"}</td>
                    <td className="mono px-5 py-2 text-right">{batch32 ?? "—"}</td>
                    <td className="mono px-5 py-2 text-right">
                      {cosine === null ? "基线" : cosine.toFixed(5)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <section className="card px-5 py-4 text-[12px] leading-6 text-[var(--color-muted)]">
        <h3 className="text-sm font-semibold text-[var(--color-ink)]">边界</h3>
        <p className="mt-1">
          20 篇语料、20 条查询、单机单浏览器，结论只在这个规模上成立。INT8 的
          nDCG 差异落在小样本噪声范围内，但排序一致性下降是真实的；如果需要更强的
          统计结论，应把语料扩到数百篇并使用公开 qrels。原始 JSON 在{" "}
          <span className="mono">bench/results/</span>，可用{" "}
          <span className="mono">pnpm bench</span> 重跑。
        </p>
      </section>
    </div>
  );
}
