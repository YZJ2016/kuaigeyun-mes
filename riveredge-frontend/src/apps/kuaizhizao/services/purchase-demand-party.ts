/**
 * 采购询价需方 API
 */
import { apiRequest } from '../../../services/api';

export interface PurchaseDemandParty {
  id: number;
  tenant_id?: number;
  code: string;
  name: string;
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
  address?: string | null;
  tax_no?: string | null;
  notes?: string | null;
  is_active: boolean;
  sort_order?: number;
}

const base = '/apps/kuaizhizao/purchase-demand-parties';

export async function listPurchaseDemandParties(params?: {
  keyword?: string;
  is_active?: boolean;
  skip?: number;
  limit?: number;
}): Promise<{ data: PurchaseDemandParty[]; total: number; success: boolean }> {
  return apiRequest(base, { method: 'GET', params });
}

export async function createPurchaseDemandParty(
  data: Partial<PurchaseDemandParty>,
): Promise<PurchaseDemandParty> {
  return apiRequest(base, { method: 'POST', data });
}

export async function updatePurchaseDemandParty(
  id: number,
  data: Partial<PurchaseDemandParty>,
): Promise<PurchaseDemandParty> {
  return apiRequest(`${base}/${id}`, { method: 'PUT', data });
}

export async function deletePurchaseDemandParty(id: number): Promise<void> {
  return apiRequest(`${base}/${id}`, { method: 'DELETE' });
}
