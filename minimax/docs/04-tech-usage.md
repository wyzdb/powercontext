# 技术使用记录

本文件汇总三项技术在本次任务中的实际使用情况；原始证据都在 `records/` 下，可按命令复现。

---

## 1. MiniMax

### 1.1 接入方式

| 项 | 取值 |
| --- | --- |
| 协议 | OpenAI 兼容（`POST /chat/completions`） |
| Base URL | `https://api.minimax.cn/v1`（国内站） |
| 模型 | `MiniMax-M3.1-Flash` |
| SDK | `openai==3.41.0` |
| 鉴权 | `Authorization: Bearer <订阅 Key>`，Key 只存在 `.env`（已 gitignore） |
| 参数 | `max_completion_tokens=8192`，`reasoning_effort=max` |
| 封装 | `tools/minimax_client.py`，每次调用写一条 JSONL |

调用记录字段：`ts`、`call_id`、`purpose`、`model`、`base_url`、`latency_ms`、`request`（含完整 messages）、`response`（正文与思考）、`usage`、`error`。

### 1.2 调用历史

| 时间 | 用途 | 结果 | 记录 |
| --- | --- | --- | --- |
| 10:52 | 环境自检（`tools/check_minimax.py`） | `402 insufficient balance (1008)` | `records/minimax/calls-20261029.jsonl` |
| 10:53 | 区域/模型矩阵排查 | 国内站鉴权通过、4 个模型均 402；国际站 401 | 见本文 §1.3 |
| 11:08 | 补丁生成（`ctx.cli patch`） | `402 insufficient balance (1008)` | 同上 |
| 11:14 | 提示词 dry-run（`--dry-run`，不调用模型） | 生成 471 行、11300 字符提示词 | `records/patches/TASK-001-20261029-111414.prompt.md` |

> 说明：订阅 Key 本身有效（`GET /v1/models` 返回 200，可见 9 个模型），但账户当前没有可用额度，
> 因此补丁生成尚未产生成功调用。额度恢复后执行 `ctx.cli patch` 即可补齐成功的调用记录与补丁文件。

### 1.3 排查记录（可复现）

```bash
# 鉴权与模型列表
curl -H "Authorization: Bearer $MINIMAX_API_KEY" https://api.minimax.cn/v1/models

# 单次最小对话
curl -X POST https://api.minimax.cn/v1/chat/completions \
  -H "Authorization: Bearer $MINIMAX_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"MiniMax-M3.1-Flash","messages":[{"role":"user","content":"hi"}],"max_completion_tokens":16}'
```

结果：`/v1/models` → 200；对话 → `{"type":"insufficient_balance_error","message":"insufficient balance (1008)"}`。

### 1.4 复现补丁生成

```powershell
cd minimax
.\.venv\Scripts\python.exe -m ctx.cli patch --context records\context-TASK-001.json --apply
```

产物：`records/patches/TASK-001-<时间>.diff`（补丁）、`TASK-001-<时间>.prompt.md`（完整提示词）。

---

## 2. seekdb

### 2.1 实例

| 项 | 取值 |
| --- | --- |
| 版本 | `5.7.25-OceanBase seekdb-v1.4.0.0` |
| 地址 | `127.0.0.1:2881`，用户 `root`，空密码 |
| 库 | `mmx_ctx`（`utf8mb4`） |
| 驱动 | `PyMySQL==2.2.8` |

### 2.2 表与数据

| 表 | 行数 | 说明 |
| --- | --- | --- |
| `documents` | 9 | 2 规格 + 4 代码 + 3 测试，含全文与 `sha256` |
| `spec_refs` | 8 | 规格 → 模块 / 测试 / 上游规格 |
| `task_state` | 0 | 预留（状态实际走 PowerContext） |

### 2.3 查询与用途

检索不是把全表读进内存：规格候选先用 SQL 预筛，再在应用层打分。

```sql
SELECT doc_key, kind, path, title, content, sha256, meta
FROM documents
WHERE kind = 'spec' AND (title LIKE %s OR content LIKE %s OR ...)
LIMIT 20;
```

完整执行记录（含版本、表、行数、`spec_refs` 明细、实际 SQL 与参数）见 [`records/seekdb-queries.log`](../records/seekdb-queries.log)，生成命令：

```powershell
.\.venv\Scripts\python.exe scripts\dump_sql_evidence.py
```

---

## 3. PowerContext

### 3.1 部署

| 项 | 取值 |
| --- | --- |
| 版本 | `powercontext[cli,server]==1.4.1` |
| 存储 | SQLite，数据目录 `state/powercontext`（`POWERCONTEXT_HOME`） |
| 监听 | `http://127.0.0.1:18080`，`ACCESS_MODE=disabled`（仅本机） |
| 启动 | `powercontext server run --env-file config/powercontext.env` |

### 3.2 写入与复用

| 对象 | 值 |
| --- | --- |
| Scope | `mmx-sdd-taskboard`，`scp_1bq2h3zc1cx29vrr74j15jpq8v` |
| Memory 家族 | `atomic-memory`，每次写入生成一个 artifact（`art_...`），按 `updated_at` 取最新 |
| 正文 | `STATE TASK-001 {...}`，含 `done / todo / verifications` |

> artifact ID 每次写入都会变化，以命令输出为准；`load_state` 会按 `updated_at` 选出最新一条，
> 因此重启后读到的一定是最后一次写入的状态。

```powershell
# 写入
.\.venv\Scripts\python.exe -m ctx.cli state-save --task-id TASK-001 --file records\state-TASK-001.json

# 停掉 Server 再启动，然后读取（已实测返回同一 artifact/revision）
.\.venv\Scripts\python.exe -m ctx.cli state-load --task-id TASK-001

# 生成上下文时合并状态
.\.venv\Scripts\python.exe -m ctx.cli build --task "..." --task-id TASK-001 --with-state
```

Scope 发现顺序：`state/scope.json` 缓存 → 按标题 `mmx-sdd-taskboard` 查找 → 用固定 idempotency key 创建。

---

## 4. 复现性说明

- 所有命令都在 `minimax/` 目录下执行，路径不含个人目录。
- `.env`、`state/`、`records/*.jsonl` 等运行时数据已 gitignore；需要随作品提交的记录用 `git add -f` 单独纳入。
- 测试日志记录命令、退出码、commit、测试文件哈希，见 `records/test-runs.jsonl`。
