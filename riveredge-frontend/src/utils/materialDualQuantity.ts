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

/** 提交单据行时附带主/副数量与行换算率。 */
export function pickDocumentLineDualQuantityFields(row: Record<string, unknown>) {
  return {
    aux_quantity: row.aux_quantity,
    aux_unit: row.aux_unit,
    unit_conversion_rate: row.unit_conversion_rate,
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
