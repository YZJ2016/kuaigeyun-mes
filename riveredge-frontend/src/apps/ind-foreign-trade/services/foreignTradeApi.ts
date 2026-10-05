import { apiRequest } from '../../../services/api';
import type { Customer, CustomerCreate, CustomerUpdate } from '../../master-data/types/supply-chain';
import type { CustomerPoolItem, CustomerPoolListResult } from '../../kuaizhizao/services/customer-pool';
import type { CustomerFollowUp } from '../../kuaizhizao/services/customer-follow-up';
import { customerFollowUpApi } from '../../kuaizhizao/services/customer-follow-up';

export type { CustomerPoolItem, CustomerFollowUp };

export interface InquiryImportRow {
  created_time?: string;
  campaign_name?: string;
  your_packaging_materials?: string;
  required_production_capacity?: string;
  phone_number?: string;
  email?: string;
  full_name?: string;
  company_name?: string;
  job_title?: string;
}

export interface InquiryImportResultItem {
  index: number;
  success: boolean;
  customer_id?: number | null;
  customer_code?: string | null;
  error?: string | null;
}

export interface InquiryImportResponse {
  total: number;
  success_count: number;
  failed_count: number;
  items: InquiryImportResultItem[];
}

export interface ForeignTradeCrmStats {
  pending_customers?: number;
  overdue_customers?: number;
  inactive_customers?: number;
  inactive_alert_days?: number;
  follow_status_pending?: number;
  follow_status_followed?: number;
  follow_up_records_total?: number;
  level_counts?: Record<string, number>;
  items?: CustomerFollowUp[];
}

type FollowUpCreateBody = Parameters<typeof customerFollowUpApi.create>[0];
type FollowUpUpdateBody = Parameters<typeof customerFollowUpApi.update>[1];

export const foreignTradeApi = {
  listExportCustomers: (params?: Record<string, unknown>) =>
    apiRequest<CustomerPoolListResult>('/apps/ind-foreign-trade/export-customers', {
      method: 'GET',
      params,
    }),

  getExportCustomer: (uuid: string) =>
    apiRequest<Customer>(`/apps/ind-foreign-trade/export-customers/${uuid}`, {
      method: 'GET',
    }),

  createExportCustomer: (data: CustomerCreate) =>
    apiRequest<Customer>('/apps/ind-foreign-trade/export-customers', {
      method: 'POST',
      data,
    }),

  updateExportCustomer: (uuid: string, data: CustomerUpdate) =>
    apiRequest<Customer>(`/apps/ind-foreign-trade/export-customers/${uuid}`, {
      method: 'PUT',
      data,
    }),

  getInquiryColumns: () =>
    apiRequest<{ columns: string[]; labels_zh: Record<string, string> }>(
      '/apps/ind-foreign-trade/inquiry-import/columns',
      { method: 'GET' },
    ),

  importInquiry: (items: InquiryImportRow[]) =>
    apiRequest<InquiryImportResponse>('/apps/ind-foreign-trade/inquiry-import', {
      method: 'POST',
      data: { items },
    }),

  getStats: (limit = 8) =>
    apiRequest<ForeignTradeCrmStats>('/apps/ind-foreign-trade/stats', {
      method: 'GET',
      params: { limit },
    }),

  listFollowUps: (params?: Record<string, unknown>) =>
    apiRequest<{ items: CustomerFollowUp[]; total: number }>('/apps/ind-foreign-trade/follow-ups', {
      method: 'GET',
      params,
    }),

  getFollowUp: (id: number) =>
    apiRequest<CustomerFollowUp>(`/apps/ind-foreign-trade/follow-ups/${id}`, {
      method: 'GET',
    }),

  createFollowUp: (data: FollowUpCreateBody) =>
    apiRequest<CustomerFollowUp>('/apps/ind-foreign-trade/follow-ups', {
      method: 'POST',
      data,
    }),

  updateFollowUp: (id: number, data: FollowUpUpdateBody) =>
    apiRequest<CustomerFollowUp>(`/apps/ind-foreign-trade/follow-ups/${id}`, {
      method: 'PUT',
      data,
    }),

  deleteFollowUp: (id: number) =>
    apiRequest(`/apps/ind-foreign-trade/follow-ups/${id}`, {
      method: 'DELETE',
    }),
};

export const foreignTradeFollowUpPersistApi = {
  list: (params?: Parameters<typeof customerFollowUpApi.list>[0]) =>
    foreignTradeApi.listFollowUps({
      skip: params?.skip,
      limit: params?.limit,
      customerId: params?.customer_id,
      activityTypeCode: params?.activity_type_code,
      keyword: params?.keyword,
      occurredFrom: params?.occurred_from,
      occurredTo: params?.occurred_to,
      pendingOnly: params?.pending_only,
      orderBy: params?.order_by,
    }),
  create: foreignTradeApi.createFollowUp,
  update: foreignTradeApi.updateFollowUp,
};
