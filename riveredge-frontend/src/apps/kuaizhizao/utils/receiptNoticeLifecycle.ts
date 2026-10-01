/**
 * 收货通知生命周期：待收货→已通知→已入库
 */

import { createLifecycleResolver } from './createLifecycleResolver';
import { requireI18nText, type LifecycleTranslateFn } from './lifecycleI18n';
import {
  LIST_LIFECYCLE_STAGE_FIELD,
  resolveListLifecycleStageFromSearch,
  toListLifecycleStageApiParams,
} from '../../../utils/listLifecycleStage';
import {
  extractProTableSort,
  pickListSearchKeyword,
  pickSearchString,
} from '../../../utils/tableQueryKey';
import { parseSalesReportDateRange } from '../services/reports';

const P = 'app.kuaizhizao.receiptNotice';

export const RECEIPT_NOTICE_LIFECYCLE_STAGE_LABELS = ['待收货', '已通知', '已入库'] as const;

const STAGE_I18N: Record<string, string> = {
  待收货: `${P}.statusPendingReceipt`,
  已通知: 'app.kuaizhizao.shipmentNotice.statusNotified',
  已入库: `${P}.statusReceived`,
};

export const getReceiptNoticeLifecycle = createLifecycleResolver({
  stageDefs: [
    { key: 'pending_receive', label: '待收货', labelKey: `${P}.statusPendingReceipt` },
    { key: 'notified', label: '已通知', labelKey: 'app.kuaizhizao.shipmentNotice.statusNotified' },
    { key: 'received', label: '已入库', labelKey: `${P}.statusReceived` },
  ],
  statusToKey: {
    待收货: 'pending_receive',
    已通知: 'notified',
    已入库: 'received',
  },
  nextStepSuggestionKeys: {},
  successKeys: ['received'],
});

export function buildReceiptNoticeLifecycleValueEnum(
  t: LifecycleTranslateFn,
): Record<string, { text: string }> {
  return Object.fromEntries(
    RECEIPT_NOTICE_LIFECYCLE_STAGE_LABELS.map((stage) => [
      stage,
      { text: requireI18nText(t, STAGE_I18N[stage]!) },
    ]),
  );
}

/** 列表 API 用 status 筛选；生命周期阶段与业务 status 一致 */
export function resolveReceiptNoticeListLifecycleParams(
  searchFormValues?: Record<string, unknown> | null,
  params?: Record<string, unknown> | null,
): { status?: string } {
  const stage = resolveListLifecycleStageFromSearch(searchFormValues, params, {
    allowedStages: [...RECEIPT_NOTICE_LIFECYCLE_STAGE_LABELS],
  });
  const api = toListLifecycleStageApiParams(stage);
  return api.lifecycle_stage ? { status: api.lifecycle_stage } : {};
}

export function resolveReceiptNoticeListApiParams(
  params: { current?: number; pageSize?: number },
  sort?: Record<string, unknown>,
  searchFormValues?: Record<string, unknown> | null,
): Record<string, unknown> {
  const lifecycleParams = resolveReceiptNoticeListLifecycleParams(searchFormValues, params);
  const { sortBy, sortOrder } = extractProTableSort(sort ?? {});
  const orderBy =
    sortBy && sortOrder ? (sortOrder === 'desc' ? `-${sortBy}` : sortBy) : undefined;
  const fuzzyKeyword = pickListSearchKeyword(searchFormValues);

  const apiParams: Record<string, unknown> = {
    skip: ((params.current || 1) - 1) * (params.pageSize || 20),
    limit: params.pageSize || 20,
    ...lifecycleParams,
    order_by: orderBy,
    include_items: true,
  };

  if (fuzzyKeyword) {
    apiParams.keyword = fuzzyKeyword;
  } else {
    const noticeCode = pickSearchString(searchFormValues, 'notice_code');
    if (noticeCode) apiParams.notice_code = noticeCode;
  }

  const supplierIdRaw = pickSearchString(searchFormValues, 'supplier_id');
  if (supplierIdRaw != null && Number.isFinite(Number(supplierIdRaw))) {
    apiParams.supplier_id = Number(supplierIdRaw);
  }

  const purchaseOrderCode = pickSearchString(searchFormValues, 'purchase_order_code');
  if (purchaseOrderCode) apiParams.purchase_order_code = purchaseOrderCode;

  const planned = parseSalesReportDateRange(searchFormValues ?? {}, ['planned_receipt_date_range']);
  if (planned.date_start) {
    apiParams.planned_start_date = planned.date_start;
    apiParams.planned_end_date = planned.date_end ?? planned.date_start;
  }
  const created = parseSalesReportDateRange(searchFormValues ?? {}, ['created_at_range', 'createdAtRange']);
  if (created.date_start) {
    apiParams.created_start_date = created.date_start;
    apiParams.created_end_date = created.date_end ?? created.date_start;
  }

  return apiParams;
}

export { LIST_LIFECYCLE_STAGE_FIELD };
