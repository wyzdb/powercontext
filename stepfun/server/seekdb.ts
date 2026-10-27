import { createHash } from "node:crypto";
import { performance } from "node:perf_hooks";
import {
  FulltextIndexConfig,
  Schema,
  SeekdbAdminClient,
  SeekdbClient,
  VectorIndexConfig,
  type Metadata,
} from "seekdb";
import { connectionHints, loadConfig, type AppConfig } from "./config.js";
import { recordTrace } from "./trace.js";

export type Dtype = "fp32" | "int8" | "fp16";

type SqlRow = Record<string, unknown>;

export interface KbInput {
  name: string;
  modelId: string;
  dim: number;
  dtype: Dtype;
}

export interface KbRecord extends KbInput {
  id: string;
  createdAt: string;
  count: number;
  missing?: boolean;
}

export interface DocInput {
  id: string;
  text: string;
  metadata?: Record<string, unknown>;
  embedding: number[];
}

export interface SearchInput {
  query: string;
  embedding: number[];
  topK: number;
  rankConstant: number;
  rankWindowSize: number;
}

export interface SearchHit {
  id: string;
  text: string;
  metadata: Metadata | null;
  score: number;
  rank: number;
}

export interface SearchOutput {
  hits: SearchHit[];
  dbMs: number;
  degraded?: "vector-only";
  warning?: string;
}

let clientPromise: Promise<SeekdbClient> | null = null;
let lastError: string | null = null;
const adminClients: SeekdbAdminClient[] = [];

export function buildSchema(dim: number): Schema {
  return new Schema({
    vectorIndex: new VectorIndexConfig({
      hnsw: {
        dimension: dim,
        distance: "cosine",
        m: 16,
        ef_construction: 200,
        ef_search: 64,
      },
      // 关键：向量必须由浏览器算好后传入，禁止 seekdb 侧再调用 embedding 服务。
      embeddingFunction: null,
    }),
    fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),
  });
}

function instrument(client: SeekdbClient): void {
  const delegate = (client as unknown as { _delegate?: Record<string, unknown> })
    ._delegate;
  if (!delegate) return;

  for (const key of ["_internal", "_adminInternal"]) {
    const internal = delegate[key] as
      | {
          execute?: (sql: string, params?: unknown[]) => Promise<unknown>;
          __traceWrapped?: boolean;
        }
      | undefined;
    if (!internal?.execute || internal.__traceWrapped) continue;

    const original = internal.execute.bind(internal);
    internal.execute = async (sql: string, params?: unknown[]) => {
      const started = performance.now();
      try {
        const rows = await original(sql, params);
        recordTrace({
          sql,
          params,
          ms: Number((performance.now() - started).toFixed(3)),
          rows: Array.isArray(rows) ? rows.length : undefined,
        });
        return rows;
      } catch (error) {
        recordTrace({
          sql,
          params,
          ms: Number((performance.now() - started).toFixed(3)),
          error: error instanceof Error ? error.message : String(error),
        });
        throw error;
      }
    };
    internal.__traceWrapped = true;
  }
}

async function connectEmbedded(config: AppConfig): Promise<SeekdbClient> {
  const admin = new SeekdbAdminClient({ path: config.embeddedPath });
  adminClients.push(admin);
  await admin.createDatabase(config.database);

  const client = new SeekdbClient({
    path: config.embeddedPath,
    database: config.database,
  });
  instrument(client);
  return client;
}

async function connectServer(config: AppConfig): Promise<SeekdbClient> {
  const base = {
    host: config.host,
    port: config.port,
    user: config.user,
    password: config.password,
    ...(config.tenant ? { tenant: config.tenant } : {}),
  };

  const admin = new SeekdbAdminClient(base);
  adminClients.push(admin);
  await admin.createDatabase(config.database);

  const client = new SeekdbClient({ ...base, database: config.database });
  instrument(client);
  return client;
}

async function connect(): Promise<SeekdbClient> {
  const config = loadConfig();

  if (config.mode === "embedded") return connectEmbedded(config);
  if (config.mode === "server") return connectServer(config);

  if (process.platform === "win32") {
    return connectServer(config).catch((error: unknown) => {
      throw new Error(
        `Windows 原生运行时不支持 seekdb 嵌入式模式；请先启动 Docker/WSL 本地 server。\n${connectionHints(config).join("\n")}\n原始错误：${String(error)}`,
      );
    });
  }

  try {
    return await connectEmbedded(config);
  } catch (embeddedError) {
    try {
      return await connectServer(config);
    } catch (serverError) {
      throw new Error(
        `无法连接 seekdb。\n嵌入式错误：${String(embeddedError)}\nserver 错误：${String(serverError)}\n${connectionHints(config).join("\n")}`,
      );
    }
  }
}

export async function getClient(): Promise<SeekdbClient> {
  if (!clientPromise) {
    clientPromise = connect()
      .then(async (client) => {
        await bootstrap(client);
        lastError = null;
        return client;
      })
      .catch((error: unknown) => {
        clientPromise = null;
        lastError = error instanceof Error ? error.message : String(error);
        throw error;
      });
  }
  return clientPromise;
}

export async function closeClient(): Promise<void> {
  if (clientPromise) {
    try {
      const client = await clientPromise;
      await client.close();
    } finally {
      clientPromise = null;
    }
  }
  await Promise.allSettled(adminClients.map((admin) => admin.close()));
  adminClients.length = 0;
}

async function bootstrap(client: SeekdbClient): Promise<void> {
  await client.execute(`
    CREATE TABLE IF NOT EXISTS kb_manifest (
      collection_name VARCHAR(191) NOT NULL PRIMARY KEY,
      display_name VARCHAR(191) NOT NULL,
      model_id VARCHAR(191) NOT NULL,
      dim INT NOT NULL,
      dtype VARCHAR(16) NOT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
  `);
}

export async function health(): Promise<Record<string, unknown>> {
  const config = loadConfig();
  const started = performance.now();
  try {
    const client = await getClient();
    const rows = (await client.execute(
      "SELECT VERSION() AS version",
    )) as SqlRow[] | null;
    const row = rows?.[0];
    return {
      ok: true,
      mode: config.mode,
      database: config.database,
      target: config.mode === "server" ? `${config.host}:${config.port}` : config.embeddedPath,
      version: String(row?.version ?? row?.VERSION ?? "unknown"),
      connectMs: Number((performance.now() - started).toFixed(1)),
    };
  } catch (error) {
    return {
      ok: false,
      mode: config.mode,
      database: config.database,
      target: config.mode === "server" ? `${config.host}:${config.port}` : config.embeddedPath,
      error: error instanceof Error ? error.message : String(error),
      lastError,
      hints: connectionHints(config),
      connectMs: Number((performance.now() - started).toFixed(1)),
    };
  }
}

function slugify(name: string): string {
  const ascii = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 24);
  const digest = createHash("sha1").update(name).digest("hex").slice(0, 6);
  return ascii || digest;
}

async function uniqueCollectionName(
  client: SeekdbClient,
  base: string,
): Promise<string> {
  let candidate = base;
  for (let i = 2; i < 50; i += 1) {
    if (!(await client.hasCollection(candidate))) return candidate;
    candidate = `${base}_${i}`;
  }
  throw new Error(`无法为 ${base} 生成唯一的 collection 名称`);
}

export async function createKb(input: KbInput): Promise<KbRecord> {
  const client = await getClient();
  const base = `kb_${slugify(input.name)}_${input.dtype}`;
  const id = await uniqueCollectionName(client, base);

  await client.createCollection({ name: id, schema: buildSchema(input.dim) });
  await client.execute(
    `INSERT INTO kb_manifest
      (collection_name, display_name, model_id, dim, dtype)
     VALUES (?, ?, ?, ?, ?)`,
    [id, input.name, input.modelId, input.dim, input.dtype],
  );

  return {
    id,
    name: input.name,
    modelId: input.modelId,
    dim: input.dim,
    dtype: input.dtype,
    createdAt: new Date().toISOString(),
    count: 0,
  };
}

export async function listKbs(): Promise<KbRecord[]> {
  const client = await getClient();
  const rows = (await client.execute(
    "SELECT collection_name, display_name, model_id, dim, dtype, created_at FROM kb_manifest ORDER BY created_at DESC",
  )) as SqlRow[] | null;

  const records: KbRecord[] = [];
  for (const raw of rows ?? []) {
    const row = raw;
    const id = String(row.collection_name);
    let count = 0;
    let missing = false;
    try {
      const collection = await client.getCollection({
    name: id,
    // getCollection 在没有显式 embeddingFunction 时会回退到 default-embed，
    // 而本应用禁止数据库侧 embedding。显式传 null 才能保持“向量只来自浏览器”。
    embeddingFunction: null,
  });
      count = await collection.count();
    } catch {
      missing = true;
    }
    records.push({
      id,
      name: String(row.display_name),
      modelId: String(row.model_id),
      dim: Number(row.dim),
      dtype: String(row.dtype) as Dtype,
      createdAt: new Date(row.created_at as string).toISOString(),
      count,
      missing,
    });
  }
  return records;
}

async function getKbRow(id: string): Promise<SqlRow> {
  const client = await getClient();
  const rows = (await client.execute(
    "SELECT collection_name, display_name, model_id, dim, dtype FROM kb_manifest WHERE collection_name = ?",
    [id],
  )) as SqlRow[] | null;
  const row = rows?.[0];
  if (!row) throw new Error(`知识库不存在：${id}`);
  return row;
}

export async function deleteKb(id: string): Promise<void> {
  const client = await getClient();
  await getKbRow(id);
  await client.deleteCollection(id);
  await client.execute("DELETE FROM kb_manifest WHERE collection_name = ?", [id]);
}

export async function addDocs(
  id: string,
  docs: DocInput[],
): Promise<{ inserted: number; ms: number }> {
  if (docs.length === 0) return { inserted: 0, ms: 0 };
  const client = await getClient();
  const row = await getKbRow(id);
  const dim = Number(row.dim);

  for (const doc of docs) {
    if (doc.embedding.length !== dim) {
      throw new Error(
        `向量维度不匹配：collection ${id} 期望 ${dim}，收到 ${doc.embedding.length}`,
      );
    }
    let norm = 0;
    for (const value of doc.embedding) norm += value * value;
    norm = Math.sqrt(norm);
    if (!Number.isFinite(norm) || Math.abs(norm - 1) > 0.02) {
      throw new Error(
        `向量未归一化（L2=${norm.toFixed(4)}）。端侧编码器必须在 normalize:true 下输出单位向量。`,
      );
    }
  }

  const collection = await client.getCollection({
    name: id,
    // getCollection 在没有显式 embeddingFunction 时会回退到 default-embed，
    // 而本应用禁止数据库侧 embedding。显式传 null 才能保持“向量只来自浏览器”。
    embeddingFunction: null,
  });
  const started = performance.now();
  const batchSize = 64;
  for (let offset = 0; offset < docs.length; offset += batchSize) {
    const batch = docs.slice(offset, offset + batchSize);
    await collection.upsert({
      ids: batch.map((doc) => doc.id),
      embeddings: batch.map((doc) => doc.embedding),
      documents: batch.map((doc) => doc.text),
      metadatas: batch.map((doc) => (doc.metadata ?? {}) as Metadata),
    });
  }
  await client.execute(
    "UPDATE kb_manifest SET updated_at = CURRENT_TIMESTAMP WHERE collection_name = ?",
    [id],
  );

  return {
    inserted: docs.length,
    ms: Number((performance.now() - started).toFixed(1)),
  };
}

export async function refreshKb(
  id: string,
): Promise<{ ms: number; count: number }> {
  const client = await getClient();
  await getKbRow(id);
  const collection = await client.getCollection({
    name: id,
    // getCollection 在没有显式 embeddingFunction 时会回退到 default-embed，
    // 而本应用禁止数据库侧 embedding。显式传 null 才能保持“向量只来自浏览器”。
    embeddingFunction: null,
  });
  const started = performance.now();
  await collection.refresh_index();
  const count = await collection.count();
  return {
    ms: Number((performance.now() - started).toFixed(1)),
    count,
  };
}

const LUCENE_SPECIAL = /([+\-&|!(){}[\]^"~*?:\\/])/g;

function escapeFulltext(query: string): string {
  return query.replace(LUCENE_SPECIAL, "\\$1").trim();
}

function isFulltextSyntaxError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /query_string|fulltext|full text|syntax|parse|MATCH/i.test(message);
}

function mapHits(
  result: {
    ids: readonly (readonly string[])[];
    documents?: readonly (readonly (string | null)[])[];
    metadatas?: readonly (readonly (Metadata | null)[])[];
    distances?: readonly (readonly (number | null)[])[];
  },
  topK: number,
): SearchHit[] {
  const ids = result.ids[0] ?? [];
  const documents = result.documents?.[0] ?? [];
  const metadatas = result.metadatas?.[0] ?? [];
  const distances = result.distances?.[0] ?? [];

  return ids.slice(0, topK).map((id, index) => ({
    id: String(id),
    text: documents[index] ?? "",
    metadata: metadatas[index] ?? null,
    score: Number(distances[index] ?? 0),
    rank: index + 1,
  }));
}

export async function searchKb(
  id: string,
  input: SearchInput,
): Promise<SearchOutput> {
  const client = await getClient();
  const row = await getKbRow(id);
  const dim = Number(row.dim);
  if (input.embedding.length !== dim) {
    throw new Error(
      `查询向量维度不匹配：collection ${id} 期望 ${dim}，收到 ${input.embedding.length}`,
    );
  }

  const collection = await client.getCollection({
    name: id,
    // getCollection 在没有显式 embeddingFunction 时会回退到 default-embed，
    // 而本应用禁止数据库侧 embedding。显式传 null 才能保持“向量只来自浏览器”。
    embeddingFunction: null,
  });
  const topK = Math.min(Math.max(input.topK, 1), 50);
  const rankWindowSize = Math.max(input.rankWindowSize, topK);
  const knnResults = Math.max(topK * 5, rankWindowSize);

  const baseOptions = {
    knn: { queryEmbeddings: input.embedding, nResults: knnResults },
    rank: {
      rrf: {
        rankConstant: input.rankConstant,
        rankWindowSize,
      },
    },
    nResults: topK,
    include: ["documents", "metadatas", "distances"] as const,
  };

  const query = escapeFulltext(input.query);
  const started = performance.now();

  try {
    const result = query
      ? await collection.hybridSearch({
          ...baseOptions,
          query: { whereDocument: { $contains: query } },
        })
      : await collection.hybridSearch(baseOptions);
    return {
      hits: mapHits(result, topK),
      dbMs: Number((performance.now() - started).toFixed(1)),
    };
  } catch (error) {
    if (!query || !isFulltextSyntaxError(error)) throw error;
    const result = await collection.hybridSearch({
      ...baseOptions,
      nResults: topK,
    });
    return {
      hits: mapHits(result, topK),
      dbMs: Number((performance.now() - started).toFixed(1)),
      degraded: "vector-only",
      warning: `全文查询语法失败，已退回纯向量检索：${
        error instanceof Error ? error.message : String(error)
      }`,
    };
  }
}

export async function getKbDdl(id: string): Promise<{
  physicalTable: string;
  createTable: string;
  createManifest: string;
  indexes: Record<string, unknown>[];
}> {
  const client = await getClient();
  await getKbRow(id);
  const collection = await client.getCollection({
    name: id,
    embeddingFunction: null,
  });
  const collectionId = (
    collection as unknown as { collectionId?: string }
  ).collectionId;
  if (!collectionId) throw new Error(`无法解析 collection 的物理表：${id}`);

  const physicalTable = `c$v2$${collectionId}`;
  const safe = physicalTable.replace(/`/g, "``");
  const tableRows = (await client.execute(
    `SHOW CREATE TABLE \`${safe}\``,
  )) as SqlRow[] | null;
  const manifestRows = (await client.execute(
    "SHOW CREATE TABLE kb_manifest",
  )) as SqlRow[] | null;
  const indexRows = (await client.execute(
    `SHOW INDEX FROM \`${safe}\``,
  )) as SqlRow[] | null;

  const table = tableRows?.[0];
  const manifest = manifestRows?.[0];

  return {
    physicalTable,
    createTable: String(table?.["Create Table"] ?? table?.create_table ?? ""),
    createManifest: String(
      manifest?.["Create Table"] ?? manifest?.create_table ?? "",
    ),
    indexes: (indexRows ?? []) as unknown as Record<string, unknown>[],
  };
}
