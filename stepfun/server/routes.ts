import type { FastifyInstance } from "fastify";
import { z } from "zod";
import {
  addDocs,
  createKb,
  deleteKb,
  getKbDdl,
  health,
  listKbs,
  refreshKb,
  searchKb,
} from "./seekdb.js";
import { createTraceId, getTrace, withTrace } from "./trace.js";

const Dtype = z.enum(["fp32", "int8", "fp16"]);

const CreateKbBody = z.object({
  name: z.string().min(1).max(80),
  modelId: z.string().min(1).max(200),
  dim: z.number().int().min(1).max(4096),
  dtype: Dtype,
});

const DocBody = z.object({
  docs: z
    .array(
      z.object({
        id: z.string().min(1).max(200),
        text: z.string().min(1).max(20000),
        metadata: z.record(z.string(), z.unknown()).optional(),
        embedding: z.array(z.number().finite()).min(1).max(4096),
      }),
    )
    .min(1)
    .max(512),
});

const SearchBody = z.object({
  query: z.string().max(2000).default(""),
  embedding: z.array(z.number().finite()).min(1).max(4096),
  topK: z.number().int().min(1).max(50).default(10),
  rankConstant: z.number().int().min(1).max(1000).default(60),
  rankWindowSize: z.number().int().min(1).max(200).default(50),
});

function parseBody<T>(schema: z.ZodType<T>, body: unknown): T {
  const result = schema.safeParse(body);
  if (!result.success) {
    const detail = result.error.issues
      .map((issue) => `${issue.path.join(".") || "body"}: ${issue.message}`)
      .join("; ");
    const error = new Error(`请求参数不合法：${detail}`) as Error & {
      statusCode?: number;
    };
    error.statusCode = 400;
    throw error;
  }
  return result.data;
}

function paramId(params: unknown): string {
  const id = (params as { id?: string }).id;
  if (!id) {
    const error = new Error("缺少 collection id") as Error & {
      statusCode?: number;
    };
    error.statusCode = 400;
    throw error;
  }
  return id;
}

export async function registerRoutes(app: FastifyInstance): Promise<void> {
  app.get("/api/health", async () => health());

  app.get("/api/kbs", async () => ({ kbs: await listKbs() }));

  app.post("/api/kbs", async (request, reply) => {
    const input = parseBody(CreateKbBody, request.body);
    const kb = await createKb(input);
    return reply.code(201).send(kb);
  });

  app.delete("/api/kbs/:id", async (request) => {
    await deleteKb(paramId(request.params));
    return { ok: true };
  });

  app.post("/api/kbs/:id/docs", async (request) => {
    const id = paramId(request.params);
    const { docs } = parseBody(DocBody, request.body);
    return addDocs(id, docs);
  });

  app.post("/api/kbs/:id/refresh", async (request) => {
    const id = paramId(request.params);
    return refreshKb(id);
  });

  app.post("/api/kbs/:id/search", async (request) => {
    const id = paramId(request.params);
    const input = parseBody(SearchBody, request.body);
    const traceId = createTraceId();
    const result = await withTrace(traceId, () => searchKb(id, input));
    return { ...result, traceId };
  });

  app.get("/api/trace/:id", async (request) => {
    const traceId = paramId(request.params);
    return { traceId, entries: getTrace(traceId) };
  });

  app.get("/api/kbs/:id/ddl", async (request) => {
    const id = paramId(request.params);
    return getKbDdl(id);
  });
}
