#!/usr/bin/env node
// Download the ONNX files for Xenova/bge-small-zh-v1.5 into public/models.
// The model is MIT-licensed; this script only mirrors the exact revision used
// in the benchmark and verifies every file against a known SHA-256.
import { createHash } from "node:crypto";
import { createReadStream, createWriteStream, existsSync } from "node:fs";
import { mkdir, rename, stat, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";

const MODEL_ID = "Xenova/bge-small-zh-v1.5";
const REVISION = "75c43b069aac4d136ba6bc1122f995fedcfd2781";
const ENDPOINT = (process.env.HF_ENDPOINT ?? "https://huggingface.co").replace(/\/$/, "");
const TARGET = path.resolve("public/models", MODEL_ID);

const FILES = [
  { file: "config.json", bytes: 716, sha256: "d4193ead3a810fd694fa8a31d7fc72fbaebc0668b603e398734bf2f6538ff42f" },
  { file: "quantize_config.json", bytes: 674, sha256: "2cc488b20fa05fe86aba2fdc2be44d24827e11e2b7c7a0753d1427da6797b46f" },
  { file: "special_tokens_map.json", bytes: 125, sha256: "b6d346be366a7d1d48332dbc9fdf3bf8960b5d879522b7799ddba59e76237ee3" },
  { file: "tokenizer.json", bytes: 439125, sha256: "48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26" },
  { file: "tokenizer_config.json", bytes: 367, sha256: "e6f3b96db926a37d4039995fbf5ad17de158dfb8f6343d607e4dbaad18d75f5a" },
  { file: "vocab.txt", bytes: 109540, sha256: "45bbac6b341c319adc98a532532882e91a9cefc0329aa57bac9ae761c27b291c" },
  { file: "onnx/model.onnx", bytes: 94851877, sha256: "69a0b846f4f116b5e6aabf9546ea6754d02264f3211a13a1bd69b31b8040749a" },
  { file: "onnx/model_fp16.onnx", bytes: 47497427, sha256: "60d0fe5eb8d4e251d4b24dff010a2625c10a013503f0d09f625e8a9b0311315f" },
  { file: "onnx/model_int8.onnx", bytes: 23903394, sha256: "b9837c19ce154ff0726d398ee77abbc03a7faf0476c6f93016c84e531be7ebb5" },
];

async function sha256File(file) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

async function download(file) {
  const destination = path.join(TARGET, file.file);
  const response = await fetch(
    `${ENDPOINT}/${MODEL_ID}/resolve/${REVISION}/${file.file}`,
    { redirect: "follow" },
  );
  if (!response.ok || !response.body) {
    throw new Error(`${file.file}: HTTP ${response.status}`);
  }
  await mkdir(path.dirname(destination), { recursive: true });
  const temporary = `${destination}.part`;
  await pipeline(
    Readable.fromWeb(response.body),
    createWriteStream(temporary),
  );
  await rename(temporary, destination);
}

for (const file of FILES) {
  const destination = path.join(TARGET, file.file);
  let valid = false;
  if (existsSync(destination)) {
    const info = await stat(destination);
    valid =
      info.size === file.bytes &&
      (await sha256File(destination)) === file.sha256;
  }
  if (valid) {
    console.log(`[models] ok ${file.file}`);
    continue;
  }
  if (existsSync(destination)) await unlink(destination);
  console.log(`[models] download ${file.file} (${(file.bytes / 1024 / 1024).toFixed(1)} MiB)`);
  await download(file);
  const info = await stat(destination);
  if (info.size !== file.bytes) {
    throw new Error(
      `${file.file}: size mismatch, expected ${file.bytes}, got ${info.size}`,
    );
  }
  const digest = await sha256File(destination);
  if (digest !== file.sha256) {
    throw new Error(`${file.file}: sha256 mismatch (${digest})`);
  }
}

const manifest = {
  modelId: MODEL_ID,
  baseModel: "BAAI/bge-small-zh-v1.5",
  revision: REVISION,
  license: "MIT",
  dimension: 512,
  maxLength: 512,
  files: FILES.map((file) => ({
    path: file.file,
    bytes: file.bytes,
    sha256: file.sha256,
  })),
  downloadedAt: new Date().toISOString(),
};
await writeFile(
  path.join(TARGET, "manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
);
console.log(`[models] wrote ${path.join(TARGET, "manifest.json")}`);
console.log("[models] done");
