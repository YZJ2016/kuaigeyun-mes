import React from 'react';
import { Form as AntForm } from 'antd';
import type { FormInstance } from 'antd/es/form';
import { DocumentLineUnitSelect } from './DocumentLineUnitSelect';
import { DocumentLineDualQuantityFormCell } from './documentLineDualQuantityColumn';
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

/** 单据明细表：单位列 + 主/副数量列（与采购/销售订单同一套交互）。 */
export function buildDocumentLineDualQuantityFormColumns(
  params: DocumentLineDualQuantityFormColumnOptions,
): Record<string, unknown>[] {
  const listName = params.listName ?? 'items';
  const unitWidth = params.unitWidth ?? 108;
  const quantityWidth = params.quantityWidth ?? 192;
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
    {
      title: params.t('common.quantity'),
      dataIndex: params.quantityField,
      width: quantityWidth,
      align: alignQuantity,
      ...params.quantityColumnSpread,
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
                form={form}
                listName={listName}
                rowIndex={index}
                quantityField={params.quantityField}
                unitField={params.unitField}
                scenario={scenario}
                quantityPrecision={quantityDecimals}
                materialId={materialId}
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
    },
  ];
}
