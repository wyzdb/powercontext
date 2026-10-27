---
id: SPEC-ORD-002
title: 订单状态筛选
version: 3
status: active
applies_to: [orderflow.service.list_orders, orderflow.service.normalize_status]
verified_by: [tests/test_service_listing.py, tests/test_api_listing.py]
---

# 订单状态筛选

## R1 取值与错误码

`status` 只接受 `pending`、`paid`、`shipped`、`cancelled` 四个取值；其他取值（包括拼写错误与空字符串）必须抛出 `invalid_status`，HTTP 层映射为 400，不得静默返回空列表。

## R2 大小写与空白

比较前对输入做去首尾空白与转小写处理，因此 `PAID`、` Paid ` 与 `paid` 等价；数据集中订单的 `status` 字段本身必须是小写规范值。
