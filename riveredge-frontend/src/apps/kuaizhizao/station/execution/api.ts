/**
 * 工位执行页调用的现有接口。路径与请求体对齐后端路由，不在此新增契约。
 */
import { apiRequest, formatApiErrorDetail } from '../../../../services/api';
import { workOrderApi } from '../../services/work-order';

const PAGE_SIZE = 50;

export const DOWNTIME_REASONS = [
  { code: 'material_shortage', label: '缺料' },
  { code: 'material_wait', label: '待料' },
  { code: 'equipment_fault', label: '设备故障' },
  { code: 'tool_change', label: '换刀/换模' },
  { code: 'quality_issue', label: '质量异常' },
  { code: 'break', label: '休息' },
  { code: 'other', label: '其他' },
] as const;

export type StationWorkOrder = {
  id: number;
  code: string;
  productName: string;
  productCode: string;
  quantity: string;
  status: string;
};

export type StationOperation = {
  id: number;
  name: string;
  code: string;
  sequence: number;
  status: string;
  machineSessionState: string;
  qualifiedQuantity: string;
};

export type SopDocumentRef = {
  uuid: string;
  revision: string;
};

export type SkillCheckResult = {
  qualified: boolean;
  message: string;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function text(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '';
}

function intId(value: unknown): number | null {
  if (typeof value === 'number' && Number.isInteger(value)) return value;
  if (typeof value === 'string' && /^\d+$/.test(value)) return Number(value);
  return null;
}

function readWorkOrder(value: unknown): StationWorkOrder | null {
  const row = asRecord(value);
  const id = intId(row?.id);
  if (!row || id == null) return null;
  return {
    id,
    code: text(row.code),
    productName: text(row.product_name),
    productCode: text(row.product_code),
    quantity: text(row.quantity),
    status: text(row.status),
  };
}

function readListRows(payload: unknown): { rows: StationWorkOrder[]; fullPage: boolean } {
  const envelope = asRecord(payload);
  const raw = Array.isArray(payload)
    ? payload
    : Array.isArray(envelope?.data)
      ? envelope.data
      : [];
  const rows = raw.map(readWorkOrder).filter((row): row is StationWorkOrder => row != null);
  return { rows, fullPage: raw.length >= PAGE_SIZE };
}

export function readOperations(payload: unknown): StationOperation[] {
  const envelope = asRecord(payload);
  const raw = Array.isArray(payload)
    ? payload
    : Array.isArray(envelope?.operations)
      ? envelope.operations
      : [];
  const rows: StationOperation[] = [];
  for (const item of raw) {
    const row = asRecord(item);
    const id = intId(row?.id);
    if (!row || id == null) continue;
    rows.push({
      id,
      name: text(row.operation_name),
      code: text(row.operation_code),
      sequence: intId(row.sequence) ?? 0,
      status: text(row.status),
      machineSessionState: text(row.machine_session_state) || 'none',
      qualifiedQuantity: text(row.qualified_quantity),
    });
  }
  rows.sort((a, b) => a.sequence - b.sequence);
  return rows;
}

export function readSopRef(payload: unknown): SopDocumentRef | null {
  const body = asRecord(payload);
  const sop = asRecord(body?.sop);
  const uuid = text(sop?.uuid).trim();
  if (!uuid) return null;
  const revision = text(sop?.current_revision).trim() || text(sop?.version).trim();
  return { uuid, revision };
}

export function readSkillCheck(payload: unknown): SkillCheckResult {
  const body = asRecord(payload);
  return {
    qualified: body?.qualified === true,
    message: text(body?.message),
  };
}

export function readSopAcknowledged(payload: unknown): boolean {
  return asRecord(payload)?.acknowledged === true;
}

export function apiErrorText(error: unknown): string {
  const response = asRecord(asRecord(error)?.response);
  const data = asRecord(response?.data);
  const detail = formatApiErrorDetail(data?.detail);
  if (detail) return detail;
  const message = formatApiErrorDetail(data?.message);
  if (message) return message;
  if (error instanceof Error && error.message) return error.message;
  return '请求失败';
}

export async function listExecutableWorkOrders(skip: number): Promise<{
  rows: StationWorkOrder[];
  hasMore: boolean;
}> {
  const params = { skip, limit: PAGE_SIZE, include_readiness: false };
  const [released, inProgress] = await Promise.all([
    workOrderApi.list({ ...params, status: 'released' }),
    workOrderApi.list({ ...params, status: 'in_progress' }),
  ]);
  const releasedPage = readListRows(released);
  const inProgressPage = readListRows(inProgress);
  const byId = new Map<number, StationWorkOrder>();
  for (const row of [...inProgressPage.rows, ...releasedPage.rows]) {
    byId.set(row.id, row);
  }
  const rows = [...byId.values()].sort((a, b) => a.code.localeCompare(b.code));
  return { rows, hasMore: releasedPage.fullPage || inProgressPage.fullPage };
}

export async function listOperations(workOrderId: number): Promise<StationOperation[]> {
  const payload = await workOrderApi.getOperations(String(workOrderId));
  return readOperations(payload);
}

export function startOperation(workOrderId: number, operationId: number) {
  return workOrderApi.startOperation(String(workOrderId), operationId, {
    stationOperatorSession: true,
  });
}

export function withdrawOperationStart(workOrderId: number, operationId: number) {
  return workOrderApi.withdrawOperationStart(String(workOrderId), operationId, {
    stationOperatorSession: true,
  });
}

export function pauseOperation(
  workOrderId: number,
  operationId: number,
  reasonCode: string,
  workstationId: number | null,
) {
  const data: { reason_code: string; workstation_id?: number } = { reason_code: reasonCode };
  if (workstationId != null) data.workstation_id = workstationId;
  return apiRequest(
    `/apps/kuaizhizao/work-orders/${workOrderId}/operations/${operationId}/pause`,
    { method: 'POST', data, stationOperatorSession: true },
  );
}

export function resumeOperation(workOrderId: number, operationId: number) {
  return apiRequest(
    `/apps/kuaizhizao/work-orders/${workOrderId}/operations/${operationId}/resume`,
    { method: 'POST', stationOperatorSession: true },
  );
}

export function completeOperation(workOrderId: number, operationId: number) {
  return apiRequest(
    `/apps/kuaizhizao/work-orders/${workOrderId}/operations/${operationId}/complete`,
    { method: 'POST', data: {}, stationOperatorSession: true },
  );
}

export function setMachineSession(
  workOrderId: number,
  operationId: number,
  action: 'on' | 'off',
) {
  return apiRequest(
    `/apps/kuaizhizao/work-orders/${workOrderId}/operations/${operationId}/machine-session`,
    { method: 'POST', data: { action }, stationOperatorSession: true },
  );
}

export function getStationOperationDocuments(workOrderId: number, operationId: number) {
  return apiRequest(
    `/apps/kuaizhizao/station/work-orders/${workOrderId}/operations/${operationId}/documents`,
    { method: 'GET' },
  );
}

export function checkSopAcknowledgment(query: {
  workOrderId: number;
  operationId: number;
  sopUuid: string;
  workerId: number;
}) {
  return apiRequest('/apps/kuaizhizao/station/sop-acknowledgments/check', {
    method: 'GET',
    params: {
      work_order_id: query.workOrderId,
      operation_id: query.operationId,
      sop_uuid: query.sopUuid,
      worker_id: query.workerId,
    },
  });
}

export function acknowledgeSop(body: {
  sopUuid: string;
  revision: string;
  workOrderId: number;
  operationId: number;
  workerId: number;
  workerName: string;
}) {
  const data: {
    sop_uuid: string;
    sop_revision?: string;
    work_order_id: number;
    operation_id: number;
    worker_id: number;
    worker_name?: string;
  } = {
    sop_uuid: body.sopUuid,
    work_order_id: body.workOrderId,
    operation_id: body.operationId,
    worker_id: body.workerId,
  };
  if (body.revision) data.sop_revision = body.revision;
  if (body.workerName) data.worker_name = body.workerName;
  return apiRequest('/apps/kuaizhizao/station/sop-acknowledgments', {
    method: 'POST',
    data,
    stationOperatorSession: true,
  });
}

export function checkOperatorSkill(body: {
  userId: number;
  operationId: number;
  workOrderId: number;
}) {
  return apiRequest('/apps/kuaizhizao/station/skill-check', {
    method: 'POST',
    data: {
      user_id: body.userId,
      operation_id: body.operationId,
      work_order_id: body.workOrderId,
    },
  });
}
