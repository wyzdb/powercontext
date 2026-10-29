"""命令行入口：本地起服务，或直接打印任务列表。"""

from __future__ import annotations

import argparse

from .app import create_app
from .store import all_tasks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="taskboard")
    parser.add_argument("command", choices=["serve", "list"], nargs="?", default="list")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    if args.command == "serve":
        create_app().run(host=args.host, port=args.port)
        return 0

    for task in all_tasks():
        print(f'{task["id"]:>2}  {task["status"]:<12} {task["title"]}  {task["tags"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
