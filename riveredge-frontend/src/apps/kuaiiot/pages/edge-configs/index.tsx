import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns, ProDescriptionsItemProps } from '@ant-design/pro-components';
import { Button, Form, Input, Modal, Select, Switch, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { rowActionKind } from '../../../../components/uni-action';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { formatDateTimeBySiteSetting } from '../../../../utils/format';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { buildDetailDrawerEditExtra } from '../../../kuaizhizao/pages/equipment-management/shared/equipmentMasterDataDetail';
import { IotMasterDetailDrawer } from '../shared/iotMasterDetailDrawer';
import { buildProtocolOptions } from '../../constants/formOptions';
import {
  IOT_LIST_COL,
  renderIotAgentStatusMarker,
  renderIotEnabledMarker,
  renderIotProtocolMarker,
} from '../../utils/iotListPresentation';
import {
  createEdgeConfig,
  deleteEdgeConfig,
  exportEdgeAgentSpec,
  listDevices,
  listEdgeConfigs,
  updateEdgeConfig,
  type Device,
  type EdgeConfig,
} from '../../services/kuaiiot';
import { getAntdModal } from '../../../../utils/antdAppApis';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';

const DEFAULT_CONFIG = JSON.stringify(
  {
    host: '192.168.1.10',
    port: 502,
    unit_id: 1,
    poll_interval_seconds: 5,
    registers: [{ tag_key: 'temp', function: 'holding', address: 100, data_type: 'float32' }],
    publish: { mode: 'http_ingest', buffer_max: 100 },
  },
  null,
  2,
);

const EdgeConfigsPage: React.FC = () => {
  const { t } = useTranslation();
  const perms = useResourcePermissions('kuaiiot:edge-config');
  const actionRef = useRef<ActionType>();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<EdgeConfig | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [detail, setDetail] = useState<EdgeConfig | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const deviceLabelMap = Object.fromEntries(devices.map((item) => [item.id, `${item.code} - ${item.name}`]));
  const protocolOptions = buildProtocolOptions(t);

  useEffect(() => {
    (async () => {
      const res = await listDevices({ page: 1, page_size: 500 });
      setDevices(res.items);
    })();
  }, []);

  const columns: ProColumns<EdgeConfig>[] = alignProColumns(
    [
      {
        title: t('common.code'),
        dataIndex: 'code',
        ...IOT_LIST_COL.code,
      },
      {
        title: t('common.name'),
        dataIndex: 'name',
        ...IOT_LIST_COL.name,
      },
      {
        title: t('app.kuaiiot.field.device'),
        dataIndex: 'device_id',
        ...IOT_LIST_COL.ref,
        render: (_, row) => deviceLabelMap[row.device_id] || row.device_id,
      },
      {
        title: t('app.kuaiiot.field.protocol'),
        dataIndex: 'protocol',
        ...IOT_LIST_COL.markerMd,
        render: (_, row) => renderIotProtocolMarker(t, row.protocol),
      },
      {
        title: t('app.kuaiiot.field.configVersion'),
        dataIndex: 'config_version',
        ...IOT_LIST_COL.count,
      },
      {
        title: t('app.kuaiiot.field.agentStatus'),
        dataIndex: 'agent_status',
        ...IOT_LIST_COL.markerMd,
        render: (_, row) => renderIotAgentStatusMarker(t, row.agent_status),
      },
      {
        title: t('app.kuaiiot.field.bufferPending'),
        dataIndex: 'buffer_pending_count',
        ...IOT_LIST_COL.count,
      },
      {
        title: t('app.kuaiiot.field.lastHeartbeat'),
        dataIndex: 'last_agent_heartbeat_at',
        ...IOT_LIST_COL.datetime,
        render: (_, row) =>
          row.last_agent_heartbeat_at ? formatDateTimeBySiteSetting(row.last_agent_heartbeat_at) : '-',
      },
      {
        title: t('common.enabled'),
        dataIndex: 'is_enabled',
        ...IOT_LIST_COL.marker,
        render: (_, row) => renderIotEnabledMarker(t, row.is_enabled),
      },
      {
        title: t('common.action'),
        key: 'action',
        fixed: 'right',
        hideInSearch: true,
        render: (_, row) => {
          const nodes: React.ReactNode[] = [];
          if (perms.canRead) {
            nodes.push(
              <Button
                key="detail"
                {...rowActionKind('read')}
                onClick={() => {
                  setDetail(row);
                  setDrawerVisible(true);
                }}
              />,
              <Button
                key="export"
                {...rowActionKind('export')}
                onClick={async () => {
                  const spec = await exportEdgeAgentSpec(row.uuid);
                  getAntdModal().info({
                    title: t('app.kuaiiot.action.exportAgentSpec'),
                    width: 720,
                    content: <pre style={{ maxHeight: 420, overflow: 'auto' }}>{JSON.stringify(spec, null, 2)}</pre>,
                  });
                }}
              />,
            );
          }
          if (perms.canUpdate) {
            nodes.push(
              <Button key="edit" {...rowActionKind('update')} onClick={() => openEdit(row)} />,
            );
          }
          if (perms.canDelete) {
            nodes.push(
              <Button
                key="delete"
                {...rowActionKind('delete')}
                onClick={async () => {
                  await deleteEdgeConfig(row.uuid);
                  message.success(t('common.deleteSuccess'));
    actionRef.current?.reload();
                }}
              />,
            );
          }
          return nodes;
        },
      },
    ],
    GLOBAL_DOC_LIST_FIELD_RANK,
  );

  const detailColumns = useMemo<ProDescriptionsItemProps<EdgeConfig>[]>(
    () => [
      { title: t('common.code'), dataIndex: 'code', copyable: true },
      { title: t('common.name'), dataIndex: 'name' },
      {
        title: t('app.kuaiiot.field.device'),
        dataIndex: 'device_id',
        render: (_, row) => deviceLabelMap[row.device_id] || row.device_id,
      },
      {
        title: t('app.kuaiiot.field.protocol'),
        dataIndex: 'protocol',
        render: (_, row) => renderIotProtocolMarker(t, row.protocol),
      },
      { title: t('app.kuaiiot.field.configVersion'), dataIndex: 'config_version' },
      {
        title: t('app.kuaiiot.field.agentStatus'),
        dataIndex: 'agent_status',
        render: (_, row) => renderIotAgentStatusMarker(t, row.agent_status),
      },
      { title: t('app.kuaiiot.field.bufferPending'), dataIndex: 'buffer_pending_count' },
      {
        title: t('app.kuaiiot.field.lastHeartbeat'),
        dataIndex: 'last_agent_heartbeat_at',
        render: (_, row) =>
          row.last_agent_heartbeat_at ? formatDateTimeBySiteSetting(row.last_agent_heartbeat_at) : '-',
      },
      {
        title: t('common.enabled'),
        dataIndex: 'is_enabled',
        render: (_, row) => renderIotEnabledMarker(t, row.is_enabled),
      },
      { title: t('common.remark'), dataIndex: 'remark' },
    ],
    [deviceLabelMap, t],
  );

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ protocol: 'modbus_tcp', is_enabled: true, config_json: DEFAULT_CONFIG });
    setOpen(true);
  };

  const openEdit = (row: EdgeConfig) => {
    setEditing(row);
    form.setFieldsValue({ ...row, config_json: JSON.stringify(row.config, null, 2) });
    setOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    let config: Record<string, unknown>;
    try {
      config = JSON.parse(values.config_json);
    } catch {
      message.error(t('app.kuaiiot.message.invalidJson'));
      return;
    }
    const payload = {
      code: values.code,
      name: values.name,
      device_id: values.device_id,
      protocol: values.protocol,
      config,
      is_enabled: values.is_enabled,
      remark: values.remark,
    };
    if (editing) {
      await updateEdgeConfig(editing.uuid, payload);
      message.success(t('common.updateSuccess'));
    } else {
      await createEdgeConfig(payload);
      message.success(t('common.createSuccess'));
    }
    setOpen(false);
    actionRef.current?.reload();
  };

  return (
    <ListPageTemplate>
      <UniTable<EdgeConfig>
        viewTypes={['table', 'help']}
          helpViewConfig={buildListPageHelpViewConfig('kuaiiot.edgeConfigs')}
        actionRef={actionRef}
        columns={columns}
        rowKey="uuid"
        columnPersistenceId="apps.kuaiiot.pages.edge-configs.list-v3"
        request={async (params) => {
          const res = await listEdgeConfigs({
            page: params.current,
            page_size: params.pageSize,
            q: params.keyword as string | undefined,
          });
          return { data: res.items, total: res.total, success: true };
        }}
        enableRowSelection={perms.canDelete}
        showDeleteButton={perms.canDelete}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => deleteEdgeConfig(String(key))));
          message.success(t('common.batchDeleteSuccess', { count: keys.length }));
          actionRef.current?.reload();
        }}
        toolBarActions={
          perms.canCreate
            ? [
                <Button {...rowActionKind('create')} key="create" type="primary" onClick={openCreate}>
                  {t('common.create')}
                </Button>,
              ]
            : []
        }
      />

      <IotMasterDetailDrawer
        title={t('common.detail')}
        open={drawerVisible}
        onClose={() => {
          setDrawerVisible(false);
          setDetail(null);
        }}
        detail={detail}
        detailColumns={detailColumns}
        extra={buildDetailDrawerEditExtra(t, Boolean(detail) && perms.canUpdate, () => {
          if (!detail) return;
          setDrawerVisible(false);
          openEdit(detail);
        })}
      />

      <Modal open={open} title={editing ? t('common.edit') : t('common.create')} onCancel={() => setOpen(false)} onOk={handleSubmit} destroyOnHidden width={760}>
        <Form form={form} layout="vertical">
          <Form.Item name="code" label={t('common.code')} rules={[{ required: !editing }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="device_id" label={t('app.kuaiiot.field.device')} rules={[{ required: true }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={devices.map((item) => ({ label: `${item.code} - ${item.name}`, value: item.id }))}
            />
          </Form.Item>
          <Form.Item name="protocol" label={t('app.kuaiiot.field.protocol')} rules={[{ required: true }]}>
            <Select options={protocolOptions} />
          </Form.Item>
          <Form.Item name="config_json" label={t('app.kuaiiot.field.edgeConfigJson')} rules={[{ required: true }]}>
            <Input.TextArea rows={12} />
          </Form.Item>
          <Form.Item name="remark" label={t('common.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="is_enabled" label={t('common.enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageTemplate>
  );
};

export default EdgeConfigsPage;
