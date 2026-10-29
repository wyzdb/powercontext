# 规有所依 —— MiniMax 赛道

面向软件持续演进的 **SDD（Spec-Driven Development）上下文管理系统**。给定一个开发任务，模块从 seekdb 里取出适用的规格条目、需要修改的代码符号、用于验证的测试，把上下文交给 MiniMax 生成补丁，并把任务进展存进 PowerContext，重启后还能接着做。

> 本目录是 PowerContext 2026 生态赛 MiniMax 赛道的参赛作品，位于比赛仓库 `minimax/` 目录。

| 验收项 | 状态 | 证据 |
| --- | --- | --- |
| 能够运行 | ✅ | 本 README 第 3–7 节 |
| MiniMax 实际参与 | ⏳ 待额度 | `records/minimax/*.jsonl`、`records/patches/` |
| 上下文正确 | ✅ | `records/context-TASK-001.json` |
| 数据库实际参与 | ✅ | seekdb `mmx_ctx` 库，`ctx/importer.py` |
| 状态能够复用 | ✅ | `ctx state-save` / `state-load`，重启后读回 |
| 代码修改有效 | ⏳ 待补丁 | `records/test-runs.jsonl` |

> 一键演示：`powershell -ExecutionPolicy Bypass -File scripts/demo.ps1`
> 逐条验收对照：[docs/05-acceptance-checklist.md](docs/05-acceptance-checklist.md)

---

## 1. 目录结构

```
minimax/
├── demo/taskboard/            # 验证样例：任务看板 API（Flask + pytest）
│   ├── taskboard/             #   业务代码（app.py / store.py / cli.py）
│   ├── specs/                 #   规格：SPEC-001 基线、SPEC-002 本次变更
│   └── tests/                 #   test_tag_filter.py（目标）、test_tasks_api.py（回归）
├── ctx/                       # 上下文模块
│   ├── db.py                  #   seekdb 连接与建表
│   ├── importer.py            #   规格/代码/测试 → seekdb（含引用关系解析）
│   ├── retrieve.py            #   按任务检索并组装上下文
│   ├── state.py               #   PowerContext 任务状态读写
│   ├── patch.py               #   调 MiniMax 生成补丁
│   └── cli.py                 #   命令行入口
├── tools/                     # MiniMax 客户端与环境自检
├── scripts/                   # run_tests.py：测试日志落盘
├── config/powercontext.env    # PowerContext 本地配置
├── records/                   # 上下文产物、测试日志、MiniMax 调用记录
├── docs/                      # 设计说明、验证样例、技术使用记录
├── requirements.txt
└── .env.example               # MiniMax Key 等配置模板
```

---

## 2. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.11+（实测 3.13.15） | 全部模块均为 Python |
| seekdb | 1.4.x（实测 `seekdb-v1.4.0.0`） | 走 MySQL 协议，默认 `127.0.0.1:2881` |
| PowerContext | 1.4.1 | `powercontext[cli,server]`，SQLite 模式 |
| MiniMax | `MiniMax-M3.1-Flash` | OpenAI 兼容协议 |

---

## 3. 安装

```powershell
cd minimax
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

macOS / Linux 把最后两行换成 `./.venv/bin/python` 与 `cp .env.example .env`。

`.env` 至少填写 MiniMax Key：

```dotenv
MINIMAX_API_KEY=sk-cp-...
MINIMAX_REGION=cn
MINIMAX_MODEL=MiniMax-M3.1-Flash
```

其他可调项见 `.env.example` 与 [docs/01-minimax-setup.md](docs/01-minimax-setup.md)。

---

## 4. 初始化数据（seekdb）

### 4.1 启动 seekdb

任选一种，模块只要求一个可连的 MySQL 协议地址：

**Docker（推荐评审使用）**

```bash
docker run -d --name seekdb -p 2881:2881 oceanbase/seekdb
```

**已有实例**：直接复用，通过环境变量指向它：

| 变量 | 默认值 |
| --- | --- |
| `SEEKDB_HOST` | `127.0.0.1` |
| `SEEKDB_PORT` | `2881` |
| `SEEKDB_USER` | `root` |
| `SEEKDB_PASSWORD` | 空 |
| `SEEKDB_DB` | `mmx_ctx` |

### 4.2 导入规格 / 代码 / 测试

```powershell
.\.venv\Scripts\python.exe -m ctx.cli import
```

输出示例：

```json
{
  "total": 9,
  "by_kind": {"code": 4, "spec": 2, "test": 3},
  "root": ".../minimax/demo/taskboard"
}
```

导入会建三张表：`documents`（规格/代码/测试全文与哈希）、`spec_refs`（规格声明的适用模块、关联测试、上游规格）、`task_state`（预留）。

---

## 5. 生成任务上下文（核心入口）

```powershell
.\.venv\Scripts\python.exe -m ctx.cli build --task "为任务列表增加按标签筛选" --out records\context-TASK-001.json
```

输出结构（节选）：

```json
{
  "task": "为任务列表增加按标签筛选",
  "retrieval": {"primary_spec": "SPEC-002", "constraints": ["SPEC-001"]},
  "specs": [
    {"key": "SPEC-002", "role": "primary",
     "requirements": ["REQ-TAG-01", "...", "REQ-TAG-06"]},
    {"key": "SPEC-001", "role": "constraint", "requirements": ["REQ-LIST-01", "..."]}
  ],
  "code": [
    {"path": "taskboard/app.py", "symbols": [{"name": "list_tasks", "line": 18, "end_line": 38}]},
    {"path": "taskboard/store.py", "symbols": [{"name": "filter_tasks", "line": 104}]}
  ],
  "tests": [
    {"path": "tests/test_tag_filter.py", "role": "target", "cases": ["test_filter_by_tag", "..."]},
    {"path": "tests/test_tasks_api.py", "role": "regression", "cases": ["test_health", "..."]}
  ],
  "state": {"done": [], "todo": [], "verifications": []}
}
```

每一条都带真实路径、行号或测试用例名，评审核对时可直接打开对应文件。

**选择方式**：任务文本切词 → 文档打分（标题权重 3、正文权重 1）→ 最高分规格作为主规格 → 沿 `spec_refs` 展开「适用模块」为代码、「关联测试」为目标测试；主规格的「上游规格」作为兼容性约束，其关联测试作为回归测试。所以即使 `app.py` 里没有出现"标签"二字，也能被定位到。

**自检**（缺任何必要来源都会以退出码 1 失败）：

```powershell
.\.venv\Scripts\python.exe scripts\verify_context.py
```

**单元测试**（切词、diff 提取；数据库/PowerContext 不可用时自动 skip）：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

---

## 6. 用 MiniMax 生成补丁

```powershell
.\.venv\Scripts\python.exe -m ctx.cli patch --context records\context-TASK-001.json --apply
```

- 提示词 = 主规格全文 + 约束规格全文 + 待改代码 + 目标/回归测试 + 输出格式要求
- 先看提示词而不调用模型：加 `--dry-run`，产物在 `records/patches/*.prompt.md`
- 模型输出只接受 unified diff（` ```diff ` 块），落盘到 `records/patches/TASK-001-<时间>.diff`，同时保存完整提示词 `TASK-001-<时间>.prompt.md`
- `--apply` 会先 `git apply --check` 再应用
- 每次调用的请求、响应、token 用量、时延都写入 `records/minimax/calls-YYYYMMDD.jsonl`

---

## 7. 测试与验证

样例工程是 `demo/taskboard`，本次任务见 [SPEC-002](demo/taskboard/specs/SPEC-002-tag-filter.md)。

```powershell
cd demo\taskboard
..\..\.venv\Scripts\python.exe -m pytest -q
```

| 阶段 | 目标测试 `test_tag_filter.py` | 回归测试 `test_tasks_api.py` |
| --- | --- | --- |
| 改前 | 7 个全部失败 | 8 个全部通过 |
| 改后 | 7 个全部通过 | 8 个全部通过 |

带证据的运行方式（记录命令、退出码、commit、测试文件哈希）：

```powershell
cd minimax
.\.venv\Scripts\python.exe scripts\run_tests.py --label baseline
.\.venv\Scripts\python.exe scripts\run_tests.py --label after-fix
```

结果追加到 `records/test-runs.jsonl`，完整输出在 `records/test-logs/`。

---

## 8. 任务状态（PowerContext）

启动本地 Server（SQLite，数据在 `state/powercontext`）：

```powershell
.\.venv\Scripts\powercontext.exe server run --env-file config\powercontext.env
```

另开终端读写状态：

```powershell
# 写入
.\.venv\Scripts\python.exe -m ctx.cli state-save --task-id TASK-001 --file records\state-TASK-001.json

# 读取（Server 重启后同样可用）
.\.venv\Scripts\python.exe -m ctx.cli state-load --task-id TASK-001

# 生成上下文时合并状态（给了 --task-id 就会自动读 PowerContext）
.\.venv\Scripts\python.exe -m ctx.cli build --task "..." --task-id TASK-001
```

状态正文是 JSON（`done` / `todo` / `verifications`），以 `STATE TASK-001` 前缀存入 PowerContext 的 Memory，Scope 为 `mmx-sdd-taskboard`。Scope ID 缓存在 `state/scope.json`；缓存丢失时会先按标题查找，找不到再用固定 idempotency key 创建。

---

## 9. 规格更新后重新导入

`docs/03-verification.md` 记录了一次完整演示：SPEC-002 从 1.0 升到 1.1（新增 REQ-TAG-06），重新 `import` 后，`ctx build` 输出的 `requirements` 从 5 条变成 6 条。前后两份上下文分别保存在 `records/context-before-spec-update.json` 与 `records/context-after-spec-update.json`。

---

## 10. 已知限制

- 检索是词面匹配（中文按二元组切分），没有接向量检索；对样例工程足够，规模变大后应换成 embedding + 向量索引。
- PowerContext 以 SQLite 模式本机运行，未接 Generation/Embedding 模型，因此只验证显式 Memory 的存取，不涉及自动抽取。
- `ctx patch` 依赖有效的 MiniMax 额度；无额度时命令以退出码 3 失败并提示。
- Windows 控制台默认 GBK，脚本已强制 UTF-8；若仍乱码先执行 `chcp 65001`。
