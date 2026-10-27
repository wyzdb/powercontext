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

const MODEL_SIZES = [
  { name: "FP32", file: "model.onnx", mib: 90.46, ratio: "1.00×" },
  { name: "FP16", file: "model_fp16.onnx", mib: 45.3, ratio: "2.00×" },
  { name: "INT8", file: "model_int8.onnx", mib: 22.8, ratio: "3.97×" },
];

export default function BenchmarkPanel() {
  const [payload, setPayload] = useState<SpikePayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/bench/phase2.json")
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data: SpikePayload) => setPayload(data))
      .catch((loadError) => setError(String(loadError)));
  }, []);

  const rows = payload?.result?.rows ?? [];

  return (
    <div className="space-y-5">
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
          基准 · 实测数据
        </p>
        <h2 className="serif mt-1 text-2xl">推理层：先看数字，再谈优化</h2>
        <p className="mt-1 max-w-3xl text-[12.5px] leading-6 text-[var(--color-muted)]">
          下表来自本机 Chrome 155 / Intel Arc 的 /spike 页面，模型为
          bge-small-zh-v1.5。每条配置先做一次 warm-up，再测 5 次单条查询的中位数；
          batch32 是把 32 条文本一次送入的每条约耗时。
        </p>
      </div>

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
            <h3 className="text-sm font-semibold">推理后端与量化</h3>
            <p className="mt-0.5 text-[11px] text-[var(--color-muted)]">
              {payload?.result?.at
                ? `采集于 ${new Date(payload.result.at).toLocaleString()}`
                : "读取 /bench/phase2.json…"}
            </p>
          </div>
          <span className="mono text-[10.5px] text-[var(--color-muted)]">
            {payload?.result?.gpu?.ok
              ? "WebGPU adapter: available"
              : `WebGPU: ${payload?.result?.gpu?.reason ?? "未知"}`}
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
        <h3 className="text-sm font-semibold text-[var(--color-ink)]">
          还没有做的部分
        </h3>
        <p className="mt-1">
          这张表只回答“哪个后端/精度更快、向量是否还接近”。检索质量（Recall@10、nDCG@10、
          MRR）和端到端延迟需要固定查询集与 qrels，放在{" "}
          <span className="mono">bench/</span> 里跑；完成后会把 6 组配置 A–F
          的原始 JSON 追加到仓库，而不是只留一张截图。
        </p>
      </section>
    </div>
  );
}
