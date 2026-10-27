"""Run the verification sample end to end and write one review record.

Sequence: reset → target tests must fail → index → build context → MiniMax
patch → target + regression tests must pass → restart check reads PowerContext
state from a new process.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "context"))

from sdd_context.config import Settings  # noqa: E402
from sdd_context.indexer import build_index  # noqa: E402
from sdd_context.maintenance import reset_sample  # noqa: E402
from sdd_context.pipeline import build_context, ingest, run_task, run_tests  # noqa: E402
from sdd_context.sample import SAMPLE_TASK, SAMPLE_TASK_ID  # noqa: E402
from sdd_context.store import SeekdbStore  # noqa: E402


def _target_nodes(business_root: Path) -> list[str]:
    bundle = build_index(business_root)
    return [test.test_id for test in bundle.tests if test.kind == "target"]


def _run_cli(arguments: list[str]) -> tuple[int, dict[str, object]]:
    command = [sys.executable, str(ROOT / "scripts" / "sdd.py"), *arguments]
    completed = subprocess.run(
        command,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"error": (completed.stdout + completed.stderr)[-800:]}
    return completed.returncode, payload


def _restart_check(task_id: str) -> dict[str, object]:
    """Read the saved state in a fresh process and use it in a fresh context."""

    status_code, status_payload = _run_cli(["status", "--task-id", task_id])
    build_code, build_payload = _run_cli(
        ["build", "--task-id", task_id, "--json"]
    )
    state = status_payload.get("powercontext_state") or {}
    context_state = build_payload.get("state") or {}
    record = {
        "commands": [
            "python scripts/sdd.py status --task-id " + task_id,
            "python scripts/sdd.py build --task-id " + task_id + " --json",
        ],
        "exit_codes": [status_code, build_code],
        "state_status": state.get("status") if isinstance(state, dict) else None,
        "verifications": len(state.get("verifications") or [])
        if isinstance(state, dict)
        else 0,
        "context_state_status": context_state.get("status")
        if isinstance(context_state, dict)
        else None,
        "context_state_verifications": len(context_state.get("verifications") or [])
        if isinstance(context_state, dict)
        else 0,
        "done": state.get("done") if isinstance(state, dict) else None,
    }
    record["ok"] = (
        status_code == 0
        and build_code == 0
        and record["state_status"] == "completed"
        and record["context_state_status"] == "completed"
        and record["verifications"] >= 2
    )
    return record


def main() -> int:
    settings = Settings.from_env()
    store = SeekdbStore(settings)
    store.ensure_schema()
    task_id = SAMPLE_TASK_ID
    steps: list[dict[str, object]] = []

    reset = reset_sample(settings, store, task_id=task_id, clear_state=True)
    steps.append({"step": "reset", "ok": True, **reset})

    before = run_tests(
        settings,
        _target_nodes(settings.business_root),
        label="target-before",
        expect_success=False,
    )
    steps.append({"step": "target-tests-before-change", **before})

    stats = ingest(settings, store)
    steps.append({"step": "index", "ok": True, **stats})

    context = build_context(settings, store, SAMPLE_TASK, task_id=task_id)
    steps.append(
        {
            "step": "context",
            "ok": True,
            "context_id": context["context_id"],
            "summary": context["summary"],
            "file": context["files"]["json"],
        }
    )

    record = run_task(settings, store, SAMPLE_TASK, task_id=task_id)
    steps.append(
        {
            "step": "minimax-change",
            "ok": record["outcome"] == "success",
            "run_id": record["run_id"],
            "model": record.get("model"),
            "changes": record.get("changes"),
            "record": record.get("record_file"),
            "tests": {
                key: {"exit_code": value["exit_code"], "log": value["log"]}
                for key, value in (record.get("tests") or {}).items()
            },
        }
    )

    combined = run_tests(settings, ["tests"], label="full-suite", expect_success=True)
    steps.append({"step": "full-test-suite", **combined})

    restart = _restart_check(task_id)
    steps.append({"step": "state-reuse-after-restart", **restart})

    ok = (
        record["outcome"] == "success"
        and before["ok"]
        and combined["ok"]
        and steps[-1]["ok"]
    )
    summary = {
        "at": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "outcome": "success" if ok else "failed",
        "steps": steps,
        "context_file": context["files"]["json"],
        "run_record": record.get("record_file"),
        "change_diff": str((settings.artifacts_dir / "change.diff").relative_to(settings.root)),
    }
    directory = settings.records_dir / "sample"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = directory / f"sample-{stamp}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({**summary, "record": str(path.relative_to(settings.root))}, ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
