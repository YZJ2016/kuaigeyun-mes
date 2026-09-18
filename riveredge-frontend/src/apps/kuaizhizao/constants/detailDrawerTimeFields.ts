/**
 * 快制造详情抽屉时间字段目录（timeconfig 页与抽屉过滤的唯一清单）。
 * key = `{documentType}.{dataIndex}`；通用字段 documentType 为 common。
 */

export type DetailDrawerTimeField = {
  key: string;
  documentType: string;
  dataIndex: string;
  labelKey: string;
};

export type DetailDrawerTimeGroup = {
  documentType: string;
  titleKey: string;
  fields: DetailDrawerTimeField[];
};

function field(documentType: string, dataIndex: string): DetailDrawerTimeField {
  return {
    key: `${documentType}.${dataIndex}`,
    documentType,
    dataIndex,
    labelKey: `app.kuaizhizao.timeconfig.field.${documentType}.${dataIndex}`,
  };
}

export const DETAIL_DRAWER_TIME_GROUPS: DetailDrawerTimeGroup[] = [
  {
    documentType: 'common',
    titleKey: 'app.kuaizhizao.timeconfig.group.common',
    fields: [field('common', 'created_at')],
  },
  {
    documentType: 'sales_order',
    titleKey: 'app.kuaizhizao.timeconfig.group.sales_order',
    fields: [
      field('sales_order', 'order_date'),
      field('sales_order', 'delivery_date'),
    ],
  },
  {
    documentType: 'quotation',
    titleKey: 'app.kuaizhizao.timeconfig.group.quotation',
    fields: [
      field('quotation', 'quotation_date'),
      field('quotation', 'delivery_date'),
      field('quotation', 'valid_until'),
    ],
  },
  {
    documentType: 'sales_contract',
    titleKey: 'app.kuaizhizao.timeconfig.group.sales_contract',
    fields: [
      field('sales_contract', 'contract_date'),
      field('sales_contract', 'valid_from'),
      field('sales_contract', 'valid_to'),
    ],
  },
  {
    documentType: 'sales_forecast',
    titleKey: 'app.kuaizhizao.timeconfig.group.sales_forecast',
    fields: [
      field('sales_forecast', 'start_date'),
      field('sales_forecast', 'end_date'),
    ],
  },
  {
    documentType: 'sales_order_change',
    titleKey: 'app.kuaizhizao.timeconfig.group.sales_order_change',
    fields: [field('sales_order_change', 'applied_at')],
  },
  {
    documentType: 'sales_return',
    titleKey: 'app.kuaizhizao.timeconfig.group.sales_return',
    fields: [field('sales_return', 'return_time')],
  },
  {
    documentType: 'sales_review',
    titleKey: 'app.kuaizhizao.timeconfig.group.sales_review',
    fields: [
      field('sales_review', 'review_date'),
      field('sales_review', 'delivery_date'),
    ],
  },
  {
    documentType: 'shipment_notice',
    titleKey: 'app.kuaizhizao.timeconfig.group.shipment_notice',
    fields: [
      field('shipment_notice', 'planned_ship_date'),
      field('shipment_notice', 'notified_at'),
    ],
  },
  {
    documentType: 'customer_follow_up',
    titleKey: 'app.kuaizhizao.timeconfig.group.customer_follow_up',
    fields: [
      field('customer_follow_up', 'occurred_at'),
      field('customer_follow_up', 'next_follow_up_at'),
    ],
  },
  {
    documentType: 'purchase_order',
    titleKey: 'app.kuaizhizao.timeconfig.group.purchase_order',
    fields: [
      field('purchase_order', 'order_date'),
      field('purchase_order', 'delivery_date'),
    ],
  },
  {
    documentType: 'purchase_requisition',
    titleKey: 'app.kuaizhizao.timeconfig.group.purchase_requisition',
    fields: [
      field('purchase_requisition', 'requisition_date'),
      field('purchase_requisition', 'required_date'),
    ],
  },
  {
    documentType: 'purchase_inquiry',
    titleKey: 'app.kuaizhizao.timeconfig.group.purchase_inquiry',
    fields: [
      field('purchase_inquiry', 'inquiry_date'),
      field('purchase_inquiry', 'quote_deadline'),
    ],
  },
  {
    documentType: 'purchase_order_change',
    titleKey: 'app.kuaizhizao.timeconfig.group.purchase_order_change',
    fields: [field('purchase_order_change', 'applied_at')],
  },
  {
    documentType: 'purchase_return',
    titleKey: 'app.kuaizhizao.timeconfig.group.purchase_return',
    fields: [
      field('purchase_return', 'return_time'),
      field('purchase_return', 'review_time'),
    ],
  },
  {
    documentType: 'receipt_notice',
    titleKey: 'app.kuaizhizao.timeconfig.group.receipt_notice',
    fields: [
      field('receipt_notice', 'notified_at'),
      field('receipt_notice', 'planned_receipt_date'),
    ],
  },
  {
    documentType: 'work_order',
    titleKey: 'app.kuaizhizao.timeconfig.group.work_order',
    fields: [
      field('work_order', 'planned_start_date'),
      field('work_order', 'planned_end_date'),
      field('work_order', 'actual_start_date'),
      field('work_order', 'actual_end_date'),
    ],
  },
  {
    documentType: 'rework_order',
    titleKey: 'app.kuaizhizao.timeconfig.group.rework_order',
    fields: [
      field('rework_order', 'planned_start_date'),
      field('rework_order', 'planned_end_date'),
      field('rework_order', 'actual_start_date'),
      field('rework_order', 'actual_end_date'),
    ],
  },
  {
    documentType: 'outsource_order',
    titleKey: 'app.kuaizhizao.timeconfig.group.outsource_order',
    fields: [
      field('outsource_order', 'planned_start_date'),
      field('outsource_order', 'planned_end_date'),
      field('outsource_order', 'actual_start_date'),
      field('outsource_order', 'actual_end_date'),
    ],
  },
  {
    documentType: 'outsource_work_order',
    titleKey: 'app.kuaizhizao.timeconfig.group.outsource_work_order',
    fields: [
      field('outsource_work_order', 'planned_start_date'),
      field('outsource_work_order', 'planned_end_date'),
      field('outsource_work_order', 'actual_start_date'),
      field('outsource_work_order', 'actual_end_date'),
    ],
  },
  {
    documentType: 'reporting',
    titleKey: 'app.kuaizhizao.timeconfig.group.reporting',
    fields: [
      field('reporting', 'work_start_time'),
      field('reporting', 'work_end_time'),
      field('reporting', 'reported_at'),
      field('reporting', 'approved_at'),
    ],
  },
  {
    documentType: 'inbound',
    titleKey: 'app.kuaizhizao.timeconfig.group.inbound',
    fields: [field('inbound', 'receipt_date')],
  },
  {
    documentType: 'other_inbound',
    titleKey: 'app.kuaizhizao.timeconfig.group.other_inbound',
    fields: [field('other_inbound', 'receipt_time')],
  },
  {
    documentType: 'outbound',
    titleKey: 'app.kuaizhizao.timeconfig.group.outbound',
    fields: [field('outbound', 'delivery_date')],
  },
  {
    documentType: 'other_outbound',
    titleKey: 'app.kuaizhizao.timeconfig.group.other_outbound',
    fields: [field('other_outbound', 'delivery_time')],
  },
  {
    documentType: 'delivery_note',
    titleKey: 'app.kuaizhizao.timeconfig.group.delivery_note',
    fields: [
      field('delivery_note', 'planned_delivery_date'),
      field('delivery_note', 'sent_at'),
    ],
  },
  {
    documentType: 'inventory_transfer',
    titleKey: 'app.kuaizhizao.timeconfig.group.inventory_transfer',
    fields: [field('inventory_transfer', 'transfer_date')],
  },
  {
    documentType: 'material_borrow',
    titleKey: 'app.kuaizhizao.timeconfig.group.material_borrow',
    fields: [
      field('material_borrow', 'borrow_time'),
      field('material_borrow', 'expected_return_date'),
    ],
  },
  {
    documentType: 'material_return',
    titleKey: 'app.kuaizhizao.timeconfig.group.material_return',
    fields: [field('material_return', 'return_time')],
  },
  {
    documentType: 'stocktaking',
    titleKey: 'app.kuaizhizao.timeconfig.group.stocktaking',
    fields: [field('stocktaking', 'stocktaking_date')],
  },
  {
    documentType: 'customer_material_registration',
    titleKey: 'app.kuaizhizao.timeconfig.group.customer_material_registration',
    fields: [
      field('customer_material_registration', 'registration_date'),
      field('customer_material_registration', 'processed_at'),
    ],
  },
  {
    documentType: 'inventory_alert',
    titleKey: 'app.kuaizhizao.timeconfig.group.inventory_alert',
    fields: [
      field('inventory_alert', 'triggered_at'),
      field('inventory_alert', 'handled_at'),
    ],
  },
  {
    documentType: 'replenishment_suggestion',
    titleKey: 'app.kuaizhizao.timeconfig.group.replenishment_suggestion',
    fields: [field('replenishment_suggestion', 'suggested_order_date')],
  },
  {
    documentType: 'assembly_disassembly',
    titleKey: 'app.kuaizhizao.timeconfig.group.assembly_disassembly',
    fields: [field('assembly_disassembly', 'executed_at')],
  },
  {
    documentType: 'packing_binding',
    titleKey: 'app.kuaizhizao.timeconfig.group.packing_binding',
    fields: [field('packing_binding', 'bound_at')],
  },
  {
    documentType: 'exception_process',
    titleKey: 'app.kuaizhizao.timeconfig.group.exception_process',
    fields: [
      field('exception_process', 'assigned_at'),
      field('exception_process', 'started_at'),
      field('exception_process', 'completed_at'),
    ],
  },
  {
    documentType: 'quality_inspection',
    titleKey: 'app.kuaizhizao.timeconfig.group.quality_inspection',
    fields: [
      field('quality_inspection', 'inspection_time'),
      field('quality_inspection', 'review_time'),
    ],
  },
  {
    documentType: 'freight_order',
    titleKey: 'app.kuaizhizao.timeconfig.group.freight_order',
    fields: [
      field('freight_order', 'planned_depart_at'),
      field('freight_order', 'planned_arrive_at'),
      field('freight_order', 'actual_depart_at'),
      field('freight_order', 'actual_arrive_at'),
    ],
  },
  {
    documentType: 'freight_bill',
    titleKey: 'app.kuaizhizao.timeconfig.group.freight_bill',
    fields: [field('freight_bill', 'reviewed_at')],
  },
  {
    documentType: 'after_sales_ticket',
    titleKey: 'app.kuaizhizao.timeconfig.group.after_sales_ticket',
    fields: [
      field('after_sales_ticket', 'registered_at'),
      field('after_sales_ticket', 'closed_at'),
    ],
  },
  {
    documentType: 'dispatch_order',
    titleKey: 'app.kuaizhizao.timeconfig.group.dispatch_order',
    fields: [
      field('dispatch_order', 'planned_start_at'),
      field('dispatch_order', 'planned_end_at'),
      field('dispatch_order', 'actual_start_at'),
      field('dispatch_order', 'actual_end_at'),
      field('dispatch_order', 'checkin_at'),
    ],
  },
  {
    documentType: 'install_execution',
    titleKey: 'app.kuaizhizao.timeconfig.group.install_execution',
    fields: [field('install_execution', 'started_at')],
  },
  {
    documentType: 'repair_order',
    titleKey: 'app.kuaizhizao.timeconfig.group.repair_order',
    fields: [
      field('repair_order', 'reported_at'),
      field('repair_order', 'closed_at'),
    ],
  },
  {
    documentType: 'service_asset',
    titleKey: 'app.kuaizhizao.timeconfig.group.service_asset',
    fields: [
      field('service_asset', 'accepted_at'),
      field('service_asset', 'warranty_start_at'),
      field('service_asset', 'warranty_end_at'),
    ],
  },
  {
    documentType: 'spare_part_requisition',
    titleKey: 'app.kuaizhizao.timeconfig.group.spare_part_requisition',
    fields: [
      field('spare_part_requisition', 'reviewed_at'),
      field('spare_part_requisition', 'created_at'),
    ],
  },
  {
    documentType: 'customer_return_visit',
    titleKey: 'app.kuaizhizao.timeconfig.group.customer_return_visit',
    fields: [field('customer_return_visit', 'visited_at')],
  },
  {
    documentType: 'service_settlement',
    titleKey: 'app.kuaizhizao.timeconfig.group.service_settlement',
    fields: [field('service_settlement', 'reviewed_at')],
  },
  {
    documentType: 'eight_d',
    titleKey: 'app.kuaizhizao.timeconfig.group.eight_d',
    fields: [field('eight_d', 'due_date')],
  },
  {
    documentType: 'demand',
    titleKey: 'app.kuaizhizao.timeconfig.group.demand',
    fields: [
      field('demand', 'start_date'),
      field('demand', 'end_date'),
      field('demand', 'order_date'),
      field('demand', 'delivery_date'),
    ],
  },
  {
    documentType: 'demand_computation',
    titleKey: 'app.kuaizhizao.timeconfig.group.demand_computation',
    fields: [
      field('demand_computation', 'computation_start_time'),
      field('demand_computation', 'computation_end_time'),
      field('demand_computation', 'delivery_date'),
      field('demand_computation', 'planned_start'),
    ],
  },
  {
    documentType: 'equipment',
    titleKey: 'app.kuaizhizao.timeconfig.group.equipment',
    fields: [
      field('equipment', 'created_at'),
      field('equipment', 'updated_at'),
    ],
  },
  {
    documentType: 'equipment_fault',
    titleKey: 'app.kuaizhizao.timeconfig.group.equipment_fault',
    fields: [field('equipment_fault', 'fault_date'), field('equipment_fault', 'created_at')],
  },
  {
    documentType: 'maintenance_plan',
    titleKey: 'app.kuaizhizao.timeconfig.group.maintenance_plan',
    fields: [
      field('maintenance_plan', 'planned_start_date'),
      field('maintenance_plan', 'planned_end_date'),
      field('maintenance_plan', 'created_at'),
    ],
  },
  {
    documentType: 'maintenance_execution',
    titleKey: 'app.kuaizhizao.timeconfig.group.maintenance_execution',
    fields: [
      field('maintenance_execution', 'execution_date'),
      field('maintenance_execution', 'created_at'),
    ],
  },
  {
    documentType: 'maintenance_reminder',
    titleKey: 'app.kuaizhizao.timeconfig.group.maintenance_reminder',
    fields: [field('maintenance_reminder', 'due_date')],
  },
  {
    documentType: 'equipment_repair',
    titleKey: 'app.kuaizhizao.timeconfig.group.equipment_repair',
    fields: [field('equipment_repair', 'repair_date'), field('equipment_repair', 'created_at')],
  },
  {
    documentType: 'equipment_calibration',
    titleKey: 'app.kuaizhizao.timeconfig.group.equipment_calibration',
    fields: [
      field('equipment_calibration', 'calibration_date'),
      field('equipment_calibration', 'expiry_date'),
    ],
  },
  {
    documentType: 'mold_calibration',
    titleKey: 'app.kuaizhizao.timeconfig.group.mold_calibration',
    fields: [
      field('mold_calibration', 'calibration_date'),
      field('mold_calibration', 'expiry_date'),
    ],
  },
  {
    documentType: 'tool_calibration',
    titleKey: 'app.kuaizhizao.timeconfig.group.tool_calibration',
    fields: [
      field('tool_calibration', 'calibration_date'),
      field('tool_calibration', 'expiry_date'),
    ],
  },
  {
    documentType: 'equipment_spot_check',
    titleKey: 'app.kuaizhizao.timeconfig.group.equipment_spot_check',
    fields: [field('equipment_spot_check', 'created_at')],
  },
  {
    documentType: 'equipment_route_patrol',
    titleKey: 'app.kuaizhizao.timeconfig.group.equipment_route_patrol',
    fields: [field('equipment_route_patrol', 'created_at')],
  },
  {
    documentType: 'equipment_scrap',
    titleKey: 'app.kuaizhizao.timeconfig.group.equipment_scrap',
    fields: [field('equipment_scrap', 'created_at')],
  },
  {
    documentType: 'bom',
    titleKey: 'app.kuaizhizao.timeconfig.group.bom',
    fields: [
      field('bom', 'approved_at'),
      field('bom', 'created_at'),
      field('bom', 'updated_at'),
    ],
  },
  {
    documentType: 'defect_type',
    titleKey: 'app.kuaizhizao.timeconfig.group.defect_type',
    fields: [field('defect_type', 'created_at'), field('defect_type', 'updated_at')],
  },
  {
    documentType: 'operation',
    titleKey: 'app.kuaizhizao.timeconfig.group.operation',
    fields: [field('operation', 'created_at'), field('operation', 'updated_at')],
  },
  {
    documentType: 'process_route',
    titleKey: 'app.kuaizhizao.timeconfig.group.process_route',
    fields: [field('process_route', 'created_at'), field('process_route', 'updated_at')],
  },
  {
    documentType: 'customer',
    titleKey: 'app.kuaizhizao.timeconfig.group.customer',
    fields: [field('customer', 'created_at'), field('customer', 'updated_at')],
  },
  {
    documentType: 'supplier',
    titleKey: 'app.kuaizhizao.timeconfig.group.supplier',
    fields: [field('supplier', 'created_at'), field('supplier', 'updated_at')],
  },
  {
    documentType: 'warehouse',
    titleKey: 'app.kuaizhizao.timeconfig.group.warehouse',
    fields: [field('warehouse', 'created_at'), field('warehouse', 'updated_at')],
  },
  {
    documentType: 'warehouse_doc',
    titleKey: 'app.kuaizhizao.timeconfig.group.warehouse_doc',
    fields: [field('warehouse_doc', 'created_at'), field('warehouse_doc', 'updated_at')],
  },
  {
    documentType: 'finance_receipt',
    titleKey: 'app.kuaizhizao.timeconfig.group.finance_receipt',
    fields: [
      field('finance_receipt', 'receipt_date'),
      field('finance_receipt', 'created_at'),
    ],
  },
  {
    documentType: 'finance_payment',
    titleKey: 'app.kuaizhizao.timeconfig.group.finance_payment',
    fields: [
      field('finance_payment', 'payment_date'),
      field('finance_payment', 'created_at'),
    ],
  },
  {
    documentType: 'payable',
    titleKey: 'app.kuaizhizao.timeconfig.group.payable',
    fields: [field('payable', '__operation_log__')],
  },
  {
    documentType: 'nonconforming_ledger',
    titleKey: 'app.kuaizhizao.timeconfig.group.nonconforming_ledger',
    fields: [field('nonconforming_ledger', 'created_at'), field('nonconforming_ledger', 'updated_at')],
  },
];

/** 仓储类单据详情：可统一用 warehouse_doc 组的创建/更新时间开关 */
export const WAREHOUSE_DETAIL_DOCUMENT_TYPES = new Set([
  'inbound',
  'other_inbound',
  'outbound',
  'other_outbound',
  'delivery_note',
  'inventory_transfer',
  'material_borrow',
  'material_return',
  'stocktaking',
  'customer_material_registration',
  'inventory_alert',
  'replenishment_suggestion',
  'assembly_disassembly',
  'packing_binding',
  'warehouse_doc',
]);

const CATALOG_KEYS = new Set(DETAIL_DRAWER_TIME_GROUPS.flatMap((g) => g.fields.map((f) => f.key)));

export function isCataloguedTimeFieldKey(key: string): boolean {
  return CATALOG_KEYS.has(key);
}

export function resolveColumnDataIndex(col: { dataIndex?: unknown; key?: unknown }): string {
  const di = col.dataIndex;
  if (typeof di === 'string') return di;
  if (Array.isArray(di) && di.length) return String(di[di.length - 1]);
  return col.key != null ? String(col.key) : '';
}

export function isUpdatedAtFieldKey(fieldKey: string): boolean {
  return fieldKey === 'updated_at' || fieldKey === 'updatedAt';
}

export function isCreatedAtFieldKey(fieldKey: string): boolean {
  return fieldKey === 'created_at' || fieldKey === 'createdAt';
}

/** 列 dataIndex 与 timeconfig 目录 key 对齐（camelCase ↔ snake_case） */
export function normalizeDetailTimeFieldKey(fieldKey: string): string {
  if (fieldKey === 'createdAt') return 'created_at';
  if (fieldKey === 'updatedAt') return 'updated_at';
  if (fieldKey === 'approvedAt') return 'approved_at';
  return fieldKey;
}

function isHiddenByDocumentField(
  documentType: string,
  fieldKey: string,
  hiddenMap: Record<string, boolean>,
): boolean {
  const normalized = normalizeDetailTimeFieldKey(fieldKey);
  const candidates = normalized === fieldKey ? [fieldKey] : [fieldKey, normalized];
  for (const fk of candidates) {
    if (hiddenMap[`${documentType}.${fk}`] === true) return true;
  }
  if (
    WAREHOUSE_DETAIL_DOCUMENT_TYPES.has(documentType) &&
    (hiddenMap[`warehouse_doc.${normalized}`] === true ||
      hiddenMap[`warehouse_doc.${fieldKey}`] === true)
  ) {
    return true;
  }
  return false;
}

/** hiddenMap: key -> true 表示隐藏。updated_at 走独立开关。 */
export function isDetailTimeFieldHidden(
  fieldKey: string,
  documentType: string | undefined,
  hiddenMap: Record<string, boolean>,
  showUpdatedAt: boolean,
): boolean {
  if (!fieldKey) return false;
  if (fieldKey === '__operation_log__') return false;
  if (isUpdatedAtFieldKey(fieldKey) && !showUpdatedAt) return true;
  if (isCreatedAtFieldKey(fieldKey) && hiddenMap['common.created_at'] === true) return true;
  if (documentType && isHiddenByDocumentField(documentType, fieldKey, hiddenMap)) return true;
  return false;
}

/** 单据级操作记录：payable.__operation_log__ 等 */
export function isDetailOperationLogEnabledForDocument(
  documentType: string | undefined,
  hiddenMap: Record<string, boolean>,
  globalEnabled: boolean,
): boolean {
  if (!globalEnabled) return false;
  if (documentType && hiddenMap[`${documentType}.__operation_log__`] === true) return false;
  return true;
}

/** 表格列：按 timeconfig 过滤创建时间等列 */
export function filterTableColumnsByDetailTime<T extends { dataIndex?: unknown; key?: unknown }>(
  columns: T[],
  documentType: string | undefined,
  hiddenMap: Record<string, boolean>,
  showUpdatedAt: boolean,
): T[] {
  return columns.filter((col) => {
    const fieldKey = resolveColumnDataIndex(col);
    return !isDetailTimeFieldHidden(fieldKey, documentType, hiddenMap, showUpdatedAt);
  });
}
