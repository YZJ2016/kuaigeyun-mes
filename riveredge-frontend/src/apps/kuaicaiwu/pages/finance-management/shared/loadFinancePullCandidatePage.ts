import {
  filterByPullScope,
  paginatePullRows,
  toUniPullQueryHttpParams,
  UNI_PULL_QUERY_MAX_FETCH_LIMIT,
  type UniPullQueryLoadParams,
  type UniPullQueryLoadResult,
} from '../../../../../components/uni-pull-query';

export type FinancePullCandidateHttpParams = {
  skip: number;
  limit: number;
  keyword?: string;
  date_from?: string;
  date_to?: string;
  supplier_id?: number;
};

export type FinancePullCandidateRow = { supplier_id?: number | null };

export function filterFinancePullRowsBySupplier<T extends FinancePullCandidateRow>(
  rows: T[],
  supplierId: number,
): T[] {
  return rows.filter((row) => Number(row.supplier_id ?? 0) === supplierId);
}

/** 轻财务取单：服务端 keyword + 日期筛选，客户端 scope 过滤与分页。 */
export async function loadFinancePullCandidatePage<T extends object>(
  params: UniPullQueryLoadParams,
  scope: string | undefined,
  isSelectable: (row: T) => boolean,
  fetch: (api: FinancePullCandidateHttpParams) => Promise<{ data?: T[]; total?: number }>,
  options?: { supplierId?: number },
): Promise<UniPullQueryLoadResult<T>> {
  const http = toUniPullQueryHttpParams({
    ...params,
    page: 1,
    pageSize: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
  });
  const supplierId = options?.supplierId;
  const res = await fetch({
    skip: http.skip,
    limit: http.limit,
    ...(http.keyword ? { keyword: http.keyword } : {}),
    ...(http.date_from ? { date_from: http.date_from } : {}),
    ...(http.date_to ? { date_to: http.date_to } : {}),
    ...(supplierId != null && supplierId > 0 ? { supplier_id: supplierId } : {}),
  });
  let rows = res.data ?? [];
  if (supplierId != null && supplierId > 0) {
    rows = filterFinancePullRowsBySupplier(rows as FinancePullCandidateRow[], supplierId) as T[];
  }
  const filtered = filterByPullScope(rows, scope, isSelectable);
  return paginatePullRows(filtered, params.page, params.pageSize);
}
