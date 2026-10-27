"""The verification sample shared by scripts, docs and tests."""

from __future__ import annotations

SAMPLE_TASK_ID = "task-order-created-after"
SAMPLE_TITLE = "为订单列表增加创建时间筛选"

SAMPLE_TASK = (
    "为 orderflow 的订单列表接口增加按创建时间筛选能力：GET /orders 支持 created_after 参数，"
    "取值为 YYYY-MM-DD，边界当天 00:00:00 与 23:59:59 的订单都必须包含，边界前一天的订单必须排除；"
    "非法日期返回 HTTP 400，错误码为 invalid_created_after；该参数要和 status、min_total、分页同时生效，"
    "先过滤后分页。不得改变原有的分页语义（SPEC-ORD-001）、状态筛选（SPEC-ORD-002）、"
    "金额下限（SPEC-ORD-003）与排序规则（SPEC-ORD-005）。"
)

SAMPLE_TARGET_TESTS = "tests/test_created_after_api.py"
SAMPLE_REGRESSION_TESTS = "tests/test_service_listing.py tests/test_api_listing.py"
