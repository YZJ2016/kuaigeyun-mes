/**
 * 自定义字段 API 工厂：每个用例自建自清，避免共享脏数据。
 */
import { BACKEND_URL, TENANT_ID } from './session';

export type ApiAuth = { token: string };

function headers(token: string, extra?: Record<string, string>): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    'X-Tenant-ID': String(TENANT_ID),
    'X-Client-Channel': 'pc',
    'Content-Type': 'application/json',
    ...extra,
  };
}

async function readError(res: Response): Promise<string> {
  try {
    return await res.text();
  } catch {
    return res.statusText;
  }
}

export async function apiGetJson<T>(token: string, path: string): Promise<T> {
  const res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
    headers: headers(token),
  });
  if (!res.ok) {
    throw new Error(`GET ${path} -> ${res.status} ${await readError(res)}`);
  }
  return res.json() as Promise<T>;
}

/** 返回状态码与正文，用于断言异常契约（不抛）。 */
export async function apiGetRaw(
  token: string,
  path: string,
): Promise<{ status: number; body: string }> {
  const res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
    headers: headers(token),
  });
  return { status: res.status, body: await res.text() };
}

export async function apiSendRaw(
  token: string,
  path: string,
  method: 'POST' | 'PUT' | 'DELETE',
  body?: unknown,
): Promise<{ status: number; body: string }> {
  const res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
    method,
    headers: headers(token),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return { status: res.status, body: await res.text() };
}

export async function apiSendJson<T>(
  token: string,
  path: string,
  method: 'POST' | 'PUT' | 'DELETE',
  body?: unknown,
): Promise<T | null> {
  const res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
    method,
    headers: headers(token),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`${method} ${path} -> ${res.status} ${await readError(res)}`);
  }
  if (res.status === 204) return null;
  const text = await res.text();
  if (!text) return null;
  return JSON.parse(text) as T;
}

export interface SystemSourceFieldDto {
  name: string;
  modelField: string;
  label: string;
  scope: string;
}

export interface CustomFieldDto {
  uuid: string;
  code: string;
  name: string;
  table_name: string;
  field_type: string;
  config?: Record<string, unknown>;
}

export async function listSystemLinkFields(
  token: string,
  tableName: string,
): Promise<SystemSourceFieldDto[]> {
  return apiGetJson(token, `/core/custom-fields/system-link-fields/${encodeURIComponent(tableName)}`);
}

export async function listSystemSourceFields(
  token: string,
  tableName: string,
): Promise<SystemSourceFieldDto[]> {
  return apiGetJson(token, `/core/custom-fields/system-fields/${encodeURIComponent(tableName)}`);
}

export async function associatedLookup(
  token: string,
  params: {
    table: string;
    matchField: string;
    matchValue: string | number;
    returnField?: string;
  },
): Promise<{ value: string | number | null; recordId?: number | null }> {
  const q = new URLSearchParams({
    table: params.table,
    match_field: params.matchField,
    match_value: String(params.matchValue),
    return_field: params.returnField || 'id',
  });
  return apiGetJson(token, `/core/custom-fields/associated-lookup?${q.toString()}`);
}

export async function createAssociatedObjectField(
  token: string,
  input: {
    tableName: string;
    code: string;
    name: string;
    sourceField: string;
    sourceFieldType?: 'system' | 'custom';
    associatedTable: string;
    matchField: string;
    returnField: string;
    displayMode?: string;
  },
): Promise<CustomFieldDto> {
  return apiSendJson(token, '/core/custom-fields', 'POST', {
    name: input.name,
    code: input.code,
    table_name: input.tableName,
    field_type: 'associated_object',
    label: input.name,
    is_required: false,
    is_searchable: false,
    is_sortable: false,
    sort_order: 0,
    is_active: true,
    config: {
      associatedTable: input.associatedTable,
      sourceField: input.sourceField,
      sourceFieldType: input.sourceFieldType || 'system',
      matchField: input.matchField,
      returnField: input.returnField,
      displayMode: input.displayMode || 'display',
    },
  }) as Promise<CustomFieldDto>;
}

export async function deleteCustomField(token: string, uuid: string): Promise<void> {
  await apiSendJson(token, `/core/custom-fields/${uuid}`, 'DELETE');
}

/** 取一条启用物料，供 BOM 主物料 / lookup 使用 */
export async function fetchOneActiveMaterial(
  token: string,
): Promise<{ id: number; base_unit?: string; baseUnit?: string; code?: string; name?: string }> {
  const q = new URLSearchParams({
    page: '1',
    page_size: '1',
    is_active: 'true',
  });
  const data = await apiGetJson<{ items?: Array<Record<string, unknown>> }>(
    token,
    `/apps/master-data/materials?${q.toString()}`,
  );
  const item = data.items?.[0];
  if (!item || item.id == null) {
    throw new Error('无可用启用物料，无法做 associated-lookup 用例');
  }
  return item as { id: number; base_unit?: string; baseUnit?: string; code?: string; name?: string };
}
