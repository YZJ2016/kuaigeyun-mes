import type { ComputationPushPreviewItem } from '../../../services/demand-computation';

export type DemandPushPreviewFilters = {
  materialName: string;
  materialGroupName: string;
  materialSpec: string;
};

export const EMPTY_DEMAND_PUSH_PREVIEW_FILTERS: DemandPushPreviewFilters = {
  materialName: '',
  materialGroupName: '',
  materialSpec: '',
};

/** Table 行身份（可重复 item_id 时仍唯一）；勾选状态真源仍是 item_id（下推 API 契约） */
export function demandPushPreviewRowKey(row: ComputationPushPreviewItem): string {
  return `${row.item_id}-${row.target_document ?? 'line'}-${row.push_line_index ?? 0}-${row.planned_receipt_date ?? ''}`;
}

export function filterDemandPushPreviewItems(
  items: ComputationPushPreviewItem[],
  filters: DemandPushPreviewFilters,
): ComputationPushPreviewItem[] {
  const nameQ = filters.materialName.trim().toLowerCase();
  const groupQ = filters.materialGroupName.trim().toLowerCase();
  const specQ = filters.materialSpec.trim().toLowerCase();
  if (!nameQ && !groupQ && !specQ) {
    return items;
  }
  return items.filter((row) => {
    if (nameQ) {
      const hay = `${row.material_code ?? ''} ${row.material_name ?? ''}`.toLowerCase();
      if (!hay.includes(nameQ)) {
        return false;
      }
    }
    if (groupQ && !(row.material_group_name ?? '').toLowerCase().includes(groupQ)) {
      return false;
    }
    if (specQ && !(row.material_spec ?? '').toLowerCase().includes(specQ)) {
      return false;
    }
    return true;
  });
}
