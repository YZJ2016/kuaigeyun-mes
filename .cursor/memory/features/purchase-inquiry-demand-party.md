---
title: 采购询价需方与商务条款
keywords:
  - 采购询价
  - 需方
  - purchase-inquiry
  - purchase-demand-party
  - 询价需方
  - TRADE_MODE
  - 成交方式
  - email_notify
when: 改采购询价新建/编辑字段、需方主数据、询价商务条款时
---

# 采购询价需方与商务条款

## 标准入口

| 层 | 路径 |
|----|------|
| 需方列表页 | `riveredge-frontend/.../purchase-management/purchase-demand-parties/index.tsx` |
| 询价表单 | `.../purchase-management/purchase-inquiries/index.tsx` FormModal |
| 需方 API | `/apps/kuaizhizao/purchase-demand-parties` |
| 模型 | `purchase_demand_party.py`、`purchase_inquiry.py`（头表商务字段 + vendor 联系/通知） |
| 迁移 | `899` 建表；`900` 补 `uuid`（899 漏列会导致 `column "uuid" does not exist`） |
| 字典 | `TRADE_MODE`（成交方式）；付款条件 `PAYMENT_TERMS`；币种 `CURRENCY`；付款方式/发票类型复用 `financeSharedOptions` |

## 约定

- 需方：独立 CRUD；询价下拉可读（`purchase-demand-party:read` **或** `purchase-inquiry:read`）
- 采购负责人：系统用户选；手机可改
- 供应商行：联系人/电话/邮箱/`email_notify` **仅落库**，本轮不发邮件
- 税率：库内存小数（0.13）；表单用百分比

## 详情 Tab

- **审批记录**：`historyTab` → `DocumentApprovalRecordsPane`（`entityType=purchase_inquiry`）
- **附件中心**：`attachmentCenter`（预览/下载/上传；`kind=system` 系统附件不可删）
- **发布生成 PDF**：见 `features/purchase-inquiry-vendor-system-pdf.md`（有几家供应商生成几份）
- 新建默认 `DRAFT` / `review_status=DRAFT`（`purchase_inquiry_service.create_inquiry`）

## 禁止

- 不要把需方做成询价页内联临时候选而不维护主数据
- 不要另起一套付款方式/发票类型选项（与财务/采购订单共用）
