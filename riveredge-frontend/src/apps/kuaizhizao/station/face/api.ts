import { apiRequest } from '../../../../services/api';

const STATION = '/apps/kuaizhizao/station';

export interface FaceTemplateResponse {
  id: number;
  user_id: number;
  quality?: number | null;
  device_info?: string | null;
  created_at: string;
}

export interface ShiftSummaryResponse {
  workstation_id?: number | null;
  shift_start: string;
  shift_end: string;
  planned_qty: string | number;
  completed_qty: string | number;
  unqualified_qty: string | number;
  downtime_minutes: string | number;
  andon_count: number;
  reporting_count: number;
}

export interface ShiftHandoverCreate {
  workstation_id?: number | null;
  workstation_name?: string | null;
  shift_start: string;
  shift_end?: string | null;
  remarks?: string | null;
}

export interface ShiftHandoverResponse {
  id: number;
  uuid: string;
  workstation_id?: number | null;
  workstation_name?: string | null;
  operator_id: number;
  operator_name: string;
  shift_start: string;
  shift_end: string;
  planned_qty: string | number;
  completed_qty: string | number;
  unqualified_qty: string | number;
  downtime_minutes: string | number;
  andon_count: number;
  remarks?: string | null;
  created_at: string;
}

export interface StationDocFileItem {
  key: string;
  name: string;
  file_uuid?: string | null;
  url?: string | null;
  source: string;
  drawing_code?: string | null;
  drawing_revision?: string | null;
}

export interface StationSopStep {
  id: string;
  type: string;
  title: string;
  description?: string | null;
  key_points?: string | null;
  attachment_uuids?: string[];
}

export interface StationSopDocument {
  uuid: string;
  name?: string | null;
  version?: string | null;
  current_revision?: string | null;
  carrier?: string | null;
  storage_location?: string | null;
  station_copy_no?: string | null;
  content?: string | null;
  steps?: StationSopStep[];
  attachments?: StationDocFileItem[];
}

export interface StationOperationDocumentsResponse {
  work_order_id: number;
  operation_id: number;
  master_operation_id?: number | null;
  material_uuid?: string | null;
  process_route_uuid?: string | null;
  operation_uuid?: string | null;
  sop?: StationSopDocument | null;
  drawings?: StationDocFileItem[];
  esop_available: boolean;
  drawings_available: boolean;
}

export interface StationWorkOrderDocumentFlags {
  work_order_id: number;
  has_esop: boolean;
  has_drawings: boolean;
  has_docs: boolean;
}

export interface StationWorkOrderDocumentFlagsResponse {
  items: StationWorkOrderDocumentFlags[];
}

export interface FaceEnrollRequest {
  user_id: number;
  descriptor: number[];
}

export interface FaceIdentifyResponse {
  matched: boolean;
  score: number;
  user_id: number;
  username: string;
  full_name: string;
  template_id: number;
}

export function enrollFaceTemplate(body: FaceEnrollRequest): Promise<FaceTemplateResponse> {
  return apiRequest<FaceTemplateResponse>(`${STATION}/face-templates`, {
    method: 'POST',
    data: body,
    stationOperatorSession: true,
  });
}

export function identifyFace(descriptor: number[]): Promise<FaceIdentifyResponse> {
  return apiRequest<FaceIdentifyResponse>(`${STATION}/face-identify`, {
    method: 'POST',
    data: { descriptor },
  });
}

export function listMyFaceTemplates(): Promise<FaceTemplateResponse[]> {
  return apiRequest<FaceTemplateResponse[]>(`${STATION}/face-templates/me`, {
    method: 'GET',
    stationOperatorSession: true,
  });
}

export function deleteFaceTemplate(templateId: number): Promise<{ deleted: boolean }> {
  return apiRequest<{ deleted: boolean }>(`${STATION}/face-templates/${templateId}`, {
    method: 'DELETE',
    stationOperatorSession: true,
  });
}

export function getShiftSummary(params: {
  workstation_id: number;
  shift_start: string;
  shift_end: string;
}): Promise<ShiftSummaryResponse> {
  return apiRequest<ShiftSummaryResponse>(`${STATION}/shift-summary`, {
    method: 'GET',
    params,
  });
}

export function confirmShiftHandover(body: ShiftHandoverCreate): Promise<ShiftHandoverResponse> {
  return apiRequest<ShiftHandoverResponse>(`${STATION}/shift-handover`, {
    method: 'POST',
    data: body,
    stationOperatorSession: true,
  });
}

export function getWorkOrderDocumentFlags(
  workOrderIds: number[],
): Promise<StationWorkOrderDocumentFlagsResponse> {
  return apiRequest<StationWorkOrderDocumentFlagsResponse>(
    `${STATION}/work-orders/document-flags`,
    {
      method: 'GET',
      params: { ids: workOrderIds.join(',') },
    },
  );
}

export function getOperationDocuments(
  workOrderId: number,
  operationId: number,
): Promise<StationOperationDocumentsResponse> {
  return apiRequest<StationOperationDocumentsResponse>(
    `${STATION}/work-orders/${workOrderId}/operations/${operationId}/documents`,
    { method: 'GET' },
  );
}
