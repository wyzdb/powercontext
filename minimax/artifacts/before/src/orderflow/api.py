"""HTTP surface for the orderflow demo service (standard library only)."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from orderflow.models import Order
from orderflow.repository import load_orders
from orderflow.service import DEFAULT_PAGE_SIZE, QueryError, list_orders


class ListQuery:
    """Validated query parameters for ``GET /orders``."""

    def __init__(
        self,
        *,
        status: str | None = None,
        min_total: str | None = None,
        page: str = "1",
        page_size: str = str(DEFAULT_PAGE_SIZE),
    ) -> None:
        self.status = status
        self.min_total = min_total
        self.page = page
        self.page_size = page_size

    def as_filters(self) -> dict[str, Any]:
        filters: dict[str, Any] = {"page": self.page, "page_size": self.page_size}
        if self.status is not None:
            filters["status"] = self.status
        if self.min_total is not None:
            filters["min_total"] = self.min_total
        return filters


def _single(query: Mapping[str, list[str]], name: str) -> str | None:
    values = query.get(name)
    if not values:
        return None
    if len(values) > 1:
        raise QueryError("invalid_query", f"duplicate query parameter: {name}")
    return values[0]


def parse_list_query(query: Mapping[str, list[str]]) -> ListQuery:
    """Turn the raw query string into the parameters the service accepts."""

    return ListQuery(
        status=_single(query, "status"),
        min_total=_single(query, "min_total"),
        page=_single(query, "page") or "1",
        page_size=_single(query, "page_size") or str(DEFAULT_PAGE_SIZE),
    )


class OrderHTTPServer(ThreadingHTTPServer):
    """``ThreadingHTTPServer`` that carries the order data set."""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], orders: tuple[Order, ...]) -> None:
        super().__init__(address, OrderRequestHandler)
        self.orders = orders


class OrderRequestHandler(BaseHTTPRequestHandler):
    """Read-only JSON API for the order list."""

    server_version = "orderflow/1.0"
    server: OrderHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health":
                self._json(200, {"status": "ok"})
                return
            if parsed.path == "/orders":
                query = parse_qs(parsed.query, keep_blank_values=True)
                page = list_orders(self.server.orders, **parse_list_query(query).as_filters())
                self._json(200, page.to_mapping())
                return
            self._error(404, "not_found", f"no route for {parsed.path}")
        except QueryError as exc:
            self._error(400, exc.code, exc.message)

    def _json(self, status: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"error": {"code": code, "message": message}})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Keep the demo quiet; request logging is the caller's concern."""


def make_server(
    host: str = "127.0.0.1",
    port: int = 0,
    orders: tuple[Order, ...] | None = None,
) -> OrderHTTPServer:
    """Create (but do not start) an order API server."""

    return OrderHTTPServer((host, port), orders if orders is not None else load_orders())


def serve(host: str, port: int) -> None:
    server = make_server(host, port)
    print(f"orderflow listening on http://{host}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the orderflow JSON API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
