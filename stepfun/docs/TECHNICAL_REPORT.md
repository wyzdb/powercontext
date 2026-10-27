# 端侧向量化与 seekdb 混合检索：一个可审计的迷你知识库

**摘要** 本文实现一个完全在浏览器内完成文档/查询向量化的个人知识库：Transformers.js 加载 bge-small-zh-v1.5，WebGPU 优先、WASM 自动降级；向量、原文与元数据写入 seekdb；向量与全文的融合由 seekdb 的 `DBMS_HYBRID_SEARCH` 在一条 SQL 内用 RRF 完成。工程上把三条约束做成了可检查的证据：Node 侧无模型依赖、SQL trace 可回放、刷新前后可检索性有对照实验。

## 1 模型与量化

模型为 `BAAI/bge-small-zh-v1.5`（MIT），使用 `Xenova/bge-small-zh-v1.5` 的 ONNX 转换，revision `75c43b06…`；512 维、最大 512 token。查询侧加 BGE 中文检索指令“为这个句子生成表示以用于检索相关文章：”，文档侧不加。选它而不是 all-MiniLM-L6-v2（中文弱）或 bge-m3（568M，端侧过重），是在中文质量、首屏体积和浏览器内存之间的折中。

| 精度 | ONNX 字节 | MiB | 压缩比 | 与 FP32 余弦（3 条样本） |
|---|---:|---:|---:|---|
| FP32 | 94,851,877 | 90.46 | 1.00× | 基线 |
| FP16 | 47,497,427 | 45.30 | 2.00× | 0.99999 / 0.99999 / 0.99998 |
| INT8 | 23,903,394 | 22.80 | 3.97× | 0.96994 / 0.96631 / 0.96100 |

INT8 采用官方预量化文件的 per-channel、`reduce_range=true`、QInt8 动态量化；FP16 为 FP32 的半精度转换。`scripts/quantize.py` 提供从 FP32 重新量化的路径（默认 `reduce_range=false`），用于复核量化配置的影响。量化是否“可接受”不能只看余弦：在 20 条查询上，FP16 的 nDCG@5 与 FP32 相同（0.986），INT8 为 0.983，但 Top-10 Jaccard 从 1.000 降到 0.859、Kendall τ 为 0.876，说明排名结构确实变了。因此 FP16/WebGPU 是默认路径，INT8 只作为 WASM 降级，并在界面标注质量代价。

## 2 端侧运行

运行时是 Transformers.js 3.8.1 + ONNX Runtime Web 1.22。初始化时先 `navigator.gpu.requestAdapter()`：成功则 `device:"webgpu", dtype:"fp16"`；失败或用户勾选“强制 WASM”则 `device:"wasm", dtype:"int8"`，并把原因写进界面徽章。模型文件自托管在 `public/models`，`env.allowRemoteModels=false`，避免运行时依赖外部推理服务；ORT 的 `.jsep.wasm` 通过 Vite 中间件/静态资源提供。

性能上做了四件事：按 16 条一批做 embedding；同一批按长度排序减少 padding；初始化后先做一次 warm-up（WebGPU 的 shader 编译约 0.3–0.7 s，不能算进首条查询）；用速度更快的后端跑吞吐更大的文档批处理。batch=32 时 FP16/WebGPU 为 1.7 ms/条，INT8/WASM 为 11.1 ms/条，FP32/WASM 为 16.4 ms/条。单条查询（warm）FP16/WebGPU 13.7 ms、INT8/WASM 20.0 ms、FP32/WASM 27.8 ms；首条查询还要叠加模型加载与 warm-up，UI 实测约 109.8 ms。

## 3 seekdb 数据层

每个知识库对应一个 collection，物理表由 seekdb-js 创建：

```sql
CREATE TABLE `c$v2$...` (
  `_id` varbinary(512) NOT NULL,
  `document` string,
  `embedding` VECTOR(512),
  `metadata` json,
  PRIMARY KEY (`_id`),
  FULLTEXT KEY `idx_fts` (`document`) WITH PARSER ik PARSER_PROPERTIES=(ik_mode="smart"),
  VECTOR KEY `idx_vec` (`embedding`) WITH (DISTANCE=COSINE, TYPE=HNSW, LIB=VSAG,
    M=16, EF_CONSTRUCTION=200, EF_SEARCH=64, SYNC_MODE=ASYNC)
)
```

`embeddingFunction` 显式为 `null`，数据库不会替我们算向量。检索调用 `collection.hybridSearch({query:{whereDocument:{$contains:...}}, knn:{queryEmbeddings:...}, rank:{rrf:{rankConstant:60, rankWindowSize:50}}})`；seekdb 生成并执行一条 SQL，核心是：

```sql
(ifnull(1/(`_fts`.`_keyword_rank`+60),0) + ifnull(1/(`_vs`.`_semantic_rank`+60),0)) AS `_score`
```

两路分别是 `match(document) against(...)` 和 `cosine_distance(embedding, ...)`，在 `FULL JOIN` 后按 `_score` 排序。客户端只读最终结果，trace 里能看到完整 SQL，因而“没有在客户端拼两路结果”是可验证的，而不是口头声明。

索引是异步的（`SYNC_MODE=ASYNC`）。导入按 16 条一批写入，结束后调用 `refresh_index()`（内部 `CALL dbms_index_manager.refresh()`）。对照实验：插入一条新文档后，同一条向量查询在 refresh 前返回 3 条、不含新文档；refresh（301.9 ms）后返回 4 条、包含新文档。增量导入、collection 切换和删除的对照数据在 `bench/results/phase1/consistency.json`。

## 4 状态与性能

每个 collection 在 `kb_manifest` 表里绑定 `model_id + dim + dtype + created_at`；切换知识库时按该指纹校验，dtype 不一致会在检索页提示“FP16 与 FP32 近似、INT8 有可测差异”，而不是静默混用。文档 ID 由 `docId + chunk + content hash` 生成，写入用 `upsert`，重复导入幂等。

| 配置（20 docs / 20 queries） | 加载 ms | docs/s | 查询嵌入 p50 | seekdb p50 | 端到端 p50 | nDCG@5 | Jaccard@10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| FP32 / WASM | 1186 | 12.2 | 27.8 | 4.3 | 46.5 | 0.986 | 1.000 |
| INT8 / WASM | 273 | 15.8 | 20.0 | 4.2 | 36.8 | 0.983 | 0.859 |
| FP16 / WebGPU | 514 | 34.9 | 13.7 | 3.8 | 28.8 | 0.986 | 1.000 |

FP16/WebGPU 相对 FP32/WASM：文档吞吐 2.86×、端到端 p50 1.62× 更快，质量在同一水平。冷启动 FP32 加载 7.1 s、warm 1.2 s；FP16 加载 0.5 s（warm）。refresh 在 20 个 chunk 上约 338–440 ms。所有延迟均为同一设备、同一 Chrome、同一语料下的中位数，原始 JSON 在 `bench/results/phase4/bench.json`。

## 5 讨论与限制

本实现刻意没有做“客户端 RRF”：它更容易写，但会把数据库降级成两个 key-value 查询，违背题目对混合检索位置的要求。把融合放进 SQL 的代价是调试不便，因此增加了 SQL trace 和 `GET_SQL` 的原始语句展示。

限制同样明确：评测集只有 20 篇文档、20 条查询，INT8 的 nDCG 差异落在小样本噪声内，不能据此宣称“量化无损”；Windows 原生嵌入式 seekdb 不可用，Windows 走 Docker/WSL；WSL 退出时 seekdb 偶发 `pthread_create` 告警，查询不受影响但说明它不是一个经过生产验证的部署环境。下一步应把语料扩到数百篇、引入公开 qrels，并对 INT8 做 per-channel / reduce_range 的消融。

---

*设备：Windows 11、Chrome 155.0.8059.85、Intel Core Ultra 5 125H（14C/18T）、Intel Arc Graphics、32 GB RAM；seekdb 1.4.0；Transformers.js 3.8.1。完整方法与逐 query 数据见 `docs/BENCHMARK.md`。*
