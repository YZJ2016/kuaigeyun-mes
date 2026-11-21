/** 将数据接口响应体规范化为预览/映射用的行字典列表 */

import type { SyncBinding } from './types';

/** 预览仅用于字段映射与样例核对；正式同步仍走服务端分页全量拉取 */
export const SYNC_PREVIEW_ROW_LIMIT = 50;

/** 关联/后续同步步骤是否已配置来源与映射 */
export function syncStepBindingConfigured(binding: SyncBinding): boolean {
  if (binding.sources?.length) {
    return binding.sources.some(
      (src) => src.field_mapping && Object.keys(src.field_mapping).length > 0,
    );
  }
  return (
    Boolean(binding.source_type) &&
    Boolean(binding.field_mapping) &&
    Object.keys(binding.field_mapping).length > 0
  );
}

const KINGDEE_TARGET_ALIASES: Record<string, string[]> = {
  order_code: ['FBillNo', 'BillNo', 'billno'],
  order_date: ['FDate', 'bizdate'],
  delivery_date: ['FDeliveryDate', 'billentrydeliverydate'],
  customer_code: ['FCustId.FNumber', 'customer_number'],
  customer_name: ['FCustId.FName', 'customer_name'],
  customer_contact: ['linkman_contactperson'],
  customer_phone: ['linkman_phone'],
  total_amount: ['totalallamount', 'totallamount', 'totalamount'],
  total_quantity: ['totalqty', 'totalquantity'],
  salesman_name: ['operator_operatorname', 'operatorname'],
  notes: ['comment'],
  shipping_address: ['receiveaddress'],
  payment_terms: ['paymode'],
  payment_method_code: ['paymode'],
  settlement_terms_code: ['settletype_number', 'reccondition_number'],
  supplier_code: ['FSupplierId.FNumber', 'FNumber'],
  supplier_name: ['FSupplierId.FName', 'FName'],
  forbid_status: ['FForbidStatus'],
  product_code: ['FMaterialId.FNumber'],
  product_name: ['FMaterialId.FName'],
  quantity: [
    'avbqty',
    'qty',
    'FQty',
    'FPlanQty',
    'entryqty',
    'entryQty',
    'entryentryqty',
    'entrychildnumerator',
    'billentryqty',
    'baseqty',
  ],
  material_code: ['material.number', 'material', 'number'],
  material_name: ['material.name'],
  warehouse_code: ['warehouse.number'],
  warehouse_name: ['warehouse.name'],
  batch_no: ['lotnum', 'lot_number', 'lot.number', 'lotnumber'],
  unit: ['unit.number', 'unit.name', 'baseunit'],
  planned_start_date: ['FPlanStartDate'],
  planned_end_date: ['FPlanFinishDate', 'FPlanEndDate'],
  sales_order_code: ['FSaleOrderNo', 'FSrcBillNo'],
  document_status: ['FDocumentStatus', 'billstatus'],
  close_status: ['FCloseStatus'],
  status: ['billstatus', 'FStatus', 'FDocumentStatus'],
  base_unit: [
    'baseunit.number',
    'baseunit_number',
    'measureunitid_number',
    'FBaseUnitId.FNumber',
    'FUnitId.FNumber',
  ],
  base_unit_name: [
    'baseunit.name',
    'baseunit_name',
    'measureunitid_name',
    'FBaseUnitId.FName',
    'FUnitId.FName',
  ],
  code: [
    'FNumber',
    'number',
    'measureunitid_number',
    'baseunit.number',
    'baseunit_number',
  ],
  name: [
    'name',
    'FName',
    'measureunitid_name',
    'baseunit.name',
    'baseunit_name',
  ],
  short_name: ['FShortName'],
  main_code: ['number', 'FNumber', 'material.number', 'material_number'],
  specification: [
    'modelnum',
    'model_num',
    'modelnumber',
    'model',
    'modelNum',
    'FSpecification',
    'FMaterialId.FSpecification',
  ],
  group_code: [
    'group_number',
    'group.number',
    'materialgroup_number',
    'materialgroup.number',
    'FMaterialGroup.FNumber',
  ],
  group_name: [
    'group_name',
    'group.name',
    'materialgroup_name',
    'materialgroup.name',
    'FMaterialGroup.FName',
  ],
  default_tax_rate: [
    'taxrate.taxrate',
    'taxrate_taxrate',
    'taxrate',
    'taxrate.number',
    'taxrate_number',
    'taxrateid_number',
    'FTaxRateId.FNumber',
    'FTaxRateId_FNumber',
    'FEntryTaxRate',
  ],
  parent_code: [
    'parent_parent_number',
    'parent_number',
    'parentid_number',
    'parent.number',
    'FParentId.FNumber',
    'FMaterialGroup.FParentId.FNumber',
    'material_number',
    'materialnumber',
    'materialid_number',
  ],
  component_code: [
    'entrymaterial_number',
    'entrymaterialnumber',
    'entrymaterialid_number',
    'entryentrymaterial_number',
    'entryentrymaterialid_number',
    'billentrymaterial_number',
    'FEntityFMaterialId_FNumber',
  ],
  'item.material_code': [
    'FMaterialId.FNumber',
    'billentry.material_masterid_number',
    'billentrymaterial_masterid_number',
  ],
  'item.material_name': [
    'FMaterialId.FName',
    'billentry.material_masterid_name',
    'billentrymaterial_masterid_name',
  ],
  'item.material_spec': [
    'billentry.material_masterid_modelnum',
    'billentrymaterial_masterid_modelnum',
  ],
  'item.material_unit': [
    'FUnitId.FNumber',
    'FBaseUnitId.FNumber',
    'billentry.unit_number',
    'billentryunit_number',
    'billentry.unit_name',
    'billentryunit_name',
  ],
  'item.required_quantity': ['FQty', 'billentry.qty', 'billentryqty'],
  'item.ordered_quantity': ['FQty', 'billentry.qty', 'billentryqty'],
  // 未税单价：勿混入 FTaxPrice（含税请映 item.display_unit_price）
  'item.unit_price': [
    'FPrice',
    'FEntityFPrice',
    'billentryFPrice',
    'billentry.price',
    'billentryprice',
  ],
  'item.display_unit_price': [
    'FTaxPrice',
    'FEntityFTaxPrice',
    'TaxPrice',
    'FPriceIncludingTax',
    'billentry.priceandtax',
    'billentrypriceandtax',
  ],
  'item.tax_rate': [
    'FEntryTaxRate',
    'billentry.taxrateid_number',
    'billentrytaxrateid_number',
  ],
  'item.delivery_date': [
    'FDeliveryDate',
    'billentry.deliverydate',
    'billentrydeliverydate',
  ],
  'item.notes': ['billentry.entrycomment', 'billentryentrycomment'],
};

export function extractKingdeeFieldKeys(requestBody?: Record<string, unknown> | null): string[] | undefined {
  if (!requestBody || typeof requestBody !== 'object') return undefined;
  let params: unknown = requestBody.parameters;
  if (Array.isArray(params) && params.length > 0) {
    const first = params[0];
    if (typeof first === 'string') {
      try {
        params = JSON.parse(first);
      } catch {
        return undefined;
      }
    } else if (typeof first === 'object' && first !== null) {
      params = first;
    }
  } else if (typeof params === 'string') {
    try {
      params = JSON.parse(params);
    } catch {
      return undefined;
    }
  }
  if (!params || typeof params !== 'object') return undefined;
  const fieldKeys =
    (params as Record<string, unknown>).FieldKeys ?? (params as Record<string, unknown>).fieldKeys;
  if (!fieldKeys) return undefined;
  return String(fieldKeys)
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

function applyCosmicPreviewPageLimit(body: Record<string, unknown>, limit: number): void {
  const hasPage =
    'pageSize' in body ||
    'page_size' in body ||
    'pageNo' in body ||
    'page_no' in body;
  if (!hasPage) return;
  body.pageNo = 1;
  body.page_no = 1;
  body.pageSize = limit;
  body.page_size = limit;
}

/**
 * 预览时压低金蝶拉取量：星空 ExecuteBillQuery 的 Limit，或苍穹 pageSize。
 * 正式同步仍走服务端分页全量；预览仅用于字段映射样例。
 */
export function withKingdeePreviewLimit(
  requestBody: Record<string, unknown> | null | undefined,
  limit: number = SYNC_PREVIEW_ROW_LIMIT,
): Record<string, unknown> | undefined {
  if (!requestBody || typeof requestBody !== 'object') return undefined;
  const cloned = structuredClone(requestBody) as Record<string, unknown>;
  const params = cloned.parameters;
  if (Array.isArray(params) && params.length > 0) {
    let query: Record<string, unknown>;
    const first = params[0];
    if (typeof first === 'string') {
      try {
        query = JSON.parse(first) as Record<string, unknown>;
      } catch {
        applyCosmicPreviewPageLimit(cloned, limit);
        return cloned;
      }
    } else if (typeof first === 'object' && first !== null) {
      query = { ...(first as Record<string, unknown>) };
    } else {
      applyCosmicPreviewPageLimit(cloned, limit);
      return cloned;
    }

    query.Limit = limit;
    query.StartRow = 0;
    params[0] = JSON.stringify(query);
    cloned.parameters = params;
  }

  applyCosmicPreviewPageLimit(cloned, limit);
  return cloned;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** 业务明细数组（勿含 data/items/rows 等响应外壳键） */
const NESTED_DETAIL_KEYS = [
  'entry',
  'billentry',
  'BillEntry',
  'FEntity',
  'fentity',
  'TreeEntity',
  'treeEntity',
] as const;

function flattenSyncFields(
  obj: Record<string, unknown>,
  prefix = '',
  glueFirst = true,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [rawKey, value] of Object.entries(obj)) {
    if (!rawKey) continue;
    let full: string;
    if (prefix) {
      if (glueFirst && rawKey.toLowerCase().startsWith(prefix.toLowerCase())) {
        full = rawKey;
      } else if (glueFirst) {
        full = `${prefix}${rawKey}`;
      } else {
        full = `${prefix}_${rawKey}`;
      }
    } else {
      full = rawKey;
    }
    if (isPlainObject(value)) {
      Object.assign(out, flattenSyncFields(value, full, false));
      continue;
    }
    if (Array.isArray(value)) continue;
    out[full] = value;
  }
  return out;
}

function findDetailKey(row: Record<string, unknown>): string | null {
  for (const key of NESTED_DETAIL_KEYS) {
    if (Array.isArray(row[key])) return key;
  }
  const lowerMap = new Map(Object.keys(row).map((k) => [k.toLowerCase(), k]));
  for (const key of NESTED_DETAIL_KEYS) {
    const found = lowerMap.get(key.toLowerCase());
    if (found && Array.isArray(row[found])) return found;
  }
  return null;
}

/** 表头 + entry[] / FEntity[] 摊成扁平行（对齐后端 sync_nested_expand） */
export function expandNestedDetailRows(
  rows: Record<string, unknown>[],
): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [];
  for (const row of rows) {
    if (!isPlainObject(row)) continue;
    const detailKey = findDetailKey(row);
    if (!detailKey) {
      out.push(flattenSyncFields(row));
      continue;
    }
    const details = row[detailKey];
    const header: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(row)) {
      if (k !== detailKey) header[k] = v;
    }
    const flatHeader = flattenSyncFields(header);
    if (!Array.isArray(details) || details.length === 0) {
      out.push(flatHeader);
      continue;
    }
    let expanded = 0;
    for (const item of details) {
      if (!isPlainObject(item)) continue;
      out.push({ ...flatHeader, ...flattenSyncFields(item, detailKey, true) });
      expanded += 1;
    }
    if (expanded === 0) out.push(flatHeader);
  }
  return out;
}

export function collectRowColumnKeys(rows: Record<string, unknown>[]): string[] {
  const seen = new Set<string>();
  const columns: string[] = [];
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      if (!key || seen.has(key)) continue;
      seen.add(key);
      columns.push(key);
    }
  }
  return columns;
}

/** 物料行按基础单位编码去重，供单位同步预览/映射 */
export function collapseMaterialRowsToUniqueUnits(
  rows: Record<string, unknown>[],
): Record<string, unknown>[] {
  const seen = new Set<string>();
  const out: Record<string, unknown>[] = [];
  for (const row of rows) {
    const code = String(
      row.baseunit_number ??
        row['baseunit.number'] ??
        row.measureunitid_number ??
        row['measureunitid.number'] ??
        '',
    ).trim();
    const name = String(
      row.baseunit_name ??
        row['baseunit.name'] ??
        row.measureunitid_name ??
        row['measureunitid.name'] ??
        code,
    ).trim();
    if (!code) continue;
    const key = code.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      baseunit_number: code,
      baseunit_name: name || code,
      number: code,
      name: name || code,
      code,
    });
  }
  return out.length ? out : rows;
}

/**
 * 预览表列收窄（仅展示用）。
 * - 无 preferredKeys：不裁列（已映射列仅置顶），否则自动匹配/下拉永远看不到未映射源列（如税率、行备注）
 * - 有 preferredKeys：只保留 preferred ∪ 已映射，避免苍穹 batchQuery 全量刷屏
 */
export function filterPreviewColumns(
  columns: string[],
  preferredKeys?: string[] | null,
  mappedSources?: string[] | null,
): string[] {
  if (!columns.length) return columns;
  const mapped: string[] = [];
  const mappedSeen = new Set<string>();
  for (const raw of mappedSources || []) {
    const key = String(raw || '').trim();
    if (!key || !columns.includes(key) || mappedSeen.has(key)) continue;
    mappedSeen.add(key);
    mapped.push(key);
  }
  const preferred = (preferredKeys || []).map((item) => String(item || '').trim()).filter(Boolean);
  if (!preferred.length) {
    if (!mapped.length) return columns;
    const tail = columns.filter((column) => !mappedSeen.has(column));
    return [...mapped, ...tail];
  }
  const keep = new Set<string>(mapped);
  const preferredLower = preferred.map((item) => item.toLowerCase());
  for (const column of columns) {
    const lower = column.toLowerCase();
    if (
      preferredLower.some(
        (key) => lower === key || lower.endsWith(`.${key}`) || lower.includes(key.replace(/\./g, '_')),
      )
    ) {
      keep.add(column);
    }
  }
  if (!keep.size) return columns;
  const ordered = columns.filter((column) => keep.has(column));
  return ordered.length ? ordered : columns;
}

/**
 * 苍穹分页体：`{ rows, pageNo, pageSize, ... }`。
 * rows 为 null/非数组时返回 []（禁止把分页壳摊成「业务行」，否则自动匹配只会命中 status）。
 */
function readCosmicPagedRowsOrEmpty(obj: Record<string, unknown>): unknown[] | null {
  const keyMap = new Map(Object.keys(obj).map((k) => [k.toLowerCase(), k]));
  const rowsKey = keyMap.get('rows');
  if (rowsKey !== undefined) {
    const rows = obj[rowsKey];
    return Array.isArray(rows) ? rows : [];
  }
  const hasPaging = ['pageno', 'pagesize', 'lastpage', 'totalcount'].some((k) => keyMap.has(k));
  return hasPaging ? [] : null;
}

/** 与接口测试预览 / 后端 sync_source_rows 一致：含 QueryGroupInfo NeedReturnData。 */
function coerceArrayCandidate(value: unknown, depth: number): unknown[] | null {
  if (Array.isArray(value)) {
    return value;
  }
  if (
    typeof value === 'string' &&
    (value.trim().startsWith('[') || value.trim().startsWith('{'))
  ) {
    try {
      const parsed = JSON.parse(value) as unknown;
      if (Array.isArray(parsed)) {
        return parsed;
      }
      if (isPlainObject(parsed) && depth < 2) {
        return extractArrayFromObject(parsed, depth + 1);
      }
    } catch {
      return null;
    }
  }
  return null;
}

function extractArrayFromObject(body: Record<string, unknown>, depth = 0): unknown[] | null {
  const candidates = [
    'data',
    'items',
    'rows',
    'records',
    'Results',
    'result',
    'Result',
    'list',
    'NeedReturnData',
    'needReturnData',
  ];
  for (const key of candidates) {
    const hit = coerceArrayCandidate(body[key], depth);
    if (hit != null) {
      return hit;
    }
  }
  // 当前对象本身就是分页壳（或 rows: null）
  const selfPaged = readCosmicPagedRowsOrEmpty(body);
  if (selfPaged !== null) {
    return selfPaged;
  }
  if (depth >= 2) {
    return null;
  }
  for (const key of candidates) {
    const value = body[key];
    if (isPlainObject(value)) {
      const nestedPaged = readCosmicPagedRowsOrEmpty(value);
      if (nestedPaged !== null) {
        return nestedPaged;
      }
      const nested = extractArrayFromObject(value, depth + 1);
      if (nested != null) {
        return nested;
      }
    }
  }
  return null;
}

function normalizeBodyValue(body: unknown): unknown {
  if (typeof body !== 'string') {
    return body;
  }
  const trimmed = body.trim();
  if (!trimmed) {
    return body;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return body;
  }
}

function formatCosmicGatewayError(errorCode: string, message: string): string {
  const text = String(message || errorCode || '苍穹接口返回失败').trim();
  if (
    errorCode === '612' ||
    text.includes('查询功能权限') ||
    (text.includes('无应用') && text.includes('业务对象'))
  ) {
    if (text.includes('开放服务云')) return text;
    return (
      `${text} 仓库列表路由是 kapi/v2/sbd/bd_warehouse/getList。` +
      'basedata 下的 query/batchQuery 网关返回 2530 路由未找到。612 是连接器代理用户缺少应用 sbd、业务对象 bd_warehouse 的查询功能权限。'
    );
  }
  return text;
}

/** 苍穹失败外壳（含无 status=false 的 612）不得当成业务行。 */
function throwIfCosmicGatewayError(body: Record<string, unknown>): void {
  const errorCode = String(body.errorCode ?? body.error_code ?? '').trim();
  const status = body.status;
  const statusOk = status === true || String(status).toLowerCase() === 'true';
  const statusFalse = status === false || String(status).toLowerCase() === 'false';
  const successCodes = new Set(['', '0', 'success', 'SUCCESS']);
  if (statusOk) return;
  if (successCodes.has(errorCode) && !statusFalse) return;
  throw new Error(
    formatCosmicGatewayError(errorCode, String(body.message ?? body.msg ?? '')),
  );
}

function normalizeApiBodyToRowsRaw(
  body: unknown,
  columnNames?: string[],
): Record<string, unknown>[] {
  const normalized = normalizeBodyValue(body);
  if (normalized == null) return [];
  if (isPlainObject(normalized) && 'error' in normalized && normalized.error) {
    throw new Error(String(normalized.error));
  }
  if (isPlainObject(normalized)) {
    throwIfCosmicGatewayError(normalized);
  }
  if (Array.isArray(normalized)) {
    if (normalized.length === 0) return [];
    const first = normalized[0];
    if (Array.isArray(first)) {
      const cols = columnNames?.length ? columnNames : first.map((_, index) => `col_${index}`);
      return normalized
        .filter((row): row is unknown[] => Array.isArray(row))
        .map((row) => {
          const padded = [...row, ...Array(Math.max(0, cols.length - row.length)).fill(null)];
          return Object.fromEntries(cols.map((col, index) => [col, padded[index]]));
        });
    }
    if (typeof first === 'object' && first !== null) {
      return normalized.filter(
        (row): row is Record<string, unknown> => typeof row === 'object' && row !== null,
      );
    }
    return normalized.map((value) => ({ value }));
  }
  if (isPlainObject(normalized)) {
    const nested = extractArrayFromObject(normalized);
    // nested 可能是 []（空预览）；空数组也要消费，不能落到「整包当一行」
    if (nested != null) {
      return normalizeApiBodyToRowsRaw(nested, columnNames);
    }
    // 无 rows 的接口壳（status/errorCode/message）不能当业务行，否则自动匹配只会命中 status
    if (looksLikeApiEnvelope(normalized)) {
      return [];
    }
    // 外层带 data 分页壳但未解出数组时，仍勿把 status/errorCode 当业务列
    if (isPlainObject(normalized.data) && readCosmicPagedRowsOrEmpty(normalized.data) != null) {
      return [];
    }
    return [normalized];
  }
  return [{ value: normalized }];
}

/** 苍穹/网关成功壳或错误壳，本身不是业务数据行 */
function looksLikeApiEnvelope(body: Record<string, unknown>): boolean {
  const keys = Object.keys(body);
  if (!keys.length) return true;
  const meta = new Set([
    'status',
    'success',
    'error',
    'errorcode',
    'errormessage',
    'message',
    'msg',
    'code',
    'filter',
    'lastpage',
    'pageno',
    'pagesize',
    'total',
    'totalcount',
  ]);
  const business = keys.filter((key) => !meta.has(key.toLowerCase()));
  return business.length === 0;
}

/**
 * 苍穹 HTTP 200 但业务失败：抽出 message，避免被当成「空 rows」静默吞掉。
 */
export function extractKingdeeApiError(body: unknown): string | null {
  if (!isPlainObject(body)) return null;
  if ('error' in body && body.error != null && String(body.error).trim()) {
    return String(body.error).trim();
  }
  const status = body.status;
  const errorCode = body.errorCode ?? body.error_code ?? body.code;
  const message = body.message ?? body.msg ?? body.errorMessage ?? body.error_message;
  const codeStr = errorCode != null ? String(errorCode).trim() : '';
  const msgStr = message != null ? String(message).trim() : '';
  const okCode =
    !codeStr ||
    codeStr === '0' ||
    codeStr.toLowerCase() === 'success' ||
    codeStr.toLowerCase() === 'ok';
  const failedStatus = status === false || status === 'false' || status === 0 || status === '0';
  if (failedStatus) {
    return msgStr || (codeStr ? `接口返回失败（errorCode=${codeStr}）` : '接口返回失败');
  }
  // status 仍为 true/缺省，但 errorCode 非成功且带说明（部分网关如此）
  if (!okCode && msgStr) {
    return msgStr;
  }
  // 无 rows 的失败壳：仅有 message 且像参数类型错误
  if (
    msgStr &&
    (/不能转换为|NumberFormatException|参数【|类型为\s*DateTime/i.test(msgStr) ||
      /TraceId/i.test(msgStr))
  ) {
    const data = body.data;
    if (data == null || (isPlainObject(data) && readCosmicPagedRowsOrEmpty(data)?.length === 0)) {
      return msgStr;
    }
  }
  return null;
}

export function normalizeApiBodyToRows(
  body: unknown,
  columnNames?: string[],
): Record<string, unknown>[] {
  const businessError = extractKingdeeApiError(body);
  if (businessError) {
    throw new Error(businessError);
  }
  return expandNestedDetailRows(normalizeApiBodyToRowsRaw(body, columnNames));
}

const CAMEL_SNAKE_PAIRS: Array<[string, string]> = [
  ['order_code', 'orderCode'],
  ['order_date', 'orderDate'],
  ['delivery_date', 'deliveryDate'],
  ['customer_id', 'customerId'],
  ['customer_code', 'customerCode'],
  ['customer_name', 'customerName'],
  ['supplier_code', 'supplierCode'],
  ['supplier_name', 'supplierName'],
  ['forbid_status', 'forbidStatus'],
  ['product_code', 'productCode'],
  ['product_name', 'productName'],
  ['quantity', 'quantity'],
  ['planned_start_date', 'plannedStartDate'],
  ['planned_end_date', 'plannedEndDate'],
  ['sales_order_code', 'salesOrderCode'],
  ['document_status', 'documentStatus'],
  ['close_status', 'closeStatus'],
  ['material_code', 'materialCode'],
  ['material_name', 'materialName'],
  ['main_code', 'mainCode'],
  ['base_unit', 'baseUnit'],
  ['base_unit_name', 'baseUnitName'],
  ['group_code', 'groupCode'],
  ['group_name', 'groupName'],
  ['parent_code', 'parentCode'],
  ['material_unit', 'materialUnit'],
  ['required_quantity', 'requiredQuantity'],
  ['unit_price', 'unitPrice'],
  ['salesman_name', 'salesmanName'],
  ['contact_person', 'contactPerson'],
  ['short_name', 'shortName'],
];

function normalizeFieldKey(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]/g, '');
}

function resolveTargetAliases(
  target: string,
  targetAliases?: Record<string, string[]> | null,
): string[] {
  if (targetAliases && Object.prototype.hasOwnProperty.call(targetAliases, target)) {
    return targetAliases[target] ?? [];
  }
  return KINGDEE_TARGET_ALIASES[target] ?? [];
}

function columnMatchesTarget(
  column: string,
  target: string,
  targetAliases?: Record<string, string[]> | null,
): boolean {
  const col = column.trim();
  const tgt = target.trim();
  if (!col || !tgt) return false;
  if (col === tgt) return true;
  const aliases = resolveTargetAliases(tgt, targetAliases);
  if (aliases.includes(col)) return true;
  const colLower = col.toLowerCase();
  const tgtLower = tgt.replace(/^item\./, '').toLowerCase();
  const normalizedColumn = normalizeFieldKey(col);
  const normalizedTarget = normalizeFieldKey(tgt.replace(/^item\./, ''));
  if (normalizedColumn === normalizedTarget) return true;
  if (aliases.some((alias) => normalizedColumn === normalizeFieldKey(alias))) return true;
  if (colLower === tgtLower) return true;
  if (colLower.endsWith(`.${tgtLower}`)) return true;
  for (const alias of aliases) {
    if (col === alias || colLower === alias.toLowerCase()) return true;
  }
  for (const [snake, camel] of CAMEL_SNAKE_PAIRS) {
    if (tgt === snake && (col === camel || colLower === camel.toLowerCase())) return true;
    if (tgt === camel && (col === snake || colLower === snake)) return true;
    if (tgt.endsWith(snake) && col.endsWith(camel)) return true;
  }
  return false;
}

function lookupColumn(
  columns: string[],
  columnByLower: Map<string, string>,
  columnByNormalized: Map<string, string>,
  key: string,
): string | undefined {
  const trimmed = key.trim();
  if (!trimmed) return undefined;
  return (
    columnByLower.get(trimmed.toLowerCase()) ||
    columnByNormalized.get(normalizeFieldKey(trimmed)) ||
    columns.find((column) => normalizeFieldKey(column) === normalizeFieldKey(trimmed))
  );
}

/**
 * 按目标字段建议「目标→来源」映射。
 * - 本页显式配置了别名（含空数组）：空=禁止自动匹配；非空=先别名再同名（避免 status→status 抢在 billstatus 前）
 * - 未配置本页别名：先同名再全局别名（物料 name 等同名优先场景）
 */
export function suggestTargetToSourceMapping(
  columns: string[],
  targetFields: string[],
  targetAliases?: Record<string, string[]> | null,
): Record<string, string> {
  const mapping: Record<string, string> = {};
  const columnByLower = new Map(columns.map((column) => [column.toLowerCase(), column]));
  // billentry.taxrateid_number ↔ billentrytaxrateid_number（摊平去点）
  const columnByNormalized = new Map(
    columns.map((column) => [normalizeFieldKey(column), column]),
  );
  for (const target of targetFields) {
    const pageOwns =
      Boolean(targetAliases) &&
      Object.prototype.hasOwnProperty.call(targetAliases, target);
    const aliases = resolveTargetAliases(target, targetAliases);

    if (pageOwns && aliases.length === 0) {
      continue;
    }

    let hit: string | undefined;
    if (pageOwns) {
      // 本页别名优先：销售订单 status 应对 billstatus，而非预览里偶发的 status 元字段
      for (const alias of aliases) {
        hit = lookupColumn(columns, columnByLower, columnByNormalized, alias);
        if (hit) break;
      }
      if (!hit) {
        hit = lookupColumn(columns, columnByLower, columnByNormalized, target);
      }
      if (!hit) {
        hit = columns.find((column) => columnMatchesTarget(column, target, targetAliases));
      }
    } else {
      // 优先同名列（苍穹 name→物料名称），避免被 baseunit_name 等别名抢先
      hit = lookupColumn(columns, columnByLower, columnByNormalized, target);
      if (!hit) {
        for (const alias of aliases) {
          hit = lookupColumn(columns, columnByLower, columnByNormalized, alias);
          if (hit) break;
        }
      }
      if (!hit) {
        hit = columns.find((column) => columnMatchesTarget(column, target, targetAliases));
      }
    }
    if (hit) mapping[target] = hit;
  }
  return mapping;
}

/** 识别导入 JSON：目标→来源（导出格式）或 来源→目标（存储 field_mapping） */
export function normalizeImportedTargetToSource(
  raw: Record<string, string>,
  knownTargets: string[],
): Record<string, string> {
  const entries = Object.entries(raw).filter(
    ([k, v]) => typeof k === 'string' && k.trim() && typeof v === 'string' && v.trim(),
  );
  if (entries.length === 0) return {};
  const known = new Set(knownTargets.map((item) => item.trim()).filter(Boolean));
  if (known.size === 0) {
    return Object.fromEntries(entries.map(([k, v]) => [k.trim(), v.trim()]));
  }
  let keyHits = 0;
  let valueHits = 0;
  for (const [key, value] of entries) {
    if (known.has(key.trim())) keyHits += 1;
    for (const part of value.split(',').map((item) => item.trim()).filter(Boolean)) {
      if (known.has(part)) {
        valueHits += 1;
        break;
      }
    }
  }
  // 值侧命中明显更多 → 当作存储用 来源→目标，反转为目标→来源
  if (valueHits > keyHits) {
    return fromFieldMapping(Object.fromEntries(entries.map(([k, v]) => [k.trim(), v.trim()])));
  }
  return Object.fromEntries(entries.map(([k, v]) => [k.trim(), v.trim()]));
}

/** 导入时按预览列宽松对齐来源列名（大小写 / 去点摊平） */
export function resolveImportSourceColumn(
  source: string,
  columns: string[],
): string | undefined {
  const trimmed = String(source || '').trim();
  if (!trimmed) return undefined;
  if (!columns.length) return trimmed;
  const columnByLower = new Map(columns.map((column) => [column.toLowerCase(), column]));
  const columnByNormalized = new Map(
    columns.map((column) => [normalizeFieldKey(column), column]),
  );
  return lookupColumn(columns, columnByLower, columnByNormalized, trimmed);
}

/** 丢弃来源列已不在预览中的映射，再用建议补齐空目标 */
export function mergeSuggestedMapping(
  columns: string[],
  targetFields: string[],
  existing: Record<string, string>,
  targetAliases?: Record<string, string[]> | null,
): Record<string, string> {
  const suggested = suggestTargetToSourceMapping(columns, targetFields, targetAliases);
  const columnSet = new Set(columns);
  const next: Record<string, string> = { ...suggested };
  for (const [target, source] of Object.entries(existing)) {
    if (!target || !source) continue;
    if (columnSet.size === 0 || columnSet.has(source)) {
      next[target] = source;
    }
  }
  return next;
}

/**
 * 目标→来源 转为存储用 来源→目标。
 * 同一来源列可对应多个目标（逗号分隔），避免 order_date 与 delivery_date 共映 bizdate 时丢字段。
 */
export function toFieldMapping(targetToSource: Record<string, string>): Record<string, string> {
  const inverted: Record<string, string> = {};
  for (const [target, source] of Object.entries(targetToSource)) {
    const src = String(source || '').trim();
    const tgt = String(target || '').trim();
    if (!src || !tgt) continue;
    const existing = inverted[src];
    if (!existing) {
      inverted[src] = tgt;
      continue;
    }
    const parts = existing.split(',').map((part) => part.trim()).filter(Boolean);
    if (!parts.includes(tgt)) inverted[src] = [...parts, tgt].join(',');
  }
  return inverted;
}

/** 存储用 来源→目标（可含逗号多目标）→ 目标→来源 */
export function fromFieldMapping(fieldMapping: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [source, targetRaw] of Object.entries(fieldMapping)) {
    const src = String(source || '').trim();
    if (!src || targetRaw == null) continue;
    for (const target of String(targetRaw)
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean)) {
      out[target] = src;
    }
  }
  return out;
}

/** @deprecated 请用 toFieldMapping / fromFieldMapping；保留别名以免旧引用断裂 */
export function invertFieldMapping(targetToSource: Record<string, string>): Record<string, string> {
  return toFieldMapping(targetToSource);
}

/** 连接器/接口停用属配置态，按普通提示处理，不走危险错误样式 */
export function isInactiveSyncSourceError(error: unknown): boolean {
  const raw =
    error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : '';
  return /已停用/.test(raw);
}

export function formatSyncErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  if (typeof error === 'string' && error.trim()) return error.trim();
  return fallback;
}

export function mappingFromBinding(
  columns: string[],
  bindingMapping: Record<string, string>,
): Record<string, string> {
  const ui = fromFieldMapping(bindingMapping);
  if (!columns.length) return ui;
  const columnSet = new Set(columns);
  const columnByLower = new Map(columns.map((column) => [column.toLowerCase(), column]));
  const out: Record<string, string> = {};
  for (const [target, source] of Object.entries(ui)) {
    if (columnSet.has(source)) {
      out[target] = source;
      continue;
    }
    const resolved = columnByLower.get(source.toLowerCase());
    if (resolved) out[target] = resolved;
  }
  return out;
}
