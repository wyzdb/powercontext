"""上下文模块命令行入口。

子命令::

    python -m ctx.cli import                      # 把规格/代码/测试导入 seekdb
    python -m ctx.cli build --task "..." [--out f]  # 生成任务上下文 JSON
    python -m ctx.cli stats                       # 看库里有什么
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import db, importer, patch, retrieve, state
from .config import DEMO_DIR


def _cmd_import(args: argparse.Namespace) -> int:
    summary = importer.import_all(Path(args.root))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    saved_state = None
    if args.task_id and not args.no_state:
        try:
            saved_state = state.load(args.task_id)
        except Exception as exc:  # Server 没起时不阻塞上下文生成
            print(f"[warn] 读取 PowerContext 状态失败（{type(exc).__name__}: {exc}），state 留空", file=sys.stderr)
    context = retrieve.build_context(
        args.task,
        root=Path(args.root),
        state=(saved_state or {}).get("state") if saved_state else None,
    )
    if saved_state:
        context["state_source"] = {
            "system": "PowerContext",
            "server": saved_state["server"],
            "scope_id": saved_state["scope_id"],
            "artifact": saved_state["artifact"],
            "revision": saved_state["revision"],
        }
    text = json.dumps(context, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"context written to {out}", file=sys.stderr)
        print(text)
    else:
        print(text)
    return 0


def _cmd_state_save(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.file).read_text(encoding="utf-8")) if args.file else {}
    result = state.save(args.task_id, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_state_load(args: argparse.Namespace) -> int:
    result = state.load(args.task_id)
    if result is None:
        print(json.dumps({"task_id": args.task_id, "found": False}, ensure_ascii=False, indent=2))
        return 4
    print(json.dumps({"task_id": args.task_id, "found": True, **result}, ensure_ascii=False, indent=2))
    return 0


def _cmd_patch(args: argparse.Namespace) -> int:
    context = patch.load_context(args.context)
    print(json.dumps(patch.summarize(context), ensure_ascii=False, indent=2), file=sys.stderr)

    if args.dry_run:
        messages = patch.build_messages(context)
        path, chars = patch.write_prompt(context, messages)
        print(json.dumps(
            {"dry_run": True, "prompt_path": str(path), "prompt_chars": chars, "messages": len(messages)},
            ensure_ascii=False,
            indent=2,
        ))
        return 0

    try:
        result = patch.generate(context, model=args.model, output_format=args.output_format)
    except Exception as exc:
        print(f"[patch] 生成失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    print(json.dumps(
        {
            "diff_path": str(result.path),
            "call_id": result.call_id,
            "latency_ms": result.latency_ms,
            "usage": result.usage,
            "diff_bytes": len(result.diff),
        },
        ensure_ascii=False,
        indent=2,
    ))

    if args.apply:
        import subprocess

        repo = DEMO_DIR.parent.parent  # powercontext/
        # Windows 下 git 默认 autocrlf=true，工作区是 CRLF、补丁是 LF，
        # 必须忽略行尾差异，否则 --check 会误报 "patch does not apply"。
        base = ["git", "-C", str(repo), "apply", "--ignore-whitespace"]
        target = ["--directory", "minimax/demo/taskboard", str(result.path)]

        check = subprocess.run(base + ["--check"] + target, capture_output=True, text=True)
        if check.returncode != 0:
            print(f"[patch] git apply --check 失败：{check.stderr.strip()}", file=sys.stderr)
            return 4
        applied = subprocess.run(base + target, capture_output=True, text=True)
        if applied.returncode != 0:
            print(f"[patch] 应用失败：{applied.stderr.strip()}", file=sys.stderr)
            return 4
        print(f"[patch] 已应用到 {DEMO_DIR}")
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT kind, COUNT(*) AS n FROM documents GROUP BY kind ORDER BY kind")
            rows = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS n FROM spec_refs")
            refs = cur.fetchone()["n"]
    finally:
        conn.close()

    print(json.dumps({"documents": rows, "spec_refs": refs}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctx", description="SDD 上下文模块")
    sub = parser.add_subparsers(dest="command", required=True)

    p_import = sub.add_parser("import", help="导入规格/代码/测试")
    p_import.add_argument("--root", default=str(DEMO_DIR))
    p_import.set_defaults(func=_cmd_import)

    p_build = sub.add_parser("build", help="按任务生成上下文")
    p_build.add_argument("--task", required=True)
    p_build.add_argument("--task-id", default=None, help="关联任务 ID（默认自动读取 PowerContext 状态）")
    p_build.add_argument("--no-state", action="store_true", help="不读取 PowerContext 状态")
    p_build.add_argument("--root", default=str(DEMO_DIR))
    p_build.add_argument("--out", default=None, help="同时写入文件")
    p_build.set_defaults(func=_cmd_build)

    p_state_save = sub.add_parser("state-save", help="把任务状态写入 PowerContext")
    p_state_save.add_argument("--task-id", required=True)
    p_state_save.add_argument("--file", default=None, help="状态 JSON 文件")
    p_state_save.set_defaults(func=_cmd_state_save)

    p_state_load = sub.add_parser("state-load", help="从 PowerContext 读取任务状态")
    p_state_load.add_argument("--task-id", required=True)
    p_state_load.set_defaults(func=_cmd_state_load)

    p_patch = sub.add_parser("patch", help="用 MiniMax 生成补丁")
    p_patch.add_argument("--context", required=True, help="ctx build 产出的上下文 JSON")
    p_patch.add_argument("--model", default=None)
    p_patch.add_argument("--output-format", choices=["files", "diff"], default="files",
                         help="files=模型给完整文件、本地算 diff（默认，最稳）；diff=模型直接给 unified diff")
    p_patch.add_argument("--apply", action="store_true", help="生成后直接 git apply")
    p_patch.add_argument("--dry-run", action="store_true", help="只生成提示词，不调用 MiniMax")
    p_patch.set_defaults(func=_cmd_patch)

    p_stats = sub.add_parser("stats", help="查看库内统计")
    p_stats.set_defaults(func=_cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
