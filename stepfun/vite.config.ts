import fs from "node:fs";
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

// ORT Web dynamically imports its Emscripten .mjs glue at runtime. If those
// files live under public/, Vite's dev server rejects the import ("file is in
// /public ... should not be imported"). Serving them through a small
// middleware keeps the raw module and wasm bytes intact in dev; production
// uses the copies made by scripts/prepare-ort.mjs.
function serveOrtAssets(): Plugin {
  const dist = path.resolve("node_modules/onnxruntime-web/dist");
  return {
    name: "serve-ort-assets",
    configureServer(server) {
      server.middlewares.use("/ort", (request, response, next) => {
        const url = (request.url ?? "").split("?")[0];
        const file = path.join(dist, url);
        if (!file.startsWith(dist) || !fs.existsSync(file)) {
          next();
          return;
        }
        response.setHeader(
          "Content-Type",
          file.endsWith(".wasm") ? "application/wasm" : "text/javascript",
        );
        fs.createReadStream(file).pipe(response);
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), serveOrtAssets()],
  server: {
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "require-corp",
    },
    proxy: {
      "/api": "http://127.0.0.1:8787",
    },
  },
  worker: {
    format: "es",
  },
  optimizeDeps: {
    exclude: ["@huggingface/transformers"],
  },
});
