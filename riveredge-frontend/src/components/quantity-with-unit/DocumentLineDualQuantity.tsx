import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { UniInputNumber } from '../uni-input-number/UniInputNumber';
import type { Material } from '../../apps/master-data/types/material';
import { isFloatingMaterialUnit } from '../../apps/master-data/utils/materialConversionType';
import {
  findMaterialAuxUnitRow,
  resolveAuxUnitForScenario,
  shouldShowDualQuantityEntry,
  coerceDocumentLineQuantity,
  syncDualQuantitiesFixed,
  syncDualQuantitiesFloating,
  type DocumentDualQuantityValue,
} from '../../utils/materialDualQuantity';
import { resolveMaterialScenarioUnit, type MaterialScenario } from '../../utils/materialScenarioUnit';
import { EMPTY_VALUE_PLACEHOLDER } from '../../utils/format';
import { QuantityWithUnit } from './index';

export type DocumentLineDualQuantityProps = {
  material?: Material | null;
  scenario?: MaterialScenario;
  value?: DocumentDualQuantityValue;
  onChange?: (next: DocumentDualQuantityValue) => void;
  quantityField?: keyof DocumentDualQuantityValue;
  unitField?: keyof DocumentDualQuantityValue;
  disabled?: boolean;
  quantityPrecision?: number;
  /** 为 false 时仅数量框（明细表已有独立单位列时使用） */
  inlineUnitWithQuantity?: boolean;
  /** 主数量列 / 副数量列；缺省时两栏横排 */
  part?: 'primary' | 'aux';
};

/**
 * 单据行数量：主数量与副数量分两栏。无副单位时副数量栏仍展示且不可录入。
 * 固定换算联动，无固定换算双录。
 */
export const DocumentLineDualQuantity: React.FC<DocumentLineDualQuantityProps> = ({
  material,
  scenario = 'purchase',
  value,
  onChange,
  quantityField = 'quantity',
  unitField = 'material_unit',
  disabled = false,
  quantityPrecision = 4,
  inlineUnitWithQuantity = true,
  part,
}) => {
  const baseUnit = String(material?.baseUnit ?? material?.base_unit ?? '').trim();
  const auxUnit = useMemo(
    () => String(value?.aux_unit ?? resolveAuxUnitForScenario(material, scenario)).trim(),
    [material, scenario, value?.aux_unit],
  );
  const auxRow = findMaterialAuxUnitRow(material, auxUnit);
  const floating = isFloatingMaterialUnit(auxRow);
  const showDual = shouldShowDualQuantityEntry(material, scenario);

  const lineQty = coerceDocumentLineQuantity(value?.quantity ?? value?.[quantityField]);
  const lineUnit = String(
    value?.material_unit ?? value?.[unitField] ?? auxUnit,
  ).trim();

  const emit = useCallback(
    (next: DocumentDualQuantityValue) => {
      const qty = coerceDocumentLineQuantity(next.quantity);
      onChange?.({
        ...value,
        ...next,
        quantity: qty,
        [quantityField]: qty,
        [unitField]: next.material_unit,
      });
    },
    [onChange, quantityField, unitField, value],
  );

  const handlePrimaryLineChange = useCallback(
    (next: { quantity?: number | null; unit?: string }) => {
      let merged: DocumentDualQuantityValue = {
        ...value,
        quantity: coerceDocumentLineQuantity(next.quantity),
        material_unit: next.unit ?? lineUnit,
        aux_unit: value?.aux_unit ?? auxUnit,
      };
      if (showDual && !floating) {
        merged = syncDualQuantitiesFixed({
          material,
          value: merged,
          changed: 'primary',
          scenario,
        });
      }
      emit(merged);
    },
    [auxUnit, emit, floating, lineUnit, material, quantityField, scenario, showDual, unitField, value],
  );

  const handleAuxQtyChange = useCallback(
    (auxQty: number | null) => {
      let merged: DocumentDualQuantityValue = {
        ...value,
        quantity: lineQty,
        material_unit: lineUnit || baseUnit,
        aux_quantity: auxQty ?? undefined,
        aux_unit: auxUnit,
      };
      if (auxQty == null || auxQty <= 0) {
        if (!floating) {
          merged.quantity = undefined;
        }
        emit(merged);
        return;
      }
      if (floating) {
        merged = syncDualQuantitiesFloating({ value: merged, changed: 'aux' });
      } else {
        merged = syncDualQuantitiesFixed({
          material,
          value: merged,
          changed: 'aux',
          scenario,
        });
      }
      emit(merged);
    },
    [auxUnit, baseUnit, emit, floating, lineQty, lineUnit, material, scenario, value],
  );

  const handleBaseQtyChange = useCallback(
    (baseQty: number | null) => {
      let merged: DocumentDualQuantityValue = {
        ...value,
        quantity: baseQty ?? undefined,
        material_unit: baseUnit,
        aux_unit: auxUnit,
      };
      if (baseQty == null || baseQty <= 0) {
        if (!floating) {
          merged.aux_quantity = undefined;
        }
        emit(merged);
        return;
      }
      if (floating) {
        merged = syncDualQuantitiesFloating({ value: merged, changed: 'primary' });
      } else {
        merged = syncDualQuantitiesFixed({
          material,
          value: merged,
          changed: 'primary',
          scenario,
        });
      }
      emit(merged);
    },
    [auxUnit, baseUnit, emit, floating, material, scenario, value],
  );

  const lastAutoSyncKeyRef = useRef<string>('');

  useEffect(() => {
    if (!showDual || floating || !onChange || !material || !baseUnit || !auxUnit) return;
    const primary = Number(lineQty);
    if (!Number.isFinite(primary) || primary <= 0) return;
    const syncKey = `${material.id ?? ''}:${primary}:${lineUnit}:${auxUnit}`;
    if (lastAutoSyncKeyRef.current === syncKey && value?.aux_quantity != null) return;

    let merged: DocumentDualQuantityValue = {
      ...value,
      quantity: primary,
      material_unit: lineUnit || baseUnit,
      aux_unit: auxUnit,
    };
    merged = syncDualQuantitiesFixed({
      material,
      value: merged,
      changed: 'primary',
      scenario,
    });
    const nextAux = Number(merged.aux_quantity);
    if (!Number.isFinite(nextAux) || nextAux <= 0) return;
    if (Number(value?.aux_quantity) === nextAux && value?.unit_conversion_rate === merged.unit_conversion_rate) {
      lastAutoSyncKeyRef.current = syncKey;
      return;
    }
    lastAutoSyncKeyRef.current = syncKey;
    emit(merged);
  }, [
    auxUnit,
    baseUnit,
    emit,
    floating,
    lineQty,
    lineUnit,
    material,
    onChange,
    scenario,
    showDual,
    value,
  ]);

  const auxEnabled = showDual && Boolean(baseUnit) && Boolean(auxUnit);
  const primaryBaseQty = lineQty;
  const scenarioUnit = String(resolveMaterialScenarioUnit(material, scenario) || '').trim();
  const primaryUnitLabel = lineUnit || scenarioUnit;

  const primaryControl = !auxEnabled ? (
    inlineUnitWithQuantity ? (
      <UniInputNumber
        value={lineQty as number | null | undefined}
        onChange={(qty) =>
          handlePrimaryLineChange({
            quantity: qty,
            unit: primaryUnitLabel || undefined,
          })
        }
        min={0}
        precision={quantityPrecision}
        disabled={disabled}
        addonAfter={primaryUnitLabel || undefined}
        style={{ width: '100%' }}
      />
    ) : (
      <QuantityWithUnit
        material={material ?? undefined}
        scenario={scenario}
        value={{
          quantity: lineQty as number | null | undefined,
          unit: lineUnit,
        }}
        onChange={handlePrimaryLineChange}
        disabled={disabled}
        quantityPrecision={quantityPrecision}
        layout="quantity-only"
      />
    )
  ) : (
    <UniInputNumber
      value={primaryBaseQty != null && Number.isFinite(primaryBaseQty) ? primaryBaseQty : undefined}
      onChange={handleBaseQtyChange}
      min={0}
      precision={quantityPrecision}
      disabled={disabled}
      addonAfter={baseUnit}
      style={{ width: '100%' }}
    />
  );

  const auxControl = (
    <UniInputNumber
      value={auxEnabled ? (value?.aux_quantity ?? undefined) : undefined}
      onChange={auxEnabled ? handleAuxQtyChange : undefined}
      min={0}
      precision={quantityPrecision}
      disabled={disabled || !auxEnabled}
      placeholder={auxEnabled ? undefined : EMPTY_VALUE_PLACEHOLDER}
      addonAfter={auxEnabled ? auxUnit : undefined}
      style={{ width: '100%' }}
    />
  );

  if (part === 'aux') return auxControl;
  if (part === 'primary') return primaryControl;

  return (
    <div style={{ display: 'flex', gap: 8, width: '100%', alignItems: 'center' }}>
      <div style={{ flex: 1, minWidth: 0 }}>{primaryControl}</div>
      <div style={{ flex: 1, minWidth: 0 }}>{auxControl}</div>
    </div>
  );
};
