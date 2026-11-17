/**
 * 已下推单据「转到」：按 document_type 跳转业务列表并带 keyword/id 筛选。
 * 列表侧由 UniTable 读取 URL `keyword` 应用模糊搜索。
 */

import { ROUTES } from '../../apps/kuaizhizao/constants/routes';
import type { UniPushLinkedDocument } from './index';

const APP_BASE = '/apps/kuaizhizao';

/** 下推下游类型 → 业务列表 path（与侧栏 / 路由一致） */
export const PUSHED_DOCUMENT_LIST_PATHS: Record<string, string> = {
  work_order: ROUTES.WORK_ORDERS,
  shipment_notice: ROUTES.SHIPMENT_NOTICES,
  sales_delivery: ROUTES.WM_OUTBOUND,
  sales_return: ROUTES.SALES_RETURNS,
  demand_computation: ROUTES.DEMAND_COMPUTATION,
  purchase_requisition: ROUTES.PURCHASE_REQUISITIONS,
  purchase_order: ROUTES.PURCHASE_ORDERS,
  purchase_return: ROUTES.PURCHASE_RETURNS,
  payment_application: `${APP_BASE}/purchase-management/payment-applications`,
  sales_order: ROUTES.SALES_ORDERS,
  sales_forecast: ROUTES.SALES_FORECASTS,
  quotation: ROUTES.QUOTATIONS,
  sales_contract: `${APP_BASE}/sales-management/sales-contracts`,
  sales_order_change: `${APP_BASE}/sales-management/sales-order-changes`,
  sales_invoice: `${APP_BASE}/finance-management/sales-invoices`,
  receipt: `${APP_BASE}/finance-management/receipts`,
  delivery_project: `${APP_BASE}/delivery-project/projects`,
  sales_review: `${APP_BASE}/sales-management/sales-reviews`,
};

/** 有独立详情页时优先深链到详情（无需再靠列表筛选） */
const PUSHED_DOCUMENT_DETAIL_PATH_BUILDERS: Record<
  string,
  (documentId: number) => string
> = {
  delivery_project: (id) => `${APP_BASE}/delivery-project/projects/${id}`,
  sales_invoice: (id) => `${APP_BASE}/finance-management/sales-invoices/${id}`,
};

export function resolvePushedDocumentListPath(documentType: string): string | null {
  const key = String(documentType || '').trim();
  if (!key) return null;
  return PUSHED_DOCUMENT_LIST_PATHS[key] || null;
}

/**
 * 构建「转到」地址：有详情页则直达；否则列表 + keyword/id。
 */
export function buildPushedDocumentNavigateUrl(doc: UniPushLinkedDocument): string | null {
  const docType = String(doc.documentType || '').trim();
  const docId = Number(doc.documentId);
  if (!docType || !Number.isFinite(docId) || docId <= 0) return null;

  const detailBuilder = PUSHED_DOCUMENT_DETAIL_PATH_BUILDERS[docType];
  if (detailBuilder) {
    return detailBuilder(docId);
  }

  const listPath = resolvePushedDocumentListPath(docType);
  if (!listPath) return null;

  const params = new URLSearchParams();
  const code = String(doc.documentCode || '').trim();
  if (code) {
    params.set('keyword', code);
  }
  params.set('id', String(docId));
  return `${listPath}?${params.toString()}`;
}

export function canNavigateToPushedDocument(doc: UniPushLinkedDocument): boolean {
  if (doc.isDeleted) return false;
  return buildPushedDocumentNavigateUrl(doc) != null;
}
