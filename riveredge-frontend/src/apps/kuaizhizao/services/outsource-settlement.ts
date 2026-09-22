import { apiRequest } from '../../../services/api';

const BASE = '/apps/kuaizhizao/outsource-settlements';

export type OutsourceSettlementItem = {
  id?: number;
  line_no?: number;
  line_type?: string;
  outsource_material_receipt_id?: number | null;
  receipt_code?: string | null;
  outsource_work_order_id?: number | null;
  outsource_work_order_code?: string | null;
  product_code?: string | null;
  product_name?: string | null;
  unit?: string | null;
  outsource_product_return_id?: number | null;
  deduction_basis_qty?: number | null;
  deduction_basis_amount?: number | null;
  settlement_quantity: number;
  unit_price: number;
  amount?: number;
  notes?: string;
};

export type OutsourceSettlementPayableLink = {
  payable_id: number;
  payable_code?: string | null;
  source_type: string;
  total_amount: number;
  invoice_status?: string | null;
};

export type OutsourceSettlement = {
  id: number;
  settlement_code: string;
  supplier_id: number;
  supplier_code: string;
  supplier_name: string;
  business_date?: string | null;
  total_amount: number;
  status: string;
  settlement_kind?: string;
  auto_generated?: boolean;
  source_doc_type?: string | null;
  source_doc_id?: number | null;
  reviewer_id?: number | null;
  reviewer_name?: string | null;
  reviewed_at?: string | null;
  review_remarks?: string | null;
  payable_id?: number | null;
  payable_code?: string | null;
  invoice_status?: string | null;
  notes?: string | null;
  created_at?: string;
  updated_at?: string;
  created_by_name?: string;
  updated_by_name?: string;
  items?: OutsourceSettlementItem[];
  payables?: OutsourceSettlementPayableLink[];
};

export type OutsourceSettleableReceipt = {
  id: number;
  code: string;
  outsource_work_order_id: number;
  outsource_work_order_code: string;
  supplier_id: number;
  supplier_code: string;
  supplier_name: string;
  product_code: string;
  product_name: string;
  unit: string;
  qualified_quantity: number;
  returned_quantity: number;
  settled_quantity: number;
  pending_settlement_quantity: number;
  settleable_quantity: number;
  unit_price: number;
  received_at?: string | null;
};

export type OutsourceMaterialDeductionPreview = {
  outsource_work_order_id: number;
  outsource_work_order_code: string;
  material_id: number;
  material_code: string;
  material_name: string;
  standard_qty: number;
  actual_qty: number;
  overrun_qty: number;
  unit_price: number;
  deduction_amount: number;
};

export type OutsourceSettlementPayloadItem = {
  line_type?: string;
  outsource_material_receipt_id?: number;
  outsource_work_order_id?: number;
  settlement_quantity: number;
  unit_price: number;
  deduction_basis_qty?: number;
  deduction_basis_amount?: number;
  notes?: string;
};

export type OutsourceSettlementPayload = {
  supplier_id: number;
  business_date?: string;
  notes?: string;
  items: OutsourceSettlementPayloadItem[];
};

export type OutsourceSettlementDocumentChainStep = {
  step: string;
  doc_type: string;
  doc_id?: number | null;
  doc_code?: string | null;
  status?: string | null;
};

function buildQuery(params?: Record<string, unknown>): string {
  if (!params) return '';
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v != null && v !== '') sp.set(k, String(v));
  });
  const q = sp.toString();
  return q ? `?${q}` : '';
}

export const outsourceSettlementApi = {
  list: (params?: Record<string, unknown>) =>
    apiRequest<{ items: OutsourceSettlement[]; total: number }>(`${BASE}${buildQuery(params)}`),
  get: (id: number) => apiRequest<OutsourceSettlement>(`${BASE}/${id}`),
  create: (payload: OutsourceSettlementPayload) =>
    apiRequest<OutsourceSettlement>(BASE, { method: 'POST', body: payload }),
  update: (id: number, payload: Partial<OutsourceSettlementPayload>) =>
    apiRequest<OutsourceSettlement>(`${BASE}/${id}`, { method: 'PUT', body: payload }),
  submit: (id: number) => apiRequest<OutsourceSettlement>(`${BASE}/${id}/submit`, { method: 'POST' }),
  audit: (id: number, body?: { review_remarks?: string }) =>
    apiRequest<OutsourceSettlement>(`${BASE}/${id}/audit`, { method: 'POST', body: body ?? {} }),
  reject: (id: number, body: { review_remarks: string }) =>
    apiRequest<OutsourceSettlement>(`${BASE}/${id}/reject`, { method: 'POST', body }),
  revoke: (id: number) => apiRequest<OutsourceSettlement>(`${BASE}/${id}/revoke`, { method: 'POST' }),
  delete: (id: number) => apiRequest<void>(`${BASE}/${id}`, { method: 'DELETE' }),
  listSettleableReceipts: (supplierId: number, excludeSettlementId?: number) =>
    apiRequest<OutsourceSettleableReceipt[]>(
      `${BASE}/settleable-receipts${buildQuery({
        supplier_id: supplierId,
        exclude_settlement_id: excludeSettlementId,
      })}`,
    ),
  previewDeductions: (supplierId: number, workOrderIds: number[]) =>
    apiRequest<OutsourceMaterialDeductionPreview[]>(
      `${BASE}/deduction-preview${buildQuery({
        supplier_id: supplierId,
        work_order_ids: workOrderIds.join(','),
      })}`,
    ),
  invoicePreview: (id: number) =>
    apiRequest<{ settlement_id: number; items: Array<{ payable_id: number; payable_code?: string; source_type: string; amount: number; description: string }>; total_amount: number }>(
      `${BASE}/${id}/invoice-preview`,
    ),
  documentChain: (id: number) =>
    apiRequest<{ settlement_id: number; steps: OutsourceSettlementDocumentChainStep[] }>(
      `${BASE}/${id}/document-chain`,
    ),
};
