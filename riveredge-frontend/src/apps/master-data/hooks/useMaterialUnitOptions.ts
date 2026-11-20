import { useQuery, type QueryClient } from '@tanstack/react-query';
import { materialUnitApi } from '../services/material-unit';
import type { MaterialUnit } from '../types/material-unit';

/** 启用单位选项（物料表单 / 单据单位下拉唯一来源；value=名称） */
export const MATERIAL_UNIT_OPTIONS_QUERY_KEY = ['master-data', 'material-units', 'active'] as const;

export function invalidateMaterialUnitOptionsQuery(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: [...MATERIAL_UNIT_OPTIONS_QUERY_KEY] });
}

/** 展示：名称与编码不同时同时显示，如 支（zhi） */
export function formatMaterialUnitOptionLabel(unit: Pick<MaterialUnit, 'code' | 'name'>): string {
  const name = String(unit.name || '').trim();
  const code = String(unit.code || '').trim();
  if (name && code && name !== code) return `${name}（${code}）`;
  return name || code;
}

/**
 * 单位下拉契约：value 为单位名称（与物料 baseUnit / 单据 material_unit 一致）；
 * label 同时带编码。匹配时名称或编码均可命中。
 */
export function useMaterialUnitOptions(enabled = true) {
  const query = useQuery({
    queryKey: [...MATERIAL_UNIT_OPTIONS_QUERY_KEY],
    queryFn: async () => {
      const res = await materialUnitApi.list({ skip: 0, limit: 500, is_active: true });
      return res.items;
    },
    enabled,
    staleTime: 60_000,
  });

  const units = query.data ?? [];
  const options = units.map((u) => {
    const name = String(u.name || u.code || '').trim();
    const code = String(u.code || '').trim();
    return {
      label: formatMaterialUnitOptionLabel(u),
      value: name,
      code,
      name,
    };
  });

  return {
    ...query,
    units,
    options,
  };
}
