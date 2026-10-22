---
title: 单据行伙伴料号与型号规格快照
keywords: partner_material_code, material_model, document_line_material_snapshot, MaterialCodeAlias, materialLineColumns
when: 改销售/采购/成品入库明细列、下推复制行、编号映射与单据行对齐
---

## 标准入口

- BE 写路径：`apps/kuaizhizao/utils/document_line_material_snapshot.py`（`enrich_line_dicts_with_partner_snapshots`、`partner_snapshot_fields_from_source_line`）
- 别名解析：`MaterialCodeService.get_partner_material_alias` / `resolve_line_partner_material_snapshots`
- 行字段 Mixin：`apps/kuaizhizao/models/mixins/document_line_partner_material.py`
- FE 列工厂：`materialLineColumns.tsx`（**规格 → 型号**紧跟物料；`buildPartnerMaterialLineColumns` 排在备注前）
- 明细表行内空值占位：`documentDetailTable.tsx` 的 `DocumentDetailLineTextInput` / `DocumentDetailLineReadonlyTextInput`（统一 `—`，禁止规格列用列标题当 placeholder）
- Form 明细列/选料：`materialLineFormDetail.tsx`（`withMaterialLineFillMapping`、`buildDocumentDetailSpecModelFormColumns`、`buildDocumentDetailPartnerMaterialFormColumns`）；`UniMaterialSelect` 缺规格/型号时自动 resolve 补全
- 销售选料价：`applySalesDocumentLineMaterialPricing` 从客户价本 resolve 回填 `partner_material_*`（无价目时仍可有编号映射）
- 报价单 Form/详情明细须挂伙伴列（与销售订单一致，备注前）
- 销售合同/预测/发货/退货、采购订单/申请/退货 Form + 列表明细视图/抽屉须挂 `buildDocumentDetailPartnerMaterialFormColumns` / `buildPartnerMaterialLineColumns`；销售合同保存走 `_persist_contract_items` enrich
- 采购选料：`applyPurchaseDocumentLineMaterialPricing` 回填 `partner_material_*`；批量价本 `resolvePurchaseDocumentMaterialLinesPricing` / `resolveSalesDocumentMaterialLinesPricing` 含伙伴字段
- 明细 rank：`GLOBAL_DOC_DETAIL_TABLE_FIELD_RANK` 中 `material_spec`（20.72）→ `material_model`（20.74）；列表 `material_spec` / `material_model` 在 `GLOBAL_DOC_LIST_FIELD_RANK`

## 规则

- 销售头 `customer_id` → CUSTOMER 映射；采购头 `supplier_id` → SUPPLIER；成品入库经 `sales_order_id` 解析客户
- 下推优先 `partner_snapshot_fields_from_source_line` 复制源行快照
- 禁止前端读侧 JOIN 映射冒充行数据

## 迁移

- `905_20261021170000_document_line_partner_material_snapshot.py`
- `910_20261021234000_purchase_receipt_item_spec_model_backfill.py`（采购入库历史行规格/型号回填）

## 采购入库

- 写路径：`create_purchase_receipt` / `update_purchase_receipt` 须 `enrich_line_dicts_with_partner_snapshots`（`partner_type=supplier`）
- 响应：`_build_purchase_receipt_item_response` 须含 `material_model` / `partner_material_*`
- Schema：`PurchaseReceiptItemBase` 与成品入库明细对齐含型号与伙伴字段
- 禁止仅靠前端 `enrichInboundItemsMaterialSpecModel` 冒充行快照
