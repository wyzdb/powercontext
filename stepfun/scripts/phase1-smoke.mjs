#!/usr/bin/env node
// Phase 1 smoke test: create a KB, insert three Chinese documents with
// hand-made 512-d unit vectors, refresh, run one hybrid query, then dump the
// SQL trace and the actual DDL. It intentionally does not use an embedding
// model: this tests the seekdb data layer in isolation.
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:8787";

async function request(method, path, body) {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!response.ok) {
    throw new Error(`${method} ${path} -> ${response.status}: ${text}`);
  }
  return data;
}

const post = (path, body) => request("POST", path, body);
const get = (path) => request("GET", path);

function unit(index) {
  return Array.from({ length: 512 }, (_, i) => (i === index ? 1 : 0));
}

const kb = await post("/api/kbs", {
  name: `Smoke Test KB ${new Date().toISOString().slice(11, 19)}`,
  modelId: "Xenova/bge-small-zh-v1.5",
  dim: 512,
  dtype: "int8",
});
console.log("collection:", kb.id);

const docs = [
  {
    id: "d1",
    text: "苹果手机搭载了自研芯片，续航表现优秀。",
    metadata: { source: "smoke", topic: "phone" },
    embedding: unit(0),
  },
  {
    id: "d2",
    text: "香蕉富含钾元素，是一种常见水果。",
    metadata: { source: "smoke", topic: "fruit" },
    embedding: unit(1),
  },
  {
    id: "d3",
    text: "数据库的向量索引使用 HNSW 算法加速近邻搜索。",
    metadata: { source: "smoke", topic: "db" },
    embedding: unit(2),
  },
];

const inserted = await post(`/api/kbs/${kb.id}/docs`, { docs });
console.log("insert:", inserted);
const refreshed = await post(`/api/kbs/${kb.id}/refresh`, {});
console.log("refresh:", refreshed);

const search = await post(`/api/kbs/${kb.id}/search`, {
  query: "苹果手机",
  embedding: unit(0),
  topK: 5,
  rankConstant: 60,
  rankWindowSize: 50,
});
console.log("search hits:");
for (const hit of search.hits) {
  console.log(`  #${hit.rank} ${hit.id} score=${hit.score} ${hit.text}`);
}
console.log("dbMs:", search.dbMs, "traceId:", search.traceId);

const trace = await get(`/api/trace/${search.traceId}`);
const hybridSql = trace.entries.find((entry) =>
  /_keyword_rank|_semantic_rank|RANK\(\) over/i.test(entry.sql),
);
console.log("\nhybrid SQL entry:");
console.log(JSON.stringify(hybridSql ?? trace.entries, null, 2).slice(0, 6000));

const ddl = await get(`/api/kbs/${kb.id}/ddl`);
console.log("\nDDL:", ddl.physicalTable);
console.log(ddl.createTable);
console.log("indexes:", ddl.indexes.map((index) => index.Key_name ?? index.key_name));

const report = { kb, inserted, refreshed, search, trace: trace.entries, ddl };
const { writeFile } = await import("node:fs/promises");
await writeFile(
  new URL("../bench/results/phase1/smoke.json", import.meta.url),
  JSON.stringify(report, null, 2),
);
console.log("\nwrote bench/results/phase1/smoke.json");
