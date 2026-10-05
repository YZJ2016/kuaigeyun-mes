/**
 * 装箱绑定列表生命周期：bound → sealed。
 */

import type { LifecycleResult } from '../../../components/uni-lifecycle/types';
import {
  extractProTableSort,
  pickListSearchKeyword,
  pickSearchString,
} from '../../../utils/tableQueryKey';
import { parseSalesReportDateRange } from '../services/reports';

export function getPackingBindingLifecycle(
  record: Record<string, unknown> | null | undefined
): LifecycleResult {
  if (!record) {
    return { percent: 0, stageName: '-', mainStages: [] };
  }
  const seal = String(record.seal_status || 'bound').toLowerCase();
  const sealed = seal === 'sealed';
  return {
    percent: sealed ? 100 : 60,
    stageName: sealed ? '已封箱' : '已绑定',
    status: sealed ? 'success' : 'process',
    mainStages: [
      { key: 'bound', label: '已绑定', status: 'done' },
      { key: 'sealed', label: '已封箱', status: sealed ? 'done' : 'wait' },
    ],
    nextStepSuggestions: sealed
      ? []
      : [{ key: 'seal', label: '封箱', action: 'seal' }],
  };
}

const PACKING_BINDING_METHOD_KEYS = ['scan', 'manual'] as const;

const PACKING_BINDING_METHOD_I18N: Record<string, string> = {
  scan: 'app.kuaizhizao.packingBinding.bindingMethodScan',
  manual: 'app.kuaizhizao.packingBinding.bindingMethodManual',
};

export function buildPackingBindingMethodValueEnum(
  t: (key: string) => string,
): Record<string, { text: string; status?: 'Success' | 'Default' }> {
  const statusByKey: Record<string, 'Success' | 'Default'> = {
    scan: 'Success',
    manual: 'Default',
  };
  return Object.fromEntries(
    PACKING_BINDING_METHOD_KEYS.map((key) => [
      key,
      { text: t(PACKING_BINDING_METHOD_I18N[key]!), status: statusByKey[key] },
    ]),
  );
}

export function resolvePackingBindingListMethodParams(
  searchFormValues?: Record<string, unknown> | null,
): { binding_method?: string } {
  const binding_method = pickSearchString(searchFormValues, 'binding_method');
  if (!binding_method) return {};
  if (PACKING_BINDING_METHOD_KEYS.includes(binding_method as (typeof PACKING_BINDING_METHOD_KEYS)[number])) {
    return { binding_method };
  }
  return {};
}

const PACKING_BINDING_SOURCE_KEYS = ['finished_goods_receipt', 'sales_delivery'] as const;

const PACKING_BINDING_SOURCE_I18N: Record<string, string> = {
  finished_goods_receipt: 'app.kuaizhizao.packingBinding.sourceFinishedGoodsReceipt',
  sales_delivery: 'app.kuaizhizao.packingBinding.sourceSalesDelivery',
};

export function buildPackingBindingSourceValueEnum(
  t: (key: string) => string,
): Record<string, { text: string }> {
  return Object.fromEntries(
    PACKING_BINDING_SOURCE_KEYS.map((key) => [key, { text: t(PACKING_BINDING_SOURCE_I18N[key]!) }]),
  );
}

export function resolvePackingBindingListSourceParams(
  searchFormValues?: Record<string, unknown> | null,
): { source_type?: string } {
  const source_type = pickSearchString(searchFormValues, 'source_type');
  if (!source_type) return {};
  if (PACKING_BINDING_SOURCE_KEYS.includes(source_type as (typeof PACKING_BINDING_SOURCE_KEYS)[number])) {
    return { source_type };
  }
  return {};
}

export function resolvePackingBindingListApiParams(
  params: { current?: number; pageSize?: number; receipt_id?: unknown; product_id?: unknown; uuid?: unknown },
  sort?: Record<string, unknown>,
  searchFormValues?: Record<string, unknown> | null,
): Record<string, unknown> {
  const methodParams = resolvePackingBindingListMethodParams(searchFormValues);
  const sourceParams = resolvePackingBindingListSourceParams(searchFormValues);
  const { sortBy, sortOrder } = extractProTableSort(sort ?? {});
  const orderBy =
    sortBy && sortOrder ? (sortOrder === 'desc' ? `-${sortBy}` : sortBy) : undefined;
  const fuzzyKeyword = pickListSearchKeyword(searchFormValues);

  const apiParams: Record<string, unknown> = {
    skip: ((params.current ?? 1) - 1) * (params.pageSize ?? 20),
    limit: params.pageSize ?? 20,
    ...methodParams,
    ...sourceParams,
    order_by: orderBy,
    receipt_id: params.receipt_id,
    product_id: params.product_id,
    uuid: params.uuid as string | undefined,
  };

  if (fuzzyKeyword) {
    apiParams.keyword = fuzzyKeyword;
  } else {
    const boxNo = pickSearchString(searchFormValues, 'box_no');
    const productCode = pickSearchString(searchFormValues, 'product_code');
    const productName = pickSearchString(searchFormValues, 'product_name');
    const productSerialNo = pickSearchString(searchFormValues, 'product_serial_no');
    const packingMaterialName = pickSearchString(searchFormValues, 'packing_material_name');
    const sealStatus = pickSearchString(searchFormValues, 'seal_status');
    if (boxNo) apiParams.box_no = boxNo;
    if (productCode) apiParams.product_code = productCode;
    if (productName) apiParams.product_name = productName;
    if (productSerialNo) apiParams.product_serial_no = productSerialNo;
    if (packingMaterialName) apiParams.packing_material_name = packingMaterialName;
    if (sealStatus) apiParams.seal_status = sealStatus;
  }

  const bound = parseSalesReportDateRange(searchFormValues ?? {}, ['bound_at_range']);
  if (bound.date_start) {
    apiParams.bound_at_start_date = bound.date_start;
    apiParams.bound_at_end_date = bound.date_end ?? bound.date_start;
  }
  const created = parseSalesReportDateRange(searchFormValues ?? {}, ['created_at_range', 'createdAtRange']);
  if (created.date_start) {
    apiParams.created_start_date = created.date_start;
    apiParams.created_end_date = created.date_end ?? created.date_start;
  }

  return apiParams;
}
