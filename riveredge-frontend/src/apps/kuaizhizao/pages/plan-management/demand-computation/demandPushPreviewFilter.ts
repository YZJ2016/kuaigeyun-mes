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
