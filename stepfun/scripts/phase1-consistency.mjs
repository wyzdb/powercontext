#!/usr/bin/env node
// Phase 1 consistency checks: async vector index visibility before/after
// refresh, incremental import, collection switching, and deletion.
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:8787";

async function request(method, path, body) {
  const response = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw new Error(`${method} ${path} -> ${response.status}: ${text}`);
  return data;
}
const post = (path, body) => request("POST", path, body);
const get = (path) => request("GET", path);
const del = (path) => request("DELETE", path);
const unit = (index) =>
  Array.from({ length: 512 }, (_, i) => (i === index ? 1 : 0));

const { readFile, writeFile } = await import("node:fs/promises");
const previous = JSON.parse(
  await readFile(
    new URL("../bench/results/phase1/smoke.json", import.meta.url),
    "utf8",
  ),
);
const kbA = previous.kb.id;
console.log("KB A:", kbA);

const search = (id, query, embedding) =>
  post(`/api/kbs/${id}/search`, {
    query,
    embedding,
    topK: 10,
    rankConstant: 60,
    rankWindowSize: 50,
  });

const d4 = {
  id: "d4",
  text: "云计算平台通过虚拟化技术提供弹性计算资源。",
  metadata: { source: "consistency", topic: "cloud" },
  embedding: unit(3),
};
const d5 = {
  id: "d5",
  text: "容器编排让多个微服务可以自动扩缩容。",
  metadata: { source: "consistency", topic: "cloud" },
  embedding: unit(4),
};

// 1. Async HNSW visibility: vector-only query before/after refresh.
await post(`/api/kbs/${kbA}/docs`, { docs: [d4] });
const beforeRefresh = await search(kbA, "", unit(3));
const refresh = await post(`/api/kbs/${kbA}/refresh`, {});
const afterRefresh = await search(kbA, "", unit(3));
const visibleBefore = beforeRefresh.hits.some((hit) => hit.id === "d4");
const visibleAfter = afterRefresh.hits.some((hit) => hit.id === "d4");
console.log("refresh semantics:", { visibleBefore, visibleAfter, refresh });

// 2. Incremental import: another doc, one refresh, count grows.
const beforeCount = (await get(`/api/kbs`)).kbs.find((kb) => kb.id === kbA).count;
await post(`/api/kbs/${kbA}/docs`, { docs: [d5] });
await post(`/api/kbs/${kbA}/refresh`, {});
const afterCount = (await get(`/api/kbs`)).kbs.find((kb) => kb.id === kbA).count;
const afterIncremental = await search(kbA, "容器编排", unit(4));
console.log("incremental:", { beforeCount, afterCount, top: afterIncremental.hits[0] });

// 3. Collection switching: a second KB must not leak into the first.
const kbB = await post("/api/kbs", {
  name: `Consistency B ${Date.now()}`,
  modelId: "Xenova/bge-small-zh-v1.5",
  dim: 512,
  dtype: "int8",
});
await post(`/api/kbs/${kbB.id}/docs`, {
  docs: [
    {
      id: "b1",
      text: "量子计算利用量子比特实现并行计算。",
      metadata: { source: "consistency-b" },
      embedding: unit(5),
    },
  ],
});
await post(`/api/kbs/${kbB.id}/refresh`, {});
const queryB = await search(kbB.id, "量子计算", unit(5));
const crossTalk = await search(kbA, "量子计算", unit(5));
console.log("switching:", {
  kbBTop: queryB.hits[0],
  kbATop: crossTalk.hits[0],
  leaked: crossTalk.hits.some((hit) => hit.id === "b1"),
});

// 4. Deletion: collection and manifest row must both disappear.
await del(`/api/kbs/${kbB.id}`);
const listAfterDelete = await get("/api/kbs");
const stillListed = listAfterDelete.kbs.some((kb) => kb.id === kbB.id);
let lookupAfterDelete;
try {
  await search(kbB.id, "量子计算", unit(5));
  lookupAfterDelete = "unexpectedly-succeeded";
} catch (error) {
  lookupAfterDelete = String(error.message).slice(0, 120);
}
console.log("deletion:", { stillListed, lookupAfterDelete });

const report = {
  kbA,
  refreshSemantics: {
    visibleBefore,
    visibleAfter,
    refreshMs: refresh.ms,
    beforeHits: beforeRefresh.hits.map((hit) => hit.id),
    afterHits: afterRefresh.hits.map((hit) => hit.id),
  },
  incremental: { beforeCount, afterCount, top: afterIncremental.hits[0] },
  switching: {
    kbB: kbB.id,
    kbBTop: queryB.hits[0],
    kbATop: crossTalk.hits[0],
    leaked: crossTalk.hits.some((hit) => hit.id === "b1"),
  },
  deletion: { stillListed, lookupAfterDelete },
};
await writeFile(
  new URL("../bench/results/phase1/consistency.json", import.meta.url),
  JSON.stringify(report, null, 2),
);
console.log("\nwrote bench/results/phase1/consistency.json");
