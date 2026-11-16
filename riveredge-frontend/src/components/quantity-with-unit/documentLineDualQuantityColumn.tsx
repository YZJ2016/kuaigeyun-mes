import React from 'react';
import { Form as AntForm, Input } from 'antd';
import type { FormInstance } from 'antd/es/form';
import type { Material } from '../../apps/master-data/types/material';
import { fetchMaterialForUnitSelectCache } from '../material-unit-select';
import type { MaterialScenario } from '../../utils/materialScenarioUnit';
import { DocumentLineDualQuantity } from './DocumentLineDualQuantity';
import type { DocumentDualQuantityValue } from '../../utils/materialDualQuantity';

export type DocumentLineDualQuantityColumnOptions = {
  form: FormInstance;
  listName: string;
  rowIndex: number;
  quantityField: string;
  unitField: string;
  scenario?: MaterialScenario;
  quantityPrecision?: number;
  materialId?: number | string | null;
  /** 明细表已有独立单位列时为 false（默认）；无单位列的弹窗传 true */
  inlineUnitWithQuantity?: boolean;
  /** 数量写入表单后回调（用于未锁定行阶梯重算等） */
  onAfterQuantityChange?: (quantity: number, rowIndex: number) => void;
};

export const DocumentLineDualQuantityFormCell: React.FC<DocumentLineDualQuantityColumnOptions> = ({
  form,
  listName,
  rowIndex,
  quantityField,
  unitField,
  scenario = 'purchase',
  quantityPrecision = 4,
  materialId,
  inlineUnitWithQuantity = false,
  onAfterQuantityChange,
}) => {
  const [material, setMaterial] = React.useState<Material | null>(null);

  React.useEffect(() => {
    if (!materialId) {
      setMaterial(null);
      return;
    }
    let cancelled = false;
    fetchMaterialForUnitSelectCache(materialId).then((m) => {
      if (!cancelled) setMaterial(m ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, [materialId]);

  return (
    <>
      {/* Form.List 提交只收集带 name 的字段；主/副数量 UI 须注册数量键 */}
      <AntForm.Item name={[rowIndex, quantityField]} hidden preserve>
        <Input type="hidden" />
      </AntForm.Item>
      <AntForm.Item noStyle shouldUpdate>
        {() => {
          const items = form.getFieldValue(listName) ?? [];
          const row = items[rowIndex] ?? {};
          const value: DocumentDualQuantityValue = {
            quantity: row[quantityField],
            material_unit: row[unitField],
            aux_quantity: row.aux_quantity,
            aux_unit: row.aux_unit,
            unit_conversion_rate: row.unit_conversion_rate,
          };
          return (
            <DocumentLineDualQuantity
              material={material}
              scenario={scenario}
              quantityField={quantityField as keyof DocumentDualQuantityValue}
              unitField={unitField as keyof DocumentDualQuantityValue}
              quantityPrecision={quantityPrecision}
              inlineUnitWithQuantity={inlineUnitWithQuantity}
              value={value}
              onChange={(next) => {
                const rowQty =
                  next.quantity ??
                  (next as Record<string, unknown>)[quantityField] ??
                  row[quantityField];
                const nextItems = [...items];
                nextItems[rowIndex] = {
                  ...row,
                  [quantityField]: rowQty,
                  [unitField]: next.material_unit ?? row[unitField],
                  aux_quantity: next.aux_quantity,
                  aux_unit: next.aux_unit,
                  unit_conversion_rate: next.unit_conversion_rate,
                };
                form.setFieldsValue({ [listName]: nextItems });
                const n = Number(rowQty);
                if (onAfterQuantityChange && Number.isFinite(n) && n > 0) {
                  onAfterQuantityChange(n, rowIndex);
                }
              }}
            />
          );
        }}
      </AntForm.Item>
    </>
  );
};
