/**
 * 兼容垫片（OUTSIDE 契约 C / PARTIAL）：`POST /apps/kuaiai/actions/execute` 不在
 * spec 138 契约 C 产品 REST 表内。本导出仅满足存量
 * `components/ai-assistant/index.tsx`（及 ai-draft）的既有 import，恢复编译；
 * 不是产品 API，UI/文档不得宣传为正式端点。
 *
 * 确认闸本期不做（KR-D15）：后端不会下发 confirm_token，抽屉「确认操作」死路径
 * 不触发。勿把本模块当作确认闸落地实现。
 */

import { apiRequest } from '../../../services/api';

export type ExecuteAiActionResult = {
  message?: string;
};

/** 兼容垫片：契约 C 外端点；仅供存量 import，勿新增调用方。 */
export async function executeAiAction(confirmToken: string): Promise<ExecuteAiActionResult> {
  return apiRequest<ExecuteAiActionResult>('/apps/kuaiai/actions/execute', {
    method: 'POST',
    data: { confirm_token: confirmToken },
  });
}
