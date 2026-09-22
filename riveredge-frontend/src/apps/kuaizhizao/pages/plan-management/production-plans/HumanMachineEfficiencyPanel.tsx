import React, { useMemo, useState } from 'react';
import { Card, Col, Empty, Row, Segmented, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import { useDashboardRequest } from '../../../utils/dashboardRequestOptions';
import { apiRequest } from '../../../../../services/api';

type HumanMachineTrendPoint = {
  period: string;
  equipment_utilization_rate: number;
  worker_report_hours: number;
};

type HumanMachineWorkerRankingItem = {
  worker_id: number;
  worker_name: string;
  report_hours: number;
};

type HumanMachineEfficiencySummary = {
  days: number;
  equipment_utilization_rate: number;
  worker_report_hours: number;
  trend: HumanMachineTrendPoint[];
  worker_ranking: HumanMachineWorkerRankingItem[];
};

export default function HumanMachineEfficiencyPanel() {
  const { t } = useTranslation();
  const [days, setDays] = useState<7 | 30>(7);
  const { data, loading } = useDashboardRequest(
    () =>
      apiRequest<HumanMachineEfficiencySummary>(
        '/apps/kuaizhizao/production-control/human-machine-efficiency',
        { method: 'GET', params: { days } }
      ),
    `kz:plan-dashboard:human-machine-${days}`,
    { refreshDeps: [days], pollingInterval: 60000 }
  );

  const rankingColumns: ColumnsType<HumanMachineWorkerRankingItem> = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.planControlTower.humanMachine.workerName'),
        dataIndex: 'worker_name',
        key: 'worker_name',
      },
      {
        title: t('app.kuaizhizao.planControlTower.humanMachine.reportHours'),
        dataIndex: 'report_hours',
        key: 'report_hours',
        align: 'right',
        render: (value: number) => value.toFixed(1),
      },
    ],
    [t]
  );

  const trendColumns: ColumnsType<HumanMachineTrendPoint> = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.planControlTower.humanMachine.period'),
        dataIndex: 'period',
        key: 'period',
      },
      {
        title: t('app.kuaizhizao.planControlTower.humanMachine.equipmentUtilization'),
        dataIndex: 'equipment_utilization_rate',
        key: 'equipment_utilization_rate',
        align: 'right',
        render: (value: number) => `${value.toFixed(1)}%`,
      },
      {
        title: t('app.kuaizhizao.planControlTower.humanMachine.workerHours'),
        dataIndex: 'worker_report_hours',
        key: 'worker_report_hours',
        align: 'right',
        render: (value: number) => value.toFixed(1),
      },
    ],
    [t]
  );

  return (
    <Card
      title={t('app.kuaizhizao.planControlTower.humanMachine.title')}
      extra={
        <Segmented
          size="small"
          value={days}
          options={[
            { label: t('app.kuaizhizao.planControlTower.humanMachine.days7'), value: 7 },
            { label: t('app.kuaizhizao.planControlTower.humanMachine.days30'), value: 30 },
          ]}
          onChange={(value) => setDays(value as 7 | 30)}
        />
      }
    >
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card size="small" variant="borderless" style={{ background: '#f7f8fa' }}>
            <Typography.Text type="secondary">
              {t('app.kuaizhizao.planControlTower.humanMachine.equipmentAvg')}
            </Typography.Text>
            <div style={{ fontSize: 28, fontWeight: 600 }}>
              {(data?.equipment_utilization_rate ?? 0).toFixed(1)}%
            </div>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card size="small" variant="borderless" style={{ background: '#f7f8fa' }}>
            <Typography.Text type="secondary">
              {t('app.kuaizhizao.planControlTower.humanMachine.workerTotal')}
            </Typography.Text>
            <div style={{ fontSize: 28, fontWeight: 600 }}>
              {(data?.worker_report_hours ?? 0).toFixed(1)}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={14}>
          <Typography.Text strong>{t('app.kuaizhizao.planControlTower.humanMachine.trendTitle')}</Typography.Text>
          <Table<HumanMachineTrendPoint>
            size="small"
            style={{ marginTop: 8 }}
            rowKey="period"
            loading={loading}
            pagination={false}
            scroll={{ y: 240 }}
            columns={trendColumns}
            dataSource={data?.trend ?? []}
            locale={{
              emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />,
            }}
          />
        </Col>
        <Col xs={24} lg={10}>
          <Typography.Text strong>{t('app.kuaizhizao.planControlTower.humanMachine.rankingTitle')}</Typography.Text>
          <Table<HumanMachineWorkerRankingItem>
            size="small"
            style={{ marginTop: 8 }}
            rowKey="worker_id"
            loading={loading}
            pagination={false}
            columns={rankingColumns}
            dataSource={data?.worker_ranking ?? []}
            locale={{
              emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('common.noData')} />,
            }}
          />
        </Col>
      </Row>
    </Card>
  );
}
