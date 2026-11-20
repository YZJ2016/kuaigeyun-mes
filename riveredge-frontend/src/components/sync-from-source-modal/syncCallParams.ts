/** 同步调用来源：请求体路径与分页批大小 */

export function asJsonObject(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return structuredClone(value as Record<string, unknown>);
  }
  return {};
}

/**
 * 苍穹 getList / batchQuery 等列表契约：顶层须有 data（可为空对象）。
 * 与仓库/仓位同一源设定；修复生产「记住调用参数」里被误删的空 data。
 * 库存 getInventory* 等 params 体不补 data。
 */
export function ensureCosmicListRequestData(
  body: Record<string, unknown> | undefined | null,
  meta?: string | { path?: string; code?: string },
): Record<string, unknown> {
  const next = asJsonObject(body);
  const hint =
    typeof meta === 'string'
      ? meta.toLowerCase()
      : `${meta?.path || ''} ${meta?.code || ''}`.toLowerCase().replace(/\\/g, '/');
  if (
    hint.includes('getinventory') ||
    hint.includes('getinvacc') ||
    hint.includes('/imrealbal') ||
    hint.includes('getmalgoodsclass')
  ) {
    return next;
  }
  // 库存式：有 params、无 data → 勿补
  if ('params' in next && !('data' in next)) {
    return next;
  }
  const looksLikeList =
    hint.includes('getlist') ||
    hint.includes('batchquery') ||
    hint.includes('bd_location') ||
    hint.includes('bd_warehouse') ||
    hint.includes('bd_warelocareference') ||
    hint.includes('query_location') ||
    hint.includes('query_warehouse') ||
    hint.includes('query_warelocareference') ||
    'pageNo' in next ||
    'pageSize' in next ||
    'page_no' in next ||
    'page_size' in next ||
    'data' in next;
  if (!looksLikeList) {
    return next;
  }
  if (
    !('data' in next) ||
    next.data === null ||
    typeof next.data !== 'object' ||
    Array.isArray(next.data)
  ) {
    next.data = {};
  }
  return next;
}

export function collectLeafPaths(
  value: unknown,
  prefix = '',
): { path: string; label: string }[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return [];
  const out: { path: string; label: string }[] = [];
  for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
    if (!key.trim()) continue;
    const path = prefix ? `${prefix}.${key}` : key;
    if (child && typeof child === 'object' && !Array.isArray(child)) {
      const nested = collectLeafPaths(child, path);
      if (nested.length > 0) {
        out.push(...nested);
        continue;
      }
    }
    out.push({ path, label: path });
  }
  return out;
}

export function setByPath(
  obj: Record<string, unknown>,
  path: string,
  value: unknown,
): Record<string, unknown> {
  const keys = path.split('.').map((part) => part.trim()).filter(Boolean);
  if (keys.length === 0) return obj;
  const root = structuredClone(obj);
  let cursor: Record<string, unknown> = root;
  for (let index = 0; index < keys.length - 1; index += 1) {
    const key = keys[index];
    const next = cursor[key];
    if (!next || typeof next !== 'object' || Array.isArray(next)) {
      cursor[key] = {};
    }
    cursor = cursor[key] as Record<string, unknown>;
  }
  cursor[keys[keys.length - 1]] = value;
  return root;
}

export function resolveCallPageSize(body: Record<string, unknown> | undefined, fallback = 100): number {
  const raw = body?.pageSize ?? body?.page_size ?? fallback;
  const size = Number(raw);
  if (!Number.isFinite(size) || size <= 0) return fallback;
  return Math.min(Math.trunc(size), 5000);
}

/** 苍穹仓库仓位关系 query：须按仓库编码分批，禁止走物料编码填充。 */
export function isWarehouseLocationReferenceApi(
  apiMeta?: string | { path?: string; code?: string },
): boolean {
  const hint =
    typeof apiMeta === 'string'
      ? apiMeta.toLowerCase()
      : `${apiMeta?.path || ''} ${apiMeta?.code || ''}`.toLowerCase().replace(/\\/g, '/');
  return (
    hint.includes('bd_warelocareference') ||
    hint.includes('query_warelocareference') ||
    hint.includes('warelocareference')
  );
}

/** 批量填入请求体时，每批写入的编码个数（仓库仓位关系须单仓调用） */
export function resolveBatchFillChunkSize(
  body: Record<string, unknown> | undefined,
  fillPath: string | undefined,
  apiMeta?: string | { path?: string; code?: string },
): number {
  const path = String(fillPath || '').toLowerCase();
  const hint =
    typeof apiMeta === 'string'
      ? apiMeta.toLowerCase()
      : `${apiMeta?.path || ''} ${apiMeta?.code || ''}`.toLowerCase();
  if (
    path.includes('warehouse_number') &&
    (hint.includes('bd_warelocareference') || isWarehouseLocationReferenceApi(apiMeta))
  ) {
    return 1;
  }
  return resolveCallPageSize(body);
}

export function suggestWarehouseFillPath(paths: { path: string }[]): string | undefined {
  const hit = paths.find((item) => /(^|\.)warehouse_number$/i.test(item.path));
  return hit?.path ?? 'data.warehouse_number';
}

export function chunkValues<T>(values: T[], size: number): T[][] {
  const chunkSize = Math.max(1, size);
  const chunks: T[][] = [];
  for (let index = 0; index < values.length; index += chunkSize) {
    chunks.push(values.slice(index, index + chunkSize));
  }
  return chunks;
}

export function suggestMaterialFillPath(paths: { path: string }[]): string | undefined {
  const hit = paths.find((item) => /(^|\.)material$/i.test(item.path));
  return hit?.path ?? paths[0]?.path;
}
