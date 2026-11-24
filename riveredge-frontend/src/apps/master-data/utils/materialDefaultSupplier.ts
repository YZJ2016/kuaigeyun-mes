/**
 * 物料默认采购供应商（与后端 resolve_default_supplier_id_from_material 同源）
 */

import type { Material } from '../types/material';

function positiveInt(value: unknown): number | undefined {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return Math.trunc(n);
}

export function resolveDefaultSupplierIdFromMaterial(
  material: Material | null | undefined,
): number | undefined {
  if (!material) return undefined;
  const sourceConfig = material.sourceConfig ?? (material as { source_config?: Record<string, unknown> }).source_config;
  if (sourceConfig && typeof sourceConfig === 'object') {
    const fromConfig = positiveInt(
      sourceConfig.default_supplier_id ?? (sourceConfig as { defaultSupplierId?: unknown }).defaultSupplierId,
    );
    if (fromConfig) return fromConfig;
  }
  const defaults = material.defaults ?? (material as { material_defaults?: Material['defaults'] }).material_defaults;
  const suppliers = defaults?.defaultSuppliers;
  if (Array.isArray(suppliers) && suppliers.length > 0) {
    const first = suppliers[0];
    const sid = positiveInt(first?.supplierId ?? (first as { supplier_id?: unknown }).supplier_id);
    if (sid) return sid;
  }
  return undefined;
}