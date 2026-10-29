/**
 * 系统内上拉/下推：选源或校验后写入草稿，打开下游新建 FormModal 或 UniTab 录入页；保存时才 create。
 */
import type { NavigateFunction } from 'react-router-dom';
import dayjs from '../../../config/dayjs';
import type { KuaizhizaoDocumentActionKey } from '../constants/documentActionRegistry';
import {
  buildDocumentCreateDraftKey,
  setDocumentFormDraft,
} from '../../../utils/documentFormDraftCache';
import { coerceFormDate } from '../../../utils/formDate';
import {

export type DocumentFlowShell = 'formModal' | 'uniTabEntry';

export type DocumentFlowHandoffConfig = {
  actionKey: KuaizhizaoDocumentActionKey;
  shell: DocumentFlowShell;
  /** 下游列表 path（UniTab 新建/录入） */
  targetListPath: string;
  /** 新建页 path 或带 :id 的 entry 前缀 */
  createPath: string;
  draftResourceKey: string;
};

const SALES_ORDER_LIST = '/apps/kuaizhizao/sales-management/sales-orders';
const SALES_ORDER_CREATE = `${SALES_ORDER_LIST}/new`;
const SALES_REVIEW_LIST = '/apps/kuaizhizao/sales-management/sales-reviews';
const WORK_ORDERS_LIST = '/apps/kuaizhizao/production-execution/work-orders';
const PURCHASE_ORDER_LIST = '/apps/kuaizhizao/purchase-management/purchase-orders';
const PURCHASE_ORDER_CREATE = `${PURCHASE_ORDER_LIST}/new`;
const PURCHASE_INQUIRY_LIST = '/apps/kuaizhizao/purchase-management/purchase-inquiries';
const PURCHASE_REQUISITION_LIST = '/apps/kuaizhizao/purchase-management/purchase-requisitions';
const PURCHASE_REQUISITION_CREATE = `${PURCHASE_REQUISITION_LIST}/new`;

/** 已落地 handoff 的 action；其余链路在 `.cursor/memory/features/document-flow-handoff.md` 标注待迁。 */
export const DOCUMENT_FLOW_HANDOFF_REGISTRY: Partial<
  Record<KuaizhizaoDocumentActionKey, DocumentFlowHandoffConfig>
> = {
  'sales_order.pull_from_quotation': {
    actionKey: 'sales_order.pull_from_quotation',
    shell: 'uniTabEntry',
    targetListPath: SALES_ORDER_LIST,
    createPath: SALES_ORDER_CREATE,
    draftResourceKey: 'kuaizhizao:sales-order',
  },
  'sales_review.pull_from_quotation': {
    actionKey: 'sales_review.pull_from_quotation',
    shell: 'formModal',
    targetListPath: SALES_REVIEW_LIST,
    createPath: SALES_REVIEW_LIST,
    draftResourceKey: 'kuaizhizao:sales-review',
  },
  'sales_order.pull_from_sales_contract': {
    actionKey: 'sales_order.pull_from_sales_contract',
    shell: 'uniTabEntry',
    targetListPath: SALES_ORDER_LIST,
    createPath: SALES_ORDER_CREATE,
    draftResourceKey: 'kuaizhizao:sales-order',
  },
  'sales_order.pull_from_sales_review': {
    actionKey: 'sales_order.pull_from_sales_review',
    shell: 'uniTabEntry',
    targetListPath: SALES_ORDER_LIST,
    createPath: SALES_ORDER_CREATE,
    draftResourceKey: 'kuaizhizao:sales-order',
  },
  'purchase_order.pull_from_requisition': {
    actionKey: 'purchase_order.pull_from_requisition',
    shell: 'uniTabEntry',
    targetListPath: PURCHASE_ORDER_LIST,
    createPath: PURCHASE_ORDER_CREATE,
    draftResourceKey: 'kuaizhizao:purchase-order',
  },
  'purchase_inquiry.pull_from_requisition': {
    actionKey: 'purchase_inquiry.pull_from_requisition',
    shell: 'formModal',
    targetListPath: PURCHASE_INQUIRY_LIST,
    createPath: PURCHASE_INQUIRY_LIST,
    draftResourceKey: 'kuaizhizao:purchase-inquiry',
  },
  'purchase_order.pull_from_inquiry': {
    actionKey: 'purchase_order.pull_from_inquiry',
    shell: 'uniTabEntry',
    targetListPath: PURCHASE_ORDER_LIST,
    createPath: PURCHASE_ORDER_CREATE,
    draftResourceKey: 'kuaizhizao:purchase-order',
  },
  'purchase_requisition.pull_from_demand_computation': {
    actionKey: 'purchase_requisition.pull_from_demand_computation',
    shell: 'uniTabEntry',
    targetListPath: PURCHASE_REQUISITION_LIST,
    createPath: PURCHASE_REQUISITION_CREATE,
    draftResourceKey: 'kuaizhizao:purchase-requisition',
  },
  'purchase_order.pull_from_demand_computation': {
    actionKey: 'purchase_order.pull_from_demand_computation',
    shell: 'uniTabEntry',
    targetListPath: PURCHASE_ORDER_LIST,
    createPath: PURCHASE_ORDER_CREATE,
    draftResourceKey: 'kuaizhizao:purchase-order',
  },
  'purchase_requisition.pull_from_replenishment_suggestion': {
    actionKey: 'purchase_requisition.pull_from_replenishment_suggestion',
    shell: 'uniTabEntry',
    targetListPath: PURCHASE_REQUISITION_LIST,
    createPath: PURCHASE_REQUISITION_CREATE,
    draftResourceKey: 'kuaizhizao:purchase-requisition',
  },
  'purchase_order.pull_from_replenishment_suggestion': {
    actionKey: 'purchase_order.pull_from_replenishment_suggestion',
    shell: 'uniTabEntry',
    targetListPath: PURCHASE_ORDER_LIST,
    createPath: PURCHASE_ORDER_CREATE,
    draftResourceKey: 'kuaizhizao:purchase-order',
  },
  'purchase_requisition.pull_from_sales_order': {
    actionKey: 'purchase_requisition.pull_from_sales_order',
    shell: 'uniTabEntry',
    targetListPath: PURCHASE_REQUISITION_LIST,
    createPath: PURCHASE_REQUISITION_CREATE,
    draftResourceKey: 'kuaizhizao:purchase-requisition',
  },
  'purchase_order.pull_from_sales_order': {
    actionKey: 'purchase_order.pull_from_sales_order',
    shell: 'uniTabEntry',
    targetListPath: PURCHASE_ORDER_LIST,
    createPath: PURCHASE_ORDER_CREATE,
    draftResourceKey: 'kuaizhizao:purchase-order',
  },
  // 采购/计划/财务等下一阶段：补 BE draft 后在此登记 shell（formModal | uniTabEntry）
};

export function resolveDocumentFlowHandoff(
  actionKey: KuaizhizaoDocumentActionKey,
): DocumentFlowHandoffConfig | undefined {
  return DOCUMENT_FLOW_HANDOFF_REGISTRY[actionKey];
}

export type DocumentFlowDraftEnvelope = {
  createPayload: Record<string, unknown>;
  documentFlow?: Record<string, unknown>;
  sourceType?: string;
  sourceId?: number;
  sourceCode?: string;
};

/** 下游新建页 setFieldsValue 前须规范化日期（与 writeDocumentFlowCreateDraft 一致）。 */
export function hydrateDocumentFlowCreateFormValues(
  raw: Record<string, unknown>,
): Record<string, unknown> {
  return hydrateDocumentFlowDraftPayload(raw);
}

function hydrateDocumentFlowDraftPayload(raw: Record<string, unknown>): Record<string, unknown> {
  const next = { ...raw };
  for (const key of [
    'order_date',
    'delivery_date',
    'review_date',
    'inquiry_date',
    'quote_deadline',
    'requisition_date',
    'required_date',
  ] as const) {
    if (next[key] != null) {
      next[key] = coerceFormDate(next[key]) ?? dayjs();
    }
  }
  const items = next.items;
  if (Array.isArray(items)) {
    next.items = items.map((row) => {
      const line = { ...(row as Record<string, unknown>) };
      if (line.delivery_date != null) {
        line.delivery_date = coerceFormDate(line.delivery_date) ?? undefined;
      }
      if (line.required_date != null) {
        line.required_date = coerceFormDate(line.required_date) ?? undefined;
      }
      return line;
    });
  }
  return next;
}

export function writeDocumentFlowCreateDraft(
  config: DocumentFlowHandoffConfig,
  createPath: string,
  search: string,
  envelope: DocumentFlowDraftEnvelope,
): string {
  const payload = hydrateDocumentFlowDraftPayload(envelope.createPayload);
  const draftKey = buildDocumentCreateDraftKey(config.draftResourceKey, createPath, search);
  setDocumentFormDraft(draftKey, {
    ...payload,
    ...(envelope.documentFlow ?? {}),
    _documentFlowMeta: {
      actionKey: config.actionKey,
      sourceType: envelope.sourceType,
      sourceId: envelope.sourceId,
      sourceCode: envelope.sourceCode,
    },
  });
  return draftKey;
}


/** 销售订单下推工单：在工单列表打开「从销售订单创建」预览（复杂录入，UniTab + 下游 Modal）。 */
export function handoffSalesOrderToWorkOrderPull(
  navigate: NavigateFunction,
  salesOrderId: number,
): void {
  if (!(salesOrderId > 0)) return;
  navigate(`${WORK_ORDERS_LIST}?pullFromSalesOrderId=${salesOrderId}`);
}
