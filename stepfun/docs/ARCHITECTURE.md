# 架构与接口

## 总览

```
┌──────────────────────── Browser (Chrome / Edge) ────────────────────────┐
│ React UI                                                                 │
│   ├─ 知识库侧栏 / 导入 / 检索 / 基准 / 方法                              │
│   ├─ embedder.ts                                                         │
│   │    ├─ Transformers.js 3.8.1                                          │
│   │    ├─ WebGPU + FP16  (preferred)                                     │
│   │    └─ WASM + INT8    (fallback / forced)                             │
│   └─ fetch('/api/...')                                                   │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │ localhost only (Vite proxy / same origin)
┌──────────────────────────────────▼───────────────────────────────────────┐
│ Node BFF (Fastify, 127.0.0.1:8787)                                       │
│   ├─ /api/health                                                         │
│   ├─ /api/kbs  /api/kbs/:id/docs  /api/kbs/:id/refresh  /api/kbs/:id/ddl │
│   ├─ /api/kbs/:id/search  /api/trace/:id                                 │
│   └─ seekdb-js 1.4.0 + AsyncLocalStorage SQL trace                      │
│        ├─ embedded: path=./.seekdb-data (Linux/macOS)                    │
│        └─ server:   host=127.0.0.1:2881 (Docker / WSL / OceanBase)       │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────┐
│ seekdb 1.4.0                                                             │
│   collection table: _id, document, embedding VECTOR(512), metadata JSON  │
│   index: HNSW(cosine,m=16,ef_construction=200,ef_search=64,ASYNC)        │
│          + FULLTEXT(ik, smart)                                           │
│   query: DBMS_HYBRID_SEARCH.GET_SQL -> RRF SQL -> _score                 │
└──────────────────────────────────────────────────────────────────────────┘
```

## 为什么需要 BFF

`seekdb-js` 是 Node SDK（`mysql2` + 可选原生绑定），浏览器不能直接加载。BFF 只做三件事：把浏览器算好的向量写进 seekdb、调用 refresh、调用 hybridSearch。它不加载模型，也不接受“文本→向量”的请求；`embeddingFunction: null` 在 schema 层禁止数据库侧 embedding。因此“端侧推理”与“seekdb 存储/检索”同时成立。

## 组件

| 文件 | 职责 |
|---|---|
| `server/seekdb.ts` | 连接（embedded/server/auto）、schema、collection CRUD、写入、refresh、hybridSearch、DDL |
| `server/trace.ts` | `AsyncLocalStorage` + 环形缓冲，记录每条 SQL、参数、耗时、行数 |
| `server/routes.ts` | Fastify 路由与 zod 校验 |
| `server/index.ts` | 静态资源、SPA fallback、COOP/COEP、错误处理、优雅退出 |
| `src/lib/embedder.ts` | Transformers.js 加载、dtype/device、warm-up、L2/cosine |
| `src/model/ModelContext.tsx` | 后端探测、自动降级、模型加载状态、query/doc embedding |
| `src/lib/chunk.ts` | 段落/句子分块、内容 hash、JSON 解析、稳定 doc ID |
| `src/lib/api.ts` | 前端 API 类型与 fetch 封装 |
| `src/lib/metrics.ts` | Recall@K、nDCG@K、MRR、Jaccard、Kendall τ |
| `src/benchrun/BenchRun.tsx` | 三配置建库、写入、查询、指标、原始 JSON |
| `bench/results/` | 可提交的原始证据（DDL、SQL trace、指标、截图） |

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | seekdb 连接状态、版本、模式、启动提示 |
| GET | `/api/kbs` | 知识库列表（`kb_manifest` + 实时 count） |
| POST | `/api/kbs` | 创建 collection；body: `{name, modelId, dim, dtype}` |
| DELETE | `/api/kbs/:id` | 删除 collection + manifest 行 |
| POST | `/api/kbs/:id/docs` | 批量 upsert；body: `{docs:[{id,text,metadata,embedding}]}` |
| POST | `/api/kbs/:id/refresh` | `collection.refresh_index()`，返回耗时与 count |
| POST | `/api/kbs/:id/search` | hybridSearch；body: `{query, embedding, topK, rankConstant, rankWindowSize}` |
| GET | `/api/trace/:id` | 某次检索的全部 SQL 语句与耗时 |
| GET | `/api/kbs/:id/ddl` | 物理表 `SHOW CREATE TABLE` 与 `SHOW INDEX` |

## 数据模型

### `kb_manifest`

```sql
CREATE TABLE IF NOT EXISTS kb_manifest (
  collection_name VARCHAR(191) NOT NULL PRIMARY KEY,
  display_name VARCHAR(191) NOT NULL,
  model_id VARCHAR(191) NOT NULL,
  dim INT NOT NULL,
  dtype VARCHAR(16) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

它保存“这个 collection 是由哪个模型/维度/精度构建的”。检索时如果当前编码器与 `dtype` 不一致，界面会提示；不会静默把 INT8 查询向量送进 FP32 知识库。

### collection 物理表

由 seekdb-js 生成，名字是 `c$v2$<collectionId>`，关键列与索引见 [README](../README.md#seekdb-数据层)。`_id` 是 `docId-chunk-contentHash`，写入用 `upsert`，重复导入幂等。

## SQL trace

`server/trace.ts` 用 `AsyncLocalStorage` 把一次请求内的所有 `execute()` 归到同一个 `traceId`。`server/seekdb.ts` 在建立连接后包装 `_delegate._internal.execute` 与 `_adminInternal.execute`，记录：

- SQL 文本、参数
- 起止耗时
- 返回行数 / 错误

`POST /search` 返回 `traceId`；`GET /trace/:id` 返回条目。前端“查看 SQL”优先展示包含 `_keyword_rank`/`_semantic_rank`/`cosine_distance` 的那条（即数据库生成的融合 SQL），而不是 `GET_SQL` 调用本身。

## 状态与一致性

- 当前知识库由 `currentId` 保存；切换时清空查询与结果。
- 导入按 16 条一批：embedding → upsert → 下一批；全部结束后 refresh 一次。
- refresh 前新文档可能不可见（异步 HNSW），UI 把“刷新索引”作为独立阶段展示。
- 删除 collection 会同时删除 `kb_manifest` 行；列表与查询都不会再返回它。
- 模型指纹不匹配时给出警告；不匹配的 `dim` 直接拒绝写入。

## 安全与隐私

- BFF 只绑定 `127.0.0.1`，没有鉴权；这是本机个人应用，不是多用户服务。
- 模型文件自托管；除首次 `pnpm models:fetch` 外，运行时不向外部发送文本或向量。
- collection 名经过 slug + hash 生成，只含 `[a-z0-9_]`；SQL 参数由 seekdb-js 参数化，`DBMS_HYBRID_SEARCH` 的 JSON 通过 `SET @search_parm = ?` 传入。
- 上传大小限制在 64 MB（Fastify `bodyLimit`），单条文本 20,000 字符；前端按 300 字分块。

## 失败模式

| 失败 | 表现 | 处理 |
|---|---|---|
| seekdb 未启动 | `/api/health` `ok:false`，页面顶部提示 | 给出 embedded/Docker/已有 server 三条命令 |
| WebGPU 初始化失败 | 自动重试 WASM/INT8，徽章显示原因 | 用户可勾选“强制 WASM”复现 |
| 模型文件缺失 | `loadEmbedder` 抛错，界面显示 | `pnpm models:fetch` |
| 全文语法错误 | BFF 捕获后退回纯向量检索，返回 `degraded:"vector-only"` | UI 显示 warning |
| 刷新失败 | 导入阶段显示错误，已写入部分保留 | 重试刷新，不重复 embedding |
| 进程退出（WSL） | `pthread_create` 告警 | 已知环境问题；重启 WSL，查询数据不丢 |
