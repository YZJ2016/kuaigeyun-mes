import {
  RESOURCE_CATEGORY_ALL_KEY,
  RESOURCE_CATEGORY_UNCATEGORIZED_KEY,
  resolveResourceCategoryListFilter,
  type ResourceCategoryListFilter,
} from '../../../services/resourceCategory';

/** 分类节点与关联单据二级 key 分隔符 */
export const API_TREE_DOC_SEP = '::doc::';

export const API_TREE_DOC_ALL = '__all__';
export const API_TREE_DOC_NONE = '__none__';

export interface ApiCategoryListFilter extends ResourceCategoryListFilter {
  related_document_code?: string;
  no_related_document?: boolean;
}

export interface ApiRelatedDocumentGroupCount {
  category_uuid?: string | null;
  related_document_code?: string | null;
  count: number;
}

export function buildApiCategoryTreeDocKey(categoryKey: string, docKey: string): string {
  return `${categoryKey}${API_TREE_DOC_SEP}${docKey}`;
}

export function resolveApiCategoryTreeKey(selectedKey: string): ApiCategoryListFilter {
  const key = String(selectedKey || '').trim();
  if (!key || key === RESOURCE_CATEGORY_ALL_KEY) {
    return {};
  }
  if (!key.includes(API_TREE_DOC_SEP)) {
    return resolveResourceCategoryListFilter(key);
  }
  const [categoryKey, docKey] = key.split(API_TREE_DOC_SEP, 2);
  const base = resolveResourceCategoryListFilter(categoryKey);
  if (!docKey || docKey === API_TREE_DOC_ALL) {
    return base;
  }
  if (docKey === API_TREE_DOC_NONE) {
    return { ...base, no_related_document: true };
  }
  return { ...base, related_document_code: docKey };
}

/** 新建表单预填分类：从左栏选中 key（含接口库 uuid::doc:: 复合键）取出纯 UUID */
export function categoryUuidFromTreeSelectKey(selectedKey: string): string | undefined {
  return resolveApiCategoryTreeKey(selectedKey).category_uuid;
}

export function normalizeApiCategoryTreeSelectKey(rawKey: string): string {
  const key = String(rawKey || '').trim();
  if (!key || key === RESOURCE_CATEGORY_ALL_KEY) {
    return RESOURCE_CATEGORY_ALL_KEY;
  }
  if (key.includes(API_TREE_DOC_SEP)) {
    return key;
  }
  if (key === RESOURCE_CATEGORY_UNCATEGORIZED_KEY) {
    return buildApiCategoryTreeDocKey(key, API_TREE_DOC_ALL);
  }
  return buildApiCategoryTreeDocKey(key, API_TREE_DOC_ALL);
}

export function groupCountsForCategory(
  counts: ApiRelatedDocumentGroupCount[],
  categoryUuid: string | null,
): ApiRelatedDocumentGroupCount[] {
  return counts.filter((row) => {
    const rowCat = row.category_uuid ?? null;
    if (categoryUuid === null) {
      return rowCat === null || rowCat === undefined;
    }
    return rowCat === categoryUuid;
  });
}
