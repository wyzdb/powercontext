import { useState, type FormEvent } from "react";
import type { Health, KbRecord } from "../lib/api";

interface SidebarProps {
  kbs: KbRecord[];
  currentId: string | null;
  loading: boolean;
  health: Health | null;
  onSelect: (id: string) => void;
  onCreate: (name: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

export default function Sidebar({
  kbs,
  currentId,
  loading,
  health,
  onSelect,
  onCreate,
  onDelete,
}: SidebarProps) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onCreate(name.trim());
      setName("");
      setCreating(false);
    } catch (createError) {
      setError(String(createError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="flex h-full w-[292px] shrink-0 flex-col border-r border-[var(--color-line)] bg-[#f2efe6]">
      <div className="flex items-center justify-between border-b border-[var(--color-line)] px-5 py-5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
            StepFun × seekdb
          </p>
          <h1 className="serif mt-1 text-[22px] leading-none">本地知识库</h1>
        </div>
        <button
          className="btn btn-ghost h-8 w-8 justify-center p-0 text-lg leading-none"
          onClick={() => setCreating((value) => !value)}
          title="新建知识库"
        >
          +
        </button>
      </div>

      {creating && (
        <form
          onSubmit={submit}
          className="border-b border-[var(--color-line)] px-4 py-3"
        >
          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="知识库名称，例如：论文笔记"
            className="w-full rounded-md border border-[var(--color-line)] bg-white px-3 py-2 text-sm outline-none focus:border-[var(--color-accent)]"
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              type="submit"
              className="btn btn-primary flex-1 justify-center py-1.5 text-xs"
              disabled={busy || !name.trim()}
            >
              {busy ? "创建中…" : "创建"}
            </button>
            <button
              type="button"
              className="btn btn-ghost py-1.5 text-xs"
              onClick={() => setCreating(false)}
            >
              取消
            </button>
          </div>
          {error && (
            <p className="mt-2 text-[11px] text-[var(--color-danger)]">{error}</p>
          )}
        </form>
      )}

      <div className="scroll-thin flex-1 overflow-y-auto px-3 py-3">
        {loading ? (
          <p className="px-2 py-4 text-xs text-[var(--color-muted)]">读取集合…</p>
        ) : kbs.length === 0 ? (
          <div className="px-2 py-4 text-xs leading-relaxed text-[var(--color-muted)]">
            还没有知识库。新建一个，然后导入文本文档。
          </div>
        ) : (
          <ul className="space-y-1.5">
            {kbs.map((kb) => {
              const active = kb.id === currentId;
              return (
                <li key={kb.id}>
                  <div
                    className={`group flex items-start gap-2 rounded-lg border px-3 py-2.5 transition ${
                      active
                        ? "border-[var(--color-accent)] bg-white"
                        : "border-transparent hover:border-[var(--color-line)] hover:bg-white/60"
                    }`}
                  >
                    <button
                      className="min-w-0 flex-1 text-left"
                      onClick={() => onSelect(kb.id)}
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="truncate text-sm font-medium">
                          {kb.name}
                        </span>
                        <span className="mono text-[11px] text-[var(--color-muted)]">
                          {kb.count}
                        </span>
                      </div>
                      <div className="mono mt-0.5 text-[10px] uppercase tracking-wide text-[var(--color-muted)]">
                        {kb.dtype} · {kb.dim}d
                        {kb.missing ? " · 表缺失" : ""}
                      </div>
                    </button>
                    <button
                      className="mt-0.5 hidden h-5 w-5 shrink-0 items-center justify-center rounded text-[var(--color-muted)] hover:bg-red-50 hover:text-[var(--color-danger)] group-hover:flex"
                      title="删除知识库"
                      onClick={async () => {
                        if (
                          window.confirm(
                            `删除「${kb.name}」及其全部向量？该操作不可撤销。`,
                          )
                        ) {
                          await onDelete(kb.id);
                        }
                      }}
                    >
                      ×
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-[var(--color-line)] px-4 py-3 text-[11px]">
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${
              health?.ok ? "bg-emerald-700" : "bg-red-700"
            }`}
          />
          <span className="font-medium">
            seekdb {health?.ok ? "已连接" : "未连接"}
          </span>
          <span className="mono ml-auto text-[var(--color-muted)]">
            {health?.mode ?? "—"}
          </span>
        </div>
        <p className="mono mt-1 truncate text-[10px] text-[var(--color-muted)]" title={health?.target}>
          {health?.version ?? health?.error ?? "—"}
        </p>
        {!health?.ok && health?.hints && (
          <details className="mt-2">
            <summary className="cursor-pointer text-[var(--color-warn)]">
              启动方式
            </summary>
            <ul className="mt-1 space-y-1 break-all text-[10px] text-[var(--color-muted)]">
              {health.hints.map((hint) => (
                <li key={hint}>{hint}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </aside>
  );
}
