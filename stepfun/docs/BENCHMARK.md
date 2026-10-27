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
| pooling | CLS（BGE 官方 `1_Pooling/config.json` 的 `pooling_mode_cls_token=true`）+ L2 normalize |
| 重复 | 每次 `pnpm bench` 跑 3 个独立浏览器 session，表中为 3 次的中位数 |

WebGPU 通过 `navigator.gpu.requestAdapter()` 探测；本机返回 adapter（`info` 为空对象，Chrome 未暴露厂商字段）。WASM 以 `numThreads=1` 运行，页面设置了 COOP/COEP，但不依赖 SharedArrayBuffer。

## 2 语料、查询与标注

- 语料：`public/corpus/sample.json`，20 篇中文短文，覆盖 AI/数据库/天文/生物/历史/地理/饮食/运动/环境等主题；每篇 100–150 字，全部落在 300 字分块窗口内，因此 20 篇 = 20 个 chunk。目的是先隔离变量：本阶段比较编码器精度与后端，不是分块策略。
- 查询：`public/bench/queries.json`，20 条，每条对应 1 个主相关文档（rel=2），部分附带 1 个弱相关文档（rel=1）；7 条偏关键词、13 条偏语义改写。
- 标注：作者按“2=直接回答、1=同主题有帮助、0=无关”标注；没有第二标注者，因此不报告 inter-annotator agreement。这是本基准最主要的效度限制。
- **饱和度检查**：一个字符二元组重叠基线（`scripts/check-saturation.mjs`）在这 20 条查询上把主文档排到第 1 的比例是 **20/20**。这说明该集合太容易，无法区分编码器质量；它只能验证“流程是否正确、量化是否把明显的排序弄坏”，不能证明模型优劣。证据在 `bench/results/phase4/saturation.json`。
- 评价：每个配置用独立 collection，写入同一批 chunk，refresh 后逐条查询，取 top-10。

## 3 指标

- **Recall@5**：相关文档（rel≥1）在 top-5 中的比例，对每条 query 计算后取平均。
- **nDCG@5**：`DCG = Σ (2^rel - 1) / log2(i+1)`，IDCG 用同一 qrels 的理想排序；跨 query 取平均。
- **MRR@10**：第一个 rel≥1 的结果的倒数排名；没有命中记 0。
- **Jaccard@10**：同一 query 下当前配置与 FP32/WASM 的 top-10 集合交集/并集；跨 query 取平均。它衡量**向量排序稳定性**，不是相关性。
- **Kendall τ**：在两者共有候选集上比较排序一致性；共有项少于 2 时返回 NaN，聚合时忽略。它同样不是相关性指标。
- **首答 ms**：`loadMs + warmupMs + 第一条 query 的端到端耗时`。它是“打开页面后第一次拿到答案”的体感，不等于磁盘冷缓存。
- **seekdb p50**：服务端从 manifest 查询开始，到 `hybridSearch` 返回为止；包含 `getKbRow`、`getCollection`、`SET @search_parm`、`GET_SQL` 和最终 SQL。比只包住 `hybridSearch()` 更接近真实数据库工作量。
- **端到端 p50**：query embedding + HTTP + 上述数据库段；不含 React 渲染。
- **p95 在 n=20 时是第 19 个 order statistic，会丢掉最大值**，因此同时给 max；不要只报 p95。
- **docs/s**：chunk 数 / 文档向量化总耗时（batch=16，warm-up 已排除，不含写入和刷新）。

## 4 总体结果

原始数据：[`bench/results/phase4/bench.json`](../bench/results/phase4/bench.json)，3 次运行的中位数；单次原始文件是 `bench-1/2/3.json`。

| 配置 | 加载 ms | 预热 ms | 首答 ms | docs/s | 刷新 ms | 查询嵌入 p50 | seekdb p50 | 端到端 p50 | p95 | max | Recall@5 | nDCG@5 | MRR@10 | Jaccard@10 | Kendall τ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FP32 / WASM | 1156 | 65 | 1295 | 13.2 | 421 | 26.8 | 7.0 | 43.3 | 53.0 | 59.1 | 0.975 | 0.980 | 1.000 | 基线 | 基线 |
| INT8 / WASM | 217 | 23 | 292 | 18.5 | 326 | 19.2 | 7.0 | 35.3 | 42.7 | 77.5 | 0.975 | 0.984 | 1.000 | 0.936 | 0.848 |
| FP32 / WebGPU | 242 | 338 | 635 | 50.8 | 228 | 15.7 | 7.4 | 32.7 | 52.8 | 63.4 | 0.975 | 0.980 | 1.000 | 1.000 | 1.000 |
| FP16 / WebGPU | 408 | 305 | 767 | 56.1 | 341 | 19.1 | 7.4 | 35.3 | 42.5 | 45.1 | 0.975 | 0.980 | 1.000 | 1.000 | 0.998 |

**读法（按可归因性排序）：**

1. **后端效应是干净的**：FP32/WASM → FP32/WebGPU，文档吞吐 13.2 → 50.8 docs/s（3.85×），端到端 p50 43.3 → 32.7 ms。两者 dtype 相同，只换执行提供者，所以这是 WebGPU 的真实收益。
2. **在 WebGPU 上，FP16 vs FP32 是“吞吐/体积换一点查询延迟”**：50.8 → 56.1 docs/s（+10%），端到端 32.7 → 35.3 ms（+2.6 ms），payload 111.6 → 66.4 MiB（1.68× 更小），质量完全一致（Jaccard 1.000，nDCG 0.980）。说“FP16 全面更快”不成立；说“FP16 是默认，因为导入吞吐和体积，单条查询 FP32/WebGPU 略快”是准确的。
3. **INT8/WASM 是冷启动/低带宽路径**：首答 292 ms，是 FP16/WebGPU 767 ms 的 0.38、FP32/WASM 1295 ms 的 0.23；payload 33.9 MiB。它的 nDCG 0.984、Recall@5 与 MRR 与 FP32 相同，但 Jaccard 0.936、Kendall 0.848，说明排序结构有变化。它不是“质量等价”的替代，但在这个集合上也**没有测到相关性损失**。
4. **质量指标本身被集合饱和限制**：主文档在所有配置下都是 rank 1（20/20），Recall@5 0.975、MRR 1.000 完全相同；nDCG 的 0.980 vs 0.984 是 20 条 query 上的 0.004 差异，且 INT8 没有更差。Jaccard/Kendall 的变化发生在 q01/q20 等弱相关文档的尾部顺序上，不是“相关文档掉出 top-5”。因此本表能支持“没有明显质量下降”，不能支持“量化无损”或“哪个编码器更好”。

## 5 首次查询与冷/热

| 配置 | 加载 ms | warm-up ms | 首答 ms |
|---|---:|---:|---:|
| FP32 / WASM | 1156 | 65 | 1295 |
| INT8 / WASM | 217 | 23 | 292 |
| FP32 / WebGPU | 242 | 338 | 635 |
| FP16 / WebGPU | 408 | 305 | 767 |

`firstAnswer` 是 `load + warmup + 第一条 query`，比“单条 warm 查询”更能代表用户第一次使用的体感。表中是 3 次运行的中位数；三次的 range 见 `bench.json` 的 `spread`（例如 FP16 首答 753–779 ms，INT8 267–345 ms）。

**这不是受控的冷缓存实验**：Playwright 每次启动使用新的临时 profile，但脚本没有显式清空 Chrome 的磁盘缓存，也没有把网络传输单独计时。因此不要把它当作“冷启动 vs 热启动”的严格对比；它只是同一次 run 内的首次查询观测值。早期一次 FP32 加载 7.1 s 的观测没有纳入这张表，因为无法确认缓存状态。

## 6 batch sweep（推理层）

来自 [`bench/results/phase2/spike.json`](../bench/results/phase2/spike.json)，batch=1/4/8/16/32，单位为每条的毫秒；CLS pooling，warm-up 已单独计时：

| 配置 | b1 | b4 | b8 | b16 | b32 | batch32 相对 b1 |
|---|---:|---:|---:|---:|---:|---:|
| FP32 / WASM | 17.1 | 16.0 | 15.6 | 15.3 | 15.4 | 1.11× |
| INT8 / WASM | 13.5 | 11.1 | 10.6 | 10.9 | 11.8 | 1.14× |
| FP16 / WebGPU | 12.5 | 4.4 | 2.8 | 2.1 | 1.7 | 7.35× |

WASM 在 batch>4 后基本平坦（CPU 已吃满）；WebGPU 的收益来自把固定开销摊到更大 batch，batch=32 时到 1.7 ms/条。这也是导入用 16 的批大小、单条查询不追求 batch 的原因。这里的单条数字没有加 BGE query instruction；应用里的查询会加，端到端数字见 §4。

## 7 索引刷新与状态

来自 [`bench/results/phase1/consistency.json`](../bench/results/phase1/consistency.json)：

- 写入 1 条新文档后，同一条**向量查询**在 `refresh_index()` 前 `visibleBefore=false`，refresh（301.9 ms）后 `visibleAfter=true`。
- 增量导入后 collection 的 count 从 4 增到 5，新文档在 top-1 命中。
- 两个 collection 交替查询，A 库不会返回 B 库的文档（`leaked=false`）。
- 删除 collection 后，列表不再包含它，按 id 查询返回“知识库不存在”。

限制：这个实验用的是空 query（走纯向量分支），不是 App 实际使用的 hybrid 分支；只测了一个时间点，没有 0/50/100/250/500/1000 ms 的时间序列。因此它证明“异步索引确实需要 refresh 才能看到新向量”，但不能区分“refresh 后立即可见”与“refresh 只是解除了一个门控”。更严格的实验应重复 5 次、在 hybrid 路径上按时间采样，并加一个不 refresh 的对照组。这条列为待补实验。

## 8 体积、payload 与量化余弦

ONNX 权重口径（任务要求的压缩比口径）：

| 变体 | 字节 | MiB | 压缩比 | 3 条样本文本与 FP32 的余弦 |
|---|---:|---:|---:|---|
| FP32 | 94,851,877 | 90.46 | 1.00× | 基线 |
| FP16 | 47,497,427 | 45.30 | 2.00× | 0.99998 / 0.99998 / 0.99998 |
| INT8 | 23,903,394 | 22.80 | 3.97× | 0.96766 / 0.97092 / 0.96674 |

端到端 payload（含实际需要加载的 ORT runtime 与 tokenizer）：

| 配置 | ONNX | ORT runtime | tokenizer/config | 合计 MiB | 相对 FP32/WASM |
|---|---:|---:|---:|---:|---:|
| FP32 / WASM | 90.46 | 10.62（`ort-wasm-simd-threaded.wasm`） | 0.52 | 101.60 | 1.00× |
| INT8 / WASM | 22.80 | 10.62 | 0.52 | 33.94 | 2.99× |
| FP32 / WebGPU | 90.46 | 20.60（`jsep.wasm`） | 0.52 | 111.58 | 0.91× |
| FP16 / WebGPU | 45.30 | 20.60 | 0.52 | 66.42 | 1.53× |

所以“FP16 2.00×、INT8 3.97×”只在 ONNX 权重口径成立；把 runtime 算进去，FP16/WebGPU 相对 FP32/WebGPU 是 1.68×，而 INT8/WASM 相对 FP32/WASM 是 2.99×。报告里两个口径都要写，否则会误导。

## 9 不能从这份数据得出的结论

- **不能**说“INT8 在中文检索上无损”。Jaccard 0.936、Kendall 0.848 是真实的排序变化；只是在这个 20 条、bigram 都能 20/20 的集合上，相关性指标没有掉。扩大语料后 recall 可能受影响。
- **不能**说“FP16 比 FP32 快”。在 WebGPU 上 FP16 的导入吞吐更高（56.1 vs 50.8 docs/s），但单条查询端到端反而慢 2.6 ms（35.3 vs 32.7）；它的主要优势是 payload 小 1.68×。
- **不能**说“WebGPU 在所有场景更快”。FP16/WebGPU 的首答 767 ms 比 INT8/WASM 的 292 ms 慢；冷启动/低带宽场景 INT8/WASM 更合适。
- **不能**把本表当作编码器质量评估。20 篇语料、20 条查询、单标注者、bigram 基线 20/20；它只适合做回归，不适合做模型排名。
- **不能**把 p95 当尾部指标。n=20 时 p95 是第 19 个值，会丢掉最大值；表里另给了 max。
- **不能**把 `loadMs` 当作受控冷启动。它来自 3 次独立 Playwright session 的中位数，但没有显式清空 Chrome 磁盘缓存；网络传输、ORT 初始化、首条 shader 编译没有拆开计时。下一步应把 load 拆成 transfer / ORT init / first inference，并用固定的 `--user-data-dir` 控制缓存。
- **没有**做 dtype × backend 的完整交叉（FP16/WASM、INT8/WebGPU 缺失），也没有做 5 次以上的重复与置信区间。表中 3 次运行的 spread 在 `bench.json` 里，但不足以做显著性检验。

## 10 复现

```bash
# 终端 1：pnpm dev 已经同时启动 BFF 和 Vite。
# Docker/server 模式则用 pnpm dev:server + pnpm dev:web 两个终端。
pnpm dev

# 以下脚本在终端 2 运行：
node scripts/spike-playwright.mjs   # 写 bench/results/phase2/spike.json + public/bench/phase2.json
pnpm bench                          # 3 次运行 + 中位数，写 bench/results/phase4/ + public/bench/phase4.json
pnpm check:saturation               # 写 bench/results/phase4/saturation.json
pnpm demo                           # 写 bench/results/demo/
```

`pnpm bench` 会创建 4 个临时 collection（`bench-<config>-<timestamp>`），跑完删除；每个配置先做 warm-up，warm-up 不计入文档/查询计时。Playwright 每次启动使用新的临时 profile，因此同一 run 内没有来自上一次 run 的浏览器磁盘缓存；但同一 run 的四个配置共享 profile，模型文件不同，不会互相复用。

注意：`spike`/`bench`/`demo` 脚本用 `channel: "chrome"`，需要安装 Google Chrome；应用本身在 Edge 里也能跑。

原始文件：

- `bench/results/phase1/smoke.json`：DDL、`DBMS_HYBRID_SEARCH` 生成的 SQL、3 条文档的检索结果。
- `bench/results/phase1/consistency.json`：刷新/增量/切换/删除。
- `bench/results/phase2/spike.json`：三配置的加载、warm-up、单条查询、batch sweep、余弦。
- `bench/results/phase4/bench-1/2/3.json`：三次独立运行；`bench.json` 是三次中位数。
- `bench/results/phase4/saturation.json`：bigram 基线 20/20。
- `bench/results/demo/`：导入、检索、SQL trace 截图。
