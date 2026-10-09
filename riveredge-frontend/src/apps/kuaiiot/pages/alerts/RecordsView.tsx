import { alignIotTableColumns } from '../../components/table-parity';
/**
 * 告警记录视图：入站告警的查询、确认 / 处置（关闭）与软删除。
 * 状态机与后端 alert_service.transition_alert 一致：
 * - 已写入 acknowledged_at 或 status=closed 的记录不可再确认；
 * - status=closed 为终态，不可再处置；不提供任何「重开」入口。
 * 权限码与后端一致：读 = kuaiiot:alert:display，全部写操作 = kuaiiot:alert:create。
 */

import React, { useMemo, useRef, useState } from 'react';
import { App, Button, Descriptions, Popconfirm } from 'antd';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import dayjs from 'dayjs';
import { UniTable } from '../../../../components/uni-table';
import { UniBatchDeleteButton } from '../../../../components/uni-batch';
import { rowActionKind, rowActionToneDestructive } from '../../../../components/uni-action';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../utils/uniTableLayoutColumns';
import { DetailDrawerTemplate, DRAWER_CONFIG } from '../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import {
  filterRowsByListKeyword,
  pickListSearchKeyword,
  pickSearchDateTimeRange,
  pickSearchString,
} from '../../../../utils/tableQueryKey';
import { formatDateTimeBySiteSetting } from '../../../../utils/format';
import {
  deleteAlert,
  listAlertRules,
  listAlerts,
  transitionAlert,
} from '../../services/kuaiiot';
import { AlertStatusTag, SeverityTag } from '../../components/status-tags';
import {
  ALERT_SEVERITY_OPTIONS,
  ALERT_STATUS_OPTIONS,
  deleteRowsInSequence,
  deviceLabel,
  loadDeviceLabelMap,
  type AlertRecordRow,
  type DeviceLabelMap,
} from './api';

function formatTime(value?: string | null): string {
  if (!value) return '—';
  return formatDateTimeBySiteSetting(value) || '—';
}

export default function RecordsView() {
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions('kuaiiot:alert');
  const canWrite = perms.canCreate;
  const canDisplay = perms.canAction?.('display') ?? false;

  const actionRef = useRef<ActionType>();
  const pageRowsRef = useRef<AlertRecordRow[]>([]);
  const [deviceMap, setDeviceMap] = useState<DeviceLabelMap>(new Map());
  const [ruleMap, setRuleMap] = useState<Map<number, string>>(new Map());
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<AlertRecordRow | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [batchBusy, setBatchBusy] = useState(false);

  const rowBusy = (id: number, action: string) => busyKey === `${id}:${action}`;

  const handleTransition = async (row: AlertRecordRow, action: 'acknowledge' | 'close') => {
    const key = `${row.id}:${action}`;
    if (busyKey) return;
    setBusyKey(key);
    try {
      const updated = await transitionAlert(row.id, action);
      setDetail(current => current?.id === row.id ? { ...current, ...updated } : current);
      messageApi.success(action === 'acknowledge' ? '已确认' : '已处置');
      actionRef.current?.reload();
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : '操作失败');
    } finally {
      setBusyKey(null);
    }
  };

  const handleBatchDelete = async (keys: React.Key[]) => {
    if (batchBusy) return;
    setBatchBusy(true);
    try {
      const items = Array.from(new Set(keys)).map((key) => {
        const id = Number(key);
        const found = pageRowsRef.current.find((row) => row.id === id);
        return { id, label: found ? `#${found.id} ${found.message}` : `#${key}` };
      });
      const result = await deleteRowsInSequence(items, (item) => deleteAlert(item.id));
      if (result.failed) {
        messageApi.error(
          `已删除 ${result.done.length} 条，「${result.failed.item.label}」删除失败：${result.failed.message}，后续已停止`,
        );
      } else {
        messageApi.success(`已删除 ${result.done.length} 条告警`);
      }
      actionRef.current?.clearSelected?.();
      actionRef.current?.reload();
    } finally {
      setBatchBusy(false);
    }
  };

  const renderRecordActions = (row: AlertRecordRow, inDetail = false) => {
          const acknowledged = !!row.acknowledged_at || row.status === 'acknowledged';
          const closed = row.status === 'closed' || !!row.closed_at;
          const nodes: React.ReactNode[] = [];
          if (canWrite) {
            nodes.push(
              <Button
                key="ack"
                {...rowActionKind('skip')}
                disabled={acknowledged || closed || busyKey != null}
                loading={rowBusy(row.id, 'acknowledge')}
                onClick={() => void handleTransition(row, 'acknowledge')}
              >
                确认
              </Button>,
              <Popconfirm
                key="close"
                title={`确认处置告警 #${row.id}？`}
                description="处置后进入终态，不可恢复"
                onConfirm={() => void handleTransition(row, 'close')}
              >
                <Button
                  {...rowActionKind('skip')}
                  disabled={closed || busyKey != null}
                  loading={rowBusy(row.id, 'close')}
                >
                  处置
                </Button>
              </Popconfirm>,
              <Popconfirm
                key="delete"
                title={`确认删除告警 #${row.id}？`}
                onConfirm={async () => {
                  try {
                    await deleteAlert(row.id);
                    setDetailOpen(false);
                    setDetail(null);
                    messageApi.success('删除成功');
                    actionRef.current?.reload();
                  } catch (error) {
                    messageApi.error(error instanceof Error ? error.message : '删除失败');
                  }
                }}
              >
                <Button {...rowActionKind('skip')} {...rowActionToneDestructive()}>
                  删除
                </Button>
              </Popconfirm>,
            );
          }
          return nodes.filter(node => React.isValidElement(node) && (inDetail ? node.key !== 'ack' : node.key === 'ack'));
        };

  const columns: ProColumns<AlertRecordRow>[] = useMemo(() => {
    const deviceValueEnum: Record<string, { text: string }> = {};
    deviceMap.forEach((label, id) => {
      deviceValueEnum[String(id)] = { text: label };
    });
    const toValueEnum = (options: { value: string; label: string }[]) =>
      Object.fromEntries(options.map((option) => [option.value, { text: option.label }]));
    return [
      {
        title: '告警说明',
        dataIndex: 'message',
        minWidth: 180,
        uniTableRemainderFlex: true,
        uniTablePrimaryFlex: true,
        resizable: false,
        ellipsis: true,
        render: (_, row) => canDisplay ? <Button type="link" size="small" style={{maxWidth:'100%',overflow:'hidden',textOverflow:'ellipsis'}} onClick={() => {setDetail(row);setDetailOpen(true);}}>{row.message}</Button> : row.message,
      },
      {
        title: '点位键',
        dataIndex: 'tag_key',
        width: 110,
        minWidth: 110,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
      },
      {
        title: '设备',
        dataIndex: 'device_id',
        width: 140,
        minWidth: 140,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        valueType: 'select',
        valueEnum: deviceValueEnum,
        render: (_, row) => deviceLabel(deviceMap, row.device_id),
      },
      {
        title: '规则',
        dataIndex: 'rule_id',
        width: 140,
        minWidth: 140,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        hideInSearch: true,
        render: (_, row) => (row.rule_id != null ? ruleMap.get(row.rule_id) ?? `规则 #${row.rule_id}` : '—'),
      },
      {
        title: '级别',
        dataIndex: 'severity',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        valueType: 'select',
        valueEnum: toValueEnum(ALERT_SEVERITY_OPTIONS),
        render: (_, row) => <SeverityTag value={row.severity} />,
      },
      {
        title: '状态',
        dataIndex: 'status',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        valueType: 'select',
        valueEnum: toValueEnum(ALERT_STATUS_OPTIONS),
        render: (_, row) => <AlertStatusTag value={row.status} />,
      },
      {
        title: '实际值',
        dataIndex: 'actual_value',
        width: 100,
        minWidth: 100,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        hideInSearch: true,
        render: (_, row) => row.actual_value ?? '—',
      },
      {
        title: '触发时间',
        dataIndex: 'triggered_at',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: (a, b) => dayjs(a.triggered_at).valueOf() - dayjs(b.triggered_at).valueOf(),
        render: (_, row) => formatTime(row.triggered_at),
      },
      {
        // 高级搜索的触发时间区间：独立隐藏列，避免与上面的展示列共用一个 dataIndex
        title: '触发时间区间',
        dataIndex: 'triggered_range',
        valueType: 'dateRange',
        hideInTable: true,
      },
      {
        title: '操作',
        key: 'action',
        fixed: 'right',
        hideInSearch: true,
        render: (_, row) => renderRecordActions(row),
      },
    ];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canDisplay, canWrite, deviceMap, ruleMap, busyKey, messageApi]);

  return (
    <>
      <UniTable<AlertRecordRow>
        columnPersistenceId="apps.kuaiiot.pages.alerts.records"
        permissionResource="kuaiiot:alert"
        actionRef={actionRef}
        rowKey="id"
        columns={alignIotTableColumns(columns, 'records')}
        viewTypes={['table', 'help']}
        helpViewConfig={{
          title: '使用帮助',
          content: (
            <div>
              <p>告警记录按状态流转：未确认 → 已确认 →（已恢复）→ 已处置。</p>
              <p>「确认」对已确认或已处置的记录不可用；「处置」为终态操作，记录进入已处置后不可恢复。</p>
              <p>模糊搜索覆盖告警说明、点位键与设备名；高级搜索可按状态、级别、设备与触发时间区间组合过滤。</p>
            </div>
          ),
        }}
        fuzzySearchPlaceholder="说明 / 点位键 / 设备"
        enableRowSelection={canWrite}
        toolBarRender={(_action, selected) =>
          canWrite
            ? [
                <UniBatchDeleteButton
                  key="batch-delete"
                  selectedRowKeys={selected.selectedRowKeys ?? []}
                  onConfirm={handleBatchDelete}
                  disabled={batchBusy}
                  confirmTitle={(count) => `确认删除选中的 ${count} 条告警？`}
                  confirmDescription="逐条删除，任一失败即停止并保留明细提示"
                />,
              ]
            : []
        }
        onTableDataChange={(rows) => {
          pageRowsRef.current = rows;
        }}
        defaultPageSize={20}
        request={async (params, _sort, _filter, searchFormValues) => {
          try {
            const [rows, devices, rules] = await Promise.all([
              listAlerts(),
              loadDeviceLabelMap().catch(() => new Map<number, string>()),
              listAlertRules().catch(() => []),
            ]);
            setDeviceMap(devices);
            setRuleMap(
              new Map<number, string>(
                (rules || []).map((rule): [number, string] => [
                  rule.id,
                  `${rule.name} (${rule.code})`,
                ]),
              ),
            );
            const keyword = pickListSearchKeyword(searchFormValues);
            let filtered = filterRowsByListKeyword<AlertRecordRow>(rows || [], keyword, (row) => [
              row.message,
              row.tag_key,
              deviceLabel(devices, row.device_id),
              row.actual_value,
            ]);
            const message = pickSearchString(searchFormValues, 'message');
            const tagKey = pickSearchString(searchFormValues, 'tag_key');
            const deviceId = pickSearchString(searchFormValues, 'device_id');
            const severity = pickSearchString(searchFormValues, 'severity');
            const status = pickSearchString(searchFormValues, 'status');
            const range = pickSearchDateTimeRange(
              searchFormValues,
              'triggered_from',
              'triggered_to',
              'triggered_range',
            );
            if (message) {
              filtered = filtered.filter((row) =>
                String(row.message ?? '').toLowerCase().includes(message.toLowerCase()),
              );
            }
            if (tagKey) filtered = filtered.filter((row) => row.tag_key.includes(tagKey));
            if (deviceId) filtered = filtered.filter((row) => row.device_id === Number(deviceId));
            if (severity) filtered = filtered.filter((row) => row.severity === severity);
            if (status) filtered = filtered.filter((row) => row.status === status);
            if (range.from) {
              const from = dayjs(range.from);
              filtered = filtered.filter((row) => !dayjs(row.triggered_at).isBefore(from));
            }
            if (range.to) {
              const to = dayjs(range.to);
              filtered = filtered.filter((row) => !dayjs(row.triggered_at).isAfter(to));
            }
            const current = Number(params?.current || 1);
            const pageSize = Number(params?.pageSize || 20);
            const start = (current - 1) * pageSize;
            return { data: filtered.slice(start, start + pageSize), success: true, total: filtered.length };
          } catch (error) {
            messageApi.error(error instanceof Error ? error.message : '读取告警记录失败');
            return { data: [], success: false, total: 0 };
          }
        }}
      />

      <DetailDrawerTemplate
        title={`告警详情${detail ? ` - #${detail.id}` : ''}`}
        open={detailOpen}
        extra={detail ? renderRecordActions(detail, true) : undefined}
        onClose={() => {
          setDetailOpen(false);
          setDetail(null);
        }}
        size={DRAWER_CONFIG.STANDARD_WIDTH}
        basic={
          detail ? (
            <Descriptions
              column={2}
              size="small"
              items={[
                { key: 'message', label: '告警说明', children: detail.message, span: 2 },
                { key: 'tag_key', label: '点位键', children: detail.tag_key || '—' },
                {
                  key: 'device_id',
                  label: '设备',
                  children: deviceLabel(deviceMap, detail.device_id),
                },
                {
                  key: 'rule_id',
                  label: '触发规则',
                  children:
                    detail.rule_id != null
                      ? ruleMap.get(detail.rule_id) ?? `规则 #${detail.rule_id}`
                      : '—',
                },
                {
                  key: 'severity',
                  label: '严重级别',
                  children: <SeverityTag value={detail.severity} />,
                },
                {
                  key: 'status',
                  label: '状态',
                  children: <AlertStatusTag value={detail.status} />,
                },
                { key: 'actual_value', label: '实际值', children: detail.actual_value ?? '—' },
                {
                  key: 'triggered_at',
                  label: '触发时间',
                  children: formatTime(detail.triggered_at),
                },
                {
                  key: 'acknowledged_at',
                  label: '确认时间',
                  children: formatTime(detail.acknowledged_at),
                },
                {
                  key: 'recovered_at',
                  label: '恢复时间',
                  children: formatTime(detail.recovered_at),
                },
                {
                  key: 'closed_at',
                  label: '处置时间',
                  children: formatTime(detail.closed_at),
                },
                { key: 'id', label: 'ID', children: detail.id },
              ]}
            />
          ) : (
            <div style={{ minHeight: 80 }} />
          )
        }
      />
    </>
  );
}
