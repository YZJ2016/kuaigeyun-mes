---
title: 采购询价发布按供应商生成系统 PDF
slug: purchase-inquiry-vendor-system-pdf
status: delivered
domain: kuaizhizao-purchase
when: 改采购询价发布附件、系统询价单 PDF、附件中心 kind=system 时
keywords:
  - 采购询价
  - 系统附件
  - purchase_inquiry_vendor
  - purchase_inquiry_vendor_pdf
  - 发布询价
  - 按供应商生成
standard: publish_inquiry → purchase_inquiry_vendor_pdf → attachments kind=system
---

# 采购询价发布按供应商生成系统 PDF

## 目标

发布询价时，按受邀供应商数量生成固定版式询价单 PDF，写入本单附件中心。

## 何时读 / 禁止另起

- 何时读：询价附件自动生成、系统附件不可删、发布后上传人工附件
- 禁止：另起「文档附件」Tab；登记打印模板码 `PURCHASE_INQUIRY_PRINT`；打开附件中心时懒生成；失败静默空附件

## 标准入口

| 层 | 标准 |
|----|------|
| BE 生成 | `purchase_inquiry_vendor_pdf.generate_purchase_inquiry_vendor_attachments` |
| BE 发布 | `PurchaseInquiryService.publish_inquiry`（先生成再改状态） |
| BE 非草稿改附件 | `update_inquiry` 仅允许 `attachments`，服务端强制保留系统条目 |
| FE 附件中心 | `DocumentAttachmentCenterPane` + `isSystemDocumentAttachment` |
| FE 询价详情 | `purchase-inquiries/index.tsx` `attachmentCenter` |

## 关键文件

| 角色 | 路径 |
|------|------|
| PDF | `riveredge-backend/src/apps/kuaizhizao/services/purchase_inquiry_vendor_pdf.py` |
| 发布/更新 | `.../services/purchase_inquiry_service.py` |
| 附件中心透传 | `.../services/document_attachment_center_service.py`、`schemas/document_relation.py` |
| FE 门禁 | `DocumentAttachmentCenterPane.tsx`、`documentAttachments.ts` |

## 扩展点

1. attachments JSON：`kind=system` + `source=purchase_inquiry_vendor` + `supplier_id`
2. 版式改动只改 `build_vendor_inquiry_html`，不进打印模板

## 踩坑

- 必须先生成 PDF 再改 `QUOTING`，避免半发布
- `normalize_attachment_entry` 须透传 `kind/source/supplier_id`，否则附件中心删不掉门禁失效
- 非草稿 `update` 若整包覆盖 attachments，须服务端合并回系统条目

## 关联

- `features/purchase-inquiry-demand-party.md`
- 更新日志 `purchase-inquiry-vendor-system-pdf-r01`
