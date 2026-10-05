import dayjs from 'dayjs';
import type { ApprovalInstanceListParams } from '../services/approvalInstance';
import type { ApprovalProcessListParams } from '../services/approvalProcess';
import type { PrintDeviceListParams } from '../services/printDevice';
import type { PrintTemplateListParams } from '../services/printTemplate';
import type { ScriptListParams } from '../services/script';
import {
  pickListSearchKeyword,
  pickListSearchKeywordOrFields,
  pickSearchDateTimeRange,
  pickSearchString,
  pickSearchTriStateBoolean,
} from './tableQueryKey';

function pickSearchOptionalUserId(
  searchFormValues: Record<string, unknown> | undefined | null,
  key: string,
): number | undefined {
  const raw = pickSearchString(searchFormValues, key);
  if (raw == null) return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : undefined;
}

function pickIsoTimeRangeFromCreatedAtColumn(
  searchFormValues: Record<string, unknown> | undefined | null,
): { start_time?: string; end_time?: string } {
  const { from, to } = pickSearchDateTimeRange(searchFormValues, 'start_time', 'end_time', 'created_at');
  return {
    start_time: from ? dayjs(from).toISOString() : undefined,
    end_time: to ? dayjs(to).toISOString() : undefined,
  };
}

export function resolveLoginLogListFilter(searchFormValues?: Record<string, unknown> | null) {
  const { start_time, end_time } = pickIsoTimeRangeFromCreatedAtColumn(searchFormValues);
  return {
    keyword: pickListSearchKeyword(searchFormValues),
    login_status: pickSearchString(searchFormValues, 'login_status'),
    username: pickSearchString(searchFormValues, 'username'),
    user_id: pickSearchOptionalUserId(searchFormValues, 'user_id'),
    login_ip: pickSearchString(searchFormValues, 'login_ip'),
    start_time,
    end_time,
  };
}

export function resolveOperationLogListFilter(searchFormValues?: Record<string, unknown> | null) {
  const { start_time, end_time } = pickIsoTimeRangeFromCreatedAtColumn(searchFormValues);
  return {
    keyword: pickListSearchKeyword(searchFormValues),
    operation_type: pickSearchString(searchFormValues, 'operation_type'),
    operation_module: pickSearchString(searchFormValues, 'operation_module'),
    operation_object_type: pickSearchString(searchFormValues, 'operation_object_type'),
    user_id: pickSearchOptionalUserId(searchFormValues, 'user_id'),
    start_time,
    end_time,
  };
}

export function resolveDataBackupListFilter(searchFormValues?: Record<string, unknown> | null) {
  return {
    keyword: pickListSearchKeywordOrFields(searchFormValues, 'name'),
    backup_type: pickSearchString(searchFormValues, 'backup_type'),
    status: pickSearchString(searchFormValues, 'status'),
  };
}

export type InfraPackageListQuery = {
  name?: string;
  plan?: string;
  is_active?: boolean;
  allow_pro_apps?: boolean;
  sort?: string;
  order?: 'asc' | 'desc';
};

export function resolveInfraPackageListFilter(
  searchFormValues: Record<string, unknown> | undefined | null,
  sort: Record<string, 'ascend' | 'descend' | null | undefined>,
): InfraPackageListQuery {
  const entries = Object.entries(sort || {}).filter(
    ([, v]) => v === 'ascend' || v === 'descend',
  ) as [string, 'ascend' | 'descend'][];
  const sortField = entries.length > 0 ? entries[0][0] : undefined;
  const sortOrder = entries.length > 0 ? (entries[0][1] === 'ascend' ? 'asc' : 'desc') : undefined;
  return {
    name: pickListSearchKeywordOrFields(searchFormValues, 'name'),
    plan: pickSearchString(searchFormValues, 'plan'),
    is_active: pickSearchTriStateBoolean(searchFormValues, 'is_active'),
    allow_pro_apps: pickSearchTriStateBoolean(searchFormValues, 'allow_pro_apps'),
    sort: sortField,
    order: sortOrder,
  };
}

export function resolveApprovalProcessListFilter(
  searchFormValues?: Record<string, unknown> | null,
): Omit<ApprovalProcessListParams, 'skip' | 'limit'> {
  return {
    keyword: pickListSearchKeywordOrFields(searchFormValues, 'code', 'name'),
    is_active: pickSearchTriStateBoolean(searchFormValues, 'is_active'),
  };
}

export function resolveApprovalInstanceListFilter(
  searchFormValues?: Record<string, unknown> | null,
): Omit<ApprovalInstanceListParams, 'skip' | 'limit'> {
  return {
    keyword: pickListSearchKeywordOrFields(searchFormValues, 'title'),
    status: pickSearchString(searchFormValues, 'status'),
  };
}

export function resolveScriptListFilter(
  searchFormValues?: Record<string, unknown> | null,
): Omit<ScriptListParams, 'skip' | 'limit'> {
  return {
    keyword: pickListSearchKeywordOrFields(searchFormValues, 'name', 'code'),
    type: pickSearchString(searchFormValues, 'type'),
    is_active: pickSearchTriStateBoolean(searchFormValues, 'is_active'),
  };
}

export function resolvePrintTemplateListFilter(
  searchFormValues?: Record<string, unknown> | null,
): Omit<PrintTemplateListParams, 'skip' | 'limit'> {
  return {
    keyword: pickListSearchKeywordOrFields(searchFormValues, 'code', 'name'),
    type: pickSearchString(searchFormValues, 'type'),
    is_active: pickSearchTriStateBoolean(searchFormValues, 'is_active'),
  };
}

export function resolvePrintDeviceListFilter(
  searchFormValues?: Record<string, unknown> | null,
): Omit<PrintDeviceListParams, 'skip' | 'limit'> {
  return {
    keyword: pickListSearchKeywordOrFields(searchFormValues, 'code', 'name'),
    type: pickSearchString(searchFormValues, 'type'),
    is_active: pickSearchTriStateBoolean(searchFormValues, 'is_active'),
  };
}
