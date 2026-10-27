"""Expense approval policy.

The manager threshold is supplied by the current requirements specification.
"""

from __future__ import annotations

MANAGER_THRESHOLD = 500.0


def approve(amount: float, category: str, requester: str) -> dict[str, object]:
    """Return an approval decision for one expense request."""

    if amount <= 0:
        raise ValueError("amount must be positive")
    if not category.strip():
        raise ValueError("category must not be empty")
    if not requester.strip():
        raise ValueError("requester must not be empty")

    if amount > MANAGER_THRESHOLD:
        return {
            "status": "pending_manager",
            "requires_manager": True,
            "amount": amount,
            "category": category,
            "requester": requester,
        }
    return {
        "status": "approved",
        "requires_manager": False,
        "amount": amount,
        "category": category,
        "requester": requester,
    }
