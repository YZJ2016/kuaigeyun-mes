import type { DataNode } from 'antd/es/tree';
import { apiRequest } from '../../services/api';
import { formatMaterialGroupLabel } from '../../apps/master-data/types/material';
import {
  parseMaterialTotalsPrimary,
  type MaterialTotalBucket,
} from '../../utils/inventoryLedgerApi';

/** 批量获取物料可用库存汇总 */
export async function fetchBatchMaterialInventory(
  materialIds: number[],
  warehouseId?: number,
): Promise<Record<number, number>> {
  if (materialIds.length === 0) return {};
  try {
    const res = await apiRequest<{ material_totals?: Record<string, number | MaterialTotalBucket> }>(
      '/apps/kuaizhizao/reports/inventory/batch-query',
      {
        method: 'GET',
        params: {
          material_ids: materialIds,
          summary_only: true,
          include_expired: false,
          ...(warehouseId != null && warehouseId > 0 ? { warehouse_id: warehouseId } : {}),
        },
      },
    );
    const result = parseMaterialTotalsPrimary(res?.material_totals);
    for (const id of materialIds) {
      if (!(id in result)) result[id] = 0;
    }
    return result;
  } catch {
    return {};
  }
}

/** 批量检查物料是否有 BOM */
export async function fetchBatchMaterialHasBom(
  materialIds: number[],
): Promise<Record<number, boolean>> {
  if (materialIds.length === 0) return {};
  try {
    const res = await apiRequest<Record<string, boolean>>(
      '/apps/master-data/materials/bom/batch-check',
      {
        method: 'GET',
        params: { material_ids: materialIds, only_active: true },
      },
    );
    const result: Record<number, boolean> = {};
    for (const [k, v] of Object.entries(res ?? {})) {
      const id = parseInt(k, 10);
      if (!Number.isNaN(id)) result[id] = !!v;
    }
    for (const id of materialIds) {
      if (!(id in result)) result[id] = false;
    }
    return result;
  } catch {
    return {};
  }
}

export function getMaterialField(m: Record<string, unknown>, field: string): unknown {
  let v = m[field];
  if (v !== undefined && v !== null) return v;
  const snake = field.replace(/([A-Z])/g, '_$1').toLowerCase();
  return m[snake];
}

export type MaterialGroupTreeNode = { title: string; value: number; key: string; children?: MaterialGroupTreeNode[] };

export function mapMaterialGroupTree(nodes: unknown[]): MaterialGroupTreeNode[] {
  if (!Array.isArray(nodes)) return [];
  return nodes.map((raw) => {
    const n = raw as Record<string, unknown>;
    const id = (n.id as number) ?? 0;
    const code = String(n.code ?? '');
    const name = String(n.name ?? '');
    const childrenRaw = n.children as unknown[] | undefined;
    const node: MaterialGroupTreeNode = {
      value: id,
      key: String(id),
      title: [code, name].filter(Boolean).join(' ') || String(id),
      children: childrenRaw?.length ? mapMaterialGroupTree(childrenRaw) : undefined,
    };
    return node;
  });
}

export function buildMaterialBatchPickerGroupTree(
  treeItems: unknown[],
  t: (key: string, options?: Record<string, unknown>) => string,
  summary?: { ungroupedMaterialCount?: number; totalMaterialCount?: number },
): DataNode[] {
  const withCount = (label: string, count: number | undefined) =>
    typeof count === 'number' && Number.isFinite(count) ? `${label} (${count})` : label;

  const convertNode = (node: Record<string, unknown>): DataNode & { searchLabel?: string } => {
    const count = Number(node.materialCount ?? node.material_count);
    const pick = formatMaterialGroupLabel({
      code: String(node.code ?? ''),
      name: String(node.name ?? ''),
      alias: typeof node.alias === 'string' ? node.alias : undefined,
    });
    const label = withCount(pick, Number.isFinite(count) ? count : undefined);
    const childrenRaw = node.children as unknown[] | undefined;
    return {
      title: label,
      searchLabel: label,
      key: String(node.id),
      isLeaf: !childrenRaw?.length,
      children: childrenRaw?.length
        ? childrenRaw.map((child) => convertNode(child as Record<string, unknown>))
        : undefined,
    };
  };

  const allLabel = withCount(
    t('app.master-data.materials.allMaterials'),
    summary?.totalMaterialCount,
  );
  const children: DataNode[] = (Array.isArray(treeItems) ? treeItems : []).map((item) =>
    convertNode(item as Record<string, unknown>),
  );

  return [
    {
      title: allLabel,
      searchLabel: allLabel,
      key: 'all',
      isLeaf: children.length === 0,
      children: children.length ? children : undefined,
    },
  ];
}

/** 按分组树展示标题过滤（保留匹配分支祖先） */
export function filterMaterialGroupTreeData(nodes: DataNode[], keyword: string): DataNode[] {
  const kw = keyword.trim().toLowerCase();
  if (!kw) return nodes;
  const walk = (list: DataNode[]): DataNode[] => {
    const out: DataNode[] = [];
    for (const node of list) {
      const searchLabel = (node as DataNode & { searchLabel?: string }).searchLabel;
      const titleText =
        searchLabel ??
        (typeof node.title === 'string' ? node.title : String(node.title ?? ''));
      const childFiltered = node.children?.length ? walk(node.children) : [];
      const selfMatch = titleText.toLowerCase().includes(kw);
      if (selfMatch || childFiltered.length > 0) {
        out.push({
          ...node,
          children: childFiltered.length ? childFiltered : node.children,
        });
      }
    }
    return out;
  };
  return walk(nodes);
}
