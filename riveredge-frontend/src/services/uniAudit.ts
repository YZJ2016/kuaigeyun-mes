import { apiRequest } from './api';

export interface SubmitInitiatorNodeHint {
  node_id: string;
  label: string;
  required: boolean;
  empty_approver_policy: string;
}

export interface SubmitInitiatorBranchHint {
  condition_node_id: string;
  label: string;
  required: boolean;
  /** 设计器勾选的默认分支下标；未设置时不预选 */
  default_index?: number | null;
  branches: Array<{ index: number; label: string; is_default?: boolean; target_label?: string }>;
}

export interface HierarchyDepartmentOption {
  uuid: string;
  name: string;
  code?: string | null;
  is_primary?: boolean;
}

export interface SubmitInitiatorRequirements {
  nodes: SubmitInitiatorNodeHint[];
  branch_conditions: SubmitInitiatorBranchHint[];
  hierarchy_department_required?: boolean;
  hierarchy_department_options?: HierarchyDepartmentOption[];
  default_hierarchy_department_uuid?: string | null;
}

export async function fetchSubmitInitiatorRequirements(
  entityType: string,
  entityId?: number,
): Promise<SubmitInitiatorRequirements> {
  const qs =
    typeof entityId === 'number' && entityId > 0
      ? `?entity_id=${encodeURIComponent(String(entityId))}`
      : '';
  const res = await apiRequest<{
    nodes?: SubmitInitiatorNodeHint[];
    branch_conditions?: SubmitInitiatorBranchHint[];
    hierarchy_department_required?: boolean;
    hierarchy_department_options?: HierarchyDepartmentOption[];
    default_hierarchy_department_uuid?: string | null;
  }>(`/core/uni-audit/${encodeURIComponent(entityType)}/submit-initiator-nodes${qs}`, {
    method: 'GET',
  });
  return {
    nodes: Array.isArray(res?.nodes) ? res.nodes : [],
    branch_conditions: Array.isArray(res?.branch_conditions) ? res.branch_conditions : [],
    hierarchy_department_required: Boolean(res?.hierarchy_department_required),
    hierarchy_department_options: Array.isArray(res?.hierarchy_department_options)
      ? res.hierarchy_department_options
      : [],
    default_hierarchy_department_uuid: res?.default_hierarchy_department_uuid ?? null,
  };
}

/** 表单/列表送审；initiator 选人时传 payload */
export async function postSubmitReview(
  entityType: string,
  entityId: number,
  payload?: Record<string, unknown>,
): Promise<unknown> {
  return apiRequest(`/core/uni-audit/${encodeURIComponent(entityType)}/${entityId}/submit_review`, {
    method: 'POST',
    data: payload ?? {},
  });
}

export async function fetchSubmitInitiatorNodes(
  entityType: string,
): Promise<SubmitInitiatorNodeHint[]> {
  const res = await fetchSubmitInitiatorRequirements(entityType);
  return res.nodes;
}
