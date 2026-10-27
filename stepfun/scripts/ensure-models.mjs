#!/usr/bin/env node
// Make `pnpm dev` / `pnpm build` self-contained on a fresh checkout: if the
// ONNX files are missing, fetch them before Vite starts. This avoids a 404 on
// /models/... when an automated runner does not read README and run `pnpm setup`.
import { existsSync } from "node:fs";

const base = "public/models/Xenova/bge-small-zh-v1.5";
const files = [
  `${base}/config.json`,
  `${base}/tokenizer.json`,
  `${base}/onnx/model.onnx`,
  `${base}/onnx/model_fp16.onnx`,
  `${base}/onnx/model_int8.onnx`,
];

if (files.every((file) => existsSync(file))) {
  console.log("[models] present");
  process.exit(0);
}

console.log("[models] missing; downloading before start/build...");
await import("./fetch-models.mjs");
