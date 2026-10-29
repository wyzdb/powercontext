"""Order listing rules.

The module is deliberately dependency-free: the demo service must start on a
clean machine with nothing but the Python standard library, and the SDD
context module must be able to index these symbols with ``ast`` alone.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Iterable, Sequence

from orderflow.models import Order, Page

STATUSES: tuple[str, ...] = ("pending", "paid", "shipped", "cancelled")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class QueryError(ValueError):
    """A list-orders request that violates the query contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_status(status: str) -> str:
    """Return the canonical status token or raise ``invalid_status``."""

    candidate = status.strip().lower()
    if candidate not in STATUSES:
        raise QueryError("invalid_status", f"unknown status: {status!r}")
    return candidate


def parse_page(value: str | int) -> int:
    """Parse a 1-based page number."""

    try:
        page = int(value)
    except (TypeError, ValueError) as exc:
        raise QueryError("invalid_pagination", f"page is not an integer: {value!r}") from exc
    if page < 1:
        raise QueryError("invalid_pagination", f"page must be >= 1: {page}")
    return page


def parse_page_size(value: str | int) -> int:
    """Parse a page size in ``1..MAX_PAGE_SIZE``."""

    try:
        size = int(value)
    except (TypeError, ValueError) as exc:
        raise QueryError("invalid_pagination", f"page_size is not an integer: {value!r}") from exc
    if size < 1 or size > MAX_PAGE_SIZE:
        raise QueryError(
            "invalid_pagination",
            f"page_size must be between 1 and {MAX_PAGE_SIZE}: {size}",
        )
    return size


def parse_min_total(value: str | int) -> int:
    """Parse the inclusive lower bound on ``total_cents``."""

    try:
        minimum = int(value)
    except (TypeError, ValueError) as exc:
        raise QueryError("invalid_min_total", f"min_total is not an integer: {value!r}") from exc
    if minimum < 0:
        raise QueryError("invalid_min_total", f"min_total must be >= 0: {minimum}")
    return minimum


def parse_created_after(value: str) -> dt.date:
    """Parse the inclusive lower bound on the order creation calendar day."""

    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise QueryError(
            "invalid_created_after",
            f"created_after is not a valid YYYY-MM-DD date: {value!r}",
        ) from exc
    if parsed.strftime("%Y-%m-%d") != value:
        raise QueryError(
            "invalid_created_after",
            f"created_after is not a valid YYYY-MM-DD date: {value!r}",
        )
    return parsed


def _sort_key(order: Order) -> tuple[int, str]:
    # SPEC-ORD-005: highest total first, ties broken by ascending order id so
    # repeated pages never reshuffle equal totals.
    return (-order.total_cents, order.id)


def list_orders(
    orders: Iterable[Order],
    *,
    status: str | None = None,
    min_total: int | str | None = None,
    created_after: str | None = None,
    page: int | str = 1,
    page_size: int | str = DEFAULT_PAGE_SIZE,
) -> Page:
    """Return one page of orders after applying the supported filters.

    Filtering happens before sorting and paging, so ``total`` always counts the
    filtered set and ``page`` indexes into it.
    """

    page_number = parse_page(page)
    size = parse_page_size(page_size)
    status_token = normalize_status(status) if status is not None else None
    minimum = parse_min_total(min_total) if min_total is not None else None
    created_after_date = (
        parse_created_after(created_after) if created_after is not None else None
    )

    filtered: Sequence[Order] = [
        order
        for order in orders
        if (status_token is None or order.status == status_token)
        and (minimum is None or order.total_cents >= minimum)
        and (
            created_after_date is None
            or dt.datetime.fromisoformat(order.created_at).date() >= created_after_date
        )
    ]

    ordered = sorted(filtered, key=_sort_key)
    total = len(ordered)
    start = (page_number - 1) * size
    items = tuple(ordered[start : start + size])
    pages = math.ceil(total / size) if total else 0
    return Page(items=items, total=total, page=page_number, page_size=size, pages=pages)
