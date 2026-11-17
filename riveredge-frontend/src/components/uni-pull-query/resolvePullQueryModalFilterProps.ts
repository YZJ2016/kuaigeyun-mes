import type { UniPullQueryModalProps } from './types';

/** useUniPullQuery 返回值中与筛选栏相关的字段 */
export type UniPullQueryFilterController = Pick<
  UniPullQueryModalProps<object>,
  | 'searchDraft'
  | 'appliedKeyword'
  | 'dateDraftFrom'
  | 'dateDraftTo'
  | 'appliedDateFrom'
  | 'appliedDateTo'
  | 'enableDateFilter'
> & {
  setSearchDraft: (value: string) => void;
  handleSearchApply: (keyword: string) => void;
  handleSearchClear: () => void;
  handleDateDraftChange: (from?: string, to?: string) => void;
  handleDateApply: (from?: string, to?: string) => void;
  handleDateClear: () => void;
  scope?: string;
  scopeOptions?: UniPullQueryModalProps<object>['scopeOptions'];
  handleScopeChange?: (scope: string) => void;
  page: number;
  pageSize: number;
  total: number;
  handlePageChange: (page: number) => void;
};

export function resolvePullQueryModalFilterProps(
  pullQuery: UniPullQueryFilterController | undefined,
  explicit: Partial<UniPullQueryModalProps<object>>,
): Partial<UniPullQueryModalProps<object>> {
  if (!pullQuery) {
    return explicit;
  }
  return {
    searchDraft: explicit.searchDraft ?? pullQuery.searchDraft,
    onSearchDraftChange:
      explicit.onSearchDraftChange ??
      ('setSearchDraft' in pullQuery ? pullQuery.setSearchDraft : undefined),
    onSearchApply: explicit.onSearchApply ?? pullQuery.handleSearchApply,
    onSearchClear: explicit.onSearchClear ?? pullQuery.handleSearchClear,
    appliedKeyword: explicit.appliedKeyword ?? pullQuery.appliedKeyword,
    dateDraftFrom: explicit.dateDraftFrom ?? pullQuery.dateDraftFrom,
    dateDraftTo: explicit.dateDraftTo ?? pullQuery.dateDraftTo,
    onDateDraftChange: explicit.onDateDraftChange ?? pullQuery.handleDateDraftChange,
    onDateApply: explicit.onDateApply ?? pullQuery.handleDateApply,
    onDateClear: explicit.onDateClear ?? pullQuery.handleDateClear,
    appliedDateFrom: explicit.appliedDateFrom ?? pullQuery.appliedDateFrom,
    appliedDateTo: explicit.appliedDateTo ?? pullQuery.appliedDateTo,
    enableDateFilter: explicit.enableDateFilter ?? pullQuery.enableDateFilter,
    scope: explicit.scope ?? pullQuery.scope,
    scopeOptions: explicit.scopeOptions ?? pullQuery.scopeOptions,
    onScopeChange: explicit.onScopeChange ?? pullQuery.handleScopeChange,
    page: explicit.page ?? pullQuery.page,
    pageSize: explicit.pageSize ?? pullQuery.pageSize,
    total: explicit.total ?? pullQuery.total,
    onPageChange: explicit.onPageChange ?? pullQuery.handlePageChange,
  };
}
