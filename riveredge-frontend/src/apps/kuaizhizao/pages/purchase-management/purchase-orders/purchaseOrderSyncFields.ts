/** 采购订单同步字段白名单（目标字段）+ 金蝶采购订单常见别名 */

import type { SyncTargetField } from '../../../../../components/sync-from-source-modal/types';

/** 主表默认展示：建单与价税必要字段 */
export const PURCHASE_ORDER_SYNC_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'order_code', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.orderCode', required: true },
  { value: 'order_date', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.orderDate', required: true },
  { value: 'delivery_date', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.deliveryDate' },
  { value: 'supplier_code', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.supplierCode', required: true },
  { value: 'supplier_name', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.supplierName' },
  { value: 'notes', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.notes' },
  { value: 'item.material_code', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.itemMaterialCode', required: true },
  { value: 'item.material_name', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.itemMaterialName' },
  { value: 'item.ordered_quantity', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.itemOrderedQuantity', required: true },
  { value: 'item.unit_price', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.itemUnitPriceExcl' },
  { value: 'item.display_unit_price', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.itemUnitPriceIncl' },
  { value: 'item.tax_rate', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.itemTaxRate' },
  { value: 'item.delivery_date', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.itemDeliveryDate' },
];

/** 「追加字段」下拉：非必要系统字段，用户按需添加 */
export const PURCHASE_ORDER_SYNC_AVAILABLE_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'supplier_contact', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.supplierContact' },
  { value: 'supplier_phone', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.supplierPhone' },
  { value: 'buyer_name', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.buyerName' },
  { value: 'price_type', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.priceType' },
  { value: 'tax_rate', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.taxRate' },
  { value: 'payment_method_code', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.paymentMethod' },
  { value: 'settlement_terms_code', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.settlementTerms' },
  { value: 'payment_terms_days', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.paymentCycle' },
  { value: 'item.material_spec', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.itemMaterialSpec' },
  { value: 'item.material_unit', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.itemMaterialUnit' },
  { value: 'item.notes', labelKey: 'app.kuaizhizao.purchaseOrder.syncField.itemNotes' },
];

/**
 * 金蝶星空采购订单常见字段 → 本系统目标。
 * 含税请映 FTaxPrice → item.display_unit_price；未税映 FPrice → item.unit_price。
 */
export const PURCHASE_ORDER_SYNC_TARGET_ALIASES: Record<string, string[]> = {
  order_code: ['FBillNo', 'BillNo', 'billno'],
  order_date: ['FDate', 'Date', 'bizdate'],
  delivery_date: ['FDeliveryDate', 'DeliveryDate'],
  supplier_code: ['FSupplierId.FNumber', 'FSupplierIdFNumber', 'FSupplierId.Number'],
  supplier_name: ['FSupplierId.FName', 'FSupplierIdFName', 'FSupplierId.Name'],
  supplier_contact: ['FProviderContact', 'FContact'],
  supplier_phone: ['FProviderPhone', 'FPhone'],
  buyer_name: ['FPurchaserId.FName', 'FPurchaserIdFName', 'FBuyerName'],
  price_type: ['FIsIncludedTax', 'FPriceType'],
  tax_rate: ['FTaxRate', 'FHeadTaxRate'],
  notes: ['FNote', 'FRemarks', 'comment'],
  'item.material_code': [
    'FMaterialId.FNumber',
    'FMaterialIdFNumber',
    'FEntityFMaterialId.FNumber',
    'FEntityFMaterialIdFNumber',
  ],
  'item.material_name': [
    'FMaterialId.FName',
    'FMaterialIdFName',
    'FEntityFMaterialId.FName',
    'FEntityFMaterialIdFName',
  ],
  'item.material_spec': [
    'FMaterialId.FSpecification',
    'FMaterialIdFSpecification',
    'FEntityFMaterialId.FSpecification',
  ],
  'item.material_unit': ['FUnitId.FName', 'FUnitIdFName', 'FUnitId.FNumber', 'FEntityFUnitId.FName'],
  'item.ordered_quantity': ['FQty', 'FEntityFQty', 'Qty'],
  'item.unit_price': ['FPrice', 'FEntityFPrice', 'Price'],
  'item.display_unit_price': ['FTaxPrice', 'FEntityFTaxPrice', 'TaxPrice', 'FPriceIncludingTax'],
  // 行税率勿与表头 FTaxRate 混用，避免自动建议串列
  'item.tax_rate': ['FEntryTaxRate', 'FEntityFEntryTaxRate', 'EntryTaxRate'],
  'item.delivery_date': ['FDeliveryDate', 'FEntityFDeliveryDate', 'FRequireDate'],
  'item.notes': ['FEntryNote', 'FEntityFNote', 'FNote'],
};

export const PURCHASE_ORDER_SYNC_REQUIRED_TARGETS = ['order_code', 'order_date', 'supplier_code'];
export const PURCHASE_ORDER_SYNC_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_purchase_orders';
export const PURCHASE_ORDER_SYNC_MAPPING_EXPORT_FILENAME = 'purchase-order-sync-field-mapping.json';
