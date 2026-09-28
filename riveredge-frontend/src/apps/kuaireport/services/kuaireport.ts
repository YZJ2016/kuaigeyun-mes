/**
 * UniReport config 模式的执行入口。
 * 分页键是 limit / offset，返回 data / total / summary。
 */

import { apiRequest } from '../../../services/api';

export type ExecuteReportResult = {
  data?: unknown[];
  total?: number;
  success?: boolean;
  summary?: Record<string, number>;
};

export async function executeReport(
  reportId: string | number,
  filters: Record<string, unknown>,
): Promise<ExecuteReportResult> {
  return apiRequest<ExecuteReportResult>(`/apps/kuaireport/reports/${reportId}/execute`, {
    method: 'POST',
    data: filters,
  });
}
