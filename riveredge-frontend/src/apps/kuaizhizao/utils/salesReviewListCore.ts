import {
  extractProTableSort,
  pickListSearchKeyword,
} from '../../../utils/tableQueryKey';

export function resolveSalesReviewListApiParams(
  params: { current?: number; pageSize?: number },
  sort?: Record<string, unknown>,
  searchFormValues?: Record<string, unknown> | null,
  options?: { statusFilter?: string },
): Record<string, unknown> {
  const { sortBy, sortOrder } = extractProTableSort(sort ?? {});
  const orderBy =
    sortBy && sortOrder ? (sortOrder === 'desc' ? `-${sortBy}` : sortBy) : undefined;
  const statusFilter = options?.statusFilter;
  return {
    skip: ((params.current || 1) - 1) * (params.pageSize || 20),
    limit: params.pageSize || 20,
    keyword: pickListSearchKeyword(searchFormValues),
    status: statusFilter === 'all' ? undefined : statusFilter,
    order_by: orderBy,
    include_items: true,
  };
}
