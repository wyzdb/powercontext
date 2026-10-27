import { useCallback, useEffect, useMemo, useState } from "react";
import AboutPanel from "./components/AboutPanel";
import BackendBadge from "./components/BackendBadge";
import BenchmarkPanel from "./components/BenchmarkPanel";
import ImportPanel from "./components/ImportPanel";
import SearchPanel from "./components/SearchPanel";
import Sidebar from "./components/Sidebar";
import { api, type Health, type KbRecord } from "./lib/api";
import { MODEL_ID } from "./lib/embedder";
import { useModel } from "./model/ModelContext";

type Tab = "kb" | "search" | "bench" | "about";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "kb", label: "语料与导入" },
  { id: "search", label: "检索" },
  { id: "bench", label: "基准" },
  { id: "about", label: "方法" },
];

export default function App() {
  const model = useModel();
  const [health, setHealth] = useState<Health | null>(null);
  const [kbs, setKbs] = useState<KbRecord[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("kb");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [nextHealth, list] = await Promise.all([
      api.health(),
      api.listKbs().catch(() => ({ kbs: [] as KbRecord[] })),
    ]);
    setHealth(nextHealth);
    setKbs(list.kbs);
    setCurrentId((previous) => {
      if (previous && list.kbs.some((kb) => kb.id === previous)) return previous;
      return list.kbs[0]?.id ?? null;
    });
  }, []);

  useEffect(() => {
    refresh()
      .catch((loadError) => setError(String(loadError)))
      .finally(() => setLoading(false));
  }, [refresh]);

  const retry = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      await refresh();
    } catch (retryError) {
      setError(String(retryError));
    } finally {
      setLoading(false);
    }
  }, [refresh]);

  const currentKb = useMemo(
    () => kbs.find((kb) => kb.id === currentId) ?? null,
    [kbs, currentId],
  );

  const createKb = async (name: string) => {
    const choice = await model.ensure();
    const kb = await api.createKb({
      name,
      modelId: MODEL_ID,
      dim: 512,
      dtype: choice.dtype as "fp32" | "int8" | "fp16",
    });
    await refresh();
    setCurrentId(kb.id);
    setTab("kb");
  };

  const deleteKb = async (id: string) => {
    await api.deleteKb(id);
    await refresh();
  };

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        kbs={kbs}
        currentId={currentId}
        loading={loading}
        health={health}
        onSelect={(id) => setCurrentId(id)}
        onCreate={createKb}
        onDelete={deleteKb}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-line)] bg-[#faf8f2]/80 px-7 py-4 backdrop-blur">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[var(--color-muted)]">
              on-device embedding · db-side hybrid retrieval
            </p>
            <div className="mt-1 flex items-baseline gap-3">
              <h1 className="serif text-[24px] leading-none">个人知识库</h1>
              <span className="truncate text-[11.5px] text-[var(--color-muted)]">
                {currentKb ? currentKb.name : "未选择知识库"}
              </span>
            </div>
          </div>
          <BackendBadge />
        </header>

        <nav className="flex gap-1 border-b border-[var(--color-line)] px-7">
          {TABS.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`border-b-2 px-3 py-2.5 text-[12.5px] transition ${
                tab === item.id
                  ? "border-[var(--color-accent)] font-semibold text-[var(--color-ink)]"
                  : "border-transparent text-[var(--color-muted)] hover:text-[var(--color-ink)]"
              }`}
            >
              {item.label}
            </button>
          ))}
          <span className="mono ml-auto self-center text-[10px] text-[var(--color-muted)]">
            {currentKb ? `${currentKb.count} chunks · ${currentKb.dtype}` : ""}
          </span>
        </nav>

        <div className="scroll-thin flex-1 overflow-y-auto px-7 py-6">
          {error && (
            <div className="mb-4 flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[12px] text-[var(--color-danger)]">
              <span className="flex-1">{error}</span>
              <button className="btn btn-ghost py-1 text-[10.5px]" onClick={retry}>
                重试
              </button>
            </div>
          )}

          {health && !health.ok && (
            <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-[12px] leading-5 text-[var(--color-warn)]">
              <div className="flex items-center gap-3">
                <span className="flex-1">
                  <strong className="font-semibold">seekdb 未连接。</strong>{" "}
                  {health.error}
                </span>
                <button
                  className="btn btn-ghost py-1 text-[10.5px]"
                  onClick={retry}
                >
                  重试连接
                </button>
              </div>
              {health.hints && (
                <details className="mt-1">
                  <summary className="cursor-pointer">查看启动命令</summary>
                  <ul className="mono mt-1 space-y-1 text-[10.5px]">
                    {health.hints.map((hint) => (
                      <li key={hint}>{hint}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}

          {tab === "kb" && (
            <ImportPanel kb={currentKb} onImported={refresh} />
          )}
          {tab === "search" && <SearchPanel kb={currentKb} />}
          {tab === "bench" && <BenchmarkPanel />}
          {tab === "about" && <AboutPanel />}
        </div>
      </main>
    </div>
  );
}
