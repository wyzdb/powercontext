"""Regression tests for the JSON HTTP contract."""

from __future__ import annotations

import pytest

from conftest import get_json


# spec: SPEC-API-001/R1
def test_orders_response_shape(api_base: str) -> None:
    status, body = get_json(f"{api_base}/orders?status=paid&page_size=2")
    assert status == 200
    assert body["total"] == 3
    assert body["pages"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert [item["id"] for item in body["items"]] == ["ORD-2002", "ORD-2001"]
    assert set(body["items"][0]) == {
        "id",
        "customer",
        "status",
        "total_cents",
        "created_at",
    }


# spec: SPEC-API-001/R2
def test_invalid_status_returns_400(api_base: str) -> None:
    status, body = get_json(f"{api_base}/orders?status=refunded")
    assert status == 400
    assert body["error"]["code"] == "invalid_status"


# spec: SPEC-API-001/R2
def test_invalid_page_returns_400(api_base: str) -> None:
    status, body = get_json(f"{api_base}/orders?page=0")
    assert status == 400
    assert body["error"]["code"] == "invalid_pagination"


# spec: SPEC-API-001/R2
def test_oversized_page_size_returns_400(api_base: str) -> None:
    status, body = get_json(f"{api_base}/orders?page_size=1000")
    assert status == 400
    assert body["error"]["code"] == "invalid_pagination"


# spec: SPEC-API-001/R3
def test_unknown_route_returns_404(api_base: str) -> None:
    status, body = get_json(f"{api_base}/refunds")
    assert status == 404
    assert body["error"]["code"] == "not_found"


# spec: SPEC-API-001/R4
def test_health_endpoint(api_base: str) -> None:
    status, body = get_json(f"{api_base}/health")
    assert status == 200
    assert body == {"status": "ok"}


@pytest.mark.parametrize("path", ["/orders?status=paid", "/orders?min_total=5000"])
def test_filters_are_query_parameters(api_base: str, path: str) -> None:
    status, body = get_json(f"{api_base}{path}")
    assert status == 200
    assert body["total"] >= 1
