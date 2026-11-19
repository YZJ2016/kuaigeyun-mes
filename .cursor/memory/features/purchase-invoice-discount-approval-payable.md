---
title: 采购收票优惠占用与审核生应付
slug: purchase-invoice-discount-approval-payable
status: in_progress
domain: finance-ui
when: 修改采购收票优惠、开票占用、红冲或审核生成应付时
keywords:
  - discount_amount
  - purchase_invoice_amounts
  - purchase_invoice_payable_auto
  - adjust_payable
standard: 金额统一走 purchase_invoice_amounts；审核钩子生成应付，保留本地创建自动送审
---

# 采购收票优惠占用与审核生应付

## 何时读 / 禁止另起

- 何时读：采购收票优惠、源单可开票额度、按票确认应付、红冲和关联删除。
- 禁止：直接覆盖上游 `kuaizhizao/finance` 路径；本地财务真源是 `apps/kuaicaiwu`。
- 禁止：创建接口和审核钩子各生成一份应付；占用金额另写第二套公式。

## 标准入口

- 后端：`riveredge-backend/src/apps/kuaicaiwu/services/purchase_invoice_amounts.py` 统一金额，`purchase_invoice_payable_auto.py` 承接审核后生成，`finance_audit_workflow.py` 接审核。
- 模型/API：同应用 `models/purchase_invoice.py`、`schemas/finance.py`、`api/finance/purchase_invoices.py`。
- 前端：`riveredge-frontend/src/apps/kuaicaiwu/pages/finance-management/purchase-invoices/`，类型位于该应用 `types/finance/purchase-invoice.ts`。
- 配置：`riveredge-backend/src/infra/services/business_config_service.py`；按票确认时强制自动生成应付，策略解析保留单据级 resolved_strategy。

## 契约与扩展点

1. 票面金额为 I、优惠为 D（可带负号）；源单占用 W=I+D。不要把优惠一律绝对值化。
2. 创建仍沿用本地自动送审；应付生成改由审核通过触发。
3. 红冲、可用额度、订单财务生命周期及删除保护须与同一金额口径联动。
4. `20261122000001_purchase_invoice_discount_amount.py` 是对应迁移；新增模型字段不代表数据库已迁移，部署前须确认实际 upgrade。

## 已知限制

- 用户明确选择忠实保留上游早退顺序：源应付处于相关已审/待审分支时提前返回，后面的优惠调整应付分支不可达。不要宣称优惠调整单自动生成已生效；改变顺序需单独决策。
- 不把这次金额迁移扩成副数量 ORM、其他支出单或付款单 uni-audit 重建。

## 关联

- `features/purchase-invoice-pull-detail-lines.md`
- `features/partner-statement-push-invoice-date.md`
