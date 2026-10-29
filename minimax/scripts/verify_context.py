#!/usr/bin/env python
"""验收脚本：检查上下文是否包含样例规定的规格、代码、测试来源。

评审可直接运行::

    python scripts/verify_context.py

退出码 0 = 全部命中；1 = 有缺失（会列出缺失项）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ctx import retrieve, state as state_module  # noqa: E402

TASK = "为任务列表增加按标签筛选"
TASK_ID = "TASK-001"

EXPECTED_SPECS = {
    "SPEC-002": {"REQ-TAG-01", "REQ-TAG-02", "REQ-TAG-03", "REQ-TAG-04", "REQ-TAG-05"},
    "SPEC-001": {"REQ-LIST-01", "REQ-LIST-02", "REQ-LIST-03"},
}
EXPECTED_CODE = {
    "taskboard/app.py": {"list_tasks"},
    "taskboard/store.py": {"filter_tasks"},
}
EXPECTED_TESTS = {
    "tests/test_tag_filter.py": "target",
    "tests/test_tasks_api.py": "regression",
}


def main() -> int:
    saved = None
    try:
        saved = state_module.load(TASK_ID)
    except Exception as exc:  # PowerContext 未启动时不阻塞上下文检查
        print(f"[warn] 读取 PowerContext 状态失败：{type(exc).__name__}: {exc}", file=sys.stderr)

    context = retrieve.build_context(TASK, state=(saved or {}).get("state"))
    problems: list[str] = []

    specs = {spec["key"]: spec for spec in context["specs"]}
    for key, required in EXPECTED_SPECS.items():
        if key not in specs:
            problems.append(f"缺少规格 {key}")
            continue
        have = {req["id"] for req in specs[key]["requirements"]}
        missing = required - have
        if missing:
            problems.append(f"{key} 缺少需求条目 {sorted(missing)}")

    if specs.get("SPEC-002", {}).get("role") != "primary":
        problems.append("SPEC-002 应为 primary 规格")

    code = {item["path"]: item for item in context["code"]}
    for path, symbols in EXPECTED_CODE.items():
        if path not in code:
            problems.append(f"缺少代码 {path}")
            continue
        have = {symbol["name"] for symbol in code[path]["symbols"]}
        missing = symbols - have
        if missing:
            problems.append(f"{path} 缺少符号 {sorted(missing)}")

    tests = {item["path"]: item["role"] for item in context["tests"]}
    for path, role in EXPECTED_TESTS.items():
        if path not in tests:
            problems.append(f"缺少测试 {path}")
        elif tests[path] != role:
            problems.append(f"{path} 的角色是 {tests[path]}，应为 {role}")

    state = context.get("state") or {}
    if saved is None:
        print("[warn] 未取到 PowerContext 状态，state 字段为空（只影响 已完成/待办 展示）", file=sys.stderr)
    else:
        if not state.get("done"):
            problems.append("state.done 为空")
        if not state.get("todo"):
            problems.append("state.todo 为空")

    print(json.dumps(
        {
            "task": TASK,
            "specs": {key: len(spec.get("requirements", [])) for key, spec in specs.items()},
            "code": {path: [s["name"] for s in item["symbols"]] for path, item in code.items()},
            "tests": tests,
            "state": {k: len(v) if isinstance(v, list) else v for k, v in state.items()},
            "primary_spec": context["retrieval"]["primary_spec"],
        },
        ensure_ascii=False,
        indent=2,
    ))

    if problems:
        print("\n[FAIL] 上下文缺少必要来源：", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("\n[OK] 上下文包含样例规定的全部规格、代码符号与测试来源。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
