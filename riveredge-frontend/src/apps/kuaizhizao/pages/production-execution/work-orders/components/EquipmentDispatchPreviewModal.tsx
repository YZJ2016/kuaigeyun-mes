import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Button,
  DatePicker,
  Descriptions,
  Modal,
  Result,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import { LinkOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { MODAL_CONFIG } from '../../../../../../components/layout-templates';
import { equipmentApi, equipmentStatusApi } from '../../../../services/equipment';
import {
  type EquipmentTraceData,
  useEquipmentTraceColumns,
} from '../../../equipment-management/equipment/equipmentTraceTabs';
import { renderMasterActiveTag } from '../../../../../master-data/utils/masterListPresentation';
import { formatDateTimeBySiteSetting } from '../../../../../../utils/format';
import { renderDocumentStatusTag } from '../../../../../../utils/documentLifecycleStatusTag';

export interface EquipmentDispatchPreviewModalProps {
  open: boolean;
  onClose: () => void;
  equipmentUuid: string | null;
  equipmentCode?: string;
  equipmentName?: string;
}

type AssignedOperationRow = {
  work_order_id: number;
  work_order_code: string;
  product_name: string;
  work_order_status: string;
  operation_id: number;
  operation_name: string;
  operation_status: string;
  assigned_worker_name?: string | null;
  planned_start_at?: string | null;
  planned_end_at?: string | null;
  updated_at?: string | null;
};

type TracePayload = EquipmentTraceData & {
  assigned_operations?: AssignedOperationRow[];
};

function isOpenFaultStatus(status: unknown): boolean {
  const raw = String(status ?? '').trim();
  if (!raw) {
    return false;
  }
  return raw !== '已完成' && raw !== 'completed' && raw !== 'closed' && raw !== '已关闭';
}

function isOpenMaintenancePlanStatus(status: unknown): boolean {
  const raw = String(status ?? '').trim();
  if (!raw) {
    return false;
  }
  return raw !== '已完成' && raw !== 'completed' && raw !== 'closed' && raw !== '已关闭';
}

const EquipmentDispatchPreviewModal: React.FC<EquipmentDispatchPreviewModalProps> = ({
  open,
  onClose,
  equipmentUuid,
  equipmentCode,
  equipmentName,
}) => {
  const { t } = useTranslation();
  const traceColumns = useEquipmentTraceColumns(t, {}, false);

  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(30, 'day'),
    dayjs(),
  ]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [trace, setTrace] = useState<TracePayload | null>(null);
  const [latestStatus, setLatestStatus] = useState<{ status?: string; is_online?: boolean; monitored_at?: string } | null>(
    null,
  );

  const loadData = useCallback(async () => {
    if (!equipmentUuid) {
      return;
    }
    const dateFrom = dateRange[0].format('YYYY-MM-DD');
    const dateTo = dateRange[1].format('YYYY-MM-DD');
    setLoading(true);
    setLoadError(null);
    try {
      const [traceRes, statusRes] = await Promise.all([
        equipmentApi.getTrace(equipmentUuid, { date_from: dateFrom, date_to: dateTo }),
        equipmentStatusApi.getLatestStatus(equipmentUuid).catch((err: unknown) => {
          const status = (err as { status?: number })?.status;
          if (status === 404 || status === 403) {
            return null;
          }
          throw err;
        }),
      ]);
      setTrace(traceRes as TracePayload);
      setLatestStatus(statusRes as typeof latestStatus);
    } catch (err: unknown) {
      const status = (err as { status?: number; message?: string })?.status;
      const detail = (err as { message?: string })?.message;
      if (status === 403) {
        setLoadError(t('app.kuaizhizao.workOrder.equipmentDispatchPreview.forbidden'));
      } else {
        setLoadError(detail || t('app.kuaizhizao.equipment.getTraceFailed'));
      }
      setTrace(null);
      setLatestStatus(null);
    } finally {
      setLoading(false);
    }
  }, [dateRange, equipmentUuid, t]);

  useEffect(() => {
    if (open && equipmentUuid) {
      void loadData();
    }
    if (!open) {
      setTrace(null);
      setLatestStatus(null);
      setLoadError(null);
    }
  }, [open, equipmentUuid, loadData]);

  const displayCode = trace?.equipment?.code ?? equipmentCode ?? '';
  const displayName = trace?.equipment?.name ?? equipmentName ?? '';

  const summaryAlerts = useMemo(() => {
    if (!trace) {
      return [];
    }
    const alerts: string[] = [];
    const openFaults = (trace.equipment_faults ?? []).filter((f) => isOpenFaultStatus(f.status));
    if (openFaults.length > 0) {
      alerts.push(t('app.kuaizhizao.workOrder.equipmentDispatchPreview.alertOpenFaults', { count: openFaults.length }));
    }
    const openPlans = (trace.maintenance_plans ?? []).filter((p) => isOpenMaintenancePlanStatus(p.status));
    if (openPlans.length > 0) {
      alerts.push(
        t('app.kuaizhizao.workOrder.equipmentDispatchPreview.alertOpenMaintenance', { count: openPlans.length }),
      );
    }
    return alerts;
  }, [t, trace]);

  const assignedOperationColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.colWorkOrderCode'),
        dataIndex: 'work_order_code',
        width: 140,
      },
      {
        title: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.colProductName'),
        dataIndex: 'product_name',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.colWorkOrderStatus'),
        dataIndex: 'work_order_status',
        width: 110,
        render: (v: string) => renderDocumentStatusTag(v, v),
      },
      {
        title: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.colOperationName'),
        dataIndex: 'operation_name',
        width: 140,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.colOperationStatus'),
        dataIndex: 'operation_status',
        width: 100,
        render: (v: string) => <Tag>{v || '-'}</Tag>,
      },
      {
        title: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.colAssignedWorker'),
        dataIndex: 'assigned_worker_name',
        width: 120,
        ellipsis: true,
        render: (v: string | null) => v || '-',
      },
      {
        title: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.colPlannedStart'),
        dataIndex: 'planned_start_at',
        width: 160,
        render: (v: string) => formatDateTimeBySiteSetting(v),
      },
      {
        title: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.colPlannedEnd'),
        dataIndex: 'planned_end_at',
        width: 160,
        render: (v: string) => formatDateTimeBySiteSetting(v),
      },
      {
        title: t('common.updatedAt'),
        dataIndex: 'updated_at',
        width: 160,
        render: (v: string) => formatDateTimeBySiteSetting(v),
      },
    ],
    [t],
  );

  const tabItems = useMemo(() => {
    if (!trace) {
      return [];
    }
    const eq = trace.equipment;
    return [
      {
        key: 'overview',
        label: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.tabOverview'),
        children: (
          <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
            {summaryAlerts.map((text) => (
              <Alert key={text} type="warning" title={text} showIcon />
            ))}
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label={t('app.kuaizhizao.equipment.colLifecycle')}>
                {eq?.status || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('common.enabled')}>
                {renderMasterActiveTag(t, eq?.is_active, 'common.enabled', 'common.disabled')}
              </Descriptions.Item>
              {latestStatus ? (
                <>
                  <Descriptions.Item label={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.realtimeStatus')}>
                    {latestStatus.status || '-'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.monitoredAt')}>
                    {formatDateTimeBySiteSetting(latestStatus.monitored_at)}
                  </Descriptions.Item>
                </>
              ) : (
                <Descriptions.Item label={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.realtimeStatus')} span={2}>
                  {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.noRealtimeStatus')}
                </Descriptions.Item>
              )}
            </Descriptions>
          </Space>
        ),
      },
      {
        key: 'maintenance',
        label: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.tabMaintenance'),
        children: (
          <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
            <Typography.Text strong>{t('app.kuaizhizao.workOrder.equipmentDispatchPreview.sectionMaintenancePlans')}</Typography.Text>
            <Table
              dataSource={trace.maintenance_plans ?? []}
              columns={traceColumns.traceMaintenancePlanColumns}
              rowKey="uuid"
              pagination={false}
              size="small"
              scroll={{ x: true }}
            />
            <Typography.Text strong>{t('app.kuaizhizao.workOrder.equipmentDispatchPreview.sectionMaintenanceExecutions')}</Typography.Text>
            <Table
              dataSource={trace.maintenance_executions ?? []}
              columns={traceColumns.traceMaintenanceExecutionColumns}
              rowKey="uuid"
              pagination={false}
              size="small"
              scroll={{ x: true }}
            />
          </Space>
        ),
      },
      {
        key: 'spot_checks',
        label: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.tabSpotCheck'),
        children: (
          <Table
            dataSource={trace.spot_checks ?? []}
            columns={traceColumns.traceSpotCheckColumns}
            rowKey="id"
            pagination={false}
            size="small"
            scroll={{ x: true }}
          />
        ),
      },
      {
        key: 'assigned_operations',
        label: t('app.kuaizhizao.workOrder.equipmentDispatchPreview.tabAssignedWorkOrders', {
          count: trace.assigned_operations?.length ?? 0,
        }),
        children: (
          <Table
            dataSource={trace.assigned_operations ?? []}
            columns={assignedOperationColumns}
            rowKey="operation_id"
            pagination={false}
            size="small"
            scroll={{ x: true }}
          />
        ),
      },
    ];
  }, [assignedOperationColumns, latestStatus, summaryAlerts, t, trace, traceColumns]);

  const detailHref = equipmentUuid
    ? `/apps/kuaizhizao/equipment-management/equipment/${equipmentUuid}`
    : undefined;

  return (
    <Modal
      title={t('app.kuaizhizao.workOrder.equipmentDispatchPreview.title', {
        code: displayCode,
        name: displayName,
      })}
      open={open}
      onCancel={onClose}
      footer={null}
      width={MODAL_CONFIG.LARGE_WIDTH}
      destroyOnHidden
      mask={{ closable: true }}
    >
      <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
        <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
          <DatePicker.RangePicker
            value={dateRange}
            onChange={(vals) => {
              if (vals?.[0] && vals[1]) {
                setDateRange([vals[0], vals[1]]);
              }
            }}
            allowClear={false}
          />
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void loadData()} loading={loading}>
              {t('common.refresh')}
            </Button>
            {detailHref ? (
              <Button type="link" href={detailHref} target="_blank" rel="noopener noreferrer" icon={<LinkOutlined />}>
                {t('app.kuaizhizao.workOrder.equipmentDispatchPreview.openEquipmentDetail')}
              </Button>
            ) : null}
          </Space>
        </Space>

        {loadError ? (
          <Result
            status="error"
            title={loadError}
            extra={
              <Button type="primary" onClick={() => void loadData()}>
                {t('common.retry')}
              </Button>
            }
          />
        ) : (
          <Spin spinning={loading}>
            {trace ? <Tabs items={tabItems} /> : null}
          </Spin>
        )}
      </Space>
    </Modal>
  );
};

export default EquipmentDispatchPreviewModal;
