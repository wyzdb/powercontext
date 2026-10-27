import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { api, type TraceEntry } from "../lib/api";

interface TraceDrawerProps {
  traceId: string | null;
  onClose: () => void;
}

export default function TraceDrawer({ traceId, onClose }: TraceDrawerProps) {
  const [entries, setEntries] = useState<TraceEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFull, setShowFull] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!traceId) return;
    let alive = true;
    setLoading(true);
    setError(null);
    api
      .trace(traceId)
      .then((result) => {
        if (alive) setEntries(result.entries);
      })
      .catch((traceError) => {
        if (alive) setError(String(traceError));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [traceId]);

  if (!traceId) return null;

  const hybrid =
    entries.find((entry) =>
      /_keyword_rank|_semantic_rank|cosine_distance/i.test(entry.sql),
    ) ??
    entries.find((entry) => /DBMS_HYBRID_SEARCH/i.test(entry.sql));
  const sql = hybrid?.sql ?? "";
  const shown = showFull ? sql : sql.slice(0, 5000);
  const totalMs = entries.reduce((sum, entry) => sum + entry.ms, 0);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0 bg-black/25"
        onClick={onClose}
        aria-hidden
      />
      <aside className="relative flex h-full w-[760px] max-w-[94vw] flex-col border-l border-[var(--color-line)] bg-[var(--color-panel)] shadow-2xl">
        <header className="flex items-start justify-between border-b border-[var(--color-line)] px-6 py-4">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
              SQL trace
            </p>
            <h2 className="serif mt-1 text-lg">这次检索在 seekdb 里执行了什么</h2>
            <p className="mt-1 text-[11px] text-[var(--color-muted)]">
              {entries.length} 条语句 · 合计{" "}
              <span className="mono">{totalMs.toFixed(1)} ms</span> · 融合由
              DBMS_HYBRID_SEARCH 生成
            </p>
          </div>
          <button className="btn btn-ghost py-1.5 text-xs" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">
          {loading && (
            <p className="text-sm text-[var(--color-muted)]">读取 trace…</p>
          )}
          {error && (
            <p className="text-sm text-[var(--color-danger)]">{error}</p>
          )}

          {hybrid && (
            <section>
              <div className="mb-2 flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold">
                  数据库生成的混合检索 SQL
                </h3>
                <div className="flex items-center gap-2">
                  <button
                    className="btn btn-ghost py-1 text-[11px]"
                    onClick={() => setShowFull((value) => !value)}
                  >
                    {showFull ? "截断显示" : "完整 SQL"}
                  </button>
                  <button
                    className="btn btn-ghost py-1 text-[11px]"
                    onClick={copy}
                  >
                    {copied ? "已复制" : "复制"}
                  </button>
                </div>
              </div>
              <pre className="sql-block">{shown}</pre>
              {!showFull && sql.length > 5000 && (
                <p className="mt-1 text-[10px] text-[var(--color-muted)]">
                  已截断，原始 SQL 共 {sql.length} 字符。点击“完整 SQL”查看。
                </p>
              )}
              <p className="mt-2 text-[11px] leading-5 text-[var(--color-muted)]">
                这条 SQL 的两路候选、排名窗口和 RRF 分数都在数据库内完成：
                <span className="mono"> _score = 1/(k+keyword_rank) + 1/(k+semantic_rank)</span>
                。客户端没有对两路结果做二次融合。
              </p>
            </section>
          )}

          <section className="mt-6">
            <h3 className="mb-2 text-sm font-semibold">全部语句</h3>
            <ul className="space-y-1.5">
              {entries.map((entry, index) => (
                <li
                  key={`${entry.sql.slice(0, 40)}-${index}`}
                  className="rounded-lg border border-[var(--color-line)] bg-white/60"
                >
                  <details>
                    <summary className="flex cursor-pointer items-center gap-3 px-3 py-2 text-[11px]">
                      <span className="mono w-14 shrink-0 text-[var(--color-muted)]">
                        {entry.ms.toFixed(1)} ms
                      </span>
                      <span className="mono w-12 shrink-0 text-[var(--color-muted)]">
                        {entry.rows ?? "—"} rows
                      </span>
                      <span className="truncate text-[#34312c]">
                        {entry.sql.replace(/\s+/g, " ").slice(0, 140)}
                      </span>
                      {entry.error && (
                        <span className="ml-auto shrink-0 text-[var(--color-danger)]">
                          error
                        </span>
                      )}
                    </summary>
                    <pre className="sql-block m-3 mt-0 max-h-64">{entry.sql}</pre>
                  </details>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </aside>
    </div>,
    document.body,
  );
}
