import type { TFunction } from 'i18next';
import {
  extractProTableSort,
  pickListSearchKeyword,
  pickSearchString,
  pickSearchTriStateBoolean,
} from '../../../utils/tableQueryKey';
import { parseSalesReportDateRange } from '../services/reports';
import { getPerformanceSummaryStatusValueEnum } from '../pages/performance/components/performanceMeta';

export const PERFORMANCE_PINNED_ACTIVE_FIELD = 'isActive';
export const PERFORMANCE_PINNED_IS_ACTIVE_FIELD = 'is_active';
export const PERFORMANCE_SUMMARY_PINNED_STATUS_FIELD = 'status';

export function normalizePerformanceListResponse(res: unknown): { data: unknown[]; total: number } {
  if (Array.isArray(res)) {
    return { data: res, total: res.length };
  }
  if (res && typeof res === 'object') {
    const obj = res as { items?: unknown[]; data?: unknown[]; total?: number };
    const data = Array.isArray(obj.items) ? obj.items : Array.isArray(obj.data) ? obj.data : [];
    const total = typeof obj.total === 'number' ? obj.total : data.length;
    return { data, total };
  }
  return { data: [], total: 0 };
}

function resolveOrderBy(sort?: Record<string, unknown>) {
  const { sortBy, sortOrder } = extractProTableSort(sort ?? {});
  return sortBy && sortOrder ? (sortOrder === 'desc' ? `-${sortBy}` : sortBy) : undefined;
}

function pickPerformanceActive(searchFormValues?: Record<string, unknown> | null): boolean | undefined {
  return (
    pickSearchTriStateBoolean(searchFormValues, 'isActive') ??
    pickSearchTriStateBoolean(searchFormValues, 'is_active')
  );
}

function resolveMasterListDateParams(searchFormValues?: Record<string, unknown> | null) {
  const search = searchFormValues ?? {};
  const { date_start: created_start_date, date_end: created_end_date } = parseSalesReportDateRange(search, [
    'created_at_range',
    'createdAtRange',
  ]);
  const { date_start: updated_start_date, date_end: updated_end_date } = parseSalesReportDateRange(search, [
    'updated_at_range',
    'updatedAtRange',
  ]);
  return { created_start_date, created_end_date, updated_start_date, updated_end_date };
}

function pickOptionalId(searchFormValues: Record<string, unknown> | null | undefined, key: string) {
  const raw = pickSearchString(searchFormValues, key);
  if (raw == null || !Number.isFinite(Number(raw))) return undefined;
  const n = Number(raw);
  return n > 0 ? n : undefined;
}

export function resolveHolidayListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | boolean | undefined> {
  const search = searchFormValues ?? {};
  const dates = resolveMasterListDateParams(searchFormValues);
  const { date_start: start_date, date_end: end_date } = parseSalesReportDateRange(search, [
    'holiday_date_range',
    'holidayDateRange',
  ]);

  return {
    order_by: resolveOrderBy(sort),
    keyword: pickListSearchKeyword(searchFormValues),
    holiday_type:
      pickSearchString(searchFormValues, 'holidayType') ??
      pickSearchString(searchFormValues, 'holiday_type'),
    start_date,
    end_date,
    is_active: pickPerformanceActive(searchFormValues),
    ...dates,
  };
}

export function resolveSkillListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | boolean | undefined> {
  return {
    order_by: resolveOrderBy(sort),
    keyword: pickListSearchKeyword(searchFormValues),
    category: pickSearchString(searchFormValues, 'category'),
    is_active: pickPerformanceActive(searchFormValues),
    ...resolveMasterListDateParams(searchFormValues),
  };
}

export function resolveShiftListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | boolean | undefined> {
  return {
    order_by: resolveOrderBy(sort),
    keyword: pickListSearchKeyword(searchFormValues),
    is_active: pickPerformanceActive(searchFormValues),
    ...resolveMasterListDateParams(searchFormValues),
  };
}

export function resolveEmployeeConfigListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | number | boolean | undefined> {
  return {
    order_by: resolveOrderBy(sort),
    keyword: pickListSearchKeyword(searchFormValues),
    employee_id: pickOptionalId(searchFormValues, 'employee_id'),
    calc_mode:
      pickSearchString(searchFormValues, 'calc_mode') ?? pickSearchString(searchFormValues, 'calcMode'),
    is_active: pickPerformanceActive(searchFormValues),
    ...resolveMasterListDateParams(searchFormValues),
  };
}

export function resolveHourlyRateListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | boolean | undefined> {
  return {
    order_by: resolveOrderBy(sort),
    keyword: pickListSearchKeyword(searchFormValues),
    is_active: pickPerformanceActive(searchFormValues),
    ...resolveMasterListDateParams(searchFormValues),
  };
}

export function resolveKpiDefinitionListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | boolean | undefined> {
  return {
    order_by: resolveOrderBy(sort),
    keyword: pickListSearchKeyword(searchFormValues),
    calc_type:
      pickSearchString(searchFormValues, 'calc_type') ?? pickSearchString(searchFormValues, 'calcType'),
    is_active: pickPerformanceActive(searchFormValues),
    ...resolveMasterListDateParams(searchFormValues),
  };
}

export function resolvePerformanceSummaryListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
  toolbar?: { period?: string; employee_id?: number },
): Record<string, string | number | undefined> {
  return {
    order_by: resolveOrderBy(sort),
    keyword: pickListSearchKeyword(searchFormValues),
    period: toolbar?.period ?? pickSearchString(searchFormValues, 'period'),
    employee_id: toolbar?.employee_id,
    status: pickSearchString(searchFormValues, 'status'),
    ...resolveMasterListDateParams(searchFormValues),
  };
}

export function buildPerformanceSummaryStatusValueEnum(t: TFunction) {
  return getPerformanceSummaryStatusValueEnum(t);
}
