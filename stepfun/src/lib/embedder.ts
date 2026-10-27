import { env, pipeline } from "@huggingface/transformers";

export type BackendDevice = "webgpu" | "wasm";
export type Dtype = "fp32" | "fp16" | "int8" | "q8";

export interface ProgressInfo {
  status?: string;
  file?: string;
  progress?: number;
  loaded?: number;
  total?: number;
}

export interface LoadOptions {
  device: BackendDevice;
  dtype: Dtype;
  onProgress?: (progress: ProgressInfo) => void;
}

interface LoadedEmbedder {
  pipe: (texts: string[], options: Record<string, unknown>) => Promise<{
    tolist: () => number[][];
  }>;
  key: string;
  loadMs: number;
}

export const MODEL_ID = "Xenova/bge-small-zh-v1.5";
export const QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章：";

env.allowLocalModels = true;
env.localModelPath = "/models/";
env.allowRemoteModels = false;
env.useBrowserCache = true;

const wasmBackend = env.backends.onnx.wasm as unknown as {
  wasmPaths: string;
  numThreads: number;
  simd: boolean;
};
wasmBackend.wasmPaths = "/ort/";
wasmBackend.numThreads = 1;
wasmBackend.simd = true;

let loaded: LoadedEmbedder | null = null;

export async function loadEmbedder(options: LoadOptions): Promise<LoadedEmbedder> {
  const key = `${options.device}/${options.dtype}`;
  if (loaded?.key === key) return loaded;
  await disposeEmbedder();

  const started = performance.now();
  const pipe = await pipeline("feature-extraction", MODEL_ID, {
    device: options.device,
    dtype: options.dtype,
    progress_callback: (progress: ProgressInfo) => options.onProgress?.(progress),
  } as never);

  loaded = {
    pipe: pipe as unknown as LoadedEmbedder["pipe"],
    key,
    loadMs: performance.now() - started,
  };
  return loaded;
}

export async function embed(
  texts: string[],
  options: { batchSize?: number } = {},
): Promise<{ vectors: number[][]; ms: number }> {
  if (!loaded) throw new Error("embedder 尚未加载");
  const started = performance.now();
  const output = await loaded.pipe(texts, {
    // BGE v1.5 was trained with CLS pooling (see 1_Pooling/config.json:
    // pooling_mode_cls_token=true). Mean pooling is a common shortcut but is a
    // different embedding function; do not mix its vectors with CLS vectors.
    pooling: "cls",
    normalize: true,
    batch_size: options.batchSize ?? 8,
  });
  return {
    vectors: output.tolist(),
    ms: performance.now() - started,
  };
}

export async function disposeEmbedder(): Promise<void> {
  if (!loaded) return;
  const pipe = loaded.pipe as unknown as { dispose?: () => Promise<void> };
  try {
    await pipe.dispose?.();
  } catch {
    // best-effort; WebGPU buffers are also reclaimed on page reload
  }
  loaded = null;
}

export function l2(vector: number[]): number {
  return Math.sqrt(vector.reduce((sum, value) => sum + value * value, 0));
}

export function cosine(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < a.length; i += 1) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  return dot / Math.sqrt(na * nb);
}
