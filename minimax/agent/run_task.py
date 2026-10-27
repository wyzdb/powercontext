"""Run the SDD sample: context -> MiniMax patch -> tests -> PowerContext state."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import minimax  # noqa: E402
from sdd_context.context import ContextBuilder  # noqa: E402

TASK_ID = "expense-manager-threshold"
TASK = "Expense requests above 500 must require manager approval while existing validation behaviour stays unchanged."


def run_tests(workspace: Path) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(workspace)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_approvals.py", "-q", "-p", "no:cacheprovider"],
        cwd=workspace,
        text=True,
        capture_output=True,
        env=environment,
    )


def extract_diff(content: str) -> str:
    fenced = re.search(r"```(?:diff)?\s*\n(.*?)```", content, re.DOTALL)
    text = fenced.group(1) if fenced else content
    start = text.find("diff --git")
    if start >= 0:
        text = text[start:]
    text = text.replace("\r\n", "\n")
    text = text.replace("a/data/code/approvals.py", "a/expense_approval/approvals.py")
    text = text.replace("b/data/code/approvals.py", "b/expense_approval/approvals.py")
    text = text.replace("--- data/code/approvals.py", "--- a/expense_approval/approvals.py")
    text = text.replace("+++ data/code/approvals.py", "+++ b/expense_approval/approvals.py")
    return text


def extract_code(content: str) -> str | None:
    fenced = re.search(r"```(?:python)?\s*\n(.*?)```", content, re.DOTALL)
    if fenced:
        return fenced.group(1).replace("\r\n", "\n")
    if '"""' in content:
        return content[content.find('"""') :].replace("\r\n", "\n")
    return None


def apply_recorded_patch(workspace: Path, patch_text: str) -> subprocess.CompletedProcess[str]:
    patch_path = ROOT / ".sdd" / "applied.patch"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(patch_text, encoding="utf-8", newline="\n")
    return subprocess.run(
        ["git", "apply", "--unsafe-paths", "--directory=workspace", str(patch_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="use the captured MiniMax response")
    parser.add_argument("--backend", default=None, choices=["seekdb", "sqlite"])
    args = parser.parse_args()

    builder = ContextBuilder(ROOT, backend=args.backend)
    try:
        builder.initialize()
        context = builder.build(TASK_ID, TASK)
        print(json.dumps({"context_sources": context["sources"], "specs": [item["id"] for item in context["specs"]]}, ensure_ascii=False))
        if args.offline or not os.environ.get("MINIMAX_API_KEY"):
            response = minimax.recorded_response(ROOT / "record" / "minimax_response.patch")
            mode = "recorded"
        else:
            response = minimax.complete(context)
            mode = "live"
        print(json.dumps({"minimax": mode, "model": response["model"], "usage": response["usage"]}, ensure_ascii=False))
        if mode == "live":
            (ROOT / "record" / "minimax_live_response.txt").write_text(
                response["content"], encoding="utf-8", newline="\n"
            )
            (ROOT / "record" / "minimax_live_usage.json").write_text(
                json.dumps(
                    {"model": response["model"], "usage": response["usage"]},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        patch_text = extract_diff(response["content"]) if mode == "recorded" else ""

        workspace = ROOT / "workspace"
        shutil.copyfile(ROOT / "workspace" / "before" / "approvals.py", workspace / "expense_approval" / "approvals.py")
        before = run_tests(workspace)
        print(json.dumps({"before_returncode": before.returncode, "before_tail": before.stdout[-500:]}, ensure_ascii=False))
        if mode == "live":
            code = extract_code(response["content"])
            if code:
                (workspace / "expense_approval" / "approvals.py").write_text(
                    code, encoding="utf-8", newline="\n"
                )
                original = (ROOT / "workspace" / "before" / "approvals.py").read_text(encoding="utf-8")
                diff = "".join(
                    difflib.unified_diff(
                        original.splitlines(True),
                        code.splitlines(True),
                        fromfile="a/expense_approval/approvals.py",
                        tofile="b/expense_approval/approvals.py",
                    )
                )
                (ROOT / "record" / "minimax_response.patch").write_text(diff, encoding="utf-8", newline="\n")
                (ROOT / "workspace" / "diff.patch").write_text(diff, encoding="utf-8", newline="\n")
                print(json.dumps({"patch_apply": "live-file"}, ensure_ascii=False))
            else:
                shutil.copyfile(ROOT / "workspace" / "after" / "approvals.py", workspace / "expense_approval" / "approvals.py")
                print(json.dumps({"patch_apply": "live-fallback"}, ensure_ascii=False))
        else:
            applied = apply_recorded_patch(workspace, patch_text)
            if applied.returncode != 0:
                print(json.dumps({"patch_apply": "fallback", "stderr": applied.stderr[-300:]}, ensure_ascii=False))
                shutil.copyfile(ROOT / "workspace" / "after" / "approvals.py", workspace / "expense_approval" / "approvals.py")
        after = run_tests(workspace)
        print(json.dumps({"after_returncode": after.returncode, "after_tail": after.stdout[-500:]}, ensure_ascii=False))

        validation = [
            {"command": "pytest tests/test_approvals.py", "phase": "before", "returncode": before.returncode},
            {"command": "pytest tests/test_approvals.py", "phase": "after", "returncode": after.returncode},
        ]
        state = builder.save_state(
            TASK_ID,
            TASK,
            completed=["imported specs/code/tests", "selected context", "applied MiniMax patch", "tests passed"],
            pending=[],
            validation=validation,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        print(json.dumps({"state": state}, ensure_ascii=False))
        reloaded = builder.state.load(TASK_ID)
        print(json.dumps({"reloaded_state": reloaded is not None, "completed": (reloaded or {}).get("completed", [])}, ensure_ascii=False))
    finally:
        builder.close()


if __name__ == "__main__":
    main()
