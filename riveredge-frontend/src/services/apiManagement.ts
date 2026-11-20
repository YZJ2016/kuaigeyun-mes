/**
 * 接口管理服务
 * 
 * 提供接口的 CRUD 操作和接口测试功能。
 * 注意：所有 API 自动过滤当前组织的接口
 */

import { apiRequest } from './api';

export type ApiInterfaceType = 'standard' | 'custom';

export interface API {
  uuid: string;
  tenant_id: number;
  name: string;
  code: string;
  description?: string;
  path: string;
  method: string;
  /** 同步方向：pull 入站 / push 出站 / bidirectional 双向 */
  sync_direction?: 'pull' | 'push' | 'bidirectional';
  connection_uuid?: string | null;
  connection_name?: string | null;
  connection_type?: string | null;
  category_uuid?: string | null;
  category_name?: string | null;
  request_headers?: Record<string, any>;
  request_params?: Record<string, any>;
  request_body?: Record<string, any>;
  response_format?: Record<string, any>;
  response_example?: Record<string, any>;
  /** 来源类型编码转换映射（接口级统一维护） */
  source_type_conversion_map?: Array<{
    field_name: string;
    mapping: Record<string, string>;
  }> | null;
  /** 出站字段映射：本地字段 → 对方字段 */
  outbound_field_mappings?: Array<{
    enabled?: boolean;
    level?: 'header' | 'entry';
    source_table?: string;
    local_field?: string;
    remote_field?: string;
    default_value?: string | number | boolean | null;
  }> | null;
  is_active: boolean;
  is_system: boolean;
  /** 关联 MES 单据 source_type（可选） */
  related_document_code?: string | null;
  /** standard 标准API / custom 自定义API */
  api_interface_type?: ApiInterfaceType;
  created_at: string;
  updated_at: string;
}

export interface APIRelatedDocumentOption {
  code: string;
  label: string;
}

export type ApiSyncDirection = 'pull' | 'push' | 'bidirectional';

export interface APIListParams {
  page?: number;
  page_size?: number;
  search?: string;
  method?: string;
  sync_direction?: ApiSyncDirection;
  is_active?: boolean;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
  category_uuid?: string;
  no_category?: boolean;
  related_document_code?: string;
  no_related_document?: boolean;
}

export interface APIListResponse {
  items: API[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateAPIData {
  name: string;
  code: string;
  description?: string;
  path: string;
  method: string;
  sync_direction?: ApiSyncDirection;
  connection_uuid?: string | null;
  category_uuid?: string | null;
  request_headers?: Record<string, any>;
  request_params?: Record<string, any>;
  request_body?: Record<string, any>;
  response_format?: Record<string, any>;
  response_example?: Record<string, any>;
  source_type_conversion_map?: Array<{
    field_name: string;
    mapping: Record<string, string>;
  }> | null;
  outbound_field_mappings?: Array<{
    enabled?: boolean;
    level?: 'header' | 'entry';
    source_table?: string;
    local_field?: string;
    remote_field?: string;
    default_value?: string | number | boolean | null;
  }> | null;
  is_active?: boolean;
  is_system?: boolean;
  related_document_code?: string | null;
  api_interface_type?: ApiInterfaceType;
}

export interface UpdateAPIData {
  name?: string;
  code?: string;
  description?: string;
  path?: string;
  method?: string;
  sync_direction?: ApiSyncDirection;
  connection_uuid?: string | null;
  category_uuid?: string | null;
  request_headers?: Record<string, any>;
  request_params?: Record<string, any>;
  request_body?: Record<string, any>;
  response_format?: Record<string, any>;
  response_example?: Record<string, any>;
  source_type_conversion_map?: Array<{
    field_name: string;
    mapping: Record<string, string>;
  }> | null;
  outbound_field_mappings?: Array<{
    enabled?: boolean;
    level?: 'header' | 'entry';
    source_table?: string;
    local_field?: string;
    remote_field?: string;
    default_value?: string | number | boolean | null;
  }> | null;
  is_active?: boolean;
  related_document_code?: string | null;
  api_interface_type?: ApiInterfaceType;
}

export async function getAPIRelatedDocumentOptions(): Promise<APIRelatedDocumentOption[]> {
  const res = await apiRequest<{ items: APIRelatedDocumentOption[] }>(
    '/api/v1/core/apis/related-document-options',
    { method: 'GET' },
  );
  return res.items ?? [];
}

export interface APIRelatedDocumentGroupCount {
  category_uuid?: string | null;
  related_document_code?: string | null;
  count: number;
}

export async function getAPIRelatedDocumentGroupCounts(): Promise<APIRelatedDocumentGroupCount[]> {
  const res = await apiRequest<{ items: APIRelatedDocumentGroupCount[] }>(
    '/api/v1/core/apis/related-document-group-counts',
    { method: 'GET' },
  );
  return res.items ?? [];
}

export interface APITestRequest {
  headers?: Record<string, any>;
  params?: Record<string, any>;
  body?: Record<string, any>;
}

export interface APITestResponse {
  status_code: number;
  headers: Record<string, any>;
  body: any;
  elapsed_time: number;
}

export interface ApiLibraryItemPreview {
  item_key: string;
  name: string;
  description: string;
}

export interface ApiLibraryPack {
  pack_id: string;
  name: string;
  description: string;
  connector_type: string;
  category_name: string;
  api_count: number;
  items: ApiLibraryItemPreview[];
  source?: 'system' | 'official' | string;
}

export interface ApiLibraryListResponse {
  items: ApiLibraryPack[];
  official_host?: string | null;
  official_base_url?: string | null;
}

export interface InstallApiLibraryPackResult {
  pack_id: string;
  connection_uuid: string;
  connection_code: string;
  connection_type: string;
  category_uuid: string;
  created_count: number;
  skipped_count: number;
  categorized_count: number;
  created_codes: string[];
  skipped_codes: string[];
  categorized_codes: string[];
}

export interface SubmitOfficialApiLibraryPayload {
  name: string;
  description?: string;
  connector_type: string;
  category_name: string;
  category_code?: string;
  category_description?: string;
  api_uuids: string[];
  submitter_hint?: string;
}

export interface SubmitOfficialApiLibraryResult {
  pack_id: string;
  name: string;
  api_count: number;
  status: string;
}

/** 与后端 `apis.list_apis` 的 Query le= 一致，超出会被截断或 422 */
export const API_LIST_MAX_PAGE_SIZE = 100;

/**
 * 获取接口列表
 * 
 * 自动过滤当前组织的接口。
 * 
 * @param params - 查询参数
 * @returns 接口列表
 */
export async function getAPIList(params?: APIListParams): Promise<APIListResponse> {
  return apiRequest<APIListResponse>('/core/apis', {
    params,
  });
}

/**
 * 分页拉取全部匹配接口（含 request_body 等完整字段，用于备份导出）。
 */
export async function getAPIListAllMatching(
  params?: Omit<APIListParams, 'page' | 'page_size'>,
): Promise<API[]> {
  const page_size = API_LIST_MAX_PAGE_SIZE;
  let page = 1;
  const out: API[] = [];
  for (;;) {
    const res = await getAPIList({ ...params, page, page_size });
    out.push(...res.items);
    if (res.items.length === 0 || res.items.length < page_size || out.length >= res.total) {
      break;
    }
    page += 1;
    if (page > 500) break;
  }
  return out;
}

/**
 * 获取接口详情
 * 
 * 自动验证组织权限：只能获取当前组织的接口。
 * 
 * @param apiUuid - 接口 UUID
 * @returns 接口信息
 */
export async function getAPIByUuid(apiUuid: string): Promise<API> {
  return apiRequest<API>(`/core/apis/${apiUuid}`);
}

/**
 * 创建接口
 * 
 * 自动设置当前组织的 tenant_id。
 * 
 * @param data - 接口创建数据
 * @returns 创建的接口信息
 */
export async function createAPI(data: CreateAPIData): Promise<API> {
  return apiRequest<API>('/core/apis', {
    method: 'POST',
    data,
  });
}

export interface APIBulkUpsertFailedItem {
  index: number;
  code?: string | null;
  reason: string;
}

export interface APIBulkUpsertResponse {
  created_count: number;
  updated_count: number;
  failed_count: number;
  requested_count: number;
  failed_items: APIBulkUpsertFailedItem[];
}

/** 单次最多 200 条；按 code 存在则更新、否则新建。 */
export async function bulkUpsertAPIs(
  items: CreateAPIData[],
): Promise<APIBulkUpsertResponse> {
  const raw = (await apiRequest<Record<string, unknown>>('/core/apis/actions/bulk-upsert', {
    method: 'POST',
    data: { items },
  })) as Record<string, unknown>;
  const failedRaw = Array.isArray(raw?.failed_items)
    ? (raw.failed_items as Array<Record<string, unknown>>)
    : Array.isArray(raw?.failedItems)
      ? (raw.failedItems as Array<Record<string, unknown>>)
      : [];
  return {
    created_count: Number(raw?.created_count ?? raw?.createdCount ?? 0) || 0,
    updated_count: Number(raw?.updated_count ?? raw?.updatedCount ?? 0) || 0,
    failed_count: Number(raw?.failed_count ?? raw?.failedCount ?? 0) || 0,
    requested_count:
      Number(raw?.requested_count ?? raw?.requestedCount ?? items.length) || items.length,
    failed_items: failedRaw.map(f => ({
      index: Number(f.index ?? 0) || 0,
      code: f.code != null ? String(f.code) : undefined,
      reason: String(f.reason ?? ''),
    })),
  };
}

/**
 * 更新接口
 * 
 * 自动验证组织权限：只能更新当前组织的接口。
 * 
 * @param apiUuid - 接口 UUID
 * @param data - 接口更新数据
 * @returns 更新后的接口信息
 */
export async function updateAPI(apiUuid: string, data: UpdateAPIData): Promise<API> {
  return apiRequest<API>(`/core/apis/${apiUuid}`, {
    method: 'PUT',
    data,
  });
}

/**
 * 删除接口
 * 
 * 自动验证组织权限：只能删除当前组织的接口。
 * 系统接口不可删除。
 * 
 * @param apiUuid - 接口 UUID
 */
export async function deleteAPI(apiUuid: string): Promise<void> {
  return apiRequest<void>(`/core/apis/${apiUuid}`, {
    method: 'DELETE',
  });
}

/**
 * 测试接口调用
 * 
 * 调用接口并返回测试结果。
 * 
 * @param apiUuid - 接口 UUID
 * @param testRequest - 测试请求数据（可覆盖接口定义的参数）
 * @param timeout - 请求超时时间（秒）
 * @returns 测试结果
 */
export async function testAPI(
  apiUuid: string,
  testRequest: APITestRequest,
  timeout?: number
): Promise<APITestResponse> {
  return apiRequest<APITestResponse>(`/core/apis/${apiUuid}/test`, {
    method: 'POST',
    data: testRequest,
    params: timeout ? { timeout } : undefined,
  });
}

export interface APIProbeRequest {
  connection_uuid: string;
  path: string;
  method?: string;
  request_headers?: Record<string, unknown>;
  request_params?: Record<string, unknown>;
  request_body?: Record<string, unknown>;
}

export interface KingdeeExecuteBillQueryCatalogItem {
  form_id: string;
  name: string;
  default_field_keys: string[];
  fields: Array<{ key: string; label: string }>;
}

/**
 * 编辑弹窗草稿探测（无需已保存接口）
 */
export async function probeAPIDraft(
  data: APIProbeRequest,
  timeout?: number,
): Promise<APITestResponse> {
  return apiRequest<APITestResponse>('/core/apis/actions/probe-draft', {
    method: 'POST',
    data,
    params: timeout ? { timeout } : undefined,
  });
}

/**
 * 金蝶 ExecuteBillQuery 字段目录
 */
export async function getKingdeeExecuteBillQueryCatalog(): Promise<KingdeeExecuteBillQueryCatalogItem[]> {
  const res = await apiRequest<{ items: KingdeeExecuteBillQueryCatalogItem[] }>(
    '/core/apis/integrations/kingdee-galaxy/execute-bill-query/catalog',
  );
  return res.items ?? [];
}

export interface OutboundSourceFieldOption {
  field: string;
  label: string;
}

export interface OutboundSourceTableItem {
  profile_code?: string | null;
  profile_name?: string | null;
  table: string;
  label: string;
  level: 'header' | 'entry';
  fields: OutboundSourceFieldOption[];
}

export interface OutboundSourceCatalogResponse {
  profiles: Array<{ code: string; name: string; match_paths: string[] }>;
  tables: OutboundSourceTableItem[];
  /** 按接口路径推荐的本地单据/实体 code */
  recommended_profile?: string | null;
}

/** 出站映射：本地表/字段目录（先选表再选字段） */
export async function getOutboundSourceCatalog(
  path?: string,
): Promise<OutboundSourceCatalogResponse> {
  const q = path ? `?path=${encodeURIComponent(path)}` : '';
  return apiRequest<OutboundSourceCatalogResponse>(`/core/apis/outbound-source-catalog${q}`);
}

/**
 * 获取系统接口库目录
 */
export async function listApiLibrary(): Promise<ApiLibraryListResponse> {
  return apiRequest<ApiLibraryListResponse>('/core/apis/library');
}

/**
 * 将系统预置接口库包加载到当前组织
 */
export async function installApiLibraryPack(
  packId: string,
  connectionUuid: string,
  itemKeys: string[],
): Promise<InstallApiLibraryPackResult> {
  return apiRequest<InstallApiLibraryPackResult>(`/core/apis/library/${packId}/install`, {
    method: 'POST',
    data: { connection_uuid: connectionUuid, item_keys: itemKeys },
  });
}

/** 获取官方接口库目录（域名见 platform_settings.official_api_library_host） */
export async function listOfficialApiLibrary(): Promise<ApiLibraryListResponse> {
  return apiRequest<ApiLibraryListResponse>('/core/apis/library/official');
}

/**
 * 将官方接口库包加载到当前组织
 */
export async function installOfficialApiLibraryPack(
  packId: string,
  connectionUuid: string,
  itemKeys: string[],
): Promise<InstallApiLibraryPackResult> {
  return apiRequest<InstallApiLibraryPackResult>(`/core/apis/library/official/${packId}/install`, {
    method: 'POST',
    data: { connection_uuid: connectionUuid, item_keys: itemKeys },
  });
}

/**
 * 将本组织接口提交到官方接口库
 */
export async function submitOfficialApiLibrary(
  payload: SubmitOfficialApiLibraryPayload,
): Promise<SubmitOfficialApiLibraryResult> {
  return apiRequest<SubmitOfficialApiLibraryResult>('/core/apis/library/official/submit', {
    method: 'POST',
    data: payload,
  });
}

