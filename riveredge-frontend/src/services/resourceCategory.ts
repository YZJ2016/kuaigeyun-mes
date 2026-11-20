/**
 * 资源分类（接口 / 数据集）管理服务
 */

import { apiRequest } from './api';

export type ResourceCategoryType =
  | 'api'
  | 'dataset'
  | 'approval_process'
  | 'message_template'
  | 'print_template';

export interface ResourceCategory {
  uuid: string;
  tenant_id: number;
  name: string;
  code: string;
  description?: string;
  resource_type: ResourceCategoryType;
  sort_order: number;
  is_active: boolean;
  item_count: number;
  created_at: string;
  updated_at: string;
}

export interface APIRelatedDocumentGroupCount {
  category_uuid?: string | null;
  related_document_code?: string | null;
  count: number;
}

export interface APIRelatedDocumentOption {
  code: string;
  label: string;
}

export interface ResourceCategoryListResponse {
  items: ResourceCategory[];
  total_count: number;
  uncategorized_count: number;
  /** 仅接口库：左栏二级「关联单据」分组统计 */
  related_document_group_counts?: APIRelatedDocumentGroupCount[];
  related_document_options?: APIRelatedDocumentOption[];
}

export interface CreateResourceCategoryData {
  name: string;
  code: string;
  description?: string;
  sort_order?: number;
  is_active?: boolean;
}

export interface UpdateResourceCategoryData {
  name?: string;
  code?: string;
  description?: string;
  sort_order?: number;
  is_active?: boolean;
}

export interface ResourceCategoryListFilter {
  category_uuid?: string;
  no_category?: boolean;
}

export const RESOURCE_CATEGORY_ALL_KEY = 'all';
export const RESOURCE_CATEGORY_UNCATEGORIZED_KEY = 'uncategorized';

function categoryBasePath(resourceType: ResourceCategoryType): string {
  switch (resourceType) {
    case 'api':
      return '/core/apis/categories';
    case 'dataset':
      return '/core/datasets/categories';
    case 'approval_process':
      return '/core/approval-processes/categories';
    case 'message_template':
      return '/core/message-templates/categories';
    case 'print_template':
      return '/core/print-templates/categories';
    default: {
      const _exhaustive: never = resourceType;
      return _exhaustive;
    }
  }
}

export async function listResourceCategories(
  resourceType: ResourceCategoryType,
): Promise<ResourceCategoryListResponse> {
  return apiRequest<ResourceCategoryListResponse>(categoryBasePath(resourceType));
}

export async function createResourceCategory(
  resourceType: ResourceCategoryType,
  data: CreateResourceCategoryData,
): Promise<ResourceCategory> {
  return apiRequest<ResourceCategory>(categoryBasePath(resourceType), {
    method: 'POST',
    data,
  });
}

export async function updateResourceCategory(
  resourceType: ResourceCategoryType,
  categoryUuid: string,
  data: UpdateResourceCategoryData,
): Promise<ResourceCategory> {
  return apiRequest<ResourceCategory>(`${categoryBasePath(resourceType)}/${categoryUuid}`, {
    method: 'PUT',
    data,
  });
}

export async function deleteResourceCategory(
  resourceType: ResourceCategoryType,
  categoryUuid: string,
): Promise<void> {
  return apiRequest<void>(`${categoryBasePath(resourceType)}/${categoryUuid}`, {
    method: 'DELETE',
  });
}

export interface LoadFunctionCategoryPresetsResponse {
  categories_created: number;
  items_categorized: number;
}

const COLLAB_FUNCTION_CATEGORY_TYPES: ResourceCategoryType[] = [
  'approval_process',
  'message_template',
  'print_template',
];

export function supportsFunctionCategoryPresets(resourceType: ResourceCategoryType): boolean {
  return COLLAB_FUNCTION_CATEGORY_TYPES.includes(resourceType);
}

export async function loadFunctionCategoryPresets(
  resourceType: ResourceCategoryType,
): Promise<LoadFunctionCategoryPresetsResponse> {
  return apiRequest<LoadFunctionCategoryPresetsResponse>(
    `${categoryBasePath(resourceType)}/load-function-presets`,
    { method: 'POST' },
  );
}

export function resolveResourceCategoryListFilter(
  selectedKey: string,
): ResourceCategoryListFilter {
  if (selectedKey === RESOURCE_CATEGORY_ALL_KEY) {
    return {};
  }
  if (selectedKey === RESOURCE_CATEGORY_UNCATEGORIZED_KEY) {
    return { no_category: true };
  }
  return { category_uuid: selectedKey };
}
