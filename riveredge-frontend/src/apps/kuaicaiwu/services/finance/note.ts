import { apiRequest } from '../../../../services/api';

export type FinanceNoteDirection = 'receivable' | 'payable';

export type FinanceNoteBillType =
  | 'bank_acceptance'
  | 'commercial_acceptance'
  | 'bank_draft'
  | 'bank_promissory_note'
  | 'cheque';

export type FinanceNoteStatus =
  | 'held'
  | 'endorsed'
  | 'discounted'
  | 'collected'
  | 'dishonored'
  | 'issued'
  | 'honored';

export interface FinanceNote {
  id: number;
  tenant_id: number;
  direction: FinanceNoteDirection;
  bill_type: FinanceNoteBillType;
  note_code: string;
  bill_no: string;
  amount: number;
  issue_date: string;
  due_date: string;
  drawer_name?: string | null;
  acceptor_name?: string | null;
  payee_name?: string | null;
  accepting_bank?: string | null;
  customer_id?: number | null;
  customer_name?: string | null;
  supplier_id?: number | null;
  supplier_name?: string | null;
  receipt_id?: number | null;
  payment_id?: number | null;
  receivable_id?: number | null;
  payable_id?: number | null;
  status: FinanceNoteStatus;
  endorse_to_name?: string | null;
  discount_bank?: string | null;
  discount_date?: string | null;
  discount_interest?: number | null;
  settle_date?: string | null;
  notes?: string | null;
  attachments?: Record<string, unknown>[] | null;
  review_status?: string | null;
  created_at?: string;
  updated_at?: string;
  created_by_name?: string | null;
  updated_by_name?: string | null;
  audit?: {
    allowed_actions?: string[];
    phase?: string;
    enabled?: boolean;
    mode?: string;
    viewer_actions?: unknown;
  } | null;
  capabilities?: Record<string, { allowed?: boolean; reason?: string | null }> | null;
}

export interface FinanceNoteListParams {
  skip?: number;
  limit?: number;
  keyword?: string;
  status?: string;
  review_status?: string;
  bill_type?: FinanceNoteBillType;
  expiring_within_days?: number;
  due_date_start?: string;
  due_date_end?: string;
  partner_id?: number;
  receipt_id?: number;
  payment_id?: number;
  unlinked_only?: boolean;
  sort_field?: string;
  sort_order?: string;
}

export interface FinanceNoteListResponse {
  items: FinanceNote[];
  total: number;
  skip: number;
  limit: number;
}

const apiBase = (direction: FinanceNoteDirection) =>
  direction === 'receivable'
    ? '/apps/kuaicaiwu/notes-receivable'
    : '/apps/kuaicaiwu/notes-payable';

export const financeNoteService = {
  list: async (direction: FinanceNoteDirection, params?: FinanceNoteListParams) => {
    const res = await apiRequest<FinanceNoteListResponse>(apiBase(direction), {
      method: 'GET',
      params,
    });
    return {
      data: res?.items ?? [],
      total: res?.total ?? 0,
      success: true,
    };
  },
  get: (direction: FinanceNoteDirection, id: number) =>
    apiRequest<FinanceNote>(`${apiBase(direction)}/${id}`, { method: 'GET' }),
  create: (direction: FinanceNoteDirection, data: Partial<FinanceNote>) =>
    apiRequest<FinanceNote>(apiBase(direction), { method: 'POST', data }),
  update: (direction: FinanceNoteDirection, id: number, data: Partial<FinanceNote>) =>
    apiRequest<FinanceNote>(`${apiBase(direction)}/${id}`, { method: 'PUT', data }),
  applyAction: (
    direction: FinanceNoteDirection,
    id: number,
    data: Record<string, unknown>,
  ) => apiRequest<FinanceNote>(`${apiBase(direction)}/${id}/action`, { method: 'PUT', data }),
  delete: (direction: FinanceNoteDirection, id: number) =>
    apiRequest<void>(`${apiBase(direction)}/${id}`, { method: 'DELETE' }),
  /** 页面提交：草稿→已提交 */
  commit: (direction: FinanceNoteDirection, id: number) =>
    apiRequest<FinanceNote>(`/core/uni-audit/${auditEntity(direction)}/${id}/submit`, {
      method: 'POST',
    }),
  submitForReview: (direction: FinanceNoteDirection, id: number) =>
    apiRequest<FinanceNote>(`/core/uni-audit/${auditEntity(direction)}/${id}/submit_review`, {
      method: 'POST',
    }),
  withdraw: (direction: FinanceNoteDirection, id: number) =>
    apiRequest<FinanceNote>(`/core/uni-audit/${auditEntity(direction)}/${id}/withdraw`, {
      method: 'POST',
    }),
  approve: (direction: FinanceNoteDirection, id: number) =>
    apiRequest<FinanceNote>(`/core/uni-audit/${auditEntity(direction)}/${id}/approve`, {
      method: 'POST',
      data: {},
    }),
  revoke: (direction: FinanceNoteDirection, id: number) =>
    apiRequest<FinanceNote>(`/core/uni-audit/${auditEntity(direction)}/${id}/revoke`, {
      method: 'POST',
    }),
};

function auditEntity(direction: FinanceNoteDirection): 'notes_receivable' | 'notes_payable' {
  return direction === 'receivable' ? 'notes_receivable' : 'notes_payable';
}

export const NOTES_RECEIVABLE_RESOURCE = 'kuaicaiwu:notes-receivable';
export const NOTES_PAYABLE_RESOURCE = 'kuaicaiwu:notes-payable';
