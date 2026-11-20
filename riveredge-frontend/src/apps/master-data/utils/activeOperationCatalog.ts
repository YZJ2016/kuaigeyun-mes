/**
 * 启用工序主数据：同会话内 dedupe 列表请求（工艺路线编辑 + 工序选择弹窗共用）。
 */

import type { Operation } from '../types/process';
import { operationApi, unwrapProcessPagedList } from '../services/process';

let catalogInFlight: Promise<Operation[]> | null = null;
let catalogCached: Operation[] | null = null;

export function invalidateActiveOperationCatalog(): void {
  catalogCached = null;
  catalogInFlight = null;
}

export function mergeOperationIntoActiveCatalog(operation: Operation): void {
  if (!catalogCached) return;
  if (catalogCached.some((op) => op.uuid === operation.uuid)) return;
  catalogCached = [...catalogCached, operation];
}

export async function fetchActiveOperationCatalog(options?: {
  force?: boolean;
}): Promise<Operation[]> {
  if (!options?.force && catalogCached) {
    return catalogCached;
  }
  if (!options?.force && catalogInFlight) {
    return catalogInFlight;
  }
  catalogInFlight = (async () => {
    const res = await operationApi.list({ isActive: true, limit: 1000 });
    const list = unwrapProcessPagedList(res);
    catalogCached = list;
    return list;
  })();
  try {
    return await catalogInFlight;
  } finally {
    catalogInFlight = null;
  }
}