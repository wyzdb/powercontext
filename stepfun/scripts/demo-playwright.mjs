#!/usr/bin/env node
// End-to-end demo: create a KB, import the bundled sample corpus, run one
// hybrid query, and capture screenshots of the import, results, and SQL trace.
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

await mkdir("bench/results/demo", { recursive: true });

await page.goto("http://127.0.0.1:5173/", { waitUntil: "networkidle" });
await page.getByRole("heading", { name: "本地知识库" }).waitFor();

const hasKb = await page.getByText("把文档变成可检索的片段").count();
if (!hasKb) {
  await page.getByTitle("新建知识库").click();
  await page
    .getByPlaceholder("知识库名称，例如：论文笔记")
    .fill("示例知识库");
  await page.getByRole("button", { name: "创建", exact: true }).click();
}
await page
  .getByText("把文档变成可检索的片段")
  .waitFor({ timeout: 120_000 });

await page.getByRole("button", { name: /加载示例语料/ }).click();
await page.getByText(/20 篇 ·/).waitFor({ timeout: 30_000 });

await page.getByRole("button", { name: "开始导入" }).click();
await page.getByText("合计", { exact: true }).waitFor({ timeout: 180_000 });
await page.screenshot({
  path: "bench/results/demo/import.png",
  fullPage: true,
});

await page.locator("nav").getByRole("button", { name: "检索" }).click();
await page
  .getByPlaceholder("例如：为什么小批量 GPU 推理不一定快？")
  .fill("为什么小批量 GPU 推理不一定快？");
await page.locator("form").getByRole("button", { name: "检索" }).click();
await page.getByText(/条结果/).waitFor({ timeout: 120_000 });
await page.screenshot({
  path: "bench/results/demo/search.png",
  fullPage: true,
});

const resultText = await page.locator("main").innerText();
const firstCard = await page.locator("article").first().innerText();

await page.getByRole("button", { name: "查看 SQL" }).click({ force: true });
await page.getByText("数据库生成的混合检索 SQL").waitFor({ timeout: 30_000 });
await page.screenshot({
  path: "bench/results/demo/sql.png",
  fullPage: true,
});

await writeFile(
  "bench/results/demo/run.json",
  JSON.stringify({ logs, resultText, firstCard }, null, 2),
);
console.log("--- first result ---");
console.log(firstCard);
console.log("--- logs ---");
console.log(logs.join("\n") || "(no console errors)");

await browser.close();
console.log("wrote bench/results/demo/{import,search,sql}.png");
