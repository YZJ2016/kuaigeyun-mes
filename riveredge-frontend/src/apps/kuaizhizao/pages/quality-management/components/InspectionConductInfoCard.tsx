import React from 'react';
import { Card, Col, Row } from 'antd';
import { useTranslation } from 'react-i18next';
import { formatQuantityWithUnit } from '../../../../../utils/materialUnitDisplay';
import { DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER } from '../../../components/document-detail-table/documentDetailTable';

export function formatInspectionMaterialDisplayValue(value: unknown): string {
  const text = String(value ?? '').trim();
  return text || DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER;
}

export type InspectionConductInfoCardProps = {
  inspection: Record<string, unknown> | null | undefined;
  /** 检验信息卡片标题；OQC 等可省略标题 */
  showSectionTitle?: boolean;
  /** 第一行：工单/工序等上下文（在物料编码之前） */
  leading?: React.ReactNode;
  /** 是否展示检验数量（默认 true） */
  showInspectionQty?: boolean;
  /** 第二行额外列（在规格型号数量之后） */
  trailing?: React.ReactNode;
  colSpan?: number;
};

/** 检验 Modal 内「检验信息」：物料编码/名称 + 规格/型号 + 检验数量 */
export function InspectionConductInfoCard({
  inspection,
  showSectionTitle = true,
  leading,
  showInspectionQty = true,
  trailing,
  colSpan = 8,
}: InspectionConductInfoCardProps) {
  const { t } = useTranslation();
  if (!inspection) return null;

  const spec = formatInspectionMaterialDisplayValue(inspection.material_spec);
  const model = formatInspectionMaterialDisplayValue(inspection.material_model);
  const qty = inspection.inspection_quantity;
  const unit = inspection.material_unit as string | undefined;

  const card = (
    <>
      {leading ? <Row gutter={16}>{leading}</Row> : null}
      <Row gutter={16} style={leading ? { marginTop: 8 } : undefined}>
        <Col span={colSpan}>
          <strong>{t('app.kuaizhizao.quality.common.label.materialCode')}：</strong>
          {formatInspectionMaterialDisplayValue(inspection.material_code)}
        </Col>
        <Col span={colSpan}>
          <strong>{t('app.kuaizhizao.quality.common.label.materialName')}：</strong>
          {formatInspectionMaterialDisplayValue(inspection.material_name)}
        </Col>
        {showInspectionQty && colSpan >= 8 ? (
          <Col span={colSpan}>
            <strong>{t('app.kuaizhizao.quality.common.label.inspectionQty')}：</strong>
            {formatQuantityWithUnit(Number(qty ?? 0), unit)}
          </Col>
        ) : null}
      </Row>
      <Row gutter={16} style={{ marginTop: 8 }}>
        <Col span={colSpan}>
          <strong>{t('app.kuaizhizao.quality.common.columns.materialSpec')}：</strong>
          {spec}
        </Col>
        <Col span={colSpan}>
          <strong>{t('app.kuaizhizao.quality.common.columns.materialModel')}：</strong>
          {model}
        </Col>
        {showInspectionQty && colSpan < 8 ? (
          <Col span={colSpan}>
            <strong>{t('app.kuaizhizao.quality.common.label.inspectionQty')}：</strong>
            {formatQuantityWithUnit(Number(qty ?? 0), unit)}
          </Col>
        ) : null}
        {trailing}
      </Row>
    </>
  );

  if (!showSectionTitle) {
    return (
      <Card size="small" style={{ marginBottom: 8 }}>
        {card}
      </Card>
    );
  }

  return (
    <Card
      title={t('app.kuaizhizao.quality.common.sections.inspectionInfo')}
      size="small"
      style={{ marginBottom: 8 }}
    >
      {card}
    </Card>
  );
}
