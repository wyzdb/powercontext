# SPEC-001 任务列表接口（基线）

| 字段 | 值 |
| --- | --- |
| 规格编号 | SPEC-001 |
| 状态 | 已发布 |
| 版本 | 1.0 |
| 生效日期 | 2026-10-15 |
| 适用模块 | `taskboard/app.py`、`taskboard/store.py` |
| 关联测试 | `tests/test_tasks_api.py` |

## 1. 目的

定义任务看板对外提供的任务列表接口，作为其他规格（如 SPEC-002）的兼容性基线。

## 2. 需求

### REQ-LIST-01 返回全部任务

`GET /api/tasks` 在不带任何查询参数时返回全部任务，按 `id` 升序排列。

### REQ-LIST-02 按状态过滤

- 支持查询参数 `status`，取值只能是 `open`、`in_progress`、`done`。
- 传入非法值时返回 HTTP 400，响应体包含 `error="invalid_status"` 与 `allowed` 数组。
- 不允许用「返回空列表」掩盖非法输入。

### REQ-LIST-03 响应结构

响应体固定为：

```json
{"items": [ ... ], "count": 12}
```

`count` 必须等于 `items` 的长度。

### REQ-LIST-04 任务字段

每个任务包含且仅包含：`id`、`title`、`status`、`tags`、`owner`、`due`。

### REQ-LIST-05 状态枚举

`status` 只有 `open`、`in_progress`、`done` 三种取值，出现在任务数据与过滤参数中。

## 3. 约束

- 本规格描述的行为是兼容性基线，任何后续改动不得破坏 REQ-LIST-01 ~ REQ-LIST-05。
- 测试文件 `tests/test_tasks_api.py` 是这些条目的可执行形式。

## 4. 验收

```bash
pytest tests/test_tasks_api.py -q
```

全部通过即视为满足本规格。
