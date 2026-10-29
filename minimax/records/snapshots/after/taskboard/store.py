"""任务数据与查询。

数据是写死的种子数据：样例工程要能在任何机器上零配置跑起来，
评审只需要 ``pip install -r requirements.txt`` 和 ``pytest``。
"""

from __future__ import annotations

from typing import Iterable

#: 合法状态集合，顺序即文档中的枚举顺序
STATUSES: tuple[str, ...] = ("open", "in_progress", "done")

TASKS: list[dict] = [
    {
        "id": 1,
        "title": "修复登录接口 500 错误",
        "status": "open",
        "tags": ["backend", "urgent"],
        "owner": "alice",
        "due": "2026-11-02",
    },
    {
        "id": 2,
        "title": "为任务列表增加分页",
        "status": "in_progress",
        "tags": ["backend"],
        "owner": "bob",
        "due": "2026-11-05",
    },
    {
        "id": 3,
        "title": "登录页样式调整",
        "status": "done",
        "tags": ["frontend"],
        "owner": "carol",
        "due": "2026-10-20",
    },
    {
        "id": 4,
        "title": "键盘导航支持",
        "status": "open",
        "tags": ["frontend", "a11y"],
        "owner": "carol",
        "due": "2026-11-10",
    },
    {
        "id": 5,
        "title": "导出 CSV 报表",
        "status": "open",
        "tags": ["data"],
        "owner": "dave",
        "due": "2026-11-12",
    },
    {
        "id": 6,
        "title": "修复统计口径偏差",
        "status": "in_progress",
        "tags": ["data", "urgent"],
        "owner": "dave",
        "due": "2026-10-30",
    },
    {
        "id": 7,
        "title": "接口错误码统一",
        "status": "done",
        "tags": ["backend"],
        "owner": "alice",
        "due": "2026-10-18",
    },
    {
        "id": 8,
        "title": "部署流水线缓存",
        "status": "open",
        "tags": ["ops"],
        "owner": "erin",
        "due": "2026-11-15",
    },
    {
        "id": 9,
        "title": "回滚夜间构建",
        "status": "done",
        "tags": ["ops", "urgent"],
        "owner": "erin",
        "due": "2026-10-22",
    },
    {
        "id": 10,
        "title": "补充审计日志",
        "status": "open",
        "tags": ["backend"],
        "owner": "alice",
        "due": "2026-11-08",
    },
]


def all_tasks() -> list[dict]:
    """按 id 升序返回全部任务。"""

    return sorted(TASKS, key=lambda task: task["id"])


def filter_tasks(
    tasks: Iterable[dict],
    *,
    status: str | None = None,
    tag: str | None = None,
) -> list[dict]:
    """按状态和标签过滤任务。标签匹配不区分大小写，但必须完整匹配。"""

    result = list(tasks)
    if status is not None:
        result = [task for task in result if task["status"] == status]
    if tag:
        normalized_tag = tag.casefold()
        result = [
            task
            for task in result
            if any(label.casefold() == normalized_tag for label in task["tags"])
        ]
    return result
