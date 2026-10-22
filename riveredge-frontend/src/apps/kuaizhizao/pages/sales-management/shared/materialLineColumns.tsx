import type { ProColumns } from '@ant-design/pro-components';
import type { TFunction } from 'i18next';

export type PartnerMaterialLineKind = 'customer' | 'supplier';

export function buildPartnerMaterialLineColumns<T extends Record<string, unknown>>(
  t: TFunction,
  partnerKind: PartnerMaterialLineKind,
  options?: { readOnly?: boolean; width?: number },
): ProColumns<T>[] {
  const readOnly = options?.readOnly ?? true;
  const width = options?.width ?? 120;
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
      key: 'partnerMaterialCode',
      width,
      ellipsis: true,
      readonly: readOnly,
    },
    {
      title: nameTitle,
      dataIndex: 'partner_material_name',
      key: 'partnerMaterialName',
      width: width + 40,
      ellipsis: true,
      readonly: readOnly,
    },
  ];
}

export function buildMaterialModelSpecColumns<T extends Record<string, unknown>>(
  t: TFunction,
  options?: { readOnly?: boolean; modelWidth?: number; specWidth?: number },
): ProColumns<T>[] {
  const readOnly = options?.readOnly ?? true;
  const modelWidth = options?.modelWidth ?? 100;
  const specWidth = options?.specWidth ?? 120;

  return [
    {
      title: t('app.kuaizhizao.salesOrder.materialSpec', '规格'),
      dataIndex: 'material_spec',
      key: 'material_spec',
      width: specWidth,
      ellipsis: true,
      readonly: readOnly,
    },
    {
      title: t('app.master-data.materials.model', '型号'),
      dataIndex: 'material_model',
      key: 'material_model',
      width: modelWidth,
      ellipsis: true,
      readonly: readOnly,
    },
  ];
}

/** 物料编码/名称之后：规格、型号（伙伴料号/品名见 buildPartnerMaterialLineColumns，排在备注前） */
export function buildDocumentMaterialLineExtensionColumns<T extends Record<string, unknown>>(
  t: TFunction,
  _partnerKind?: PartnerMaterialLineKind,
  options?: { readOnly?: boolean },
): ProColumns<T>[] {
  return buildMaterialModelSpecColumns(t, options);
}
