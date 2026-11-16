/**
 * 物料导入：按主编码解析主物料（列表级拆分导入共用）
 */

import type { Material } from '../types/material';
import { materialApi } from '../services/material';
import { isVariantSkuMaterial } from '../components/MaterialVariantCombinationsTable';

type MaterialWithImportAliases = Material & { __importAliasCodes?: string[] };

export function pickMaterialMainCode(material: Material): string {
  return String(
    material.mainCode ?? (material as { main_code?: string }).main_code ?? material.code ?? '',
  ).trim();
}

function materialCodeKeys(material: Material): string[] {
  const aliases = (material as MaterialWithImportAliases).__importAliasCodes ?? [];
  const keys = [
    pickMaterialMainCode(material),
    String(material.code ?? '').trim(),
    String((material as { main_code?: string }).main_code ?? '').trim(),
    ...aliases,
  ];
  return [...new Set(keys.map((k) => k.toUpperCase()).filter(Boolean))];
}

/** 清洗导入表编码：去 BOM/不间断空格，避免 Excel 粘贴导致假未命中 */
export function normalizeImportMaterialCode(raw: unknown): string {
  return String(raw ?? '')
    .replace(/^\uFEFF/, '')
    .replace(/\u00A0/g, ' ')
    .trim();
}

function attachImportAlias(material: Material, alias: string): MaterialWithImportAliases {
  const key = normalizeImportMaterialCode(alias).toUpperCase();
  if (!key) return material;
  const prev = material as MaterialWithImportAliases;
  const nextAliases = [...new Set([...(prev.__importAliasCodes ?? []), key])];
  return { ...prev, __importAliasCodes: nextAliases };
}

/** 导入行按编码匹配：主编码 / code / 导入别名 任一命中即可（大小写不敏感） */
export function findMaterialByImportCode(
  materials: Material[],
  rawCode: string,
): Material | undefined {
  const key = normalizeImportMaterialCode(rawCode).toUpperCase();
  if (!key) return undefined;
  return materials.find((m) => materialCodeKeys(m).includes(key));
}

/** 从导入矩阵指定列收集物料编码（去重、已清洗） */
export function collectImportMaterialCodes(
  rows: unknown[][],
  materialColIndex: number,
): string[] {
  if (materialColIndex < 0) return [];
  return [
    ...new Set(
      rows
        .map((row) =>
          normalizeImportMaterialCode(Array.isArray(row) ? row[materialColIndex] : ''),
        )
        .filter(Boolean),
    ),
  ];
}

/**
 * 销售/采购等单据导入：先用已有清单匹配，缺码再按 code 精确查 API 补齐。
 * 禁止仅依赖页面内存缓存（常只有几十条），否则会误报「未找到产品」。
 *
 * API 可能按部门别名命中物料，返回行的 mainCode/code 与导入编码不同，
 * 必须把「查询用的导入编码」挂到物料上，findMaterialByImportCode 才能命中。
 */
export async function resolveMaterialsByCodesForImport(
  codes: string[],
  seed: Material[] = [],
): Promise<Material[]> {
  const byId = new Map<number, Material>();
  const byKey = new Map<string, Material>();

  const remember = (m: Material, extraKeys: string[] = []) => {
    let row = byId.get(m.id) ?? m;
    for (const raw of extraKeys) {
      row = attachImportAlias(row, raw);
    }
    byId.set(row.id, row);
    for (const k of materialCodeKeys(row)) {
      byKey.set(k, row);
    }
  };

  for (const m of seed) remember(m);

  const missing = [
    ...new Set(
      codes
        .map((c) => normalizeImportMaterialCode(c))
        .filter((c) => c && !byKey.has(c.toUpperCase())),
    ),
  ];

  const concurrency = 6;
  for (let i = 0; i < missing.length; i += concurrency) {
    const chunk = missing.slice(i, i + concurrency);
    await Promise.all(
      chunk.map(async (code) => {
        try {
          // 不限 isActive：系统内已存在的编码（含停用）导入应能命中
          const { items } = await materialApi.list({
            code,
            limit: 50,
          });
          const upper = code.toUpperCase();
          const hit =
            (items ?? []).find((m) => materialCodeKeys(m).includes(upper)) ??
            // 别名精确命中时返回行编码可能与导入码不同；list?code= 精确路径通常只一条
            ((items ?? []).length === 1 ? items![0] : undefined);
          if (hit) remember(hit, [code]);
        } catch (error) {
          // 单码失败不阻断整批，但必须可观测，避免静默成「未找到产品」
          console.warn('[materialImportResolve] list by code failed', code, error);
        }
      }),
    );
  }

  return [...byId.values()];
}

export async function resolveMasterByMainCode(
  mainCode: string,
  cache: Map<string, Material>,
): Promise<Material | null> {
  const key = mainCode.trim();
  if (!key) return null;

  const cacheKey = key.toUpperCase();
  const cached = cache.get(cacheKey);
  if (cached) return cached;

  const { items } = await materialApi.list({ code: key, mastersOnly: true, limit: 50 });
  const master = (items ?? []).find(
    (m) => !isVariantSkuMaterial(m) && pickMaterialMainCode(m).toUpperCase() === cacheKey,
  );
  if (master) {
    cache.set(cacheKey, master);
  }
  return master ?? null;
}
