# 验收对照清单

评审按六项必做验收时，可以直接照这张表逐条执行。命令都在 `minimax/` 目录下运行。

前置：完成 README 第 3 节安装，seekdb 已启动（`127.0.0.1:2881`），`.env` 已填 Key。

---

## 1. 能够运行

```powershell
.\.venv\Scripts\python.exe -m ctx.cli import
.\.venv\Scripts\python.exe scripts\verify_context.py
```

| 检查 | 预期 |
| --- | --- |
| import 输出 | `total: 9`，`code:4 / spec:2 / test:3` |
| verify_context | 打印来源清单后输出 `[OK]`，退出码 0 |
| 空库可重建 | 删掉 `mmx_ctx` 后重跑 import 仍得到 9 篇文档（`records/clean-init.log`） |

---

## 2. MiniMax 实际参与

```powershell
.\.venv\Scripts\python.exe tools\check_minimax.py
.\.venv\Scripts\python.exe -m ctx.cli patch --context records\context-TASK-001.json --apply
```

| 检查 | 预期 |
| --- | --- |
| 自检 | `MINIMAX_OK`，`usage` 有 token 数 |
| 补丁 | 生成 `records/patches/TASK-001-*.diff` 与同名 `.prompt.md` |
| 调用记录 | `records/minimax/calls-*.jsonl` 里 `purpose=patch-generation` 且 `ok=true` |

> 当前状态：账户额度未开通前，调用返回 `402 insufficient balance (1008)`（记录在 `calls-20261029.jsonl`）。
> 额度开通后重跑上面两条命令即可补齐。

---

## 3. 上下文正确

```powershell
.\.venv\Scripts\python.exe -m ctx.cli build --task "为任务列表增加按标签筛选" --task-id TASK-001 --out records\context-TASK-001.json
```

| 检查 | 预期 |
| --- | --- |
| 规格 | `SPEC-002`（primary，REQ-TAG-01~06）、`SPEC-001`（constraint，REQ-LIST-01~05） |
| 代码 | `taskboard/app.py::list_tasks`、`taskboard/store.py::filter_tasks` |
| 测试 | `test_tag_filter.py`（target，7 例）、`test_tasks_api.py`（regression，8 例） |
| 状态 | `state.done=4`、`state.todo=3`、`state.verifications=2`，`state_source.system=PowerContext` |
| 规格更新 | 改 SPEC-002 后重新 import，`requirements` 从 5 条变 6 条（`context-before-spec-update.json` vs `context-after-spec-update.json`） |

---

## 4. 数据库实际参与

```powershell
.\.venv\Scripts\python.exe scripts\dump_sql_evidence.py
```

| 检查 | 预期 |
| --- | --- |
| 版本 | `5.7.25-OceanBase seekdb-v1.4.0.0` |
| 表 | `documents` / `spec_refs` / `task_state` |
| 数据 | 9 篇文档、7 条引用 |
| 检索 SQL | `SELECT ... FROM documents WHERE kind='spec' AND (title LIKE %s OR content LIKE %s ...)` |

证据：`records/seekdb-queries.log`。

---

## 5. 状态能够复用

```powershell
# 终端 A：启动 Server
.\.venv\Scripts\powercontext.exe server run --env-file config\powercontext.env

# 终端 B：写入 → 停掉 A → 重启 A → 读取
.\.venv\Scripts\python.exe -m ctx.cli state-save --task-id TASK-001 --file records\state-TASK-001.json
.\.venv\Scripts\python.exe -m ctx.cli state-load --task-id TASK-001
```

| 检查 | 预期 |
| --- | --- |
| 写入 | 返回 `scope_id`、`artifact`、`mode=append` |
| 重启后读取 | `found=true`，`state.done/todo/verifications` 与写入一致 |
| 重复写入 | 生成新 artifact，读取取 `updated_at` 最新一条 |

---

## 6. 代码修改有效

```powershell
.\.venv\Scripts\python.exe scripts\run_tests.py --label baseline
# 生成补丁并应用后
.\.venv\Scripts\python.exe scripts\run_tests.py --label after-fix
```

| 阶段 | 目标测试 | 回归测试 | 退出码 |
| --- | --- | --- | --- |
| 改前 | 7 failed | 8 passed | 1 |
| 改后 | 7 passed | 8 passed | 0 |

证据：`records/test-runs.jsonl`、`records/test-logs/`。

---

## 附：一键串起来

```powershell
powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
```
