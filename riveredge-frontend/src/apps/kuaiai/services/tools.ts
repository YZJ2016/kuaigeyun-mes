/**
 * KU-AI Tool 目录 API（spec 189）。
 *
 * Tool 名称/中文 label/kind/权限码一律由后端 `GET /apps/kuaiai/tools`
 * 下发（manifest ai_tools 唯一真源），前端不再维护本地 Tool 名闭集。
 */

import { apiRequest } from '../../../services/api';

export interface KuaiAiToolCatalogItem {
  name: string;
  /** 中文显示名（后端 manifest label） */
  label: string;
  description?: string | null;
  /** read|write；write 确认闸语义由后续 spec 消费 */
  kind: 'read' | 'write';
  permission?: string | null;
}

/** GET /apps/kuaiai/tools（kuaiai:agent:read） */
export function listToolCatalog(): Promise<KuaiAiToolCatalogItem[]> {
  return apiRequest<KuaiAiToolCatalogItem[]>('/apps/kuaiai/tools');
}
