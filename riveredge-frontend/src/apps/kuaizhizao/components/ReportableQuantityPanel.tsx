/**
 * 报工弹窗：工单计划 / 可报数量 / 可超报数量 / 物料剩余 / 本次可报 等参考量
 */

import React, { useMemo } from 'react';
import { Col, Row, Statistic, Typography, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import {
  getReportableQuantityBreakdown,
  getWorkOrderMaterialLossTotal,
} from '../utils/workOrderReporting';
import { warehouseApi } from '../services/warehouse-execution';
import { formatQuantity } from '../../../utils/format';
import { convertBaseQtyToProductionDisplay } from '../../../utils/materialScenarioUnit';

export interface ReportableQuantityPanelProps {
  operation: any;
  /** 工单计划数量（基础单位） */
  workOrderQuantity: number;
  operations?: any[];
  workOrderId?: number;
  /** 工单头（行超报为 none 时回落默认超报） */
  workOrder?: any;
  /** 生产场景展示单位；与基础单位不同时，面板数值按生产单位展示 */
  unitContext?: {
    product_unit?: string;
    productUnit?: string;
    base_unit?: string;
    baseUnit?: string;
    unit_to_base_factor?: number;
    unitToBaseFactor?: number;
  };
}

const ReportableQuantityPanel: React.FC<ReportableQuantityPanelProps> = ({
  operation,
  workOrderQuantity,
  operations = [],
  workOrderId,
  workOrder,
  unitContext,
}) => {
  const { token } = theme.useToken();
  const { t } = useTranslation();
  const {
    standardPlanRemaining,
    overReportRemaining,
    materialRemaining,
    effectiveRemaining,
    planRemaining,
  } = getReportableQuantityBreakdown(
    operation,
    workOrderQuantity,
    workOrder ?? unitContext,
    operations,
  );

  const toDisplay = (baseQty: number) =>
    unitContext ? convertBaseQtyToProductionDisplay(baseQty, unitContext) : baseQty;

  const unitSuffix = (() => {
    const productUnit = String(unitContext?.product_unit ?? unitContext?.productUnit ?? '').trim();
    const baseUnit = String(unitContext?.base_unit ?? unitContext?.baseUnit ?? '').trim();
    const raw = productUnit || baseUnit;
    return raw ? ` ${raw}` : '';
  })();

  const qtyText = (baseQty: number) => `${formatQuantity(toDisplay(baseQty))}${unitSuffix}`;

  const operationQualified =
    Number(operation?.qualified_quantity ?? operation?.qualifiedQuantity ?? 0) || 0;

  const cumulativeLoss = useMemo(
    () => getWorkOrderMaterialLossTotal(operations),
    [operations],
  );

  const { data: replenishmentQty = 0 } = useQuery({
    queryKey: ['woReplenishmentQty', workOrderId],
    enabled: workOrderId != null,
    queryFn: async () => {
      const res = await warehouseApi.materialCall.list({ work_order_id: workOrderId, limit: 200 });
      const rows = Array.isArray(res) ? res : (res as any)?.data ?? (res as any)?.items ?? [];
      return rows
        .filter(
          (c: any) =>
            String(c.call_reason ?? '') === 'SCRAP_REPLENISH' &&
            String(c.status ?? '') !== 'cancelled',
        )
        .reduce((sum: number, c: any) => sum + (Number(c.delivered_quantity) || 0), 0);
    },
    staleTime: 0,
  });

  const statTitleStyle: React.CSSProperties = {
    fontSize: 11,
    color: token.colorTextSecondary,
    fontWeight: 400,
    whiteSpace: 'nowrap',
  };
  const statValueStyle: React.CSSProperties = {
    color: token.colorText,
    fontSize: 18,
    fontWeight: 600,
    lineHeight: 1.2,
  };

  type Metric = {
    key: string;
    title: string;
    value: number | string;
    valueStyle?: React.CSSProperties;
    emphasis?: boolean;
  };

  const primaryMetrics: Metric[] = [
    {
      key: 'plan',
      title: t('apps.kuaizhizao.workOrder.quickReport.workOrderPlanQty'),
      value: qtyText(workOrderQuantity),
    },
    {
      key: 'standard',
      title: t('apps.kuaizhizao.workOrder.quickReport.standardReportableQty'),
      value: qtyText(standardPlanRemaining),
      valueStyle: { color: token.colorTextHeading },
    },
    {
      key: 'over',
      title: t('apps.kuaizhizao.workOrder.quickReport.overReportableQty'),
      value: overReportRemaining > 0 ? qtyText(overReportRemaining) : `0${unitSuffix}`,
      valueStyle: {
        color: overReportRemaining > 0 ? token.colorWarning : token.colorTextTertiary,
      },
    },
    {
      key: 'materialRemaining',
      title: t('apps.kuaizhizao.workOrder.quickReport.materialRemainingTitle'),
      value:
        materialRemaining == null ? '—' : qtyText(materialRemaining),
    },
    {
      key: 'effective',
      title: t('apps.kuaizhizao.workOrder.quickReport.effectiveReportableTitle'),
      value: qtyText(effectiveRemaining),
      valueStyle: { color: token.colorPrimary, fontSize: 20 },
      emphasis: true,
    },
  ];

  const secondaryMetrics: Metric[] = [
    {
      key: 'qualified',
      title: t('apps.kuaizhizao.workOrder.quickReport.reportedQualifiedQty'),
      value: qtyText(operationQualified),
    },
    {
      key: 'loss',
      title: t('apps.kuaizhizao.workOrder.quickReport.cumulativeMaterialLoss'),
      value: qtyText(cumulativeLoss),
      valueStyle: {
        color: cumulativeLoss > 0 ? token.colorError : token.colorTextTertiary,
      },
    },
    {
      key: 'replenish',
      title: t('apps.kuaizhizao.workOrder.quickReport.replenishmentQty'),
      value: qtyText(replenishmentQty),
      valueStyle: {
        color: replenishmentQty > 0 ? token.colorWarning : token.colorTextTertiary,
      },
    },
  ];

  const renderMetricRow = (items: Metric[]) => (
    <Row gutter={[12, 8]} wrap align="top">
      {items.map((m) => (
        <Col key={m.key} flex={m.emphasis ? '1.15 1 120px' : '1 1 88px'} style={{ minWidth: 0 }}>
          <Statistic
            title={<span style={statTitleStyle}>{m.title}</span>}
            value={m.value}
            styles={{ content: { ...statValueStyle, ...m.valueStyle } }}
          />
        </Col>
      ))}
    </Row>
  );

  return (
    <div
      style={{
        padding: '12px 14px',
        borderRadius: token.borderRadiusLG,
        background: token.colorFillAlter,
        border: `1px solid ${token.colorBorderSecondary}`,
      }}
    >
      {renderMetricRow(primaryMetrics)}
      <div style={{ marginTop: 10 }}>{renderMetricRow(secondaryMetrics)}</div>
      {planRemaining > effectiveRemaining + 1e-9 ? (
        <Typography.Text type="secondary" style={{ display: 'block', marginTop: 10, fontSize: 12 }}>
          {t('apps.kuaizhizao.workOrder.quickReport.effectiveCappedByMaterialHint')}
        </Typography.Text>
      ) : null}
    </div>
  );
};

export default ReportableQuantityPanel;