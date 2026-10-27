#!/usr/bin/env node
// Download the native seekdb binding without loading it. Loading the .so/.dylib
// requires libaio/LD_PRELOAD; downloading does not. Doing this in `pnpm setup`
// avoids the first-start race where run-embedded.sh cannot find libseekdb.so.
import path from "node:path";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

if (process.platform === "win32") {
  console.log("[seekdb] Windows does not support embedded seekdb; skip binding.");
  process.exit(0);
}

const require = createRequire(import.meta.url);

try {
  const entry = require.resolve("@seekdb/js-bindings");
  const downloadFile = path.join(path.dirname(entry), "download.js");
  const mod = await import(pathToFileURL(downloadFile).href);
  const ensure =
    mod.ensureBindingsDownloaded ?? mod.default?.ensureBindingsDownloaded;
  if (typeof ensure !== "function") {
    throw new Error("ensureBindingsDownloaded not found in @seekdb/js-bindings");
  }
  const dir = await ensure();
  console.log(`[seekdb] embedded binding ready: ${dir}`);
} catch (error) {
  console.error(`[seekdb] binding download failed: ${String(error)}`);
  console.error("[seekdb] server mode (Docker/WSL) does not need this binding.");
  process.exitCode = 1;
}
