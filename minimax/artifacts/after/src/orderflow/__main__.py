"""Print one page of orders as JSON, mirroring the HTTP API."""

from __future__ import annotations

import argparse
import json
import sys

from orderflow.repository import load_orders
from orderflow.service import DEFAULT_PAGE_SIZE, QueryError, list_orders


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List orders from the demo data set")
    parser.add_argument("--status")
    parser.add_argument("--min-total", type=int)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--data", help="path to a JSON order file")
    parser.add_argument("--indent", type=int, default=2)
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        page = list_orders(
            load_orders(args.data),
            status=args.status,
            min_total=args.min_total,
            page=args.page,
            page_size=args.page_size,
        )
    except QueryError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": exc.message}}, ensure_ascii=False))
        return 2

    print(json.dumps(page.to_mapping(), ensure_ascii=False, indent=args.indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
