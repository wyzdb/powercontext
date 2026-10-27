#!/usr/bin/env node
// Run the /benchrun page (fp32/wasm, int8/wasm, fp16/webgpu) and capture the
// structured quality + latency result. Headful Chrome is used for WebGPU.
import { mkdir, writeFile } from "node:fs/promises";
import { chromium } from "@playwright/test";

const browser = await chromium.launch({
  channel: "chrome",
  headless: false,
  args: [
    "--enable-unsafe-webgpu",
    "--enable-webgpu-developer-features",
    "--disable-webgpu-blocklist",
  ],
});

const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const logs = [];
page.on("console", (message) => {
  if (message.type() === "error") logs.push(`[console] ${message.text()}`);
});
page.on("pageerror", (error) => logs.push(`[pageerror] ${error.message}`));

await page.goto("http://127.0.0.1:5173/benchrun", {
  waitUntil: "networkidle",
});
await page.getByRole("button", { name: "运行全部配置" }).click();
await page.waitForFunction(() => window.__BENCH_RESULT__ !== undefined, null, {
  timeout: 600_000,
});
const result = await page.evaluate(() => window.__BENCH_RESULT__);

await mkdir("bench/results/phase4", { recursive: true });
await writeFile(
  "bench/results/phase4/bench.json",
  JSON.stringify({ result, logs }, null, 2),
);
await page.screenshot({
  path: "bench/results/phase4/bench.png",
  fullPage: true,
});

console.log(JSON.stringify(result, null, 2));
console.log("\n--- logs ---");
console.log(logs.join("\n") || "(no console errors)");
await browser.close();
console.log("\nwrote bench/results/phase4/bench.json and bench.png");
