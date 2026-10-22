/**
 * 有物料明细的单据 Form 行：选料回填映射、规格/型号列（规格在前、空占位 —）
 */
import React from 'react';
import { Form } from 'antd';
import type { TFunction } from 'i18next';
import {
  DOCUMENT_DETAIL_COL_WIDTH,
  DOCUMENT_DETAIL_CONTROL_SIZE,
  DOCUMENT_DETAIL_TEXT_COL,
  DocumentDetailLineReadonlyTextInput,
  DocumentDetailLineTextInput,
} from '../../../components/document-detail-table/documentDetailTable';
import type { PartnerMaterialLineKind } from './materialLineColumns';

/** UniMaterialSelect fillMapping：编码/名称/规格/型号 */
export const DOCUMENT_MATERIAL_LINE_FILL_MAPPING: Record<string, string> = {
  material_code: 'mainCode',
  material_name: 'name',
  material_spec: 'specification',
  material_model: 'model',
};

export function withMaterialLineFillMapping(extra?: Record<string, string>): Record<string, string> {
  return { ...DOCUMENT_MATERIAL_LINE_FILL_MAPPING, ...extra };
}

export type DocumentDetailSpecModelFormColumnOptions = {
  width?: number;
  textCol?: Record<string, unknown>;
  specEditable?: boolean;
  inputSize?: React.ComponentProps<typeof DocumentDetailLineTextInput>['size'];
};

/** 明细表：规格 → 型号（Form.List 行内） */
export function buildDocumentDetailSpecModelFormColumns(
  t: TFunction,
  options?: DocumentDetailSpecModelFormColumnOptions,
) {
  const width = options?.width ?? DOCUMENT_DETAIL_COL_WIDTH.spec;
  const textCol = options?.textCol ?? DOCUMENT_DETAIL_TEXT_COL;
  const specEditable = options?.specEditable ?? true;
  const inputSize = options?.inputSize ?? DOCUMENT_DETAIL_CONTROL_SIZE;

  return [
    {
      title: t('app.kuaizhizao.salesOrder.spec', '规格'),
      dataIndex: 'material_spec',
      width,
      ...textCol,
      render: (_: unknown, __: unknown, index: number) => (
        <Form.Item name={[index, 'material_spec']} style={{ margin: 0 }}>
          {specEditable ? (
            <DocumentDetailLineTextInput size={inputSize} />
          ) : (
            <DocumentDetailLineReadonlyTextInput size={inputSize} />
          )}
        </Form.Item>
      ),
    },
    {
      title: t('app.master-data.materials.model', '型号'),
      dataIndex: 'material_model',
      width,
      ...textCol,
      render: (_: unknown, __: unknown, index: number) => (
        <Form.Item name={[index, 'material_model']} style={{ margin: 0 }}>
          <DocumentDetailLineReadonlyTextInput size={inputSize} />
        </Form.Item>
      ),
    },
  ];
}

/** 明细表：客户/供应商料号品名（只读，排在备注前） */
export function buildDocumentDetailPartnerMaterialFormColumns(
  t: TFunction,
  partnerKind: PartnerMaterialLineKind,
  options?: DocumentDetailSpecModelFormColumnOptions,
) {
  const width = options?.width ?? DOCUMENT_DETAIL_COL_WIDTH.spec;
  const textCol = options?.textCol ?? DOCUMENT_DETAIL_TEXT_COL;
  const inputSize = options?.inputSize ?? DOCUMENT_DETAIL_CONTROL_SIZE;
  const codeTitle =
    partnerKind === 'customer'
      ? t('app.master-data.priceBook.customerMaterialCode', '客户料号')
      : t('app.master-data.priceBook.supplierMaterialCode', '供应商料号');
  const nameTitle =
    partnerKind === 'customer'
      ? t('app.master-data.priceBook.customerMaterialName', '客户品名')
      : t('app.master-data.priceBook.supplierMaterialName', '供应商品名');

  return [
    {
      title: codeTitle,
      dataIndex: 'partner_material_code',
      width,
      ...textCol,
      render: (_: unknown, __: unknown, index: number) => (
        <Form.Item name={[index, 'partner_material_code']} style={{ margin: 0 }}>
          <DocumentDetailLineReadonlyTextInput size={inputSize} />
        </Form.Item>
      ),
    },
    {
      title: nameTitle,
      dataIndex: 'partner_material_name',
      width: width + 24,
      ...textCol,
      render: (_: unknown, __: unknown, index: number) => (
        <Form.Item name={[index, 'partner_material_name']} style={{ margin: 0 }}>
          <DocumentDetailLineReadonlyTextInput size={inputSize} />
        </Form.Item>
      ),
    },
  ];
}
