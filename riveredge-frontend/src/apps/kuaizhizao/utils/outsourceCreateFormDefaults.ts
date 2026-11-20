import { coerceFormDate } from '../../../utils/formDate';

/** 从工单工序带入新建委外单的预填字段（仅在有值时写入） */
export type OutsourceOperationFormPrefill = {
  work_order_operation_id: number;
  outsourceable_quantity?: number;
  default_outsource_supplier_id?: number | null;
  planned_start_date?: string | null;
  planned_end_date?: string | null;
};

export function buildOutsourceCreateFormDefaults(
  operation: OutsourceOperationFormPrefill,
  supplierList?: Array<{ id: number }>,
): Record<string, unknown> {
  const patch: Record<string, unknown> = {
    work_order_operation_id: operation.work_order_operation_id,
  };

  const qty = Number(operation.outsourceable_quantity ?? 0);
  if (qty > 0) {
    patch.outsource_quantity = qty;
  }

  const supplierId =
    operation.default_outsource_supplier_id != null
      ? Number(operation.default_outsource_supplier_id)
      : null;
  if (supplierId != null && Number.isFinite(supplierId) && supplierId > 0) {
    if (!supplierList || supplierList.some((s) => Number(s.id) === supplierId)) {
      patch.supplier_id = supplierId;
    }
  }

  const plannedStart = coerceFormDate(operation.planned_start_date);
  if (plannedStart) {
    patch.planned_start_date = plannedStart;
  }
  const plannedEnd = coerceFormDate(operation.planned_end_date);
  if (plannedEnd) {
    patch.planned_end_date = plannedEnd;
  }

  return patch;
}