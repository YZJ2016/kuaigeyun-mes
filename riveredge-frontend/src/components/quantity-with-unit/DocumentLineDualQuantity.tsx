import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import { InputNumber, Space } from 'antd';
import { MaterialUnitRoleBadge } from './MaterialUnitRoleBadge';
import type { Material } from '../../apps/master-data/types/material';
import { isFloatingMaterialUnit } from '../../apps/master-data/utils/materialConversionType';
import {
  findMaterialAuxUnitRow,
  resolveAuxUnitForScenario,
  shouldShowDualQuantityEntry,
  syncDualQuantitiesFixed,
  syncDualQuantitiesFloating,
  type DocumentDualQuantityValue,
} from '../../utils/materialDualQuantity';
import type { MaterialScenario } from '../../utils/materialScenarioUnit';
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
};

/**
 * 单据行数量：有副单位时展示主数量 + 副数量；固定换算联动，无固定换算双录。
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
}) => {
  const baseUnit = String(material?.baseUnit ?? material?.base_unit ?? '').trim();
  const auxUnit = useMemo(
    () => String(value?.aux_unit ?? resolveAuxUnitForScenario(material, scenario)).trim(),
    [material, scenario, value?.aux_unit],
  );
  const auxRow = findMaterialAuxUnitRow(material, auxUnit);
  const floating = isFloatingMaterialUnit(auxRow);
  const showDual = shouldShowDualQuantityEntry(material, scenario);

  const lineQty =
    (value?.quantity as number | null | undefined) ??
    (value?.[quantityField] as number | null | undefined);
  const lineUnit = String(
    value?.material_unit ?? value?.[unitField] ?? auxUnit,
  ).trim();

  const emit = useCallback(
    (next: DocumentDualQuantityValue) => {
      onChange?.({
        ...value,
        ...next,
        [quantityField]: next.quantity,
        [unitField]: next.material_unit,
      });
    },
    [onChange, quantityField, unitField, value],
  );

  const handlePrimaryLineChange = useCallback(
    (next: { quantity?: number | null; unit?: string }) => {
      let merged: DocumentDualQuantityValue = {
        ...value,
        quantity: next.quantity ?? undefined,
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
        quantity: lineQty as number | undefined,
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

  if (!showDual || !baseUnit || !auxUnit) {
    return (
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
      />
    );
  }

  const primaryBaseQty = Number(value?.quantity ?? lineQty);

  return (
    <Space orientation="vertical" size={4} style={{ width: '100%' }}>
      <Space size={8} style={{ width: '100%', alignItems: 'center' }}>
        <MaterialUnitRoleBadge role="primary" style={{ flexShrink: 0 }} />
        <InputNumber
          value={Number.isFinite(primaryBaseQty) ? primaryBaseQty : undefined}
          onChange={handleBaseQtyChange}
          min={0}
          precision={quantityPrecision}
          disabled={disabled}
          addonAfter={baseUnit}
          style={{ flex: 1, minWidth: 80 }}
        />
      </Space>
      <Space size={8} style={{ width: '100%', alignItems: 'center' }}>
        <MaterialUnitRoleBadge role="aux" style={{ flexShrink: 0 }} />
        <InputNumber
          value={value?.aux_quantity ?? undefined}
          onChange={handleAuxQtyChange}
          min={0}
          precision={quantityPrecision}
          disabled={disabled}
          addonAfter={auxUnit}
          style={{ flex: 1, minWidth: 80 }}
        />
      </Space>
    </Space>
  );
};
