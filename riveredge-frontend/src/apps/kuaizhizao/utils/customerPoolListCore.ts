import {
  extractProTableSort,
  pickListSearchKeyword,
  pickSearchDateTimeRange,
  pickSearchString,
  pickSearchTriStateBoolean,
} from '../../../utils/tableQueryKey';
import { parseSalesReportDateRange } from '../services/reports';
import { formatDateTime } from '../../../utils/format';

export function normalizeCustomerPoolListResponse(res: unknown): { data: unknown[]; total: number } {
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

export function resolveCustomerPoolListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | number | boolean | undefined> {
  const search = searchFormValues ?? {};
  const fuzzyKeyword = pickListSearchKeyword(searchFormValues);
  const lastFollowUpRange = pickSearchDateTimeRange(
    searchFormValues,
    'last_follow_up_from',
    'last_follow_up_to',
    'last_follow_up_at_range',
  );
  const recycleRange = pickSearchDateTimeRange(
    searchFormValues,
    'recycle_from',
    'recycle_to',
    'recycle_at_range',
  );
  const assignedRange = pickSearchDateTimeRange(
    searchFormValues,
    'assigned_from',
    'assigned_to',
    'assigned_at_range',
  );
  const { date_start: created_start_date, date_end: created_end_date } = parseSalesReportDateRange(search, [
    'created_at_range',
    'createdAtRange',
  ]);
  const { date_start: updated_start_date, date_end: updated_end_date } = parseSalesReportDateRange(search, [
    'updated_at_range',
    'updatedAtRange',
  ]);

  const salesmanRaw = pickSearchString(searchFormValues, 'salesmanId');
  const salesmanId =
    salesmanRaw != null && Number.isFinite(Number(salesmanRaw)) ? Number(salesmanRaw) : undefined;
  const poolStatusRaw = pickSearchString(searchFormValues, 'poolStatus');
  const poolStatus =
    poolStatusRaw === 'pool' || poolStatusRaw === 'owned' ? poolStatusRaw : undefined;
  const followStatusRaw =
    pickSearchString(searchFormValues, 'follow_status') ?? pickSearchString(searchFormValues, 'followStatus');
  const marketScopeRaw =
    pickSearchString(searchFormValues, 'market_scope') ??
    pickSearchString(searchFormValues, 'marketScope') ??
    'domestic';
  const inactiveTri = pickSearchTriStateBoolean(searchFormValues, 'inactive');

  const params: Record<string, string | number | boolean | undefined> = {
    order_by: resolveOrderBy(sort),
    salesmanId: Number.isFinite(salesmanId) && salesmanId! > 0 ? salesmanId : undefined,
    poolStatus,
    marketScope: marketScopeRaw === 'export' ? 'export' : 'domestic',
    followStatus:
      followStatusRaw === 'pending' || followStatusRaw === 'followed' ? followStatusRaw : undefined,
    intentMaterialName:
      pickSearchString(searchFormValues, 'intent_material_name') ??
      pickSearchString(searchFormValues, 'intentMaterialName'),
    customerLevelCode:
      pickSearchString(searchFormValues, 'customer_level_code') ??
      pickSearchString(searchFormValues, 'customerLevelCode'),
    regionText:
      pickSearchString(searchFormValues, 'region_text') ?? pickSearchString(searchFormValues, 'regionText'),
    inactive: inactiveTri === true ? true : undefined,
    last_follow_up_from: lastFollowUpRange.from,
    last_follow_up_to: lastFollowUpRange.to,
    recycle_from: recycleRange.from,
    recycle_to: recycleRange.to,
    assigned_from: assignedRange.from,
    assigned_to: assignedRange.to,
    created_start_date,
    created_end_date,
    updated_start_date,
    updated_end_date,
  };

  if (fuzzyKeyword) {
    params.keyword = fuzzyKeyword;
  } else {
    const code = pickSearchString(searchFormValues, 'code');
    const name = pickSearchString(searchFormValues, 'name');
    const contactPerson = pickSearchString(searchFormValues, 'contact_person');
    const phone = pickSearchString(searchFormValues, 'phone');
    if (code) params.code = code;
    if (name) params.name = name;
    if (contactPerson) params.contact_person = contactPerson;
    if (phone) params.phone = phone;
  }

  return params;
}

export function formatCustomerPoolDateTimeCell(value: unknown): string {
  if (!value) return '—';
  return formatDateTime(value as string | Date, 'YYYY-MM-DD HH:mm');
}
