"""End-to-end task pipeline: context → MiniMax → patch → tests → records."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sdd_context.config import Settings
from sdd_context.context_builder import ContextBuilder, write_context_files
from sdd_context.indexer import build_index
from sdd_context.minimax_client import MiniMaxClient, MiniMaxError, extract_patch
from sdd_context.models import TaskState
from sdd_context.patcher import (
    PatchError,
    apply_patch,
    snapshot_sources,
    unified_diff,
)
from sdd_context.store import SeekdbStore, new_id

SYSTEM_PROMPT = """你是严格遵循 SDD（规格驱动开发）的资深 Python 工程师。
你只能依据用户给出的规格条目、现有代码和测试来修改实现。

硬性要求：
1. 只输出一个 unified diff（可放在 <<<PATCH ... PATCH>>> 标记内），不要解释、不要输出完整文件；
2. 不要修改测试文件，也不要新增测试；
3. 保持文件原有结构：模块 docstring 与 `from __future__ import annotations` 必须仍在文件最前面，新增 import 追加到已有 import 区块，不移动已有行；
4. 只做满足规格的最小改动，既有分页、排序与错误码行为必须保持不变。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest(settings: Settings, store: SeekdbStore) -> dict[str, Any]:
    """Parse the business project and replace the seekdb index."""

    store.ensure_schema()
    bundle = build_index(settings.business_root)
    stats = store.replace_index(bundle)
    record = {
        "at": _now(),
        "business_root": str(settings.business_root),
        "database": f"{settings.db_host}:{settings.db_port}/{settings.db_database}",
        **stats,
        "spec_ids": [spec.spec_id for spec in bundle.specs],
    }
    _append_jsonl(settings.records_dir / "seekdb" / "ingest.jsonl", record)
    return record


def build_context(
    settings: Settings,
    store: SeekdbStore,
    task_text: str,
    *,
    task_id: str | None = None,
    title: str | None = None,
    with_state: bool = True,
) -> dict[str, Any]:
    state = None
    if with_state and task_id:
        from sdd_context.powercontext_state import PowerContextState

        state = PowerContextState(settings).load(store, task_id)
    payload = ContextBuilder(store, settings).build(
        task_text, task_id=task_id, title=title, state=state
    )
    json_path, md_path = write_context_files(settings, payload)
    payload["files"] = {"json": str(json_path), "markdown": str(md_path)}
    return payload


def build_prompt(settings: Settings, context: dict[str, Any]) -> dict[str, str]:
    """Assemble the prompt from the context payload and real file contents."""

    required = [item for item in context["specs"] if item["role"] == "required"]
    constraints = [item for item in context["specs"] if item["role"] == "constraint"]
    targets = [item for item in context["code"] if item["role"] == "modify"]
    target_tests = [item for item in context["tests"] if item["kind"] == "target"]
    regression_tests = [item for item in context["tests"] if item["kind"] == "regression"]

    files: dict[str, str] = {}
    for entry in targets:
        files.setdefault(entry["path"], (settings.business_root / entry["path"]).read_text(encoding="utf-8"))
    for entry in target_tests:
        files.setdefault(entry["path"], (settings.business_root / entry["path"]).read_text(encoding="utf-8"))

    lines: list[str] = []
    lines.append("## 任务")
    lines.append(context["task"])
    lines.append("")
    lines.append("## 必须满足的规格条目")
    for item in required:
        lines.append(
            f"### {item['clause_id']} {item['heading']}"
            f"（{item['source']['path']}:{item['source']['line_start']}-{item['source']['line_end']}）"
        )
        lines.append(item["body"])
        lines.append("")
    if constraints:
        lines.append("## 不得破坏的既有约束")
        for item in constraints:
            lines.append(
                f"### {item['clause_id']} {item['heading']}"
                f"（{item['source']['path']}:{item['source']['line_start']}-{item['source']['line_end']}）"
            )
            lines.append(item["body"])
            lines.append("")
    lines.append("## 需要修改的符号")
    for item in targets:
        lines.append(
            f"- {item['symbol_id']}（{item['signature']}），"
            f"{item['source']['path']}:{item['source']['line_start']}-{item['source']['line_end']}"
        )
    lines.append("")
    lines.append("## 相关文件当前内容")
    for path, content in files.items():
        lines.append(f"### {path}")
        lines.append("```python")
        lines.append(content.rstrip("\n"))
        lines.append("```")
        lines.append("")
    lines.append("## 目标功能测试（修改后必须全部通过）")
    for item in target_tests:
        lines.append(f"- {item['test_id']}")
    lines.append("")
    lines.append("## 回归测试（修改后必须继续通过）")
    for item in regression_tests:
        lines.append(f"- {item['test_id']}")
    lines.append("")
    lines.append("## 输出格式")
    lines.append("只输出如下形式的 unified diff（行号以文件第 1 行为起点）：")
    lines.append("<<<PATCH")
    lines.append("--- a/<相对路径>")
    lines.append("+++ b/<相对路径>")
    lines.append("@@ -<旧起始行>,<旧行数> +<新起始行>,<新行数> @@")
    lines.append(" 上下文行")
    lines.append("-被删除的行")
    lines.append("+新增的行")
    lines.append("PATCH>>>")
    return {"system": SYSTEM_PROMPT, "user": "\n".join(lines)}


def run_tests(
    settings: Settings,
    node_ids: list[str],
    *,
    label: str,
    expect_success: bool,
) -> dict[str, Any]:
    """Run pytest for the given node ids and keep the full log."""

    command = [sys.executable, "-m", "pytest", *node_ids, "-q", "-p", "no:cacheprovider"]
    display = " ".join(["python", "-m", "pytest", *node_ids, "-q", "-p", "no:cacheprovider"])
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=settings.business_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    duration_ms = int((time.perf_counter() - started) * 1000)
    output = (completed.stdout or "") + (completed.stderr or "")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_dir = settings.records_dir / "tests"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{stamp}-{label}.log"
    log_path.write_text(
        "command: " + display + f"\nexit: {completed.returncode}\n\n" + output,
        encoding="utf-8",
    )
    result = {
        "label": label,
        "command": display,
        "cwd": str(settings.business_root),
        "exit_code": completed.returncode,
        "expected_success": expect_success,
        "ok": (completed.returncode == 0) == expect_success,
        "duration_ms": duration_ms,
        "log": str(log_path.relative_to(settings.root)),
        "tail": output.strip().splitlines()[-12:],
        "at": _now(),
    }
    return result


def validate_code_patch(patch_text: str, business_root: Path) -> None:
    """Reject changes to tests/specs, even if a model ignores the prompt."""
    changes = apply_patch(patch_text, business_root, dry_run=True)
    source_root = (business_root / "src").resolve()
    for change in changes:
        target = (business_root / change.path).resolve()
        if source_root not in target.parents or target.suffix != ".py":
            raise PatchError(f"model may modify only existing src/*.py code: {change.path}")


def run_task(
    settings: Settings,
    store: SeekdbStore,
    task_text: str,
    *,
    task_id: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Run one full SDD task: context, MiniMax patch, tests, state, records."""

    from sdd_context.powercontext_state import PowerContextState

    start = time.perf_counter()
    run_id = new_id("run")
    task_id = task_id or new_id("task")
    title = title or task_text.strip().splitlines()[0][:80]

    state = PowerContextState(settings).load(store, task_id) or TaskState(
        task_id=task_id, title=title, status="in_progress", step="context"
    )
    state.status = "in_progress"
    state.step = "context"
    state.todo = state.todo or ["生成上下文", "调用 MiniMax 修改代码", "运行目标测试与回归测试"]
    store.upsert_task(state, task_text)

    context = build_context(settings, store, task_text, task_id=task_id, title=title)
    state.context_id = context["context_id"]
    state.step = "prompt"
    store.add_event(task_id, "context", "built", context["summary"])

    prompt = build_prompt(settings, context)
    prompt_path = settings.records_dir / "minimax" / f"{run_id}.prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(
        f"# system\n{prompt['system']}\n\n# user\n{prompt['user']}", encoding="utf-8"
    )

    client = MiniMaxClient(settings)
    completion = client.complete(prompt["system"], prompt["user"], max_tokens=8192)
    response_path = settings.records_dir / "minimax" / f"{run_id}.response.txt"
    response_path.write_text(completion.text, encoding="utf-8")

    before_dir = settings.artifacts_dir / "before"
    if not before_dir.exists():
        snapshot_sources(settings.business_root, before_dir)
    try:
        patch_text = extract_patch(completion.text)
        validate_code_patch(patch_text, settings.business_root)
    except (MiniMaxError, PatchError) as exc:
        state.status = "failed"
        state.step = "patch"
        PowerContextState(settings).save(store, state)
        store.add_event(
            task_id, "patch", "failed", {"run_id": run_id, "error": f"{type(exc).__name__}: {exc}"}
        )
        failed = {
            "run_id": run_id,
            "task_id": task_id,
            "title": title,
            "task": task_text,
            "context_id": context["context_id"],
            "context_file": context["files"]["json"],
            "context_markdown": context["files"]["markdown"],
            "prompt_file": str(prompt_path.relative_to(settings.root)),
            "model": {
                "name": completion.model,
                "base_url": settings.minimax_base_url,
                "request_id": completion.request_id,
                "duration_ms": completion.duration_ms,
                "usage": completion.usage,
            },
            "request": {"system": prompt["system"], "user": prompt["user"]},
            "response": completion.to_record(),
            "response_file": str(response_path.relative_to(settings.root)),
            "patch": None,
            "changes": [],
            "tests": None,
            "state": state.to_mapping(),
            "outcome": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "finished_at": _now(),
        }
        failed_path = settings.records_dir / "minimax" / f"{run_id}.json"
        failed_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")
        failed["record_file"] = str(failed_path.relative_to(settings.root))
        return failed

    changes = apply_patch(patch_text, settings.business_root)
    state.step = "verify"

    target_tests = [item["test_id"] for item in context["tests"] if item["kind"] == "target"]
    regression_tests = [
        item["test_id"] for item in context["tests"] if item["kind"] == "regression"
    ]
    target_result = run_tests(settings, target_tests, label="target", expect_success=True)
    regression_result = run_tests(
        settings, regression_tests, label="regression", expect_success=True
    )

    ok = target_result["ok"] and regression_result["ok"]
    state.status = "completed" if ok else "failed"
    state.step = "done" if ok else "verify"
    state.done = [f"上下文 {context['context_id']}", f"补丁 {len(changes)} 个文件"]
    state.todo = [] if ok else ["根据失败日志修复实现"]
    state.verifications.append(
        {
            "run_id": run_id,
            "command": target_result["command"],
            "exit_code": target_result["exit_code"],
            "log": target_result["log"],
        }
    )
    state.verifications.append(
        {
            "run_id": run_id,
            "command": regression_result["command"],
            "exit_code": regression_result["exit_code"],
            "log": regression_result["log"],
        }
    )
    powercontext_record = PowerContextState(settings).save(store, state)
    store.upsert_task(state, task_text)
    store.add_event(
        task_id,
        "verify",
        "passed" if ok else "failed",
        {"target": target_result["exit_code"], "regression": regression_result["exit_code"]},
    )

    after_dir = settings.artifacts_dir / "after"
    snapshot_sources(settings.business_root, after_dir)
    diff_path = settings.artifacts_dir / "change.diff"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(
        unified_diff(before_dir, after_dir, [change.path for change in changes]),
        encoding="utf-8",
    )

    record = {
        "run_id": run_id,
        "task_id": task_id,
        "title": title,
        "task": task_text,
        "context_id": context["context_id"],
        "context_file": context["files"]["json"],
        "context_markdown": context["files"]["markdown"],
        "prompt_file": str(prompt_path.relative_to(settings.root)),
        "model": {
            "name": completion.model,
            "base_url": settings.minimax_base_url,
            "request_id": completion.request_id,
            "duration_ms": completion.duration_ms,
            "usage": completion.usage,
        },
        "request": {"system": prompt["system"], "user": prompt["user"]},
        "response": completion.to_record(),
        "patch": patch_text,
        "changes": [
            {
                "path": change.path,
                "added": change.added,
                "removed": change.removed,
                "before_sha": change.before_sha,
                "after_sha": change.after_sha,
            }
            for change in changes
        ],
        "tests": {"target": target_result, "regression": regression_result},
        "powercontext": powercontext_record,
        "state": state.to_mapping(),
        "outcome": "success" if ok else "failed",
        "duration_ms": int((time.perf_counter() - start) * 1000),
        "finished_at": _now(),
    }
    record_path = settings.records_dir / "minimax" / f"{run_id}.json"
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _append_jsonl(
        settings.records_dir / "minimax" / "runs.jsonl",
        {
            "run_id": run_id,
            "task_id": task_id,
            "outcome": record["outcome"],
            "context_id": context["context_id"],
            "model": completion.model,
            "request_id": completion.request_id,
            "tokens": completion.usage.get("total_tokens"),
            "duration_ms": record["duration_ms"],
            "finished_at": record["finished_at"],
        },
    )
    record["record_file"] = str(record_path.relative_to(settings.root))
    return record


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
