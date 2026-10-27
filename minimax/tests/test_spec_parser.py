"""Specification parsing: clause identity, ranges and front matter."""

from __future__ import annotations

from sdd_context.spec_parser import parse_spec_file, parse_spec_text

SAMPLE = """---
id: SPEC-ORD-900
title: 示例规格
version: 3
status: proposed
applies_to: [orderflow.service.list_orders]
verified_by: [tests/test_example.py]
---

# 示例规格

## R1 第一条

第一段正文。

## R2 第二条

第二段正文。
"""


def test_clause_identity_and_ranges() -> None:
    document = parse_spec_text(SAMPLE, path="specs/SPEC-ORD-900.md")
    assert document.spec_id == "SPEC-ORD-900"
    assert document.version == 3
    assert document.status == "proposed"
    assert document.applies_to == ("orderflow.service.list_orders",)
    assert [clause.clause_id for clause in document.clauses] == [
        "SPEC-ORD-900/R1",
        "SPEC-ORD-900/R2",
    ]
    first, second = document.clauses
    assert first.heading == "第一条"
    assert first.body == "第一段正文。"
    assert first.line_start == 12
    assert second.line_start > first.line_end


def test_real_specs_are_parseable() -> None:
    root = __import__("pathlib").Path(__file__).resolve().parents[1] / "business"
    for path in sorted((root / "specs").glob("SPEC-*.md")):
        document = parse_spec_file(path, root)
        assert document.clauses, f"{path.name} has no normative clauses"
        for clause in document.clauses:
            assert clause.line_start >= 1
            assert clause.line_end >= clause.line_start
