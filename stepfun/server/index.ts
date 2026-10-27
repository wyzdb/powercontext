import { existsSync } from "node:fs";
import path from "node:path";
import fastifyStatic from "@fastify/static";
import Fastify from "fastify";
import { registerRoutes } from "./routes.js";
import { closeClient } from "./seekdb.js";

const app = Fastify({
  logger: {
    level: process.env.LOG_LEVEL ?? "info",
    transport:
      process.env.NODE_ENV === "production"
        ? undefined
        : { target: "pino-pretty", options: { translateTime: "HH:MM:ss" } },
  },
  bodyLimit: 64 * 1024 * 1024,
});

const distDir = path.join(process.cwd(), "dist");
const indexHtml = path.join(distDir, "index.html");
const hasDist = existsSync(indexHtml);

if (hasDist) {
  await app.register(fastifyStatic, {
    root: distDir,
    prefix: "/",
    wildcard: false,
  });
}

app.setErrorHandler((error, request, reply) => {
  const err = error as { name?: string; message: string; statusCode?: unknown };
  const statusCode =
    typeof err.statusCode === "number" ? err.statusCode : 500;
  request.log.error({ err: error }, "request failed");
  reply.code(statusCode).send({
    error: err.name ?? "Error",
    message: err.message,
  });
});

await registerRoutes(app);

app.setNotFoundHandler((request, reply) => {
  if (request.url.startsWith("/api/")) {
    return reply.code(404).send({ error: "NotFound", message: "API not found" });
  }
  if (hasDist) {
    return reply.type("text/html").sendFile("index.html");
  }
  return reply
    .code(404)
    .send({ error: "NotFound", message: "前端尚未构建，开发时请访问 Vite 端口" });
});

const port = Number(process.env.PORT ?? 8787);
await app.listen({ port, host: "127.0.0.1" });
app.log.info(`BFF listening on http://127.0.0.1:${port}`);

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    void app
      .close()
      .then(() => closeClient())
      .finally(() => process.exit(0));
  });
}
