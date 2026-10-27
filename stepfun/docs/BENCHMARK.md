# 基准方法与原始数据

这份文档记录“怎么测的、测到了什么、哪些结论不能下”。所有数字来自提交代码的实际运行，不是估算。

## 1 环境

| 项 | 值 |
|---|---|
| 设备 | HUAWEI FLMH-XX，Intel Core Ultra 5 125H（14C/18T），Intel Arc Graphics，32 GB RAM |
| 系统 | Windows 11 家庭版 中文版 |
| 浏览器 | Chrome 155.0.8059.85（Playwright `channel: "chrome"`，headful） |
| 推理 | Transformers.js 3.8.1，ONNX Runtime Web 1.22.0-dev |
| 数据库 | seekdb 1.4.0（WSL2 Ubuntu 24.04，嵌入式） |
| 模型 | `Xenova/bge-small-zh-v1.5`，revision `75c43b069aac4d136ba6bc1122f995fedcfd2781` |

WebGPU 通过 `navigator.gpu.requestAdapter()` 探测；本机返回 adapter（`info` 为空对象，Chrome 未暴露厂商字段）。WASM 以 `numThreads=1` 运行，页面设置了 COOP/COEP，但不依赖 SharedArrayBuffer。

## 2 语料、查询与标注

- 语料：`public/corpus/sample.json`，20 篇中文短文，覆盖 AI/数据库/天文/生物/历史/地理/饮食/运动/环境等主题；每篇 100–150 字，全部落在 300 字分块窗口内，因此 20 篇 = 20 个 chunk。这样做的目的不是“让检索变简单”，而是先隔离变量：本阶段比较的是编码器精度与后端，不是分块策略。
- 查询：`public/bench/queries.json`，20 条，每条对应 1 个主相关文档（rel=2），部分附带 1 个弱相关文档（rel=1）。类型上 7 条偏关键词、13 条偏语义改写。
- 标注：作者按“2=直接回答、1=同主题有帮助、0=无关”的规则标注；没有第二标注者，因此不报告 inter-annotator agreement。这是本基准最主要的效度限制。
- 评价：每个配置用**独立 collection**，写入同一批 chunk，refresh 后逐条查询，取 top-10。

## 3 指标

- **Recall@5**：相关文档（rel≥1）在 top-5 中的比例，对每条 query 计算后取平均。
- **nDCG@5**：`DCG = Σ (2^rel - 1) / log2(i+1)`，IDCG 用同一 qrels 的理想排序；跨 query 取平均。
- **MRR@10**：第一个 rel≥1 的结果的倒数排名；没有命中记 0。
- **Jaccard@10**：同一 query 下，当前配置与 FP32 的 top-10 集合交集/并集；跨 query 取平均。
- **Kendall τ**：在两者的共有候选集上比较排序一致性；跨 query 取平均。
- **端到端 p50**：从 query embedding 开始，到 `api.search` 返回并解析完成为止；不含 React 渲染。UI 里另有一个从提交到渲染完成的端到端计时，首次查询约 109.8 ms（包含模型 warm-up），warm 后与表中 28.8 ms 同量级。
- **docs/s**：chunk 数 / 文档向量化总耗时（batch=16，不含写入和刷新）。

## 4 总体结果

原始数据：[`bench/results/phase4/bench.json`](../bench/results/phase4/bench.json)。warm cache，中位数：

| 配置 | 加载 ms | docs/s | 刷新 ms | 查询嵌入 p50 | seekdb p50 | 端到端 p50 | 端到端 p95 | Recall@5 | nDCG@5 | MRR@10 | Jaccard@10 | Kendall τ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FP32 / WASM | 1186 | 12.2 | 338 | 27.8 | 4.3 | 46.5 | 56.3 | 0.975 | 0.986 | 1.000 | 1.000 | 1.000 |
| INT8 / WASM | 273 | 15.8 | 434 | 20.0 | 4.2 | 36.8 | 50.6 | 0.975 | 0.983 | 1.000 | 0.859 | 0.876 |
| FP16 / WebGPU | 514 | 34.9 | 440 | 13.7 | 3.8 | 28.8 | 50.8 | 0.975 | 0.986 | 1.000 | 1.000 | 0.996 |

**读法：**

1. **FP16/WebGPU 是明确的最优默认**。文档吞吐 2.86× 于 FP32/WASM，端到端 p50 1.62× 更快；nDCG 相同，Top-10 集合完全一致，只有两条 query 的内部顺序有 0.956 的 Kendall τ（q07、q14）。这符合“FP16 只改变数值精度、不改变语义”的预期。
2. **INT8 不是“无损压缩”**。nDCG 从 0.986 降到 0.983，但 Top-10 Jaccard 0.859、Kendall 0.876；q03/q09/q19 的 Jaccard 只有 0.667，q01 的 nDCG 从 1.000 降到 0.964，q20 从 0.945 降到 0.933。总体 Recall@5 仍是 0.975，与 FP32 相同——在这个小语料上“找得到”没变，“排得对不对”变了。不能因为平均值没掉就宣称量化无损。
3. **seekdb 检索本身不是瓶颈**。三种配置的 DB 段都在 4 ms 左右，端到端差异主要来自 query embedding（13.7 vs 27.8 ms）和模型加载。继续优化 DB 参数（ef_search、RRF window）的收益远小于换后端。

## 5 冷启动与 warm

| 场景 | FP32/WASM | INT8/WASM | FP16/WebGPU |
|---|---:|---:|---:|
| 首次加载（冷，清空站点数据） | 7066 ms | 498 ms | 1222 ms |
| 再次加载（warm cache） | 1186 ms | 273 ms | 514 ms |
| warm-up（首条推理） | 57 ms | 19 ms | 337–747 ms |
| 单条查询（warm，5 次中位） | 19.9 ms | 12.1 ms | 13.4 ms |

冷启动的 FP32 是 7.1 s（95 MB 权重 + ORT 初始化）；FP16 只有 1.2 s（47 MB）。WebGPU 的 warm-up 包含 shader 编译，单独计时 337–747 ms，不能把它算进“首条查询延迟”来制造好看的数字。UI 首次查询 109.8 ms 就是“模型已加载、但首条 query 还要编译/分配”的真实体感；warm 后回落到 28.8 ms。

## 6 batch sweep（推理层）

来自 [`bench/results/phase2/spike.json`](../bench/results/phase2/spike.json)，batch=1/4/8/16/32，单位为每条的毫秒：

| 配置 | b1 | b4 | b8 | b16 | b32 | batch32 相对 b1 |
|---|---:|---:|---:|---:|---:|---:|
| FP32 / WASM | 20.0 | 17.6 | 16.2 | 16.4 | 16.4 | 1.22× |
| INT8 / WASM | 12.8 | 10.8 | 11.5 | 10.7 | 11.1 | 1.15× |
| FP16 / WebGPU | 12.0 | 3.4 | 2.7 | 2.0 | 1.7 | 7.06× |

WASM 在 batch>4 后基本平坦（CPU 已经吃满）；WebGPU 的收益来自把固定开销摊到更大的 batch 上，batch=32 时才到 1.7 ms/条。这也是为什么导入用 16–32 的批大小，而单条查询不需要追求 batch。

## 7 索引刷新与状态

来自 [`bench/results/phase1/consistency.json`](../bench/results/phase1/consistency.json)：

- 写入 1 条新文档后，同一条向量查询在 `refresh_index()` 前 `visibleBefore=false`，refresh（301.9 ms）后 `visibleAfter=true`。
- 增量导入后 collection 的 count 从 4 增到 5，新文档在 top-1 命中。
- 两个 collection 交替查询，A 库不会返回 B 库的文档（`leaked=false`）。
- 删除 collection 后，列表不再包含它，按 id 查询返回“知识库不存在”。

这组数据说明 `refresh_index()` 不是装饰性的调用。seekdb 的 HNSW 索引是 `SYNC_MODE=ASYNC`，写入与可见性之间确实存在窗口。

## 8 量化余弦与体积

| 变体 | 字节 | MiB | 压缩比 | 3 条样本文本与 FP32 的余弦 |
|---|---:|---:|---:|---|
| FP32 | 94,851,877 | 90.46 | 1.00× | 基线 |
| FP16 | 47,497,427 | 45.30 | 2.00× | 0.99999 / 0.99999 / 0.99998 |
| INT8 | 23,903,394 | 22.80 | 3.97× | 0.96994 / 0.96631 / 0.96100 |

余弦只是必要条件：INT8 的 0.966 均值已经预示了排序会变，实际 Jaccard 0.859 验证了这一点。

## 9 不能从这份数据得出的结论

- **不能**说“INT8 在中文检索上无损”。20 条 query 里 Recall@5 没掉，但 Top-10 排序的一致性只有 0.859，个别 query 的 nDCG 掉了 0.036；扩大语料后 recall 也可能受影响。
- **不能**说“WebGPU 一定比 WASM 快”。单条 warm 查询上 INT8/WASM 12.1 ms 甚至略快于 FP16/WebGPU 13.4 ms；WebGPU 的优势在批量吞吐和 FP16 质量，不在所有场景的延迟。
- **不能**把本表的绝对延迟外推到其他设备。Intel Arc 的 WebGPU 表现与独显、Apple Silicon、移动端差异很大；应把“相对趋势”和“绝对数字”分开看。
- **不能**把 20 篇语料的 nDCG 当作模型能力评估。它是工程回归测试，不是 MTEB/C-MTEB 榜单。

## 10 复现

```bash
# 终端 1：BFF（Linux/macOS 嵌入式；Windows 用 Docker/WSL）
pnpm dev

# 终端 2：前端
pnpm dev:web

# 推理层 spike：写 bench/results/phase2/spike.json
node scripts/spike-playwright.mjs

# 检索质量/延迟矩阵：写 bench/results/phase4/bench.json
pnpm bench

# 端到端 UI 截图：写 bench/results/demo/
pnpm demo
```

`pnpm bench` 会创建 3 个临时 collection（`bench-<config>-<timestamp>`），跑完删除；每个配置先 warm-up 再计时。若要复现冷启动，先在 Chrome DevTools 里 Clear site data，再重新加载。

原始文件：

- `bench/results/phase1/smoke.json`：DDL、`DBMS_HYBRID_SEARCH` 生成的 SQL、3 条文档的检索结果。
- `bench/results/phase1/consistency.json`：刷新/增量/切换/删除。
- `bench/results/phase2/spike.json`：三配置的加载、warm-up、单条查询、batch sweep、余弦。
- `bench/results/phase4/bench.json`：逐 query 的 ranked 列表、指标、延迟。
- `bench/results/demo/`：导入、检索、SQL trace 截图。
