/** 销售订单同步字段白名单（目标字段）+ 苍穹销售订单查询别名 */

import type { SyncTargetField } from '../../../../../components/sync-from-source-modal/types';

export const SALES_ORDER_SYNC_TARGET_FIELDS: SyncTargetField[] = [
  { value: 'order_code', labelKey: 'app.kuaizhizao.salesOrder.syncField.orderCode' },
  { value: 'order_date', labelKey: 'app.kuaizhizao.salesOrder.syncField.orderDate' },
  { value: 'delivery_date', labelKey: 'app.kuaizhizao.salesOrder.syncField.deliveryDate' },
  { value: 'status', labelKey: 'app.kuaizhizao.salesOrder.syncField.status' },
  { value: 'customer_code', labelKey: 'app.kuaizhizao.salesOrder.syncField.customerCode' },
  { value: 'customer_name', labelKey: 'app.kuaizhizao.salesOrder.syncField.customerName' },
  { value: 'customer_contact', labelKey: 'app.kuaizhizao.salesOrder.syncField.customerContact' },
  { value: 'customer_phone', labelKey: 'app.kuaizhizao.salesOrder.syncField.customerPhone' },
  { value: 'total_amount', labelKey: 'app.kuaizhizao.salesOrder.syncField.totalAmount' },
  { value: 'total_quantity', labelKey: 'app.kuaizhizao.salesOrder.syncField.totalQuantity' },
  { value: 'salesman_name', labelKey: 'app.kuaizhizao.salesOrder.syncField.salesmanName' },
  { value: 'notes', labelKey: 'app.kuaizhizao.salesOrder.syncField.notes' },
  { value: 'shipping_address', labelKey: 'app.kuaizhizao.salesOrder.syncField.shippingAddress' },
  { value: 'payment_method_code', labelKey: 'app.kuaizhizao.salesOrder.syncField.paymentMethod' },
  { value: 'settlement_terms_code', labelKey: 'app.kuaizhizao.salesOrder.syncField.settlementTerms' },
  { value: 'payment_terms_days', labelKey: 'app.kuaizhizao.salesOrder.syncField.paymentCycle' },
  { value: 'item.material_code', labelKey: 'app.kuaizhizao.salesOrder.syncField.itemMaterialCode' },
  { value: 'item.material_name', labelKey: 'app.kuaizhizao.salesOrder.syncField.itemMaterialName' },
  { value: 'item.material_spec', labelKey: 'app.kuaizhizao.salesOrder.syncField.itemMaterialSpec' },
  { value: 'item.material_unit', labelKey: 'app.kuaizhizao.salesOrder.syncField.itemMaterialUnit' },
  { value: 'item.required_quantity', labelKey: 'app.kuaizhizao.salesOrder.syncField.itemRequiredQuantity' },
  { value: 'item.delivery_date', labelKey: 'app.kuaizhizao.salesOrder.syncField.itemDeliveryDate' },
  { value: 'item.unit_price', labelKey: 'app.kuaizhizao.salesOrder.syncField.itemUnitPrice' },
  { value: 'item.tax_rate', labelKey: 'app.kuaizhizao.salesOrder.syncField.itemTaxRate' },
  { value: 'item.notes', labelKey: 'app.kuaizhizao.salesOrder.syncField.itemNotes' },
];

/**
 * 苍穹销售订单查询 sm_salorder/query（预置 sm_query）→ 本系统目标字段别名。
 * 真源：`docs/销售订单.md` 返回参数 + 示例 JSON。
 *
 * 响应里 billentry[] 分录字段本身已是扁平名（如 taxrateid_number）；
 * 前端 expandNestedDetailRows 再拼前缀 → 预览列实际为 billentrytaxrateid_number。
 * 别名同时保留「文档点分写法 / 摊平列名 / 分录裸字段名」。
 */
export const SALES_ORDER_SYNC_TARGET_ALIASES: Record<string, string[]> = {
  order_code: ['billno'],
  order_date: ['bizdate'],
  // 苍穹表头无交期；禁止再映 bizdate（会与 order_date 抢同一列，保存后订单日期丢失）。
  // 表头交期未映射时后端用 order_date；行交期用 item.delivery_date。
  delivery_date: [],
  // 单据状态 A暂存/B已提交/C已审核 → 本系统 status + review_status
  status: ['billstatus', 'FDocumentStatus'],
  // 客户比对只用编码（customer_code）；不提供 customer_id 映射目标
  customer_code: ['customer_number'],
  customer_name: ['customer_name'],
  customer_contact: ['linkman_contactperson'],
  customer_phone: ['linkman_phone'],
  // 价税合计；勿把 totalamount（未税金额）当首选
  total_amount: ['totalallamount'],
  // 官方返回无表头总数量字段（无 totalqty），无法自动匹配
  total_quantity: [],
  salesman_name: ['operator_operatorname'],
  notes: ['comment'],
  shipping_address: ['receiveaddress'],
  // 付款方式 CREDIT/CASH（文档 paymode）— 目标字段是 payment_method_code
  payment_method_code: ['paymode'],
  // 结算方式.编码；收款条件无「账期天数」字段，payment_terms_days 不自动匹配
  settlement_terms_code: ['settletype_number'],
  payment_terms_days: [],
  'item.material_code': [
    'billentrymaterial_masterid_number',
    'billentry.material_masterid_number',
    'material_masterid_number',
  ],
  'item.material_name': [
    'billentrymaterial_masterid_name',
    'billentry.material_masterid_name',
    'material_masterid_name',
  ],
  'item.material_spec': [
    'billentrymaterial_masterid_modelnum',
    'billentry.material_masterid_modelnum',
    'material_masterid_modelnum',
  ],
  'item.material_unit': [
    'billentryunit_number',
    'billentry.unit_number',
    'unit_number',
    'billentryunit_name',
    'billentry.unit_name',
    'unit_name',
  ],
  'item.required_quantity': ['billentryqty', 'billentry.qty', 'qty'],
  'item.delivery_date': ['billentrydeliverydate', 'billentry.deliverydate', 'deliverydate'],
  'item.unit_price': ['billentrypriceandtax', 'billentry.priceandtax', 'priceandtax'],
  // 税率.编码；摊平列 = billentry + taxrateid_number
  'item.tax_rate': [
    'billentrytaxrateid_number',
    'billentry.taxrateid_number',
    'taxrateid_number',
  ],
  // 官方 sm_salorder/query 分录无行备注/entrycomment 字段，无法自动匹配
  'item.notes': [],
};

// 交货日期非强制：苍穹无表头交期；有明细交期或后端用订单日期即可
export const SALES_ORDER_SYNC_REQUIRED_TARGETS = ['order_code', 'order_date'];
export const SALES_ORDER_SYNC_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_sales_orders';
export const SALES_ORDER_SYNC_MAPPING_EXPORT_FILENAME = 'sales-order-sync-field-mapping.json';