"""Prompt assembly from a context payload."""

from __future__ import annotations

from pathlib import Path

from sdd_context.config import Settings
from sdd_context.pipeline import build_prompt

ROOT = Path(__file__).resolve().parents[1]


def _context() -> dict:
    return {
        "task": "为订单列表增加 created_after 过滤",
        "specs": [
            {
                "clause_id": "SPEC-ORD-004/R2",
                "heading": "过滤语义",
                "body": "边界当天的订单必须全部包含。",
                "role": "required",
                "version": 1,
                "status": "proposed",
                "source": {
                    "path": "specs/SPEC-ORD-004-created-after.md",
                    "line_start": 16,
                    "line_end": 18,
                },
            },
            {
                "clause_id": "SPEC-ORD-005/R1",
                "heading": "排序键",
                "body": "总额从高到低，相同总额按订单号升序。",
                "role": "constraint",
                "version": 5,
                "status": "active",
                "source": {
                    "path": "specs/SPEC-ORD-005-stable-ordering.md",
                    "line_start": 12,
                    "line_end": 14,
                },
            },
        ],
        "code": [
            {
                "symbol_id": "orderflow.service.list_orders",
                "path": "src/orderflow/service.py",
                "signature": "list_orders(orders, *, status=None, min_total=None)",
                "role": "modify",
                "source": {
                    "path": "src/orderflow/service.py",
                    "line_start": 83,
                    "line_end": 114,
                },
            }
        ],
        "tests": [
            {
                "test_id": "tests/test_created_after_api.py::test_created_after_filters_orders",
                "path": "tests/test_created_after_api.py",
                "kind": "target",
            },
            {
                "test_id": "tests/test_service_listing.py::test_ordering_is_total_desc_then_id_asc",
                "path": "tests/test_service_listing.py",
                "kind": "regression",
            },
        ],
        "change_targets": ["orderflow.service.list_orders"],
    }


def test_prompt_includes_required_and_constraint_clauses() -> None:
    prompt = build_prompt(Settings.from_env(root=ROOT), _context())
    assert "边界当天的订单必须全部包含。" in prompt["user"]
    assert "总额从高到低" in prompt["user"]
    assert "SPEC-ORD-004/R2" in prompt["user"]


def test_prompt_embeds_real_file_contents() -> None:
    prompt = build_prompt(Settings.from_env(root=ROOT), _context())
    assert "### src/orderflow/service.py" in prompt["user"]
    assert "from __future__ import annotations" in prompt["user"]


def test_prompt_states_output_contract_and_hard_rules() -> None:
    prompt = build_prompt(Settings.from_env(root=ROOT), _context())
    assert "PATCH>>>" in prompt["user"]
    assert "unified diff" in prompt["user"]
    assert "不要修改测试" in prompt["system"]
    assert "from __future__" in prompt["system"]
