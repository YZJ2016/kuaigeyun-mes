import React, { useState, useEffect, useMemo } from 'react';
import { Select, Spin } from 'antd';
import { materialApi } from '../../apps/master-data/services/material';
import type { Material } from '../../apps/master-data/types/material';
import {
  formatMaterialUnitOptionLabel,
  useMaterialUnitOptions,
} from '../../apps/master-data/hooks/useMaterialUnitOptions';
import { EMPTY_VALUE_PLACEHOLDER } from '../../utils/format';

export interface MaterialUnitSelectProps {
  /** 物料 ID (支持数字 ID 或字符串 UUID) */
  materialId?: number | string;
  /** 当前选中的单位值（单位名称；兼容历史存编码） */
  value?: string;
  /** 变更回调（回写单位名称） */
  onChange?: (value: string) => void;
  /** 尺寸 */
  size?: 'large' | 'medium' | 'small';
  /** 是否禁用 */
  disabled?: boolean;
  /** 占位符 */
  placeholder?: string;
  /** 是否带样式（用于 Form.Item noStyle 模式，去边框等） */
  noStyle?: boolean;
  /**
   * true：选项来自单位管理（可改任意启用单位）；
   * false：仅物料基础单位 + 辅助单位（旧行为）。
   * 默认 true。
   */
  allowCatalogUnits?: boolean;
}

// 同一瞬间并发去重，不跨渲染/操作复用物料档案。
const materialInflight = new Map<string, Promise<Material | null>>();
const materialByKeyCache = new Map<string, Material>();

/** @deprecated 不再提供 code→name 映射；保留空实现避免旧 import 断裂 */
export async function getMaterialUnitDisplayMapShared(): Promise<Record<string, string>> {
  return {};
}

/** 页面已加载物料列表时写入，避免 numeric id 误调 GET /materials/{id}（仅 UUID 合法） */
export function registerMaterialsForUnitSelect(materials: Array<Material | Record<string, unknown>>): void {
  for (const raw of materials) {
    const m = raw as Material;
    if (m.id != null) materialByKeyCache.set(String(m.id), m);
    if (m.uuid) materialByKeyCache.set(String(m.uuid), m);
  }
}

function rememberMaterialForUnitSelect(material: Material): void {
  if (material.id != null) materialByKeyCache.set(String(material.id), material);
  if (material.uuid) materialByKeyCache.set(String(material.uuid), material);
}

function looksLikeMaterialUuid(idStr: string): boolean {
  return idStr.includes('-') && idStr.length > 20;
}

/**
 * 拉取单条物料（同 id 并发去重）。数字 id 用 ids 精确查，禁止 limit=2000 全表扫。
 */
export async function fetchMaterialForUnitSelectCache(materialId: number | string): Promise<Material | null> {
  const cacheKey = String(materialId);
  const cached = materialByKeyCache.get(cacheKey);
  if (cached) return cached;

  const inflight = materialInflight.get(cacheKey);
  if (inflight) return inflight;

  const promise = (async () => {
    const idStr = String(materialId);
    let resp: Material | null = null;

    if (looksLikeMaterialUuid(idStr)) {
      resp = await materialApi.get(idStr);
    } else {
      const numericId = Number(idStr);
      if (Number.isFinite(numericId) && numericId > 0) {
        const listRes = await materialApi.list({ ids: [numericId], limit: 1 });
        const items = Array.isArray(listRes?.items) ? listRes.items : [];
        resp = items.find((m) => Number(m.id) === numericId) ?? null;
      }
    }
    if (resp) rememberMaterialForUnitSelect(resp);
    return resp;
  })().finally(() => {
    materialInflight.delete(cacheKey);
  });

  materialInflight.set(cacheKey, promise);
  return promise;
}

/**
 * 批量预取物料档案（写入组件内部缓存）。数字 id 一次 ids 查询，避免 N 次或全表扫。
 */
export async function prefetchMaterialsForUnitSelect(
  materialIds: Array<number | string | null | undefined>
): Promise<Map<string, Material>> {
  const unique = [
    ...new Set(
      materialIds
        .filter((x): x is number | string => x != null && x !== '')
        .map((x) => String(x))
    ),
  ];
  const out = new Map<string, Material>();
  if (unique.length === 0) return out;

  const missingNumeric: number[] = [];
  const missingUuid: string[] = [];
  for (const key of unique) {
    const cached = materialByKeyCache.get(key);
    if (cached) {
      out.set(key, cached);
      continue;
    }
    if (looksLikeMaterialUuid(key)) {
      missingUuid.push(key);
      continue;
    }
    const numericId = Number(key);
    if (Number.isFinite(numericId) && numericId > 0) {
      missingNumeric.push(numericId);
    }
  }

  if (missingNumeric.length > 0) {
    try {
      const listRes = await materialApi.list({
        ids: missingNumeric,
        limit: missingNumeric.length,
      });
      for (const m of listRes.items || []) {
        rememberMaterialForUnitSelect(m);
        out.set(String(m.id), m);
        if (m.uuid) out.set(String(m.uuid), m);
      }
    } catch (error) {
      console.error('Failed to load material units:', error);
    }
  }

  await Promise.all(
    missingUuid.map(async (key) => {
      try {
        const m = await fetchMaterialForUnitSelectCache(key);
        if (m) out.set(key, m);
      } catch {
        /* ignore single miss */
      }
    }),
  );
  return out;
}

function collectMaterialUnitNames(material: Material | null | undefined): string[] {
  if (!material) return [];
  const unitSet = new Set<string>();
  if (material.baseUnit) unitSet.add(String(material.baseUnit).trim());
  material.units?.units?.forEach((u) => {
    if (u.unit) unitSet.add(String(u.unit).trim());
  });
  return Array.from(unitSet).filter(Boolean);
}

/**
 * 单据明细单位：默认带出物料基础单位；更改时从单位管理取选项（名称 + 编码）。
 */
export const MaterialUnitSelect: React.FC<MaterialUnitSelectProps> = ({
  materialId,
  value,
  onChange,
  size,
  disabled,
  placeholder,
  noStyle,
  allowCatalogUnits = true,
}) => {
  const [material, setMaterial] = useState<Material | null>(() =>
    materialId != null && materialId !== ''
      ? materialByKeyCache.get(String(materialId)) ?? null
      : null,
  );
  const [loadingMaterial, setLoadingMaterial] = useState(false);
  const { units: catalogUnits, options: catalogOptions, isLoading: loadingCatalog } =
    useMaterialUnitOptions(allowCatalogUnits);

  useEffect(() => {
    if (materialId == null || materialId === '') {
      setMaterial(null);
      return;
    }
    const cached = materialByKeyCache.get(String(materialId));
    if (cached) {
      setMaterial(cached);
      return;
    }
    let cancelled = false;
    setLoadingMaterial(true);
    fetchMaterialForUnitSelectCache(materialId)
      .then((resp) => {
        if (!cancelled && resp) setMaterial(resp);
      })
      .catch((error) => {
        console.error('Failed to load material units:', error);
      })
      .finally(() => {
        if (!cancelled) setLoadingMaterial(false);
      });
    return () => {
      cancelled = true;
    };
  }, [materialId]);

  const materialUnitNames = useMemo(() => collectMaterialUnitNames(material), [material]);

  const selectOptions = useMemo(() => {
    if (allowCatalogUnits) {
      // 单位管理全量；物料已有单位排前面
      const preferred = new Set(
        materialUnitNames.map((n) => n.toLowerCase()),
      );
      const sorted = [...catalogOptions].sort((a, b) => {
        const ap = preferred.has(String(a.value).toLowerCase()) || preferred.has(String(a.code).toLowerCase()) ? 0 : 1;
        const bp = preferred.has(String(b.value).toLowerCase()) || preferred.has(String(b.code).toLowerCase()) ? 0 : 1;
        return ap - bp;
      });
      // 当前值若不在目录（历史脏数据），补一条以免空白
      const raw = String(value || '').trim();
      if (raw && !sorted.some((o) => o.value === raw || o.code === raw)) {
        return [{ label: raw, value: raw, code: raw, name: raw }, ...sorted];
      }
      return sorted;
    }
    return materialUnitNames.map((u) => {
      const hit = catalogUnits.find(
        (c) => c.name === u || c.code === u || c.name?.toLowerCase() === u.toLowerCase(),
      );
      return {
        label: hit ? formatMaterialUnitOptionLabel(hit) : u,
        value: hit ? String(hit.name || hit.code || u).trim() : u,
        code: hit ? String(hit.code || '').trim() : u,
        name: hit ? String(hit.name || hit.code || u).trim() : u,
      };
    });
  }, [allowCatalogUnits, catalogOptions, catalogUnits, materialUnitNames, value]);

  /** 名称或编码都能选中对应项；回写统一用名称 */
  const selectValue = useMemo(() => {
    const raw = String(value || '').trim();
    if (!raw) return undefined;
    const hit = selectOptions.find(
      (o) => o.value === raw || o.code === raw || o.name === raw,
    );
    return hit?.value ?? raw;
  }, [selectOptions, value]);

  const cellTextStyle: React.CSSProperties = {
    fontSize: 'inherit',
    lineHeight: 'inherit',
    color: 'inherit',
  };

  if (materialId == null || materialId === '') {
    return <span style={cellTextStyle}>{EMPTY_VALUE_PLACEHOLDER}</span>;
  }

  const loading = loadingMaterial || (allowCatalogUnits && loadingCatalog);
  if (loading && (value == null || value === '')) {
    return <Spin size="small" />;
  }

  if (!material && !allowCatalogUnits) {
    if (value != null && value !== '') {
      return <span style={cellTextStyle}>{String(value)}</span>;
    }
    return <span style={cellTextStyle}>{EMPTY_VALUE_PLACEHOLDER}</span>;
  }

  // 仅物料单位且只有一个、且不允许目录：只读展示
  if (!allowCatalogUnits && selectOptions.length <= 1) {
    const raw = selectValue || material?.baseUnit || '';
    return <span style={cellTextStyle}>{raw || EMPTY_VALUE_PLACEHOLDER}</span>;
  }

  return (
    <Select
      value={selectValue}
      onChange={(next) => onChange?.(String(next || '').trim())}
      size={size}
      disabled={disabled}
      placeholder={placeholder}
      showSearch
      optionFilterProp="label"
      style={{ width: '100%', minWidth: 72, fontSize: 'inherit' }}
      variant={noStyle ? 'borderless' : 'outlined'}
      popupMatchSelectWidth={false}
      options={selectOptions}
      loading={loading}
    />
  );
};

export default MaterialUnitSelect;
