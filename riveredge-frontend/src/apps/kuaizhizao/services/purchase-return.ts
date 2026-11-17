/**
 * 采购退货单类型（API 见 warehouse-execution / production warehouseApi）
 */

import { apiRequest } from '../../../services/api';

export interface ActionCapability {
  allowed: boolean;
  reason?: string | null;
}

export interface PurchaseReturnCapabilities {
  update?: ActionCapability;
  delete?: ActionCapability;
  confirm?: ActionCapability;
  withdraw?: ActionCapability;
  print?: ActionCapability;
  submit?: ActionCapability;
  withdraw_submit?: ActionCapability;
  approve?: ActionCapability;
  revoke_approval?: ActionCapability;
}

export interface PurchaseReturn {
  id?: number;
  tenant_id?: number;
  return_code?: string;
  purchase_receipt_id?: number;
  purchase_receipt_code?: string;
  purchase_order_id?: number;
  purchase_order_code?: string;
  supplier_id?: number;
  supplier_name?: string;
  warehouse_id?: number;
  warehouse_name?: string;
  return_time?: string;
  returner_id?: number;
  returner_name?: string;
  reviewer_id?: number;
  reviewer_name?: string;
  review_time?: string;
  review_status?: string;
  review_remarks?: string;
  return_reason?: string;
  return_type?: string;
  replenish?: boolean;
  status?: string;
  total_quantity?: number;
  total_amount?: number;
  shipping_method?: string;
  tracking_number?: string;
  shipping_address?: string;
  notes?: string;
  attachments?: Array<{ uid?: string; name?: string; url?: string }>;
  created_at?: string;
  updated_at?: string;
  lifecycle?: Record<string, unknown>;
  capabilities?: PurchaseReturnCapabilities;
  audit?: {
    phase?: string;
    enabled?: boolean;
    mode?: string;
    allowed_actions?: string[];
  } | null;
  items?: PurchaseReturnItem[];
}

export interface PurchaseReturnFinanceBlueOffset {
  payable_id: number;
  payable_code: string;
  offset_amount: number;
}

export interface PurchaseReturnFinanceOutcome {
  return_amount: number;
  blue_offset_total: number;
  refund_remainder: number;
  needs_payment_refund: boolean;
  no_blue_payable: boolean;
  red_payable_id?: number | null;
  red_payable_code?: string | null;
  red_payable_amount?: number | null;
  auto_payable_skipped?: boolean;
  auto_payable_skip_reason?: string | null;
  settlement_codes: string[];
  blue_offsets: PurchaseReturnFinanceBlueOffset[];
}

export interface PurchaseReturnDetail extends PurchaseReturn {
  items?: PurchaseReturnItem[];
  finance_outcome?: PurchaseReturnFinanceOutcome | null;
}

export interface PurchaseReturnItem {
  id?: number;
  material_code?: string;
  material_name?: string;
  return_quantity?: number;
  unit_price?: number;
  total_amount?: number;
  batch_number?: string;
  expiry_date?: string;
  location_code?: string;
  serial_numbers?: string[];
  notes?: string;
}

export interface PurchaseReturnListParams {
  skip?: number;
  limit?: number;
  status?: string;
  purchase_receipt_id?: number;
  supplier_id?: number;
  warehouse_id?: number;
  keyword?: string;
  return_code?: string;
  purchase_receipt_code?: string;
  purchase_order_code?: string;
  return_start_date?: string;
  return_end_date?: string;
  created_start_date?: string;
  created_end_date?: string;
  order_by?: string;
  include_items?: boolean;
}

export interface PurchaseReturnListResult {
  data: PurchaseReturn[];
  total: number;
  success: boolean;
}

export function commitPurchaseReturn(id: number) {
  return apiRequest(`/core/uni-audit/purchase_return/${id}/submit`, { method: 'POST' });
}

export function submitPurchaseReturnForReview(id: number) {
  return apiRequest(`/core/uni-audit/purchase_return/${id}/submit_review`, { method: 'POST' });
}

export function withdrawPurchaseReturn(id: number) {
  return apiRequest(`/core/uni-audit/purchase_return/${id}/withdraw`, { method: 'POST' });
}

export function approvePurchaseReturn(id: number) {
  return apiRequest(`/core/uni-audit/purchase_return/${id}/approve`, { method: 'POST' });
}

export function revokePurchaseReturn(id: number) {
  return apiRequest(`/core/uni-audit/purchase_return/${id}/revoke`, { method: 'POST' });
}
