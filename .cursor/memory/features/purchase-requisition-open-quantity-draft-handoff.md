---
title: 采购申请实际余量与订单草稿队列
slug: purchase-requisition-open-quantity-draft-handoff
status: in_progress
domain: mes-purchase
when: 修改采购申请开口取单、分批转单、撤回重开或采购订单草稿接续时
keywords:
  - pull_open_line_quantity
  - list_purchase_order_pull_lines
  - handoffRequisitionToPurchaseOrderCreate
  - startPoHandoffDraftQueue
standard: 主数量按实际占用计算；转单复用现有采购订单新建草稿队列，不另建直推路径
---

# 采购申请实际余量与订单草稿队列

## 何时读 / 禁止另起

- 何时读：采购申请分批下推、取单数量列、订单草稿多张接续、撤回后重新取单。
- 禁止：仅凭 purchase_order_id 就把整行判为转满；把主数量映射解包成并不存在的主副数量 tuple。
- 禁止：缺少 ORM 副数量读写闭环时伪造辅助数量字段，或新建第二套草稿/引用展示实现。

## 标准入口

- 服务：`riveredge-backend/src/apps/kuaizhizao/services/purchase_requisition_service.py`。
- 数量工具：`riveredge-backend/src/apps/kuaizhizao/utils/pull_open_line_quantity.py`，本地仅主数量。
- 前端接续：`riveredge-frontend/src/apps/kuaizhizao/utils/documentFlowHandoff.ts` 的 `handoffRequisitionToPurchaseOrderCreate`，复用 `draftPurchaseOrdersFromRequisitionItems` 与 `startPoHandoffDraftQueue`。
- 采购申请/采购订单页：同应用 `pages/purchase-management/purchase-requisitions/index.tsx`、`purchase-orders/index.tsx`。
- 来源筛选：既有 `loadPullSourceReferenceOptions` + `PULL_SOURCE_REFERENCE.purchaseRequisition`，宿主 `kuaizhizao:purchase-order`；不为了筛选去打开来源完整列表读取权限。

## 契约与扩展点

1. 可选数量仍以主数量为门禁，实际占用决定已转/剩余；链接 ID 并非占满证明。
2. 同申请/物料拆分行合并建议与占用口径，展示未转承运行；占满组保留代表行以免重复。
3. 预览/规划也检查真实剩余量，前端禁选不能代替后端校验。
4. 申请头 DateField 在取单响应中序列化为日历日；`document_date` 与 `requisition_date` 同源，不能引用未初始化局部变量。

## 验证入口

- 既有 `riveredge-backend/tests/apps/kuaizhizao/services/test_purchase_requisition_required_date.py` 包含实际服务调用的分批、链接行重开及闭组合并回归。
- 若扩副数量，必须先评 ORM、迁移和占用写读闭环，不直接把上游 aux helper 整段覆盖到本地。

## 关联

- `features/purchase-requisition-line-delivery-carry.md`
- `features/pull-source-display-echo.md`
