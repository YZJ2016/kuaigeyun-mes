/**
 * 采购退货单生命周期：待退货 → 已退货；已取消为异常分支。
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

const P = 'app.kuaizhizao.purchaseReturn';

export const PURCHASE_RETURN_LIFECYCLE_STAGE_LABELS = ['待退货', '已退货'] as const;

const STAGE_I18N: Record<string, string> = {
  待退货: `${P}.statusPending`,
  已退货: `${P}.statusReturned`,
};

export const getPurchaseReturnLifecycle = createLifecycleResolver({
  stageDefs: [
    { key: 'pending_return_goods', label: '待退货', labelKey: `${P}.statusPending` },
    { key: 'returned_goods', label: '已退货', labelKey: `${P}.statusReturned` },
  ],
  statusToKey: {
    待退货: 'pending_return_goods',
    已退货: 'returned_goods',
    已取消: 'cancelled',
  },
  nextStepSuggestionKeys: {
    pending_return_goods: [],
    returned_goods: [],
  },
  successKeys: ['returned_goods'],
});

export function buildPurchaseReturnLifecycleValueEnum(
  t: LifecycleTranslateFn,
): Record<string, { text: string }> {
  return Object.fromEntries(
    PURCHASE_RETURN_LIFECYCLE_STAGE_LABELS.map((stage) => [
      stage,
      { text: requireI18nText(t, STAGE_I18N[stage]!) },
    ]),
  );
}

export function resolvePurchaseReturnListLifecycleParams(
  searchFormValues?: Record<string, unknown> | null,
  params?: Record<string, unknown> | null,
): { status?: string } {
  const stage = resolveListLifecycleStageFromSearch(searchFormValues, params, {
    allowedStages: [...PURCHASE_RETURN_LIFECYCLE_STAGE_LABELS],
  });
  const api = toListLifecycleStageApiParams(stage);
  return api.lifecycle_stage ? { status: api.lifecycle_stage } : {};
}

export function resolvePurchaseReturnListApiParams(
  params: { current?: number; pageSize?: number },
  sort?: Record<string, unknown>,
  searchFormValues?: Record<string, unknown> | null,
): Record<string, unknown> {
  const lifecycleParams = resolvePurchaseReturnListLifecycleParams(searchFormValues, params);
  const { sortBy, sortOrder } = extractProTableSort(sort ?? {});
  const orderBy =
    sortBy && sortOrder ? (sortOrder === 'desc' ? `-${sortBy}` : sortBy) : undefined;
  const fuzzyKeyword = pickListSearchKeyword(searchFormValues);

  const apiParams: Record<string, unknown> = {
    skip: ((params.current ?? 1) - 1) * (params.pageSize ?? 20),
    limit: params.pageSize ?? 20,
    ...lifecycleParams,
    order_by: orderBy,
    include_items: true,
  };

  if (fuzzyKeyword) {
    apiParams.keyword = fuzzyKeyword;
  } else {
    const returnCode = pickSearchString(searchFormValues, 'return_code');
    if (returnCode) apiParams.return_code = returnCode;
  }

  const supplierIdRaw = pickSearchString(searchFormValues, 'supplier_id');
  if (supplierIdRaw != null && Number.isFinite(Number(supplierIdRaw))) {
    apiParams.supplier_id = Number(supplierIdRaw);
  }

  const purchaseReceiptCode = pickSearchString(searchFormValues, 'purchase_receipt_code');
  if (purchaseReceiptCode) apiParams.purchase_receipt_code = purchaseReceiptCode;

  const purchaseOrderCode = pickSearchString(searchFormValues, 'purchase_order_code');
  if (purchaseOrderCode) apiParams.purchase_order_code = purchaseOrderCode;

  const returnRange = parseSalesReportDateRange(searchFormValues ?? {}, ['return_time_range']);
  if (returnRange.date_start) {
    apiParams.return_start_date = returnRange.date_start;
    apiParams.return_end_date = returnRange.date_end ?? returnRange.date_start;
  }
  const created = parseSalesReportDateRange(searchFormValues ?? {}, ['created_at_range', 'createdAtRange']);
  if (created.date_start) {
    apiParams.created_start_date = created.date_start;
    apiParams.created_end_date = created.date_end ?? created.date_start;
  }

  return apiParams;
}

export { LIST_LIFECYCLE_STAGE_FIELD };

export interface PurchaseReturnLike {
  status?: string;
  lifecycle?: unknown;
}
