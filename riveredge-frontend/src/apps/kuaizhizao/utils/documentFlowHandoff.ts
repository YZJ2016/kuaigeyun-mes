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
  draftSalesOrderFromQuotation,
  draftSalesReviewFromQuotation,
  type QuotationToSalesOrderDraftResponse,
  type QuotationToSalesReviewDraftResponse,
} from '../services/quotation';
import {
  salesContractApi,
  type ConvertToOrderPayload,
  type SalesContractToSalesOrderDraftResponse,
} from '../services/sales-contract';
import { salesReviewApi } from '../services/sales-review';
import {
  draftPurchaseOrdersFromRequisitionItems,
  draftPurchaseRequisitionFromDemandComputationItems,
  type RequisitionConvertToPurchaseOrderPayload,
} from '../services/purchase-requisition';
import {
  draftPurchaseInquiryFromRequisitionItems,
  draftPurchaseOrdersFromInquiryItems,
  type RequisitionToPurchaseInquiryDraftPayload,
} from '../services/purchase-inquiry';
import { draftPurchaseOrdersFromDemandComputationItems } from '../services/purchase';
import { warehouseApi } from '../services/production';
import {
  draftSalesOrderToPurchaseOrders,
  draftSalesOrderToPurchaseRequisition,
  type PushSalesOrderToPurchaseRequest,
} from '../services/sales-order';

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
const PURCHASE_INQUIRY_CREATE = `${PURCHASE_INQUIRY_LIST}/new`;
const PURCHASE_REQUISITION_LIST = '/apps/kuaizhizao/purchase-management/purchase-requisitions';
const PURCHASE_REQUISITION_CREATE = `${PURCHASE_REQUISITION_LIST}/new`;

const PO_HANDOFF_QUEUE_KEY = 'kuaizhizao:document-flow-po-handoff-queue';

type PoHandoffQueuedDraft = {
  actionKey: KuaizhizaoDocumentActionKey;
  createPath: string;
  search: string;
  createPayload: Record<string, unknown>;
  documentFlow: Record<string, unknown>;
};

type PoHandoffFlowKind =
  | 'purchase_requisition'
  | 'purchase_inquiry'
  | 'demand_computation'
  | 'replenishment_suggestion'
  | 'sales_order';

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
    shell: 'uniTabEntry',
    targetListPath: PURCHASE_INQUIRY_LIST,
    createPath: PURCHASE_INQUIRY_CREATE,
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

export async function handoffQuotationToSalesOrderCreate(
  navigate: NavigateFunction,
  quotationId: number,
  options?: { selectedItemIds?: number[] },
): Promise<void> {
  const config = resolveDocumentFlowHandoff('sales_order.pull_from_quotation');
  if (!config) return;
  const draftRes: QuotationToSalesOrderDraftResponse = await draftSalesOrderFromQuotation(
    quotationId,
    options?.selectedItemIds,
  );
  const search = `?flow=quotation&sourceId=${quotationId}`;
  const createPath = config.createPath;
  writeDocumentFlowCreateDraft(config, createPath, search, {
    createPayload: draftRes.create_payload,
    documentFlow: draftRes.document_flow,
    sourceType: draftRes.source_type,
    sourceId: draftRes.source_id,
    sourceCode: draftRes.source_code,
  });
  navigate(`${createPath}${search}`, {
    state: {
      documentFlowCreate: {
        ...draftRes.create_payload,
        ...draftRes.document_flow,
      },
    },
  });
}

function stashPoHandoffDraftQueue(remaining: PoHandoffQueuedDraft[]): void {
  if (typeof sessionStorage === 'undefined') return;
  if (!remaining.length) {
    sessionStorage.removeItem(PO_HANDOFF_QUEUE_KEY);
    return;
  }
  sessionStorage.setItem(PO_HANDOFF_QUEUE_KEY, JSON.stringify(remaining));
}

function popPoHandoffDraftQueue(): PoHandoffQueuedDraft | null {
  if (typeof sessionStorage === 'undefined') return null;
  const raw = sessionStorage.getItem(PO_HANDOFF_QUEUE_KEY);
  if (!raw) return null;
  try {
    const list = JSON.parse(raw) as PoHandoffQueuedDraft[];
    if (!Array.isArray(list) || list.length === 0) {
      sessionStorage.removeItem(PO_HANDOFF_QUEUE_KEY);
      return null;
    }
    const [next, ...rest] = list;
    stashPoHandoffDraftQueue(rest);
    return next;
  } catch {
    sessionStorage.removeItem(PO_HANDOFF_QUEUE_KEY);
    return null;
  }
}

function openSinglePoHandoffDraft(
  navigate: NavigateFunction,
  config: DocumentFlowHandoffConfig,
  search: string,
  createPayload: Record<string, unknown>,
  documentFlow: Record<string, unknown>,
  sourceType?: string,
): void {
  writeDocumentFlowCreateDraft(config, config.createPath, search, {
    createPayload,
    documentFlow,
    sourceType,
  });
  // 与报价→销售订单一致：navigate state 供 UniTab 新建页 initialValues 即时灌入，
  // 避免仅靠 draft + setTimeout(setFieldsValue) 在 Strict Mode / 表单未挂载时丢明细。
  navigate(`${config.createPath}${search}`, {
    state: {
      documentFlowCreate: {
        ...createPayload,
        ...documentFlow,
      },
    },
  });
}

/** 多草稿 UniTab/FormModal handoff：显式 search（含 sourceId）写入队列，禁止循环 navigate 冲掉前一张。 */
function startUniTabHandoffDraftQueue(
  navigate: NavigateFunction,
  config: DocumentFlowHandoffConfig,
  drafts: Array<{
    search: string;
    createPayload: Record<string, unknown>;
    documentFlow: Record<string, unknown>;
  }>,
  sourceType: string,
): void {
  if (!drafts.length) return;
  const [first, ...rest] = drafts;
  stashPoHandoffDraftQueue(
    rest.map((entry) => ({
      actionKey: config.actionKey,
      createPath: config.createPath,
      search: entry.search,
      createPayload: entry.createPayload,
      documentFlow: entry.documentFlow,
    })),
  );
  openSinglePoHandoffDraft(
    navigate,
    config,
    first.search,
    first.createPayload,
    first.documentFlow,
    sourceType,
  );
}

function startPoHandoffDraftQueue(
  navigate: NavigateFunction,
  config: DocumentFlowHandoffConfig,
  flow: PoHandoffFlowKind,
  drafts: Array<{ create_payload: Record<string, unknown>; document_flow: Record<string, unknown> }>,
  sourceType: string,
): void {
  if (!drafts.length) return;
  const batch = Date.now();
  startUniTabHandoffDraftQueue(
    navigate,
    config,
    drafts.map((entry, index) => ({
      search: `?flow=${flow}&batch=${batch}&seq=${index + 1}`,
      createPayload: entry.create_payload,
      documentFlow: entry.document_flow,
    })),
    sourceType,
  );
}

function mergeSalesOrderPurchaseRequisitionDrafts(
  drafts: Array<{
    create_payload: Record<string, unknown>;
    document_flow: Record<string, unknown>;
    source_code?: string;
    source_id?: number;
  }>,
): { create_payload: Record<string, unknown>; document_flow: Record<string, unknown> } | null {
  if (!drafts.length) return null;
  if (drafts.length === 1) {
    return {
      create_payload: drafts[0]!.create_payload,
      document_flow: drafts[0]!.document_flow,
    };
  }

  const items: Record<string, unknown>[] = [];
  const salesOrderIds: number[] = [];
  const orderCodes: string[] = [];
  let requiredDate: string | undefined;
  let requisitionDate: string | undefined;

  for (const draft of drafts) {
    const payload = draft.create_payload;
    const rowItems = Array.isArray(payload.items)
      ? (payload.items as Record<string, unknown>[])
      : [];
    items.push(...rowItems);

    const soId = Number(
      draft.document_flow.documentFlowSalesOrderId ?? draft.source_id ?? payload.source_id ?? 0,
    );
    if (Number.isFinite(soId) && soId > 0 && !salesOrderIds.includes(soId)) {
      salesOrderIds.push(soId);
    }

    const code = String(draft.source_code ?? payload.source_code ?? '').trim();
    if (code && !orderCodes.includes(code)) {
      orderCodes.push(code);
    }

    const headReq = payload.required_date != null ? String(payload.required_date) : undefined;
    if (headReq && (!requiredDate || headReq < requiredDate)) {
      requiredDate = headReq;
    }
    for (const row of rowItems) {
      const lineReq = row.required_date != null ? String(row.required_date) : undefined;
      if (lineReq && (!requiredDate || lineReq < requiredDate)) {
        requiredDate = lineReq;
      }
    }

    const reqDate = payload.requisition_date != null ? String(payload.requisition_date) : undefined;
    if (reqDate && (!requisitionDate || reqDate < requisitionDate)) {
      requisitionDate = reqDate;
    }
  }

  const first = drafts[0]!;
  const codesLabel =
    orderCodes.length > 0 ? orderCodes.join('、') : salesOrderIds.map(String).join('、');

  return {
    create_payload: {
      ...first.create_payload,
      requisition_name:
        orderCodes.length === 1
          ? first.create_payload.requisition_name
          : `销售订单${codesLabel}请购`,
      requisition_date: requisitionDate ?? first.create_payload.requisition_date,
      required_date: requiredDate ?? first.create_payload.required_date,
      source_type: 'sales_order',
      source_id: salesOrderIds[0] ?? first.create_payload.source_id,
      source_code: orderCodes[0] ?? first.create_payload.source_code,
      notes: `由销售订单 ${codesLabel} 直推生成（按单外购，未做库存抵扣）`,
      items,
    },
    document_flow: {
      documentFlowSourceType: 'sales_order_buy_push',
      documentFlowSalesOrderId: salesOrderIds[0],
      documentFlowSalesOrderIds: salesOrderIds,
    },
  };
}

/** 多张销售订单取行：合并一张采购申请草稿再打开新建页。 */
export async function handoffSalesOrdersToPurchaseRequisitionCreate(
  navigate: NavigateFunction,
  selections: Array<{ salesOrderId: number; payload: PushSalesOrderToPurchaseRequest }>,
): Promise<void> {
  const config = resolveDocumentFlowHandoff('purchase_requisition.pull_from_sales_order');
  if (!config || !selections.length) return;

  const draftPieces: Array<{
    create_payload: Record<string, unknown>;
    document_flow: Record<string, unknown>;
    source_code?: string;
    source_id?: number;
  }> = [];
  for (const sel of selections) {
    const draftRes = await draftSalesOrderToPurchaseRequisition(sel.salesOrderId, sel.payload);
    draftPieces.push({
      create_payload: draftRes.create_payload,
      document_flow: draftRes.document_flow,
      source_code: draftRes.source_code,
      source_id: draftRes.source_id,
    });
  }

  const merged = mergeSalesOrderPurchaseRequisitionDrafts(draftPieces);
  if (!merged) return;

  const primaryId = selections[0]!.salesOrderId;
  const search = `?flow=sales_order&sourceId=${primaryId}`;
  writeDocumentFlowCreateDraft(config, config.createPath, search, {
    createPayload: merged.create_payload,
    documentFlow: merged.document_flow,
    sourceType: 'sales_order',
    sourceId: Number(merged.create_payload.source_id ?? primaryId),
    sourceCode:
      merged.create_payload.source_code != null
        ? String(merged.create_payload.source_code)
        : undefined,
  });
  openSinglePoHandoffDraft(
    navigate,
    config,
    search,
    merged.create_payload,
    merged.document_flow,
    'sales_order',
  );
}

export async function handoffSalesOrderToPurchaseRequisitionCreate(
  navigate: NavigateFunction,
  salesOrderId: number,
  payload: PushSalesOrderToPurchaseRequest,
): Promise<void> {
  await handoffSalesOrdersToPurchaseRequisitionCreate(navigate, [{ salesOrderId, payload }]);
}

export async function handoffSalesOrderToPurchaseOrderCreate(
  navigate: NavigateFunction,
  salesOrderId: number,
  payload: PushSalesOrderToPurchaseRequest,
): Promise<void> {
  const config = resolveDocumentFlowHandoff('purchase_order.pull_from_sales_order');
  if (!config) return;
  const draftRes = await draftSalesOrderToPurchaseOrders(salesOrderId, payload);
  const drafts = draftRes.drafts ?? [];
  if (!drafts.length) return;
  startPoHandoffDraftQueue(navigate, config, 'sales_order', drafts, draftRes.source_type);
}

export async function handoffReplenishmentToPurchaseRequisitionCreate(
  navigate: NavigateFunction,
  suggestionIds: number[],
): Promise<void> {
  const config = resolveDocumentFlowHandoff('purchase_requisition.pull_from_replenishment_suggestion');
  if (!config) return;
  const draftRes = await warehouseApi.replenishmentSuggestion.draftPurchaseRequisition(suggestionIds);
  const search = '?flow=replenishment_suggestion';
  writeDocumentFlowCreateDraft(config, config.createPath, search, {
    createPayload: draftRes.create_payload,
    documentFlow: draftRes.document_flow,
    sourceType: draftRes.source_type,
  });
  openSinglePoHandoffDraft(
    navigate,
    config,
    search,
    draftRes.create_payload,
    draftRes.document_flow,
    draftRes.source_type,
  );
}

export async function handoffReplenishmentToPurchaseOrderCreate(
  navigate: NavigateFunction,
  suggestionIds: number[],
): Promise<void> {
  const config = resolveDocumentFlowHandoff('purchase_order.pull_from_replenishment_suggestion');
  if (!config) return;
  const draftRes = await warehouseApi.replenishmentSuggestion.draftPurchaseOrders(suggestionIds);
  const drafts = draftRes.drafts ?? [];
  if (!drafts.length) return;
  startPoHandoffDraftQueue(navigate, config, 'replenishment_suggestion', drafts, draftRes.source_type);
}

export async function handoffDemandComputationToPurchaseOrderCreate(
  navigate: NavigateFunction,
  selectedItemIds: number[],
  options?: { includeSalesOrderAttachments?: boolean },
): Promise<void> {
  const config = resolveDocumentFlowHandoff('purchase_order.pull_from_demand_computation');
  if (!config) return;
  const draftRes = await draftPurchaseOrdersFromDemandComputationItems(selectedItemIds, options);
  const drafts = draftRes.drafts ?? [];
  if (!drafts.length) return;
  startPoHandoffDraftQueue(navigate, config, 'demand_computation', drafts, draftRes.source_type);
}

export async function handoffDemandComputationToPurchaseRequisitionCreate(
  navigate: NavigateFunction,
  selectedItemIds: number[],
  itemRequiredDates?: Array<{ item_id: number; required_date: string }>,
  options?: { includeSalesOrderAttachments?: boolean },
): Promise<void> {
  const config = resolveDocumentFlowHandoff('purchase_requisition.pull_from_demand_computation');
  if (!config) return;
  const draftRes = await draftPurchaseRequisitionFromDemandComputationItems(
    selectedItemIds,
    itemRequiredDates,
    options,
  );
  const search = '?flow=demand_computation';
  writeDocumentFlowCreateDraft(config, config.createPath, search, {
    createPayload: draftRes.create_payload,
    documentFlow: draftRes.document_flow,
    sourceType: draftRes.source_type,
  });
  openSinglePoHandoffDraft(
    navigate,
    config,
    search,
    draftRes.create_payload,
    draftRes.document_flow,
    draftRes.source_type,
  );
}

export async function handoffRequisitionToPurchaseInquiryCreate(
  navigate: NavigateFunction,
  payload: RequisitionToPurchaseInquiryDraftPayload,
): Promise<void> {
  const config = resolveDocumentFlowHandoff('purchase_inquiry.pull_from_requisition');
  if (!config) return;
  const draftRes = await draftPurchaseInquiryFromRequisitionItems(payload);
  const search = '?flow=purchase_requisition';
  writeDocumentFlowCreateDraft(config, config.createPath, search, {
    createPayload: draftRes.create_payload,
    documentFlow: draftRes.document_flow,
    sourceType: draftRes.source_type,
  });
  navigate(`${config.createPath}${search}`);
}

export async function handoffRequisitionToPurchaseOrderCreate(
  navigate: NavigateFunction,
  payload: RequisitionConvertToPurchaseOrderPayload | { selected_item_ids: number[] },
): Promise<void> {
  const config = resolveDocumentFlowHandoff('purchase_order.pull_from_requisition');
  if (!config) return;
  const draftRes = await draftPurchaseOrdersFromRequisitionItems(payload);
  const drafts = draftRes.drafts ?? [];
  if (!drafts.length) return;
  startPoHandoffDraftQueue(navigate, config, 'purchase_requisition', drafts, draftRes.source_type);
}

export async function handoffInquiryToPurchaseOrderCreate(
  navigate: NavigateFunction,
  payload: { selected_item_ids: number[] } | { item_ids: number[] },
): Promise<void> {
  const config = resolveDocumentFlowHandoff('purchase_order.pull_from_inquiry');
  if (!config) return;
  const draftRes = await draftPurchaseOrdersFromInquiryItems(payload);
  const drafts = draftRes.drafts ?? [];
  if (!drafts.length) return;
  startPoHandoffDraftQueue(navigate, config, 'purchase_inquiry', drafts, draftRes.source_type);
}

/** 保存当前采购单后若队列中还有后续 handoff 草稿，打开下一张新建页 */
export function continuePoHandoffQueueIfAny(navigate: NavigateFunction): boolean {
  const next = popPoHandoffDraftQueue();
  if (!next) return false;
  const config = resolveDocumentFlowHandoff(next.actionKey);
  if (!config) return false;
  const flow = new URLSearchParams(next.search).get('flow');
  const sourceType =
    flow === 'purchase_inquiry'
      ? 'purchase_inquiry'
      : flow === 'demand_computation'
        ? 'demand_computation'
        : flow === 'replenishment_suggestion'
          ? 'replenishment_suggestion'
          : flow === 'sales_order'
            ? 'sales_order'
            : flow === 'quotation'
              ? 'quotation'
              : flow === 'sales_contract'
                ? 'sales_contract'
                : flow === 'sales_review'
                  ? 'sales_review'
                  : 'purchase_requisition';
  openSinglePoHandoffDraft(
    navigate,
    config,
    next.search,
    next.createPayload,
    next.documentFlow,
    sourceType,
  );
  return true;
}

export async function handoffSalesReviewToSalesOrderCreate(
  navigate: NavigateFunction,
  reviewId: number,
): Promise<void> {
  const config = resolveDocumentFlowHandoff('sales_order.pull_from_sales_review');
  if (!config) return;
  const draftRes = await salesReviewApi.draftSalesOrderFromSalesReview(reviewId);
  const search = `?flow=sales_review&sourceId=${reviewId}`;
  writeDocumentFlowCreateDraft(config, config.createPath, search, {
    createPayload: draftRes.create_payload,
    documentFlow: draftRes.document_flow,
    sourceType: draftRes.source_type,
    sourceId: draftRes.source_id,
    sourceCode: draftRes.source_code,
  });
  navigate(`${config.createPath}${search}`);
}

export async function handoffSalesContractToSalesOrderCreate(
  navigate: NavigateFunction,
  contractId: number,
  options?: { convertPayload?: ConvertToOrderPayload | null },
): Promise<void> {
  const config = resolveDocumentFlowHandoff('sales_order.pull_from_sales_contract');
  if (!config) return;
  const draftRes: SalesContractToSalesOrderDraftResponse =
    await salesContractApi.draftSalesOrderFromSalesContract(contractId, options?.convertPayload ?? {});
  const search = `?flow=sales_contract&sourceId=${contractId}`;
  writeDocumentFlowCreateDraft(config, config.createPath, search, {
    createPayload: draftRes.create_payload,
    documentFlow: draftRes.document_flow,
    sourceType: draftRes.source_type,
    sourceId: draftRes.source_id,
    sourceCode: draftRes.source_code,
  });
  navigate(`${config.createPath}${search}`);
}

export async function handoffQuotationToSalesReviewCreate(
  navigate: NavigateFunction,
  quotationId: number,
  options?: { selectedItemIds?: number[] },
): Promise<void> {
  await handoffQuotationsToSalesReviewCreate(navigate, [
    { quotationId, selectedItemIds: options?.selectedItemIds },
  ]);
}

/** 跨多张报价单取行建评审：先汇总 draft 再开队列。 */
export async function handoffQuotationsToSalesReviewCreate(
  navigate: NavigateFunction,
  selections: Array<{ quotationId: number; selectedItemIds?: number[] }>,
): Promise<void> {
  const config = resolveDocumentFlowHandoff('sales_review.pull_from_quotation');
  if (!config || !selections.length) return;
  const drafts: Array<{
    search: string;
    createPayload: Record<string, unknown>;
    documentFlow: Record<string, unknown>;
  }> = [];
  let sourceType = 'quotation';
  for (const sel of selections) {
    const draftRes: QuotationToSalesReviewDraftResponse = await draftSalesReviewFromQuotation(
      sel.quotationId,
      sel.selectedItemIds,
    );
    sourceType = draftRes.source_type || sourceType;
    drafts.push({
      search: `?flow=quotation&sourceId=${sel.quotationId}`,
      createPayload: draftRes.create_payload,
      documentFlow: draftRes.document_flow,
    });
  }
  startUniTabHandoffDraftQueue(navigate, config, drafts, sourceType);
}

const DC_TO_WO_HANDOFF_KEY = 'kuaizhizao:dc-to-wo-handoff';

export type DemandComputationToWorkOrderHandoffPayload = {
  computationId: number;
  selectedItemIds?: number[];
  pushMode?: 'draft' | 'confirm';
  workOrderGranularity?: 'grouped' | 'individual';
};

/** 工单页深链打开预览时读取并清除（须与 computationId 一致）。 */
export function consumeDemandComputationToWorkOrderHandoff(
  computationId: number,
): Omit<DemandComputationToWorkOrderHandoffPayload, 'computationId'> | null {
  if (!(computationId > 0)) return null;
  try {
    const raw = sessionStorage.getItem(DC_TO_WO_HANDOFF_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DemandComputationToWorkOrderHandoffPayload;
    if (Number(parsed.computationId) !== computationId) return null;
    sessionStorage.removeItem(DC_TO_WO_HANDOFF_KEY);
    return {
      selectedItemIds: parsed.selectedItemIds,
      pushMode: parsed.pushMode,
      workOrderGranularity: parsed.workOrderGranularity,
    };
  } catch {
    sessionStorage.removeItem(DC_TO_WO_HANDOFF_KEY);
    return null;
  }
}

/** 需求计算下推工单：在工单列表打开「从需求计算创建」预览（复杂录入，UniTab + 下游 Modal）。 */
export function handoffDemandComputationToWorkOrderPull(
  navigate: NavigateFunction,
  computationId: number,
  options?: Omit<DemandComputationToWorkOrderHandoffPayload, 'computationId'>,
): void {
  if (!(computationId > 0)) return;
  const payload: DemandComputationToWorkOrderHandoffPayload = {
    computationId,
    ...options,
  };
  sessionStorage.setItem(DC_TO_WO_HANDOFF_KEY, JSON.stringify(payload));
  navigate(`${WORK_ORDERS_LIST}?pullFromDemandComputationId=${computationId}`);
}

/** 销售订单下推工单：在工单列表打开「从销售订单创建」预览（复杂录入，UniTab + 下游 Modal）。 */
export function handoffSalesOrderToWorkOrderPull(
  navigate: NavigateFunction,
  salesOrderId: number,
): void {
  if (!(salesOrderId > 0)) return;
  navigate(`${WORK_ORDERS_LIST}?pullFromSalesOrderId=${salesOrderId}`);
}
