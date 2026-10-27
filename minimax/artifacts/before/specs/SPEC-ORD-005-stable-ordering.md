---
id: SPEC-ORD-005
title: 订单列表稳定排序
version: 5
status: active
applies_to: [orderflow.service.list_orders, orderflow.service._sort_key]
verified_by: [tests/test_service_listing.py]
---

# 订单列表稳定排序

## R1 排序键

排序键是 `(-total_cents, id)`：总额从高到低；总额相同时按订单号字符串升序。排序必须稳定且与过滤条件无关，翻页前后不能出现同一订单重复或遗漏。

## R2 兼容性约束

新增筛选条件只能缩小候选集合，不得改变同一集合内的相对顺序；任何改动都必须让 `tests/test_service_listing.py` 中的排序回归用例继续通过。
