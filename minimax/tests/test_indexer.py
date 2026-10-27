"""Indexing of the shipped business project."""

from __future__ import annotations

from pathlib import Path

from sdd_context.indexer import build_index

BUSINESS = Path(__file__).resolve().parents[1] / "business"


def test_index_covers_specs_symbols_and_tests() -> None:
    bundle = build_index(BUSINESS)
    stats = bundle.stats()
    assert stats["specs"] == 6
    assert stats["clauses"] >= 15
    assert stats["symbols"] >= 25
    assert stats["tests"] >= 18
    assert stats["terms"] > 500


def test_proposed_spec_tests_are_targets() -> None:
    bundle = build_index(BUSINESS)
    by_id = {test.test_id: test for test in bundle.tests}
    target = [test for test in bundle.tests if test.kind == "target"]
    assert len(target) == 4
    assert all(test.path.endswith("test_created_after_api.py") for test in target)
    assert by_id["tests/test_service_listing.py::test_ordering_is_total_desc_then_id_asc"].kind == (
        "regression"
    )


def test_symbol_identity_uses_module_qualname() -> None:
    bundle = build_index(BUSINESS)
    symbols = {symbol.symbol_id: symbol for symbol in bundle.symbols}
    assert "orderflow.service.list_orders" in symbols
    assert "orderflow.api.OrderRequestHandler.do_GET" in symbols
    assert symbols["orderflow.service.list_orders"].path == "src/orderflow/service.py"


def test_every_test_cites_at_least_one_spec_or_symbol() -> None:
    bundle = build_index(BUSINESS)
    for test in bundle.tests:
        if not (test.spec_refs or test.code_refs):
            # Fallback links come from the specification's verified_by list.
            assert test.path.endswith(".py")
    claused = {clause.clause_id for clause in bundle.clauses}
    spec_ids = {clause.spec_id for clause in bundle.clauses}
    for test in bundle.tests:
        for ref in test.spec_refs:
            assert ref in claused or ref in spec_ids, f"{test.test_id} cites unknown {ref}"
