import React, { useMemo } from 'react';
import { Empty, Progress, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import type { GanttTaskLevel } from '../../../../components/GanttSchedulingChart/types';
import {
  buildSchedulingLoadTableRows,
  type SchedulingLoadTableRow,
} from '../schedulingLoadTableUtils';
import type { VisualSchedulingBoardScan } from '../../../../services/production';
import type { WorkOrderForGantt } from '../../../../components/GanttSchedulingChart/types';

interface SchedulingLoadTableProps {
  t: TFunction;
  boardScan: VisualSchedulingBoardScan | null | undefined;
  taskLevel: GanttTaskLevel;
  horizonDays: number;
  workOrders: WorkOrderForGantt[];
  pinnedResourceIds?: number[];
  showPinnedOnly?: boolean;
  loading?: boolean;
}

export default function SchedulingLoadTable({
  t,
  boardScan,
  taskLevel,
  horizonDays,
  workOrders,
  pinnedResourceIds = [],
  showPinnedOnly = false,
  loading = false,
}: SchedulingLoadTableProps) {
  const rows = useMemo(() => {
    const all = buildSchedulingLoadTableRows(boardScan, taskLevel, horizonDays, workOrders);
    if (!showPinnedOnly || pinnedResourceIds.length === 0) return all;
    const pinned = new Set(pinnedResourceIds);
    return all.filter((row) => pinned.has(row.resourceId));
  }, [boardScan, horizonDays, pinnedResourceIds, showPinnedOnly, taskLevel, workOrders]);

  const columns: ColumnsType<SchedulingLoadTableRow> = [
    {
      title: t('app.kuaizhizao.scheduling.loadTable.columnResource'),
      dataIndex: 'resourceName',
      key: 'resourceName',
      ellipsis: true,
    },
    {
      title: t('app.kuaizhizao.scheduling.loadTable.columnScheduledHours'),
      dataIndex: 'scheduledHours',
      key: 'scheduledHours',
      width: 110,
      align: 'right',
      render: (value: number) => value.toFixed(1),
    },
    {
      title: t('app.kuaizhizao.scheduling.loadTable.columnAvailableHours'),
      dataIndex: 'availableHours',
      key: 'availableHours',
      width: 110,
      align: 'right',
      render: (value: number) => value.toFixed(1),
    },
    {
      title: t('app.kuaizhizao.scheduling.loadTable.columnLoadRate'),
      dataIndex: 'loadRate',
      key: 'loadRate',
      width: 160,
      render: (rate: number, record) => (
        <div className="scheduling-load-table__rate">
          <Progress
            percent={Math.min(rate, 100)}
            size="small"
            status={record.overloaded ? 'exception' : rate >= 85 ? 'active' : 'normal'}
            format={() => `${rate}%`}
          />
        </div>
      ),
    },
    {
      title: t('app.kuaizhizao.scheduling.loadTable.columnOverloaded'),
      dataIndex: 'overloaded',
      key: 'overloaded',
      width: 88,
      align: 'center',
      render: (overloaded: boolean) =>
        overloaded ? (
          <Tag color="error" variant="filled">
            {t('app.kuaizhizao.scheduling.loadTable.overloadedYes')}
          </Tag>
        ) : (
          <Tag variant="filled">{t('app.kuaizhizao.scheduling.loadTable.overloadedNo')}</Tag>
        ),
    },
    {
      title: t('app.kuaizhizao.scheduling.loadTable.columnWorkOrders'),
      dataIndex: 'workOrderCount',
      key: 'workOrderCount',
      width: 96,
      align: 'right',
    },
    {
      title: t('app.kuaizhizao.scheduling.loadTable.columnOnMachine'),
      dataIndex: 'onMachineCount',
      key: 'onMachineCount',
      width: 88,
      align: 'right',
      render: (count: number) =>
        count > 0 ? (
          <Typography.Text type="success">{count}</Typography.Text>
        ) : (
          count
        ),
    },
  ];

  if (taskLevel === 'worker' || taskLevel === 'work_order' || taskLevel === 'operation') {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t('app.kuaizhizao.scheduling.loadTable.unsupportedLevel')}
        style={{ padding: '48px 0' }}
      />
    );
  }

  return (
    <Table<SchedulingLoadTableRow>
      className="scheduling-load-table"
      size="small"
      rowKey={(row) => `${taskLevel}-${row.resourceId}`}
      loading={loading}
      pagination={false}
      scroll={{ y: 'calc(100vh - 320px)' }}
      columns={columns}
      dataSource={rows}
      locale={{
        emptyText: (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={t('app.kuaizhizao.scheduling.loadTable.empty')}
          />
        ),
      }}
    />
  );
}
