/**
 * 边缘配置运营列表：模糊 + 高级搜索、新建、编辑、详情抽屉、删除/批量删除、
 * 客户端只读导出与 Modbus TCP 现场试读。
 * 列表接口为数组响应，筛选/排序/分页在前端完成。
 * 权限与后端一致：列表/详情/导出 = kuaiiot:device:display；
 * 新建/编辑/删除/试读 = kuaiiot:device:update（后端无独立 delete/export 权限码）。
 * 详情与导出的 config 做脱敏（不回显凭据类键与现场地址类键值）；
 * 编辑表单回显完整 config，保证合法字段整存不丢。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
  ProFormDependency,
  ProFormDigit,
  ProFormGroup,
  ProFormInstance,
  ProFormItem,
  ProFormList,
  ProFormSelect,
  ProFormSwitch,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { Alert, App, Button, Descriptions, Popconfirm, Result, Table, Tag, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { UniTable } from '../../../../components/uni-table';
import { UniBatchDeleteButton } from '../../../../components/uni-batch';
import { UniExportMenuButton } from '../../../../components/uni-export/UniExportMenuButton';
import { rowActionKind } from '../../../../components/uni-action';
import {
  DetailDrawerTemplate,
  DetailDrawerSection,
  DRAWER_CONFIG,
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
  detailDrawerDescriptionItems,
} from '../../../../components/layout-templates';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { withSingleNewShortcutHint } from '../../../../utils/globalNewShortcut';
import { getApiErrorMessage } from '../../../../utils/errorHandler';
import { downloadRecordsAsXlsx } from '../../../../utils/exportRecordsXlsx';
import { formatDateTimeBySiteSetting, todaySiteDateString } from '../../../../utils/format';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { AgentStatusTag } from '../../components/status-tags';
import { DeviceSelect } from '../../components/entity-selects';
import type { DeviceOut, EdgeConfigWrite } from '../../services/kuaiiot';
import {
  createEdgeConfigRow,
  deleteEdgeConfigRow,
  filterEdgeConfigRows,
  getEdgeConfigRow,
  listEdgeConfigRows,
  listEdgeDeviceRows,
  maskEdgeConfigForDisplay,
  requestEdgeTrial,
  sortLocalRows,
  updateEdgeConfigRow,
  EDGE_AGENT_STATUSES,
  EDGE_PROTOCOLS,
  MODBUS_DATA_TYPES,
  PUBLISH_MODES,
  type EdgeConfigRow,
} from './api';

const PROTOCOL_LABEL_KEYS: Record<string, string> = {
  modbus_tcp: 'app.kuaiiot.option.protocol.modbusTcp',
  modbus_rtu: 'app.kuaiiot.option.protocol.modbusRtu',
  opc_ua: 'app.kuaiiot.option.protocol.opcUa',
  s7: 'app.kuaiiot.option.protocol.s7',
};

/** UniTable 布局扩展列属性（uniTable* 由布局引擎读取，页面侧仅声明可选）。 */
type TableColumn<T extends Record<string, unknown>> = ProColumns<T> & {
  uniTableKeepWidth?: boolean;
  uniTableRemainderFlex?: boolean;
  uniTablePrimaryFlex?: boolean;
};

type RegisterRow = {
  tag_key?: string;
  address?: number;
  data_type?: string;
  scale?: number;
};

type EdgeFormValues = {
  code?: string;
  name?: string;
  device_id?: number;
  protocol?: string;
  is_enabled?: boolean;
  host?: string;
  port?: number;
  unit_id?: number;
  rack?: number;
  slot?: number;
  endpoint?: string;
  publish_mode?: string;
  registers?: RegisterRow[];
  nodes_json?: string;
  db_blocks_json?: string;
};

/** 详情/导出渲染用：config → 脱敏 JSON 文本 */
function maskedConfigText(config: Record<string, unknown> | undefined): string {
  return JSON.stringify(maskEdgeConfigForDisplay(config || {}), null, 2);
}

const EdgeConfigsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions('kuaiiot:device');
  const canDisplay = perms.canAction?.('display') ?? false;
  const canUpdate = perms.canAction?.('update') ?? false;

  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<ProFormInstance>(null);
  /** 跨页批量删除/导出选中解析：request 内增量累积（prefetch 只增不覆盖）。 */
  const allRowsRef = useRef<Map<number, EdgeConfigRow>>(new Map());
  const [pageRows, setPageRows] = useState<EdgeConfigRow[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [devices, setDevices] = useState<DeviceOut[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<EdgeConfigRow | null>(null);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detail, setDetail] = useState<EdgeConfigRow | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailIdRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    listEdgeDeviceRows()
      .then((rows) => {
        if (!cancelled) setDevices(rows || []);
      })
      .catch(() => {
        if (!cancelled) setDevices([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const deviceLabel = useCallback(
    (deviceId: number) => {
      const device = devices.find((row) => row.id === deviceId);
      return device ? `${device.name} (${device.code})` : `#${deviceId}`;
    },
    [devices],
  );

  const deviceSearchOptions = useMemo(
    () => devices.map((row) => ({ value: row.id, label: `${row.name} (${row.code})` })),
    [devices],
  );

  const protocolText = useCallback(
    (protocol: string | undefined) => {
      const key = PROTOCOL_LABEL_KEYS[String(protocol || '')];
      return key ? t(key) : protocol || '—';
    },
    [t],
  );

  const openCreate = useCallback(() => {
    if (!canUpdate) return;
    setEditing(null);
    setFormOpen(true);
  }, [canUpdate]);

  const openEdit = useCallback((row: EdgeConfigRow) => {
    setEditing(row);
    setFormOpen(true);
  }, []);

  const loadDetail = useCallback(
    async (id: number) => {
      detailIdRef.current = id;
      setDetailLoading(true);
      setDetailError(null);
      try {
        const row = await getEdgeConfigRow(id);
        if (detailIdRef.current === id) {
          setDetail(row);
        }
      } catch (e) {
        if (detailIdRef.current === id) {
          setDetail(null);
          setDetailError(getApiErrorMessage(e, t('app.kuaiiot.edgeConfigs.detailLoadFailed')));
        }
      } finally {
        if (detailIdRef.current === id) {
          setDetailLoading(false);
        }
      }
    },
    [t],
  );

  const openDetail = useCallback(
    (row: EdgeConfigRow) => {
      setDrawerOpen(true);
      setDetail(row);
      void loadDetail(row.id);
    },
    [loadDetail],
  );

  const formInitialValues = useMemo<Record<string, unknown>>(() => {
    if (!editing) {
      return {
        protocol: 'modbus_tcp',
        is_enabled: true,
        port: 502,
        unit_id: 1,
        publish_mode: 'http_ingest',
        registers: [{ tag_key: '', address: 0, data_type: 'uint16', scale: 1 }],
      };
    }
    const config = editing.config || {};
    const publish = (config.publish || {}) as Record<string, unknown>;
    return {
      code: editing.code,
      name: editing.name,
      device_id: editing.device_id,
      protocol: editing.protocol,
      is_enabled: editing.is_enabled,
      host: config.host,
      port: config.port,
      unit_id: config.unit_id,
      rack: config.rack,
      slot: config.slot,
      endpoint: config.endpoint,
      publish_mode: publish.mode || 'http_ingest',
      registers: Array.isArray(config.registers) ? config.registers : undefined,
      nodes_json: Array.isArray(config.nodes) ? JSON.stringify(config.nodes, null, 2) : undefined,
      db_blocks_json: Array.isArray(config.db_blocks)
        ? JSON.stringify(config.db_blocks, null, 2)
        : undefined,
    };
  }, [editing]);

  const handleSubmit = useCallback(
    async (values: EdgeFormValues) => {
      const protocol = values.protocol || 'modbus_tcp';
      const publishMode = values.publish_mode || 'http_ingest';

      /** 保留编辑态 config 中表单未覆盖的扩展键；清掉各协议形态键避免协议切换残留。 */
      const base: Record<string, unknown> = { ...(editing?.config || {}) };
      for (const key of [
        'host',
        'port',
        'unit_id',
        'registers',
        'endpoint',
        'nodes',
        'rack',
        'slot',
        'db_blocks',
      ]) {
        delete base[key];
      }
      const publishExtras = { ...((base.publish as Record<string, unknown>) || {}) };
      delete base.publish;
      const publish = { ...publishExtras, mode: publishMode };

      let config: Record<string, unknown>;
      if (protocol === 'modbus_tcp' || protocol === 'modbus_rtu') {
        const host = String(values.host || '').trim();
        const port = Number(values.port);
        const unitId = Number(values.unit_id);
        const registers = (values.registers || [])
          .filter((row) => row && String(row.tag_key || '').trim())
          .map((row) => ({
            tag_key: String(row.tag_key).trim(),
            address: Number(row.address),
            data_type: row.data_type || 'uint16',
            scale: row.scale == null ? 1 : Number(row.scale),
          }));
        if (!host) {
          messageApi.error(t('app.kuaiiot.edgeConfigs.hostRequired'));
          return;
        }
        if (!Number.isInteger(port) || port < 1 || port > 65535 || !Number.isInteger(unitId) || unitId < 0) {
          messageApi.error(t('app.kuaiiot.edgeConfigs.modbusInvalid'));
          return;
        }
        if (!registers.length) {
          messageApi.error(t('app.kuaiiot.edgeConfigs.registersRequired'));
          return;
        }
        if (new Set(registers.map((row) => row.tag_key)).size !== registers.length) {
          messageApi.error(t('app.kuaiiot.edgeConfigs.registerKeyDup'));
          return;
        }
        config = { ...base, host, port, unit_id: unitId, registers, publish };
      } else if (protocol === 'opc_ua') {
        const endpoint = String(values.endpoint || '').trim();
        let nodes: unknown;
        try {
          nodes = JSON.parse(values.nodes_json || '');
        } catch {
          messageApi.error(t('app.kuaiiot.message.invalidJson'));
          return;
        }
        if (!endpoint || !Array.isArray(nodes) || !nodes.length) {
          messageApi.error(t('app.kuaiiot.edgeConfigs.opcInvalid'));
          return;
        }
        config = { ...base, endpoint, nodes, publish };
      } else {
        const host = String(values.host || '').trim();
        let dbBlocks: unknown;
        try {
          dbBlocks = JSON.parse(values.db_blocks_json || '');
        } catch {
          messageApi.error(t('app.kuaiiot.message.invalidJson'));
          return;
        }
        const rack = Number(values.rack);
        const slot = Number(values.slot);
        if (!host || !Number.isFinite(rack) || !Number.isFinite(slot) || !Array.isArray(dbBlocks) || !dbBlocks.length) {
          messageApi.error(t('app.kuaiiot.edgeConfigs.s7Invalid'));
          return;
        }
        config = { ...base, host, rack, slot, db_blocks: dbBlocks, publish };
      }

      const payload: EdgeConfigWrite = {
        code: String(values.code || '').trim(),
        name: String(values.name || '').trim(),
        device_id: Number(values.device_id),
        protocol,
        config,
        is_enabled: values.is_enabled ?? true,
      };

      try {
        if (editing) {
          await updateEdgeConfigRow(editing.id, payload);
        } else {
          await createEdgeConfigRow(payload);
        }
        messageApi.success(t('common.saveSuccess'));
        setFormOpen(false);
        setEditing(null);
        actionRef.current?.reload();
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.saveFailed')));
      }
    },
    [editing, messageApi, t],
  );

  const handleDelete = useCallback(
    async (row: EdgeConfigRow) => {
      try {
        await deleteEdgeConfigRow(row.id);
        messageApi.success(t('common.deleteSuccess'));
        actionRef.current?.reload();
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.deleteFailed')));
      }
    },
    [messageApi, t],
  );

  /** 串行批量删除：首条失败即停并报明细。 */
  const handleBatchDelete = useCallback(
    async (keys: React.Key[]) => {
      const rows = keys
        .map((key) => allRowsRef.current.get(Number(key)))
        .filter((row): row is EdgeConfigRow => Boolean(row));
      let success = 0;
      for (const row of rows) {
        try {
          await deleteEdgeConfigRow(row.id);
          success += 1;
        } catch (e) {
          messageApi.error(
            t('app.kuaiiot.message.batchDeleteStopped', {
              success,
              name: row.name || row.code,
              reason: getApiErrorMessage(e, t('common.operationFailed')),
            }),
          );
          break;
        }
      }
      if (success === rows.length && rows.length > 0) {
        messageApi.success(t('common.batchDeleteSuccess', { count: success }));
      }
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    },
    [messageApi, t],
  );

  const handleTrial = useCallback(
    async (row: EdgeConfigRow) => {
      try {
        await requestEdgeTrial(row.id);
        messageApi.info(t('app.kuaiiot.edgeConfigs.trialSubmitted'));
        actionRef.current?.reload();
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('app.kuaiiot.edgeConfigs.trialFailed')));
      }
    },
    [messageApi, t],
  );

  const buildExportRows = useCallback(
    (rows: EdgeConfigRow[]) =>
      rows.map((row) => ({
        code: row.code,
        name: row.name,
        device: deviceLabel(row.device_id),
        protocol: protocolText(row.protocol),
        is_enabled: row.is_enabled ? t('common.enabled') : t('common.disabled'),
        agent_status: row.agent_status || '—',
        agent_version: row.agent_version || '—',
        config_version: row.config_version,
        agent_config_version: row.agent_config_version ?? '—',
        buffer_pending_count: row.buffer_pending_count,
        last_agent_heartbeat_at: formatDateTimeBySiteSetting(row.last_agent_heartbeat_at),
        config_json: maskedConfigText(row.config),
      })),
    [deviceLabel, protocolText, t],
  );

  const handleExport = useCallback(
    async (type: 'selected' | 'currentPage' | 'all', keys?: React.Key[], pageData?: EdgeConfigRow[]) => {
      try {
        let rows: EdgeConfigRow[] = [];
        if (type === 'selected' && keys?.length) {
          rows = keys
            .map((key) => allRowsRef.current.get(Number(key)))
            .filter((row): row is EdgeConfigRow => Boolean(row));
        } else if (type === 'currentPage' && pageData) {
          rows = pageData;
        } else {
          rows = await listEdgeConfigRows();
        }
        if (!rows.length) {
          messageApi.warning(t('common.noDataToExport'));
          return;
        }
        await downloadRecordsAsXlsx(
          buildExportRows(rows),
          `${t('app.kuaiiot.edgeConfigs.exportFileName', { date: todaySiteDateString() })}.xlsx`,
          {
            columns: [
              { key: 'code', title: t('common.code') },
              { key: 'name', title: t('common.name') },
              { key: 'device', title: t('app.kuaiiot.field.device') },
              { key: 'protocol', title: t('app.kuaiiot.field.protocol') },
              { key: 'is_enabled', title: t('common.status') },
              { key: 'agent_status', title: t('app.kuaiiot.field.agentStatus') },
              { key: 'agent_version', title: t('app.kuaiiot.edgeConfigs.agentVersion') },
              { key: 'config_version', title: t('app.kuaiiot.field.configVersion') },
              { key: 'agent_config_version', title: t('app.kuaiiot.edgeConfigs.agentConfigVersion') },
              { key: 'buffer_pending_count', title: t('app.kuaiiot.field.bufferPending') },
              { key: 'last_agent_heartbeat_at', title: t('app.kuaiiot.field.lastHeartbeat') },
              { key: 'config_json', title: t('app.kuaiiot.edgeConfigs.configJsonMasked') },
            ],
          },
        );
        messageApi.success(t('common.exportSuccess', { count: rows.length }));
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.exportFailed')));
      }
    },
    [buildExportRows, messageApi, t],
  );

  const columns = useMemo<TableColumn<EdgeConfigRow>[]>(
    () =>
      alignProColumns<EdgeConfigRow>(
        [
          {
            title: t('common.code'),
            dataIndex: 'code',
            width: 130,
            minWidth: 130,
            uniTableKeepWidth: true,
            resizable: false,
            copyable: true,
            ellipsis: true,
            sorter: true,
          },
          {
            title: t('common.name'),
            dataIndex: 'name',
            width: 150,
            minWidth: 140,
            ellipsis: true,
            sorter: true,
          },
          {
            title: t('app.kuaiiot.field.device'),
            dataIndex: 'device_id',
            minWidth: 170,
            uniTableRemainderFlex: true,
            uniTablePrimaryFlex: true,
            resizable: false,
            ellipsis: true,
            valueType: 'select',
            fieldProps: { options: deviceSearchOptions, showSearch: true, optionFilterProp: 'label' },
            render: (_, row) => deviceLabel(row.device_id),
          },
          {
            title: t('app.kuaiiot.field.protocol'),
            dataIndex: 'protocol',
            width: 110,
            minWidth: 110,
            uniTableKeepWidth: true,
            resizable: false,
            valueType: 'select',
            valueEnum: EDGE_PROTOCOLS.reduce<Record<string, { text: string }>>((map, value) => {
              map[value] = { text: t(PROTOCOL_LABEL_KEYS[value]) };
              return map;
            }, {}),
            render: (_, row) => <Tag>{protocolText(row.protocol)}</Tag>,
          },
          {
            title: t('common.status'),
            dataIndex: 'is_enabled',
            width: 90,
            minWidth: 90,
            uniTableKeepWidth: true,
            resizable: false,
            valueType: 'select',
            valueEnum: {
              true: { text: t('common.enabled') },
              false: { text: t('common.disabled') },
            },
            render: (_, row) =>
              row.is_enabled ? (
                <Tag color="green">{t('common.enabled')}</Tag>
              ) : (
                <Tag>{t('common.disabled')}</Tag>
              ),
          },
          {
            title: t('app.kuaiiot.field.agentStatus'),
            dataIndex: 'agent_status',
            width: 100,
            minWidth: 100,
            uniTableKeepWidth: true,
            resizable: false,
            valueType: 'select',
            valueEnum: EDGE_AGENT_STATUSES.reduce<Record<string, { text: string }>>(
              (map, value) => {
                map[value] = { text: t(`app.kuaiiot.edgeConfigs.agentStatus.${value}`) };
                return map;
              },
              {},
            ),
            render: (_, row) => <AgentStatusTag value={row.agent_status} />,
          },
          {
            title: t('app.kuaiiot.field.lastHeartbeat'),
            dataIndex: 'last_agent_heartbeat_at',
            width: 165,
            minWidth: 165,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            sorter: true,
            render: (_, row) => formatDateTimeBySiteSetting(row.last_agent_heartbeat_at),
          },
          {
            title: t('app.kuaiiot.edgeConfigs.colVersion'),
            dataIndex: 'config_version',
            width: 130,
            minWidth: 130,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            sorter: true,
            render: (_, row) => (
              <Typography.Text type="secondary">
                {`v${row.config_version} / Agent ${row.agent_config_version ?? '—'}`}
              </Typography.Text>
            ),
          },
          {
            title: t('app.kuaiiot.field.bufferPending'),
            dataIndex: 'buffer_pending_count',
            width: 100,
            minWidth: 100,
            uniTableKeepWidth: true,
            resizable: false,
            align: 'right',
            hideInSearch: true,
            sorter: true,
            render: (_, row) => row.buffer_pending_count,
          },
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => {
              const trialDisabled = !row.is_enabled || row.protocol !== 'modbus_tcp';
              return [
                <Button
                  key="detail"
                  type="link"
                  size="small"
                  {...rowActionKind('display')}
                  onClick={() => openDetail(row)}
                >
                  {t('common.detail')}
                </Button>,
                <Button
                  key="trial"
                  type="link"
                  size="small"
                  {...rowActionKind('update')}
                  disabled={trialDisabled}
                  title={trialDisabled ? t('app.kuaiiot.edgeConfigs.trialDisabled') : undefined}
                  onClick={() => void handleTrial(row)}
                >
                  {t('app.kuaiiot.edgeConfigs.trial')}
                </Button>,
                <Button
                  key="edit"
                  type="link"
                  size="small"
                  {...rowActionKind('update')}
                  onClick={() => openEdit(row)}
                >
                  {t('common.edit')}
                </Button>,
                <Popconfirm
                  key="delete"
                  title={t('app.kuaiiot.edgeConfigs.deleteConfirm', {
                    name: row.name || row.code,
                  })}
                  onConfirm={() => void handleDelete(row)}
                >
                  <Button type="link" size="small" danger {...rowActionKind('update')}>
                    {t('common.delete')}
                  </Button>
                </Popconfirm>,
              ];
            },
          },
        ] as TableColumn<EdgeConfigRow>[],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [t, deviceSearchOptions, deviceLabel, protocolText, openDetail, openEdit, handleTrial, handleDelete],
  );

  const detailColumns = useMemo<ProDescriptionsItemProps<EdgeConfigRow>[]>(
    () => [
      { title: t('common.code'), dataIndex: 'code' },
      { title: t('common.name'), dataIndex: 'name' },
      {
        title: t('app.kuaiiot.field.device'),
        dataIndex: 'device_id',
        render: (_, row) => deviceLabel(row.device_id),
      },
      {
        title: t('app.kuaiiot.field.protocol'),
        dataIndex: 'protocol',
        render: (_, row) => protocolText(row.protocol),
      },
      {
        title: t('common.status'),
        dataIndex: 'is_enabled',
        render: (_, row) =>
          row.is_enabled ? (
            <Tag color="green">{t('common.enabled')}</Tag>
          ) : (
            <Tag>{t('common.disabled')}</Tag>
          ),
      },
      {
        title: t('app.kuaiiot.edgeConfigs.publishMode'),
        dataIndex: 'publish_mode',
        render: (_, row) => {
          const publish = (row.config?.publish || {}) as Record<string, unknown>;
          return publish.mode ? String(publish.mode) : '—';
        },
      },
    ],
    [t, deviceLabel, protocolText],
  );

  if (!canDisplay) {
    return <Result status="403" title={t('common.noPermission')} />;
  }

  return (
    <ListPageTemplate>
      <UniTable<EdgeConfigRow>
        viewTypes={['table', 'help']}
        helpViewConfig={buildListPageHelpViewConfig('kuaiiot.edgeConfigs')}
        columnPersistenceId="apps.kuaiiot.pages.edge-configs.list-v1"
        permissionResource="kuaiiot:device"
        actionRef={actionRef}
        rowKey="id"
        headerTitle={t('app.kuaiiot.menu.edgeConfigs')}
        columns={columns}
        onCreate={openCreate}
        toolBarActions={[
          canUpdate ? (
            <Button key="create" type="primary" icon={<PlusOutlined />} onClick={openCreate}>
              {withSingleNewShortcutHint(t('app.kuaiiot.action.createEdgeConfig'))}
            </Button>
          ) : null,
          canUpdate ? (
            <UniBatchDeleteButton
              key="batch-delete"
              selectedRowKeys={selectedRowKeys}
              onConfirm={handleBatchDelete}
              confirmTitle={t('common.batchDeleteTitle')}
              confirmDescription={(count) => t('common.batchDeleteContent', { count })}
            />
          ) : null,
        ].filter(Boolean)}
        rightToolBarActionsBeforeExport={
          canDisplay
            ? [
                <UniExportMenuButton<EdgeConfigRow>
                  key="export"
                  onExport={handleExport}
                  selectedRowKeys={selectedRowKeys}
                  tableData={pageRows}
                />,
              ]
            : []
        }
        enableRowSelection={canUpdate}
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        onTableDataChange={(rows) => {
          setPageRows(rows);
        }}
        defaultPageSize={20}
        request={async (params, sort, _filter, searchFormValues) => {
          try {
            const rows = await listEdgeConfigRows();
            for (const row of rows) {
              allRowsRef.current.set(row.id, row);
            }
            const filtered = sortLocalRows(
              filterEdgeConfigRows(rows, searchFormValues, deviceLabel),
              sort,
            );
            const pageSize = params.pageSize || 20;
            const current = params.current || 1;
            return {
              data: filtered.slice((current - 1) * pageSize, current * pageSize),
              success: true,
              total: filtered.length,
            };
          } catch (e) {
            messageApi.error(getApiErrorMessage(e, t('app.kuaiiot.edgeConfigs.listFailed')));
            return { data: [], success: false, total: 0 };
          }
        }}
      />

      <FormModalTemplate
        title={
          editing
            ? t('app.kuaiiot.edgeConfigs.editTitle')
            : t('app.kuaiiot.action.createEdgeConfig')
        }
        open={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        isEdit={Boolean(editing)}
        formRef={formRef}
        initialValues={formInitialValues}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        onFinish={handleSubmit}
      >
        <ProFormText
          name="code"
          label={t('common.code')}
          rules={[{ required: true, message: t('common.required') }]}
          fieldProps={{ maxLength: 50 }}
        />
        <ProFormText
          name="name"
          label={t('common.name')}
          rules={[{ required: true, message: t('common.required') }]}
          fieldProps={{ maxLength: 100 }}
        />
        <ProFormItem
          name="device_id"
          label={t('app.kuaiiot.field.device')}
          rules={[{ required: true, message: t('common.required') }]}
        >
          <DeviceSelect />
        </ProFormItem>
        <ProFormSelect
          name="protocol"
          label={t('app.kuaiiot.field.protocol')}
          options={EDGE_PROTOCOLS.map((value) => ({
            value,
            label: t(PROTOCOL_LABEL_KEYS[value]),
          }))}
          rules={[{ required: true, message: t('common.required') }]}
        />
        <ProFormDependency name={['protocol']}>
          {({ protocol }: { protocol?: string }) =>
            protocol && protocol !== 'modbus_tcp' ? (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message={t('app.kuaiiot.hint.edgeProtocolAgentSupport')}
              />
            ) : null
          }
        </ProFormDependency>
        <ProFormSelect
          name="publish_mode"
          label={t('app.kuaiiot.edgeConfigs.publishMode')}
          options={PUBLISH_MODES.map((value) => ({ value, label: value }))}
          rules={[{ required: true, message: t('common.required') }]}
        />
        <ProFormDependency name={['protocol']}>
          {({ protocol }: { protocol?: string }) => {
            if (protocol === 'opc_ua') {
              return (
                <>
                  <ProFormText
                    name="endpoint"
                    label={t('app.kuaiiot.edgeConfigs.fieldEndpoint')}
                    rules={[{ required: true, message: t('common.required') }]}
                  />
                  <ProFormTextArea
                    name="nodes_json"
                    label={t('app.kuaiiot.edgeConfigs.fieldNodesJson')}
                    fieldProps={{ rows: 4 }}
                    rules={[{ required: true, message: t('common.required') }]}
                  />
                </>
              );
            }
            if (protocol === 's7') {
              return (
                <>
                  <ProFormText
                    name="host"
                    label={t('app.kuaiiot.edgeConfigs.fieldHost')}
                    rules={[{ required: true, message: t('common.required') }]}
                  />
                  <ProFormDigit
                    name="rack"
                    label={t('app.kuaiiot.edgeConfigs.fieldRack')}
                    min={0}
                    rules={[{ required: true, message: t('common.required') }]}
                    fieldProps={{ precision: 0 }}
                  />
                  <ProFormDigit
                    name="slot"
                    label={t('app.kuaiiot.edgeConfigs.fieldSlot')}
                    min={0}
                    rules={[{ required: true, message: t('common.required') }]}
                    fieldProps={{ precision: 0 }}
                  />
                  <ProFormTextArea
                    name="db_blocks_json"
                    label={t('app.kuaiiot.edgeConfigs.fieldDbBlocksJson')}
                    fieldProps={{ rows: 4 }}
                    rules={[{ required: true, message: t('common.required') }]}
                  />
                </>
              );
            }
            return (
              <>
                <ProFormText
                  name="host"
                  label={t('app.kuaiiot.edgeConfigs.fieldHost')}
                  rules={[{ required: true, message: t('common.required') }]}
                />
                <ProFormDigit
                  name="port"
                  label={t('app.kuaiiot.edgeConfigs.fieldPort')}
                  min={1}
                  max={65535}
                  rules={[{ required: true, message: t('common.required') }]}
                  fieldProps={{ precision: 0 }}
                />
                <ProFormDigit
                  name="unit_id"
                  label={t('app.kuaiiot.edgeConfigs.fieldUnitId')}
                  min={0}
                  max={255}
                  rules={[{ required: true, message: t('common.required') }]}
                  fieldProps={{ precision: 0 }}
                />
                <ProFormList
                  name="registers"
                  label={t('app.kuaiiot.edgeConfigs.sectionRegisters')}
                  min={1}
                  creatorButtonProps={{ creatorButtonText: t('app.kuaiiot.action.addTagRow') }}
                  creatorRecord={{ tag_key: '', address: 0, data_type: 'uint16', scale: 1 }}
                  copyIconProps={false}
                  deleteIconProps={{ tooltipText: t('common.delete') }}
                >
                  <ProFormGroup>
                    <ProFormText
                      name="tag_key"
                      label={t('app.kuaiiot.field.tagKey')}
                      rules={[{ required: true, message: t('common.required') }]}
                      width="sm"
                      fieldProps={{ maxLength: 100 }}
                    />
                    <ProFormDigit
                      name="address"
                      label={t('app.kuaiiot.edgeConfigs.fieldAddress')}
                      min={0}
                      rules={[{ required: true, message: t('common.required') }]}
                      width="xs"
                      fieldProps={{ precision: 0 }}
                    />
                    <ProFormSelect
                      name="data_type"
                      label={t('app.kuaiiot.edgeConfigs.fieldDataType')}
                      options={MODBUS_DATA_TYPES.map((value) => ({ value, label: value }))}
                      width="xs"
                    />
                    <ProFormDigit
                      name="scale"
                      label={t('app.kuaiiot.edgeConfigs.fieldScale')}
                      width="xs"
                    />
                  </ProFormGroup>
                </ProFormList>
              </>
            );
          }}
        </ProFormDependency>
        <ProFormSwitch name="is_enabled" label={t('common.status')} />
      </FormModalTemplate>

      <DetailDrawerTemplate
        title={t('app.kuaiiot.edgeConfigs.detailTitle')}
        open={drawerOpen}
        onClose={() => {
          setDrawerOpen(false);
          setDetail(null);
          setDetailError(null);
          detailIdRef.current = null;
        }}
        size={DRAWER_CONFIG.STANDARD_WIDTH}
        loading={detailLoading}
        plainBody={
          detailError && !detail ? (
            <Result
              status="error"
              title={detailError}
              extra={
                <Button
                  type="primary"
                  onClick={() => {
                    const id = detailIdRef.current;
                    if (id != null) void loadDetail(id);
                  }}
                >
                  {t('common.retry')}
                </Button>
              }
            />
          ) : undefined
        }
        basic={
          detail ? (
            <Descriptions
              column={2}
              size="small"
              items={detailDrawerDescriptionItems(detailColumns, detail)}
            />
          ) : undefined
        }
        supplementaryTitle={detail ? t('app.kuaiiot.edgeConfigs.agentSection') : undefined}
        supplementary={
          detail ? (
            <Descriptions
              column={2}
              size="small"
              items={[
                {
                  key: 'agent_status',
                  label: t('app.kuaiiot.field.agentStatus'),
                  children: <AgentStatusTag value={detail.agent_status} />,
                },
                {
                  key: 'agent_version',
                  label: t('app.kuaiiot.edgeConfigs.agentVersion'),
                  children: detail.agent_version || '—',
                },
                {
                  key: 'config_version',
                  label: t('app.kuaiiot.field.configVersion'),
                  children: `v${detail.config_version}`,
                },
                {
                  key: 'agent_config_version',
                  label: t('app.kuaiiot.edgeConfigs.agentConfigVersion'),
                  children: detail.agent_config_version ?? '—',
                },
                {
                  key: 'buffer_pending_count',
                  label: t('app.kuaiiot.field.bufferPending'),
                  children: detail.buffer_pending_count,
                },
                {
                  key: 'last_agent_heartbeat_at',
                  label: t('app.kuaiiot.field.lastHeartbeat'),
                  children: formatDateTimeBySiteSetting(detail.last_agent_heartbeat_at),
                },
              ]}
            />
          ) : undefined
        }
        linesTitle={detail ? t('app.kuaiiot.edgeConfigs.configSection') : undefined}
        lines={
          detail ? (
            <>
              <DetailDrawerSection
                title={t('app.kuaiiot.edgeConfigs.configSection')}
                titleExtra={
                  <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
                    {t('app.kuaiiot.edgeConfigs.configMaskedHint')}
                  </Typography.Text>
                }
              >
                <pre
                  style={{
                    margin: 0,
                    maxHeight: 320,
                    overflow: 'auto',
                    fontSize: 12,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                  }}
                >
                  {maskedConfigText(detail.config)}
                </pre>
              </DetailDrawerSection>
              <DetailDrawerSection title={t('app.kuaiiot.edgeConfigs.trialResult')} marginBottom={0}>
                {detail.trial_result ? (
                  <>
                    <Table
                      rowKey="key"
                      size="small"
                      pagination={false}
                      dataSource={Object.entries(detail.trial_result.tags || {}).map(
                        ([key, value]) => ({
                          key,
                          raw: JSON.stringify(detail.trial_result?.raw_values?.[key] ?? null),
                          value: JSON.stringify(value),
                          quality: detail.trial_result?.qualities?.[key] || '—',
                        }),
                      )}
                      columns={[
                        { title: t('app.kuaiiot.edgeConfigs.trialTag'), dataIndex: 'key' },
                        { title: t('app.kuaiiot.edgeConfigs.trialRaw'), dataIndex: 'raw' },
                        { title: t('app.kuaiiot.edgeConfigs.trialValue'), dataIndex: 'value' },
                        { title: t('app.kuaiiot.edgeConfigs.trialQuality'), dataIndex: 'quality' },
                      ]}
                    />
                    <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
                      {t('app.kuaiiot.edgeConfigs.trialMeta', {
                        version: detail.trial_result.config_version,
                        time: formatDateTimeBySiteSetting(detail.trial_result.received_at),
                      })}
                    </Typography.Text>
                  </>
                ) : (
                  <Typography.Text type="secondary">
                    {detail.trial_request_uuid
                      ? t('app.kuaiiot.edgeConfigs.trialPending')
                      : t('app.kuaiiot.edgeConfigs.trialNone')}
                  </Typography.Text>
                )}
              </DetailDrawerSection>
            </>
          ) : undefined
        }
      />
    </ListPageTemplate>
  );
};

export default EdgeConfigsPage;
