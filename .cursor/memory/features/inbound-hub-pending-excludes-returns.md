---
title: 入库 Hub「待入库」不含退料/退货
slug: inbound-hub-pending-excludes-returns
status: delivered
domain: warehouse
when: 生产入库待入库筛出退料、待退料混进待入库、inboundListAggregate status pending
keywords:
  - 待入库
  - 待退料
  - production_return
  - inboundListAggregate
  - 生产入库
standard: Hub status=pending 只拉入库待确认源；退料/退货类仅在 posted/all 或显式 receipt_type 时拉
---

# 入库 Hub「待入库」不含退料/退货

## 目标

筛选「待入库」只出现成品/半成品/采购等待入库单，不出现生产退料「待退料」等。

## 标准入口

| 层 | 标准 |
|----|------|
| 列表聚合 | `inboundListAggregate.ts`：`excludeReturnLikeForPendingHub` |
| 状态文案 | `inboundHubNormalize.resolveInboundHubStatusLabel`：待退料≠待入库 |

## 踩坑

- 旧逻辑用 `sourceStatus('待退料','已退料')` 把退料塞进 pending，生命周期显示「待退料」
- 显式选单据类型=生产退料 + 待入库时仍拉待退料（类型筛选优先）
