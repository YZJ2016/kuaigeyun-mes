/**
 * 有物料明细的单据 Form 行：选料回填映射、规格/型号列（规格在前、空占位 —）
 * 规格/型号一律从物料资料带入，明细行不可改。
 */
import React from 'react';
import { Form } from 'antd';
import type { TFunction } from 'i18next';
import {
  DOCUMENT_DETAIL_COL_WIDTH,
  DOCUMENT_DETAIL_CONTROL_SIZE,
  DOCUMENT_DETAIL_NUM_COL,
  DOCUMENT_DETAIL_TEXT_COL,
  DocumentDetailLineReadonlyTextInput,
} from '../../../components/document-detail-table/documentDetailTable';
import { DocumentLineTotalStockCell } from '../../../components/DocumentLineTotalStock';
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
  /** @deprecated 规格一律只读；保留字段以免旧调用方报错 */
  specEditable?: boolean;
  inputSize?: React.ComponentProps<typeof DocumentDetailLineReadonlyTextInput>['size'];
};

/** 明细表：总库存（租户全仓汇总，hover 分仓） */
export function buildDocumentDetailTotalStockFormColumn(t: TFunction) {
  return {
    title: t('app.kuaizhizao.documentDetail.totalStock', '总库存'),
    dataIndex: '_line_total_stock',
    width: 112,
    ...DOCUMENT_DETAIL_NUM_COL,
    render: (_: unknown, __: unknown, index: number) => (
      <Form.Item
        noStyle
        shouldUpdate={(prev, curr) => prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id}
      >
        {({ getFieldValue }) => {
          const materialId = getFieldValue(['items', index, 'material_id']);
          return <DocumentLineTotalStockCell materialId={materialId} />;
        }}
      </Form.Item>
    ),
  };
}

/** 明细表：规格 → 型号（Form.List 行内；均只读，选料时由物料资料回填） */
export function buildDocumentDetailSpecModelFormColumns(
  t: TFunction,
  options?: DocumentDetailSpecModelFormColumnOptions,
) {
  const width = options?.width ?? DOCUMENT_DETAIL_COL_WIDTH.spec;
  const textCol = options?.textCol ?? DOCUMENT_DETAIL_TEXT_COL;
  const inputSize = options?.inputSize ?? DOCUMENT_DETAIL_CONTROL_SIZE;

  return [
    buildDocumentDetailTotalStockFormColumn(t),
    {
      title: t('app.kuaizhizao.salesOrder.spec', '规格'),
      dataIndex: 'material_spec',
      width,
      ...textCol,
      render: (_: unknown, __: unknown, index: number) => (
        <Form.Item name={[index, 'material_spec']} style={{ margin: 0 }}>
          <DocumentDetailLineReadonlyTextInput size={inputSize} />
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
