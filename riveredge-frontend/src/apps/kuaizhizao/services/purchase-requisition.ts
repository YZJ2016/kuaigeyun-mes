/**
 * 采购申请API服务
 */

import { apiRequest } from '../../../services/api';

export interface ActionCapability {
  allowed: boolean;
  reason?: string | null;
}

export interface PurchaseRequisitionCapabilities {
  update?: ActionCapability;
  delete?: ActionCapability;
  submit?: ActionCapability;
  withdraw_submit?: ActionCapability;
  approve?: ActionCapability;
  revoke_approval?: ActionCapability;
  push_purchase_order?: ActionCapability;
  push_inquiry?: ActionCapability;
  print?: ActionCapability;
}

export interface PurchaseRequisitionLifecycle {
  status_class?: string;
  flow_class?: string;
  current_stage_key?: string;
  current_stage_name?: string;
  status?: string;
  main_stages?: Array<{ key?: string; label?: string; status?: string }>;
  sub_stages?: Array<{ key?: string; label?: string; status?: string }>;
}

export interface PurchaseRequisitionItem {
  id?: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_spec?: string;
  unit?: string;
  quantity?: number;
  aux_quantity?: number | null;
  aux_unit?: string | null;
  unit_conversion_rate?: number | null;
  suggested_unit_price?: number;
  required_date?: string;
  supplier_id?: number;
  purchase_order_id?: number;
  purchase_order_item_id?: number;
  demand_computation_item_id?: number;
  converted_quantity_draft?: number;
  converted_quantity_confirmed?: number;
  notes?: string;
  attachments?: unknown;
}

export interface PurchaseRequisition {
  id?: number;
  requisition_code?: string;
  order_type?: string;
  requisition_name?: string;
  status?: string;
  applicant_id?: number;
  applicant_name?: string;
  department_id?: number | null;
  department_name?: string | null;
  requisition_date?: string;
  required_date?: string;
  source_type?: string;
  source_id?: number;
  source_code?: string;
  review_status?: string;
  notes?: string;
  attachments?: unknown;
  items_count?: number;
  total_quantity?: number;
  total_amount?: number;
  items?: PurchaseRequisitionItem[];
  created_at?: string;
  updated_at?: string;
  lifecycle?: PurchaseRequisitionLifecycle;
  capabilities?: PurchaseRequisitionCapabilities;
  audit?: { phase?: string; allowed_actions?: string[] };
}

export async function listPurchaseRequisitions(params: {
  skip?: number;
  limit?: number;
  status?: string;
  lifecycle_stage?: string;
  source_type?: string;
  keyword?: string;
  requisition_code?: string;
  requisition_name?: string;
  required_date_from?: string;
  required_date_to?: string;
  created_start_date?: string;
  created_end_date?: string;
  order_by?: string;
  include_items?: boolean;
} = {}): Promise<{ data: PurchaseRequisition[]; total: number; success: boolean }> {
  return apiRequest('/apps/kuaizhizao/purchase-requisitions', { method: 'GET', params });
}

export async function getPurchaseRequisition(id: number): Promise<PurchaseRequisition> {
  return apiRequest(`/apps/kuaizhizao/purchase-requisitions/${id}`);
}

export type MaterialWarehouseStockLine = {
  warehouse_name: string;
  quantity: number;
};

export async function getPurchaseRequisitionMaterialWarehouseStock(
  materialIds: number[],
): Promise<{ by_material: Record<string, MaterialWarehouseStockLine[]> }> {
  if (!materialIds.length) {
    return { by_material: {} };
  }
  return apiRequest('/apps/kuaizhizao/purchase-requisitions/material-warehouse-stock', {
    method: 'GET',
    params: { material_ids: materialIds },
  });
}

export async function createPurchaseRequisition(data: Partial<PurchaseRequisition>): Promise<PurchaseRequisition> {
  return apiRequest('/apps/kuaizhizao/purchase-requisitions', { method: 'POST', data });
}

export type DemandComputationToPurchaseRequisitionDraftResponse = {
  target_type: 'purchase_requisition';
  source_type: 'demand_computation';
  create_payload: Record<string, unknown>;
  document_flow: Record<string, unknown>;
};

export async function draftPurchaseRequisitionFromDemandComputationItems(
  selectedItemIds: number[],
  itemRequiredDates?: Array<{ item_id: number; required_date: string }>,
  options?: { includeSalesOrderAttachments?: boolean },
): Promise<DemandComputationToPurchaseRequisitionDraftResponse> {
  return apiRequest('/apps/kuaizhizao/purchase-requisitions/draft-from-demand-computation-items', {
    method: 'POST',
    data: {
      selected_item_ids: selectedItemIds,
      ...(itemRequiredDates?.length
        ? { item_required_dates: itemRequiredDates }
        : {}),
      ...(options?.includeSalesOrderAttachments
        ? { include_sales_order_attachments: true }
        : {}),
    },
  });
}

export async function pullPurchaseRequisitionFromDemandComputationItems(
  selectedItemIds: number[],
  itemRequiredDates?: Array<{ item_id: number; required_date: string }>,
): Promise<{ success: boolean; message: string; target_document?: { id: number; code: string } }> {
  return apiRequest('/apps/kuaizhizao/purchase-requisitions/pull-from-demand-computation-items', {
    method: 'POST',
    data: {
      selected_item_ids: selectedItemIds,
      ...(itemRequiredDates?.length
        ? { item_required_dates: itemRequiredDates }
        : {}),
    },
  });
}

export type PurchaseRequisitionPullLine = {
  id: number;
  requisition_id: number;
  requisition_code?: string;
  /** 来源申请主状态（「全部」分段展示） */
  requisition_status?: string | null;
  /** 是否允许下推采购订单/询价（与 capabilities 一致） */
  can_push?: boolean;
  /** 单据日期（申请日期）YYYY-MM-DD */
  document_date?: string | null;
  /** 申请日期 YYYY-MM-DD */
  requisition_date?: string | null;
  applicant_name?: string | null;
  department_id?: number | null;
  department_name?: string | null;
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
  /** 全仓可用总库存（与看板总库存同口径） */
  current_stock?: number;
  required_date?: string | null;
  /** 申请行备注 */
  line_notes?: string | null;
  supplier_id?: number | null;
};

export async function listPurchaseRequisitionPurchaseOrderPullLines(params: {
  skip?: number;
  limit?: number;
  keyword?: string;
  requisition_id?: number;
  pullable_only?: boolean;
}): Promise<{ data: PurchaseRequisitionPullLine[]; total: number }> {
  return apiRequest('/apps/kuaizhizao/purchase-requisitions/purchase-order-pull-lines', {
    method: 'GET',
    params,
  });
}

export async function listPurchaseRequisitionPurchaseInquiryPullLines(params: {
  skip?: number;
  limit?: number;
  keyword?: string;
  requisition_id?: number;
  pullable_only?: boolean;
}): Promise<{ data: PurchaseRequisitionPullLine[]; total: number }> {
  return apiRequest('/apps/kuaizhizao/purchase-requisitions/purchase-inquiry-pull-lines', {
    method: 'GET',
    params,
  });
}

export type RequisitionToPurchaseOrderDraftEntry = {
  create_payload: Record<string, unknown>;
  document_flow: Record<string, unknown>;
  supplier_id?: number;
  requisition_ids?: number[];
};

export type RequisitionToPurchaseOrderDraftResponse = {
  target_type: 'purchase_order';
  source_type: 'purchase_requisition';
  drafts: RequisitionToPurchaseOrderDraftEntry[];
};

export type RequisitionConvertToPurchaseOrderPayload = {
  item_ids: number[];
  supplier_id?: number;
  supplier_name?: string;
  item_quantities?: Record<number, number>;
  item_unit_prices?: Record<number, number>;
  item_suppliers?: Record<number, number>;
  persist_default_supplier_to_material?: boolean;
};

export async function draftPurchaseOrdersFromRequisitionItems(
  data: RequisitionConvertToPurchaseOrderPayload | { selected_item_ids: number[] },
): Promise<RequisitionToPurchaseOrderDraftResponse> {
  return apiRequest('/apps/kuaizhizao/purchase-orders/draft-from-requisition-items', {
    method: 'POST',
    data,
  });
}

export async function pullPurchaseOrdersFromRequisitionItems(
  selectedItemIds: number[],
): Promise<{
  success: boolean;
  message: string;
  purchase_order_id?: number;
  purchase_order_code?: string;
  purchase_orders?: Array<{ purchase_order_id: number; purchase_order_code: string; supplier_id: number }>;
}> {
  return apiRequest('/apps/kuaizhizao/purchase-orders/pull-from-requisition-items', {
    method: 'POST',
    data: { selected_item_ids: selectedItemIds },
  });
}

export async function updatePurchaseRequisition(id: number, data: Partial<PurchaseRequisition>): Promise<PurchaseRequisition> {
  return apiRequest(`/apps/kuaizhizao/purchase-requisitions/${id}`, { method: 'PUT', data });
}

export async function deletePurchaseRequisition(id: number): Promise<void> {
  return apiRequest(`/apps/kuaizhizao/purchase-requisitions/${id}`, { method: 'DELETE' });
}

const PURCHASE_REQUEST_AUDIT_ENTITY = 'purchase_request';

/** 采购申请审核动作（与行内 UniWorkflowActions / 审批状态门控同一入口） */
export async function uniAuditPurchaseRequisition(
  id: number,
  action: 'submit' | 'withdraw' | 'approve' | 'reject' | 'revoke',
  data: Record<string, unknown> = {},
): Promise<unknown> {
  return apiRequest(`/core/uni-audit/${PURCHASE_REQUEST_AUDIT_ENTITY}/${id}/${action}`, {
    method: 'POST',
    data,
  });
}

export async function submitPurchaseRequisition(id: number): Promise<PurchaseRequisition> {
  return uniAuditPurchaseRequisition(id, 'submit') as Promise<PurchaseRequisition>;
}

export async function submitPurchaseRequisitionForReview(id: number): Promise<PurchaseRequisition> {
  return apiRequest(`/core/uni-audit/${PURCHASE_REQUEST_AUDIT_ENTITY}/${id}/submit_review`, {
    method: 'POST',
  });
}

export async function approvePurchaseRequisition(
  id: number,
  data: { approved: boolean; review_remarks?: string }
): Promise<PurchaseRequisition> {
  return apiRequest(`/apps/kuaizhizao/purchase-requisitions/${id}/approve`, {
    method: 'POST',
    data,
  });
}

export async function withdrawPurchaseRequisition(id: number): Promise<PurchaseRequisition> {
  return apiRequest(`/apps/kuaizhizao/purchase-requisitions/${id}/withdraw-approval`, {
    method: 'POST',
  });
}

/** 撤回提交（待审核 -> 草稿），走统一审核入口 */
export async function withdrawPurchaseRequisitionSubmit(id: number): Promise<PurchaseRequisition> {
  return apiRequest(`/core/uni-audit/purchase_request/${id}/withdraw`, {
    method: 'POST',
  });
}

export async function fixPurchaseRequisitionStatus(id: number): Promise<PurchaseRequisition> {
  return apiRequest(`/apps/kuaizhizao/purchase-requisitions/${id}/fix-status`, {
    method: 'POST',
  });
}

export async function convertToPurchaseOrder(
  requisitionId: number,
  data: {
    item_ids: number[];
    supplier_id?: number;
    supplier_name?: string;
    item_quantities?: Record<number, number>;
    item_unit_prices?: Record<number, number>;
    /** 申请行 id -> 供应商 id，优先于行上 supplier_id */
    item_suppliers?: Record<number, number>;
    /** 转单成功后写回采购件物料默认供应商 */
    persist_default_supplier_to_material?: boolean;
  }
): Promise<{
  success: boolean;
  message: string;
  purchase_order_id: number;
  purchase_order_code: string;
  purchase_orders?: Array<{ purchase_order_id: number; purchase_order_code: string; supplier_id: number }>;
  persisted_material_ids?: number[];
}> {
  return apiRequest(`/apps/kuaizhizao/purchase-requisitions/${requisitionId}/convert-to-purchase-order`, {
    method: 'POST',
    data,
  });
}

export interface DocumentPushPreviewItem {
  item_id: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_spec?: string;
  unit?: string;
  quantity: number;
  pushed_quantity: number;
  max_push_quantity: number;
  suggested_unit_price?: number;
  supplier_id?: number;
  required_date?: string;
  in_active_inquiry?: boolean;
}

export interface DocumentPushPreview {
  target_type: string;
  summary: string;
  items: DocumentPushPreviewItem[];
  has_blocking_issues?: boolean;
  blocking_reason?: string | null;
  tip?: string;
  requisition_id?: number;
  requisition_code?: string;
  computation_id?: number;
  computation_code?: string;
}

export async function previewPushToPurchaseOrder(requisitionId: number): Promise<DocumentPushPreview> {
  return apiRequest(`/apps/kuaizhizao/purchase-requisitions/${requisitionId}/push-to-purchase-order/preview`, {
    method: 'GET',
  });
}

export async function previewPushToInquiry(requisitionId: number): Promise<DocumentPushPreview> {
  return apiRequest(`/apps/kuaizhizao/purchase-requisitions/${requisitionId}/push-to-purchase-inquiry/preview`, {
    method: 'GET',
  });
}

export interface PriceComparisonItem {
  supplier_id: number;
  supplier_name: string;
  last_price: number;
  last_order_date?: string;
  delivery_lead_time: number;
}

export interface MaterialPriceComparison {
  material_id: number;
  material_code?: string;
  material_name: string;
  /** 后端字段名 comparison */
  comparison: PriceComparisonItem[];
}

export interface PriceComparisonResponse {
  results: MaterialPriceComparison[];
}

/** 获取多个物料的价格对比助手数据 */
export async function getPriceComparison(materialIds: number[]): Promise<PriceComparisonResponse> {
  return apiRequest('/apps/kuaizhizao/price-comparison', {
    method: 'GET',
    params: { material_ids: materialIds.join(',') },
  });
}
