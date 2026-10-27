import type { SearchHit } from "../lib/api";

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function Highlight({ text, query }: { text: string; query: string }) {
  const terms = [...new Set(query.split(/\s+/).filter(Boolean))];
  if (terms.length === 0) return <>{text}</>;
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "gi");
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, index) =>
        terms.some((term) => term.toLowerCase() === part.toLowerCase()) ? (
          <mark
            key={index}
            className="rounded bg-[#f4e3b8] px-0.5 text-inherit"
          >
            {part}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
}

export default function ResultCard({
  hit,
  query,
}: {
  hit: SearchHit;
  query: string;
}) {
  const metadata = hit.metadata ?? {};
  const title =
    typeof metadata.title === "string" ? metadata.title : null;
  const source =
    typeof metadata.source === "string" ? metadata.source : null;
  const chunk =
    typeof metadata.chunk === "number" ? metadata.chunk + 1 : null;
  const chunks =
    typeof metadata.chunks === "number" ? metadata.chunks : null;

  return (
    <article className="card px-5 py-4">
      <div className="flex items-baseline gap-3">
        <span className="mono text-[11px] text-[var(--color-muted)]">
          #{hit.rank}
        </span>
        <h3 className="serif min-w-0 flex-1 truncate text-[15px] font-semibold">
          {title ?? "未命名片段"}
        </h3>
        <span
          className="mono text-[12px] text-[var(--color-accent)]"
          title="seekdb 返回的 RRF 融合分"
        >
          {hit.score.toFixed(4)}
        </span>
      </div>
      <p className="mt-2 text-[13.5px] leading-6 text-[#34312c]">
        <Highlight text={hit.text} query={query} />
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2 text-[10.5px] text-[var(--color-muted)]">
        {source && (
          <span className="rounded border border-[var(--color-line)] px-1.5 py-0.5">
            {source}
          </span>
        )}
        {chunk && (
          <span className="mono">
            chunk {chunk}
            {chunks ? `/${chunks}` : ""}
          </span>
        )}
        <span className="mono truncate" title={hit.id}>
          {hit.id}
        </span>
      </div>
    </article>
  );
}
