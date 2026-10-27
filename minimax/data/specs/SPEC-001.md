# SPEC-001: Expense approval authority

- Status: active
- Version: 1
- Owner: finance-platform

## Requirement

Expense requests at or below **500** units may be auto-approved.
Expense requests above **500** units must be marked `pending_manager` and set
`requires_manager` to `true`.

The threshold is inclusive: exactly 500 is auto-approved; 500.01 requires a manager.

## Compatibility

Existing behaviour for invalid amounts must remain: non-positive amounts raise
`ValueError`, and empty category or requester values raise `ValueError`.
