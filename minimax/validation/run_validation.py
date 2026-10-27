from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sdd_context.context import ContextBuilder  # noqa: E402

TASK_ID = "expense-manager-threshold"
TASK = "Expense requests above 500 must require manager approval while existing validation behaviour stays unchanged."


def pytest(workspace: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(workspace)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_approvals.py", "-q", "-p", "no:cacheprovider"],
        cwd=workspace,
        text=True,
        capture_output=True,
        env=environment,
    )


def main() -> None:
    backend = sys.argv[1] if len(sys.argv) > 1 else None
    workspace = ROOT / "workspace"
    shutil.copyfile(ROOT / "workspace" / "before" / "approvals.py", workspace / "expense_approval" / "approvals.py")
    before = pytest(workspace)
    shutil.copyfile(ROOT / "workspace" / "after" / "approvals.py", workspace / "expense_approval" / "approvals.py")
    after = pytest(workspace)

    builder = ContextBuilder(ROOT, backend=backend)
    try:
        imported = builder.initialize()
        context = builder.build(TASK_ID, TASK)
        required = {
            "specs": {"SPEC-001", "SPEC-002"},
            "code": {"code:approvals"},
            "tests": {"test:test_approvals"},
        }
        present = {
            "specs": {item["id"] for item in context["specs"]},
            "code": {item["id"] for item in context["code"]},
            "tests": {item["id"] for item in context["tests"]},
        }
        assert all(required[key] <= present[key] for key in required), (required, present)
        sources_real = all(
            item["path"] and Path(ROOT / item["path"]).exists()
            for group in ("specs", "code", "tests")
            for item in context[group]
        )
        assert sources_real

        spec_path = ROOT / "data" / "specs" / "SPEC-001.md"
        original_spec = spec_path.read_text(encoding="utf-8")
        updated_spec = original_spec.replace("Version: 1", "Version: 2").replace("**500**", "**300**").replace(
            "exactly 500", "exactly 300"
        )
        spec_path.write_text(updated_spec, encoding="utf-8")
        try:
            builder.initialize()
            updated_context = builder.build(TASK_ID, TASK)
            spec = next(item for item in updated_context["specs"] if item["id"] == "SPEC-001")
            assert spec["version"] == 2 and "**300**" in spec["text"] and "**500**" not in spec["text"]
        finally:
            spec_path.write_text(original_spec, encoding="utf-8")
            builder.initialize()

        state = builder.save_state(
            TASK_ID,
            TASK,
            completed=["imported", "built context", "applied patch", "tests passed"],
            pending=[],
            validation=[
                {"phase": "before", "returncode": before.returncode, "tail": before.stdout[-300:]},
                {"phase": "after", "returncode": after.returncode, "tail": after.stdout[-300:]},
            ],
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
    finally:
        builder.close()

    restarted = ContextBuilder(ROOT, backend=backend)
    try:
        reloaded = restarted.state.load(TASK_ID)
        assert reloaded is not None and reloaded["completed"] == state["completed"]
        restarted_context = restarted.build(TASK_ID, TASK)
        assert restarted_context["state"]["task_id"] == TASK_ID
    finally:
        restarted.close()

    result = {
        "backend": context["sources"]["backend"],
        "store": context["sources"]["documents"],
        "imported": imported,
        "before_returncode": before.returncode,
        "after_returncode": after.returncode,
        "required": sorted(required["specs"] | required["code"] | required["tests"]),
        "state_reloaded": reloaded is not None,
        "updated_spec_version": 2,
    }
    (ROOT / "record" / "validation_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "record" / "pytest_before.log").write_text(before.stdout + before.stderr, encoding="utf-8")
    (ROOT / "record" / "pytest_after.log").write_text(after.stdout + after.stderr, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert before.returncode != 0, "target test must fail before the change"
    assert after.returncode == 0, "all tests must pass after the change"


if __name__ == "__main__":
    main()
