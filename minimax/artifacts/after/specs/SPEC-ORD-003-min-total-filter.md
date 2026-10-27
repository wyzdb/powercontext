---
id: SPEC-ORD-003
title: 订单金额下限筛选
version: 2
status: active
applies_to: [orderflow.service.list_orders, orderflow.service.parse_min_total]
verified_by: [tests/test_service_listing.py]
---

# 订单金额下限筛选

## R1 闭区间语义

`min_total` 表示订单总额（单位：分）的下界，过滤条件为 `total_cents >= min_total`，等于下界的订单必须保留。

## R2 非法取值

`min_total` 必须是大于等于 0 的整数；负数、非整数文本抛出 `invalid_min_total`，HTTP 层映射为 400。
