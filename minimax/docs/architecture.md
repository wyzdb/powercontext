# 架构说明

## 1. 目标与边界

目标：给「AI 开发助手」补上一个工程上下文模块，使它在改代码之前能拿到
**当前有效的规格、需要改的代码、验证用的测试**，并在跨会话时知道**已经做到哪一步**。

边界：

- 不重新造 Agent 框架：模块只负责选上下文、调模型、应用补丁、跑测试、存状态。
- 不引入 embedding 依赖：检索用 seekdb 中的倒排索引完成，离线可复现。
- 不信任模型输出：补丁必须通过上下文行校验才能落盘，测试不过就不算完成。

## 2. 数据模型（seekdb）

| 表 | 关键列 | 用途 |
| --- | --- | --- |
| `sdd_specs` | `spec_id` PK、`version`、`status`、`applies_to`、`verified_by`、`content_sha` | 规格文件头信息 |
| `sdd_spec_clauses` | `clause_id` PK（如 `SPEC-ORD-004/R2`）、`body`、`line_start/end`、`path` | 条款级规格，上下文的最小单位 |
| `sdd_code_symbols` | `symbol_id` PK（`orderflow.service.list_orders`）、`kind`、`signature`、`line_start/end` | AST 抽出的函数/方法/类 |
| `sdd_tests` | `test_id` PK（`tests/x.py::test_y`）、`kind`（target/regression）、`spec_refs`、`code_refs` | 测试与规格、符号的引用关系 |
| `sdd_terms` | PK(`term`,`ref_kind`,`ref_id`)、`weight` | 倒排索引 |
| `sdd_tasks` / `sdd_task_events` | `task_id`、`status`、`step`、`detail` | 任务与事件流 |
| `sdd_contexts` | `context_id` PK、`payload` | 每次构建的上下文快照 |
| `sdd_config` | `config_key` PK | PowerContext scope 等运行配置 |
| `sdd_query_log` | `purpose`、`sql_sha`、`row_count`、`duration_ms` | 数据库参与证据 |

所有表使用 utf8mb4；写入统一走 `ON DUPLICATE KEY UPDATE`，`ingest` 在一个事务里
先清空再写入，保证重复导入幂等。

## 3. 索引构建

1. **规格**：Markdown + front matter；`## R<n>` 切条款，记录 1 起始的行号区间。
   `status` 为 `proposed` 的规格代表「待实现需求」，其条款在上下文中 `role=required`，
   其余 `active` 条款是 `role=constraint`（必须保持）。
2. **代码**：`ast` 遍历 `business/src/**/*.py`，抽顶层函数、类与方法；
   `symbol_id = 模块名 + 限定名`，签名用 `ast.unparse` 还原，记录行号区间。
3. **测试**：`ast` 遍历 `business/tests/test_*.py`，识别 `test_*` 函数；
   紧邻定义的 `# spec: X/Rn[, ...]` 与 `# covers: symbol_id` 注释建立引用；
   若没有注释，回退到规格 front matter 的 `verified_by`。
   引用了 `proposed` 规格的测试自动归为 `target`，其余为 `regression`。
4. **倒排**：同一分词器处理三类文本，权重：条款标题 4、条款正文 1、规格号 3、
   `applies_to` 2；符号限定名 3、签名 2、doc 1；测试名 3、doc 2、引用 2。

分词器（`tokenizer.py`）对英文保留完整标识符并额外切分 `created_after → created + after`，
对中文生成二元组并保留 2–6 字短语，`SPEC-ORD-004/R2` 归一化为单个词项。

## 4. 检索与闭包

```
task text ──tokenize──► terms
terms ──SQL──► sdd_terms GROUP BY ref_kind, ref_id ORDER BY SUM(weight)
   │
   ├─ spec  ──► 条款（required / constraint）
   ├─ code  ──► 相关符号
   └─ test  ──► 相关测试
```

闭包（`context_builder.py`）：

1. 选中条款的 `applies_to` 符号与 `verified_by` 测试 → 补入；
2. 选中符号被哪些测试引用（`code_refs LIKE`）→ 补入回归测试；
3. 目标测试（`kind=target`）引用的条款若未被检索到 → 补入（例如错误信封条款）；
4. 目标测试 `code_refs` 指向的符号 → 标为 `modify`。

`role=modify` 的判定：`proposed` 条款的 `applies_to` 并集 + 目标测试的 `code_refs`。
输出按「required 在前、modify 在前」稳定排序，因此同一份数据重复构建结果一致。

## 5. 上下文载荷

`build` 输出 JSON（并渲染 Markdown）：

- `specs[]`：`clause_id / version / status / role / body / source{path,line_start,line_end} / score / reason`
- `code[]`：`symbol_id / kind / signature / role / source`
- `tests[]`：`test_id / kind / spec_refs / code_refs / source`
- `change_targets[]`、`state`（PowerContext 读回）、`queries[]`（本次 SQL 摘要）、`summary`

写入 `sdd_contexts` 与 `records/contexts/<context_id>.{json,md}`。

## 6. 状态协议（PowerContext）

- Scope：`sdd-context`，`create_scope` 幂等键固定；scope_id 存 `sdd_config`，避免每次重建。
- 一条任务状态 = 一个 Source（`source_type=content`），内容是 `TaskState` JSON：
  `task_id / status / step / done / todo / verifications / context_id / revision`。
- Source id 形如 `sdd-task-state-<task_id>-r<rev>-<HHMMSSffffff>`：
  Source 只追加，不复用同一 id，避免内容冲突（409）。
- 读回：`list_sources` 取该任务前缀下 `position` 最大的 Source，解析 JSON 注入上下文。
- 验证：`status` 子命令与 `run_sample.py` 都在新进程中读取，等价于「重启模块」。

## 7. 补丁协议

模型输出 `<<<PATCH ... PATCH>>>` 包裹的 unified diff。`patcher.py`：

1. 解析 `---/+++` 与 `@@`，拒绝绝对路径与 `..` 越界；
2. 按 hunk 顺序应用，上下文/删除行必须与文件一致（忽略行尾空白）；
3. 允许 hunk 行号漂移：在声明位置 ±80 行内寻找整块上下文匹配的位置（类似 `patch` 的 fuzz）；
4. 先 `dry_run` 全量校验，再真实写入；任何失败都不落盘，并保留 `PatchError` 记录。

## 8. 一次 run 的记录链

```
task text
  └─ build ──► records/contexts/ctx-*.json
       └─ prompt ──► records/minimax/run-*.prompt.md
            └─ MiniMax ──► records/minimax/run-*.json（含 request/response/usage/request_id）
                 └─ patch ──► artifacts/change.diff（与响应中的 diff 一致）
                      └─ pytest ──► records/tests/*.log
                           └─ PowerContext ──► records/powercontext/state.jsonl
                                └─ 汇总 ──► records/sample/sample-*.json
```

## 9. 失败处理与扩展

- 模型返回非 diff、补丁不匹配、测试失败都会写一条 `outcome=failed` 记录并更新状态为
  `failed`，不会把错误状态留在「已完成」。
- 成本/时延：一次成功调用 prompt 4544 tokens、completion 756 tokens、约 6.1 秒；
  检索查询在毫秒级，索引 20 个测试 / 30 个符号耗时 < 1 秒。
- 扩展方向：规格变更已支持（`spec-demo apply` 后重新导入即生效）；
  跨会话恢复由 PowerContext Source 承担；跨模块协作可把 `sdd-terms` 的 `ref_kind`
  扩展为 `doc`/`adr` 等来源。
