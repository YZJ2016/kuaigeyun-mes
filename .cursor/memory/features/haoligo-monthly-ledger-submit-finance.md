---
title: 月度工厂台账提交财务
slug: haoligo-monthly-ledger-submit-finance
status: delivered
domain: dedicated-haoligo
when: 改好力 GO 月度工厂台账「提交财务」选人、财务开票、站内信通知
keywords:
  - 月度工厂台账
  - 提交财务
  - monthly-factory-ledger
  - submit-finance
  - finance_submitted
  - 开票信息
standard: 销售 update → POST submit-finance 多选接收人+站内信；财务 monthly-factory-ledger-finance:read 后填开票字段
---

# 月度工厂台账提交财务

## 目标

销售填完发货/开票数量后「提交财务」多选接收人并通知；财务账号看到已提交单据后点「开票信息」填发票号、金额、时间。

## 何时读 / 禁止另起

- 何时读：改月度台账财务流转、通知、开票门禁
- 禁止：再把行操作叫「财务」直开编辑；禁止未提交就允许写开票字段；禁止旁路财务权限码用销售 update 冒充可见开票列

## 标准入口

| 层 | 标准 |
|----|------|
| FE | `haoligo/pages/monthly-factory-ledger/index.tsx`：未提交显示「提交财务」→ FormModalTemplate 多选用户；已提交且有财务 read →「开票信息」 |
| BE | `POST .../monthly-factory-ledgers/{id}/submit-finance`；PATCH 开票字段须 `finance_submitted` + finance read |
| 权限 | 提交：`haoligo:monthly-factory-ledger:update`；看/填开票：`haoligo:monthly-factory-ledger-finance:read`（写仍要 ledger update） |

## 关键文件

| 角色 | 路径 |
|------|------|
| 列表页 | `riveredge-frontend/src/apps/haoligo/pages/monthly-factory-ledger/index.tsx` |
| API | `riveredge-frontend/src/apps/haoligo/services/salesTracking.ts` |
| 路由 | `riveredge-backend/src/apps/haoligo/api/routes_monthly_factory_ledger.py` |
| 模型 | `riveredge-backend/src/apps/haoligo/models/monthly_factory_ledger.py` |
| 迁移 | `migrations/models/908_20261021230000_haoligo_monthly_ledger_submit_finance.py` |

## 扩展点

1. 接收人检索：`searchUserDisplay` + `host_resource=haoligo:monthly-factory-ledger`
2. 通知：`MessageService.send_message`，`detail_path=/apps/haoligo/monthly-factory-ledger`
3. 未开票：`uninvoiced_qty = monthly_shipment_total - monthly_invoice_qty`（销售改数量时重算）

## 踩坑

- 财务列仅 `canViewFinance` 时展示；无财务权限的销售列表不露票号金额
- 已提交后隐藏「提交财务」，避免重复提交；若需重提要另开产品需求
- 角色须勾选 `monthly-factory-ledger-finance` 的 read，否则看不到「开票信息」按钮与发票列

## 关联

- `features/haoligo-ledger-batch-export.md`
- `principles/reuse-existing-patterns.md`
