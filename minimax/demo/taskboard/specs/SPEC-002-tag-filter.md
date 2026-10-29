# SPEC-002 任务列表按标签筛选

| 字段 | 值 |
| --- | --- |
| 规格编号 | SPEC-002 |
| 状态 | 已批准 |
| 版本 | 1.1 |
| 生效日期 | 2026-10-29 |
| 适用模块 | `taskboard/app.py`、`taskboard/store.py` |
| 上游规格 | SPEC-001（必须保持兼容） |
| 关联测试 | `tests/test_tag_filter.py` |
| 回归测试 | `tests/test_tasks_api.py` |
| 任务 | TASK-001 为任务列表增加按标签筛选 |

## 1. 背景

看板任务增长到两位数后，按标签（backend / frontend / data / ops / urgent）筛选成为高频诉求。
当前 `GET /api/tasks` 只支持 `status`，前端只能拿到全量数据再自行过滤，导致移动端首屏变慢。

## 2. 需求

### REQ-TAG-01 支持 tag 查询参数

`GET /api/tasks?tag=<label>` 只返回 `tags` 数组包含该标签的任务。

### REQ-TAG-02 匹配规则

- 标签匹配**大小写不敏感**：`tag=backend` 与 `tag=Backend` 结果相同。
- 按**完整标签**匹配，不做子串匹配：`tag=back` 不得匹配 `backend`。

### REQ-TAG-03 与 status 组合

当 `tag` 与 `status` 同时出现时，两个条件取交集：
`GET /api/tasks?status=open&tag=backend` 返回既未完成、又带 backend 标签的任务。

### REQ-TAG-04 边界输入

- `tag=`（空字符串）视为未提供该参数，等价于不按标签过滤。
- 未知标签（不匹配任何任务）返回空列表，HTTP 状态码仍为 200，不得报错。

### REQ-TAG-05 兼容性

响应结构 `{"items": [...], "count": n}`、任务字段、`id` 升序排列均保持不变；
`status` 的校验逻辑（REQ-LIST-02）不得改变。

### REQ-TAG-06 参数顺序无关

`?tag=a&status=b` 与 `?status=b&tag=a` 必须返回相同结果，筛选逻辑不得依赖查询参数的书写顺序。

## 3. 非目标

- 不支持多标签 OR / AND 组合（如 `tag=backend,data`），本期不做。
- 不引入数据库或缓存层，数据仍来自 `store.TASKS`。

## 4. 约束

- 不得修改 `tests/` 下任何测试文件来迁就实现。
- 不得破坏 SPEC-001 的既有行为。

## 5. 验收

```bash
pytest tests/test_tag_filter.py -q   # 本次新增，改前应失败
pytest tests/test_tasks_api.py -q    # 回归，改前改后都应通过
```

`test_tag_filter.py` 全部通过，且 `test_tasks_api.py` 无回归，即视为满足本规格。

## 6. 变更记录

| 版本 | 日期 | 变更 | 影响 |
| --- | --- | --- | --- |
| 1.0 | 2026-10-29 | 初版：REQ-TAG-01 ~ REQ-TAG-05 | 建立 tag 筛选契约 |
| 1.1 | 2026-10-29 | 新增 REQ-TAG-06（参数顺序无关） | 现有测试不变；实现需保证组合条件与参数顺序解耦 |

