import { apiRequest } from '../../../services/api';
import { kuaioaDelete, kuaioaGet, kuaioaList, kuaioaPost, kuaioaPut } from './kuaioaApi';

const BASE = '/apps/kuaioa/employees';

export type EmployeeBulkCreateResult = {
  createdCount: number;
  failedCount: number;
  requestedCount: number;
  failedItems: Array<{ index: number; reason: string }>;
};

export const listEmployees = (params?: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(BASE, params);

export const getEmployee = (id: number) =>
  kuaioaGet<Record<string, unknown>>(`${BASE}/${id}`);

export const createEmployee = (data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(BASE, data);

/** 批量创建员工（导入分片，单次最多 200） */
export const bulkCreateEmployees = async (
  items: Record<string, unknown>[],
): Promise<EmployeeBulkCreateResult> => {
  const raw = (await apiRequest(`${BASE}/batch-create`, {
    method: 'POST',
    data: { items },
  })) as Record<string, unknown>;
  const failedRaw = Array.isArray(raw?.failedItems)
    ? (raw.failedItems as Array<Record<string, unknown>>)
    : Array.isArray(raw?.failed_items)
      ? (raw.failed_items as Array<Record<string, unknown>>)
      : [];
  return {
    createdCount: Number(raw?.createdCount ?? raw?.created_count ?? 0) || 0,
    failedCount: Number(raw?.failedCount ?? raw?.failed_count ?? 0) || 0,
    requestedCount:
      Number(raw?.requestedCount ?? raw?.requested_count ?? items.length) || items.length,
    failedItems: failedRaw.map((f) => ({
      index: Number(f.index ?? 0) || 0,
      reason: String(f.reason ?? ''),
    })),
  };
};

export const updateEmployee = (id: number, data: Record<string, unknown>) =>
  kuaioaPut<Record<string, unknown>>(`${BASE}/${id}`, data);

export const deleteEmployee = (id: number) => kuaioaDelete(`${BASE}/${id}`);

export const listEmployeeMovements = (params: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(`${BASE}/movements`, params);
