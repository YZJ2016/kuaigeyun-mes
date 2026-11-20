/**
 * 接口管理导入/导出（完整备份）：含请求头、请求参数、请求体等详情，可再导入还原。
 */

import type { TFunction } from 'i18next';
import {
  bulkUpsertAPIs,
  deleteAPI,
  getAPIByUuid,
  getAPIListAllMatching,
  type API,
  type CreateAPIData,
} from '../services/apiManagement';
import { getApiErrorMessage } from './errorHandler';

/** 与后端 bulk-upsert 上限一致 */
const API_IMPORT_CHUNK_SIZE = 100;
import type { IntegrationConfig } from '../services/integrationConfig';
import {
  listResourceCategories,
  type ResourceCategory,
} from '../services/resourceCategory';
import { downloadRecordsAsXlsx, type ExportXlsxColumn } from './exportRecordsXlsx';
import {
  buildFactoryImportTemplate,
  resolveFactoryImportHeaderIndexMap,
  type FactoryImportFieldDef,
} from './spreadsheetImportTemplate';

const EXCEL_CELL_MAX = 32767;

export type ApiExportScope = 'selected' | 'currentPage' | 'all' | string;

const API_IMPORT_FIELDS: FactoryImportFieldDef[] = [
  {
    field: 'name',
    required: true,
    labelKey: 'pages.system.apis.columnName',
    aliases: ['接口名称'],
  },
  {
    field: 'code',
    required: true,
    labelKey: 'pages.system.apis.columnCode',
    aliases: ['接口代码'],
  },
  {
    field: 'path',
    required: true,
    labelKey: 'pages.system.apis.columnPath',
    aliases: ['接口路径'],
  },
  {
    field: 'method',
    required: true,
    labelKey: 'pages.system.apis.columnMethod',
    aliases: ['请求方法'],
  },
  {
    field: 'sync_direction',
    labelKey: 'pages.system.apis.columnSyncDirection',
    aliases: ['同步方向'],
  },
  {
    field: 'description',
    labelKey: 'common.remark',
    aliases: ['描述', '备注', 'description'],
  },
  {
    field: 'is_active',
    labelKey: 'pages.system.apis.columnActive',
    aliases: ['启用状态'],
  },
  {
    field: 'is_system',
    labelKey: 'pages.system.apis.columnSystem',
    aliases: ['系统接口'],
  },
  {
    field: 'connection_uuid',
    labelKey: 'pages.system.apis.exportColumnConnectionUuid',
    aliases: ['连接器UUID', 'connection_uuid'],
  },
  {
    field: 'connection_code',
    labelKey: 'pages.system.apis.exportColumnConnectionCode',
    aliases: ['连接器代码', 'connection_code'],
  },
  {
    field: 'connection_name',
    labelKey: 'pages.system.apis.columnConnection',
    aliases: ['应用连接器', '连接器名称', 'connection_name'],
  },
  {
    field: 'category_uuid',
    labelKey: 'pages.system.apis.exportColumnCategoryUuid',
    aliases: ['分类UUID', 'category_uuid'],
  },
  {
    field: 'category_name',
    labelKey: 'pages.system.apis.exportColumnCategoryName',
    aliases: ['分类', '分类名称', 'category_name'],
  },
  {
    field: 'request_headers',
    labelKey: 'pages.system.apis.labelRequestHeaders',
    aliases: ['请求头', 'request_headers'],
  },
  {
    field: 'request_params',
    labelKey: 'pages.system.apis.labelRequestParams',
    aliases: ['请求参数', 'request_params'],
  },
  {
    field: 'request_body',
    labelKey: 'pages.system.apis.labelRequestBody',
    aliases: ['请求体', 'request_body'],
  },
  {
    field: 'response_format',
    labelKey: 'pages.system.apis.labelResponseFormat',
    aliases: ['响应格式', 'response_format'],
  },
  {
    field: 'response_example',
    labelKey: 'pages.system.apis.labelResponseExample',
    aliases: ['响应示例', 'response_example'],
  },
  {
    field: 'source_type_conversion_map',
    labelKey: 'pages.system.apis.exportColumnSourceTypeConversionMap',
    aliases: ['来源类型编码转换', 'source_type_conversion_map'],
  },
  {
    field: 'outbound_field_mappings',
    labelKey: 'pages.system.apis.outboundFieldMappingLabel',
    aliases: ['出站字段映射', 'outbound_field_mappings'],
  },
];

/** 示例行：出站同步 + 出站字段映射，便于对照格式再导入 */
const API_IMPORT_EXAMPLE_OUTBOUND_MAPPINGS = JSON.stringify([
  {
    enabled: true,
    level: 'header',
    source_table: 'apps_kuaizhizao_purchase_receipts',
    local_field: 'receipt_code',
    remote_field: 'trdbillno',
    default_value: '',
  },
  {
    enabled: true,
    level: 'entry',
    source_table: 'apps_kuaizhizao_purchase_receipt_items',
    local_field: 'material_code',
    remote_field: 'material_number',
    default_value: '',
  },
]);

const API_IMPORT_EXAMPLE: string[] = [
  '示例出站接口',
  'example_api',
  '/kapi/v2/im/im_purinbill/add',
  'POST',
  'push',
  '',
  'true',
  'false',
  '',
  '',
  '',
  '',
  '',
  '{}',
  '{}',
  '{}',
  '{}',
  '{}',
  '[]',
  API_IMPORT_EXAMPLE_OUTBOUND_MAPPINGS,
];

export function buildApiImportTemplate(t: TFunction) {
  return buildFactoryImportTemplate(t, API_IMPORT_FIELDS, API_IMPORT_EXAMPLE);
}

function jsonCell(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return '';
  }
}

function parseJsonCell(raw: unknown): unknown {
  if (raw == null || raw === '') return undefined;
  if (typeof raw === 'object') return raw;
  const text = String(raw).trim();
  if (!text) return undefined;
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function parseJsonObjectCell(raw: unknown): Record<string, unknown> | undefined {
  const parsed = parseJsonCell(raw);
  if (parsed == null) return undefined;
  if (typeof parsed === 'object' && !Array.isArray(parsed)) {
    return parsed as Record<string, unknown>;
  }
  return undefined;
}

function parseJsonArrayCell(raw: unknown): Array<Record<string, unknown>> | undefined {
  const parsed = parseJsonCell(raw);
  if (parsed == null) return undefined;
  if (Array.isArray(parsed)) {
    return parsed.filter(
      (item): item is Record<string, unknown> =>
        item != null && typeof item === 'object' && !Array.isArray(item),
    );
  }
  return undefined;
}

function asBool(raw: unknown, defaultValue = true): boolean {
  if (raw == null || raw === '') return defaultValue;
  const text = String(raw).trim().toLowerCase();
  if (['false', '0', 'no', 'n', '否', '禁用', '停用'].includes(text)) return false;
  if (['true', '1', 'yes', 'y', '是', '启用'].includes(text)) return true;
  return defaultValue;
}

/** 与表单 code 规则对齐：仅保留 a-z0-9_，小写，最长 50。 */
export function normalizeApiCode(raw: string): string {
  return String(raw)
    .replace(/[^a-zA-Z0-9_]/g, '_')
    .toLowerCase()
    .slice(0, 50);
}

/**
 * 解析数据行起始下标：模板为「表头 + 示例 + 数据」；导出文件常无示例行。
 * 若第 2 行（index=1）像示例则从 index=2 起，否则整表数据从 index=1 起。
 */
export function resolveApiImportDataStartRow(
  data: any[][],
  headerIndexMap: Record<string, number>,
): number {
  if (!data || data.length < 2) return 2;
  const row1 = data[1];
  if (!Array.isArray(row1)) return 2;
  const codeIdx = headerIndexMap.code;
  const nameIdx = headerIndexMap.name;
  const code1 =
    codeIdx != null ? String(row1[codeIdx] ?? '').trim() : '';
  const name1 =
    nameIdx != null ? String(row1[nameIdx] ?? '').trim() : '';
  const normalizedCode = code1 ? normalizeApiCode(code1) : '';
  const looksLikeExample =
    !code1 ||
    normalizedCode === 'example_api' ||
    name1.includes('示例') ||
    name1.toLowerCase().includes('example');
  return looksLikeExample ? 2 : 1;
}

function resolveSyncDirection(
  raw: unknown,
  t: TFunction,
): 'pull' | 'push' | 'bidirectional' {
  const text = String(raw ?? 'pull').trim();
  const map: Record<string, 'pull' | 'push' | 'bidirectional'> = {
    pull: 'pull',
    push: 'push',
    bidirectional: 'bidirectional',
    [t('pages.system.apis.syncDirection.pull')]: 'pull',
    [t('pages.system.apis.syncDirection.push')]: 'push',
    [t('pages.system.apis.syncDirection.bidirectional')]: 'bidirectional',
    入站同步: 'pull',
    出站同步: 'push',
    双向同步: 'bidirectional',
  };
  return map[text] || map[text.toLowerCase()] || 'pull';
}

/** 导出用：统一出站字段映射行结构（含 source_table） */
function serializeOutboundFieldMappingsForExport(
  raw: API['outbound_field_mappings'],
): string {
  if (!Array.isArray(raw) || raw.length === 0) return '[]';
  const cleaned = raw
    .filter(row => row != null && String(row.remote_field || '').trim())
    .map(row => ({
      enabled: row.enabled !== false,
      level: row.level === 'entry' ? 'entry' : 'header',
      source_table: String(row.source_table || '').trim(),
      local_field: String(row.local_field || '').trim(),
      remote_field: String(row.remote_field || '').trim(),
      default_value: row.default_value ?? '',
    }));
  return jsonCell(cleaned);
}

/** 导入用：规范化出站字段映射，丢弃无对方字段的脏行 */
function normalizeOutboundMappingsForImport(
  raw: Array<Record<string, unknown>> | undefined,
): CreateAPIData['outbound_field_mappings'] {
  if (raw === undefined) return undefined;
  if (!Array.isArray(raw) || raw.length === 0) return [];
  return raw
    .filter(row => row != null && String(row.remote_field || row.target_field || '').trim())
    .map(row => ({
      enabled: row.enabled !== false,
      level: (String(row.level || 'header').toLowerCase() === 'entry'
        ? 'entry'
        : 'header') as 'header' | 'entry',
      source_table: String(
        row.source_table || row.local_table || row.table || '',
      ).trim(),
      local_field: String(row.local_field || row.source_field || '').trim(),
      remote_field: String(row.remote_field || row.target_field || '').trim(),
      default_value:
        row.default_value === undefined || row.default_value === null
          ? ''
          : (row.default_value as string | number | boolean),
    }));
}

function apiNeedsExportDetail(item: API): boolean {
  // 列表偶发不带详情 JSON 时，拉详情补齐
  if (
    item.request_body == null &&
    item.request_params == null &&
    item.request_headers == null
  ) {
    return true;
  }
  const direction = item.sync_direction || 'pull';
  // 出站/双向必须带上 outbound_field_mappings，缺字段时补拉详情
  if (
    (direction === 'push' || direction === 'bidirectional') &&
    item.outbound_field_mappings == null
  ) {
    return true;
  }
  return false;
}

export function buildApiExportColumns(t: TFunction): ExportXlsxColumn[] {
  const tpl = buildApiImportTemplate(t);
  return API_IMPORT_FIELDS.map((field, index) => ({
    key: field.field,
    title: tpl.importHeaders[index] || field.field,
  }));
}

export function buildApiExportRecords(
  apis: API[],
  connections: IntegrationConfig[] = [],
): Array<Record<string, unknown>> {
  const byUuid = new Map(connections.map(c => [c.uuid, c]));
  return apis.map(api => {
    const conn = api.connection_uuid ? byUuid.get(api.connection_uuid) : undefined;
    const syncDirection = api.sync_direction || 'pull';
    return {
      name: api.name,
      code: api.code,
      path: api.path,
      method: api.method,
      // 导出规范值 push/pull/bidirectional（导入同时认「出站同步」等中文）
      sync_direction: syncDirection,
      description: api.description || '',
      is_active: api.is_active !== false,
      is_system: !!api.is_system,
      connection_uuid: api.connection_uuid || '',
      connection_code: conn?.code || '',
      connection_name: api.connection_name || conn?.name || '',
      category_uuid: api.category_uuid || '',
      category_name: api.category_name || '',
      request_headers: jsonCell(api.request_headers ?? {}),
      request_params: jsonCell(api.request_params ?? {}),
      request_body: jsonCell(api.request_body ?? {}),
      response_format: jsonCell(api.response_format ?? {}),
      response_example: jsonCell(api.response_example ?? {}),
      source_type_conversion_map: jsonCell(api.source_type_conversion_map ?? []),
      // 出站同步数据：字段映射一并导出
      outbound_field_mappings: serializeOutboundFieldMappingsForExport(
        api.outbound_field_mappings,
      ),
    };
  });
}

function assertExportCellsWithinLimit(records: Array<Record<string, unknown>>): void {
  for (const record of records) {
    for (const [key, value] of Object.entries(record)) {
      if (typeof value === 'string' && value.length > EXCEL_CELL_MAX) {
        throw new Error(
          `字段 ${key}（接口 ${String(record.code || '')}）超过 Excel 单元格上限，无法导出`,
        );
      }
    }
  }
}

/** 按导出范围收集接口（全部时分页拉全量，保证含请求体、出站字段映射等详情） */
export async function collectApisForExport(
  type: ApiExportScope,
  keys?: Array<string | number>,
  pageData?: API[],
): Promise<API[]> {
  if (type === 'selected' && keys?.length) {
    return Promise.all(keys.map(k => getAPIByUuid(String(k))));
  }
  if (type === 'currentPage' && pageData?.length) {
    if (!pageData.some(apiNeedsExportDetail)) return pageData;
    return Promise.all(pageData.map(item => getAPIByUuid(item.uuid)));
  }
  const all = await getAPIListAllMatching();
  // 全量列表若缺出站映射，对出站/双向接口补拉详情，避免导出空映射
  const needFix = all.some(apiNeedsExportDetail);
  if (!needFix) return all;
  return Promise.all(
    all.map(item => (apiNeedsExportDetail(item) ? getAPIByUuid(item.uuid) : Promise.resolve(item))),
  );
}

export async function exportApisToXlsx(options: {
  t: TFunction;
  type: ApiExportScope;
  keys?: Array<string | number>;
  pageData?: API[];
  connections?: IntegrationConfig[];
  fileName: string;
}): Promise<number> {
  const items = await collectApisForExport(options.type, options.keys, options.pageData);
  if (items.length === 0) return 0;
  const records = buildApiExportRecords(items, options.connections || []);
  assertExportCellsWithinLimit(records);
  const columns = buildApiExportColumns(options.t);
  const tpl = buildApiImportTemplate(options.t);
  // 与导入约定一致：表头 + 示例行 + 数据，导出文件可直接再导入
  const exampleRecord: Record<string, unknown> = {};
  API_IMPORT_FIELDS.forEach((field, index) => {
    exampleRecord[field.field] = tpl.importExampleRow[index] ?? '';
  });
  await downloadRecordsAsXlsx(
    [exampleRecord, ...records],
    columns,
    options.fileName,
  );
  return items.length;
}

function resolveConnectionUuid(
  row: {
    connection_uuid?: string;
    connection_code?: string;
    connection_name?: string;
  },
  connections: IntegrationConfig[],
): string | null | undefined {
  const uuid = String(row.connection_uuid || '').trim();
  if (uuid && connections.some(c => c.uuid === uuid)) return uuid;

  const code = String(row.connection_code || '').trim();
  if (code) {
    const byCode = connections.find(c => c.code === code);
    if (byCode) return byCode.uuid;
  }

  const name = String(row.connection_name || '').trim();
  if (name) {
    const byName = connections.find(c => c.name === name);
    if (byName) return byName.uuid;
  }

  // 有填写但无法匹配时不绑定，避免写入无效 UUID
  if (uuid || code || name) return null;
  return undefined;
}

function resolveCategoryUuid(
  row: { category_uuid?: string; category_name?: string },
  categories: ResourceCategory[],
): string | null | undefined {
  const uuid = String(row.category_uuid || '').trim();
  if (uuid && categories.some(c => c.uuid === uuid)) return uuid;

  const name = String(row.category_name || '').trim();
  if (name) {
    const byName = categories.find(c => c.name === name);
    if (byName) return byName.uuid;
  }

  if (uuid || name) return null;
  return undefined;
}

export interface ApiImportRowError {
  /** Excel/表格行号（从 1 起，含表头） */
  row: number;
  code?: string;
  error: string;
}

export interface ApiImportResult {
  created: number;
  updated: number;
  failed: number;
  /** 有效数据行总数（跳过空行后） */
  total: number;
  errors: ApiImportRowError[];
}

function sleepMs(ms: number): Promise<void> {
  const delay = Math.max(0, Math.trunc(ms));
  if (delay <= 0) return Promise.resolve();
  return new Promise(resolve => setTimeout(resolve, delay));
}

function isWriteRateLimitError(error: unknown): boolean {
  const err = error as { response?: { status?: number }; message?: string };
  if (err?.response?.status === 429) return true;
  return String(err?.message ?? '').includes('过于频繁');
}

function retryAfterMsFromError(error: unknown): number {
  const headers = (error as { response?: { headers?: Record<string, string> } })?.response
    ?.headers;
  const raw = headers?.['retry-after'] ?? headers?.['Retry-After'];
  const seconds = raw != null ? Number.parseInt(String(raw), 10) : Number.NaN;
  if (Number.isFinite(seconds) && seconds > 0) return seconds * 1000;
  return 60_000;
}

async function invokeWriteWithRateLimitRetry(
  write: () => Promise<void>,
  maxRateLimitRetries: number,
): Promise<void> {
  let rateLimitAttempts = 0;
  for (;;) {
    try {
      await write();
      return;
    } catch (error: unknown) {
      if (!isWriteRateLimitError(error) || rateLimitAttempts >= maxRateLimitRetries) {
        throw error;
      }
      rateLimitAttempts += 1;
      await sleepMs(retryAfterMsFromError(error));
    }
  }
}

type ApiImportPreparedRow = {
  sheetRowNo: number;
  codeRaw: string;
  payload: CreateAPIData;
};

/**
 * 从导入表格还原接口：按 code 分片 bulk-upsert（备份恢复）。
 * 表格第 0 行表头，第 1 行示例，其后为数据（无示例行时自动识别）。
 */
export async function importApisFromSpreadsheet(options: {
  t: TFunction;
  data: any[][];
  connections: IntegrationConfig[];
  onProgress?: (done: number, total: number, partial: ApiImportResult) => void;
  maxRateLimitRetries?: number;
  chunkSize?: number;
}): Promise<ApiImportResult> {
  const { t, data, connections } = options;
  const empty: ApiImportResult = {
    created: 0,
    updated: 0,
    failed: 0,
    total: 0,
    errors: [],
  };
  if (!data || data.length < 2) {
    return empty;
  }

  const maxRateLimitRetries = Math.max(0, Math.trunc(options.maxRateLimitRetries ?? 8));
  const chunkSize = Math.min(
    200,
    Math.max(1, Math.trunc(options.chunkSize ?? API_IMPORT_CHUNK_SIZE)),
  );

  const tpl = buildApiImportTemplate(t);
  const headers = (data[0] || []).map((h: any) =>
    String(h || '')
      .replace(/^\*/, '')
      .trim(),
  );
  const headerIndexMap = resolveFactoryImportHeaderIndexMap(headers, tpl.importHeaderMap);
  const dataStartRow = resolveApiImportDataStartRow(data, headerIndexMap);
  const rawRows = data.slice(dataStartRow);

  const categoryRes = await listResourceCategories('api').catch(() => ({
    items: [] as ResourceCategory[],
  }));
  const categories = categoryRes.items || [];

  let created = 0;
  let updated = 0;
  let failed = 0;
  const errors: ApiImportRowError[] = [];

  const cell = (row: any[], field: string): unknown => {
    const idx = headerIndexMap[field];
    if (idx == null) return undefined;
    return row[idx];
  };

  const prepared: ApiImportPreparedRow[] = [];
  for (let i = 0; i < rawRows.length; i += 1) {
    const row = rawRows[i];
    if (!Array.isArray(row) || !row.some(c => c != null && String(c).trim())) continue;
    const sheetRowNo = dataStartRow + i + 1;
    const name = String(cell(row, 'name') ?? '').trim();
    const codeRaw = String(cell(row, 'code') ?? '').trim();
    const path = String(cell(row, 'path') ?? '').trim();
    const method = String(cell(row, 'method') ?? '')
      .trim()
      .toUpperCase();
    if (normalizeApiCode(codeRaw) === 'example_api') continue;
    if (!name || !codeRaw || !path || !method) {
      failed += 1;
      errors.push({
        row: sheetRowNo,
        code: codeRaw || undefined,
        error: '缺少名称/代码/路径/请求方法',
      });
      continue;
    }
    const code = normalizeApiCode(codeRaw);
    if (!code) {
      failed += 1;
      errors.push({ row: sheetRowNo, code: codeRaw, error: '接口代码无效' });
      continue;
    }
    const payload: CreateAPIData = {
      name,
      code,
      path,
      method,
      sync_direction: resolveSyncDirection(cell(row, 'sync_direction'), t),
      description: (() => {
        const d = cell(row, 'description');
        return d != null && String(d).trim() !== '' ? String(d) : undefined;
      })(),
      is_active: asBool(cell(row, 'is_active'), true),
      is_system: asBool(cell(row, 'is_system'), false),
      request_headers: parseJsonObjectCell(cell(row, 'request_headers')),
      request_params: parseJsonObjectCell(cell(row, 'request_params')),
      request_body: parseJsonObjectCell(cell(row, 'request_body')),
      response_format: parseJsonObjectCell(cell(row, 'response_format')),
      response_example: parseJsonObjectCell(cell(row, 'response_example')),
      source_type_conversion_map: parseJsonArrayCell(
        cell(row, 'source_type_conversion_map'),
      ) as CreateAPIData['source_type_conversion_map'],
      outbound_field_mappings: normalizeOutboundMappingsForImport(
        parseJsonArrayCell(cell(row, 'outbound_field_mappings')),
      ),
    };
    const connectionUuid = resolveConnectionUuid(
      {
        connection_uuid: String(cell(row, 'connection_uuid') ?? ''),
        connection_code: String(cell(row, 'connection_code') ?? ''),
        connection_name: String(cell(row, 'connection_name') ?? ''),
      },
      connections,
    );
    if (connectionUuid !== undefined) {
      payload.connection_uuid = connectionUuid;
    }
    const categoryUuid = resolveCategoryUuid(
      {
        category_uuid: String(cell(row, 'category_uuid') ?? ''),
        category_name: String(cell(row, 'category_name') ?? ''),
      },
      categories,
    );
    if (categoryUuid !== undefined) {
      payload.category_uuid = categoryUuid;
    }
    prepared.push({ sheetRowNo, codeRaw, payload });
  }

  const total = prepared.length + failed;
  const snapshot = (): ApiImportResult => ({
    created,
    updated,
    failed,
    total,
    errors: [...errors],
  });
  options.onProgress?.(failed, Math.max(total, 1), snapshot());

  for (let offset = 0; offset < prepared.length; offset += chunkSize) {
    const chunk = prepared.slice(offset, offset + chunkSize);
    try {
      let res!: Awaited<ReturnType<typeof bulkUpsertAPIs>>;
      await invokeWriteWithRateLimitRetry(async () => {
        res = await bulkUpsertAPIs(chunk.map(r => r.payload));
      }, maxRateLimitRetries);
      created += Number(res.created_count || 0);
      updated += Number(res.updated_count || 0);
      for (const item of res.failed_items || []) {
        const local = chunk[item.index];
        failed += 1;
        errors.push({
          row: local?.sheetRowNo ?? offset + item.index + 1,
          code: item.code || local?.codeRaw,
          error: item.reason || '写入失败',
        });
      }
    } catch (error: unknown) {
      const reason = getApiErrorMessage(error, '分片写入失败');
      for (const row of chunk) {
        failed += 1;
        errors.push({ row: row.sheetRowNo, code: row.codeRaw, error: reason });
      }
    }
    options.onProgress?.(
      Math.min(failed + created + updated, total),
      Math.max(total, 1),
      snapshot(),
    );
  }

  return snapshot();
}

export interface ApiCodeDedupGroup {
  /** 规范化后的 code，用于归并 */
  normalizedCode: string;
  keep: API;
  remove: API[];
}

export interface ApiCodeDedupPlan {
  groups: ApiCodeDedupGroup[];
  /** 将删除的条数（不含系统接口） */
  removeCount: number;
  /** 因系统接口跳过删除的条数 */
  skippedSystemCount: number;
}

function apiCreatedAtMs(api: API): number {
  const ms = api.created_at ? Date.parse(String(api.created_at)) : Number.NaN;
  return Number.isFinite(ms) ? ms : Number.MAX_SAFE_INTEGER;
}

/** 同组内保留优先级：系统接口 > 更早创建 > 已是合法 code 形态 */
function pickApiToKeep(candidates: API[]): API {
  return [...candidates].sort((a, b) => {
    const sys = Number(!!b.is_system) - Number(!!a.is_system);
    if (sys !== 0) return sys;
    const byTime = apiCreatedAtMs(a) - apiCreatedAtMs(b);
    if (byTime !== 0) return byTime;
    const aClean = normalizeApiCode(a.code) === String(a.code || '').trim() ? 1 : 0;
    const bClean = normalizeApiCode(b.code) === String(b.code || '').trim() ? 1 : 0;
    if (bClean !== aClean) return bClean - aClean;
    return String(a.uuid).localeCompare(String(b.uuid));
  })[0];
}

/**
 * 按规范化 code 归并重复接口：保留每组一条，其余待删。
 * 系统接口不会进入 remove 列表。
 */
export function planApiCodeDedup(apis: API[]): ApiCodeDedupPlan {
  const byKey = new Map<string, API[]>();
  for (const api of apis) {
    const raw = String(api.code ?? '').trim();
    if (!raw) continue;
    const key = normalizeApiCode(raw) || raw;
    const list = byKey.get(key);
    if (list) list.push(api);
    else byKey.set(key, [api]);
  }

  const groups: ApiCodeDedupGroup[] = [];
  let removeCount = 0;
  let skippedSystemCount = 0;

  for (const [normalizedCode, list] of byKey) {
    if (list.length < 2) continue;
    const keep = pickApiToKeep(list);
    const remove: API[] = [];
    for (const api of list) {
      if (api.uuid === keep.uuid) continue;
      if (api.is_system) {
        skippedSystemCount += 1;
        continue;
      }
      remove.push(api);
    }
    if (remove.length === 0) continue;
    groups.push({ normalizedCode, keep, remove });
    removeCount += remove.length;
  }

  return { groups, removeCount, skippedSystemCount };
}

export interface ApiCodeDedupResult {
  deleted: number;
  failed: number;
  skippedSystem: number;
  groupCount: number;
}

/**
 * 扫描全量接口，按规范化 code 删除重复项（保留更早/系统优先的那条）。
 * 删除带写限流重试，避免批量清理时成片 429。
 */
export async function dedupeApisByNormalizedCode(options?: {
  onProgress?: (done: number, total: number) => void;
  maxRateLimitRetries?: number;
  delayBetweenDeletesMs?: number;
}): Promise<ApiCodeDedupResult> {
  const maxRateLimitRetries = Math.max(0, Math.trunc(options?.maxRateLimitRetries ?? 8));
  const delayBetweenDeletesMs = Math.max(0, Math.trunc(options?.delayBetweenDeletesMs ?? 80));
  const all = await getAPIListAllMatching();
  const plan = planApiCodeDedup(all);
  const toDelete = plan.groups.flatMap(g => g.remove);
  let deleted = 0;
  let failed = 0;

  for (let i = 0; i < toDelete.length; i += 1) {
    const api = toDelete[i];
    let rateLimitAttempts = 0;
    for (;;) {
      try {
        await deleteAPI(api.uuid);
        deleted += 1;
        break;
      } catch (error: unknown) {
        if (isWriteRateLimitError(error) && rateLimitAttempts < maxRateLimitRetries) {
          rateLimitAttempts += 1;
          await sleepMs(retryAfterMsFromError(error));
          continue;
        }
        failed += 1;
        // 保留原因便于调试，但不中断整批
        void getApiErrorMessage(error);
        break;
      }
    }
    options?.onProgress?.(i + 1, toDelete.length);
    if (delayBetweenDeletesMs > 0 && i + 1 < toDelete.length) {
      await sleepMs(delayBetweenDeletesMs);
    }
  }

  return {
    deleted,
    failed,
    skippedSystem: plan.skippedSystemCount,
    groupCount: plan.groups.length,
  };
}
