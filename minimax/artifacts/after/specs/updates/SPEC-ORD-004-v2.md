---
id: SPEC-ORD-004
title: 订单列表按创建时间筛选
version: 2
status: active
applies_to: [orderflow.service.list_orders, orderflow.api.parse_list_query, orderflow.api.ListQuery, orderflow.api.ListQuery.as_filters]
verified_by: [tests/test_created_after_api.py]
---

# 订单列表按创建时间筛选

## R1 参数形态

`GET /orders` 新增可选查询参数 `created_after`，取值为 ISO-8601 日历日期，格式固定为 `YYYY-MM-DD`。参数缺省时行为与当前版本一致；参数出现且非空时进入 R2 的过滤逻辑。`created_after` 以原始字符串从 HTTP 层传入服务层，由服务层解析与校验；HTTP 层只做参数透传，不得假设调用方会传入日期对象。

## R2 过滤语义

过滤条件是 `created_at` 的日期部分大于等于 `created_after`，比较按日历日进行，不受时区偏移影响。边界当天的订单必须全部包含：`00:00:00` 到 `23:59:59` 的所有时刻都算命中，边界前一天 `23:59:59` 的订单必须排除；日期比较不得按字符串前缀截断。数据契约：`Order.created_at` 是 ISO-8601 **字符串**（例如 `2026-09-15T00:00:00+08:00`），不是 `date` 或 `datetime` 对象，实现不得调用其 `.date()` 一类方法。

## R3 非法输入

`created_after` 无法按 `YYYY-MM-DD` 解析时（例如 `2026-13-01`、`2026-9-1`、空值、非日期文本），接口返回 HTTP 400，响应体 `error.code` 为 `invalid_created_after`，并沿用 SPEC-API-001 的错误信封。

## R4 与既有筛选、分页的组合

`created_after` 必须能和 `status`、`min_total`、`page`、`page_size` 同时使用：先做全部过滤，再排序，最后分页；`total` 与 `pages` 按过滤后的集合计算，不得按过滤前的集合计算。

## R5 筛选审计字段

响应体在 `filters` 字段中回显本次实际生效的筛选条件，`created_after` 归一化为 `YYYY-MM-DD`；未生效的筛选条件不出现在 `filters` 中。该字段用于验证样例核对过滤是否真的生效。
