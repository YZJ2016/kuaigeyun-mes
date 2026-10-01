import {
  extractProTableSort,
  pickListSearchKeyword,
  pickSearchString,
} from '../../../utils/tableQueryKey';
import { parseSalesReportDateRange } from '../services/reports';

export const QUALITY_INSPECTION_PINNED_STATUS_FIELD = 'status';

export function buildQualityInspectionDocStatusValueEnum(
  t: (key: string) => string,
): Record<string, { text: string }> {
  return {
    待检验: { text: t('app.kuaizhizao.quality.common.docStatus.pendingInspection') },
    已检验: { text: t('app.kuaizhizao.quality.common.status.inspected') },
  };
}

export function buildQualityInspectionQualityStatusValueEnum(
  t: (key: string) => string,
): Record<string, { text: string }> {
  return {
    待判定: { text: t('app.kuaizhizao.quality.common.qualityStatus.pending') },
    合格: { text: t('app.kuaizhizao.quality.common.qualityStatus.qualified') },
    不合格: { text: t('app.kuaizhizao.quality.common.qualityStatus.unqualified') },
  };
}

export function buildOqcInspectionStatusValueEnum(
  t: (key: string) => string,
): Record<string, { text: string }> {
  return {
    待检验: { text: t('app.kuaizhizao.quality.common.docStatus.pendingInspection') },
    已检验: { text: t('app.kuaizhizao.quality.common.status.inspected') },
    待审核: { text: t('app.kuaizhizao.quality.common.reviewStatus.pendingReview') },
    已审核: { text: t('app.kuaizhizao.quality.common.reviewStatus.reviewed') },
    已驳回: { text: t('app.kuaizhizao.quality.common.reviewStatus.rejected') },
  };
}

function pickOptionalId(
  searchFormValues: Record<string, unknown> | null | undefined,
  key: string,
): number | undefined {
  const raw = pickSearchString(searchFormValues, key);
  if (raw == null || !Number.isFinite(Number(raw))) return undefined;
  const n = Number(raw);
  return n > 0 ? n : undefined;
}

export function resolveQualityInspectionListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | number | undefined> {
  const { sortBy, sortOrder } = extractProTableSort(sort ?? {});
  const order_by =
    sortBy && sortOrder ? (sortOrder === 'desc' ? `-${sortBy}` : sortBy) : undefined;
  const search = searchFormValues ?? {};
  const { date_start: inspection_start_date, date_end: inspection_end_date } =
    parseSalesReportDateRange(search, ['inspection_time_range', 'inspectionTimeRange']);
  const { date_start: created_start_date, date_end: created_end_date } =
    parseSalesReportDateRange(search, ['created_at_range', 'createdAtRange']);

  return {
    order_by,
    keyword: pickListSearchKeyword(searchFormValues),
    status: pickSearchString(searchFormValues, 'status'),
    quality_status: pickSearchString(searchFormValues, 'quality_status'),
    supplier_id: pickOptionalId(searchFormValues, 'supplier_id'),
    material_id: pickOptionalId(searchFormValues, 'material_id'),
    purchase_receipt_id: pickOptionalId(searchFormValues, 'purchase_receipt_id'),
    work_order_id: pickOptionalId(searchFormValues, 'work_order_id'),
    operation_id: pickOptionalId(searchFormValues, 'operation_id'),
    inspection_start_date,
    inspection_end_date,
    created_start_date,
    created_end_date,
  };
}

export function normalizeQualityInspectionListResponse(res: unknown): { data: unknown[]; total: number } {
  if (Array.isArray(res)) {
    return { data: res, total: res.length };
  }
  if (res && typeof res === 'object') {
    const obj = res as { data?: unknown[]; items?: unknown[]; total?: number };
    const data = Array.isArray(obj.data) ? obj.data : Array.isArray(obj.items) ? obj.items : [];
    const total = typeof obj.total === 'number' ? obj.total : data.length;
    return { data, total };
  }
  return { data: [], total: 0 };
}
