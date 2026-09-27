import {
  workshopApi,
  productionLineApi,
  factoryListItems,
} from '../../master-data/services/factory';

/** 从主数据车间管理取启用车间，供薪酬/人事筛选与表单下拉（存 workshop_name）。 */
export async function loadOaWorkshopNameOptions(): Promise<
  Array<{ label: string; value: string }>
> {
  const res = await workshopApi.list({ is_active: true, limit: 1000 });
  const items = factoryListItems(res);
  const byName = new Map<string, { code: string; name: string }>();
  for (const w of items) {
    const name = String(w.name ?? '').trim();
    if (!name || byName.has(name)) continue;
    byName.set(name, { code: String(w.code ?? '').trim(), name });
  }
  return Array.from(byName.values())
    .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
    .map(({ code, name }) => ({
      label: code ? `${code} ${name}` : name,
      value: name,
    }));
}

export type OaProductionLineNameOption = {
  label: string;
  value: string;
  workshopName?: string;
};

/** 从主数据产线管理取启用产线（存 production_line_name）。 */
export async function loadOaProductionLineNameOptions(): Promise<OaProductionLineNameOption[]> {
  const res = await productionLineApi.list({ is_active: true, limit: 1000 });
  const items = factoryListItems(res);
  const byName = new Map<string, OaProductionLineNameOption>();
  for (const row of items) {
    const name = String(row.name ?? '').trim();
    if (!name || byName.has(name)) continue;
    const code = String(row.code ?? '').trim();
    const workshopName = String(row.workshopName ?? '').trim() || undefined;
    byName.set(name, {
      label: code ? `${code} ${name}` : name,
      value: name,
      workshopName,
    });
  }
  return Array.from(byName.values()).sort((a, b) =>
    a.value.localeCompare(b.value, 'zh-CN'),
  );
}

/** 按所属车间过滤产线选项；未选车间时返回全部。 */
export function filterOaProductionLineOptions(
  all: OaProductionLineNameOption[],
  workshopName?: string | null,
): Array<{ label: string; value: string }> {
  const ws = String(workshopName ?? '').trim();
  const filtered = ws
    ? all.filter((o) => !o.workshopName || o.workshopName === ws)
    : all;
  return filtered.map(({ label, value }) => ({ label, value }));
}
