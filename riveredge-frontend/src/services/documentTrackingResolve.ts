/**
 * 单据跟踪 / 按编号解析（供 IM 等场景打开关联详情）
 */

import { apiRequest } from './api';

export type DocumentCodeResolveItem = {
  document_type: string;
  document_id: number;
  document_code: string;
};

export async function resolveDocumentByCode(
  code: string,
): Promise<{ items: DocumentCodeResolveItem[]; total: number }> {
  return apiRequest('/core/document-tracking/resolve-by-code', {
    method: 'GET',
    params: { code: code.trim() },
  });
}
