#!/usr/bin/env node
// Copy the ORT Web WASM runtime into public/ort so Vite serves it as a normal
// static asset. Keeping this out of vite.config avoids dev-server middleware
// differences between Vite versions.
import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";

const source = path.resolve("node_modules/onnxruntime-web/dist");
const target = path.resolve("public/ort");
const files = [
  "ort-wasm-simd-threaded.jsep.wasm",
  "ort-wasm-simd-threaded.jsep.mjs",
  "ort-wasm-simd-threaded.wasm",
  "ort-wasm-simd-threaded.mjs",
];

await mkdir(target, { recursive: true });
for (const file of files) {
  await copyFile(path.join(source, file), path.join(target, file));
}
console.log(`[prepare-ort] copied ${files.length} files to public/ort`);
