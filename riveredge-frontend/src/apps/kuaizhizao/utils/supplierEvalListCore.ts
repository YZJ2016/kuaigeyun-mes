import {
  pickListSearchKeyword,
  pickSearchString,
  pickSearchTriStateBoolean,
} from '../../../utils/tableQueryKey';

function pickOptionalPeriodYear(
  searchFormValues?: Record<string, unknown> | null,
): number | undefined {
  const raw = pickSearchString(searchFormValues, 'period_year');
  if (raw == null) return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : undefined;
}

export function resolveSupplierEvalPlanListParams(
  searchFormValues?: Record<string, unknown> | null,
  pagination?: { current?: number; pageSize?: number },
) {
  return {
    skip: ((pagination?.current ?? 1) - 1) * (pagination?.pageSize ?? 20),
    limit: pagination?.pageSize ?? 20,
    keyword: pickListSearchKeyword(searchFormValues),
    status: pickSearchString(searchFormValues, 'status'),
    period_type: pickSearchString(searchFormValues, 'period_type'),
    period_year: pickOptionalPeriodYear(searchFormValues),
  };
}

export function resolveSupplierEvaluationListParams(
  searchFormValues?: Record<string, unknown> | null,
  pagination?: { current?: number; pageSize?: number },
) {
  return resolveSupplierEvalPlanListParams(searchFormValues, pagination);
}

export function resolveSupplierEvalEnvListParams(
  searchFormValues?: Record<string, unknown> | null,
  pagination?: { current?: number; pageSize?: number },
) {
  return {
    skip: ((pagination?.current ?? 1) - 1) * (pagination?.pageSize ?? 20),
    limit: pagination?.pageSize ?? 20,
    keyword: pickListSearchKeyword(searchFormValues),
    doc_type: pickSearchString(searchFormValues, 'doc_type'),
  };
}

export function resolveSupplierEvalTemplateListParams(
  searchFormValues?: Record<string, unknown> | null,
  pagination?: { current?: number; pageSize?: number },
) {
  return {
    skip: ((pagination?.current ?? 1) - 1) * (pagination?.pageSize ?? 20),
    limit: pagination?.pageSize ?? 20,
    keyword: pickListSearchKeyword(searchFormValues),
    is_active: pickSearchTriStateBoolean(searchFormValues, 'is_active'),
    period_type: pickSearchString(searchFormValues, 'period_type'),
  };
}
