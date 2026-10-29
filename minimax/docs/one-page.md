# 一页技术说明：SDD 上下文管理系统

## 模块结构

```
CLI (scripts/sdd.py)
  ├── db-init / ingest ── indexer ──► store ──► seekdb
  ├── build ──────────── context_builder ──► records/contexts/*.json|md
  ├── run ── pipeline ──► minimax_client ──► patcher ──► pytest
  │                    └► powercontext_state ──► PowerContext Server
  └── status / reset-sample / spec-demo
```

上下文模块只有一层进程：CLI 负责参数，`indexer` 与 `context_builder` 是纯逻辑，
`store` 负责 seekdb 访问，`powercontext_state` 负责 PowerContext 访问，
`pipeline` 把「上下文 → 代码修改 → 验证 → 状态」串成一次可记录的执行。

## 上下文是怎么选出来的

1. **规格切成条款**：每个 `## R<n>` 是一个稳定标识（如 `SPEC-ORD-004/R2`），
   前置元数据声明 `applies_to`（代码符号）与 `verified_by`（测试文件）。
2. **建倒排索引**：`sdd_terms(term, ref_kind, ref_id, weight)`，中文按二元组、
   英文按标识符及其片段切分，规格标题权重 4、正文 1，代码限定名 3、签名 2，测试名 3。
3. **检索排序**：任务文本经同一分词器得到词项，`SELECT ref_kind, ref_id,
   SUM(weight) score FROM sdd_terms WHERE term IN (...) GROUP BY ...` 排序。
4. **引用闭包**：选中条款后补入其 `applies_to` 符号与 `verified_by` 测试；
   再按「符号 → 引用它的测试」「目标测试 → 它引用的条款」双向补全，
   保证「要改什么」和「哪些原有行为必须保持」同时出现在上下文里。
5. **输出可核对**：每条规格/代码/测试都带仓库路径与行号，JSON 与 Markdown 双份落盘。

## 三项技术的分工

- **seekdb**：`sdd_specs`、`sdd_spec_clauses`、`sdd_code_symbols`、`sdd_tests`、
  `sdd_terms`、`sdd_tasks`、`sdd_task_events`、`sdd_contexts`、`sdd_config`、`sdd_query_log`
  共 10 张表。每次检索的 SQL、参数摘要、行数、耗时同时写入表与
  `records/seekdb/queries.jsonl`，上下文里的每个条目都能追溯到一次真实查询。
- **MiniMax**：`MiniMax-M3` 通过 OpenAI 兼容接口接收规格条款、文件内容与测试清单，
  只输出 unified diff；`records/minimax/<run>.json` 保存模型名、请求 ID、token 用量、
  prompt、响应、补丁与测试退出码，`artifacts/change.diff` 与补丁逐行一致。
  `M3` 默认把 completion 预算全部用于推理，客户端显式发送 `thinking: disabled`。
- **PowerContext**：任务状态不是本地文件，而是 Scope 下的 Source。
  每次保存写入一条新 Source（`sdd-task-state-<task>-r<rev>-<时刻>`），
  读取时取该任务前缀下 `position` 最大的 Source。`build` 会把读到的
  已完成、待办、验证结果渲染进上下文；`status` 与 `run_sample.py` 用**新进程**验证重启后可读。

## 可验证的结果

- 修改前：4 个目标测试失败（`AssertionError` / 断言失败，不是环境错误），17 个回归测试通过。
- 修改后：同一组目标测试 4 passed，回归测试 17 passed，全量 21 passed。
- 上下文：11 条规格条款、14 个代码符号、4 个待修改符号、4 个目标测试、16 个回归测试。
- 数据库：一次上下文构建触发 15 次查询，全部记录在 `sdd_query_log`。
- 状态：PowerContext 中 `task-order-created-after` 的最新 Source 为 `completed`，
  含 2 条验证结果；在新进程中 `status` 读回一致，`build --json` 也把该状态注入新上下文
  （`records/powercontext/restart-context.json`）。
- 规格更新：执行 `spec-demo apply` 后重新导入，输出条款版本从 v1 变为 v2 并出现新增的
  `SPEC-ORD-004/R5`（`records/spec-update/apply.json`），`restore` 后回到 17 条。

## 2026-10-29 的真实服务端到端复跑

以上结论在 2026-10-29 用**真实服务**重新跑过一遍：seekdb `v1.4.0.0` 容器、
PowerContext `1.4.1` 服务端、MiniMax 官方接口 `https://api.minimaxi.com/v1` 全部在线参与。

| 证据 | 位置 |
| --- | --- |
| MiniMax 调用（请求 ID `073232ae526ecd34c40d866df3801cd7`，prompt/响应/补丁） | `records/minimax/run-20261029T081123882396-4aa9d9.*` |
| 上下文（含 15 次检索查询的来源） | `records/contexts/ctx-20261029T081123817310-24d063.json` |
| 红/绿测试日志（4 failed → 4 passed、17 passed、21 passed） | `records/tests/20261029T0811*.log` |
| 状态写入与新进程复用 | `records/powercontext/state.jsonl`、`records/sample/sample-20261029T081154.json` |
| 离线一致性校验（live 标记由记录算出） | `records/native-validation-2026-10-29-live/result.json` |

两次独立运行由 MiniMax 给出**不同但都通过测试**的补丁（`service.py` +16 行 / +27 行），
说明验收不依赖模型复现同一份补丁。命令、退出码与环境见
[`live-e2e-2026-10-29.md`](live-e2e-2026-10-29.md)。
