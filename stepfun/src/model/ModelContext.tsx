import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  embed,
  loadEmbedder,
  type BackendDevice,
  type Dtype,
  type ProgressInfo,
} from "../lib/embedder";
import { probeWebGPU, type GpuProbe } from "../lib/gpu";

export const QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章：";

export interface ModelChoice {
  device: BackendDevice;
  dtype: Dtype;
  label: string;
  reason?: string;
}

type Status = "idle" | "probing" | "loading" | "ready" | "fallback" | "error";

interface ModelContextValue {
  status: Status;
  choice: ModelChoice | null;
  progress: string;
  loadMs: number | null;
  error: string | null;
  gpu: GpuProbe | null;
  forceWasm: boolean;
  setForceWasm: (value: boolean) => void;
  ensure: () => Promise<ModelChoice>;
  embedDocs: (texts: string[], batchSize?: number) => Promise<{ vectors: number[][]; ms: number }>;
  embedQuery: (text: string) => Promise<{ vector: number[]; ms: number }>;
}

const ModelContext = createContext<ModelContextValue | null>(null);

const FORCE_KEY = "stepfun-kb-force-wasm";

export function ModelProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("idle");
  const [choice, setChoice] = useState<ModelChoice | null>(null);
  const [progress, setProgress] = useState("");
  const [loadMs, setLoadMs] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gpu, setGpu] = useState<GpuProbe | null>(null);
  const [forceWasm, setForceWasmState] = useState(
    () => localStorage.getItem(FORCE_KEY) === "1",
  );

  const choiceRef = useRef<ModelChoice | null>(null);
  const statusRef = useRef<Status>("idle");
  const loadingRef = useRef<Promise<ModelChoice> | null>(null);

  const setForceWasm = useCallback((value: boolean) => {
    localStorage.setItem(FORCE_KEY, value ? "1" : "0");
    setForceWasmState(value);
    // Reload instead of trying to tear down WebGPU buffers in-place. This is
    // also how a reviewer can reproduce the WASM fallback path deterministically.
    window.location.reload();
  }, []);

  const ensure = useCallback(async (): Promise<ModelChoice> => {
    if (statusRef.current === "ready" && choiceRef.current) {
      return choiceRef.current;
    }
    if (loadingRef.current) return loadingRef.current;

    loadingRef.current = (async () => {
      setStatus("probing");
      statusRef.current = "probing";
      const probe = await probeWebGPU();
      setGpu(probe);

      const preferred: ModelChoice =
        forceWasm || !probe.ok
          ? {
              device: "wasm",
              dtype: "int8",
              label: "WASM · INT8",
              reason: forceWasm ? "用户强制使用 WASM" : probe.reason,
            }
          : { device: "webgpu", dtype: "fp16", label: "WebGPU · FP16" };

      const load = async (candidate: ModelChoice): Promise<ModelChoice> => {
        setStatus("loading");
        statusRef.current = "loading";
        setError(null);
        const loaded = await loadEmbedder({
          device: candidate.device,
          dtype: candidate.dtype,
          onProgress: (info: ProgressInfo) => {
            const percent =
              typeof info.progress === "number"
                ? `${Math.round(info.progress * 100)}%`
                : "";
            setProgress(`${info.file ?? ""} ${percent}`.trim());
          },
        });
        setLoadMs(Math.round(loaded.loadMs));
        setChoice(candidate);
        choiceRef.current = candidate;
        statusRef.current = "ready";
        setStatus(candidate.reason ? "fallback" : "ready");
        return candidate;
      };

      try {
        return await load(preferred);
      } catch (loadError) {
        if (preferred.device === "webgpu") {
          const fallback: ModelChoice = {
            device: "wasm",
            dtype: "int8",
            label: "WASM · INT8（自动降级）",
            reason: String(loadError),
          };
          setGpu({ ok: false, reason: String(loadError) });
          return load(fallback);
        }
        setStatus("error");
        statusRef.current = "error";
        setError(String(loadError));
        throw loadError;
      }
    })();

    try {
      return await loadingRef.current;
    } finally {
      loadingRef.current = null;
    }
  }, [forceWasm]);

  const embedDocs = useCallback(
    async (texts: string[], batchSize = 16) => {
      await ensure();
      return embed(texts, { batchSize });
    },
    [ensure],
  );

  const embedQuery = useCallback(
    async (text: string) => {
      await ensure();
      const result = await embed([`${QUERY_INSTRUCTION}${text}`], {
        batchSize: 1,
      });
      return { vector: result.vectors[0], ms: result.ms };
    },
    [ensure],
  );

  return (
    <ModelContext.Provider
      value={{
        status,
        choice,
        progress,
        loadMs,
        error,
        gpu,
        forceWasm,
        setForceWasm,
        ensure,
        embedDocs,
        embedQuery,
      }}
    >
      {children}
    </ModelContext.Provider>
  );
}

export function useModel(): ModelContextValue {
  const value = useContext(ModelContext);
  if (!value) throw new Error("useModel must be used inside ModelProvider");
  return value;
}
