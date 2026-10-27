#!/usr/bin/env node
// Run the /spike page in real Chrome and capture the structured result.
// WebGPU needs a real GPU adapter, so this launches headful Chrome (the system
// Chrome channel) instead of a headless bundled Chromium.
import { copyFile, mkdir, writeFile } from "node:fs/promises";
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

const page = await browser.newPage({ viewport: { width: 1280, height: 960 } });
const logs = [];
page.on("console", (message) => logs.push(`[${message.type()}] ${message.text()}`));
page.on("pageerror", (error) => logs.push(`[pageerror] ${error.message}`));
page.on("response", (response) => {
  if (response.status() >= 400) {
    logs.push(`[http ${response.status()}] ${response.url()}`);
  }
});
page.on("requestfailed", (request) => {
  logs.push(`[failed] ${request.url()} ${request.failure()?.errorText ?? ""}`);
});

await page.goto("http://127.0.0.1:5173/spike", { waitUntil: "networkidle" });
await page.getByRole("button", { name: "运行全部配置" }).click();
await page.waitForFunction(() => window.__SPIKE_RESULT__ !== undefined, null, {
  timeout: 300_000,
});
const result = await page.evaluate(() => window.__SPIKE_RESULT__);

console.log(JSON.stringify(result, null, 2));
console.log("\n--- page logs ---");
console.log(logs.join("\n"));

await mkdir("bench/results/phase2", { recursive: true });
await writeFile(
  "bench/results/phase2/spike.json",
  JSON.stringify({ result, logs }, null, 2),
);
await copyFile(
  "bench/results/phase2/spike.json",
  "public/bench/phase2.json",
);
await page.screenshot({
  path: "bench/results/phase2/spike.png",
  fullPage: false,
  timeout: 60_000,
});
await browser.close();
console.log("\nwrote bench/results/phase2/spike.json and spike.png");
