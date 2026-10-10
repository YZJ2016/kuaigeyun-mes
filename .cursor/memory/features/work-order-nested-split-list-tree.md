---
title: 生产工单多级拆分列表树
slug: work-order-nested-split-list-tree
status: active
keywords:
  - 工单拆分
  - 二次拆分
  - 多级拆分
  - attach_tree_children
  - parent_work_order_id
  - workOrderListTable
updated: 2026-10-08
---

## 何时读

生产工单「第一次拆分正常、再拆一次看不到子单 / 列表无变化」。

## 原因

两处叠加：

1. 列表树 `WorkOrderTreeService.attach_tree_children` 原先只按页内根工单 ID 拉一层 `parent_work_order_id`。对**拆分子工单再拆分**时，新单挂在子单下，不会出现在根的 `children` 里。
2. 前端 `normalizeUngroupedWorkOrderTree` / `attachSplitAndReworkChildren` 挂子行时 `push({ ...child })` 拷贝对象，孙单挂到 Map 原对象上，展开展示的仍是无孙单的拷贝，列表看起来完全没变化。

组内工单另有坑：`propagateWorkOrderGroupIdFromParent` 只传一层 `work_order_group_id`，孙单丢组后进 ungrouped，从组树消失。拆分写入现已复制 `work_order_group_id`。

## 标准入口

- 后端：`riveredge-backend/src/apps/kuaizhizao/services/work_order_tree_service.py`（BFS 拉全层级拆分子单并递归 nest）
- 前端：`workOrderListTable.ts`（组 ID 沿 parent 链迭代传递）；`workOrderListGroupTree.ts`（多级 depth）

## 禁止

- 不要为二次拆分另做列表接口或平行树组件
- 不要只在前端用编码正则猜挂载而跳过后端 `parent_work_order_id` 多级数据

## 踩坑（工序卡 / 报工）

- 首次拆分会软删主工单工序；`_resolve_split_operation_template_ops` 必须能回落**归档工序**或旁系兄弟，否则二次/多级拆分子单无工序、工序卡空白、无法报工。
- 列表默认展开原先故意收起「仅有拆分子行」的父行；多级拆分时要默认展开有孙拆分的祖先与带 children 的拆分行，否则「看不到孙工单」。
- `resolveWorkOrderOperationSteps` 查父行不能写死 `work_order-{id}`，多级时父行 key 是 `split-{id}`。

## 踩坑（工序进度串行）

- 子单**有自有** `operation_steps` 时，进度 = 本单合格 / 本单计划量（`build_work_order_operation_steps`）；完成后应为 done/100%。
- 子单**缺**自有步骤、或已拆分父行借下级路线展示时，只能用 `asRouteOnlyWorkOrderOperationSteps` / `as_route_only_operation_steps`（全 pending、无 %），禁止直接复用父/兄弟/子行的带进度 steps，否则会出现「未报工子单显示兄弟 100%」或「父行显示某一子单进度」。

## 踩坑（列表「完工进度」列恒 0%）

- 列表 `_batch_work_order_downstream_push_progress` 只算页内根工单。拆分子单由 `attach_tree_children` 挂树，**必须在挂树时再批量算子单进度**并写入 `downstream_push_progress`。
- 已拆分主单/中间拆分行工序已软删，自身算出来恒 0%；应在 nest 时按**拆分子单数量加权**汇总（`sum(子进度×子数量)/主数量`，未拆完剩余量视为 0%）。
- 开关：`attach_tree_children(..., include_downstream_push_progress=)` 与列表 prefetch 对齐，避免多余查询。
