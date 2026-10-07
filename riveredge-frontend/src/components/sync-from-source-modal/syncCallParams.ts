/** 同步调用来源：请求体路径与分页批大小 */

export function asJsonObject(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return structuredClone(value as Record<string, unknown>);
  }
  return {};
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
