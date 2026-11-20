import React, { useEffect, useState } from 'react';
import { Alert, Drawer, Empty, Spin, Table, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { visualSchedulingApi } from '../../../../services/production';
import { MarkerTag } from '../../../../../../constants/statusBadges';
import { DRAWER_CONFIG } from '../../../../../../components/layout-templates';

interface DueEstimateRow {
  work_order_id: number;
  work_order_code?: string | null;
  expected_date?: string | null;
  committed_date?: string | null;
  estimated_date?: string | null;
  variance_days?: number | null;
  status?: string | null;
}

interface SchedulingDueEstimateDrawerProps {
  open: boolean;
  workOrderIds: number[];
  onClose: () => void;
}

const SchedulingDueEstimateDrawer: React.FC<SchedulingDueEstimateDrawerProps> = ({
  open,
  workOrderIds,
  onClose,
}) => {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<DueEstimateRow[]>([]);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (workOrderIds.length === 0) {
      setRows([]);
      setGeneratedAt(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void visualSchedulingApi
      .dueEstimate(workOrderIds.slice(0, 100))
      .then((res) => {
        if (cancelled) return;
        setRows(res.items ?? []);
        setGeneratedAt(res.generated_at ?? null);
      })
      .catch((e: { message?: string }) => {
        if (cancelled) return;
        setRows([]);
        setGeneratedAt(null);
        setError(e?.message || t('app.kuaizhizao.scheduling.dueEstimate.loadFailed'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, t, workOrderIds]);

  return (
    <Drawer
      title={t('app.kuaizhizao.scheduling.dueEstimate.title')}
      open={open}
      onClose={onClose}
      size={DRAWER_CONFIG.HALF_WIDTH}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        {t('app.kuaizhizao.scheduling.dueEstimate.hint')}
        {generatedAt ? ` ${t('app.kuaizhizao.scheduling.dueEstimate.generatedAt', { time: generatedAt })}` : ''}
      </Typography.Paragraph>
      {error ? (
        <Alert type="error" showIcon style={{ marginBottom: 12 }} title={error} />
      ) : null}
      {loading ? (
        <Spin description={t('common.loading')} />
      ) : error ? null : rows.length === 0 ? (
        <Empty description={t('app.kuaizhizao.scheduling.dueEstimate.empty')} />
      ) : (
        <Table
          size="small"
          rowKey="work_order_id"
          pagination={false}
          dataSource={rows}
          columns={[
            {
              title: t('app.kuaizhizao.scheduling.dueEstimate.colCode'),
              dataIndex: 'work_order_code',
              width: 140,
              render: (v, r) => v || r.work_order_id,
            },
            {
              title: t('app.kuaizhizao.scheduling.dueEstimate.colExpected'),
              dataIndex: 'expected_date',
              width: 160,
              render: (v) => v || '-',
            },
            {
              title: t('app.kuaizhizao.scheduling.dueEstimate.colCommitted'),
              dataIndex: 'committed_date',
              width: 160,
              render: (v) => v || '-',
            },
            {
              title: t('app.kuaizhizao.scheduling.dueEstimate.colEstimated'),
              dataIndex: 'estimated_date',
              width: 160,
              render: (v) => v || '-',
            },
            {
              title: t('app.kuaizhizao.scheduling.dueEstimate.colVariance'),
              dataIndex: 'variance_days',
              width: 100,
              render: (v: number | null | undefined) => {
                if (v == null) return '-';
                const late = v > 0;
                const early = v < 0;
                return (
                  <MarkerTag color={late ? 'error' : early ? 'success' : 'default'} variant="filled">
                    {late
                      ? t('app.kuaizhizao.scheduling.dueEstimate.lateDays', { days: v })
                      : early
                        ? t('app.kuaizhizao.scheduling.dueEstimate.earlyDays', { days: Math.abs(v) })
                        : t('app.kuaizhizao.scheduling.dueEstimate.onTime')}
                  </MarkerTag>
                );
              },
            },
          ]}
        />
      )}
    </Drawer>
  );
};

export default SchedulingDueEstimateDrawer;
