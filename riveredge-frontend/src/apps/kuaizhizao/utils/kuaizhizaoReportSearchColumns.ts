import type { ProColumns } from '@ant-design/pro-components';
import type { TFunction } from 'i18next';
import { warehouseApi } from '../../master-data/services/warehouse';
import { materialApi } from '../../master-data/services/material';
import { supplierApi, unwrapSupplyPagedList } from '../../master-data/services/supply-chain';
import {
  mergeColumnFilters,
  parseColumnFiltersParam,
  serializeColumnFiltersParam,
  type AdvancedColumnFilter,
} from '../../../components/uni-query/columnFilterContract';
import { DELIVERY_PROJECT_STATUS } from '../services/delivery-project';
import type { KuaizhizaoReportDomain } from './kuaizhizaoReportCore';
import {
  demandTypeEnum,
  outsourceWorkOrderStatusEnum,
  productionDelayStatusEnum,
  purchaseOrderStatusEnum,
  purchaseRequisitionStatusEnum,
  reportTextEnum,
  salesOrderStatusEnum,
  workOrderStatusEnum,
} from './reportPresentation';

function columnDataIndexKey(col: ProColumns): string | undefined {
  const di = col.dataIndex;
  if (typeof di === 'string') return di;
  if (Array.isArray(di)) return di.join('.');
  return undefined;
}

function hasSearchableColumn(columns: ProColumns[], dataIndex: string): boolean {
  return columns.some((col) => !col.hideInSearch && columnDataIndexKey(col) === dataIndex);
}

function mergeMissingSearchColumns(pageColumns: ProColumns[], injections: ProColumns[]): ProColumns[] {
  const missing = injections.filter((col) => {
    const key = columnDataIndexKey(col);
    return key ? !hasSearchableColumn(pageColumns, key) : false;
  });
  return [...missing, ...pageColumns];
}

async function fetchWarehouseOptions(params?: { keyWords?: string }) {
  const res = await warehouseApi.list({
    ...(params?.keyWords?.trim() ? { keyword: params.keyWords.trim() } : {}),
    is_active: true,
    limit: 200,
  });
  const items = res.items || [];
  return items.map((w) => ({ label: w.name, value: w.id }));
}

async function fetchMaterialOptions(params?: { keyWords?: string }) {
  const res = await materialApi.list({
    ...(params?.keyWords?.trim() ? { keyword: params.keyWords.trim() } : {}),
    isActive: true,
    limit: 50,
  });
  const items = res.items || [];
  return items.map((m) => ({
    label: `${m.code} ${m.name}`,
    value: m.id,
  }));
}

async function fetchSupplierNameOptions(params?: { keyWords?: string }) {
  const res = await supplierApi.list({
    ...(params?.keyWords?.trim() ? { keyword: params.keyWords.trim() } : {}),
    isActive: true,
    limit: 200,
  });
  const items = unwrapSupplyPagedList(res);
  return items.map((s) => ({ label: s.name, value: s.name }));
}

async function fetchSupplierIdOptions(params?: { keyWords?: string }) {
  const res = await supplierApi.list({
    ...(params?.keyWords?.trim() ? { keyword: params.keyWords.trim() } : {}),
    isActive: true,
    limit: 200,
  });
  const items = unwrapSupplyPagedList(res);
  return items.map((s) => ({ label: s.name, value: s.id }));
}

function keywordSearchColumn(t: TFunction, placeholderKey: string, order = 10): ProColumns {
  return {
    title: t('app.kuaizhizao.warehouseReports.keyword'),
    dataIndex: 'keyword',
    hideInTable: true,
    fieldProps: {
      placeholder: t(placeholderKey),
    },
    search: { order },
  };
}

function warehouseSelectColumn(t: TFunction, order = 20): ProColumns {
  return {
    title: t('app.kuaizhizao.warehouseReports.colWarehouse'),
    dataIndex: 'warehouse_id',
    hideInTable: true,
    valueType: 'select',
    request: fetchWarehouseOptions,
    fieldProps: { showSearch: true, allowClear: true },
    search: { order },
  };
}

function materialSelectColumn(t: TFunction, order = 30): ProColumns {
  return {
    title: t('app.kuaizhizao.reports.materialName'),
    dataIndex: 'material_id',
    hideInTable: true,
    valueType: 'select',
    request: fetchMaterialOptions,
    fieldProps: { showSearch: true, allowClear: true },
    search: { order },
  };
}

function statusSelectColumn(
  t: TFunction,
  valueEnum: Record<string, { text: string }>,
  order = 40,
): ProColumns {
  return {
    title: t('app.kuaizhizao.reports.documentStatus'),
    dataIndex: 'status',
    hideInTable: true,
    valueType: 'select',
    valueEnum,
    fieldProps: { allowClear: true },
    search: { order },
  };
}

function supplierNameSelectColumn(t: TFunction, order = 25): ProColumns {
  return {
    title: t('app.kuaizhizao.purchaseReports.colSupplier'),
    dataIndex: 'supplier_name',
    hideInTable: true,
    valueType: 'select',
    request: fetchSupplierNameOptions,
    fieldProps: { showSearch: true, allowClear: true },
    search: { order },
  };
}

function supplierIdSelectColumn(t: TFunction, order = 25): ProColumns {
  return {
    title: t('app.kuaizhizao.purchaseReports.colSupplier'),
    dataIndex: 'supplier_id',
    hideInTable: true,
    valueType: 'select',
    request: fetchSupplierIdOptions,
    fieldProps: { showSearch: true, allowClear: true },
    search: { order },
  };
}

function qualityInspectionStatusEnum(t: TFunction) {
  return reportTextEnum({
    pending: t('app.kuaizhizao.quality.common.status.pending'),
    draft: t('app.kuaizhizao.quality.common.status.draft'),
    inspected: t('app.kuaizhizao.quality.common.status.inspected'),
    reviewed: t('app.kuaizhizao.quality.common.status.reviewed'),
    rejected: t('app.kuaizhizao.quality.common.status.rejected'),
    cancelled: t('app.kuaizhizao.quality.common.status.cancelled'),
  });
}

function buildWarehouseSearchColumns(t: TFunction): ProColumns[] {
  return [
    keywordSearchColumn(
      t,
      'app.kuaizhizao.warehouseReports.keywordPlaceholder',
    ),
    warehouseSelectColumn(t),
    materialSelectColumn(t),
  ];
}

function buildInventorySearchColumns(t: TFunction): ProColumns[] {
  return [
    keywordSearchColumn(
      t,
      'app.kuaizhizao.warehouseReports.keywordPlaceholder',
    ),
    warehouseSelectColumn(t),
  ];
}

function buildSalesSearchColumns(t: TFunction): ProColumns[] {
  return [statusSelectColumn(t, salesOrderStatusEnum(t))];
}

function buildPurchaseSearchColumns(t: TFunction, reportType: string): ProColumns[] {
  const cols: ProColumns[] = [supplierNameSelectColumn(t)];
  if (reportType === 'requisition_tracking') {
    cols.push(statusSelectColumn(t, purchaseRequisitionStatusEnum(t)));
  } else {
    cols.push(statusSelectColumn(t, purchaseOrderStatusEnum(t)));
  }
  return cols;
}

function buildProductionSearchColumns(t: TFunction, reportType: string): ProColumns[] {
  const cols: ProColumns[] = [];
  if (reportType === 'outsource_query' || reportType === 'outsource-work-order-query') {
    cols.push(
      supplierNameSelectColumn(t),
      statusSelectColumn(t, outsourceWorkOrderStatusEnum(t)),
    );
    return cols;
  }
  if (reportType === 'production-delay-warning') {
    cols.push(statusSelectColumn(t, productionDelayStatusEnum(t)));
    return cols;
  }
  cols.push(statusSelectColumn(t, workOrderStatusEnum(t)));
  return cols;
}

function buildPlanSearchColumns(t: TFunction): ProColumns[] {
  return [
    {
      title: t('app.kuaizhizao.reports.demandType'),
      dataIndex: 'demand_type',
      hideInTable: true,
      valueType: 'select',
      valueEnum: demandTypeEnum(t),
      fieldProps: { allowClear: true },
      search: { order: 15 },
    },
    statusSelectColumn(t, salesOrderStatusEnum(t), 25),
  ];
}

function buildQualitySearchColumns(t: TFunction): ProColumns[] {
  return [
    keywordSearchColumn(
      t,
      'app.kuaizhizao.quality.reports.keywordPlaceholder',
    ),
    supplierIdSelectColumn(t),
    statusSelectColumn(t, qualityInspectionStatusEnum(t)),
  ];
}

function buildDeliverySearchColumns(t: TFunction): ProColumns[] {
  return [
    keywordSearchColumn(
      t,
      'app.kuaizhizao.deliveryProject.report.keywordPlaceholder',
    ),
    {
      title: t('common.status'),
      dataIndex: 'status',
      hideInTable: true,
      valueType: 'select',
      valueEnum: reportTextEnum(DELIVERY_PROJECT_STATUS),
      fieldProps: { allowClear: true },
      search: { order: 20 },
    },
  ];
}

function buildDomainSearchColumns(
  domain: KuaizhizaoReportDomain,
  reportType: string,
  t: TFunction,
): ProColumns[] {
  switch (domain) {
    case 'warehouse':
      return buildWarehouseSearchColumns(t);
    case 'inventory':
      return buildInventorySearchColumns(t);
    case 'sales':
      return buildSalesSearchColumns(t);
    case 'purchase':
      return buildPurchaseSearchColumns(t, reportType);
    case 'production':
      return buildProductionSearchColumns(t, reportType);
    case 'plan':
      return buildPlanSearchColumns(t);
    case 'quality':
      return buildQualitySearchColumns(t);
    case 'delivery':
      return buildDeliverySearchColumns(t);
    default:
      return [];
  }
}

/** 合并页面列与域级默认高级搜索列（仅补缺失项，不覆盖页面已有配置） */
export function mergeKuaizhizaoReportSearchColumns(
  pageColumns: ProColumns[],
  options: {
    domain: KuaizhizaoReportDomain;
    reportType: string;
    t: TFunction;
  },
): ProColumns[] {
  const injections = buildDomainSearchColumns(options.domain, options.reportType, options.t);
  if (!injections.length) return pageColumns;
  return mergeMissingSearchColumns(pageColumns, injections);
}

const ALWAYS_NATIVE_KEYS = new Set([
  'keyword',
  'date_range',
  'column_filters',
  'period_basis',
  'warehouse_id',
  'material_id',
  'customer_name',
  'supplier_name',
  'supplier_id',
  'demand_type',
]);

function domainUsesNativeStatus(domain: KuaizhizaoReportDomain): boolean {
  return domain === 'purchase' || domain === 'production' || domain === 'plan' || domain === 'quality';
}

function productionNativeKeys(): Set<string> {
  return new Set(['order_code', 'code', 'product_name', 'material_name', 'work_order_code', 'template_code', 'team_name']);
}

function isEmptySearchValue(value: unknown): boolean {
  if (value === undefined || value === null || value === '') return true;
  if (Array.isArray(value) && value.length === 0) return true;
  return false;
}

/** 字段搜索值并入 column_filters，使文本/枚举筛选在后端列表收尾阶段生效 */
export function augmentReportSearchFormValues(
  searchFormValues: Record<string, unknown> | undefined,
  columns: ProColumns[],
  domain: KuaizhizaoReportDomain,
): Record<string, unknown> {
  if (!searchFormValues) return {};
  const nativeKeys = new Set(ALWAYS_NATIVE_KEYS);
  if (domainUsesNativeStatus(domain)) {
    nativeKeys.add('status');
  }
  if (domain === 'production') {
    productionNativeKeys().forEach((k) => nativeKeys.add(k));
  }
  if (domain === 'delivery') {
    nativeKeys.add('status');
    nativeKeys.add('keyword');
  }

  const searchableColumns = columns.filter(
    (col) => !col.hideInSearch && col.valueType !== 'option' && columnDataIndexKey(col),
  );

  const existing = parseColumnFiltersParam(searchFormValues.column_filters);
  const existingFields = new Set(existing.map((f) => f.field));
  const appended: AdvancedColumnFilter[] = [];

  for (const col of searchableColumns) {
    const field = columnDataIndexKey(col);
    if (!field || nativeKeys.has(field) || existingFields.has(field)) continue;
    const raw = searchFormValues[field];
    if (isEmptySearchValue(raw)) continue;
    const isSelect = col.valueType === 'select' || col.valueEnum;
    appended.push({
      field,
      op: isSelect ? 'eq' : 'contains',
      value: Array.isArray(raw) ? raw.map(String) : String(raw),
    });
  }

  if (!appended.length) return searchFormValues;

  const merged = mergeColumnFilters(existing, appended);
  const serialized = serializeColumnFiltersParam(merged);
  return {
    ...searchFormValues,
    ...(serialized ? { column_filters: serialized } : {}),
  };
}
