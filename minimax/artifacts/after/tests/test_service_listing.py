"""Regression tests for the order listing rules that already shipped."""

from __future__ import annotations

from orderflow.models import Order
from orderflow.service import (
    MAX_PAGE_SIZE,
    QueryError,
    list_orders,
    normalize_status,
    parse_min_total,
    parse_page,
    parse_page_size,
)


# spec: SPEC-ORD-002/R1
def test_unknown_status_is_rejected(sample_orders: tuple[Order, ...]) -> None:
    try:
        list_orders(sample_orders, status="refunded")
    except QueryError as exc:
        assert exc.code == "invalid_status"
    else:  # pragma: no cover - the branch is unreachable when the rule holds
        raise AssertionError("unknown status must raise invalid_status")


# spec: SPEC-ORD-002/R2
def test_status_filter_is_case_insensitive(sample_orders: tuple[Order, ...]) -> None:
    page = list_orders(sample_orders, status="PAID")
    assert [order.id for order in page.items] == ["ORD-2002", "ORD-2001", "ORD-2006"]


# spec: SPEC-ORD-003/R1
def test_min_total_is_inclusive(sample_orders: tuple[Order, ...]) -> None:
    page = list_orders(sample_orders, min_total=5000)
    assert [order.id for order in page.items] == [
        "ORD-2004",
        "ORD-2002",
        "ORD-2001",
        "ORD-2003",
    ]


# spec: SPEC-ORD-003/R2
def test_negative_min_total_is_rejected() -> None:
    try:
        parse_min_total(-1)
    except QueryError as exc:
        assert exc.code == "invalid_min_total"
    else:  # pragma: no cover
        raise AssertionError("negative min_total must raise invalid_min_total")


# spec: SPEC-ORD-001/R2
def test_pagination_counts_the_filtered_set(sample_orders: tuple[Order, ...]) -> None:
    page = list_orders(sample_orders, page=3, page_size=2)
    assert page.total == 6
    assert page.pages == 3
    assert [order.id for order in page.items] == ["ORD-2006", "ORD-2005"]


# spec: SPEC-ORD-001/R3
def test_empty_result_reports_zero_pages(sample_orders: tuple[Order, ...]) -> None:
    page = list_orders(sample_orders, status="cancelled", min_total=5000)
    assert page.items == ()
    assert page.total == 0
    assert page.pages == 0


# spec: SPEC-ORD-005/R1
def test_ordering_is_total_desc_then_id_asc(sample_orders: tuple[Order, ...]) -> None:
    page = list_orders(sample_orders, page_size=MAX_PAGE_SIZE)
    assert [order.id for order in page.items] == [
        "ORD-2004",
        "ORD-2002",
        "ORD-2001",
        "ORD-2003",
        "ORD-2006",
        "ORD-2005",
    ]


# spec: SPEC-ORD-001/R1
def test_page_bounds_are_validated() -> None:
    for value in (0, -3, "many"):
        try:
            parse_page(value)
        except QueryError as exc:
            assert exc.code == "invalid_pagination"
        else:  # pragma: no cover
            raise AssertionError(f"page={value!r} must raise invalid_pagination")
    for value in (0, MAX_PAGE_SIZE + 1):
        try:
            parse_page_size(value)
        except QueryError as exc:
            assert exc.code == "invalid_pagination"
        else:  # pragma: no cover
            raise AssertionError(f"page_size={value!r} must raise invalid_pagination")


# spec: SPEC-ORD-002/R1
def test_status_normalisation_strips_and_lowercases() -> None:
    assert normalize_status("  Shipped ") == "shipped"
