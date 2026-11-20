import type { TFunction } from 'i18next';
import type { ColumnType } from 'antd/es/table';
import {
  MaterialStackedCell,
  UniTableStackedPrimaryCell,
} from '../uni-table/stackedPrimaryColumn';

export type PullQueryPartnerField = 'customer_name' | 'supplier_name';

export type PullQueryMaterialIdentityRow = {
  material_name?: string | null;
  material_code?: string | null;
  material_spec?: string | null;
};

/** 取单：物料名称 / 编码·规格 叠列（替代 material_code + material_name + material_spec 三列） */
export function buildPullQueryMaterialIdentityColumn<T extends PullQueryMaterialIdentityRow>(
  t: TFunction,
  options?: { titleKey?: string; width?: number },
): ColumnType<T> {
  return {
    title: t(options?.titleKey ?? 'app.kuaizhizao.purchaseOrder.col.materialName'),
    dataIndex: 'material_name',
    key: 'pull_material_identity',
    width: options?.width ?? 200,
    ellipsis: false,
    render: (_: unknown, record: T) => (
      <MaterialStackedCell
        material_name={record.material_name}
        material_code={record.material_code}
        material_spec={record.material_spec}
      />
    ),
  };
}

/** 取单：往来单位 / 单号 叠列（替代 customer_name + order_code 等两列） */
export function buildPullQueryPartnerDocumentColumn<
  T extends Record<string, unknown>,
>(t: TFunction, options: {
  titleKey: string;
  codeDataIndex: keyof T & string;
  partnerField: PullQueryPartnerField;
  width?: number;
}): ColumnType<T> {
  return {
    title: t(options.titleKey),
    dataIndex: options.codeDataIndex,
    key: `pull_partner_${String(options.codeDataIndex)}`,
    width: options.width ?? 168,
    ellipsis: false,
    render: (_: unknown, record: T) => (
      <UniTableStackedPrimaryCell
        primary={String(record[options.partnerField] ?? '')}
        secondary={String(record[options.codeDataIndex] ?? '')}
        skipLinkedDocumentLink
      />
    ),
  };
}