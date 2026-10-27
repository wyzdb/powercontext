# 端侧向量化与 seekdb 混合检索：一个可审计的迷你知识库

**摘要** 本文实现一个完全在浏览器内完成文档/查询向量化的个人知识库：Transformers.js 加载 bge-small-zh-v1.5，WebGPU 优先、WASM 自动降级；向量、原文与元数据写入 seekdb；向量与全文的融合由 seekdb 的 `DBMS_HYBRID_SEARCH` 在一条 SQL 内用 RRF 完成。工程上把三条约束做成了可检查的证据：Node 侧无模型依赖、SQL trace 可回放、刷新前后可检索性有对照实验。

> 严格一页版见 [`ONE_PAGER.md`](ONE_PAGER.md)；本文是完整版，包含方法、数据与限制。

## 1 模型与量化

模型为 `BAAI/bge-small-zh-v1.5`（MIT），使用 `Xenova/bge-small-zh-v1.5` 的 ONNX 转换，revision `75c43b06…`；512 维、最大 512 token，CLS pooling（BGE 官方配置）+ L2 normalize。查询侧加 BGE 中文检索指令“为这个句子生成表示以用于检索相关文章：”，文档侧不加；这是模型卡推荐用法，本文没有单独做 instruction 消融。选它而不是 all-MiniLM-L6-v2（中文弱）或 bge-m3（568M，端侧过重），是在中文质量、首屏体积和浏览器内存之间的折中。

| 精度 | ONNX 字节 | MiB | 压缩比 | 与 FP32 余弦（3 条样本） |
|---|---:|---:|---:|---|
| FP32 | 94,851,877 | 90.46 | 1.00× | 基线 |
| FP16 | 47,497,427 | 45.30 | 2.00× | 0.99998 / 0.99998 / 0.99998 |
| INT8 | 23,903,394 | 22.80 | 3.97× | 0.96766 / 0.97092 / 0.96674 |

INT8 采用官方预量化文件的 per-channel、`reduce_range=true`、QInt8 动态量化；FP16 为 FP32 的半精度转换。`scripts/quantize.py` 提供从 FP32 重新量化的路径（默认 `reduce_range=false`），用于复核量化配置的影响。量化是否“可接受”不能只看余弦：在 20 条查询上，FP16 的 nDCG@5 与 FP32 相同（0.980），INT8 为 0.984；但 Top-10 Jaccard 为 0.936、Kendall τ 为 0.848，说明排序结构确实变了。在这个 20 条、bigram 基线 20/20 的集合上，INT8 没有测到相关性损失，但不能据此宣称“无损”；它作为 WASM 降级路径，界面会标注精度与质量边界。

## 2 端侧运行

运行时是 Transformers.js 3.8.1 + ONNX Runtime Web 1.22。初始化时先 `navigator.gpu.requestAdapter()`：成功则 `device:"webgpu", dtype:"fp16"`；失败或用户勾选“强制 WASM”则 `device:"wasm", dtype:"int8"`，并把原因写进界面徽章。模型文件自托管在 `public/models`，`env.allowRemoteModels=false`，避免运行时依赖外部推理服务；ORT 的 `.jsep.wasm` 通过 Vite 中间件/静态资源提供。

性能上做了四件事：按 16 条一批做 embedding；同一批按长度排序减少 padding；初始化后先做一次 warm-up（WebGPU 的 shader 编译约 300–640 ms，不能算进文档批或首条查询的计时）；用速度更快的后端跑吞吐更大的文档批处理。batch=32 时 FP16/WebGPU 为 1.7 ms/条，INT8/WASM 为 11.8 ms/条，FP32/WASM 为 15.4 ms/条（spike，CLS，无 instruction）。应用里的查询带 BGE instruction，端到端 p50 见 §4；`load + warmup + first query` 分别是 1295 / 292 / 767 ms（FP32/WASM、INT8/WASM、FP16/WebGPU）。

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

每个 collection 在 `kb_manifest` 表里绑定 `model_id + dim + dtype + created_at`；导入时服务端会把请求里的编码器 dtype 与 collection 指纹比对，不一致直接拒绝（409），避免把 INT8 向量写进 FP16 collection。检索时 dtype 不一致会提示，但允许只读查询。文档 ID 由 `docId + chunk + content hash` 生成，写入用 `upsert`，重复导入幂等。

| 配置（20 docs / 20 queries，3 次中位数） | 加载 ms | 首答 ms | docs/s | 查询嵌入 p50 | seekdb p50 | 端到端 p50 | nDCG@5 | Jaccard@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| FP32 / WASM | 1156 | 1295 | 13.2 | 26.8 | 7.0 | 43.3 | 0.980 | 基线 |
| INT8 / WASM | 217 | 292 | 18.5 | 19.2 | 7.0 | 35.3 | 0.984 | 0.936 |
| FP32 / WebGPU | 242 | 635 | 50.8 | 15.7 | 7.4 | 32.7 | 0.980 | 1.000 |
| FP16 / WebGPU | 408 | 767 | 56.1 | 19.1 | 7.4 | 35.3 | 0.980 | 1.000 |

后端效应是干净的：FP32/WASM → FP32/WebGPU，文档吞吐 13.2 → 50.8 docs/s（3.85×），端到端 43.3 → 32.7 ms。FP16 vs FP32（都在 WebGPU）是吞吐/体积换延迟：56.1 vs 50.8 docs/s，端到端 35.3 vs 32.7 ms，payload 66.4 vs 111.6 MiB，质量相同。默认选 FP16/WebGPU 是因为导入吞吐和体积，不是“单条查询最快”。INT8/WASM 的首答 292 ms、payload 33.9 MiB，是冷启动/低带宽路径；nDCG 0.984、Recall@5 0.975、MRR 1.000 与 FP32 持平，但 Top-10 Jaccard 0.936、Kendall 0.848，排序结构有变化。refresh 在 20 个 chunk 上约 228–421 ms；seekdb 段 7.0–7.4 ms 已包含 manifest/collection 查询，不只是 `hybridSearch()`。

## 5 讨论与限制

本实现刻意没有做“客户端 RRF”：它更容易写，但会把数据库降级成两个 key-value 查询，违背题目对混合检索位置的要求。把融合放进 SQL 的代价是调试不便，因此增加了 SQL trace 和 `GET_SQL` 的原始语句展示。

限制同样明确：评测集只有 20 篇文档、20 条查询，且一个字符二元组基线就能把主文档排到第 1（20/20），所以本表只能说明“没有明显质量下降”，不能说明“量化无损”或编码器优劣；INT8 的 nDCG 差异只有 0.004，排序一致性 0.936 才是更可信的信号。Windows 原生嵌入式 seekdb 不可用，Windows 走 Docker/WSL；WSL 退出时 seekdb 偶发 `pthread_create` 告警，查询不受影响但说明它不是一个经过生产验证的部署环境。下一步应把语料扩到数百篇、引入公开 qrels 和第二个标注者，并对 INT8 做 per-channel / reduce_range 的消融。

---

*设备：Windows 11、Chrome 155.0.8059.85、Intel Core Ultra 5 125H（14C/18T）、Intel Arc Graphics、32 GB RAM；seekdb 1.4.0；Transformers.js 3.8.1。完整方法与逐 query 数据见 `docs/BENCHMARK.md`。*
