"""Shared fixtures for the orderflow test suite."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

import pytest

from orderflow.api import make_server
from orderflow.models import Order

SAMPLE_ORDERS: tuple[dict[str, Any], ...] = (
    {
        "id": "ORD-2001",
        "customer": "aurora",
        "status": "paid",
        "total_cents": 5000,
        "created_at": "2026-09-10T08:00:00+08:00",
    },
    {
        "id": "ORD-2002",
        "customer": "beacon",
        "status": "paid",
        "total_cents": 7000,
        "created_at": "2026-09-15T00:00:00+08:00",
    },
    {
        "id": "ORD-2003",
        "customer": "cobalt",
        "status": "pending",
        "total_cents": 5000,
        "created_at": "2026-09-15T23:59:59+08:00",
    },
    {
        "id": "ORD-2004",
        "customer": "delta",
        "status": "shipped",
        "total_cents": 9000,
        "created_at": "2026-09-20T12:00:00+08:00",
    },
    {
        "id": "ORD-2005",
        "customer": "ember",
        "status": "cancelled",
        "total_cents": 1000,
        "created_at": "2026-09-01T09:30:00+08:00",
    },
    {
        "id": "ORD-2006",
        "customer": "fjord",
        "status": "paid",
        "total_cents": 3000,
        "created_at": "2026-09-14T23:59:59+08:00",
    },
)


@pytest.fixture
def sample_orders() -> tuple[Order, ...]:
    return tuple(Order.from_mapping(item) for item in SAMPLE_ORDERS)


@pytest.fixture
def api_base(sample_orders: tuple[Order, ...]) -> Iterator[str]:
    server = make_server(port=0, orders=sample_orders)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def get_json(url: str) -> tuple[int, dict[str, Any]]:
    """GET ``url`` and return ``(status, decoded_body)`` for both 2xx and 4xx."""

    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))
