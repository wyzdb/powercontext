#!/usr/bin/env node
// Aggregate three benchmark runs into medians. Each run is produced by
// `RUN_ID=1|2|3 node scripts/bench-playwright.mjs`.
import { copyFile, readFile, writeFile } from "node:fs/promises";

const runs = [];
for (const id of [1, 2, 3]) {
  const file = `bench/results/phase4/bench-${id}.json`;
  runs.push(JSON.parse(await readFile(file, "utf8")));
}

const first = runs[0].result;
const configIds = first.results.map((row) => row.id);
const fields = [
  "loadMs",
  "warmupMs",
  "firstAnswerMs",
  "docEmbedMs",
  "docsPerSecond",
  "writeMs",
  "refreshMs",
  "queryEmbedMsMedian",
  "queryEmbedMsP95",
  "dbMsMedian",
  "dbMsP95",
  "totalMsMedian",
  "totalMsP95",
  "totalMsMax",
  "recall5",
  "ndcg5",
  "mrr10",
  "jaccard10VsBaseline",
  "kendallVsBaseline",
];

function median(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (sorted.length === 0) return undefined;
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

function range(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (sorted.length === 0) return undefined;
  return [sorted[0], sorted[sorted.length - 1]];
}

const results = configIds.map((id) => {
  const rows = runs
    .map((run) => run.result.results.find((row) => row.id === id))
    .filter(Boolean);
  const aggregated = { ...rows[0], runs: rows.length };
  for (const field of fields) {
    const values = rows.map((row) => row[field]);
    if (values.every((value) => value === undefined)) {
      aggregated[field] = undefined;
    } else {
      aggregated[field] = median(values);
    }
  }
  aggregated.spread = {
    docsPerSecond: range(rows.map((row) => row.docsPerSecond)),
    totalMsMedian: range(rows.map((row) => row.totalMsMedian)),
    firstAnswerMs: range(rows.map((row) => row.firstAnswerMs)),
  };
  return aggregated;
});

const payload = {
  result: {
    results,
    runs: runs.length,
    corpusDocs: first.corpusDocs,
    chunks: first.chunks,
    queries: first.queries,
    probe: first.probe,
    userAgent: first.userAgent,
    at: first.at,
    aggregation: "median of 3 runs; quality metrics are deterministic",
  },
  runFiles: [1, 2, 3].map((id) => `bench-${id}.json`),
};

await writeFile(
  "bench/results/phase4/bench.json",
  JSON.stringify(payload, null, 2),
);
await copyFile("bench/results/phase4/bench.json", "public/bench/phase4.json");
await copyFile("bench/results/phase4/bench-3.png", "bench/results/phase4/bench.png").catch(
  () => undefined,
);

console.log("aggregated 3 runs");
for (const row of results) {
  console.log(
    [
      row.id,
      `docs/s=${row.docsPerSecond?.toFixed(1)}`,
      `first=${Math.round(row.firstAnswerMs)}ms`,
      `e2e=${row.totalMsMedian?.toFixed(1)}ms`,
      `nDCG=${row.ndcg5?.toFixed(3)}`,
      `J=${row.jaccard10VsBaseline?.toFixed(3) ?? "baseline"}`,
    ].join("  "),
  );
}
