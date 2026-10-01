import type { ProColumns } from '@ant-design/pro-components';
import {
  extractProTableSort,
  pickListSearchKeyword,
  pickSearchString,
  pickSearchTriStateBoolean,
} from '../../../utils/tableQueryKey';
import { parseSalesReportDateRange } from '../../kuaizhizao/services/reports';
import {
  buildMasterCrudActiveValueEnum,
  formatMasterDateTimeCell,
  MASTER_CRUD_PINNED_ACTIVE_FIELD,
  MASTER_DATA_LIST_FIELD_RANK,
  masterCrudCodeNameSearchColumns,
  masterCrudCreatedUpdatedColumns,
  pickOptionalString,
} from './masterListCore';
import { masterCrudCreatedUpdatedSnakeColumns } from './materialListCore';

export {
  buildMasterCrudActiveValueEnum,
  formatMasterDateTimeCell,
  MASTER_CRUD_PINNED_ACTIVE_FIELD,
  MASTER_DATA_LIST_FIELD_RANK,
  masterCrudCodeNameSearchColumns,
  masterCrudCreatedUpdatedColumns,
  masterCrudCreatedUpdatedSnakeColumns,
};

export const PROCESS_ROUTE_PINNED_ACTIVE_FIELD = 'is_active';

const PROCESS_LIST_SORT_MAP: Record<string, string> = {
  code: 'code',
  name: 'name',
  category: 'category',
  createdAt: 'created_at',
  updatedAt: 'updated_at',
  isActive: 'is_active',
  is_active: 'is_active',
  reportingType: 'reporting_type',
  operationId: 'operation_id',
  version: 'version',
};

export function resolveProcessListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
  options?: {
    activeField?: string;
    extra?: (search: Record<string, unknown>) => Record<string, string | number | boolean | undefined>;
  },
): Record<string, string | number | boolean | undefined> {
  const search = searchFormValues ?? {};
  const activeField = options?.activeField ?? MASTER_CRUD_PINNED_ACTIVE_FIELD;
  const fuzzyKeyword = pickListSearchKeyword(searchFormValues);
  const { sortBy, sortOrder } = extractProTableSort(sort ?? {});
  const sortKey = sortBy ? PROCESS_LIST_SORT_MAP[sortBy] ?? sortBy : undefined;
  const { date_start: created_start_date, date_end: created_end_date } = parseSalesReportDateRange(search, [
    'created_at_range',
    'createdAtRange',
  ]);
  const { date_start: updated_start_date, date_end: updated_end_date } = parseSalesReportDateRange(search, [
    'updated_at_range',
    'updatedAtRange',
  ]);

  const params: Record<string, string | number | boolean | undefined> = {
    isActive: pickSearchTriStateBoolean(searchFormValues, activeField),
    sortBy: sortKey,
    sortOrder,
    created_start_date,
    created_end_date,
    updated_start_date,
    updated_end_date,
    ...(options?.extra?.(search) ?? {}),
  };

  if (fuzzyKeyword) {
    params.keyword = fuzzyKeyword;
  } else {
    const code = pickSearchString(searchFormValues, 'code');
    const name = pickSearchString(searchFormValues, 'name');
    if (code) params.code = code;
    if (name) params.name = name;
  }

  return params;
}

export function resolveSopListParams(
  searchFormValues?: Record<string, unknown> | null,
  sort?: Record<string, unknown>,
): Record<string, string | number | boolean | undefined> {
  return resolveProcessListParams(searchFormValues, sort, {
    extra: (search) => {
      const extra: Record<string, string | number | boolean | undefined> = {};
      const operationIdRaw = pickSearchString(search, 'operationId');
      if (operationIdRaw != null && Number.isFinite(Number(operationIdRaw))) {
        extra.operationId = Number(operationIdRaw);
      }
      const materialUuid = pickOptionalString(search, 'material_uuid');
      if (materialUuid) extra.material_uuid = materialUuid;
      const materialGroupUuid = pickOptionalString(search, 'material_group_uuid');
      if (materialGroupUuid) extra.material_group_uuid = materialGroupUuid;
      const routeUuid = pickOptionalString(search, 'route_uuid');
      if (routeUuid) extra.route_uuid = routeUuid;
      const carrier = pickOptionalString(search, 'carrier');
      if (carrier) extra.carrier = carrier;
      const controlStatus = pickOptionalString(search, 'controlStatus');
      if (controlStatus) extra.controlStatus = controlStatus;
      const sopDomain = pickOptionalString(search, 'sopDomain');
      if (sopDomain) extra.sop_domain = sopDomain;
      return extra;
    },
  });
}

export function processRouteActiveSearchColumn(
  title: string,
  valueEnum: Record<string, { text: string }>,
): ProColumns {
  return {
    title,
    dataIndex: 'is_active',
    hideInTable: true,
    order: 20,
    valueType: 'select',
    valueEnum,
    fieldProps: { allowClear: true },
  };
}
