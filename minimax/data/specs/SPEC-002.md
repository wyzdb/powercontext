# SPEC-002: Audit metadata

- Status: active
- Version: 1

## Requirement

Every approval decision must preserve the original `amount`, `category` and
`requester` values so that the caller can write an audit record.

## Compatibility

No field may be removed or renamed without a specification revision.
