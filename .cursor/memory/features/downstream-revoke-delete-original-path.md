---
title: 下推下游原路反审再删除
slug: downstream-revoke-delete-original-path
status: delivered
domain: mes-production
when: 反审核、删除、销售订单下推工单/采购、需求计算撤回、销售已出库仍能删报工、出库撤回
keywords:
  - 原路递归反审
  - has_downstream
  - has_posted_sales_outbound
  - _cascade_delete_unexecuted_downstream
  - _is_downstream_executed
  - withdraw_from_computation
  - 请先反审核并删除
  - sales_order.revoke_approval.has_downstream
standard: 销售订单/工单/报工/出库等上游反审删除只 block；需求计算撤回/删除保持原逻辑——下游未执行（含草稿）可级联删，已执行则拦。
---

# 下推下游原路反审再删除

## 目标

下推产生的下游单据，多数上游反审/删除须先对下游**反审核再删除**，禁止跳级吞单。

**例外（保持原行为）**：需求计算撤回/删除——下游未执行时可级联删除；仅草稿等未执行态可级联，已执行则拦截。

## 何时读 / 禁止另起

- 何时读：销售订单/采购订单/工单/需求计算/报工/出库的 revoke、delete、withdraw
- 禁止：改需求计算时另起「有下游一律拦」；把需求计算级联改成与销售订单同一套硬拦

## 标准入口

| 场景 | 标准 |
|------|------|
| 销售订单反审/删除 | `list_sales_order_active_downstream_documents` + assert；文案「请先反审核并删除下游」 |
| 需求计算撤回/删除 | `_is_downstream_executed` 拦已执行；未执行走 `_cascade_delete_unexecuted_downstream` |
| 采购订单反审/删除 | `purchase_order_has_downstream` |
| 工单撤回/删除 | `_assert_work_order_revoke_no_downstream` |
| 报工反审/删除 | `has_posted_sales_outbound` + `has_approved_inbound_downstream` |
| 销售出库撤回 | 对齐 delete：非待发送送货单 / 已确认退货 |
| 成品入库撤回 | 装箱绑定 + 工单产品已出库 |

## 关键文件

| 角色 | 路径 |
|------|------|
| SO 下游 | `sales_order_code_sync.py`、`sales_order_service._assert_sales_order_capability_for_order` |
| 需求计算 | `demand_service.py`（`_is_downstream_executed` / `_cascade_delete_unexecuted_downstream`） |
| 报工 | `reporting_service.py` + `document_action_policy/reporting_record.py` |
| 出库 | `warehouse_service.withdraw_delivery_confirmation` |
| 文案 | `document_action_policy/types.py`、`useDocumentCapabilities.ts` |

## 扩展点

1. 销售订单等新下推边：父单据 revoke/delete **只 block**；列表 capabilities 批量探测。
2. 需求计算：草稿/未执行下游可级联删；勿改为「存在即拦」。
3. 报工关联已审核/已入库：禁级联冲销，须先反审删入库再反审报工。

## 过程（销售订单）

1. 有生产工单 / 采购订单 / 采购申请 / 出库等 → 禁反审、禁删。
2. 用户先对下游反审 → 再删下游 → 再撤需求计算（若有）→ 再反审/删销售订单。
3. 需求计算撤回：未执行下游级联删；已执行则提示先处理下游。

## 踩坑

- PO 常无 `sales_order_id` FK，须查 `DocumentRelation`。
- 勿把需求计算改成与 SO 相同的「有下游一律拦」；用户约定需求计算保持原级联逻辑。

## 关联

- `principles/reuse-existing-patterns.md`
