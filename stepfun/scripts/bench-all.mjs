#!/usr/bin/env node
// Run the benchmark three times (separate browser sessions) and aggregate the
// medians. Kept in Node so it works in PowerShell and POSIX shells alike.
import { spawnSync } from "node:child_process";

for (const id of [1, 2, 3]) {
  console.log(`\n=== benchmark run ${id}/3 ===`);
  const result = spawnSync(process.execPath, ["scripts/bench-playwright.mjs"], {
    stdio: "inherit",
    env: { ...process.env, RUN_ID: String(id) },
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

await import("./aggregate-bench.mjs");
await import("./check-saturation.mjs");
