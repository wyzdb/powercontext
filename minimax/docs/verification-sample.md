# 验证样例：为订单列表增加创建时间筛选

## 1. 任务描述

> 为 orderflow 的订单列表接口增加按创建时间筛选能力：`GET /orders` 支持 `created_after` 参数，
> 取值为 `YYYY-MM-DD`，边界当天 `00:00:00` 与 `23:59:59` 的订单都必须包含，边界前一天的订单必须排除；
> 非法日期返回 HTTP 400，错误码为 `invalid_created_after`；该参数要和 `status`、`min_total`、
> 分页同时生效，先过滤后分页。不得改变原有的分页语义（SPEC-ORD-001）、状态筛选（SPEC-ORD-002）、
> 金额下限（SPEC-ORD-003）与排序规则（SPEC-ORD-005）。

任务文本定义在 `context/sdd_context/sample.py`（`SAMPLE_TASK`），
任务编号固定为 `task-order-created-after`。

## 2. 有效规格

上下文必须包含下列条款（子集即可，不能缺项）：

| 条款 | 作用 | 来源 |
| --- | --- | --- |
| `SPEC-ORD-004/R1` 参数形态 | 新增参数、字符串透传 | `business/specs/SPEC-ORD-004-created-after.md:12-14` |
| `SPEC-ORD-004/R2` 过滤语义 | 按日历日比较、边界当天全含、`created_at` 是字符串 | 同上 `:16-18` |
| `SPEC-ORD-004/R3` 非法输入 | 400 + `invalid_created_after` | 同上 `:20-22` |
| `SPEC-ORD-004/R4` 组合与分页 | 先过滤、后排序、再分页 | 同上 `:24-26` |
| `SPEC-API-001/R2` 错误信封 | `{"error": {"code", "message"}}` | `business/specs/SPEC-API-001-query-contract.md:16-18` |
| `SPEC-ORD-001/R2` total/pages | 按过滤后集合计算 | `business/specs/SPEC-ORD-001-pagination.md:16-18` |
| `SPEC-ORD-005/R1` 排序键 | `(-total_cents, id)` 不变 | `business/specs/SPEC-ORD-005-stable-ordering.md:12-14` |

**必须保持的原有行为**：状态筛选的大小写与错误码、`min_total` 闭区间、
分页边界（`page>=1`、`1<=page_size<=100`）、排序稳定性、响应字段集合、
未知路由 404、`/health` 返回 `{"status":"ok"}`。

### 上下文中必须出现的代码与测试来源

| 类型 | 标识 | 来源 |
| --- | --- | --- |
| 待修改代码 | `orderflow.service.list_orders` | `business/src/orderflow/service.py:83-114` |
| 待修改代码 | `orderflow.api.parse_list_query` | `business/src/orderflow/api.py:51-59` |
| 待修改代码 | `orderflow.api.ListQuery` | `business/src/orderflow/api.py:17-39` |
| 待修改代码 | `orderflow.api.ListQuery.as_filters` | `business/src/orderflow/api.py:33-39` |
| 目标测试 | `tests/test_created_after_api.py::test_created_after_filters_orders` | 同文件 `:13` |
| 目标测试 | `tests/test_created_after_api.py::test_created_after_includes_the_boundary_day` | 同文件 `:25` |
| 目标测试 | `tests/test_created_after_api.py::test_invalid_created_after_returns_400` | 同文件 `:34` |
| 目标测试 | `tests/test_created_after_api.py::test_created_after_combines_with_status_and_paging` | 同文件 `:41` |
| 回归测试 | `tests/test_service_listing.py`、`tests/test_api_listing.py` | 两个文件，共 17 个用例 |

## 3. 初始数据

- 业务数据：`business/src/orderflow/data/orders.json`，12 条订单，覆盖四种状态与边界日期。
- 测试数据：`business/tests/conftest.py` 中 `SAMPLE_ORDERS` 6 条，包含
  `2026-09-15T00:00:00+08:00`（边界零点）、`2026-09-15T23:59:59+08:00`（边界末刻）、
  `2026-09-14T23:59:59+08:00`（边界前一天）。
- 初始代码：`business/src/orderflow/service.py` 的 `list_orders` 没有 `created_after` 参数；
  `business/tests/test_created_after_api.py` 的 4 个目标测试因此失败。

## 4. 操作步骤

```bash
# 0) 依赖与基础设施
python -m pip install -r requirements.txt
docker run -d --name seekdb -p 2881:2881 quay.io/oceanbase/seekdb:latest
cp .env.example .env      # 填入 MINIMAX_API_KEY 与绝对 SQLite 路径
python scripts/powercontext_server.py .env   # 保持运行

# 1) 自检 + 建库
python scripts/sdd.py doctor
python scripts/sdd.py db-init

# 2) 重置到「修改前」并跑目标测试（必须失败）
python scripts/sdd.py reset-sample --task-id task-order-created-after --clear-state
cd business && python -m pytest tests/test_created_after_api.py -q ; cd ..
# 期望：4 failed

# 3) 一键验证样例（导入 → 上下文 → MiniMax → 测试 → 重启检查）
python scripts/run_sample.py
```

也可以逐步执行：

```bash
python scripts/sdd.py ingest
python scripts/sdd.py build --task-id task-order-created-after          # 打印 Markdown 上下文
python scripts/sdd.py run   --task-id task-order-created-after          # 调用 MiniMax 并验证
python scripts/sdd.py status --task-id task-order-created-after         # 新进程读取状态
```

## 5. 预期结果

| 阶段 | 命令 | 期望 |
| --- | --- | --- |
| 修改前目标测试 | `pytest tests/test_created_after_api.py -q` | `4 failed`，原因是参数缺失或过滤未生效，不是导入错误 |
| 回归测试 | `pytest tests/test_service_listing.py tests/test_api_listing.py -q` | `17 passed` |
| 上下文 | `build --task-id ...` | 含 `SPEC-ORD-004/R1-R4`、`SPEC-API-001/R2`、`SPEC-ORD-001/R2`、`SPEC-ORD-005/R1`；4 个 `role=modify` 符号；4 个目标测试、16 个回归测试 |
| MiniMax 修改 | `run --task-id ...` | `outcome=success`，`changes` 覆盖 `src/orderflow/api.py` 与 `src/orderflow/service.py` |
| 修改后目标测试 | 同上 | `4 passed` |
| 修改后回归测试 | 同上 | `17 passed` |
| 全量测试 | `pytest tests -q` | `21 passed` |
| 状态复用 | `status --task-id ...` + `build --task-id ... --json` | `powercontext_state.status=completed`，`verifications` 长度 2；新上下文的 `state.status` 同为 `completed` |

`run_sample.py` 会把上述结果写入 `records/sample/sample-<时间>.json`，
并在 `records/tests/` 保留每个阶段的完整日志。

## 6. 规格更新检查

```bash
python scripts/sdd.py spec-demo apply     # 导入 v2 规格并重建上下文
python scripts/sdd.py spec-demo restore   # 还原 v1 并重新导入
```

`apply` 的输出中 `SPEC-ORD-004/*` 的 `version` 变为 `2`，并新增 `SPEC-ORD-004/R5`
（筛选审计字段）；`restore` 后条款数回到 17。记录见 `records/spec-update/`。

## 7. 重置方法

```bash
python scripts/sdd.py reset-sample --task-id task-order-created-after --clear-state
```

- 从 `artifacts/before/` 恢复 `business/src`、`business/tests`、`business/specs`；
- 删除 `sdd_tasks`、`sdd_task_events`、`sdd_contexts` 中该任务的记录；
- 在 PowerContext 写入 `status=empty` 的新 Source；
- 如需彻底清空状态库，停止 PowerContext 后删除 `.state/powercontext.db`，
  再执行 `python scripts/sdd.py db-init --reset`。

执行后重新运行 `python scripts/run_sample.py` 即可复现「修改前失败 → 修改后通过」。
