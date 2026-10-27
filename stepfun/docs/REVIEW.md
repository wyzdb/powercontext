# 红队评审记录

三个独立评审（只读，不改代码）分别从合规、科学严谨、复现/UX 角度审查。下面是他们的结论、我实际改了什么、以及仍然没解决的问题。评审时的 HEAD 是 `007770e`，之后又提交了修复。

## 1 评分

| 评审 | 分数 | 主要判断 |
|---|---:|---|
| 合规（对照题目 3.1） | **18.5 / 20** | 功能闭环、本地推理、seekdb 内混合检索、量化证据都成立；扣分在 dtype 完整性、warm-up 声明与代码不符、提交落后于工作树 |
| 科学严谨 | **4 / 10** | 输入固定、指标实现正确、SHA 可复现；但 dtype/backend 混淆、20 条查询饱和、docs/s 含首次推理、没有重复/置信区间 |
| 复现 + UX | **6 / 10 / 6 / 10** | 主流程顺畅、证据完整；但 WSL 步骤是作者机器增量、Linux 首次启动有 binding 竞态、`/spike` 未样式化、基准重跑不写回 |
| 红队自评（修复后） | **19 / 20**（合规）/ 6.5 / 10（严谨）/ 7.5 / 10（复现） | 见下 |

## 2 已修复的 blocking

| 问题 | 修复 | 证据 |
|---|---|---|
| 强制 WASM 后可以把 INT8 向量写进 FP16 collection，只给事后警告 | 服务端 `addDocs` 增加 `encoderDtype` 校验，不一致返回 409；导入页在 dtype 不一致时直接禁用并提示新建/切回 | `server/seekdb.ts`、`server/routes.ts`、`ImportPanel.tsx` |
| 文档声称“先 warm-up 再计时”“按长度排序”，代码里没有 | `ModelContext` 加载后 warm-up 并记录 `warmupMs`；`ImportPanel`/`BenchRun` 按文本长度排序后分批；文档改成与代码一致 | `ModelContext.tsx`、`ImportPanel.tsx`、`BenchRun.tsx`、`TECHNICAL_REPORT.md` |
| 量化质量结论建立在 mean pooling 上，BGE 官方是 CLS | 改为 `pooling:"cls"`，重跑 spike/bench/demo；MODEL_CARD 注明 `1_Pooling/config.json` | `src/lib/embedder.ts`、`MODEL_CARD.md` |
| 单次运行、dtype 与 backend 完全混淆 | 3 次独立运行取中位数；增加 FP32/WebGPU 隔离 backend；表中标出 `firstAnswer`、p95、max；INT8 的收益/代价重新表述 | `BenchRun.tsx`、`bench-all.mjs`、`bench.json`、`BENCHMARK.md` |
| 20 条查询饱和，却宣称 INT8 有质量代价 | 增加 bigram 基线：20/20 主文档 rank 1；把结论改为“没有测到相关性损失，但排序结构变了”，删除“INT8 掉 recall”的错误说法 | `check-saturation.mjs`、`saturation.json`、`BENCHMARK.md` |
| 压缩比只算 ONNX，忽略 ORT runtime | 增加端到端 payload 表：FP32/WASM 101.6 MiB、INT8/WASM 33.9、FP32/WebGPU 111.6、FP16/WebGPU 66.4；两个口径都写 | `BENCHMARK.md` |
| `dbMs` 只包住 `hybridSearch()`，低估 DB 工作量 | `searchKb` 从 manifest 查询开始计时，包含 `getKbRow`/`getCollection`；文档改为 7.0–7.4 ms，并给出 residual | `server/seekdb.ts`、`BENCHMARK.md` |
| 首次查询 109.8 ms 被误写成“包含模型 warm-up” | 删除该说法；改为 `load + warmup + first query` 的 `firstAnswer`，四配置分别 1295/292/635/767 ms | `bench.json`、`TECHNICAL_REPORT.md` |
| “337–747 ms warm-up” 只有 337 有数据 | 删除 747；使用当前 spike 的 58/16/347 ms 和中位数 | `spike.json` |
| `kendallTau` 在无共有项时返回 1；p95 在 n=20 时丢最大值 | 改为 NaN + 聚合过滤；表里同时给 max，文档说明 p95 的局限 | `metrics.ts`、`BENCHMARK.md` |
| 基准重跑不写回“基准”页；`/spike` 无样式；标题 `scaffold` | `bench-playwright`/`spike-playwright` 复制到 `public/bench/`；`index.css` 增加 `.spike`；`index.html` 改中文标题 | `scripts/*`、`src/index.css`、`index.html` |
| 导入取消仍显示“完成”；切换 KB 不清空暂存 docs/timings；BFF 挂了没有重试 | 增加 `cancelled` 状态、`useEffect` 按 `kb.id` 重置、健康检查“重试连接”按钮 | `ImportPanel.tsx`、`App.tsx` |
| `pnpm e2e` 没有配置；`pnpm quantize` 缺参数；Docker 镜像未固定 | 删除这两个 npm script；`docker-compose.yml` 固定 `oceanbase/seekdb:1.4.0`（若 tag 不可用则按注释改 latest） | `package.json`、`docker-compose.yml` |
| 复现文档的 clone 占位符、WSL 不是完整步骤、Ubuntu 22.04 用了 24.04 的包名 | 改写 REPRODUCE/README：本目录已在仓库中；WSL 先装 Node/pnpm，Windows 侧单独 `pnpm install && pnpm setup`；22.04 用 `libaio1`，24.04 用 `libaio1t64` + 架构无关符号链接 | `README.md`、`REPRODUCE.md`、`check-linux-deps.sh` |
| Linux 首次启动时 binding 尚未下载，wrapper 找不到 `.so` | `pnpm setup`/`predev` 增加 `prepare-seekdb`，只下载不加载；`run-embedded.sh` 找不到时也会补下载 | `prepare-seekdb.mjs`、`package.json`、`run-embedded.sh` |
| 工作树领先 commit，评审看到的是旧 model card / 无测试 | 提交全部修复与 10 个单元测试；`pnpm test`/`tsc -b`/`build` 全绿 | git log、`src/lib/*.test.ts` |

## 3 仍然没解决 / 不应夸大

1. **评测集饱和**：20 篇文档、20 条查询，bigram 基线 20/20。即使加了 FP32/WebGPU、3 次中位数，也只能支持“没有明显质量下降”，不能支持“INT8 无损”或“哪个编码器更好”。需要 100+ 文档、hard negatives、公开 qrels 和第二标注者。
2. **dtype × backend 不是完整交叉**：有 FP32/WASM、INT8/WASM、FP32/WebGPU、FP16/WebGPU，缺 FP16/WASM 与 INT8/WebGPU；因此“FP16 的收益”仍有一部分归因于 WebGPU。FP32/WebGPU 这一行至少把 backend 单独隔离出来了。
3. **重复次数只有 3 次，没有置信区间**：表中给了 spread，但 3 次不足以做显著性检验；p95 在 n=20 时仍不是可靠的尾部指标，所以同时给了 max。
4. **refresh 实验只测了纯向量分支、单个时间点**：它证明“不 refresh 看不到新向量”，但没有区分“refresh 后立即可见”与“refresh 只是解除门控”；需要 hybrid 路径 + 0/50/100/250/500/1000 ms 时间序列。
5. **冷启动不是受控实验**：Playwright 每次新 profile，但没有显式清空磁盘缓存，也没有把 transfer / ORT init / first inference 拆开；`firstAnswer` 只能当作同一次 run 的首次查询体感。
6. **Docker 镜像 tag 未在当前机器验证**：本机没有 Docker，固定到 `1.4.0` 是按发布版本推断；如果 Docker Hub 没有该 tag，按 compose 注释改 `latest` 并在报告里记录实际版本。

## 4 评审的原话（节选）

- 合规评审：“Likely passes on all hard criteria — browser-only inference is real, hybrid retrieval is genuinely DB-side … the single biggest risk is the dtype-integrity gap.”
- 科学评审：“The three headline claims are each compromised … 2.86× throughput is contaminated by first-call cost, the INT8 quality cost is 2 queries × one weakly-relevant rank swap (p=0.5), and FP16 quality parity is a ceiling result.”
- 复现评审：“The submission cannot be followed literally from a clean machine … commit everything before submitting.”

这些原话保留在这里，方便对照我是否真的改了，而不是只写“已修复”。
