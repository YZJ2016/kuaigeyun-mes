import React, { useMemo } from 'react';
import { Empty, Table, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import type { VisualSchedulingBoardScan } from '../../../../services/production';
import { MarkerTag } from '../../../../../../constants/statusBadges';

export type SchedulingAlertSeverity = 'high' | 'medium' | 'low';

export interface SchedulingAlertRow {
  key: string;
  severity: SchedulingAlertSeverity;
  category: string;
  message: string;
  workOrderId?: number;
  workOrderCode?: string;
}

interface SchedulingAlertsPanelProps {
  boardScan: VisualSchedulingBoardScan | null | undefined;
  onOpenWorkOrder?: (workOrderId: number) => void;
}

function severityRank(s: SchedulingAlertSeverity): number {
  if (s === 'high') return 0;
  if (s === 'medium') return 1;
  return 2;
}

const SchedulingAlertsPanel: React.FC<SchedulingAlertsPanelProps> = ({
  boardScan,
  onOpenWorkOrder,
}) => {
  const { t } = useTranslation();

  const rows = useMemo<SchedulingAlertRow[]>(() => {
    if (!boardScan) return [];
    const out: SchedulingAlertRow[] = [];

    for (const c of boardScan.conflicts ?? []) {
      out.push({
        key: `conflict-${c.work_order_id ?? ''}-${c.operation_id ?? ''}-${c.type}-${c.message}`,
        severity: 'high',
        category: t('app.kuaizhizao.scheduling.alerts.categoryConflict'),
        message: c.message || c.type || '',
        workOrderId: c.work_order_id ?? undefined,
        workOrderCode: c.work_order_code ?? undefined,
      });
    }
    for (const m of boardScan.material_issues ?? []) {
      out.push({
        key: `material-${m.work_order_id}-${m.message}`,
        severity: 'high',
        category: t('app.kuaizhizao.scheduling.alerts.categoryMaterial'),
        message: m.message || '',
        workOrderId: m.work_order_id,
        workOrderCode: m.work_order_code ?? undefined,
      });
    }
    for (const u of boardScan.unscheduled_orders ?? []) {
      out.push({
        key: `unscheduled-${u.work_order_id}`,
        severity: 'medium',
        category: t('app.kuaizhizao.scheduling.alerts.categoryUnscheduled'),
        message: u.reason || t('app.kuaizhizao.scheduling.alerts.unscheduledDefault'),
        workOrderId: u.work_order_id,
        workOrderCode: u.work_order_code ?? undefined,
      });
    }
    for (const s of boardScan.missing_settings ?? []) {
      out.push({
        key: `missing-${s.work_order_id}-${s.operation_id ?? ''}-${s.field}`,
        severity: 'medium',
        category: t('app.kuaizhizao.scheduling.alerts.categoryMissing'),
        message: s.label || s.field,
        workOrderId: s.work_order_id,
        workOrderCode: s.work_order_code ?? undefined,
      });
    }
    for (const load of boardScan.load_by_station ?? []) {
      if (!load.overloaded && Number(load.rate ?? 0) <= 1) continue;
      out.push({
        key: `overload-station-${load.station_id}-${load.day ?? ''}`,
        severity: 'low',
        category: t('app.kuaizhizao.scheduling.alerts.categoryOverload'),
        message: t('app.kuaizhizao.scheduling.alerts.overloadStation', {
          name: load.station_name || load.station_id,
          rate: Math.round(Number(load.rate ?? 0) * 100),
        }),
      });
    }
    for (const load of boardScan.load_by_work_center ?? []) {
      if (!load.overloaded && Number(load.rate ?? 0) <= 1) continue;
      out.push({
        key: `overload-wc-${load.work_center_id}-${load.day ?? ''}`,
        severity: 'low',
        category: t('app.kuaizhizao.scheduling.alerts.categoryOverload'),
        message: t('app.kuaizhizao.scheduling.alerts.overloadWorkCenter', {
          name: load.work_center_name || load.work_center_id,
          rate: Math.round(Number(load.rate ?? 0) * 100),
        }),
      });
    }

    return out.sort((a, b) => severityRank(a.severity) - severityRank(b.severity));
  }, [boardScan, t]);

  if (!boardScan) {
    return <Empty description={t('app.kuaizhizao.scheduling.alerts.emptyScan')} />;
  }
  if (rows.length === 0) {
    return <Empty description={t('app.kuaizhizao.scheduling.alerts.empty')} />;
  }

  return (
    <div className="aps-alerts-panel">
      <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>
        {t('app.kuaizhizao.scheduling.alerts.hint', { count: rows.length })}
      </Typography.Paragraph>
      <Table
        size="small"
        rowKey="key"
        pagination={{ pageSize: 20, showSizeChanger: false }}
        dataSource={rows}
        columns={[
          {
            title: t('app.kuaizhizao.scheduling.alerts.colSeverity'),
            dataIndex: 'severity',
            width: 88,
            render: (v: SchedulingAlertSeverity) => (
              <MarkerTag
                color={v === 'high' ? 'error' : v === 'medium' ? 'warning' : 'default'}
                variant="filled"
              >
                {t(`app.kuaizhizao.scheduling.alerts.severity.${v}`)}
              </MarkerTag>
            ),
          },
          {
            title: t('app.kuaizhizao.scheduling.alerts.colCategory'),
            dataIndex: 'category',
            width: 120,
          },
          {
            title: t('app.kuaizhizao.scheduling.alerts.colWorkOrder'),
            dataIndex: 'workOrderCode',
            width: 140,
            render: (code: string | undefined, row) =>
              row.workOrderId && onOpenWorkOrder ? (
                <Typography.Link onClick={() => onOpenWorkOrder(row.workOrderId!)}>
                  {code || row.workOrderId}
                </Typography.Link>
              ) : (
                code || '-'
              ),
          },
          {
            title: t('app.kuaizhizao.scheduling.alerts.colMessage'),
            dataIndex: 'message',
            ellipsis: true,
          },
        ]}
      />
    </div>
  );
};

export default SchedulingAlertsPanel;
