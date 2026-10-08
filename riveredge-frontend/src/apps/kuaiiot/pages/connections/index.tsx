/**
 * 接入配置：数采连接运营列表页。
 * 写操作（新建/编辑/删除/启停）后端统一要求 kuaiiot:connection:create；
 * 行内按钮用 rowActionKind('skip') + 显式权限判断，避免 manifest 缺 :update/:delete 误隐藏。
 */

import React, { useCallback, useMemo, useRef, useState } from 'react';
import type {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
  ProFormInstance,
} from '@ant-design/pro-components';
import { ProFormSwitch, ProFormText, ProFormTextArea } from '@ant-design/pro-components';
import { Alert, App, Button, Divider, Dropdown, Form, Popconfirm, Select, Space, Tag, Typography } from 'antd';
import { UniTable } from '../../../../components/uni-table';
import { rowActionKind } from '../../../../components/uni-action';
import { UniBatchDeleteButton } from '../../../../components/uni-batch';
import {
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
} from '../../../../components/layout-templates';
import SafeProFormSelect from '../../../../components/safe-pro-form-select';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { formatDateTimeBySiteSetting } from '../../../../utils/format';
import {
  extractProTableSort,
  filterRowsByListKeyword,
  pickListSearchKeyword,
  pickSearchString,
  pickSearchTriStateBoolean,
} from '../../../../utils/tableQueryKey';
import {
  getIntegrationConfigListAllMatching,
  type IntegrationConfig,
} from '../../../../services/integrationConfig';
import { IotConnectionModal } from '../../../../pages/system/application-connections/IotConnectionModal';
import { eligibleIotConnections } from '../../../../pages/system/application-connections/iotConnectionConfig';
import { HealthStatusTag } from '../../components/status-tags';
import {
  createConnectionRow,
  deleteConnectionRow,
  getConnectionRow,
  listConnectionRows,
  updateConnectionRow,
  type ConnectionRow,
} from './api';

const CONNECTION_TYPE_OPTIONS = [
  { value: 'http', label: 'HTTP（直接入站）' },
  { value: 'mqtt', label: 'MQTT' },
  { value: 'thingsboard', label: 'ThingsBoard' },
  { value: 'jetlinks', label: 'JetLinks' },
];

const HEALTH_OPTIONS = [
  { value: 'connected', label: '已连接' },
  { value: 'connecting', label: '连接中' },
  { value: 'receiving', label: '接收中' },
  { value: 'authenticated', label: '已认证' },
  { value: 'idle', label: '空闲' },
  { value: 'disconnected', label: '已断开' },
  { value: 'unavailable', label: '不可用' },
  { value: 'disabled', label: '已停用' },
  { value: 'unknown', label: '未知' },
];

/** 映射字段只允许这些键（后端 validate_mapping 强校验；地址与凭据在公共连接维护）。 */
const MAPPING_FIELDS: Array<{ name: string; label: string; mqttOnly?: boolean }> = [
  { name: 'topic', label: '订阅主题', mqttOnly: true },
  { name: 'device_token_path', label: '设备凭据路径' },
  { name: 'tags_path', label: '点位路径' },
  { name: 'events_path', label: '事件路径' },
  { name: 'timestamp_path', label: '采样时间路径' },
  { name: 'idempotency_key_path', label: '幂等键路径' },
];

function fmtTime(value?: string | null): string {
  return value ? formatDateTimeBySiteSetting(value, '—') : '—';
}

function sortRows(rows: ConnectionRow[], sort: Record<string, 'ascend' | 'descend' | null>) {
  const { sortBy, sortOrder } = extractProTableSort(sort);
  const sorted = [...rows].sort((a, b) => {
    const av = (a as Record<string, unknown>)[sortBy ?? 'created_at'];
    const bv = (b as Record<string, unknown>)[sortBy ?? 'created_at'];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    return String(av).localeCompare(String(bv), 'zh-CN');
  });
  return sortOrder === 'asc' ? sorted : sorted.reverse();
}

const ConnectionsPage: React.FC = () => {
  const { message: messageApi, modal } = App.useApp();
  const perms = useResourcePermissions('kuaiiot:connection');
  const canWrite = perms.canCreate;
  const actionRef = useRef<ActionType>();
  const formRef = useRef<ProFormInstance>();
  /** 跨页批量删除解析：request 内增量累积（只增不覆盖），不依赖当前展示页。 */
  const allRowsRef = useRef<Map<number, ConnectionRow>>(new Map());

  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ConnectionRow | null>(null);
  const [formConnType, setFormConnType] = useState('http');
  const [iotModalOpen, setIotModalOpen] = useState(false);
  const [coreLoading, setCoreLoading] = useState(false);
  const [coreError, setCoreError] = useState(false);
  const [coreConnections, setCoreConnections] = useState<IntegrationConfig[]>([]);
  const [detail, setDetail] = useState<ConnectionRow | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadCoreConnections = useCallback(async () => {
    setCoreLoading(true);
    setCoreError(false);
    try {
      setCoreConnections(await getIntegrationConfigListAllMatching({ is_active: true }));
    } catch {
      setCoreError(true);
    } finally {
      setCoreLoading(false);
    }
  }, []);

  const openCreate = useCallback(() => {
    setEditing(null);
    setIotModalOpen(false);
    setFormConnType('http');
    void loadCoreConnections();
    setModalOpen(true);
  }, [loadCoreConnections]);

  const openEdit = useCallback((row: ConnectionRow) => {
    setEditing(row);
    setModalOpen(true);
  }, []);

  const openDetail = useCallback(async (row: ConnectionRow) => {
    setDetail(row);
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      setDetail(await getConnectionRow(row.id));
    } catch (error) {
      messageApi.error(error instanceof Error ? error.message : '读取连接详情失败');
    } finally {
      setDetailLoading(false);
    }
  }, [messageApi]);

  const handleToggleEnabled = useCallback(
    async (row: ConnectionRow) => {
      try {
        await updateConnectionRow(row.id, { is_enabled: !row.is_enabled });
        messageApi.success(row.is_enabled ? '已停用' : '已启用');
        actionRef.current?.reload();
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '操作失败');
      }
    },
    [messageApi],
  );

  const handleDelete = useCallback(
    async (row: ConnectionRow) => {
      try {
        await deleteConnectionRow(row.id);
        messageApi.success('删除成功');
        setSelectedRowKeys((keys) => keys.filter((k) => k !== row.id));
        actionRef.current?.reload();
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '删除失败');
      }
    },
    [messageApi],
  );

  /** 批删串行执行：任一失败即停止，报告成功数与失败明细；跨页选中行从 allRowsRef 解析名称。 */
  const handleBatchDelete = useCallback(
    async (keys: React.Key[]) => {
      let done = 0;
      for (const key of keys) {
        const row = allRowsRef.current.get(Number(key));
        const label = row ? `${row.name} (${row.code})` : `#${key}`;
        try {
          await deleteConnectionRow(Number(key));
          done += 1;
        } catch (error) {
          modal.warning({
            title: '批量删除未完成',
            content: `已删除 ${done} 条；“${label}”删除失败：${
              error instanceof Error ? error.message : '未知错误'
            }。后续 ${keys.length - done - 1} 条未执行。`,
          });
          actionRef.current?.reload();
          setSelectedRowKeys([]);
          return;
        }
      }
      messageApi.success(`成功删除 ${done} 条记录`);
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    },
    [messageApi, modal],
  );

  const columns = useMemo<ProColumns<ConnectionRow>[]>(
    () => [
      {
        title: '编码',
        dataIndex: 'code',
        key: 'code',
        sorter: true,
        copyable: true,
        ellipsis: true,
        width: 140,
      },
      { title: '名称', dataIndex: 'name', key: 'name', sorter: true, ellipsis: true, minWidth: 160 },
      {
        title: '类型',
        dataIndex: 'connection_type',
        key: 'connection_type',
        valueType: 'select',
        valueEnum: Object.fromEntries(CONNECTION_TYPE_OPTIONS.map((o) => [o.value, { text: o.label }])),
        width: 110,
        render: (_, row) => <Tag>{row.connection_type}</Tag>,
      },
      {
        title: '健康状态',
        dataIndex: 'health_status',
        key: 'health_status',
        valueType: 'select',
        valueEnum: Object.fromEntries(HEALTH_OPTIONS.map((o) => [o.value, { text: o.label }])),
        width: 110,
        render: (_, row) => <HealthStatusTag value={row.health_status} />,
      },
      {
        title: '启用',
        dataIndex: 'is_enabled',
        key: 'is_enabled',
        valueType: 'select',
        valueEnum: { true: { text: '启用' }, false: { text: '停用' } },
        width: 80,
        render: (_, row) =>
          row.is_enabled ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
      },
      {
        title: '创建时间',
        dataIndex: 'created_at',
        key: 'created_at',
        sorter: true,
        hideInSearch: true,
        width: 160,
        render: (_, row) => fmtTime(row.created_at),
      },
      {
        title: '操作',
        key: 'action',
        fixed: 'right',
        hideInSearch: true,
        render: (_, row) => [
          <Button
            key="detail"
            type="link"
            size="small"
            {...rowActionKind('display')}
            onClick={() => void openDetail(row)}
          >
            详情
          </Button>,
          ...(canWrite
            ? [
                <Button
                  key="edit"
                  type="link"
                  size="small"
                  {...rowActionKind('skip')}
                  onClick={() => openEdit(row)}
                >
                  编辑
                </Button>,
                <Popconfirm
                  key="delete"
                  title="确定删除该连接？"
                  description="删除为软删除，关联设备将失去连接来源"
                  onConfirm={() => void handleDelete(row)}
                >
                  <Button type="link" size="small" danger {...rowActionKind('skip')}>
                    删除
                  </Button>
                </Popconfirm>,
                <Dropdown
                  key="more"
                  {...rowActionKind('skip')}
                  trigger={['click']}
                  menu={{
                    items: [
                      {
                        key: 'toggle-enabled',
                        label: row.is_enabled ? '停用' : '启用',
                        onClick: () => {
                          modal.confirm({
                            title: row.is_enabled ? '确认停用该连接？' : '确认启用该连接？',
                            content: row.is_enabled ? '停用后将不再接收数据' : undefined,
                            onOk: () => handleToggleEnabled(row),
                          });
                        },
                      },
                    ],
                  }}
                >
                  <Button type="link" size="small">
                    更多
                  </Button>
                </Dropdown>,
              ]
            : []),
        ],
      },
    ],
    [canWrite, openDetail, openEdit, handleToggleEnabled, handleDelete, modal],
  );

  const modalInitialValues = useMemo(() => {
    if (editing) {
      return {
        name: editing.name,
        is_enabled: editing.is_enabled,
        config_json: editing.config ? JSON.stringify(editing.config, null, 2) : undefined,
      };
    }
    return { connection_type: 'http', is_enabled: true };
  }, [editing]);

  const handleFinish = useCallback(
    async (values: Record<string, any>) => {
      try {
        if (editing) {
          const payload: Record<string, unknown> = {
            name: String(values.name ?? '').trim(),
            is_enabled: Boolean(values.is_enabled),
          };
          if (typeof values.remark === 'string' && values.remark.trim()) {
            payload.remark = values.remark.trim();
          }
          const rawConfig = String(values.config_json ?? '').trim();
          if (rawConfig) {
            let parsed: unknown;
            try {
              parsed = JSON.parse(rawConfig);
            } catch {
              messageApi.error('映射配置不是合法 JSON');
              return;
            }
            if (parsed == null || typeof parsed !== 'object' || Array.isArray(parsed)) {
              messageApi.error('映射配置必须是 JSON 对象');
              return;
            }
            payload.config = parsed;
          }
          await updateConnectionRow(editing.id, payload);
          messageApi.success('更新成功');
        } else {
          const config = Object.fromEntries(
            MAPPING_FIELDS.map((f) => [
              f.name,
              typeof values[f.name] === 'string' ? values[f.name].trim() : '',
            ]).filter(([, v]) => v),
          ) as Record<string, string>;
          await createConnectionRow({
            code: String(values.code ?? '').trim(),
            name: String(values.name ?? '').trim(),
            connection_type: values.connection_type,
            integration_uuid: values.integration_uuid || undefined,
            config: Object.keys(config).length ? config : undefined,
            is_enabled: Boolean(values.is_enabled ?? true),
            remark: typeof values.remark === 'string' && values.remark.trim() ? values.remark.trim() : undefined,
          });
          messageApi.success('创建成功');
        }
        setModalOpen(false);
        actionRef.current?.reload();
      } catch (error) {
        messageApi.error(error instanceof Error ? error.message : '保存失败');
      }
    },
    [editing, messageApi],
  );

  const coreOptions = useMemo(
    () =>
      eligibleIotConnections(coreConnections, formConnType).map((row) => ({
        value: row.uuid,
        label: `${row.name} (${row.code})`,
      })),
    [coreConnections, formConnType],
  );

  const detailColumns = useMemo<ProDescriptionsItemProps<ConnectionRow>[]>(
    () => [
      { title: '编码', dataIndex: 'code' },
      { title: '名称', dataIndex: 'name' },
      {
        title: '类型',
        dataIndex: 'connection_type',
        render: (_, row) =>
          CONNECTION_TYPE_OPTIONS.find((o) => o.value === row.connection_type)?.label ??
          row.connection_type,
      },
      {
        title: '健康状态',
        dataIndex: 'health_status',
        render: (_, row) => <HealthStatusTag value={row.health_status} />,
      },
      {
        title: '启用',
        dataIndex: 'is_enabled',
        render: (_, row) => (row.is_enabled ? '启用' : '停用'),
      },
      {
        title: '公共连接',
        dataIndex: 'integration_id',
        render: (_, row) => (row.integration_id != null ? `#${row.integration_id}` : '—'),
      },
      { title: '创建时间', dataIndex: 'created_at', valueType: 'dateTime' },
      { title: 'UUID', dataIndex: 'uuid' },
      {
        title: '映射配置（已脱敏）',
        dataIndex: 'config',
        span: 2,
        render: (_, row) =>
          row.config ? (
            <Typography.Paragraph
              style={{ marginBottom: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}
              copyable={{ text: JSON.stringify(row.config, null, 2) }}
            >
              {JSON.stringify(row.config, null, 2)}
            </Typography.Paragraph>
          ) : (
            '—'
          ),
      },
    ],
    [],
  );

  return (
    <ListPageTemplate>
      <UniTable<ConnectionRow>
        actionRef={actionRef}
        rowKey="id"
        columns={columns}
        columnPersistenceId="kuaiiot-connections-v1"
        permissionResource="kuaiiot:connection"
        showCreateButton
        createButtonText="新建接入配置"
        onCreate={openCreate}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        toolBarActionsAfterCreate={
          canWrite
            ? [
                <UniBatchDeleteButton
                  key="batch-delete"
                  selectedRowKeys={selectedRowKeys}
                  onConfirm={handleBatchDelete}
                  confirmTitle={(count) => `确定批量删除 ${count} 条连接？`}
                  confirmDescription="逐条删除，任一失败即停止并报告明细"
                />,
              ]
            : []
        }
        helpViewConfig={buildListPageHelpViewConfig('kuaiiot.connections')}
        defaultPageSize={20}
        request={async (params, sort, _filter, searchFormValues) => {
          try {
            const rows = await listConnectionRows();
            for (const row of rows) {
              allRowsRef.current.set(row.id, row);
            }
            let filtered = filterRowsByListKeyword(
              rows,
              pickListSearchKeyword(searchFormValues),
              (row) => [row.code, row.name, row.connection_type],
            );
            const connType = pickSearchString(searchFormValues, 'connection_type');
            if (connType) filtered = filtered.filter((row) => row.connection_type === connType);
            const health = pickSearchString(searchFormValues, 'health_status');
            if (health) filtered = filtered.filter((row) => (row.health_status || 'unknown') === health);
            const enabled = pickSearchTriStateBoolean(searchFormValues, 'is_enabled');
            if (enabled !== undefined) filtered = filtered.filter((row) => row.is_enabled === enabled);
            const sorted = sortRows(filtered, sort);
            const { current = 1, pageSize = 20 } = params;
            return {
              data: sorted.slice((current - 1) * pageSize, current * pageSize),
              success: true,
              total: sorted.length,
            };
          } catch (error) {
            messageApi.error(error instanceof Error ? error.message : '连接列表加载失败');
            return { data: [], success: false, total: 0 };
          }
        }}
      />

      <FormModalTemplate
        title={editing ? '编辑接入配置' : '新建接入配置'}
        open={modalOpen}
        onOpenChange={(open) => { setModalOpen(open); if (!open) setIotModalOpen(false); }}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        initialValues={modalInitialValues}
        formRef={formRef}
        onValuesChange={(changed) => {
          if (!editing && changed?.connection_type != null) {
            setFormConnType(String(changed.connection_type));
            formRef.current?.setFieldValue?.('integration_uuid', undefined);
          }
        }}
        onFinish={handleFinish}
      >
        {!editing ? (
          <>
            <ProFormText
              name="code"
              label="编码"
              rules={[{ required: true, message: '请填写编码' }]}
              fieldProps={{ maxLength: 50 }}
            />
            <ProFormText
              name="name"
              label="名称"
              rules={[{ required: true, message: '请填写名称' }]}
              fieldProps={{ maxLength: 100 }}
            />
            <SafeProFormSelect
              name="connection_type"
              label="类型"
              options={CONNECTION_TYPE_OPTIONS}
              rules={[{ required: true, message: '请选择类型' }]}
            />
            <Form.Item
              name="integration_uuid"
              label="应用连接"
              rules={[
                { required: formConnType !== 'http', message: '该类型必须绑定同租户公共连接' },
              ]}
              extra="选择当前租户的一条应用连接；可维护多条同类型连接。直接 HTTP 入站可不选。"
            >
              <Select allowClear showSearch loading={coreLoading} optionFilterProp="label" options={coreOptions} placeholder="选择已启用的应用连接（名称 / 编码）" />
            </Form.Item>
            <Space wrap style={{ marginBottom: 16 }}>
              {formConnType !== 'http' ? <Button disabled={coreLoading} onClick={() => setIotModalOpen(true)}>新建 IoT 应用连接</Button> : null}
              <Button loading={coreLoading} onClick={() => void loadCoreConnections()}>刷新连接</Button>
            </Space>
            {coreError ? <Alert type="warning" showIcon message="应用连接列表读取失败，请检查权限后刷新重试" style={{ marginBottom: 16 }} /> : null}
            {MAPPING_FIELDS.filter((f) => (f.mqttOnly ? formConnType === 'mqtt' : formConnType !== 'http')).map(
              (field) => (
                <ProFormText
                  key={field.name}
                  name={field.name}
                  label={field.label}
                  fieldProps={{ placeholder: '载荷中的点分路径' }}
                />
              ),
            )}
          </>
        ) : (
          <>
            <ProFormText
              name="name"
              label="名称"
              rules={[{ required: true, message: '请填写名称' }]}
              fieldProps={{ maxLength: 100 }}
            />
            <Divider titlePlacement="left" plain>
              高级配置
            </Divider>
            <ProFormTextArea
              name="config_json"
              label="映射配置（JSON，可空表示不修改）"
              fieldProps={{ rows: 4, placeholder: '{"topic": "plant/+"}' }}
            />
          </>
        )}
        <ProFormSwitch name="is_enabled" label="启用" />
        {!editing ? (
          <ProFormTextArea name="remark" label="备注" fieldProps={{ rows: 2, maxLength: 500 }} />
        ) : null}
      </FormModalTemplate>

      <IotConnectionModal
        key={formConnType}
        open={iotModalOpen && modalOpen && !editing}
        type={formConnType}
        onOpenChange={setIotModalOpen}
        onCreated={(connection) => {
          setCoreConnections(rows => [...rows.filter(row => row.uuid !== connection.uuid), connection]);
          formRef.current?.setFieldValue('integration_uuid', connection.uuid);
          setCoreError(false);
        }}
      />

      <DetailDrawerTemplate
        title={detail ? `接入配置：${detail.name}` : '接入配置详情'}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        size={DRAWER_CONFIG.SMALL_WIDTH}
        loading={detailLoading}
        columns={detailColumns}
        dataSource={detail ?? undefined}
        column={2}
      />
    </ListPageTemplate>
  );
};

export default ConnectionsPage;
