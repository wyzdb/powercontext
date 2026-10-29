# 规有所依：面向软件连续演进的 SDD 上下文管理系统

2026-10-29 交付补充：[提测指导](docs/submission-guide.md)、[本轮原生验证与历史证据边界](docs/native-validation-2026-10-29.md)。本轮 Windows 验证未启动 Linux/数据库，历史服务记录不等于本轮服务重测。

本目录是「MiniMax × OceanBase 生态题」的提交材料。它实现了一个工程上下文模块：
给定一条开发任务，从 seekdb 中检索适用的**规格条目**、**需要修改的代码符号**和**验证测试**，
把上下文交给 **MiniMax** 完成一次真实代码修改，全程用 **PowerContext** 保存任务状态，
并在模块重启后继续复用。

目录内的业务工程 `business/orderflow`、规格库、测试与改动记录都是自包含的，
评审从干净环境按本文档操作即可复现。

## 1. 技术与分工

| 技术 | 在本作品中的实际作用 | 证据位置 |
| --- | --- | --- |
| MiniMax（`MiniMax-M3`，OpenAI 兼容接口） | 读取上下文，产出 unified diff，完成 `created_after` 过滤功能 | `records/minimax/*.json`、`records/minimax/*.prompt.md`、`artifacts/change.diff` |
| seekdb（`v1.4.0.0`，MySQL 协议） | 存储规格条目、代码符号、测试索引与倒排索引；检索查询结果直接构造上下文 | `context/sdd_context/store.py`、`records/seekdb/queries.jsonl`、`sdd_query_log` 表 |
| PowerContext（`1.4.1` Server + Python Client） | 把任务进展、已完成/待办、验证结果写为 Source，重启后读回并注入上下文 | `context/sdd_context/powercontext_state.py`、`records/powercontext/state.jsonl` |

MiniMax 的接入方式是 HTTP API（`POST {MINIMAX_BASE_URL}/chat/completions`），
不是只安装组件或只在文档里点名：`records/minimax/` 中每次调用都保存了模型名、请求 ID、
token 用量、完整 prompt、原始响应和实际应用的补丁，并与 `artifacts/change.diff` 一一对应。

## 2. 目录结构

```
minimax/
├── business/                     # 可运行、带测试的业务工程（demo）
│   ├── src/orderflow/            # 订单查询服务：models / service / repository / api / CLI
│   ├── specs/                    # SDD 规格（6 份，17 条 R 编号条款）
│   │   └── updates/              # 规格更新样例（v2），用于验证「重新导入后输出更新」
│   └── tests/                    # 17 个回归用例 + 4 个目标功能用例
├── context/sdd_context/          # 本题主体：上下文模块
│   ├── cli.py                    # 调用入口（db-init / ingest / build / run / status / spec-demo ...）
│   ├── indexer.py                # Markdown 规格 + AST 代码符号 + 测试注解 → 索引
│   ├── store.py                  # seekdb 表结构、写入、检索、查询日志
│   ├── context_builder.py        # 检索排序 + 引用闭包 + 上下文载荷与 Markdown 渲染
│   ├── minimax_client.py         # MiniMax 客户端与补丁提取
│   ├── patcher.py                # unified diff 校验、容错定位与应用
│   ├── powercontext_state.py     # PowerContext Source 状态读写
│   ├── pipeline.py               # context → MiniMax → patch → tests → 记录
│   └── sample.py                 # 验证样例的任务文本与编号
├── scripts/
│   ├── sdd.py                    # 模块入口包装（兼容忽略 PYTHONPATH 的解释器）
│   ├── run_sample.py             # 一键跑完验证样例并输出记录
│   ├── powercontext_server.py    # 启动 PowerContext Server
│   └── start_seekdb.ps1          # 启动 seekdb 容器（Windows）
├── docs/                         # 一页技术说明、验证样例、架构、运行日志
├── records/                      # 真实运行记录（context / minimax / seekdb / powercontext / tests / sample）
└── artifacts/                    # 修改前快照、修改后快照、change.diff
```

## 3. 环境要求

- Python **3.11+**（本作品在 3.12.10 上验证）
- Docker（运行 seekdb）或一台可连接的 seekdb / OceanBase MySQL 模式实例
- MiniMax Token Plan 的 API Key

依赖版本固定为 `requirements.txt`：`powercontext[server]==1.4.1`、`PyMySQL==1.2.0`、`pytest==9.1.1`。

```bash
python -m pip install -r requirements.txt
```

## 4. 快速开始

### 4.1 启动 seekdb 并初始化数据

```powershell
docker run -d --name seekdb -p 2881:2881 --restart unless-stopped quay.io/oceanbase/seekdb:latest
```

也可以复用已在运行的实例；默认连接 `127.0.0.1:2881`，用户 `root`，空密码。
确认实例可用：

```bash
python scripts/sdd.py doctor
```

`doctor` 会同时检查 seekdb、PowerContext 与 MiniMax Key，输出每项的 `ok`。

### 4.2 配置 MiniMax 与 PowerContext

复制 `.env.example` 为 `.env`，填入真实 Key 与绝对路径：

```dotenv
MINIMAX_API_KEY=sk-api-...
MINIMAX_BASE_URL=https://api.minimax.chat/v1
MINIMAX_MODEL=MiniMax-M3
SDD_SEEKDB_HOST=127.0.0.1
SDD_SEEKDB_PORT=2881
SDD_SEEKDB_DATABASE=sdd
POWERCONTEXT_SERVER_URL=http://127.0.0.1:8765
POWERCONTEXT_SERVER_DATABASE_KIND=sqlite
POWERCONTEXT_SERVER_DATABASE_URL=sqlite+aiosqlite:////absolute/path/to/minimax/.state/powercontext.db
```

`.env` 已在 `.gitignore` 中，不会进入提交。

启动 PowerContext Server（前台运行，另开终端继续下一步）：

```bash
python scripts/powercontext_server.py .env
```

### 4.3 建库、导入工程资料

```bash
python scripts/sdd.py db-init          # 在 seekdb 中建库建表
python scripts/sdd.py ingest           # 解析规格/代码/测试并写入索引
```

`ingest` 输出示例：

```json
{"specs": 6, "clauses": 17, "symbols": 30, "tests": 20, "terms": 1678}
```

### 4.4 一键运行验证样例

```bash
python scripts/sdd.py reset-sample --task-id task-order-created-after --clear-state
python scripts/run_sample.py
```

`run_sample.py` 依次执行并在 `records/sample/` 留下记录：

1. 重置业务工程（恢复修改前代码）与任务状态；
2. 修改前跑目标测试 → **必须失败**（`4 failed`）；
3. 重新导入索引；
4. 构建上下文（`records/contexts/ctx-*.json` 与 `.md`）；
5. 调用 MiniMax 生成补丁、应用补丁；
6. 修改后跑同一组目标测试与回归测试 → **必须全部通过**；
7. 跑完整测试集（21 passed）；
8. 在**新进程**中读取 PowerContext 状态：先 `status` 确认 `completed` 与 2 条验证结果，
   再 `build --json` 确认状态被注入新的上下文（`state.status=completed`）。

期望输出结尾：

```json
{"task_id": "task-order-created-after", "outcome": "success", ...}
```

## 5. 调用入口与输出

模块入口是 CLI：`python scripts/sdd.py <子命令>`（等价于在 `context/` 加入 `PYTHONPATH` 后
`python -m sdd_context`）。输入为任务文本与任务编号，输出为 JSON 上下文载荷，同时写入
`records/contexts/`。

| 子命令 | 输入 | 输出 / 作用 |
| --- | --- | --- |
| `db-init [--reset]` | — | 建库建表（`--reset` 先删表） |
| `ingest` | 业务工程目录 | 规格条款、代码符号、测试、倒排索引写入 seekdb |
| `build --task <文本> [--task-id <id>] [--json]` | 任务描述 | 上下文载荷：适用规格、待改符号、目标/回归测试、任务状态、查询记录 |
| `run --task <文本> [--task-id <id>]` | 任务描述 | 完整闭环：上下文 → MiniMax → 补丁 → 测试 → PowerContext 状态 |
| `status --task-id <id>` | 任务编号 | task 行、事件流、PowerContext 状态 |
| `reset-sample --task-id <id> [--clear-state]` | 任务编号 | 恢复修改前代码、清理任务记录 |
| `spec-demo apply\|restore` | — | 应用/还原规格 v2，验证「重新导入后输出使用更新内容」 |
| `doctor` | — | seekdb / PowerContext / MiniMax 自检 |

`build` 的 JSON 关键字段（`records/contexts/ctx-*.json`）：

```json
{
  "context_id": "ctx-...",
  "task_id": "task-order-created-after",
  "specs": [{"clause_id": "SPEC-ORD-004/R2", "version": 1, "status": "proposed",
             "role": "required", "body": "...", "source": {"path": "...", "line_start": 16, "line_end": 18}}],
  "code": [{"symbol_id": "orderflow.service.list_orders", "role": "modify",
            "path": "src/orderflow/service.py", "line_start": 83, "line_end": 114}],
  "tests": [{"test_id": "tests/test_created_after_api.py::test_created_after_filters_orders",
             "kind": "target", "spec_refs": ["SPEC-ORD-004/R1"]}],
  "state": {"status": "completed", "done": ["..."], "todo": [], "verifications": [{"exit_code": 0}]}
}
```

每条规格、代码、测试都带 `source.path` 与行号，来源是仓库中真实存在的文件。

## 6. 验证样例与重置

验证样例的任务文本、有效规格、初始数据、步骤与预期结果见
[`docs/verification-sample.md`](docs/verification-sample.md)。

重置示例：

```bash
python scripts/sdd.py reset-sample --task-id task-order-created-after --clear-state
```

该命令把 `artifacts/before/` 还原回 `business/`，删除该任务在 `sdd_tasks`、
`sdd_task_events`、`sdd_contexts` 中的记录，并在 PowerContext 中写入一个 `empty` 状态。
随后重新执行 `scripts/run_sample.py` 即可从空状态复现。

## 7. 测试

```bash
# 上下文模块自身
python -m pytest -q                      # 19 passed

# 业务工程（修改前）
cd business && python -m pytest -q       # 4 failed, 17 passed（目标功能尚未实现）

# 业务工程（应用补丁后）
cd business && python -m pytest -q       # 21 passed
```

`records/tests/` 保存了每次测试的完整命令、退出码与输出。

## 8. 记录与证据

| 路径 | 内容 |
| --- | --- |
| `records/contexts/` | 每次构建的上下文 JSON 与 Markdown |
| `records/minimax/` | 每次 MiniMax 调用的 prompt、响应、补丁、测试结果（含失败尝试） |
| `records/seekdb/queries.jsonl` | 实际执行的 SQL、参数摘要、行数、耗时 |
| `records/powercontext/state.jsonl` | 状态写入、读取、缺失与重启检查 |
| `records/tests/` | 目标测试、回归测试、全量测试日志 |
| `records/sample/` | 验证样例的整体结果 |
| `artifacts/before/`、`artifacts/after/`、`artifacts/change.diff` | 修改前后快照与差异 |

## 9. 已知限制

- MiniMax 是 `MiniMax-M3`；`M3` 默认会消耗全部 completion 预算做推理，客户端因此显式发送
  `thinking: {"type": "disabled"}`，仅对 `MiniMax-M3*` 生效。
- 补丁应用是严格校验的 unified diff：允许行号漂移（在 ±80 行内按上下文定位），
  但上下文行必须匹配；不匹配会失败并保留记录，不会静默改错文件。
- 检索是词法倒排索引（中文二元组 + 英文标识符切分），不依赖 embedding 模型，
  因此完全离线、结果可复现；语义相近但用词不同的任务需要扩充规格措辞。
- PowerContext 使用 SQLite 单机模式；多副本部署需要改用 OceanBase/seekdb 后端并配置鉴权。
- 业务工程是刻意保持依赖为零的 demo；把它换成真实仓库时，只需替换 `SDD_BUSINESS_ROOT`
  并保持 `specs/`、`src/`、`tests/` 的布局。

## 10. 排错

- `doctor` 中 seekdb 不 ok：确认容器在运行、端口 2881 可连、`.env` 中账号密码正确。
- PowerContext 不 ok：确认 `scripts/powercontext_server.py` 仍在运行，端口与
  `POWERCONTEXT_SERVER_URL` 一致；`/health/live` 可直接用浏览器访问。
- MiniMax 调用失败：检查 `MINIMAX_API_KEY` 是否有效、额度是否可用；
  `records/minimax/*.json` 中 `error` 字段会保留服务端返回的错误码与信息。
- Windows 上无法写临时目录：本作品的所有目录都由 `os.makedirs` 创建，不使用 `mkdtemp`；
  若仍遇到权限问题，把仓库放到用户目录下再试。
