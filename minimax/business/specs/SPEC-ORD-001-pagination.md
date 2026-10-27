---
id: SPEC-ORD-001
title: 订单列表分页
version: 4
status: active
applies_to: [orderflow.service.list_orders, orderflow.service.parse_page, orderflow.service.parse_page_size]
verified_by: [tests/test_service_listing.py, tests/test_api_listing.py]
---

# 订单列表分页

## R1 页码与页大小边界

`page` 是 1 起始的页码，取值必须大于等于 1；`page_size` 取值必须在 `1..100` 闭区间内，默认 20。非整数或越界时抛出 `invalid_pagination`，HTTP 层映射为 400。

## R2 total 与 pages 的语义

`total` 是过滤后的记录总数，`pages` 是 `ceil(total / page_size)`；两者都不能按过滤前的集合计算。响应必须回显调用方实际使用的 `page` 与 `page_size`。

## R3 空结果

过滤后没有记录时，`items` 为空数组，`total` 为 0，`pages` 为 0，不得返回 1 页空数据。
