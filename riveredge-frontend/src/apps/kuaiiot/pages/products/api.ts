/**
 * 产品模型页封装。列表为数组响应，搜索/筛选/分页在前端完成；
 * 写入沿用与 services/kuaiiot 相同的 URL、method 与响应外层。
 */

import { apiRequest } from '../../../../services/api';
import {
  deleteProduct,
  getProduct,
  listProducts,
  updateProduct,
  type ProductEvent,
  type ProductFunction,
  type ProductOut,
  type ProductTag,
} from '../../services/kuaiiot';
import {
  filterRowsByListKeyword,
  pickListSearchKeyword,
  pickSearchString,
} from '../../../../utils/tableQueryKey';

/** 后端 ProductOut 还带 remark；列表行保留该字段。 */
export type ProductRow = ProductOut & { remark?: string | null };

/** POST /products 请求体（后端 ProductCreate 支持 events/functions/remark）。 */
export type ProductWritePayload = {
  code: string;
  name: string;
  description?: string;
  tags: ProductTag[];
  events?: ProductEvent[];
  functions?: ProductFunction[];
  remark?: string;
};

export type ProductUpdatePayload = {
  name?: string;
  description?: string;
  tags?: ProductTag[];
  events?: ProductEvent[];
  functions?: ProductFunction[];
  remark?: string;
};

export async function listProductRows(): Promise<ProductRow[]> {
  return (await listProducts()) as ProductRow[];
}

export async function getProductRow(productId: number): Promise<ProductRow> {
  return (await getProduct(productId)) as ProductRow;
}

export function createProductFull(payload: ProductWritePayload): Promise<ProductRow> {
  return apiRequest<ProductRow>('/apps/kuaiiot/products', { method: 'POST', data: payload });
}

export async function updateProductRow(
  productId: number,
  payload: ProductUpdatePayload,
): Promise<ProductRow> {
  return (await updateProduct(productId, payload)) as ProductRow;
}

export async function deleteProductRow(productId: number): Promise<void> {
  return deleteProduct(productId);
}

/**
 * 客户端筛选：模糊词覆盖编码/名称/描述/点位键；高级搜索按列字段精确收敛。
 */
export function filterProductRows(
  rows: ProductRow[],
  searchFormValues?: Record<string, unknown>,
): ProductRow[] {
  let out = filterRowsByListKeyword(rows, pickListSearchKeyword(searchFormValues), (row) => [
    row.code,
    row.name,
    row.description,
    row.remark,
    ...(row.tags || []).flatMap((tag) => [tag.tag_key, tag.name]),
  ]);
  const code = pickSearchString(searchFormValues, 'code');
  if (code) {
    const q = code.toLowerCase();
    out = out.filter((row) => (row.code || '').toLowerCase().includes(q));
  }
  const name = pickSearchString(searchFormValues, 'name');
  if (name) {
    const q = name.toLowerCase();
    out = out.filter((row) => (row.name || '').toLowerCase().includes(q));
  }
  return out;
}

/** 客户端排序：仅在用户点击列头排序时生效，未点保持接口顺序。 */
export function sortLocalRows<T extends Record<string, unknown>>(
  rows: T[],
  sort: Record<string, 'ascend' | 'descend' | null | undefined>,
): T[] {
  const entry = Object.entries(sort || {}).find(([, v]) => v === 'ascend' || v === 'descend');
  if (!entry) return rows;
  const [key, dir] = entry as [string, 'ascend' | 'descend'];
  const factor = dir === 'ascend' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = a[key];
    const bv = b[key];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * factor;
    return String(av).localeCompare(String(bv)) * factor;
  });
}
