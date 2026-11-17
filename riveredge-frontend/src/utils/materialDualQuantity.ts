import type { Material, MaterialUnit } from '../apps/master-data/types/material';
import {
  getMaterialUnitConversionType,
  isFloatingMaterialUnit,
  CONVERSION_TYPE_FIXED,
} from '../apps/master-data/utils/materialConversionType';
import {
  parseMaterialUnitsConfig,
  resolveUnitToBaseFactor,
  type MaterialScenario,
} from './materialScenarioUnit';

type MaterialLike = Pick<Material, 'baseUnit' | 'units'> & { base_unit?: string };

function readBaseUnit(material?: MaterialLike | null): string {
  return String(material?.baseUnit ?? material?.base_unit ?? '').trim();
}

export function findMaterialAuxUnitRow(
  material: MaterialLike | null | undefined,
  unitName: string,
): MaterialUnit | undefined {
  const target = String(unitName ?? '').trim();
  if (!target) return undefined;
  const cfg = parseMaterialUnitsConfig(material?.units);
  return cfg?.units?.find((u) => String(u.unit ?? '').trim() === target);
}

export function isFloatingLineUnit(
  material: MaterialLike | null | undefined,
  unitName: string,
): boolean {
  const row = findMaterialAuxUnitRow(material, unitName);
  return isFloatingMaterialUnit(row);
}

/** 1 副单位 = rate 主单位 */
export function computeLineUnitConversionRate(
  primaryQuantity: number,
  auxQuantity: number,
): number | undefined {
  const primary = Number(primaryQuantity);
  const aux = Number(auxQuantity);
  if (!Number.isFinite(primary) || !Number.isFinite(aux) || primary <= 0 || aux <= 0) {
    return undefined;
  }
  return primary / aux;
}

export type DocumentDualQuantityValue = {
  /** 行数量（material_unit 对应单位） */
  quantity?: number | null;
  material_unit?: string;
  aux_quantity?: number | null;
  aux_unit?: string;
  unit_conversion_rate?: number | null;
};

/**
 * 单据行主数量只接受有限数字。
 * 选料回写若把 `{ quantity }` 整包写进行字段，输入框会显示 [object Object]。
 */
export function coerceDocumentLineQuantity(raw: unknown): number | undefined {
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : undefined;
  if (typeof raw === 'string') {
    const text = raw.trim();
    if (!text) return undefined;
    const n = Number(text);
    return Number.isFinite(n) ? n : undefined;
  }
  if (raw && typeof raw === 'object') {
    const stamp = (raw as { $d?: unknown }).$d;
    if (stamp instanceof Date && !Number.isNaN(stamp.getTime())) {
      return stamp.getTime();
    }
    const marker = (raw as { __draftDayjs?: unknown }).__draftDayjs;
    if (typeof marker === 'string') {
      const parsed = Date.parse(marker);
      return Number.isFinite(parsed) ? parsed : undefined;
    }
    const inner = (raw as { quantity?: unknown }).quantity;
    if (inner !== undefined && inner !== raw) return coerceDocumentLineQuantity(inner);
  }
  return undefined;
}

export function resolveAuxUnitForScenario(
  material: MaterialLike | null | undefined,
  scenario: MaterialScenario,
): string {
  const base = readBaseUnit(material);
  const cfg = parseMaterialUnitsConfig(material?.units);
  const mapped = cfg?.scenarios?.[scenario];
  const unit = String(mapped ?? '').trim();
  if (unit && unit !== base) return unit;
  const firstAux = cfg?.units?.[0]?.unit;
  return String(firstAux ?? '').trim();
}

export function shouldShowDualQuantityEntry(
  material: MaterialLike | null | undefined,
  scenario: MaterialScenario,
): boolean {
  const auxUnit = resolveAuxUnitForScenario(material, scenario);
  const base = readBaseUnit(material);
  if (!auxUnit || !base || auxUnit === base) return false;
  return Boolean(findMaterialAuxUnitRow(material, auxUnit));
}

/** 固定换算：改主数量推副数量（主单位数量 = quantity 当 material_unit 为副单位时按行率） */
export function syncDualQuantitiesFixed(params: {
  material: MaterialLike | null | undefined;
  value: DocumentDualQuantityValue;
  changed: 'primary' | 'aux';
  scenario?: MaterialScenario;
}): DocumentDualQuantityValue {
  const { material, changed, scenario = 'purchase' } = params;
  const value = { ...params.value };
  const base = readBaseUnit(material);
  const auxUnit = String(value.aux_unit ?? resolveAuxUnitForScenario(material, scenario)).trim();
  const lineUnit = String(value.material_unit ?? auxUnit).trim() || auxUnit;

  if (!base || !auxUnit || auxUnit === base) return value;

  const factor = resolveUnitToBaseFactor(material, auxUnit);
  if (factor == null || factor <= 0) return value;

  const qty = Number(value.quantity);
  const auxQty = Number(value.aux_quantity);

  if (changed === 'primary' && Number.isFinite(qty) && qty > 0) {
    let baseQty = qty;
    if (lineUnit === auxUnit) {
      baseQty = qty * factor;
    } else if (lineUnit !== base) {
      baseQty = qty * factor;
    }
    const nextAux = baseQty / factor;
    if (Number.isFinite(nextAux) && nextAux > 0) {
      value.aux_quantity = nextAux;
    }
    value.quantity = baseQty;
    value.material_unit = base;
    value.unit_conversion_rate = factor;
    if (!value.aux_unit) value.aux_unit = auxUnit;
    return value;
  }

  if (changed === 'aux' && Number.isFinite(auxQty) && auxQty > 0) {
    const baseQty = auxQty * factor;
    value.quantity = baseQty;
    value.material_unit = base;
    value.unit_conversion_rate = factor;
    if (!value.aux_unit) value.aux_unit = auxUnit;
    return value;
  }

  return value;
}

export function syncDualQuantitiesFloating(params: {
  value: DocumentDualQuantityValue;
  changed: 'primary' | 'aux';
}): DocumentDualQuantityValue {
  const value = { ...params.value };
  const primary = Number(value.quantity);
  const aux = Number(value.aux_quantity);
  const rate = computeLineUnitConversionRate(primary, aux);
  if (rate != null) {
    value.unit_conversion_rate = rate;
  }
  return value;
}

/** 从 Form.List 行解析业务数量（主单位）；兼容未注册 Form.Item 时的 quantity 键与副×行率。 */
export function resolveDocumentLineQuantityField(
  row: Record<string, unknown>,
  quantityField: string,
): number {
  const direct = Number(row[quantityField]);
  if (Number.isFinite(direct) && direct > 0) return direct;
  const legacy = Number(row.quantity);
  if (Number.isFinite(legacy) && legacy > 0) return legacy;
  const aux = Number(row.aux_quantity);
  const rate = Number(row.unit_conversion_rate);
  if (Number.isFinite(aux) && aux > 0 && Number.isFinite(rate) && rate > 0) {
    return aux * rate;
  }
  return 0;
}

/** 提交单据行时附带主/副数量与行换算率。 */
export function pickDocumentLineDualQuantityFields(row: Record<string, unknown>) {
  return {
    aux_quantity: row.aux_quantity,
    aux_unit: row.aux_unit,
    unit_conversion_rate: row.unit_conversion_rate,
  };
}

/**
 * 上游单据行 → 下游表单/创建载荷的副数量三字段。
 * 部分下推时按主数量比例缩放副数量；行换算率原样带出。
 */
export function documentLineDualQuantityForPush(
  source: Record<string, unknown> | null | undefined,
  params: { sourcePrimaryQty: number; pushPrimaryQty: number },
): {
  aux_quantity: number | undefined;
  aux_unit: string | undefined;
  unit_conversion_rate: number | undefined;
} {
  const auxUnitRaw = source?.aux_unit ?? source?.auxUnit;
  const auxUnit =
    auxUnitRaw != null && String(auxUnitRaw).trim() ? String(auxUnitRaw).trim() : undefined;
  const rateRaw = source?.unit_conversion_rate ?? source?.unitConversionRate;
  const rateNum = rateRaw != null ? Number(rateRaw) : NaN;
  const rate = Number.isFinite(rateNum) && rateNum > 0 ? rateNum : undefined;
  const auxRaw = source?.aux_quantity ?? source?.auxQuantity;
  if (auxRaw == null || auxRaw === '') {
    return { aux_quantity: undefined, aux_unit: auxUnit, unit_conversion_rate: rate };
  }
  const full = Number(params.sourcePrimaryQty);
  const push = Number(params.pushPrimaryQty);
  let aux = Number(auxRaw);
  if (!Number.isFinite(aux)) {
    return { aux_quantity: undefined, aux_unit: auxUnit, unit_conversion_rate: rate };
  }
  if (!(push > 0)) {
    aux = 0;
  } else if (Number.isFinite(full) && full > 0 && push < full && aux > 0) {
    aux = (aux * push) / full;
  }
  return {
    aux_quantity: aux,
    aux_unit: auxUnit,
    unit_conversion_rate: rate,
  };
}

export function validateDualQuantityBeforeSave(params: {
  material: MaterialLike | null | undefined;
  value: DocumentDualQuantityValue;
}): string | undefined {
  const unit = String(params.value.material_unit ?? '').trim();
  if (!isFloatingLineUnit(params.material, unit)) return undefined;
  const primary = Number(params.value.quantity);
  const aux = Number(params.value.aux_quantity);
  const rate = Number(params.value.unit_conversion_rate);
  if (Number.isFinite(rate) && rate > 0 && Number.isFinite(primary) && primary > 0) {
    return undefined;
  }
  if (Number.isFinite(primary) && primary > 0 && Number.isFinite(aux) && aux > 0) {
    return undefined;
  }
  return '无固定换算须同时填写主数量与副数量，或填写行换算率';
}
