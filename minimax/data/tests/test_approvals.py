from __future__ import annotations

import pytest

from expense_approval.approvals import approve


def test_manager_approval_required_above_threshold() -> None:
    result = approve(750, "travel", "alice")
    assert result["status"] == "pending_manager"
    assert result["requires_manager"] is True


def test_auto_approval_at_or_below_threshold() -> None:
    result = approve(500, "travel", "alice")
    assert result["status"] == "approved"
    assert result["requires_manager"] is False


def test_invalid_amount_is_rejected() -> None:
    with pytest.raises(ValueError):
        approve(0, "travel", "alice")
