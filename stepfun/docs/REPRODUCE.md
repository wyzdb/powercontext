# 复现步骤

目标：在一台干净的机器上，从代码目录到看到“导入 → 检索 → SQL trace → 基准表”。

## 1 前置

| 依赖 | 版本 | 检查 |
|---|---|---|
| Node.js | 20+（实测 22.19 / 24.22） | `node -v` |
| pnpm | 10+（实测 12.15） | `pnpm -v` |
| Chrome / Edge | 最新版（WebGPU 可选） | `chrome://gpu` |
| seekdb | 1.4.0 | 嵌入式自动安装；或 Docker `oceanbase/seekdb` |
| Docker Desktop 或 WSL2 | Windows 必选其一 | `docker --version` / `wsl -l -v` |
| Python（可选） | 3.11–3.13 | 只有跑 `scripts/quantize.py` 需要 |

模型约 166 MB（159 MiB），ORT wasm 约 33 MiB；首次需要网络。磁盘预留 500 MB。

## 2 进入代码目录

本提交已经把全部代码放在 `stepfun/`。如果拿到的是私有仓库：

```bash
cd powercontext/stepfun
```

如果拿到的是压缩包，解压后进入 `stepfun/`，保持相对路径不变。后续命令都在这个目录执行。

## 3 安装依赖与模型

```bash
pnpm install
pnpm setup          # prepare:ort + models:fetch
```

`pnpm setup` 做三件事：

1. 把 `node_modules/onnxruntime-web/dist` 下的 4 个 ORT wasm/mjs 文件复制到 `public/ort`；
2. 下载 seekdb 的 Linux/macOS 原生 binding（Windows 跳过；这一步只下载，不加载，避免首次启动找不到 `libseekdb.so`）；
3. 从 Hugging Face（或 `HF_ENDPOINT` 指定的镜像）下载模型到 `public/models/Xenova/bge-small-zh-v1.5`，逐文件校验 SHA-256。

国内网络建议：

```bash
HF_ENDPOINT=https://hf-mirror.com pnpm models:fetch
```

## 4A Linux / macOS：嵌入式 seekdb

```bash
pnpm check:linux     # Linux：检查 libaio 与 binding
pnpm dev
```

`pnpm dev` 会并行启动：

- `WATCH=1 bash scripts/run-embedded.sh`：BFF + 嵌入式 seekdb，监听 127.0.0.1:8787；
- `vite`：前端，监听 127.0.0.1:5173，`/api` 代理到 8787。

首次启动 seekdb 约 4 秒；数据目录 `./.seekdb-data`。打开 <http://127.0.0.1:5173>。

Linux 如果报 `libaio.so.1`：

```bash
# Ubuntu 22.04
sudo apt-get install -y libaio1
# Ubuntu 24.04
sudo apt-get install -y libaio1t64
sudo ln -sf /usr/lib/$(uname -m)-linux-gnu/libaio.so.1t64 \
            /usr/lib/$(uname -m)-linux-gnu/libaio.so.1
```

如果报 `cannot allocate memory in static TLS block`：不要直接 `tsx server/index.ts`，用 `scripts/run-embedded.sh`；它会在启动前设置 `LD_PRELOAD`。首次运行前 `pnpm setup` 已经把 binding 下载好；如果跳过 `setup`，wrapper 会自己补下载。

## 4B Docker：本地 server

```bash
docker compose up -d
cp .env.example .env
# 编辑 .env，把 SEEKDB_MODE=auto 改成 SEEKDB_MODE=server
pnpm dev:server      # 终端 1
pnpm dev:web         # 终端 2
```

Windows 必须使用 named volume（compose 已配置），不要挂载 `D:\...` 到 `/var/lib/seekdb`。验证：

```bash
docker logs stepfun-seekdb --tail 20
```

## 4C Windows + WSL2：本仓库实际验证的方式

WSL（Ubuntu 22.04/24.04）先装 Node 20+ 与 pnpm：

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs rsync
sudo npm install -g pnpm@12
```

再装 libaio（22.04 用 `libaio1`，24.04 用 `libaio1t64` + 符号链接）：

```bash
# Ubuntu 24.04 示例
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
cd ~/stepfun
pnpm install
pnpm setup
bash scripts/run-embedded.sh
```

Windows 侧需要**单独**安装依赖和模型（Vite 在 Windows 上服务 `public/models`，`/api` 代理到 WSL 的 8787）：

```powershell
cd D:\powercontext-gaode\stepfun
pnpm install
pnpm setup
pnpm dev:web
```

打开 <http://127.0.0.1:5173>。推理在 Windows Chrome 的 WebGPU 上，BFF/数据库在 WSL。

> 注意：不要在 Windows 的 `stepfun/` 目录里直接跑 WSL 的 `pnpm install`，Windows 与 Linux 的 `node_modules` 二进制不兼容。用 rsync 复制到 `~/stepfun`。

## 5 走一遍功能

1. 左侧点“+”，输入“示例知识库”，创建。
2. “加载示例语料（20 篇）”，点“开始导入”。
3. 等“完成”，右侧计时出现；此时刷新索引已结束。
4. 切到“检索”，输入“为什么小批量 GPU 推理不一定快？”，点“检索”。
5. 结果第一条应是「WebGPU 与浏览器推理」，score 约 0.0328。
6. 点“查看 SQL”，应看到 `DBMS_HYBRID_SEARCH.GET_SQL` 生成的 SQL，含 `_keyword_rank`、`_semantic_rank`、`cosine_distance` 和 `_score` 的 RRF 公式。
7. 切到“基准”，应看到 3 行配置表；点“重新跑完整基准”可重跑。

如果结果为空：确认导入的“刷新索引”阶段已完成；确认 BFF 日志没有 SQL 错误；在 SQL trace 中看 `refresh` 是否返回 200。

## 6 复现基准

```bash
# 终端 1
pnpm dev
# 终端 2
node scripts/spike-playwright.mjs     # 推理层；写 bench/results/phase2
pnpm bench                            # 检索质量/延迟；写 bench/results/phase4
pnpm demo                             # UI 截图；写 bench/results/demo
```

这些脚本用 `channel: "chrome"` 启动**有头** Chrome（WebGPU 需要真实 adapter），会弹出一个浏览器窗口。脚本结束自动关闭。

预期（本机）：

- `phase2`：fp32/wasm、int8/wasm、fp16/webgpu 三行；fp16/webgpu 的 batch32 约 1.7 ms/条。
- `phase4`：四行；fp16/webgpu docs/s 约 56，端到端 p50 约 35.3 ms，nDCG@5 0.980；fp32/wasm 约 13.2 docs/s / 43.3 ms；int8/wasm 首答约 292 ms。
- `demo`：`import.png`、`search.png`、`sql.png`。

数字会随设备/浏览器/缓存变化；趋势应一致。

## 7 干净环境检查清单

- [ ] `pnpm install` 退出码 0（pnpm 12 的 `allowBuilds` 已写在 `pnpm-workspace.yaml`）。
- [ ] `pnpm build` 退出码 0。
- [ ] `pnpm exec tsc -b` 退出码 0。
- [ ] `pnpm test` 通过（10 个指标/分块用例）。
- [ ] `/api/health` 返回 `ok:true` 与 seekdb 版本。
- [ ] 导入 20 篇后 `count` 为 20。
- [ ] 检索返回非空，SQL trace 中有 `DBMS_HYBRID_SEARCH` 生成的 SQL。
- [ ] 勾选“强制 WASM”后刷新页面，徽章显示 `WASM · INT8`，检索仍可用。
- [ ] `pnpm bench` 产出 3 个配置的 JSON。

## 8 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `ERR_PNPM_IGNORED_BUILDS` | pnpm 12 默认阻止依赖脚本 | 仓库的 `pnpm-workspace.yaml` 已有 `allowBuilds`；若被覆盖，执行 `pnpm approve-builds --all` |
| `Collection name contains invalid characters` | 早期版本用 `-` 生成 collection 名 | 已改为 `_`；确认 `server/seekdb.ts` 的 `slugify` 是最新版本 |
| `Embedding function 'default-embed' is not registered` | `getCollection` 未显式传 `embeddingFunction: null` | 已修；确认 `server/seekdb.ts` 的所有 `getCollection` 都带 null |
| `Table doesn't exist` | DDL 用了 collection 名而不是物理表 `c$v2$...` | 已修；`/api/kbs/:id/ddl` 会先解析 `collectionId` |
| WSL 退出时 `pthread_create` | WSL2 下 seekdb 后台线程的已知告警 | 查询不受影响；进程退出后 `wsl --shutdown` 再启动 |
| Windows 原生嵌入式挂起 | seekdb-js 的 Windows 绑定不可用 | 用 Docker/WSL |
| 页面 WebGPU 不可用 | 浏览器/驱动/远程桌面 | 用最新 Chrome，勾选“强制 WASM” |
| 模型 404 | `public/models` 未下载或未复制进 `dist` | `pnpm setup`，再 `pnpm build` |
| ORT wasm 404 | `public/ort` 未生成 | `pnpm prepare:ort` |

## 9 已知不复现的部分

- 本仓库没有提交 `node_modules`、`public/models`、`public/ort`、`.seekdb-data`；这些由安装脚本生成。
- 基准数字来自一台具体机器（Intel Core Ultra 5 125H + Intel Arc）；其他设备应看相对趋势。
- 20 篇语料 / 20 条查询是工程回归集，不是公开榜单；扩大语料后结论可能变化。
