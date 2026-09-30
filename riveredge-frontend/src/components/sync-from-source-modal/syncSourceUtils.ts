/** 将数据接口响应体规范化为预览/映射用的行字典列表 */

/** 预览仅用于字段映射与样例核对；正式同步仍走服务端分页全量拉取 */
export const SYNC_PREVIEW_ROW_LIMIT = 50;

const KINGDEE_TARGET_ALIASES: Record<string, string[]> = {
  order_code: ['FBillNo', 'BillNo'],
  order_date: ['FDate'],
  delivery_date: ['FDeliveryDate'],
  customer_code: ['FCustId.FNumber', 'FNumber'],
  customer_name: ['FCustId.FName', 'FName'],
  supplier_code: ['FSupplierId.FNumber', 'FNumber'],
  supplier_name: ['FSupplierId.FName', 'FName'],
  forbid_status: ['FForbidStatus'],
  product_code: ['FMaterialId.FNumber'],
  product_name: ['FMaterialId.FName'],
  quantity: ['FQty', 'FPlanQty'],
  planned_start_date: ['FPlanStartDate'],
  planned_end_date: ['FPlanFinishDate', 'FPlanEndDate'],
  sales_order_code: ['FSaleOrderNo', 'FSrcBillNo'],
  document_status: ['FDocumentStatus'],
  close_status: ['FCloseStatus'],
  status: ['FStatus', 'FDocumentStatus'],
  base_unit: ['FBaseUnitId.FName', 'FBaseUnitId.FNumber', 'FUnitId.FName', 'FUnitId.FNumber'],
  base_unit_name: ['FBaseUnitId.FName', 'FUnitId.FName'],
  code: ['FName', 'FNumber'],
  name: ['FName'],
  short_name: ['FShortName'],
  main_code: ['FNumber'],
  specification: ['FSpecification', 'FMaterialId.FSpecification'],
  group_code: ['FMaterialGroup.FNumber'],
  group_name: ['FMaterialGroup.FName'],
  parent_code: ['FParentId.FNumber', 'FMaterialGroup.FParentId.FNumber'],
  'item.material_code': ['FMaterialId.FNumber'],
  'item.material_name': ['FMaterialId.FName'],
  'item.material_unit': ['FUnitId.FNumber', 'FBaseUnitId.FNumber'],
  'item.required_quantity': ['FQty'],
  'item.ordered_quantity': ['FQty'],
  'item.unit_price': ['FPrice', 'FTaxPrice'],
  'item.tax_rate': ['FEntryTaxRate'],
  'item.delivery_date': ['FDeliveryDate'],
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

/**
 * 预览时压低金蝶 ExecuteBillQuery 的 Limit，避免一次拉 2000 行进弹窗。
 * 浅拷贝 body 并重写 parameters[0] 内 Limit/StartRow；无法解析时原样返回供调用方兜底 slice。
 */
export function withKingdeePreviewLimit(
  requestBody: Record<string, unknown> | null | undefined,
  limit: number = SYNC_PREVIEW_ROW_LIMIT,
): Record<string, unknown> | undefined {
  if (!requestBody || typeof requestBody !== 'object') return undefined;
  const cloned = structuredClone(requestBody) as Record<string, unknown>;
  const params = cloned.parameters;
  if (!Array.isArray(params) || params.length === 0) return cloned;

  let query: Record<string, unknown>;
  const first = params[0];
  if (typeof first === 'string') {
    try {
      query = JSON.parse(first) as Record<string, unknown>;
    } catch {
      return cloned;
    }
  } else if (typeof first === 'object' && first !== null) {
    query = { ...(first as Record<string, unknown>) };
  } else {
    return cloned;
  }

  query.Limit = limit;
  query.StartRow = 0;
  params[0] = JSON.stringify(query);
  cloned.parameters = params;
  return cloned;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** 与接口测试预览一致：解包 data.rows / items / records 等嵌套数组。 */
function extractArrayFromObject(body: Record<string, unknown>, depth = 0): unknown[] | null {
  const candidates = ['data', 'items', 'rows', 'records', 'Results', 'result', 'list'];
  for (const key of candidates) {
    const value = body[key];
    if (Array.isArray(value)) {
      return value;
    }
  }
  if (depth >= 2) {
    return null;
  }
  for (const key of candidates) {
    const value = body[key];
    if (isPlainObject(value)) {
      const nested = extractArrayFromObject(value, depth + 1);
      if (nested) {
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

export function normalizeApiBodyToRows(
  body: unknown,
  columnNames?: string[],
): Record<string, unknown>[] {
  const normalized = normalizeBodyValue(body);
  if (normalized == null) return [];
  if (isPlainObject(normalized) && 'error' in normalized) {
    throw new Error(String(normalized.error));
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
    if (nested) {
      return normalizeApiBodyToRows(nested, columnNames);
    }
    return [normalized];
  }
  return [{ value: normalized }];
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

function columnMatchesTarget(column: string, target: string): boolean {
  const col = column.trim();
  const tgt = target.trim();
  if (!col || !tgt) return false;
  if (col === tgt) return true;
  const aliases = KINGDEE_TARGET_ALIASES[tgt] ?? [];
  if (aliases.includes(col)) return true;
  const colLower = col.toLowerCase();
  const tgtLower = tgt.replace(/^item\./, '').toLowerCase();
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

export function suggestTargetToSourceMapping(
  columns: string[],
  targetFields: string[],
): Record<string, string> {
  const mapping: Record<string, string> = {};
  for (const target of targetFields) {
    const hit = columns.find((column) => columnMatchesTarget(column, target));
    if (hit) mapping[target] = hit;
  }
  return mapping;
}

export function invertFieldMapping(targetToSource: Record<string, string>): Record<string, string> {
  const inverted: Record<string, string> = {};
  for (const [target, source] of Object.entries(targetToSource)) {
    if (source && target) inverted[source] = target;
  }
  return inverted;
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
  const ui: Record<string, string> = {};
  const hasColumns = columns.length > 0;
  for (const [source, target] of Object.entries(bindingMapping)) {
    if (!source || !target) continue;
    // 无预览列时仍恢复绑定，再次同步无需重新映射
    if (!hasColumns || columns.includes(source)) {
      ui[String(target)] = String(source);
    }
  }
  return ui;
}
