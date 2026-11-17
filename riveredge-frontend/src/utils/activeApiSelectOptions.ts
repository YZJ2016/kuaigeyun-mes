import { getAPIList, type API } from '../services/apiManagement';

/** 与 sync-from-source 一致：分页拉取全部启用中的数据接口。 */
export async function loadAllActiveApis(): Promise<API[]> {
  const items: API[] = [];
  let page = 1;
  while (page <= 50) {
    const res = await getAPIList({ page, page_size: 100, is_active: true });
    items.push(...(res.items || []));
    if ((res.items || []).length < 100 || items.length >= res.total) break;
    page += 1;
  }
  return items;
}

/** 按 code/path/name 命中 preferredHints 的靠前（仅排序，不过滤）。 */
export function sortApisByPreferredHints(items: API[], preferredHints: string[]): API[] {
  const hints = preferredHints.map((h) => String(h || '').trim().toLowerCase()).filter(Boolean);
  if (!hints.length) return items;
  const score = (api: API): number => {
    const hay = `${api.code || ''} ${api.path || ''} ${api.name || ''}`.toLowerCase();
    for (let i = 0; i < hints.length; i += 1) {
      if (hay.includes(hints[i])) return i;
    }
    return hints.length;
  };
  return [...items].sort((a, b) => score(a) - score(b));
}

export function toApiSelectOptions(items: API[]): Array<{ label: string; value: string }> {
  return items.map((api) => ({
    value: api.uuid,
    label: api.name ? `${api.name}（${api.code}）` : String(api.code || api.uuid),
  }));
}
