import type { TFunction } from 'i18next';
import {
  extractProTableSort,
  pickListSearchKeyword,
  pickSearchString,
} from '../../../utils/tableQueryKey';
import { parseSalesReportDateRange } from '../services/reports';
import { formatDateTime } from '../../../utils/format';

export function normalizePlanListResponse(res: unknown): { data: unknown[]; total: number } {
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

export function buildComputationStatusValueEnum(t: TFunction): Record<string, { text: string }> {
  return {
    待执行: { text: t('app.kuaizhizao.demandComputation.statusPending') },
    计算中: { text: t('app.kuaizhizao.demandComputation.statusComputing') },
    完成: { text: t('app.kuaizhizao.demandComputation.statusCompleted') },
    失败: { text: t('app.kuaizhizao.demandComputation.statusFailed') },
  };
}

export function resolveComputationHistoryListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | number | undefined> {
  const search = searchFormValues ?? {};
  const { date_start: start_date, date_end: end_date } = parseSalesReportDateRange(search, [
    'computation_start_time_range',
    'computationStartTimeRange',
  ]);
  const { date_start: created_start_date, date_end: created_end_date } = parseSalesReportDateRange(search, [
    'created_at_range',
    'createdAtRange',
  ]);
  const fuzzyKeyword = pickListSearchKeyword(searchFormValues);

  const demandIdRaw = pickSearchString(searchFormValues, 'demand_id');
  const demandId =
    demandIdRaw != null && Number.isFinite(Number(demandIdRaw)) ? Number(demandIdRaw) : undefined;

  const params: Record<string, string | number | undefined> = {
    order_by: resolveOrderBy(sort),
    business_mode: pickSearchString(searchFormValues, 'business_mode'),
    computation_status: pickSearchString(searchFormValues, 'computation_status'),
    computation_type: pickSearchString(searchFormValues, 'computation_type'),
    demand_id: demandId,
    start_date,
    end_date,
    created_start_date,
    created_end_date,
  };

  if (fuzzyKeyword) {
    params.keyword = fuzzyKeyword;
  } else {
    const computationCode = pickSearchString(searchFormValues, 'computation_code');
    const demandCode = pickSearchString(searchFormValues, 'demand_code');
    if (computationCode) params.computation_code = computationCode;
    if (demandCode) params.demand_code = demandCode;
  }

  return params;
}

export function formatPlanDateTimeCell(value: unknown): string {
  if (!value) return '-';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD HH:mm:ss');
}
