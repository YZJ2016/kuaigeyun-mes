import React, { useMemo, useState } from 'react';
import { ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import KuaizhizaoReport from '../../../components/KuaizhizaoReport';
import { ThemedSegmented } from '../../../../../components/themed-segmented';

/** 呆滞判定：批次 updated_at 早于「今天 − N 天」 */
type StaleDays = 7 | 14 | 30 | 60 | 90;

const STALE_DAY_OPTIONS: StaleDays[] = [7, 14, 30, 60, 90];

const SlowMovingInventory: React.FC = () => {
  const { t } = useTranslation();
  const [staleDays, setStaleDays] = useState<StaleDays>(7);

  const columns: ProColumns[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.warehouseReports.colMaterialCode'),
        dataIndex: 'material_code',
        width: 120,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.warehouseReports.colMaterialName'),
        dataIndex: 'material_name',
        ellipsis: true,
        width: 180,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.warehouseReports.colBatchNo'),
        dataIndex: 'batch_no',
        width: 140,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.warehouseCommon.colSerialNo'),
        dataIndex: 'serial_no',
        width: 100,
        hideInSearch: true,
        render: (v: unknown) => (v != null && String(v).trim() ? String(v) : '—'),
      },
      {
        title: t('app.kuaizhizao.warehouseReports.colStockQty'),
        dataIndex: 'quantity',
        valueType: 'digit',
        width: 100,
        hideInSearch: true,
        align: 'right',
      },
      {
        title: t('app.kuaizhizao.warehouseReports.colLastMoveDate'),
        dataIndex: 'last_move_date',
        valueType: 'date',
        width: 120,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.warehouseReports.colAgeDays'),
        dataIndex: 'age_days',
        valueType: 'digit',
        width: 100,
        hideInSearch: true,
        align: 'right',
        sorter: true,
      },
    ],
    [t],
  );

  const staleOptions = useMemo(
    () =>
      STALE_DAY_OPTIONS.map((value) => ({
        value,
        label: t('app.kuaizhizao.warehouseReports.staleDaysOption', { days: value }),
      })),
    [t],
  );

  return (
    <KuaizhizaoReport
      title={t('app.kuaizhizao.menu.reports.slow-moving-inventory')}
      reportType="slow_moving"
      columns={columns}
      columnPersistenceId="apps.kuaizhizao.pages.warehouse-management.reports.SlowMovingInventory-v3"
      summaryFields={['quantity']}
      params={{ stale_days: staleDays }}
      beforeSearchButtons={
        <ThemedSegmented
          surfaceBackground
          size="medium"
          value={staleDays}
          onChange={(value) => setStaleDays(value as StaleDays)}
          options={staleOptions}
        />
      }
    />
  );
};

export default SlowMovingInventory;
