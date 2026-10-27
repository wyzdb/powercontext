export interface GpuProbe {
  ok: boolean;
  reason?: string;
  info?: Record<string, unknown>;
}

export async function probeWebGPU(): Promise<GpuProbe> {
  const gpu = (navigator as Navigator & { gpu?: GPU }).gpu;
  if (!gpu) {
    return {
      ok: false,
      reason: "navigator.gpu 不存在（浏览器未启用 WebGPU 或不是安全上下文）",
    };
  }
  try {
    const adapter = await gpu.requestAdapter({
      powerPreference: "high-performance",
    });
    if (!adapter) {
      return { ok: false, reason: "requestAdapter() 返回 null" };
    }
    const info =
      (adapter as unknown as { info?: Record<string, unknown> }).info ?? {};
    return { ok: true, info };
  } catch (error) {
    return { ok: false, reason: String(error) };
  }
}
