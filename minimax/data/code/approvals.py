"""Expense approval policy (before the SDD task)."""

from __future__ import annotations


def approve(amount: float, category: str, requester: str) -> dict[str, object]:
    if amount <= 0:
        raise ValueError("amount must be positive")
    if not category.strip():
        raise ValueError("category must not be empty")
    if not requester.strip():
        raise ValueError("requester must not be empty")
    return {
        "status": "approved",
        "requires_manager": False,
        "amount": amount,
        "category": category,
        "requester": requester,
    }
