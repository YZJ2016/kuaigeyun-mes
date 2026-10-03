import type { TFunction } from 'i18next';
import {
  extractProTableSort,
  pickListSearchKeyword,
  pickSearchDateTimeRange,
  pickSearchRaw,
  pickSearchString,
  pickSearchTriStateBoolean,
} from '../../../utils/tableQueryKey';
import { parseSalesReportDateRange } from '../services/reports';
import { normalizeQualityInspectionListResponse } from './qualityInspectionListCore';
import {
  EIGHT_D_SEVERITY_I18N_KEY,
  EIGHT_D_STATUS_I18N_KEY,
} from '../pages/quality-management/eight-d-reports/components/eightDMeta';
import {
  QUALITY_DEFECT_TYPE_I18N,
  QUALITY_DISPOSAL_I18N,
  QUALITY_NC_LEDGER_STATUS_I18N,
  QUALITY_PLAN_TYPE_I18N,
} from '../pages/quality-management/components/qualityMeta';
import { formatDateTime } from '../../../utils/format';

export const NC_LEDGER_PINNED_STATUS_FIELD = 'status';
export const EIGHT_D_PINNED_STATUS_FIELD = 'status';
export const INSPECTION_PLAN_PINNED_STATUS_FIELD = 'is_active';

export { normalizeQualityInspectionListResponse as normalizeQualityImprovementListResponse };

export function buildNcLedgerStatusValueEnum(
  t: TFunction,
): Record<string, { text: string }> {
  return Object.fromEntries(
    Object.entries(QUALITY_NC_LEDGER_STATUS_I18N).map(([value, key]) => [
      value,
      { text: t(key) },
    ]),
  );
}

export function buildNcDefectTypeValueEnum(t: TFunction): Record<string, { text: string }> {
  return Object.fromEntries(
    Object.entries(QUALITY_DEFECT_TYPE_I18N).map(([value, key]) => [value, { text: t(key) }]),
  );
}

export function buildNcDispositionValueEnum(t: TFunction): Record<string, { text: string }> {
  return Object.fromEntries(
    Object.entries(QUALITY_DISPOSAL_I18N).map(([value, key]) => [value, { text: t(key) }]),
  );
}

export function buildEightDStatusValueEnum(t: TFunction): Record<string, { text: string }> {
  return Object.fromEntries(
    Object.entries(EIGHT_D_STATUS_I18N_KEY).map(([value, key]) => [value, { text: t(key) }]),
  );
}

export function buildEightDSeverityValueEnum(t: TFunction): Record<string, { text: string }> {
  return Object.fromEntries(
    Object.entries(EIGHT_D_SEVERITY_I18N_KEY).map(([value, key]) => [value, { text: t(key) }]),
  );
}

export function buildInspectionPlanTypeValueEnum(t: TFunction): Record<string, { text: string }> {
  return Object.fromEntries(
    Object.entries(QUALITY_PLAN_TYPE_I18N).map(([value, key]) => [value, { text: t(key) }]),
  );
}

export function buildInspectionPlanActiveValueEnum(t: TFunction): Record<string, { text: string }> {
  return {
    true: { text: t('common.enabled') },
    false: { text: t('app.kuaizhizao.quality.plans.active.disabled') },
  };
}

function resolveOrderBy(sort?: Record<string, unknown>) {
  const { sortBy, sortOrder } = extractProTableSort(sort ?? {});
  return sortBy && sortOrder ? (sortOrder === 'desc' ? `-${sortBy}` : sortBy) : undefined;
}

function pickUrlId(urlFilters: Record<string, unknown> | undefined, key: string): number | undefined {
  const raw = urlFilters?.[key];
  if (raw == null || raw === '') return undefined;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : undefined;
}

export function formatQualityDateTimeCell(value: unknown): string {
  if (!value) return '-';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD HH:mm');
}

export function resolveInspectionPlanListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | number | boolean | undefined> {
  const search = searchFormValues ?? {};
  const fuzzyKeyword = pickListSearchKeyword(searchFormValues);
  const { date_start: created_start_date, date_end: created_end_date } = parseSalesReportDateRange(search, [
    'created_at_range',
    'createdAtRange',
  ]);
  const { date_start: updated_start_date, date_end: updated_end_date } = parseSalesReportDateRange(search, [
    'updated_at_range',
    'updatedAtRange',
  ]);

  const params: Record<string, string | number | boolean | undefined> = {
    order_by: resolveOrderBy(sort),
    plan_type: pickSearchString(searchFormValues, 'plan_type'),
    is_active: pickSearchTriStateBoolean(searchFormValues, 'is_active'),
    created_start_date,
    created_end_date,
    updated_start_date,
    updated_end_date,
  };

  if (fuzzyKeyword) {
    params.keyword = fuzzyKeyword;
  } else {
    const planCode = pickSearchString(searchFormValues, 'plan_code');
    const planName = pickSearchString(searchFormValues, 'plan_name');
    if (planCode) params.plan_code = planCode;
    if (planName) params.plan_name = planName;
  }

  return params;
}

export function resolveSpcSampleListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | number | undefined> {
  const fuzzyKeyword = pickListSearchKeyword(searchFormValues);
  const sampleTimeRange = pickSearchDateTimeRange(
    searchFormValues,
    'sample_time_from',
    'sample_time_to',
    'sample_time_range',
  );

  const params: Record<string, string | number | undefined> = {
    order_by: resolveOrderBy(sort),
    sample_time_from: sampleTimeRange.from,
    sample_time_to: sampleTimeRange.to,
  };

  if (fuzzyKeyword) {
    params.keyword = fuzzyKeyword;
  } else {
    const characteristicName = pickSearchString(searchFormValues, 'characteristic_name');
    if (characteristicName) params.characteristic_name = characteristicName;
  }

  return params;
}

export function resolveNonconformingLedgerListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
  urlFilters?: Record<string, unknown>,
): Record<string, string | number | undefined> {
  const { sortBy, sortOrder } = extractProTableSort(sort ?? {});
  const order_by =
    sortBy && sortOrder ? (sortOrder === 'desc' ? `-${sortBy}` : sortBy) : undefined;
  const search = searchFormValues ?? {};
  const { date_start: created_start_date, date_end: created_end_date } =
    parseSalesReportDateRange(search, ['created_at_range', 'createdAtRange']);

  return {
    order_by,
    keyword: pickListSearchKeyword(searchFormValues),
    status: pickSearchString(searchFormValues, 'status'),
    defect_type: pickSearchString(searchFormValues, 'defect_type'),
    disposition: pickSearchString(searchFormValues, 'disposition'),
    created_start_date,
    created_end_date,
    defect_id: pickUrlId(urlFilters, 'defect_id'),
    incoming_inspection_id: pickUrlId(urlFilters, 'incoming_inspection_id'),
    process_inspection_id: pickUrlId(urlFilters, 'process_inspection_id'),
    finished_goods_inspection_id: pickUrlId(urlFilters, 'finished_goods_inspection_id'),
  };
}

export function resolveEightDReportListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | number | boolean | undefined> {
  const { sortBy, sortOrder } = extractProTableSort(sort ?? {});
  const order_by =
    sortBy && sortOrder ? (sortOrder === 'desc' ? `-${sortBy}` : sortBy) : undefined;
  const search = searchFormValues ?? {};
  const { date_start: created_start_date, date_end: created_end_date } =
    parseSalesReportDateRange(search, ['created_at_range', 'createdAtRange']);
  const { date_start: due_start_date, date_end: due_end_date } = parseSalesReportDateRange(search, [
    'due_date_range',
    'dueDateRange',
  ]);
  const overdueRaw = pickSearchRaw(searchFormValues, 'overdue_only');
  const overdue_only =
    overdueRaw === true ||
    overdueRaw === 'true' ||
    (Array.isArray(overdueRaw) && overdueRaw.includes('true'));
  const myStageRaw = pickSearchRaw(searchFormValues, 'my_stage_pending');
  const my_stage_pending =
    myStageRaw === true ||
    myStageRaw === 'true' ||
    (Array.isArray(myStageRaw) && myStageRaw.includes('true'));
  const myActionRaw = pickSearchRaw(searchFormValues, 'my_action_pending');
  const my_action_pending =
    myActionRaw === true ||
    myActionRaw === 'true' ||
    (Array.isArray(myActionRaw) && myActionRaw.includes('true'));

  return {
    order_by,
    keyword: pickListSearchKeyword(searchFormValues),
    status: pickSearchString(searchFormValues, 'status'),
    severity: pickSearchString(searchFormValues, 'severity'),
    overdue_only: overdue_only || undefined,
    my_stage_pending: my_stage_pending || undefined,
    my_action_pending: my_action_pending || undefined,
    created_start_date,
    created_end_date,
    due_start_date,
    due_end_date,
  };
}
