import React from 'react';
import { Form as AntForm, Input } from 'antd';
import type { FormInstance } from 'antd/es/form';
import type { Material } from '../../apps/master-data/types/material';
import { fetchMaterialForUnitSelectCache } from '../material-unit-select';
import type { MaterialScenario } from '../../utils/materialScenarioUnit';
import { DocumentLineDualQuantity } from './DocumentLineDualQuantity';
import {
  coerceDocumentLineQuantity,
  type DocumentDualQuantityValue,
} from '../../utils/materialDualQuantity';
import { syncFormListLineItemAmountAfterQuantityChange } from '../../apps/kuaizhizao/utils/documentLineAmounts';

export type DocumentLineDualQuantityColumnOptions = {
  form: FormInstance;
  listName: string;
  rowIndex: number;
  quantityField: string;
  unitField: string;
  scenario?: MaterialScenario;
  quantityPrecision?: number;
  materialId?: number | string | null;
  /** 单位贴在主数量右侧（默认 true，与采购申请一致）。仅 `buildDocumentLineDualQuantityFormColumns` 已有独立单位列时传 false */
  inlineUnitWithQuantity?: boolean;
  /** 数量写入表单后回调（用于未锁定行阶梯重算等） */
  onAfterQuantityChange?: (quantity: number, rowIndex: number) => void;
  /** 主数量列或副数量列 */
  part?: 'primary' | 'aux';
};

/** 行上的主数量若被写成对象，输入框会显示 [object Object]。见到非数字就收回数字。 */
const LineQuantityStoreRepair: React.FC<{
  form: FormInstance;
  listName: string;
  rowIndex: number;
  quantityField: string;
  raw: unknown;
}> = ({ form, listName, rowIndex, quantityField, raw }) => {
  const repairKey =
    typeof raw === 'number' || raw == null || raw === ''
      ? ''
      : `bad:${coerceDocumentLineQuantity(raw) ?? ''}`;
  React.useEffect(() => {
    if (!repairKey) return;
    const items = form.getFieldValue(listName) ?? [];
    const current = items[rowIndex]?.[quantityField];
    if (typeof current === 'number' && Number.isFinite(current)) return;
    if (current == null || current === '') return;
    const recovered = coerceDocumentLineQuantity(current);
    if (recovered == null) return;
    form.setFieldValue([listName, rowIndex, quantityField], recovered);
  }, [form, listName, quantityField, repairKey, rowIndex]);
  return null;
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
  inlineUnitWithQuantity = true,
  onAfterQuantityChange,
  part,
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
      {/* Form.List 提交只收集带 name 的字段；主/副数量与换算率须全部注册，否则 setFieldsValue 写入也会在 finish 时丢掉 */}
      {part !== 'aux' ? (
        <>
          {inlineUnitWithQuantity ? (
            <AntForm.Item name={[rowIndex, unitField]} hidden preserve>
              <Input type="hidden" />
            </AntForm.Item>
          ) : null}
          <AntForm.Item name={[rowIndex, quantityField]} hidden preserve>
            <Input type="hidden" />
          </AntForm.Item>
          <AntForm.Item name={[rowIndex, 'aux_quantity']} hidden preserve>
            <Input type="hidden" />
          </AntForm.Item>
          <AntForm.Item name={[rowIndex, 'aux_unit']} hidden preserve>
            <Input type="hidden" />
          </AntForm.Item>
          <AntForm.Item name={[rowIndex, 'unit_conversion_rate']} hidden preserve>
            <Input type="hidden" />
          </AntForm.Item>
        </>
      ) : null}
      <AntForm.Item noStyle shouldUpdate>
        {() => {
          const items = form.getFieldValue(listName) ?? [];
          const row = items[rowIndex] ?? {};
          const value: DocumentDualQuantityValue = {
            quantity: coerceDocumentLineQuantity(row[quantityField]),
            material_unit: row[unitField],
            aux_quantity: row.aux_quantity,
            aux_unit: row.aux_unit,
            unit_conversion_rate: row.unit_conversion_rate,
          };
          return (
            <>
            {part !== 'aux' ? (
              <LineQuantityStoreRepair
                form={form}
                listName={listName}
                rowIndex={rowIndex}
                quantityField={quantityField}
                raw={row[quantityField]}
              />
            ) : null}
            <DocumentLineDualQuantity
              material={material}
              scenario={scenario}
              quantityField={quantityField as keyof DocumentDualQuantityValue}
              unitField={unitField as keyof DocumentDualQuantityValue}
              quantityPrecision={quantityPrecision}
              inlineUnitWithQuantity={inlineUnitWithQuantity}
              part={part}
              value={value}
              onChange={(next) => {
                const rawPrimary = row[quantityField];
                const rowQty = coerceDocumentLineQuantity(
                  next.quantity ??
                    (next as Record<string, unknown>)[quantityField] ??
                    rawPrimary,
                );
                const prevPrimary = coerceDocumentLineQuantity(rawPrimary);
                const primaryChanged =
                  rowQty != null && (prevPrimary == null || rowQty !== prevPrimary);
                // 只写数量/单位相关字段，禁止整行 setFieldsValue 冲掉规格等快照列。
                // 数量必须是数字；对象写进去会在输入框显示 [object Object]。
                if (rowQty != null && rowQty !== rawPrimary) {
                  form.setFieldValue([listName, rowIndex, quantityField], rowQty);
                } else if (rowQty == null && typeof rawPrimary === 'number') {
                  form.setFieldValue([listName, rowIndex, quantityField], undefined);
                }
                const nextUnit = next.material_unit ?? row[unitField];
                if (
                  (typeof nextUnit === 'string' || nextUnit == null || nextUnit === '') &&
                  nextUnit !== row[unitField]
                ) {
                  form.setFieldValue([listName, rowIndex, unitField], nextUnit);
                }
                form.setFieldValue([listName, rowIndex, 'aux_quantity'], next.aux_quantity);
                form.setFieldValue([listName, rowIndex, 'aux_unit'], next.aux_unit);
                form.setFieldValue(
                  [listName, rowIndex, 'unit_conversion_rate'],
                  next.unit_conversion_rate,
                );
                // 主数量走 setFieldValue，不触发 onValuesChange；销售行 item_amount 须按新数量重算
                if (primaryChanged && rowQty != null) {
                  syncFormListLineItemAmountAfterQuantityChange(
                    form,
                    rowIndex,
                    quantityField,
                    rowQty,
                    listName,
                  );
                }
                // 副数量自动换算不得触发阶梯重价（否则下推打开页会把来源单价冲成 0）
                if (primaryChanged && onAfterQuantityChange && rowQty != null && rowQty > 0) {
                  onAfterQuantityChange(rowQty, rowIndex);
                }
              }}
            />
            </>
          );
        }}
      </AntForm.Item>
    </>
  );
};
