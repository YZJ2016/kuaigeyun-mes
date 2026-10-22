---
title: 需求计算与采购业务自动化
slug: planning-procurement-automation
status: delivered
domain: platform-config
when: 配置中心业务自动化、需求计算自动执行、采购订单自动审核、收货通知自动下推
keywords:
  - auto_execute_computation_on_create
  - auto_push_purchase_on_computation_complete
  - auto_approve_purchase_order_on_create
  - auto_push_receipt_notice_on_approve
  - demand-computation/auto-run
  - 业务自动化
  - 收货通知
standard: 配置中心 AUTOMATION_CATEGORIES + BusinessConfigService helpers + Taskiq demand-computation/auto-run
---

# 需求计算与采购业务自动化

## 目标

组织级开关（默认关）：需求计算创建后自动执行并下推采购；采购订单创建后自动审核并下推收货通知。

## 何时读 / 禁止另起

- 何时读：改配置中心「业务自动化」计划/采购分组；串 SO→MRP→PO→收货通知自动链
- 禁止：另写一套下推/审核引擎；旁路 `require_purchase_requisition` 直开采购订单；自动过审绕过 `is_auto_approve` 门禁却留孤儿审批实例

## 标准入口

| 层 | 标准 |
|----|------|
| FE | `configTree.ts` → `AUTOMATION_CATEGORIES` planning / procurement |
| BE 配置 | `BusinessConfigService` helpers + `DEFAULT_PARAMETERS` / `IMPLEMENTED_PARAMETER_KEYS` |
| BE 计划 | 创建计算后 `enqueue_demand_computation_automation` → 事件 `demand-computation/auto-run` |
| BE 采购 | `PurchaseService.try_auto_approve_purchase_order` / `try_auto_push_receipt_notice` |

## 关键文件

| 角色 | 路径 |
|------|------|
| 配置树 | `riveredge-frontend/src/pages/system/config-center/configTree.ts` |
| 配置服务 | `riveredge-backend/src/infra/services/business_config_service.py` |
| Taskiq | `riveredge-backend/src/apps/kuaizhizao/workflows/functions/demand_computation_automation_workflow.py` |
| 创建钩子 | `demand_computation_service.create_computation` / `generate_work_orders_and_purchase_orders` |
| 采购钩子 | `purchase_service.create_purchase_order` / `approve_purchase_order` |

## 扩展点

1. 开关：`planning.auto_execute_computation_on_create`、`planning.auto_push_purchase_on_computation_complete`、`procurement.auto_approve_purchase_order_on_create`、`procurement.auto_push_receipt_notice_on_approve`
2. 须先采购申请时：自动下推目标改为 `purchase_requisition`（`DocumentPushPullService`）
3. 下推形态：全局 `automation.push_default_mode`

## 踩坑

- 需求计算下推采购走 `PurchaseOrder.create` 旁路，须在 generate 结束后调 `try_auto_approve_purchase_order`
- 自动过审：草稿+有审核时不要先 `submit`（会启审批流）；置待审后 `is_auto_approve=True`；confirm 下推已启流时先 `cancel_approval`
- 失败写单据备注 `[业务自动化]`，不回滚上游审核

## 关联

- `features/scheduled-task-tenant-isolation-event.md`（Taskiq / tenant_id）
- `principles/reuse-existing-patterns.md`
