/**
 * 交付项目节点关联单据：新建意图（sessionStorage）与创建后自动关联。
 */

import type { NavigateFunction } from 'react-router-dom';
import type { TFunction } from 'i18next';
import type { MessageInstance } from 'antd/es/message/interface';
import {
  deliveryProjectApi,
  DELIVERY_NODE_DOCUMENT_TYPES,
  type DeliveryNodeDocumentKind,
} from '../../../services/delivery-project';

export const DELIVERY_NODE_DOCUMENT_LINK_INTENT_KEY = 'delivery_node_document_link_intent';

export interface DeliveryNodeDocumentLinkIntent {
  projectId: number;
  nodeId: number;
  docType: DeliveryNodeDocumentKind;
  returnPath: string;
}

export function saveDeliveryNodeDocumentLinkIntent(intent: DeliveryNodeDocumentLinkIntent): void {
  sessionStorage.setItem(DELIVERY_NODE_DOCUMENT_LINK_INTENT_KEY, JSON.stringify(intent));
}

export function peekDeliveryNodeDocumentLinkIntent(): DeliveryNodeDocumentLinkIntent | null {
  try {
    const raw = sessionStorage.getItem(DELIVERY_NODE_DOCUMENT_LINK_INTENT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DeliveryNodeDocumentLinkIntent;
    if (!parsed?.projectId || !parsed?.nodeId || !parsed?.docType || !parsed?.returnPath) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function clearDeliveryNodeDocumentLinkIntent(): void {
  sessionStorage.removeItem(DELIVERY_NODE_DOCUMENT_LINK_INTENT_KEY);
}

export function isDeliveryCreateQuery(search: string): boolean {
  return new URLSearchParams(search).get('delivery_create') === '1';
}

export function stripDeliveryCreateQuery(search: string): string {
  const sp = new URLSearchParams(search);
  sp.delete('delivery_create');
  sp.delete('sales_order_id');
  const next = sp.toString();
  return next ? `?${next}` : '';
}

type CreateNavContext = {
  projectId: number;
  nodeId: number;
  returnPath: string;
  salesOrderId?: number | null;
};

export function buildDeliveryNodeDocumentCreatePath(
  docType: DeliveryNodeDocumentKind,
  ctx: CreateNavContext,
): string | null {
  saveDeliveryNodeDocumentLinkIntent({
    projectId: ctx.projectId,
    nodeId: ctx.nodeId,
    docType,
    returnPath: ctx.returnPath,
  });

  switch (docType) {
    case 'work_order': {
      const sp = new URLSearchParams({ delivery_create: '1' });
      if (ctx.salesOrderId) sp.set('sales_order_id', String(ctx.salesOrderId));
      return `/apps/kuaizhizao/production-execution/work-orders?${sp.toString()}`;
    }
    case 'purchase_order':
      return '/apps/kuaizhizao/purchase-management/purchase-orders/new?delivery_create=1';
    case 'rd_project':
      return '/apps/kuaiplm/rd-projects?delivery_create=1';
    case 'sales_order':
      return '/apps/kuaizhizao/sales-management/sales-orders?delivery_create=1';
    case 'purchase_receipt':
      return '/apps/kuaizhizao/purchase-management/inbound?delivery_create=1';
    case 'sales_delivery':
      return '/apps/kuaizhizao/sales-management/outbound?delivery_create=1';
    case 'quality_inspection':
      return '/apps/kuaizhizao/quality-management/incoming-inspections?delivery_create=1';
    default:
      return null;
  }
}

export const DELIVERY_NODE_DOCUMENT_AUTO_LINK_TYPES = new Set<DeliveryNodeDocumentKind>([
  'work_order',
  'purchase_order',
  'rd_project',
]);

export async function completeDeliveryNodeDocumentLinkIfPending(params: {
  docType: DeliveryNodeDocumentKind;
  docId: number;
  docCode: string;
  title?: string | null;
  navigate: NavigateFunction;
  message: MessageInstance;
  t: TFunction;
}): Promise<boolean> {
  const intent = peekDeliveryNodeDocumentLinkIntent();
  if (!intent || intent.docType !== params.docType) {
    return false;
  }
  if (!DELIVERY_NODE_DOCUMENT_AUTO_LINK_TYPES.has(params.docType)) {
    clearDeliveryNodeDocumentLinkIntent();
    return false;
  }
  try {
    await deliveryProjectApi.linkNodeDocument(intent.projectId, {
      node_id: intent.nodeId,
      doc_type: params.docType,
      doc_id: params.docId,
      doc_code: params.docCode,
      title: params.title ?? params.docCode,
    });
    clearDeliveryNodeDocumentLinkIntent();
    params.message.success(
      params.t('app.kuaizhizao.deliveryProject.nodeDocumentCreateLinked', {
        docType: DELIVERY_NODE_DOCUMENT_TYPES[params.docType] ?? params.docType,
        docCode: params.docCode,
      }),
    );
    params.navigate(intent.returnPath);
    return true;
  } catch (error: unknown) {
    params.message.error((error as Error)?.message ?? params.t('common.operationFailed'));
    return false;
  }
}
