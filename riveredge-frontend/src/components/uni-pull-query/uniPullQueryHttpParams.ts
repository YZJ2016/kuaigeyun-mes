import type { UniPullQueryLoadParams, UniPullQueryLoadResult } from './types';

export type UniPullQueryHttpListParams = {
  skip: number;
  limit: number;
  keyword?: string;
  date_from?: string;
  date_to?: string;
};

/** 取单 loadData → 后端 skip/limit/keyword/date_from/date_to */
export function toUniPullQueryHttpParams(params: UniPullQueryLoadParams): UniPullQueryHttpListParams {
  const keyword = params.keyword.trim();
  return {
    skip: (params.page - 1) * params.pageSize,
    limit: params.pageSize,
    ...(keyword ? { keyword } : {}),
    ...(params.dateFrom ? { date_from: params.dateFrom } : {}),
    ...(params.dateTo ? { date_to: params.dateTo } : {}),
  };
}

type PullLineListResponse<T> = { data?: T[]; items?: T[]; total: number };

/** 统一解析取单行列表响应（data 或 items） */
export function normalizePullLineListResponse<T>(res: PullLineListResponse<T>): UniPullQueryLoadResult<T> {
  const data = res.data ?? res.items ?? [];
  return { data, total: res.total ?? data.length };
}

/**
 * 包装取单 loadData：自动带上分页、关键词与日期筛选参数。
 */
export function wrapPullLineLoadData<T extends object, Extra extends Record<string, unknown> = Record<string, never>>(
  fetch: (apiParams: UniPullQueryHttpListParams & Extra) => Promise<PullLineListResponse<T>>,
  buildExtra?: (params: UniPullQueryLoadParams) => Extra,
): (params: UniPullQueryLoadParams) => Promise<UniPullQueryLoadResult<T>> {
  return async (params) => {
    const extra = buildExtra ? buildExtra(params) : ({} as Extra);
    const res = await fetch({ ...toUniPullQueryHttpParams(params), ...extra });
    return normalizePullLineListResponse(res);
  };
}
