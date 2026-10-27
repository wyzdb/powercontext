import { useModel } from "../model/ModelContext";

const tones: Record<string, string> = {
  ready: "bg-emerald-700",
  fallback: "bg-amber-600",
  loading: "bg-amber-500",
  probing: "bg-amber-500",
  error: "bg-red-700",
  idle: "bg-stone-400",
};

export default function BackendBadge() {
  const {
    status,
    choice,
    progress,
    loadMs,
    warmupMs,
    gpu,
    forceWasm,
    setForceWasm,
    error,
  } = useModel();

  const label =
    status === "ready" || status === "fallback"
      ? choice?.label ?? "未知后端"
      : status === "loading"
        ? "模型加载中"
        : status === "probing"
          ? "探测后端"
          : status === "error"
            ? "后端错误"
            : choice?.label ?? "模型未加载";

  const detail =
    status === "loading"
      ? progress
      : status === "ready" || status === "fallback"
        ? `${loadMs ?? "—"} ms 加载${warmupMs === null ? "" : ` · ${warmupMs} ms 预热`}`
        : status === "error"
          ? error ?? ""
          : status === "idle"
            ? "首次导入/检索时加载"
            : gpu?.reason ?? "";

  return (
    <div className="flex items-center gap-3">
      <span
        className="inline-flex items-center gap-2 rounded-full border border-[var(--color-line)] bg-white/50 px-3 py-1 text-xs"
        title={choice?.reason ?? gpu?.reason ?? ""}
      >
        <span
          className={`h-2 w-2 rounded-full ${tones[status] ?? tones.idle}`}
        />
        <span className="font-medium">{label}</span>
        {detail && (
          <span className="mono max-w-[220px] truncate text-[var(--color-muted)]">
            {detail}
          </span>
        )}
      </span>
      <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-[var(--color-muted)]">
        <input
          type="checkbox"
          checked={forceWasm}
          onChange={(event) => setForceWasm(event.target.checked)}
          className="accent-[var(--color-accent)]"
        />
        强制 WASM
      </label>
    </div>
  );
}
