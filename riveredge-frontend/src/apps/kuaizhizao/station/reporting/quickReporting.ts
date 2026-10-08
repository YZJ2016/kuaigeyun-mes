/**
 * 工位快捷报工请求体。写入只组装现有 POST /reporting/quick 与附属接口的字段。
 * 渠道不放进 body，由 apiRequest 的 X-Client-Channel 携带。
 */

export type StationReportMode = 'self' | 'team';

export type StationOperator = {
  id: number;
  name: string;
};

export type QuickReportRefusal =
  | 'missing-operator'
  | 'missing-team'
  | 'missing-workstation'
  | 'missing-work-order'
  | 'missing-operation'
  | 'quantity-not-positive'
  | 'missing-defect-reason'
  | 'missing-reported-at'
  | 'invalid-work-hours';

export type QuickReportInput = {
  mode: StationReportMode;
  workstationId: number | null;
  operator: StationOperator | null;
  team: { id: number; name: string } | null;
  workOrder: {
    id?: number | null;
    code?: string | null;
    name?: string | null;
    product_name?: string | null;
  } | null;
  operation: {
    operation_id?: number | null;
    operation_code?: string | null;
    operation_name?: string | null;
  } | null;
  qualifiedQuantity: number;
  unqualifiedQuantity: number;
  workHours: number;
  reportedAt: string;
  defectReason?: string;
  remarks?: string;
};

export type QuickReportDecision =
  | { submit: true; body: Record<string, unknown> }
  | { submit: false; reason: QuickReportRefusal };

/** 与报工页 resolveWorkOrderDisplayName 相同的名称回退。 */
export function workOrderDisplayName(workOrder: {
  name?: string | null;
  product_name?: string | null;
  code?: string | null;
} | null | undefined): string {
  if (!workOrder) return '';
  return (
    String(workOrder.name ?? '').trim()
    || String(workOrder.product_name ?? '').trim()
    || String(workOrder.code ?? '').trim()
  );
}

export function parseWorkstationId(raw: unknown): number | null {
  if (typeof raw === 'number' && Number.isInteger(raw) && raw > 0) return raw;
  if (typeof raw !== 'string') return null;
  const text = raw.trim();
  if (!text) return null;
  const n = Number(text);
  if (!Number.isInteger(n) || n <= 0) return null;
  return n;
}

/** 页面已绑定工位优先，否则读 URL query `workstationId`。 */
export function resolveWorkstationId(bound: unknown, queryRaw: unknown): number | null {
  return parseWorkstationId(bound) ?? parseWorkstationId(queryRaw);
}

function positiveInt(raw: unknown): number | null {
  const n = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isInteger(n) || n <= 0) return null;
  return n;
}

function finiteNonNegative(raw: unknown): number | null {
  const n = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isFinite(n) || n < 0) return null;
  return n;
}

export function buildQuickReportingBody(input: QuickReportInput): QuickReportDecision {
  const workstationId = parseWorkstationId(input.workstationId);
  if (workstationId == null) {
    return { submit: false, reason: 'missing-workstation' };
  }

  const workOrderId = positiveInt(input.workOrder?.id);
  const workOrderCode = String(input.workOrder?.code ?? '').trim();
  const workOrderName = workOrderDisplayName(input.workOrder);
  if (workOrderId == null || !workOrderCode || !workOrderName) {
    return { submit: false, reason: 'missing-work-order' };
  }

  const operationId = positiveInt(input.operation?.operation_id);
  const operationCode = String(input.operation?.operation_code ?? '').trim();
  const operationName = String(input.operation?.operation_name ?? '').trim();
  if (operationId == null || !operationCode || !operationName) {
    return { submit: false, reason: 'missing-operation' };
  }

  const qualified = finiteNonNegative(input.qualifiedQuantity);
  const unqualified = finiteNonNegative(input.unqualifiedQuantity);
  if (qualified == null || unqualified == null || qualified + unqualified <= 0) {
    return { submit: false, reason: 'quantity-not-positive' };
  }

  const workHours = finiteNonNegative(input.workHours);
  if (workHours == null) {
    return { submit: false, reason: 'invalid-work-hours' };
  }
  const reportedAt = String(input.reportedAt ?? '').trim();
  if (!reportedAt) {
    return { submit: false, reason: 'missing-reported-at' };
  }

  const body: Record<string, unknown> = {
    work_order_id: workOrderId,
    work_order_code: workOrderCode,
    work_order_name: workOrderName,
    operation_id: operationId,
    operation_code: operationCode,
    operation_name: operationName,
    reported_quantity: qualified + unqualified,
    qualified_quantity: qualified,
    unqualified_quantity: unqualified,
    work_hours: workHours,
    reported_at: reportedAt,
    status: 'pending',
    device_info: { workstation_id: workstationId },
  };

  const remarks = String(input.remarks ?? '').trim();
  if (remarks) body.remarks = remarks;

  if (unqualified > 0) {
    const defectReason = String(input.defectReason ?? '').trim();
    if (!defectReason) {
      return { submit: false, reason: 'missing-defect-reason' };
    }
    body.defect = {
      defect_quantity: unqualified,
      defect_reason: defectReason,
    };
  }

  if (input.mode === 'team') {
    const teamId = positiveInt(input.team?.id);
    const teamName = String(input.team?.name ?? '').trim();
    if (teamId == null || !teamName) {
      return { submit: false, reason: 'missing-team' };
    }
    body.team_id = teamId;
    body.team_name = teamName;
    body.worker_name = teamName;
    return { submit: true, body };
  }

  // 工位只保留已确认操作员的本人报工；不提供独立代报入口
  const personId = positiveInt(input.operator?.id);
  const personName = String(input.operator?.name ?? '').trim();
  if (personId == null || !personName) {
    return { submit: false, reason: 'missing-operator' };
  }
  body.worker_id = personId;
  body.worker_name = personName;
  return { submit: true, body };
}

export type MaterialBindingRefusal = 'missing-material' | 'quantity-not-positive';

export function buildMaterialBindingBody(input: {
  bindingType: 'feeding' | 'discharging';
  materialId: unknown;
  quantity: unknown;
  materialCode?: string | null;
  materialName?: string | null;
}): { submit: true; body: Record<string, unknown> } | { submit: false; reason: MaterialBindingRefusal } {
  const materialId = positiveInt(input.materialId);
  if (materialId == null) return { submit: false, reason: 'missing-material' };
  const quantity = finiteNonNegative(input.quantity);
  if (quantity == null || quantity <= 0) return { submit: false, reason: 'quantity-not-positive' };
  const body: Record<string, unknown> = {
    binding_type: input.bindingType,
    material_id: materialId,
    quantity,
  };
  const materialCode = String(input.materialCode ?? '').trim();
  const materialName = String(input.materialName ?? '').trim();
  if (materialCode) body.material_code = materialCode;
  if (materialName) body.material_name = materialName;
  return { submit: true, body };
}

export type ScrapRefusal = 'quantity-not-positive' | 'missing-scrap-reason' | 'exceeds-unqualified';

const SCRAP_TYPES = new Set(['process', 'material', 'quality', 'equipment', 'other']);

export function buildScrapBody(input: {
  scrapQuantity: unknown;
  scrapReason: unknown;
  scrapType?: unknown;
  unqualifiedQuantity?: unknown;
}): { submit: true; body: Record<string, unknown> } | { submit: false; reason: ScrapRefusal } {
  const scrapQuantity = finiteNonNegative(input.scrapQuantity);
  if (scrapQuantity == null || scrapQuantity <= 0) {
    return { submit: false, reason: 'quantity-not-positive' };
  }
  const scrapReason = String(input.scrapReason ?? '').trim();
  if (!scrapReason) return { submit: false, reason: 'missing-scrap-reason' };
  if (input.unqualifiedQuantity != null) {
    const cap = finiteNonNegative(input.unqualifiedQuantity);
    if (cap != null && scrapQuantity > cap) {
      return { submit: false, reason: 'exceeds-unqualified' };
    }
  }
  const scrapTypeRaw = String(input.scrapType ?? '').trim();
  const body: Record<string, unknown> = {
    scrap_quantity: scrapQuantity,
    scrap_reason: scrapReason,
  };
  if (SCRAP_TYPES.has(scrapTypeRaw)) body.scrap_type = scrapTypeRaw;
  return { submit: true, body };
}

export function rowsFromListResponse<T>(raw: unknown): T[] {
  if (Array.isArray(raw)) return raw as T[];
  if (raw && typeof raw === 'object' && Array.isArray((raw as { data?: unknown }).data)) {
    return (raw as { data: T[] }).data;
  }
  return [];
}
