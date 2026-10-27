---
id: SPEC-API-001
title: 订单查询接口契约
version: 6
status: active
applies_to: [orderflow.api.parse_list_query, orderflow.api.OrderRequestHandler.do_GET, orderflow.api.OrderHTTPServer]
verified_by: [tests/test_api_listing.py, tests/test_created_after_api.py]
---

# 订单查询接口契约

## R1 成功响应

`GET /orders` 返回 200 与 JSON 对象，字段为 `items`、`total`、`page`、`page_size`、`pages`；`items` 的每一项包含 `id`、`customer`、`status`、`total_cents`、`created_at`，不得删减既有字段或改名。

## R2 业务校验失败

过滤参数或分页参数非法时返回 400，响应体固定为 `{"error": {"code": "...", "message": "..."}}`，`code` 使用服务层抛出的错误码（如 `invalid_status`、`invalid_pagination`、`invalid_min_total`）。

## R3 未知路由

未定义的路由返回 404，`error.code` 为 `not_found`，不得回落到订单列表。

## R4 健康检查

`GET /health` 返回 `{"status": "ok"}`，用于验证样例与评测脚本确认服务已就绪。
