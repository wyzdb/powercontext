# 端侧向量化 × seekdb 混合检索

一个在浏览器里完成文档/查询向量化、用 seekdb 做向量 + 全文 RRF 融合的迷你知识库。给 OceanBase 2026 生态大赛 StepFun 赛道用。

![检索结果](bench/results/demo/search.png)

## 它到底做了什么

- **推理在浏览器**：Transformers.js 3.8.1 加载 `Xenova/bge-small-zh-v1.5`（512 维），WebGPU 可用时走 FP16，初始化失败或用户强制时降级到 WASM + INT8。Node 侧不加载任何模型。
- **存储在 seekdb**：每个知识库是一个 collection，物理表含 `VECTOR(512)`、`document`、`metadata JSON`；HNSW（cosine）+ IK 全文索引。
- **融合在 seekdb 内**：`collection.hybridSearch()` 调用 `DBMS_HYBRID_SEARCH.GET_SQL`，由数据库生成一条带 RRF 的 SQL。客户端不分别取两路再拼。
- **可审计**：界面的“查看 SQL”直接展示本次执行的 SQL、参数和每条语句耗时；`bench/results/` 保留了 DDL、trace 和基准原始 JSON。

## 快速开始

前置：Node.js 20+、pnpm 10+（实测 12.15）、Chrome/Edge 最新版；Linux 还需要 `libaio`。Windows 需要 Docker Desktop 或 WSL2。模型约 166 MB（159 MiB），首次下载需要网络。

### A. Linux / macOS：seekdb 嵌入式（最省事）

```bash
pnpm install
pnpm setup          # 下载 binding + 模型 + 拷贝 ORT wasm
pnpm check:linux    # 仅 Linux：检查 libaio / binding
pnpm dev            # BFF:8787 + Vite:5173
```

打开 <http://127.0.0.1:5173>。第一次启动嵌入式 seekdb 约 4 秒，数据在 `./.seekdb-data`。

`pnpm dev` 用 `scripts/run-embedded.sh` 启动 BFF；它会自动设置 `LD_PRELOAD`（Linux）或 `DYLD_INSERT_LIBRARIES`（macOS），规避 `libseekdb.so` 的 static TLS 问题。macOS 的 seekdb binding 目前只提供 arm64；Intel Mac 请走 Docker/server 模式。

### B. Docker 本地 server（Windows / macOS / Linux 通用）

```bash
docker compose up -d          # oceanbase/seekdb, 端口 2881
cp .env.example .env          # 把 SEEKDB_MODE 改成 server
pnpm install
pnpm setup
pnpm dev:server               # 终端 1：BFF 连接 127.0.0.1:2881
pnpm dev:web                  # 终端 2：Vite
```

Windows 上 Docker 数据卷必须用 named volume（`docker-compose.yml` 已经这样做），不要挂宿主目录。

### C. Windows + WSL2（本地开发的实际用法）

浏览器仍在 Windows，推理也在 Windows Chrome 里；BFF 和嵌入式 seekdb 跑在 WSL。先在 WSL 装 Node 与 libaio：

```bash
# WSL 里
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs rsync
sudo npm install -g pnpm@12
# Ubuntu 22.04 用 libaio1；24.04 用 libaio1t64 + 符号链接：
sudo apt-get install -y libaio1t64
sudo ln -sf /usr/lib/$(uname -m)-linux-gnu/libaio.so.1t64 \
            /usr/lib/$(uname -m)-linux-gnu/libaio.so.1
```

把代码复制到 Linux 文件系统（不要在 `/mnt/d` 上复用 Windows 的 `node_modules`）：

```bash
export REPO=/mnt/d/powercontext-gaode/stepfun   # 改成你的实际路径
mkdir -p ~/stepfun
rsync -a --exclude node_modules --exclude dist --exclude .seekdb-data \
  "$REPO/" ~/stepfun/
cd ~/stepfun && pnpm install && pnpm setup
bash scripts/run-embedded.sh        # 监听 127.0.0.1:8787
```

```powershell
# Windows 里另开一个终端；Vite 在 Windows 上服务 public/models
cd D:\powercontext-gaode\stepfun
pnpm install
pnpm setup
pnpm dev:web                        # /api 代理到 WSL 的 8787
```

WSL 的 localhost 会转发到 Windows，直接打开 <http://127.0.0.1:5173>。

### 生产构建

```bash
pnpm build
SEEKDB_MODE=server pnpm start       # 8787 同时提供 API 和 dist/
```

PowerShell 里没有 `VAR=value command` 语法：

```powershell
pnpm build
$env:SEEKDB_MODE='server'; pnpm start
```

## 模型与量化

| 精度 | 文件 | MiB | 压缩比 | 与 FP32 的余弦（3 条样本） |
|---|---|---:|---:|---|
| FP32 | `onnx/model.onnx` | 90.46 | 1.00× | 基线 |
| FP16 | `onnx/model_fp16.onnx` | 45.30 | 2.00× | 0.99998 |
| INT8 | `onnx/model_int8.onnx` | 22.80 | 3.97× | 0.96766 / 0.97092 / 0.96674 |

- 模型：`BAAI/bge-small-zh-v1.5`（MIT），ONNX 转换仓库 `Xenova/bge-small-zh-v1.5`，revision `75c43b06…`。`pnpm models:fetch` 会校验每个文件的 SHA-256。
- 输出用 BGE 官方的 CLS pooling（`1_Pooling/config.json` 里 `pooling_mode_cls_token=true`）+ L2 normalize；不要和 mean-pooling 的向量混用。
- 默认路径：WebGPU + FP16；失败自动降级 WASM + INT8，界面明确显示后端与原因。勾选“强制 WASM”可复现降级路径。
- 查询侧加 BGE 中文检索指令，文档侧不加（模型卡推荐用法；未做 instruction 消融，所有配置使用同一指令，不影响配置间比较）。
- INT8 用官方预量化文件（per-channel、`reduce_range=true`）。`scripts/quantize.py` 提供从 FP32 重新量化的路径（默认 `reduce_range=false`），便于对比。压缩比按 ONNX 权重口径；把 ORT runtime 算进去的端到端 payload 见 [BENCHMARK.md](docs/BENCHMARK.md)。

## seekdb 数据层

实际 DDL（省略物理表名）：

```sql
CREATE TABLE `c$v2$...` (
  `_id` varbinary(512) NOT NULL,
  `document` string DEFAULT NULL,
  `embedding` VECTOR(512) DEFAULT NULL,
  `metadata` json DEFAULT NULL,
  PRIMARY KEY (`_id`),
  FULLTEXT KEY `idx_fts` (`document`)
    WITH PARSER ik PARSER_PROPERTIES=(ik_mode="smart"),
  VECTOR KEY `idx_vec` (`embedding`)
    WITH (DISTANCE=COSINE, TYPE=HNSW, LIB=VSAG,
          M=16, EF_CONSTRUCTION=200, EF_SEARCH=64, SYNC_MODE=ASYNC)
)
```

检索 SQL 由数据库生成，核心是两路排名和 RRF：

```sql
SELECT ..., (ifnull(1 / (`_fts`.`_keyword_rank` + 60), 0)
           + ifnull(1 / (`_vs`.`_semantic_rank` + 60), 0)) AS `_score`
FROM (
  SELECT *, RANK() OVER (ORDER BY `_keyword_score` DESC) AS `_keyword_rank`
  FROM (SELECT ..., match(`document`) against('...' in natural language mode) AS `_keyword_score`
        FROM `kb`.`c$v2$...` WHERE match(`document`) against('...' in natural language mode)
        ORDER BY `_keyword_score` DESC LIMIT 1000)
) `_fts`
FULL JOIN (
  SELECT *, RANK() OVER (ORDER BY `_semantic_score` DESC) AS `_semantic_rank`
  FROM (SELECT ..., cosine_distance(`embedding`, '[...]') AS `_distance`
        FROM `kb`.`c$v2$...` ORDER BY `_distance` APPROXIMATE LIMIT 50)
) `_vs` ON `_fts`.`__pk_increment` = `_vs`.`__pk_increment`
ORDER BY `_score` DESC LIMIT 10
```

写入是异步索引：`SYNC_MODE=ASYNC`。导入结束后调用 `refresh_index()`（内部 `CALL dbms_index_manager.refresh()`）。实测同一条向量查询在 refresh 前看不到新文档、refresh 后能看到，见 [consistency.json](bench/results/phase1/consistency.json)。

## 基准结果

20 篇语料 / 20 个 chunk / 20 条查询，Windows 11、Chrome 155、Intel Core Ultra 5 125H + Intel Arc、32 GB；3 次独立运行的中位数，warm-up 不计入文档/查询计时：

| 配置 | 加载 ms | 首答 ms | docs/s | 查询嵌入 p50 | seekdb p50 | 端到端 p50 | nDCG@5 | Jaccard@10 | Kendall τ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| FP32 / WASM | 1156 | 1295 | 13.2 | 26.8 | 7.0 | 43.3 | 0.980 | 1.000 | 1.000 |
| INT8 / WASM | 217 | 292 | 18.5 | 19.2 | 7.0 | 35.3 | 0.984 | 0.936 | 0.848 |
| FP32 / WebGPU | 242 | 635 | 50.8 | 15.7 | 7.4 | 32.7 | 0.980 | 1.000 | 1.000 |
| FP16 / WebGPU | 408 | 767 | 56.1 | 19.1 | 7.4 | 35.3 | 0.980 | 1.000 | 0.998 |

同一 dtype 只换后端：FP32/WASM → FP32/WebGPU，文档吞吐 13.2 → 50.8 docs/s（3.85×），端到端 43.3 → 32.7 ms。WebGPU 上 FP16 vs FP32 是吞吐/体积换延迟：56.1 vs 50.8 docs/s，payload 66.4 vs 111.6 MiB，但单条查询端到端 35.3 vs 32.7 ms；默认选 FP16 是因为导入吞吐和体积，不是“单条最快”。INT8/WASM 的首答 292 ms、payload 33.9 MiB，是冷启动/低带宽路径；它没有测到相关性损失，但 Top-10 Jaccard 0.936 / Kendall 0.848 说明排序结构有变化，不能宣称“无损”。

需要注意：这 20 条查询太容易，一个字符 bigram 基线就能把主文档排到第 1（20/20），所以本表只能支持“没有明显质量下降”，不能支持“量化无损”或“编码器优劣”。完整方法、payload 口径、batch sweep 和限制见 [BENCHMARK.md](docs/BENCHMARK.md)。

完整方法、冷/热启动、batch sweep、逐 query 结果和限制见 [BENCHMARK.md](docs/BENCHMARK.md)；原始 JSON 在 [bench/results](bench/results)。

## 复现与证据

| 证据 | 位置 |
|---|---|
| 数据层冒烟 + DDL + 混合 SQL | [smoke.json](bench/results/phase1/smoke.json) |
| 增量 / 切换 / 刷新可见性 | [consistency.json](bench/results/phase1/consistency.json) |
| 推理后端 / batch sweep | [spike.json](bench/results/phase2/spike.json) |
| 检索质量 / 延迟矩阵 | [bench.json](bench/results/phase4/bench.json) |
| UI 演示截图 | [demo/](bench/results/demo) |
| 复现步骤 | [REPRODUCE.md](docs/REPRODUCE.md) |

```bash
pnpm dev                 # 终端 1（已包含 Vite）
pnpm test                # 指标/分块单元测试
pnpm demo                # 端到端截图（需要 BFF + Vite + Google Chrome）
pnpm bench               # 检索基准（需要 BFF + Vite + Google Chrome）
node scripts/spike-playwright.mjs   # 推理后端 spike
```

`pnpm demo` / `pnpm bench` 用 Playwright 的有头 Google Chrome 获取真实 WebGPU adapter；应用本身在 Edge 里也可以运行。脚本会把结果同时写到 `bench/results/` 和 `public/bench/`，刷新“基准”页即可看到新数据。

## 故障排查

| 现象 | 处理 |
|---|---|
| `libaio.so.1: cannot open shared object file` | `sudo apt-get install -y libaio1t64`，再按 `pnpm check:linux` 提示建符号链接 |
| `cannot allocate memory in static TLS block` | 用 `bash scripts/run-embedded.sh` 启动，不要直接 `tsx server/index.ts` |
| Windows 原生启动 seekdb 挂起 | Windows 不支持嵌入式；用 Docker/WSL |
| WSL 启动日志出现 `pthread_create: Invalid argument` | 查询通常仍可用的已知告警；若进程退出，`wsl --shutdown` 后重试 |
| 模型下载慢/失败 | `HF_ENDPOINT=https://hf-mirror.com pnpm models:fetch` |
| 页面没有 WebGPU | 用最新 Chrome/Edge；勾选“强制 WASM”仍可完整运行 |
| 2881 端口被占用 | 改 `docker-compose.yml` 和 `.env` 的端口 |
| 构建后模型 404 | `pnpm setup` 要把模型放到 `public/models`；`pnpm build` 会复制进 `dist` |

## 目录

```
stepfun/
├── src/                 React UI、embedder、spike、benchrun
├── server/              Fastify BFF、seekdb 连接、SQL trace
├── scripts/             模型下载、ORT 拷贝、量化、spike/bench/demo
├── public/              示例语料、bench JSON、模型与 ORT（后两者 gitignored）
├── bench/results/       Phase 1/2/4 原始数据与截图
└── docs/                技术说明、基准、模型卡、架构、复现
```

## 限制

- 文本知识库；图片 OCR 未实现（题目列为扩展）。
- 评测集只有 20 篇 / 20 条查询，结论只在这个规模上成立；INT8 的 nDCG 差异落在小样本噪声内，但排序一致性下降是真实的。
- Windows 原生嵌入式不可用；WSL 退出时 seekdb 偶发线程告警。
- 未做多用户、权限、分布式 seekdb；这是个人知识库，不是生产系统。

更完整的设计判断见 [TECHNICAL_REPORT.md](docs/TECHNICAL_REPORT.md)，接口与表结构见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)。
