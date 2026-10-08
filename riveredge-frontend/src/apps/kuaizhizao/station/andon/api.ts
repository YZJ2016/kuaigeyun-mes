/**
 * 工位安灯页调用的现有接口。路径与请求体对齐后端路由，不在此新增契约。
 */
import { apiRequest, formatApiErrorDetail } from '../../../../services/api';
import { getEquipmentList } from '../../../../services/equipment';
import { searchUserDisplay } from '../../../../services/user';
import { workOrderApi } from '../../services/work-order';

const PAGE_SIZE = 50;

export const ANDON_CALL_TYPES = [
  { value: 'quality', label: '质量' },
  { value: 'material', label: '物料' },
  { value: 'equipment', label: '设备' },
  { value: 'supervisor', label: '班长' },
] as const;

export type AndonCallType = (typeof ANDON_CALL_TYPES)[number]['value'];

export const FAULT_LEVELS = ['轻微', '一般', '严重', '紧急'] as const;

export type FaultLevel = (typeof FAULT_LEVELS)[number];

/** 物料安灯唯一允许的叫料模式。 */
export const MATERIAL_CALL_MODE = 'FULL_ORDER';

export type StationAndonCreateBody = {
  call_type: AndonCallType;
  workstation_id: number;
  workstation_name?: string;
  work_order_id?: number;
  work_order_code?: string;
  operation_id?: number;
  remarks?: string;
  equipment_uuid?: string;
  fault_level?: FaultLevel;
  material_call_mode?: typeof MATERIAL_CALL_MODE;
  supervisor_user_id?: number;
};

export type StationAndonRecord = {
  id: number;
  callType: string;
  status: string;
  workOrderId: number | null;
  workOrderCode: string;
  operationId: number | null;
  workstationId: number | null;
  workstationName: string;
  callerId: number;
  callerName: string;
  remarks: string;
  relatedDocType: string;
  relatedDocCode: string;
  equipmentUuid: string;
  faultLevel: string;
  materialCallMode: string;
  supervisorUserId: number | null;
  createdAt: string;
};

export type WorkOrderChoice = {
  id: number;
  code: string;
  name: string;
};

export type OperationChoice = {
  /** 工单工序行 id，对应开工路径里的 operation_id。 */
  id: number;
  name: string;
  code: string;
  sequence: number;
};

export type EquipmentChoice = {
  uuid: string;
  code: string;
  name: string;
};

export type SupervisorChoice = {
  id: number;
  label: string;
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

function readRows(payload: unknown): unknown[] {
  if (Array.isArray(payload)) return payload;
  const envelope = asRecord(payload);
  if (Array.isArray(envelope?.data)) return envelope.data;
  if (Array.isArray(envelope?.items)) return envelope.items;
  if (Array.isArray(envelope?.operations)) return envelope.operations;
  return [];
}

function readAndon(value: unknown): StationAndonRecord | null {
  const row = asRecord(value);
  const id = intId(row?.id);
  const callerId = intId(row?.caller_id);
  if (!row || id == null || callerId == null) return null;
  return {
    id,
    callType: text(row.call_type),
    status: text(row.status),
    workOrderId: intId(row.work_order_id),
    workOrderCode: text(row.work_order_code),
    operationId: intId(row.operation_id),
    workstationId: intId(row.workstation_id),
    workstationName: text(row.workstation_name),
    callerId,
    callerName: text(row.caller_name),
    remarks: text(row.remarks),
    relatedDocType: text(row.related_doc_type),
    relatedDocCode: text(row.related_doc_code),
    equipmentUuid: text(row.equipment_uuid),
    faultLevel: text(row.fault_level),
    materialCallMode: text(row.material_call_mode),
    supervisorUserId: intId(row.supervisor_user_id),
    createdAt: text(row.created_at),
  };
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

export async function listWorkOrders(keyword: string): Promise<WorkOrderChoice[]> {
  const params: Record<string, string | number | boolean> = {
    skip: 0,
    limit: PAGE_SIZE,
    include_readiness: false,
    include_downstream_push_progress: false,
  };
  const q = keyword.trim();
  if (q) params.keyword = q;
  const payload = await workOrderApi.list(params);
  const rows: WorkOrderChoice[] = [];
  for (const item of readRows(payload)) {
    const row = asRecord(item);
    const id = intId(row?.id);
    if (!row || id == null) continue;
    rows.push({
      id,
      code: text(row.code),
      name: text(row.name) || text(row.product_name),
    });
  }
  return rows;
}

export async function listOperationRows(workOrderId: number): Promise<OperationChoice[]> {
  const payload = await workOrderApi.getOperations(String(workOrderId));
  const rows: OperationChoice[] = [];
  for (const item of readRows(payload)) {
    const row = asRecord(item);
    const id = intId(row?.id);
    if (!row || id == null) continue;
    rows.push({
      id,
      name: text(row.operation_name),
      code: text(row.operation_code),
      sequence: intId(row.sequence) ?? 0,
    });
  }
  rows.sort((a, b) => a.sequence - b.sequence);
  return rows;
}

export async function listEquipment(keyword: string): Promise<EquipmentChoice[]> {
  const q = keyword.trim();
  const payload = await getEquipmentList({
    skip: 0,
    limit: PAGE_SIZE,
    is_active: true,
    ...(q ? { search: q } : {}),
  });
  const rows: EquipmentChoice[] = [];
  for (const item of payload?.items ?? []) {
    const uuid = text(item?.uuid).trim();
    if (!uuid) continue;
    rows.push({
      uuid,
      code: text(item.code),
      name: text(item.name),
    });
  }
  return rows;
}

export async function searchSupervisors(keyword: string): Promise<SupervisorChoice[]> {
  const q = keyword.trim();
  const payload = await searchUserDisplay({
    page: 1,
    page_size: PAGE_SIZE,
    is_active: true,
    ...(q ? { keyword: q } : {}),
  });
  const rows: SupervisorChoice[] = [];
  for (const item of payload?.items ?? []) {
    const id = intId(item?.id);
    if (id == null) continue;
    rows.push({
      id,
      label: text(item.label) || text(item.full_name) || text(item.username) || String(id),
    });
  }
  return rows;
}

export async function listAndonCalls(workstationId: number): Promise<StationAndonRecord[]> {
  const payload = await apiRequest<unknown>('/apps/kuaizhizao/station/andon', {
    method: 'GET',
    params: { workstation_id: workstationId },
  });
  return readRows(payload).map(readAndon).filter((row): row is StationAndonRecord => row != null);
}

export async function listOpenAndonCalls(workstationId: number): Promise<StationAndonRecord[]> {
  const payload = await apiRequest<unknown>('/apps/kuaizhizao/station/andon/open', {
    method: 'GET',
    params: { workstation_id: workstationId },
  });
  return readRows(payload).map(readAndon).filter((row): row is StationAndonRecord => row != null);
}

export async function createAndonCall(body: StationAndonCreateBody): Promise<StationAndonRecord | null> {
  const payload = await apiRequest<unknown>('/apps/kuaizhizao/station/andon', {
    method: 'POST',
    data: body,
    stationOperatorSession: true,
  });
  return readAndon(payload);
}

export async function acknowledgeAndon(andonId: number): Promise<StationAndonRecord | null> {
  const payload = await apiRequest<unknown>(
    `/apps/kuaizhizao/station/andon/${andonId}/acknowledge`,
    { method: 'POST', stationOperatorSession: true },
  );
  return readAndon(payload);
}

export async function closeAndon(andonId: number): Promise<StationAndonRecord | null> {
  const payload = await apiRequest<unknown>(
    `/apps/kuaizhizao/station/andon/${andonId}/close`,
    { method: 'POST', stationOperatorSession: true },
  );
  return readAndon(payload);
}

export async function cancelAndon(andonId: number): Promise<StationAndonRecord | null> {
  const payload = await apiRequest<unknown>(
    `/apps/kuaizhizao/station/andon/${andonId}/cancel`,
    { method: 'POST', stationOperatorSession: true },
  );
  return readAndon(payload);
}
