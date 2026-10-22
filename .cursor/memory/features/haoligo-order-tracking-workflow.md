---
title: 订单跟踪发货付款与排产拆分
slug: haoligo-order-tracking-workflow
status: delivered
domain: dedicated-haoligo
when: 改好力 GO 订单跟踪价格/生产/财务行操作、提交生产选人、分批发货、付款提交财务
keywords:
  - 订单跟踪
  - order-tracking
  - 发货信息跟踪
  - 付款信息跟踪
  - submit-production
  - submit-finance
  - completion_status
standard: 新建含合同金额+附件+生产接收人；排产/完成分字段分次更新；发货多行备注；付款保存后选人提交财务开票
---

# 订单跟踪发货付款与排产拆分

## 目标

销售侧取消行内「价格/生产/财务」旧入口，改为：新建带合同信息并提交生产；发货与付款独立跟踪；生产接收人改排产/完成；财务收付款提交后填开票。

## 何时读 / 禁止另起

- 何时读：改订单跟踪工作流、通知、开票门禁、发货明细
- 禁止：再把排产/完成塞进发货弹窗；禁止未 `finance_submitted` 就写开票字段；禁止把 `completed` 塞回 `order_status`

## 标准入口

| 层 | 标准 |
|----|------|
| FE | `haoligo/pages/order-tracking/index.tsx` |
| BE | `routes_order_tracking.py`：`POST submit-production` / `submit-finance`；PATCH 分权限写字段 |
| 权限 | 提交生产：`update` 或 `submit`；开票：`order-tracking-finance:read` + `update`；排产/完成：`submit` 或生产接收人 |

## 关键文件

| 角色 | 路径 |
|------|------|
| 模型 | `models/order_tracking.py`（`completion_status`、接收人、发货 `remarks`） |
| 迁移 | `909_20261021233000_haoligo_order_tracking_workflow.py` |
| API | `api/routes_order_tracking.py` |
| 服务 | `services/salesTracking.ts` |

## 踩坑

- 历史 `order_status=completed` 迁移拆到 `completion_status=completed` 且排产回落 `scheduled`
- 付款弹窗保存后未提交财务会弹出选人；已 `finance_submitted` 只保存付款
- 列表筛「排产」「完成」可同时生效（独立字段）

## 关联

- `features/haoligo-monthly-ledger-submit-finance.md`
