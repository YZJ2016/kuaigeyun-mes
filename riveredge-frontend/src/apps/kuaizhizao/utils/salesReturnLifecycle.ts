import { createLifecycleResolver } from './createLifecycleResolver';
import { requireI18nText, type LifecycleTranslateFn } from './lifecycleI18n';
import {
  resolveListLifecycleStageFromSearch,
  toListLifecycleStageApiParams,
} from '../../../utils/listLifecycleStage';
import {
  extractProTableSort,
  pickListSearchKeyword,
  pickSearchString,
} from '../../../utils/tableQueryKey';
import { parseSalesReportDateRange } from '../services/reports';

const P = 'app.kuaizhizao.salesReturn';

export const SALES_RETURN_LIFECYCLE_STAGE_LABELS = ['待退货', '已退货'] as const;

const STAGE_I18N: Record<string, string> = {
  待退货: `${P}.statusPending`,
  已退货: `${P}.statusReturned`,
};

export const getSalesReturnLifecycle = createLifecycleResolver({
  stageDefs: [
    { key: 'pending_return_goods', label: '待退货', labelKey: `${P}.statusPending` },
    { key: 'completed', label: '已退货', labelKey: `${P}.statusReturned` },
  ],
  statusToKey: {
    待退货: 'pending_return_goods',
    已退货: 'completed',
    草稿: 'pending_return_goods',
  },
  nextStepSuggestionKeys: {
    pending_return_goods: [`${P}.lifecycleNextConfirmReturn`],
    completed: [`${P}.lifecycleNextWithdrawConfirm`],
  },
  successKeys: ['completed'],
});

export function buildSalesReturnLifecycleValueEnum(
  t: LifecycleTranslateFn,
): Record<string, { text: string }> {
  return Object.fromEntries(
    SALES_RETURN_LIFECYCLE_STAGE_LABELS.map((stage) => [
      stage,
      { text: requireI18nText(t, STAGE_I18N[stage]!) },
    ]),
  );
}

export function resolveSalesReturnListLifecycleParams(
  searchFormValues?: Record<string, unknown> | null,
  params?: Record<string, unknown> | null,
): { status?: string } {
  const stage = resolveListLifecycleStageFromSearch(searchFormValues, params, {
    allowedStages: [...SALES_RETURN_LIFECYCLE_STAGE_LABELS],
  });
  const api = toListLifecycleStageApiParams(stage);
  return api.lifecycle_stage ? { status: api.lifecycle_stage } : {};
}

export function resolveSalesReturnListApiParams(
  params: { current?: number; pageSize?: number },
  sort?: Record<string, unknown>,
  searchFormValues?: Record<string, unknown> | null,
): Record<string, unknown> {
  const lifecycleParams = resolveSalesReturnListLifecycleParams(searchFormValues, params);
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
    const returnCode = pickSearchString(searchFormValues, 'return_code');
    if (returnCode) apiParams.return_code = returnCode;
  }

  const customerIdRaw = pickSearchString(searchFormValues, 'customer_id');
  if (customerIdRaw != null && Number.isFinite(Number(customerIdRaw))) {
    apiParams.customer_id = Number(customerIdRaw);
  }

  const salesDeliveryCode = pickSearchString(searchFormValues, 'sales_delivery_code');
  if (salesDeliveryCode) apiParams.sales_delivery_code = salesDeliveryCode;

  const salesOrderCode = pickSearchString(searchFormValues, 'sales_order_code');
  if (salesOrderCode) apiParams.sales_order_code = salesOrderCode;

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
