from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .context import ContextBuilder


def _root(value: str) -> Path:
    return Path(value).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(prog="sdd-context", description="SDD engineering context module")
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="import specs, code and tests")
    init.add_argument("--backend", default=None, choices=["seekdb", "sqlite"])

    context = sub.add_parser("context", help="build context for a task")
    context.add_argument("--task-id", required=True)
    context.add_argument("--task", required=True)
    context.add_argument("--backend", default=None, choices=["seekdb", "sqlite"])

    state = sub.add_parser("state", help="save task state")
    state.add_argument("--task-id", required=True)
    state.add_argument("--task", required=True)
    state.add_argument("--completed", nargs="*", default=[])
    state.add_argument("--pending", nargs="*", default=[])
    state.add_argument("--validation", default="[]", help="JSON list of validation records")
    state.add_argument("--backend", default=None, choices=["seekdb", "sqlite"])

    status = sub.add_parser("status", help="read task state after a restart")
    status.add_argument("--task-id", required=True)
    status.add_argument("--backend", default=None, choices=["seekdb", "sqlite"])

    update = sub.add_parser("update-spec", help="import a new specification revision")
    update.add_argument("--threshold", required=True, type=float)
    update.add_argument("--backend", default=None, choices=["seekdb", "sqlite"])

    args = parser.parse_args()
    root = _root(args.root)
    builder = ContextBuilder(root, backend=getattr(args, "backend", None))
    try:
        if args.command == "init":
            _print(builder.initialize())
        elif args.command == "context":
            _print(builder.build(args.task_id, args.task))
        elif args.command == "state":
            validation = json.loads(args.validation)
            _print(
                builder.save_state(
                    args.task_id,
                    args.task,
                    completed=args.completed,
                    pending=args.pending,
                    validation=validation,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        elif args.command == "status":
            _print(builder.state.load(args.task_id))
        elif args.command == "update-spec":
            path = root / "data" / "specs" / "SPEC-001.md"
            text = path.read_text(encoding="utf-8")
            text = re.sub(r"(-\s*Version:\s*)\d+", r"\g<1>2", text)
            text = re.sub(r"at or below \*\*\d+(?:\.\d+)?\*\*", f"at or below **{args.threshold:g}**", text)
            text = re.sub(r"above \*\*\d+(?:\.\d+)?\*\*", f"above **{args.threshold:g}**", text)
            text = re.sub(r"exactly \d+(?:\.\d+)? is", f"exactly {args.threshold:g} is", text)
            path.write_text(text, encoding="utf-8")
            _print(builder.initialize())
    finally:
        builder.close()


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
