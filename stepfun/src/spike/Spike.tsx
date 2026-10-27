import { useCallback, useState } from "react";
import {
  cosine,
  disposeEmbedder,
  embed,
  l2,
  loadEmbedder,
  type BackendDevice,
  type Dtype,
} from "../lib/embedder";
import { probeWebGPU, type GpuProbe } from "../lib/gpu";

declare global {
  interface Window {
    __SPIKE_RESULT__?: unknown;
  }
}

const TEXTS = [
  "苹果手机搭载了自研芯片，续航表现优秀。",
  "数据库的向量索引使用 HNSW 算法加速近邻搜索。",
  "云计算平台通过虚拟化技术提供弹性计算资源。",
];

interface Row {
  device: BackendDevice;
  dtype: Dtype;
  loadMs?: number;
  warmupMs?: number;
  embedMs?: number;
  perTextMs?: number;
  queryMs?: number;
  dim?: number;
  norms?: number[];
  cosineVsFp32?: number[];
  batchSweep?: Array<{ batchSize: number; ms: number; perTextMs: number }>;
  error?: string;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

async function runOne(
  device: BackendDevice,
  dtype: Dtype,
  reference: number[][] | undefined,
  onStatus: (text: string) => void,
): Promise<{ row: Row; vectors: number[][] }> {
  const loaded = await loadEmbedder({
    device,
    dtype,
    onProgress: (progress) => {
      const percent =
        typeof progress.progress === "number"
          ? `${Math.round(progress.progress * 100)}%`
          : "";
      onStatus(`${device}/${dtype} 加载中 ${progress.file ?? ""} ${percent}`.trim());
    },
  });
  const warm = await embed(["warmup"], { batchSize: 1 });
  const output = await embed(TEXTS, { batchSize: 3 });

  const queryRuns: number[] = [];
  for (let run = 0; run < 5; run += 1) {
    const single = await embed([TEXTS[0]], { batchSize: 1 });
    queryRuns.push(single.ms);
  }

  const corpus = Array.from({ length: 32 }, (_, index) => TEXTS[index % TEXTS.length]);
  const batchSweep: Row["batchSweep"] = [];
  for (const batchSize of [1, 4, 8, 16, 32]) {
    const batch = await embed(corpus.slice(0, batchSize), { batchSize });
    batchSweep.push({
      batchSize,
      ms: Math.round(batch.ms),
      perTextMs: Math.round((batch.ms / batchSize) * 10) / 10,
    });
  }

  const row: Row = {
    device,
    dtype,
    loadMs: Math.round(loaded.loadMs),
    warmupMs: Math.round(warm.ms),
    embedMs: Math.round(output.ms),
    perTextMs: Math.round((output.ms / TEXTS.length) * 10) / 10,
    queryMs: Math.round(median(queryRuns) * 10) / 10,
    dim: output.vectors[0]?.length,
    norms: output.vectors.map((vector) => Math.round(l2(vector) * 10000) / 10000),
    cosineVsFp32: reference
      ? output.vectors.map(
          (vector, index) =>
            Math.round(cosine(vector, reference[index]) * 100000) / 100000,
        )
      : undefined,
    batchSweep,
  };
  await disposeEmbedder();
  return { row, vectors: output.vectors };
}

export default function Spike() {
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState("等待运行");
  const [rows, setRows] = useState<Row[]>([]);
  const [gpu, setGpu] = useState<GpuProbe | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runAll = useCallback(async () => {
    setRunning(true);
    setError(null);
    setRows([]);
    const collected: Row[] = [];
    let probe: GpuProbe | null = null;

    try {
      setStatus("探测 WebGPU...");
      probe = await probeWebGPU();
      setGpu(probe);

      setStatus("加载 FP32 / WASM（质量基线）...");
      const fp32 = await runOne("wasm", "fp32", undefined, setStatus);
      collected.push(fp32.row);
      setRows([...collected]);

      setStatus("加载 INT8 / WASM...");
      try {
        const int8 = await runOne("wasm", "int8", fp32.vectors, setStatus);
        collected.push(int8.row);
      } catch (int8Error) {
        collected.push({
          device: "wasm",
          dtype: "int8",
          error: String(int8Error),
        });
      }
      setRows([...collected]);

      if (probe.ok) {
        setStatus("加载 FP16 / WebGPU...");
        try {
          const fp16 = await runOne("webgpu", "fp16", fp32.vectors, setStatus);
          collected.push(fp16.row);
        } catch (webgpuError) {
          collected.push({
            device: "webgpu",
            dtype: "fp16",
            error: String(webgpuError),
          });
        }
      } else {
        collected.push({
          device: "webgpu",
          dtype: "fp16",
          error: `WebGPU 不可用：${probe.reason ?? "unknown"}`,
        });
      }
      setRows([...collected]);
      setStatus("完成");
    } catch (runError) {
      setError(String(runError));
      setStatus("失败");
    } finally {
      setRunning(false);
      window.__SPIKE_RESULT__ = {
        gpu: probe,
        rows: collected,
        userAgent: navigator.userAgent,
        at: new Date().toISOString(),
      };
    }
  }, []);

  return (
    <main className="spike">
      <header>
        <p className="eyebrow">Phase 2 · on-device inference spike</p>
        <h1>WebGPU / WASM 与 INT8 / FP16 实测</h1>
        <p className="lede">
          这个页面不经过 seekdb，只验证浏览器端推理：模型能否加载、后端能否初始化、
          量化后的向量是否仍然接近 FP32 基线。结果会写入{" "}
          <code>window.__SPIKE_RESULT__</code>，供 Playwright 抓取。
        </p>
      </header>

      <section className="controls">
        <button onClick={runAll} disabled={running}>
          {running ? "运行中..." : "运行全部配置"}
        </button>
        <span className="status">{status}</span>
      </section>

      <section className="panel">
        <h2>WebGPU 探测</h2>
        {gpu ? (
          <pre>{JSON.stringify(gpu, null, 2)}</pre>
        ) : (
          <p className="muted">尚未探测。</p>
        )}
      </section>

      <section className="panel">
        <h2>结果</h2>
        {rows.length === 0 ? (
          <p className="muted">点击“运行全部配置”。首次会加载 95 MB 的 FP32 模型。</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>配置</th>
                <th>加载 ms</th>
                <th>预热 ms</th>
                <th>3 条耗时 ms</th>
                <th>单条 ms</th>
                <th>单条中位 ms</th>
                <th>batch32 ms/条</th>
                <th>维度</th>
                <th>L2</th>
                <th>cos vs FP32</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.device}-${row.dtype}`}>
                  <td>
                    {row.device}/{row.dtype}
                  </td>
                  <td>{row.loadMs ?? "—"}</td>
                  <td>{row.warmupMs ?? "—"}</td>
                  <td>{row.embedMs ?? "—"}</td>
                  <td>{row.perTextMs ?? "—"}</td>
                  <td>{row.queryMs ?? "—"}</td>
                  <td>
                    {row.batchSweep?.find((item) => item.batchSize === 32)
                      ?.perTextMs ?? "—"}
                  </td>
                  <td>{row.dim ?? "—"}</td>
                  <td>{row.norms?.join(", ") ?? "—"}</td>
                  <td>
                    {row.cosineVsFp32?.join(", ") ?? row.error ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {error && (
        <section className="panel error">
          <h2>错误</h2>
          <pre>{error}</pre>
        </section>
      )}

      <section className="panel">
        <h2>原始 JSON</h2>
        <pre>{JSON.stringify(rows, null, 2)}</pre>
      </section>
    </main>
  );
}
