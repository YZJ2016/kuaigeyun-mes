import { apiRequest } from '../../../services/api';

export type PurchaseArrivalWarningLevel = 'normal' | 'imminent' | 'overdue';

export type PurchaseArrivalProcessingStatus =
  | 'unprocessed'
  | 'reported'
  | 'submitted'
  | 'pending_review'
  | 'approved'
  | 'change_pending'
  | 'changed'
  | 'rejected';

export interface PurchaseArrivalWarningRow {
  id: number;
  purchase_order_id: number;
  purchase_order_item_id: number;
  order_code: string;
  supplier_name?: string;
  buyer_name?: string;
  material_code?: string;
  material_name?: string;
  required_date?: string;
  outstanding_quantity?: number;
  warning_level?: PurchaseArrivalWarningLevel;
  day_offset?: number;
  remaining_days?: number;
  overdue_days?: number;
  processing_status?: PurchaseArrivalProcessingStatus;
  impacted_assembly?: string;
  delay_report_id?: number;
  delay_status?: string | null;
  delay_review_status?: string | null;
  purchase_order_change_id?: number;
  capabilities?: Record<string, { allowed?: boolean; reason?: string | null }> | null;
  audit?: { allowed_actions?: string[]; phase?: string; enabled?: boolean; mode?: string; viewer_actions?: unknown } | null;
}

export interface PurchaseArrivalWarningListResult {
  data: PurchaseArrivalWarningRow[];
  total: number;
  success: boolean;
  summary: {
    normal: number;
    imminent: number;
    overdue: number;
    total_open_lines: number;
  };
}

export interface PurchaseArrivalDelayReport {
  id: number;
  report_code: string;
  purchase_order_id: number;
  purchase_order_item_id: number;
  order_code: string;
  material_code: string;
  material_name: string;
  planned_arrival_date: string;
  delay_reason: string;
  estimated_arrival_date: string;
  impact_description?: string;
  impacted_assembly_summary?: string;
  status: string;
  review_status: string;
  purchase_order_change_id?: number;
  purchase_order_change_code?: string;
}

export interface PurchaseArrivalWarningListParams {
  skip?: number;
  limit?: number;
  warning_level?: PurchaseArrivalWarningLevel;
  supplier_keyword?: string;
  order_code?: string;
  material_keyword?: string;
  processing_status?: PurchaseArrivalProcessingStatus;
}

export async function listPurchaseArrivalWarnings(
  params: PurchaseArrivalWarningListParams = {},
): Promise<PurchaseArrivalWarningListResult> {
  return apiRequest('/apps/kuaizhizao/purchase-arrival/warnings', { method: 'GET', params });
}

export async function createPurchaseArrivalDelayReport(data: {
  purchase_order_item_id: number;
  delay_reason: string;
  estimated_arrival_date: string;
  impact_description?: string;
  notes?: string;
}): Promise<PurchaseArrivalDelayReport> {
  return apiRequest('/apps/kuaizhizao/purchase-arrival/delay-reports', { method: 'POST', data });
}

export async function updatePurchaseArrivalDelayReport(
  id: number,
  data: {
    delay_reason?: string;
    estimated_arrival_date?: string;
    impact_description?: string;
  },
): Promise<PurchaseArrivalDelayReport> {
  return apiRequest(`/apps/kuaizhizao/purchase-arrival/delay-reports/${id}`, { method: 'PUT', data });
}

export async function getPurchaseArrivalDelayReport(id: number): Promise<PurchaseArrivalDelayReport> {
  return apiRequest(`/apps/kuaizhizao/purchase-arrival/delay-reports/${id}`, { method: 'GET' });
}

export async function commitPurchaseArrivalDelayReport(id: number): Promise<PurchaseArrivalDelayReport> {
  return apiRequest(`/core/uni-audit/purchase_arrival_delay/${id}/submit`, { method: 'POST' });
}

export async function submitPurchaseArrivalDelayForReview(id: number): Promise<PurchaseArrivalDelayReport> {
  return apiRequest(`/core/uni-audit/purchase_arrival_delay/${id}/submit_review`, { method: 'POST' });
}

export async function withdrawPurchaseArrivalDelaySubmit(id: number): Promise<PurchaseArrivalDelayReport> {
  return apiRequest(`/core/uni-audit/purchase_arrival_delay/${id}/withdraw`, { method: 'POST' });
}

export async function approvePurchaseArrivalDelayByAudit(id: number): Promise<PurchaseArrivalDelayReport> {
  return apiRequest(`/core/uni-audit/purchase_arrival_delay/${id}/approve`, { method: 'POST' });
}

export async function revokePurchaseArrivalDelayApproval(id: number): Promise<PurchaseArrivalDelayReport> {
  return apiRequest(`/core/uni-audit/purchase_arrival_delay/${id}/revoke`, { method: 'POST' });
}

export async function submitPurchaseArrivalDelayReport(id: number): Promise<PurchaseArrivalDelayReport> {
  return commitPurchaseArrivalDelayReport(id);
}

export async function approvePurchaseArrivalDelayReport(
  id: number,
  approved: boolean,
  reviewRemarks?: string,
): Promise<PurchaseArrivalDelayReport> {
  return apiRequest(`/apps/kuaizhizao/purchase-arrival/delay-reports/${id}/approve`, {
    method: 'POST',
    data: { approved, review_remarks: reviewRemarks },
  });
}

export const PURCHASE_ARRIVAL_DELAY_REASONS = [
  { value: 'supplier_capacity', labelKey: 'app.kuaizhizao.purchaseArrival.delayReason.supplierCapacity' },
  { value: 'logistics', labelKey: 'app.kuaizhizao.purchaseArrival.delayReason.logistics' },
  { value: 'quality_rework', labelKey: 'app.kuaizhizao.purchaseArrival.delayReason.qualityRework' },
  { value: 'drawing_change', labelKey: 'app.kuaizhizao.purchaseArrival.delayReason.drawingChange' },
  { value: 'payment_delay', labelKey: 'app.kuaizhizao.purchaseArrival.delayReason.paymentDelay' },
  { value: 'other', labelKey: 'app.kuaizhizao.purchaseArrival.delayReason.other' },
] as const;
