/**
 * 报价单管理API服务
 *
 * 提供报价单相关的API调用接口。
 *
 * @author RiverEdge Team
 * @date 2026-02-19
 */

import { apiRequest } from '../../../services/api';
import type { DocumentPrintApiResult } from '../../../utils/printResponseHelpers';

export interface ActionCapability {
  allowed: boolean;
  reason?: string | null;
}

export interface QuotationCapabilities {
  update: ActionCapability;
  delete: ActionCapability;
  submit: ActionCapability;
  withdraw_submit: ActionCapability;
  approve: ActionCapability;
  revoke_approval: ActionCapability;
  confirm_customer: ActionCapability;
  cancel_customer_confirm: ActionCapability;
  convert_to_order: ActionCapability;
  convert_to_contract: ActionCapability;
  convert_to_sales_review: ActionCapability;
  revoke_push: ActionCapability;
  reopen: ActionCapability;
  create_revision: ActionCapability;
  print_formal: ActionCapability;
}

export interface QuotationItem {
  id?: number;
  uuid?: string;
  tenant_id?: number;
  quotation_id?: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_spec?: string;
  material_model?: string;
  partner_material_code?: string;
  partner_material_name?: string;
  material_unit?: string;
  quote_quantity?: number;
  unit_price?: number;
  /** 税率（%），含税模式下录入 */
  tax_rate?: number;
  total_amount?: number;
  is_gift?: boolean;
  gift_ref_unit_price?: number;
  delivery_date?: string;
  notes?: string;
  pricing_snapshot?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}

export interface Quotation {
  id?: number;
  uuid?: string;
  tenant_id?: number;
  quotation_code?: string;
  quotation_date?: string;
  valid_until?: string;
  delivery_date?: string;
  customer_id?: number;
  customer_name?: string;
  customer_contact?: string;
  customer_phone?: string;
  total_quantity?: number;
  total_amount?: number;
  /** 整单优惠金额（从价税合计扣减，不改明细单价） */
  discount_amount?: number;
  /** 与销售订单一致：tax_inclusive 含税单价 / tax_exclusive 不含税单价 */
  price_type?: 'tax_inclusive' | 'tax_exclusive' | string;
  status?: string;
  reviewer_id?: number;
  reviewer_name?: string;
  review_time?: string;
  review_status?: string;
  review_remarks?: string;
  salesman_id?: number;
  salesman_name?: string;
  shipping_address?: string;
  shipping_method?: string;
  payment_terms?: string;
  /** 币种（数据字典 CURRENCY，默认 CNY 人民币） */
  currency_code?: string;
  sales_order_id?: number;
  sales_order_code?: string;
  contract_id?: number;
  contract_code?: string;
  sales_review_id?: number;
  sales_review_code?: string;
  /** 报价系列编码（首版通常与 quotation_code 相同） */
  quotation_series_code?: string;
  root_quotation_id?: number;
  version_no?: number;
  previous_quotation_id?: number;
  is_latest_in_series?: boolean;
  superseded_by_id?: number;
  formal_document_generated_at?: string;
  /** 已转单但下游销售订单已不存在（如已删除） */
  conversion_downstream_missing?: boolean;
  /** 仍有关联 contract_id，但下游销售合同已不存在（如已删除） */
  contract_downstream_missing?: boolean;
  /** 仍有关联 sales_review_id，但下游订单评审已不存在（如已删除） */
  sales_review_downstream_missing?: boolean;
  notes?: string;
  is_active?: boolean;
  created_by?: number;
  created_by_name?: string;
  updated_by?: number;
  updated_by_name?: string;
  created_at?: string;
  updated_at?: string;
  items?: QuotationItem[];
  lifecycle?: Record<string, unknown>;
  capabilities?: QuotationCapabilities;
  audit?: {
    phase?: string;
    allowed_actions?: string[];
    [key: string]: unknown;
  };
}

export interface QuotationListParams {
  skip?: number;
  limit?: number;
  status?: string;
  lifecycle_stage?: string;
  salesman_id?: number;
  customer_id?: number;
  start_date?: string;
  end_date?: string;
  /** 工具栏模糊搜索：编号、系列、客户、销售员 */
  keyword?: string;
  quotation_code?: string;
  customer_name?: string;
  quotation_series_code?: string;
  /** 排序字段，如 quotation_date、-updated_at */
  order_by?: string;
  /** 数据范围：all 全部 / mine 我的 / department 我的部门 */
  list_scope?: 'all' | 'mine' | 'department';
  /** 仅可加载建销售订单：未关联销售订单且非已转订单 */
  pullable_only?: boolean;
  /** 加载目标单据类型：销售订单 / 销售合同 / 订单评审 */
  pull_target?: 'sales_order' | 'sales_contract' | 'sales_review';
  /** 明细表格视图：附带报价明细 */
  include_items?: boolean;
}

export interface QuotationListResponse {
  data: Quotation[];
  total: number;
  success: boolean;
}

export async function listQuotations(params: QuotationListParams = {}): Promise<QuotationListResponse> {
  return apiRequest<QuotationListResponse>('/apps/kuaizhizao/quotations', {
    method: 'GET',
    params,
  });
}

export interface QuotationSalesmanOption {
  id: number;
  name: string;
}

/** 当前可见报价单中的去重销售人员（列表筛选下拉） */
export async function listQuotationSalesmen(
  params: { list_scope?: 'all' | 'mine' | 'department' } = {},
): Promise<QuotationSalesmanOption[]> {
  const res = await apiRequest<QuotationSalesmanOption[] | { data?: QuotationSalesmanOption[] }>(
    '/apps/kuaizhizao/quotations/salesmen',
    { method: 'GET', params },
  );
  if (Array.isArray(res)) return res;
  return Array.isArray(res?.data) ? res.data : [];
}

export async function getQuotation(id: number, includeItems: boolean = true): Promise<Quotation> {
  return apiRequest<Quotation>(`/apps/kuaizhizao/quotations/${id}`, {
    method: 'GET',
    params: { include_items: includeItems },
  });
}

export async function createQuotation(
  data: Partial<Quotation>,
  options?: { autoSubmit?: boolean },
): Promise<Quotation> {
  return apiRequest<Quotation>('/apps/kuaizhizao/quotations', {
    method: 'POST',
    data,
    params:
      options?.autoSubmit === false
        ? { auto_submit: false }
        : options?.autoSubmit === true
          ? { auto_submit: true }
          : undefined,
  });
}

export async function updateQuotation(id: number, data: Partial<Quotation>): Promise<Quotation> {
  return apiRequest<Quotation>(`/apps/kuaizhizao/quotations/${id}`, {
    method: 'PUT',
    data,
  });
}

/** 提交报价单（草稿 → 已提交；页面提交走本接口） */
export async function submitQuotation(id: number): Promise<Quotation> {
  return apiRequest<Quotation>(`/apps/kuaizhizao/quotations/${id}/submit`, {
    method: 'POST',
  });
}

/** 提交审核（已提交 → 待审核/已发送，或免审直接已发送+已通过） */
export async function submitQuotationForReview(id: number): Promise<Quotation> {
  return apiRequest<Quotation>(`/core/uni-audit/quotation/${id}/submit_review`, {
    method: 'POST',
  });
}

/** 撤销提交 / 撤回审核 */
export async function withdrawQuotation(id: number): Promise<Quotation> {
  return apiRequest<Quotation>(`/core/uni-audit/quotation/${id}/withdraw`, {
    method: 'POST',
  });
}

/** 审核通过（已发送 + 待审核 → 保持已发送，审核通过） */
export async function approveQuotation(id: number, data?: { review_remarks?: string }): Promise<Quotation> {
  return apiRequest<Quotation>(`/apps/kuaizhizao/quotations/${id}/approve`, {
    method: 'POST',
    data: data ?? {},
  });
}

/** 驳回（已发送 + 待审核 → 已拒绝） */
export async function rejectQuotation(id: number, data?: { review_remarks?: string }): Promise<Quotation> {
  return apiRequest<Quotation>(`/apps/kuaizhizao/quotations/${id}/reject`, {
    method: 'POST',
    data: data ?? {},
  });
}

/** 撤回审核（已发送 + 已通过 → 待审核） */
export async function revokeReviewQuotation(id: number): Promise<Quotation> {
  return apiRequest<Quotation>(`/apps/kuaizhizao/quotations/${id}/revoke-review`, {
    method: 'POST',
  });
}

/** 客户确认 / 标记已接受（已发送 + 已通过 → 已接受） */
export async function confirmCustomerQuotation(id: number): Promise<Quotation> {
  return apiRequest<Quotation>(`/apps/kuaizhizao/quotations/${id}/confirm-customer`, {
    method: 'POST',
  });
}

/** 客户取消确认（已接受 → 已发送，可撤回审核或删除） */
export async function cancelCustomerConfirmQuotation(id: number): Promise<Quotation> {
  return apiRequest<Quotation>(
    `/apps/kuaizhizao/quotations/${id}/cancel-customer-confirm`,
    { method: 'POST' },
  );
}

/** 驳回后重新编辑（已拒绝 → 草稿） */
export async function reopenQuotation(id: number): Promise<Quotation> {
  return apiRequest<Quotation>(`/apps/kuaizhizao/quotations/${id}/reopen`, {
    method: 'POST',
  });
}

/** 撤回下推（已转订单且下游销售订单已不存在 → 已接受） */
export async function revokePushQuotation(id: number): Promise<Quotation> {
  return apiRequest<Quotation>(`/apps/kuaizhizao/quotations/${id}/revoke-push`, {
    method: 'POST',
  });
}

/** 新建修订版：从系列当前最新版复制为草稿修订 */
export async function createQuotationRevision(
  quotationId: number,
  data?: Record<string, unknown>
): Promise<Quotation> {
  return apiRequest<Quotation>(`/apps/kuaizhizao/quotations/${quotationId}/revision`, {
    method: 'POST',
    data: data ?? {},
  });
}

export async function deleteQuotation(id: number): Promise<void> {
  return apiRequest<void>(`/apps/kuaizhizao/quotations/${id}`, {
    method: 'DELETE',
  });
}

export interface ConvertToOrderResponse {
  sales_order: { id?: number; order_code?: string; [key: string]: any };
  quotation: Quotation;
}

export interface QuotationPushPreviewItem {
  item_id: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_spec?: string;
  material_unit?: string;
  quantity: number;
  pushed_quantity: number;
  max_push_quantity: number;
  delivery_date?: string | null;
  unit_price?: number;
  total_amount?: number;
}

export interface QuotationPushPreviewResponse {
  target_type: 'sales_order' | 'sales_contract' | 'sales_review';
  summary: string;
  items: QuotationPushPreviewItem[];
  has_blocking_issues?: boolean;
  blocking_reason?: string | null;
  tip?: string;
}

export async function previewPushQuotationToSalesOrder(
  quotationId: number,
): Promise<QuotationPushPreviewResponse> {
  return apiRequest<QuotationPushPreviewResponse>(
    `/apps/kuaizhizao/quotations/${quotationId}/push-to-sales-order/preview`,
    { method: 'GET' },
  );
}

export interface QuotationToSalesOrderDraftResponse {
  target_type: 'sales_order';
  source_type: 'quotation';
  source_id: number;
  source_code?: string;
  document_flow: {
    documentFlowSourceType: 'quotation';
    documentFlowSourceId: number;
    documentFlowSourceItemIds: number[];
  };
  create_payload: Record<string, unknown>;
}

export interface QuotationToSalesReviewDraftResponse {
  target_type: 'sales_review';
  source_type: 'quotation';
  source_id: number;
  source_code?: string;
  document_flow: {
    documentFlowSourceType: 'quotation';
    documentFlowSourceId: number;
    documentFlowSourceItemIds: number[];
  };
  create_payload: Record<string, unknown>;
}

export async function draftSalesReviewFromQuotation(
  quotationId: number,
  selectedItemIds?: number[],
): Promise<QuotationToSalesReviewDraftResponse> {
  const qs =
    selectedItemIds?.length ?
      `?${selectedItemIds.map((id) => `selected_item_ids=${id}`).join('&')}`
    : '';
  return apiRequest<QuotationToSalesReviewDraftResponse>(
    `/apps/kuaizhizao/quotations/${quotationId}/push-to-sales-review/draft${qs}`,
    { method: 'GET' },
  );
}

export async function draftSalesOrderFromQuotation(
  quotationId: number,
  selectedItemIds?: number[],
): Promise<QuotationToSalesOrderDraftResponse> {
  const qs =
    selectedItemIds?.length ?
      `?${selectedItemIds.map((id) => `selected_item_ids=${id}`).join('&')}`
    : '';
  return apiRequest<QuotationToSalesOrderDraftResponse>(
    `/apps/kuaizhizao/quotations/${quotationId}/push-to-sales-order/draft${qs}`,
    { method: 'GET' },
  );
}

export async function previewPushQuotationToSalesContract(
  quotationId: number,
): Promise<QuotationPushPreviewResponse> {
  return apiRequest<QuotationPushPreviewResponse>(
    `/apps/kuaizhizao/quotations/${quotationId}/push-to-sales-contract/preview`,
    { method: 'GET' },
  );
}

export async function previewPushQuotationToSalesReview(
  quotationId: number,
): Promise<QuotationPushPreviewResponse> {
  return apiRequest<QuotationPushPreviewResponse>(
    `/apps/kuaizhizao/quotations/${quotationId}/push-to-sales-review/preview`,
    { method: 'GET' },
  );
}

export async function convertQuotationToOrder(
  quotationId: number,
  options?: { selected_item_ids?: number[] },
): Promise<ConvertToOrderResponse> {
  return apiRequest<ConvertToOrderResponse>(`/apps/kuaizhizao/quotations/${quotationId}/convert-to-order`, {
    method: 'POST',
    data: options?.selected_item_ids?.length ? { selected_item_ids: options.selected_item_ids } : undefined,
  });
}

export async function convertQuotationToSalesReview(
  quotationId: number,
  options?: { selected_item_ids?: number[] },
): Promise<{ sales_review?: { id?: number; review_code?: string }; quotation?: Quotation }> {
  return apiRequest(`/apps/kuaizhizao/quotations/${quotationId}/convert-to-sales-review`, {
    method: 'POST',
    data: options?.selected_item_ids?.length ? { selected_item_ids: options.selected_item_ids } : undefined,
  });
}

export async function printQuotation(
  quotationId: number,
  options?: {
    templateUuid?: string;
    outputFormat?: 'html' | 'pdf';
    responseFormat?: 'json' | 'html';
  }
): Promise<DocumentPrintApiResult> {
  return apiRequest<DocumentPrintApiResult>(`/apps/kuaizhizao/quotations/${quotationId}/print`, {
    method: 'GET',
    params: {
      template_uuid: options?.templateUuid,
      output_format: options?.outputFormat ?? 'pdf',
      response_format: options?.responseFormat ?? 'json',
    },
  });
}

export async function getQuotationPrintVariables(quotationId: number): Promise<Record<string, any>> {
  return apiRequest<Record<string, any>>(`/apps/kuaizhizao/quotations/${quotationId}/print-variables`, {
    method: 'GET',
  });
}

export async function recordQuotationPrint(quotationId: number): Promise<{ success: boolean; timestamp?: string }> {
  return apiRequest<{ success: boolean; timestamp?: string }>(`/apps/kuaizhizao/quotations/${quotationId}/record-print`, {
    method: 'POST',
  });
}

export type QuotationSalesOrderPullLine = {
  id: number;
  quotation_id: number;
  quotation_code?: string;
  quotation_status?: string;
  document_date?: string | null;
  quotation_date?: string | null;
  valid_until?: string | null;
  customer_name?: string | null;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_spec?: string | null;
  unit?: string;
  suggested_quantity?: number;
  pushed_quantity?: number;
  remaining_quantity?: number;
  suggested_aux_quantity?: number | null;
  pushed_aux_quantity?: number | null;
  remaining_aux_quantity?: number | null;
  aux_unit?: string | null;
  line_notes?: string | null;
  can_push?: boolean;
};

export async function listQuotationSalesOrderPullLines(params: {
  skip?: number;
  limit?: number;
  keyword?: string;
  quotation_id?: number;
  pullable_only?: boolean;
}): Promise<{ data: QuotationSalesOrderPullLine[]; total: number }> {
  return apiRequest('/apps/kuaizhizao/quotations/sales-order-pull-lines', {
    method: 'GET',
    params,
  });
}

export async function listQuotationSalesReviewPullLines(params: {
  skip?: number;
  limit?: number;
  keyword?: string;
  quotation_id?: number;
  pullable_only?: boolean;
}): Promise<{ data: QuotationSalesOrderPullLine[]; total: number }> {
  return apiRequest('/apps/kuaizhizao/quotations/sales-review-pull-lines', {
    method: 'GET',
    params,
  });
}

