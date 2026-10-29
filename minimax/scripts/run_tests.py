#!/usr/bin/env python
"""跑测试并把「命令 / 退出码 / 代码版本 / 输出」落盘成可核对的日志。

用法::

    python scripts/run_tests.py --label baseline
    python scripts/run_tests.py --label after-fix -- -k tag

评审可以按 ``records/test-runs.jsonl`` 里的记录逐条复现。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo" / "taskboard"
RECORDS = ROOT / "records"
LOG_DIR = RECORDS / "test-logs"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="run")
    parser.add_argument("--repo", default=str(ROOT.parent), help="用于记录 commit 的仓库")
    parser.add_argument("extra", nargs="*", help="透传给 pytest 的参数")
    args = parser.parse_args(argv)

    pytest_args = [a for a in args.extra if a != "--"]
    command = [sys.executable, "-m", "pytest", "-q", *pytest_args]

    started = datetime.now().astimezone()
    result = subprocess.run(command, cwd=DEMO, capture_output=True, text=True)
    output = (result.stdout or "") + (result.stderr or "")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"{args.label}-{stamp}.log"
    log_path.write_text(
        f"# label: {args.label}\n"
        f"# time: {started.isoformat(timespec='seconds')}\n"
        f"# cwd: {DEMO}\n"
        f"# command: {' '.join(command)}\n"
        f"# exit: {result.returncode}\n\n{output}",
        encoding="utf-8",
    )

    summary = next((line for line in reversed(output.strip().splitlines()) if "passed" in line or "failed" in line), "")
    entry = {
        "ts": started.isoformat(timespec="seconds"),
        "label": args.label,
        "command": " ".join(["python", "-m", "pytest", "-q", *pytest_args]),
        "cwd": "minimax/demo/taskboard",
        "exit_code": result.returncode,
        "summary": summary.strip().strip("=").strip(),
        "commit": _git(Path(args.repo), "rev-parse", "HEAD"),
        "dirty": bool(_git(Path(args.repo), "status", "--porcelain")),
        "python": platform.python_version(),
        "test_files": {
            path.relative_to(DEMO).as_posix(): _sha256(path)
            for path in sorted((DEMO / "tests").glob("test_*.py"))
        },
        "log": log_path.relative_to(ROOT).as_posix(),
    }

    with (RECORDS / "test-runs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
