import { apiRequest } from '../../../services/api';
import type {
  RdProjectDeliverable,
  RdProjectDeliverableVersionListResponse,
} from './rd-project';

const BASE = '/apps/kuaiplm/rd-deliverables';

export interface RdDeliverableListQuery {
  skip?: number;
  limit?: number;
  keyword?: string;
  deliverable_type?: string;
  material_code?: string;
  project_id?: number;
  unlinked_only?: boolean;
  linked_only?: boolean;
}

export interface RdDeliverableListResponse {
  items: RdProjectDeliverable[];
  total: number;
}

export type RdDeliverablePayload = Partial<RdProjectDeliverable> & {
  project_id?: number | null;
  project_code?: string | null;
};

export async function listRdDeliverables(
  params: RdDeliverableListQuery = {},
): Promise<RdDeliverableListResponse> {
  return apiRequest<RdDeliverableListResponse>(BASE, { method: 'GET', params });
}

export async function getRdDeliverable(id: number | string): Promise<RdProjectDeliverable> {
  return apiRequest<RdProjectDeliverable>(`${BASE}/${id}`, { method: 'GET' });
}

export async function createRdDeliverable(data: RdDeliverablePayload): Promise<RdProjectDeliverable> {
  return apiRequest<RdProjectDeliverable>(BASE, { method: 'POST', data });
}

export async function updateRdDeliverable(
  id: number | string,
  data: RdDeliverablePayload,
): Promise<RdProjectDeliverable> {
  return apiRequest<RdProjectDeliverable>(`${BASE}/${id}`, { method: 'PUT', data });
}

export async function deleteRdDeliverable(id: number | string): Promise<void> {
  return apiRequest<void>(`${BASE}/${id}`, { method: 'DELETE' });
}

export async function listRdDeliverableVersions(
  id: number | string,
): Promise<RdProjectDeliverableVersionListResponse> {
  return apiRequest<RdProjectDeliverableVersionListResponse>(`${BASE}/${id}/versions`, {
    method: 'GET',
  });
}

export async function reviseRdDeliverable(
  id: number | string,
  data: {
    version?: string;
    change_summary?: string;
    file_url?: string;
    file_name?: string;
    file_uuid?: string;
  },
): Promise<RdProjectDeliverable> {
  return apiRequest<RdProjectDeliverable>(`${BASE}/${id}/revise`, { method: 'POST', data });
}

export async function submitRdDeliverable(id: number | string): Promise<RdProjectDeliverable> {
  return apiRequest<RdProjectDeliverable>(`${BASE}/${id}/submit`, { method: 'POST' });
}

export async function approveRdDeliverable(id: number | string): Promise<RdProjectDeliverable> {
  return apiRequest<RdProjectDeliverable>(`${BASE}/${id}/approve`, { method: 'POST' });
}

export async function rejectRdDeliverable(
  id: number | string,
  reason?: string,
): Promise<RdProjectDeliverable> {
  return apiRequest<RdProjectDeliverable>(`${BASE}/${id}/reject`, {
    method: 'POST',
    data: reason ? { reason } : {},
  });
}
