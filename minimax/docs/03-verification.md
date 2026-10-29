# 验证样例：TASK-001 任务列表按标签筛选

## 1. 任务

**要改什么**：`GET /api/tasks` 增加 `tag` 查询参数，按标签筛选任务（大小写不敏感、完整标签匹配、可与 `status` 组合、空值与未知标签有明确行为）。

**为什么改**：看板任务到两位数后，前端拿全量再自己过滤，移动端首屏变慢；标签筛选是最高频诉求。

**哪些原有行为必须保持**：SPEC-001 的全部条目——返回全部任务且按 `id` 升序、`status` 过滤、非法状态返回 400、响应结构 `{items, count}`、任务六字段。

规格原文：[SPEC-002](../demo/taskboard/specs/SPEC-002-tag-filter.md)、[SPEC-001](../demo/taskboard/specs/SPEC-001-task-list-baseline.md)。

## 2. 上下文中必须出现的来源

评审核对时按这张表逐条打开文件即可。

| 类型 | 来源 | 必须包含的内容 |
| --- | --- | --- |
| 规格 | `specs/SPEC-002-tag-filter.md` | REQ-TAG-01 ~ REQ-TAG-06 |
| 规格（约束） | `specs/SPEC-001-task-list-baseline.md` | REQ-LIST-01 ~ REQ-LIST-05 |
| 代码 | `taskboard/app.py` | 符号 `list_tasks`（L18–L38） |
| 代码 | `taskboard/store.py` | 符号 `filter_tasks`（L104–L119），`all_tasks`（L98–L101） |
| 目标测试 | `tests/test_tag_filter.py` | 7 个用例：`test_filter_by_tag`、`test_tag_match_is_case_insensitive`、`test_tag_requires_exact_token`、`test_unknown_tag_returns_empty_list`、`test_empty_tag_is_treated_as_absent`、`test_tag_combined_with_status`、`test_tag_filter_keeps_response_shape` |
| 回归测试 | `tests/test_tasks_api.py` | 8 个用例：health、排序、字段、status 过滤、非法状态、count 一致性、未知参数 |

对应产物：`records/context-TASK-001.json`。

## 3. 初始数据

样例工程自带 10 条任务（`demo/taskboard/taskboard/store.py`）：

| 状态 | 数量 | id |
| --- | --- | --- |
| open | 5 | 1, 4, 5, 8, 10 |
| in_progress | 2 | 2, 6 |
| done | 3 | 3, 7, 9 |

标签分布：`backend` → 1/2/7/10；`urgent` → 1/6/9；`frontend` → 3/4；`data` → 5/6；`ops` → 8/9。

seekdb 初始为空库；执行一次 `ctx.cli import` 后应得到 **9 篇文档**（2 规格 + 4 代码 + 3 测试）与 **7 条引用**。

## 4. 操作步骤

```powershell
cd minimax
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 1) 初始化数据库（需要先起 seekdb，见 README 第 4 节）
.\.venv\Scripts\python.exe -m ctx.cli import

# 2) 生成上下文
.\.venv\Scripts\python.exe -m ctx.cli build --task "为任务列表增加按标签筛选" --out records\context-TASK-001.json

# 3) 改前测试（预期红灯）
.\.venv\Scripts\python.exe scripts\run_tests.py --label baseline

# 4) 用 MiniMax 生成补丁并应用
.\.venv\Scripts\python.exe -m ctx.cli patch --context records\context-TASK-001.json --apply

# 5) 改后测试（预期全绿）
.\.venv\Scripts\python.exe scripts\run_tests.py --label after-fix

# 6) 保存状态 + 重启后读取（另开终端先启动 PowerContext Server）
.\.venv\Scripts\python.exe -m ctx.cli state-save --task-id TASK-001 --file records\state-TASK-001.json
.\.venv\Scripts\python.exe -m ctx.cli state-load --task-id TASK-001
```

## 5. 预期结果

### 5.1 上下文（第 2 步）

```json
{
  "retrieval": {"primary_spec": "SPEC-002", "constraints": ["SPEC-001"]},
  "specs": [
    {"key": "SPEC-002", "role": "primary", "requirements": ["REQ-TAG-01", "...", "REQ-TAG-06"]},
    {"key": "SPEC-001", "role": "constraint", "requirements": ["REQ-LIST-01", "...", "REQ-LIST-05"]}
  ],
  "code": [
    {"path": "taskboard/app.py", "symbols": [{"name": "list_tasks", "line": 18, "end_line": 38}]},
    {"path": "taskboard/store.py", "symbols": [{"name": "filter_tasks", "line": 104}, {"name": "all_tasks", "line": 98}]}
  ],
  "tests": [
    {"path": "tests/test_tag_filter.py", "role": "target"},
    {"path": "tests/test_tasks_api.py", "role": "regression"}
  ]
}
```

### 5.2 测试

| 阶段 | 目标测试 | 回归测试 | 记录 |
| --- | --- | --- | --- |
| 改前 | 7 failed | 8 passed | `records/test-runs.jsonl`，label=`baseline` |
| 改后 | 7 passed | 8 passed | `records/test-runs.jsonl`，label=`after-fix`（exit 0） |

改后使用的补丁由 MiniMax 生成：`records/patches/TASK-001-20261029-120132.diff`，
应用后 `taskboard/app.py` 读取 `tag` 参数并透传，`taskboard/store.py` 用 `casefold()` 做大小写不敏感的完整标签匹配。
测试文件在改前改后哈希一致（见 `test-runs.jsonl` 的 `test_files` 字段），未被改动。

### 5.3 状态复用

`state-save` 后重启 PowerContext Server，再 `state-load`，应返回同一个 `artifact` 与 `revision`，`state.done/todo/verifications` 与写入时一致。

## 6. 重置方法

```powershell
# 代码回到改前
git checkout -- minimax/demo/taskboard

# 数据库清空重导
python -c "import pymysql; c=pymysql.connect(host='127.0.0.1',port=2881,user='root'); c.cursor().execute('DROP DATABASE IF EXISTS mmx_ctx'); c.commit()"
.\.venv\Scripts\python.exe -m ctx.cli import

# 状态与记录（可选）
Remove-Item -Recurse -Force state, records\patches, records\test-logs
```
