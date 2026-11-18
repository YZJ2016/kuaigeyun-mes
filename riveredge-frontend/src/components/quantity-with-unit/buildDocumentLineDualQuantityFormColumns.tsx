import React from 'react';
import { Form as AntForm } from 'antd';
import type { FormInstance } from 'antd/es/form';
import { DocumentLineUnitSelect } from './DocumentLineUnitSelect';
import { DocumentLineDualQuantityFormCell } from './documentLineDualQuantityColumn';
import { QuantityWithUnitDisplay } from './QuantityWithUnitDisplay';
import { EMPTY_VALUE_PLACEHOLDER } from '../../utils/format';
import type { MaterialScenario } from '../../utils/materialScenarioUnit';

export type DocumentLineDualQuantityFormColumnOptions = {
  t: (key: string) => string;
  getForm: () => FormInstance | null | undefined;
  listName?: string;
  quantityField: string;
  unitField: string;
  scenario?: MaterialScenario;
  quantityDecimals?: number;
  unitWidth?: number;
  quantityWidth?: number;
  controlSize?: 'small' | 'middle' | 'large';
  alignQuantity?: 'left' | 'right' | 'center';
  unitColumnSpread?: Record<string, unknown>;
  quantityColumnSpread?: Record<string, unknown>;
  /** 数量变更后（未锁定行阶梯重算等） */
  onAfterQuantityChange?: (rowIndex: number) => void;
};

const DUAL_QUANTITY_COL_WIDTH = 168;

export type DocumentLineDualQuantityPairColumnOptions = {
  t: (key: string) => string;
  getForm: () => FormInstance | null | undefined;
  listName?: string;
  quantityField: string;
  unitField: string;
  scenario?: MaterialScenario;
  quantityPrecision?: number;
  width?: number;
  columnSpread?: Record<string, unknown>;
  /** 默认 true：单位贴主数量；有独立单位列时须显式 false */
  inlineUnitWithQuantity?: boolean;
  onAfterQuantityChange?: (rowIndex: number) => void;
};

/** 主数量、副数量两列。无副单位时副数量列仍显示；默认单位贴主数量（与采购申请一致）。 */
export function buildDocumentLineDualQuantityPairColumns(
  params: DocumentLineDualQuantityPairColumnOptions,
): Record<string, unknown>[] {
  const listName = params.listName ?? 'items';
  const width = params.width ?? DUAL_QUANTITY_COL_WIDTH;
  const scenario = params.scenario ?? 'purchase';
  const quantityPrecision = params.quantityPrecision ?? 4;
  const inlineUnitWithQuantity = params.inlineUnitWithQuantity !== false;

  const makeColumn = (part: 'primary' | 'aux') => ({
    title: params.t(part === 'primary' ? 'common.primaryQuantity' : 'common.auxQuantity'),
    dataIndex: part === 'primary' ? params.quantityField : 'aux_quantity',
    width,
    ...params.columnSpread,
    render: (_: unknown, __: unknown, index: number) => (
      <AntForm.Item
        noStyle
        shouldUpdate={(prev: Record<string, unknown>, curr: Record<string, unknown>) =>
          (prev?.[listName] as Record<string, unknown>[])?.[index]?.material_id !==
          (curr?.[listName] as Record<string, unknown>[])?.[index]?.material_id
        }
      >
        {({ getFieldValue }) => {
          const materialId = getFieldValue([listName, index, 'material_id']);
          const form = params.getForm();
          if (!form) return null;
          return (
            <DocumentLineDualQuantityFormCell
              part={part}
              form={form}
              listName={listName}
              rowIndex={index}
              quantityField={params.quantityField}
              unitField={params.unitField}
              scenario={scenario}
              quantityPrecision={quantityPrecision}
              materialId={materialId}
              inlineUnitWithQuantity={inlineUnitWithQuantity}
              onAfterQuantityChange={
                params.onAfterQuantityChange
                  ? () => params.onAfterQuantityChange?.(index)
                  : undefined
              }
            />
          );
        }}
      </AntForm.Item>
    ),
  });

  return [makeColumn('primary'), makeColumn('aux')];
}

export type DocumentLineDualQuantityDetailColumnOptions = {
  t: (key: string) => string;
  quantityField?: string;
  unitField?: string;
  auxQuantityField?: string;
  auxUnitField?: string;
  width?: number;
};

/** 详情抽屉/只读 Table：主数量 + 副数量，与 buildDocumentLineDualQuantityPairColumns 列序一致 */
export function buildDocumentLineDualQuantityDetailColumns(
  params: DocumentLineDualQuantityDetailColumnOptions,
): Record<string, unknown>[] {
  const quantityField = params.quantityField ?? 'quantity';
  const unitField = params.unitField ?? 'unit';
  const auxQuantityField = params.auxQuantityField ?? 'aux_quantity';
  const auxUnitField = params.auxUnitField ?? 'aux_unit';
  const width = params.width ?? DUAL_QUANTITY_COL_WIDTH;

  return [
    {
      title: params.t('common.primaryQuantity'),
      dataIndex: quantityField,
      width,
      align: 'right' as const,
      render: (val: unknown, row: Record<string, unknown>) => (
        <QuantityWithUnitDisplay quantity={val} unit={row[unitField]} />
      ),
    },
    {
      title: params.t('common.auxQuantity'),
      dataIndex: auxQuantityField,
      width,
      align: 'right' as const,
      render: (_: unknown, row: Record<string, unknown>) => {
        const auxQty = row[auxQuantityField];
        const auxUnit = row[auxUnitField];
        const auxNum = auxQty != null && auxQty !== '' ? Number(auxQty) : NaN;
        const hasAux =
          (Number.isFinite(auxNum) && auxNum > 0) || String(auxUnit ?? '').trim().length > 0;
        if (!hasAux) {
          return EMPTY_VALUE_PLACEHOLDER;
        }
        return <QuantityWithUnitDisplay quantity={auxQty} unit={auxUnit} />;
      },
    },
  ];
}

/** 单据明细表：单位列 + 主数量列 + 副数量列。 */
export function buildDocumentLineDualQuantityFormColumns(
  params: DocumentLineDualQuantityFormColumnOptions,
): Record<string, unknown>[] {
  const listName = params.listName ?? 'items';
  const unitWidth = params.unitWidth ?? 108;
  const quantityWidth = params.quantityWidth ?? DUAL_QUANTITY_COL_WIDTH;
  const scenario = params.scenario ?? 'purchase';
  const quantityDecimals = params.quantityDecimals ?? 4;
  const controlSize = params.controlSize ?? 'small';
  const alignQuantity = params.alignQuantity ?? 'right';

  return [
    {
      title: params.t('common.unit'),
      dataIndex: params.unitField,
      width: unitWidth,
      ...params.unitColumnSpread,
      render: (_: unknown, __: unknown, index: number) => (
        <AntForm.Item
          noStyle
          shouldUpdate={(prev: Record<string, unknown>, curr: Record<string, unknown>) =>
            (prev?.[listName] as unknown[])?.[index] !== (curr?.[listName] as unknown[])?.[index] ||
            (prev?.[listName] as Record<string, unknown>[])?.[index]?.material_id !==
              (curr?.[listName] as Record<string, unknown>[])?.[index]?.material_id
          }
        >
          {({ getFieldValue }) => {
            const materialId = getFieldValue([listName, index, 'material_id']);
            const form = params.getForm();
            if (!form) return null;
            return (
              <AntForm.Item name={[index, params.unitField]} style={{ margin: 0 }}>
                <DocumentLineUnitSelect
                  form={form}
                  listName={listName}
                  rowIndex={index}
                  fields={{ quantity: params.quantityField, unit: params.unitField }}
                  materialId={materialId}
                  size={controlSize}
                  noStyle
                />
              </AntForm.Item>
            );
          }}
        </AntForm.Item>
      ),
    },
    ...buildDocumentLineDualQuantityPairColumns({
      t: params.t,
      getForm: params.getForm,
      listName,
      quantityField: params.quantityField,
      unitField: params.unitField,
      scenario,
      quantityPrecision: quantityDecimals,
      width: quantityWidth,
      columnSpread: { align: alignQuantity, ...params.quantityColumnSpread },
      inlineUnitWithQuantity: false,
      onAfterQuantityChange: params.onAfterQuantityChange,
    }),
  ];
}
