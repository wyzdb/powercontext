"""Command line entry point for the SDD context module.

Every subcommand is a thin adapter: configuration comes from the environment,
business logic lives in the modules next to this file, and the printed JSON is
the same payload that is persisted for review.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from sdd_context.config import Settings
from sdd_context.context_builder import render_markdown
from sdd_context.maintenance import capture_baseline, reset_sample
from sdd_context.pipeline import build_context, ingest, run_task
from sdd_context.powercontext_state import PowerContextState
from sdd_context.sample import SAMPLE_TASK, SAMPLE_TASK_ID
from sdd_context.store import SeekdbStore


def _settings() -> Settings:
    return Settings.from_env()


def _print_json(payload: Any) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _store(settings: Settings) -> SeekdbStore:
    store = SeekdbStore(settings)
    store.ensure_schema()
    return store


def cmd_db_init(args: argparse.Namespace) -> int:
    settings = _settings()
    store = SeekdbStore(settings)
    if args.reset:
        store.reset()
        result = {"reset": True, "database": settings.db_database}
    else:
        store.ensure_schema()
        result = {"reset": False, "database": settings.db_database}
    _print_json(result)
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    settings = _settings()
    store = _store(settings)
    _print_json(ingest(settings, store))
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    settings = _settings()
    store = _store(settings)
    payload = build_context(
        settings,
        store,
        args.task or SAMPLE_TASK,
        task_id=args.task_id,
        title=args.title,
    )
    if args.json:
        _print_json(payload)
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(render_markdown(payload))
        print(f"context: {payload['files']['json']}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    settings = _settings()
    store = _store(settings)
    record = run_task(
        settings,
        store,
        args.task or SAMPLE_TASK,
        task_id=args.task_id,
        title=args.title,
    )
    if record["outcome"] != "success":
        _print_json(
            {
                "run_id": record["run_id"],
                "task_id": record["task_id"],
                "outcome": record["outcome"],
                "error": record.get("error"),
                "model": record.get("model"),
                "record": record.get("record_file"),
            }
        )
        return 1
    _print_json(
        {
            "run_id": record["run_id"],
            "task_id": record["task_id"],
            "outcome": record["outcome"],
            "model": record["model"],
            "changes": record["changes"],
            "tests": {
                "target": {
                    "exit_code": record["tests"]["target"]["exit_code"],
                    "log": record["tests"]["target"]["log"],
                },
                "regression": {
                    "exit_code": record["tests"]["regression"]["exit_code"],
                    "log": record["tests"]["regression"]["log"],
                },
            },
            "powercontext": record["powercontext"],
            "record": record.get("record_file"),
        }
    )
    return 0 if record["outcome"] == "success" else 1


def cmd_status(args: argparse.Namespace) -> int:
    settings = _settings()
    store = _store(settings)
    if args.task_id:
        row = store.get_task(args.task_id)
        events = store.task_events(args.task_id)
        state = PowerContextState(settings).load(store, args.task_id)
        _print_json(
            {
                "task": row,
                "events": [
                    {**event, "detail": json.loads(event["detail"])} for event in events
                ],
                "powercontext_state": state.to_mapping() if state else None,
            }
        )
    else:
        _print_json({"tasks": store.list_tasks(limit=args.limit)})
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    settings = _settings()
    store = _store(settings)
    _print_json(
        reset_sample(
            settings,
            store,
            task_id=args.task_id,
            clear_state=args.clear_state,
            restore_code=not args.keep_code,
        )
    )
    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    settings = _settings()
    _print_json(capture_baseline(settings))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    settings = _settings()
    checks: dict[str, Any] = {}
    try:
        store = SeekdbStore(settings)
        store.ensure_schema()
        checks["seekdb"] = {
            "ok": True,
            "endpoint": f"{settings.db_host}:{settings.db_port}/{settings.db_database}",
            "tables": len(store.list_tasks(limit=1)) >= 0,
        }
    except Exception as exc:  # noqa: BLE001 - doctor reports, never raises
        checks["seekdb"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        checks["powercontext"] = {
            "ok": True,
            "url": settings.powercontext_url,
            "liveness": PowerContextState(settings).health(),
        }
    except Exception as exc:  # noqa: BLE001
        checks["powercontext"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    checks["minimax"] = {
        "ok": bool(settings.minimax_api_key),
        "base_url": settings.minimax_base_url,
        "model": settings.minimax_model,
    }
    checks["business_root"] = str(settings.business_root)
    _print_json(checks)
    return 0 if all(item.get("ok") for item in checks.values() if isinstance(item, dict) and "ok" in item) else 1


def cmd_spec_demo(args: argparse.Namespace) -> int:
    settings = _settings()
    store = _store(settings)
    target = settings.spec_dir / "SPEC-ORD-004-created-after.md"
    update = settings.spec_dir / "updates" / "SPEC-ORD-004-v2.md"
    backup_dir = settings.spec_dir / "updates" / ".backup"
    backup = backup_dir / target.name

    if args.action == "apply":
        if not update.is_file():
            raise SystemExit(f"missing spec update: {update}")
        backup_dir.mkdir(parents=True, exist_ok=True)
        if not backup.is_file():
            backup.write_bytes(target.read_bytes())
        target.write_bytes(update.read_bytes())
        stats = ingest(settings, store)
        payload = build_context(settings, store, SAMPLE_TASK, task_id=args.task_id)
        clauses = [
            item for item in payload["specs"] if item["clause_id"].startswith("SPEC-ORD-004/")
        ]
        _print_json(
            {
                "action": "apply",
                "ingest": stats,
                "spec_version": clauses[0]["version"] if clauses else None,
                "clauses": [
                    {"clause_id": item["clause_id"], "version": item["version"], "body": item["body"]}
                    for item in clauses
                ],
                "context": payload["files"]["json"],
            }
        )
        return 0
    if args.action == "restore":
        if not backup.is_file():
            raise SystemExit(f"missing spec backup: {backup}")
        target.write_bytes(backup.read_bytes())
        stats = ingest(settings, store)
        _print_json({"action": "restore", "ingest": stats, "restored": target.name})
        return 0
    raise SystemExit(f"unknown action: {args.action}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdd-context",
        description="SDD 上下文模块：从 seekdb 选择规格/代码/测试，驱动 MiniMax 完成代码修改",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    db_init = sub.add_parser("db-init", help="create (or reset) the seekdb schema")
    db_init.add_argument("--reset", action="store_true")
    db_init.set_defaults(func=cmd_db_init)

    ingest_cmd = sub.add_parser("ingest", help="index specs, code symbols and tests into seekdb")
    ingest_cmd.set_defaults(func=cmd_ingest)

    build_cmd = sub.add_parser("build", help="build the context payload for a task")
    build_cmd.add_argument("--task", help="task description (defaults to the sample task)")
    build_cmd.add_argument("--task-id", help="task id used to load saved state")
    build_cmd.add_argument("--title")
    build_cmd.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    build_cmd.set_defaults(func=cmd_build)

    run_cmd = sub.add_parser("run", help="run context → MiniMax → patch → tests → state")
    run_cmd.add_argument("--task", help="task description (defaults to the sample task)")
    run_cmd.add_argument("--task-id", default=SAMPLE_TASK_ID)
    run_cmd.add_argument("--title")
    run_cmd.set_defaults(func=cmd_run)

    status_cmd = sub.add_parser("status", help="show saved task state and verification results")
    status_cmd.add_argument("--task-id")
    status_cmd.add_argument("--limit", type=int, default=20)
    status_cmd.set_defaults(func=cmd_status)

    reset_cmd = sub.add_parser("reset-sample", help="restore the pristine sources and clear task rows")
    reset_cmd.add_argument("--task-id", default=SAMPLE_TASK_ID)
    reset_cmd.add_argument("--clear-state", action="store_true")
    reset_cmd.add_argument("--keep-code", action="store_true")
    reset_cmd.set_defaults(func=cmd_reset)

    baseline_cmd = sub.add_parser("baseline", help="snapshot the pristine sources under artifacts/before")
    baseline_cmd.set_defaults(func=cmd_baseline)

    doctor_cmd = sub.add_parser("doctor", help="check seekdb, PowerContext and MiniMax configuration")
    doctor_cmd.set_defaults(func=cmd_doctor)

    spec_cmd = sub.add_parser("spec-demo", help="apply or restore the updated specification")
    spec_cmd.add_argument("action", choices=["apply", "restore"])
    spec_cmd.add_argument("--task-id", default=SAMPLE_TASK_ID)
    spec_cmd.set_defaults(func=cmd_spec_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
