/** 生产执行报表 → 后端 /reports/production 表单字段（排序走 extractReportProTableSort 统一路径） */
import { pickListSearchKeyword, pickSearchString } from '../../../utils/tableQueryKey';

export function resolveProductionReportFormParams(
  searchFormValues?: Record<string, unknown> | null,
): Record<string, string | undefined> {
  const keyword = pickListSearchKeyword(searchFormValues);
  const status = pickSearchString(searchFormValues, 'status');
  return {
    keyword,
    status,
    order_code:
      pickSearchString(searchFormValues, 'order_code') ?? pickSearchString(searchFormValues, 'code'),
    product_name:
      pickSearchString(searchFormValues, 'product_name') ??
      pickSearchString(searchFormValues, 'material_name'),
    supplier_name: pickSearchString(searchFormValues, 'supplier_name'),
    work_order_code:
      pickSearchString(searchFormValues, 'work_order_code') ??
      pickSearchString(searchFormValues, 'order_code') ??
      pickSearchString(searchFormValues, 'code') ??
      pickSearchString(searchFormValues, 'outsource_work_order_code'),
    template_code: pickSearchString(searchFormValues, 'template_code'),
    team_name: pickSearchString(searchFormValues, 'team_name'),
  };
}

/** @deprecated 使用 resolveProductionReportFormParams + extractReportProTableSort */
export function resolveProductionReportApiParams(
  searchFormValues?: Record<string, unknown> | null,
  _sort?: Record<string, unknown>,
): Record<string, string | undefined> {
  return resolveProductionReportFormParams(searchFormValues);
}
