---
title: 其他费用收入/支出/支出申请
keywords: other_income, other_expense, other_expense_application, finance-misc-category, misc_voucher_posting, review_status
---

# 其他费用收入 / 其他费用支出 / 其他费用支出申请

上游对齐版（Spec 225）：三类单据均为三段式审核，审核态由 `review_status` 承载。

## 标准入口

- 模型：`apps/kuaicaiwu/models/other_voucher.py`（OtherIncome/OtherExpense）、`other_expense_application.py`、`finance_misc_category.py`
- 服务：`other_income_service.py` / `other_expense_service.py` / `other_expense_application_service.py`；审核 `other_income_audit_service.py` / `other_expense_audit_service.py` / `other_expense_application_audit_service.py`；过账 `misc_voucher_posting_service.py`；关联/识别回写 `misc_voucher_finance_bridge.py`
- API：`/apps/kuaicaiwu/other-incomes`、`other-expenses`、`other-expense-applications`、`finance-misc-categories/{income|expense}`
- 前端：`pages/finance-management/other-incomes|other-expenses|other-expense-applications`（共享 `shared/MiscVoucherListPage` + `MiscVoucherDetailDrawer`，申请单走 `documentVariant="expense_application"`）；明细行类别用 `MiscCategoryQuickSelect` = `UniDropdown.quickCreate` + `QuickCreateModal`（禁止 Select 自写 popupRender）
- 类别维护：`finance-misc-categories/index.tsx`（UniTable 标准壳）
- 权限 manifest：`kuaicaiwu:other-income:*`、`kuaicaiwu:other-expense:*`、`kuaicaiwu:other-expense-application:*`（含 `:push`）、`kuaicaiwu:finance-misc-category:*`
- 审核节点：`manifest.audit` → `other_income` / `other_expense` / `other_expense_application`（`check_audit_required`；finance_misc 策略）

## 状态语义（硬契约）

- `status` ∈ `Draft` / `Confirmed` / `Cancelled`（申请单审核通过后为 `Approved`）
- `review_status` ∈ `草稿` / `SUBMITTED` / `待审核` / `已审核` / `已驳回` 承载审核相位
- 三段式：`submit`→`commit_*`（草稿→SUBMITTED）、`submit_review`→`submit_*_for_review`（SUBMITTED→待审核）、approve/reject/withdraw/revoke 经 `*AuditService`
- `uni_audit_handlers._dispatch_other_*` + `approval_instance_service` completion handler 已直连三个 audit service

## 确认过账（仅供应商/客户往来）

- 支出 `confirm`：仅 `counterparty_kind=supplier` 且有自动应付；经 `create_concurrent_payment_for_payable` 生成真实付款单并挂单据关系
- 收入 `confirm`：`counterparty_kind=customer` + 应收 → 真实收款单
- 非供应商/客户往来无确认入口（审核即终点）；历史 `Confirmed` 无付款链路的单据不可反确认

## 禁止

- 复用 Payment/Receipt 手工创建链路；非供应商支出给确认入口
- 已 `Confirmed` 单据直接改回 `Draft`（须 unconfirm 冲销链路）

## 交付

- 迁移 `20261127210000`（申请表+expense source_*/counterparty_*）、`20261127210100`（申请单 related_purchase_receipts）、`20261127210200`（三类单据 review_status 数据收敛）
- 编码规则 `kuaicaiwu-finance-other-expense-application` → `QZSQ`；`manual_create_auto_lifecycle` 含三节点
- 申请单下推支出单走 uni-pull；支出单关联采购入库 `related_purchase_receipts` 走 UniPullQueryModal
</content>
