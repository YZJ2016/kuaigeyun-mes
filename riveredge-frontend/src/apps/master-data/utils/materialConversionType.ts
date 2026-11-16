import type { MaterialUnit } from '../types/material';

export type MaterialConversionType = 'fixed' | 'floating';

export const CONVERSION_TYPE_FIXED: MaterialConversionType = 'fixed';
export const CONVERSION_TYPE_FLOATING: MaterialConversionType = 'floating';

export function normalizeMaterialConversionType(
  value?: string | null,
): MaterialConversionType {
  const raw = String(value ?? '').trim().toLowerCase();
  if (raw === 'floating' || raw === 'float' || raw === 'none' || raw === 'no_fixed' || raw === 'nofixed') {
    return CONVERSION_TYPE_FLOATING;
  }
  return CONVERSION_TYPE_FIXED;
}

export function getMaterialUnitConversionType(row?: MaterialUnit | null): MaterialConversionType {
  return normalizeMaterialConversionType(row?.conversionType);
}

export function isFloatingMaterialUnit(row?: MaterialUnit | null): boolean {
  return getMaterialUnitConversionType(row) === CONVERSION_TYPE_FLOATING;
}
