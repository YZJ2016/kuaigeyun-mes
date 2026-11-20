import type { Material } from '../types/material';

/** 与后端 resolve_primary_default_warehouse_from_material 及物料 defaults 写入格式一致 */
export function resolvePrimaryDefaultWarehouseId(material?: Material | null): number | undefined {
  return resolvePrimaryDefaultWarehouseFromMaterial(material)?.id;
}

/** 物料 defaults.defaultWarehouses 按 priority 取首个默认入库仓（与后端 resolve_primary_default_warehouse_from_material 一致） */
export function resolvePrimaryDefaultWarehouseFromMaterial(
  material?: Material | null,
): { id: number; name: string } | null {
  const defaults = material?.defaults;
  if (!defaults || typeof defaults !== 'object') return null;
  const rawList = (
    defaults as {
      defaultWarehouses?: Array<{
        warehouseId?: number;
        warehouse_id?: number;
        warehouseName?: string;
        warehouse_name?: string;
        priority?: number;
      }>;
    }
  ).defaultWarehouses;
  if (!Array.isArray(rawList) || rawList.length === 0) return null;
  const sorted = [...rawList].sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999));
  const first = sorted[0];
  const id = first?.warehouseId ?? first?.warehouse_id;
  if (id == null || !Number.isFinite(Number(id)) || Number(id) <= 0) return null;
  const name = String(first?.warehouseName ?? first?.warehouse_name ?? '').trim();
  return { id: Number(id), name };
}