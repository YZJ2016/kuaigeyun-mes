---
title: 返工单起始工序列表/报工展示
slug: rework-order-start-operation-display
status: delivered
domain: mes-production
when: 返工工单起始工序显示「-」、返工报工起始工序未显示
keywords:
  - 起始工序
  - start_operation_name
  - rework_operations
  - ReworkReportingOptionsResponse
standard: 列表返回 start_operation_*；报工 options 返回 start_operation_name；勿只靠列表里的 rework_operations
---

# 返工单起始工序列表/报工展示

## 踩坑

- 列表 `ReworkOrderListResponse` 原先无 `rework_operations`，前端 `colStartOperation` 读不到工序
- 报工弹窗读 `start_operation_name`，后端只回了 `current_operation_name`

## 标准入口

| 层 | 路径 |
|----|------|
| Schema | `schemas/rework_order.py` List + ReportingOptions |
| BE | `rework_order_service.list_rework_orders` / `get_rework_reporting_options` |
| FE | `rework-orders/index.tsx` 列与报工卡片 |
