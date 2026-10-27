"""Target acceptance tests for SPEC-ORD-004 (created_after filter).

These tests describe the requested behaviour, so they fail against the
unmodified service and pass once the change is applied.
"""

from __future__ import annotations

from conftest import get_json


# spec: SPEC-ORD-004/R1
def test_created_after_filters_orders(api_base: str) -> None:
    status, body = get_json(f"{api_base}/orders?created_after=2026-09-15&page_size=10")
    assert status == 200
    assert [item["id"] for item in body["items"]] == [
        "ORD-2004",
        "ORD-2002",
        "ORD-2003",
    ]
    assert body["total"] == 3


# spec: SPEC-ORD-004/R2
def test_created_after_includes_the_boundary_day(api_base: str) -> None:
    _, body = get_json(f"{api_base}/orders?created_after=2026-09-15&page_size=10")
    ids = [item["id"] for item in body["items"]]
    assert "ORD-2002" in ids, "an order at 00:00:00 on the boundary day must be included"
    assert "ORD-2003" in ids, "an order at 23:59:59 on the boundary day must be included"
    assert "ORD-2006" not in ids, "the day before the boundary must stay excluded"


# spec: SPEC-ORD-004/R3, SPEC-API-001/R2
def test_invalid_created_after_returns_400(api_base: str) -> None:
    status, body = get_json(f"{api_base}/orders?created_after=2026-13-01")
    assert status == 400
    assert body["error"]["code"] == "invalid_created_after"


# spec: SPEC-ORD-004/R4
def test_created_after_combines_with_status_and_paging(api_base: str) -> None:
    status, body = get_json(
        f"{api_base}/orders?status=paid&created_after=2026-09-14&page=2&page_size=1"
    )
    assert status == 200
    assert body["total"] == 2
    assert body["pages"] == 2
    assert [item["id"] for item in body["items"]] == ["ORD-2006"]
