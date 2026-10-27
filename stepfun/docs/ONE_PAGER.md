# 一页技术说明

**问题与做法** 我们要在浏览器里完成文档和查询的向量化，再把向量、原文与元数据交给 seekdb，由数据库完成向量与全文的混合检索。实现采用“浏览器推理 + 本机 BFF + seekdb”三段式：BFF 只连接数据库、写入、刷新和检索，不加载模型；collection 的 `embeddingFunction` 显式为 `null`，从 schema 层禁止数据库替我们算向量。

**模型与量化** 模型是 `BAAI/bge-small-zh-v1.5`（MIT，512 维，4 层 BERT，CLS pooling + L2 normalize），ONNX 转换来自 `Xenova/bge-small-zh-v1.5`，revision `75c43b06…`。ONNX 权重 FP32 90.46 MiB、FP16 45.30 MiB（2.00×）、INT8 22.80 MiB（3.97×）；三条样本文本与 FP32 的余弦分别是 0.99998（FP16）和 0.96766/0.97092/0.96674（INT8）。INT8 是官方 per-channel、`reduce_range=true` 的动态量化；`scripts/quantize.py` 提供 `reduce_range=false` 的复现路径。把 ORT runtime 也算进 payload 后，FP32/WASM 101.6 MiB、INT8/WASM 33.9 MiB（2.99×）、FP32/WebGPU 111.6 MiB、FP16/WebGPU 66.4 MiB（相对 FP32/WebGPU 1.68×）。

**端侧运行** 运行时是 Transformers.js 3.8.1 + ONNX Runtime Web 1.22。`navigator.gpu.requestAdapter()` 成功时用 WebGPU + FP16；失败或用户强制时降级 WASM + INT8，界面徽章显示当前后端、加载耗时、warm-up 耗时和降级原因。模型文件自托管，`allowRemoteModels=false`；ORT 的 `.jsep.wasm` 由 Vite 中间件/静态资源提供。导入按 16 条一批、按文本长度排序后 embedding；加载后先做一次 warm-up，warm-up 不计入文档/查询计时。

**seekdb 数据层** 每个知识库对应一个 collection，物理表含 `_id`、`document`、`VECTOR(512)`、`metadata JSON`，索引是 HNSW（cosine, m=16, ef_construction=200, ef_search=64, SYNC_MODE=ASYNC）+ IK 全文索引。检索调用 `collection.hybridSearch()`，seekdb 生成并执行一条 SQL：`match(document) against(...)` 与 `cosine_distance(embedding, ...)` 两路候选在 `FULL JOIN` 后用 `1/(60+keyword_rank) + 1/(60+semantic_rank)` 融合。客户端只读最终结果；trace 里能看到完整 SQL，所以“没有客户端拼两路结果”是可审计的。写入是异步索引，导入结束后 `refresh_index()`；对照实验显示同一条向量查询在 refresh 前看不到新文档、refresh 后能看到。

**实测（20 篇 / 20 条查询，3 次运行中位数）**

| 配置 | 加载 ms | 首答 ms | docs/s | 端到端 p50 | nDCG@5 | Jaccard@10 |
|---|---:|---:|---:|---:|---:|---:|
| FP32 / WASM | 1156 | 1295 | 13.2 | 43.3 | 0.980 | 基线 |
| INT8 / WASM | 217 | 292 | 18.5 | 35.3 | 0.984 | 0.936 |
| FP32 / WebGPU | 242 | 635 | 50.8 | 32.7 | 0.980 | 1.000 |
| FP16 / WebGPU | 408 | 767 | 56.1 | 35.3 | 0.980 | 1.000 |

同一 dtype 只换后端：FP32/WASM → FP32/WebGPU，文档吞吐 13.2 → 50.8 docs/s（3.85×），端到端 43.3 → 32.7 ms。WebGPU 上 FP16 vs FP32 是吞吐/体积换延迟：56.1 vs 50.8 docs/s、payload 66.4 vs 111.6 MiB，但单条查询 35.3 vs 32.7 ms。INT8/WASM 首答 292 ms、payload 33.9 MiB，是冷启动/低带宽路径；它没有测到相关性损失，但 Jaccard 0.936 说明排序结构有变化，不能宣称无损。

**边界** 这 20 条查询太容易：一个字符 bigram 基线就能把主文档排到第 1（20/20），所以本表只能支持“没有明显质量下降”，不能支持“量化无损”或“编码器优劣”；也没有做 5 次以上重复、置信区间、FP16/WASM 与 INT8/WebGPU 的完整交叉。refresh 实验只测了纯向量分支和单个时间点；冷启动没有拆开 transfer / ORT init / first inference。Windows 原生嵌入式 seekdb 不可用，Windows 走 Docker/WSL；WSL 退出时偶发 `pthread_create` 告警。
