import React, { useCallback, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns, ProDescriptionsItemProps } from '@ant-design/pro-components';
import { Button, Form, Input, InputNumber, Modal, Select, Switch, Table, Typography, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { rowActionKind, rowActionLabelKeep } from '../../../../components/uni-action';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { buildDetailDrawerEditExtra } from '../../../kuaizhizao/pages/equipment-management/shared/equipmentMasterDataDetail';
import { formatDateTimeBySiteSetting } from '../../../../utils/format';
import { IotMasterDetailDrawer } from '../shared/iotMasterDetailDrawer';
import {
  buildConnectionTypeOptions,
  buildPayloadFormatOptions,
  QOS_OPTIONS,
  translateHealthStatus,
  translatePayloadFormat,
} from '../../constants/formOptions';
import {
  IOT_LIST_COL,
  renderIotConnectionTypeMarker,
  renderIotEnabledMarker,
  renderIotHealthMarker,
} from '../../utils/iotListPresentation';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';
import {
  createConnection,
  deleteConnection,
  healthCheckConnection,
  listConnectionRecentMessages,
  listConnections,
  pullConnectionTelemetry,
  syncConnectionDevices,
  updateConnection,
  type Connection,
  type ConnectionRecentMessage,
} from '../../services/kuaiiot';

const ConnectionsPage: React.FC = () => {
  const { t } = useTranslation();
  const perms = useResourcePermissions('kuaiiot:connection');
  const actionRef = useRef<ActionType>();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Connection | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [detail, setDetail] = useState<Connection | null>(null);
  const [recentMessages, setRecentMessages] = useState<ConnectionRecentMessage[]>([]);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [messageDetail, setMessageDetail] = useState<ConnectionRecentMessage | null>(null);
  const connectionType = Form.useWatch('connection_type', form);
  const connectionTypeOptions = buildConnectionTypeOptions(t);
  const payloadFormatOptions = buildPayloadFormatOptions(t);

  const loadRecentMessages = useCallback(
    async (row: Connection, opts?: { notifyEmpty?: boolean }) => {
      if (row.connection_type !== 'mqtt') {
        setRecentMessages([]);
        return;
      }
      setMessagesLoading(true);
      try {
        const res = await listConnectionRecentMessages(row.uuid, 20);
        setRecentMessages(res.items || []);
        if (opts?.notifyEmpty && !res.items?.length) {
          message.info(t('app.kuaiiot.message.recentMessagesEmpty'));
        }
      } catch {
        setRecentMessages([]);
        message.error(t('app.kuaiiot.message.recentMessagesFailed'));
      } finally {
        setMessagesLoading(false);
      }
    },
    [t],
  );

  const columns: ProColumns<Connection>[] = alignProColumns(
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
        title: t('app.kuaiiot.field.type'),
        dataIndex: 'connection_type',
        ...IOT_LIST_COL.markerMd,
        render: (_, row) => renderIotConnectionTypeMarker(t, row.connection_type),
      },
      {
        title: t('app.kuaiiot.field.health'),
        dataIndex: 'health_status',
        ...IOT_LIST_COL.marker,
        render: (_, row) => renderIotHealthMarker(t, row.health_status),
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
                  void loadRecentMessages(row);
                }}
              />,
            );
          }
          if (perms.canUpdate) {
            nodes.push(
              <Button key="edit" {...rowActionKind('update')} onClick={() => openEdit(row)} />,
              <Button
                key="sync"
                {...rowActionKind('skip')}
                {...rowActionLabelKeep()}
                onClick={async () => {
                  const res = await syncConnectionDevices(row.uuid);
                  message.success(t('app.kuaiiot.message.syncedDevices', { count: res.synced_devices }));
                  actionRef.current?.reload();
                }}
              >
                同步
              </Button>,
            );
            if (row.connection_type === 'thingsboard' || row.connection_type === 'jetlinks') {
              nodes.push(
                <Button
                  key="pull"
                  {...rowActionKind('skip')}
                  {...rowActionLabelKeep()}
                  onClick={async () => {
                    const res = await pullConnectionTelemetry(row.uuid);
                    message.success(
                      t('app.kuaiiot.message.pulledTelemetry', {
                        ingested: res.ingested_devices,
                        skipped: res.skipped_devices,
                      }),
                    );
    actionRef.current?.reload();
                  }}
                >
                  拉取
                </Button>,
              );
            }
            nodes.push(
              <Button
                key="health"
                {...rowActionKind('skip')}
                {...rowActionLabelKeep()}
                onClick={async () => {
                  const res = await healthCheckConnection(row.uuid);
                  message.info(`${t('app.kuaiiot.field.health')}: ${translateHealthStatus(t, res.health_status)}`);
    actionRef.current?.reload();
                }}
              >
                检查
              </Button>,
            );
          }
          if (perms.canDelete) {
            nodes.push(
              <Button
                key="delete"
                {...rowActionKind('delete')}
                onClick={async () => {
                  await deleteConnection(row.uuid);
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

  const detailColumns = useMemo<ProDescriptionsItemProps<Connection>[]>(
    () => [
      { title: t('common.code'), dataIndex: 'code', copyable: true },
      { title: t('common.name'), dataIndex: 'name' },
      {
        title: t('app.kuaiiot.field.type'),
        dataIndex: 'connection_type',
        render: (_, row) => renderIotConnectionTypeMarker(t, row.connection_type),
      },
      {
        title: t('app.kuaiiot.field.health'),
        dataIndex: 'health_status',
        render: (_, row) => renderIotHealthMarker(t, row.health_status),
      },
      {
        title: t('common.enabled'),
        dataIndex: 'is_enabled',
        render: (_, row) => renderIotEnabledMarker(t, row.is_enabled),
      },
      {
        title: t('app.kuaiiot.field.lastSeen'),
        dataIndex: 'last_health_at',
        render: (_, row) => (row.last_health_at ? formatDateTimeBySiteSetting(row.last_health_at) : '-'),
      },
      { title: t('common.remark'), dataIndex: 'remark' },
    ],
    [t],
  );

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      is_enabled: true,
      connection_type: 'http_webhook',
      topic_filter: 'kuaiiot/ingest/+',
      broker_port: 1883,
      qos: 1,
      payload_format: 'auto',
    });
    setOpen(true);
  };

  const openEdit = (row: Connection) => {
    setEditing(row);
    form.setFieldsValue({
      ...row,
      base_url: row.config?.base_url,
      username: row.config?.username,
      password: row.config?.password,
      token: row.config?.token,
      broker_host: row.config?.broker_host,
      broker_port: row.config?.broker_port,
      topic_filter: row.config?.topic_filter,
      qos: row.config?.qos,
      use_tls: row.config?.use_tls,
      payload_format: row.config?.payload_format || 'auto',
      client_id: row.config?.client_id,
    });
    setOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const payload = {
      code: values.code,
      name: values.name,
      connection_type: values.connection_type,
      is_enabled: values.is_enabled,
      remark: values.remark,
      config: {
        base_url: values.base_url,
        username: values.username,
        password: values.password,
        token: values.token,
        broker_host: values.broker_host,
        broker_port: values.broker_port,
        topic_filter: values.topic_filter,
        qos: values.qos,
        use_tls: values.use_tls,
        payload_format: values.payload_format || 'auto',
        client_id: values.client_id,
      },
    };
    if (editing) {
      await updateConnection(editing.uuid, payload);
      message.success(t('common.updateSuccess'));
    } else {
      await createConnection(payload);
      message.success(t('common.createSuccess'));
    }
    setOpen(false);
    actionRef.current?.reload();
  };

  return (
    <ListPageTemplate>
      <UniTable<Connection>
        viewTypes={['table', 'help']}
          helpViewConfig={buildListPageHelpViewConfig('kuaiiot.connections')}
        actionRef={actionRef}
        columns={columns}
        rowKey="uuid"
        columnPersistenceId="apps.kuaiiot.pages.connections.list-v3"
        request={async (params) => {
          const res = await listConnections({
            page: params.current,
            page_size: params.pageSize,
            q: params.keyword as string | undefined,
          });
          return { data: res.items, total: res.total, success: true };
        }}
        enableRowSelection={perms.canDelete}
        showDeleteButton={perms.canDelete}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => deleteConnection(String(key))));
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
          setRecentMessages([]);
        }}
        detail={detail}
        detailColumns={detailColumns}
        extra={buildDetailDrawerEditExtra(t, Boolean(detail) && perms.canUpdate, () => {
          if (!detail) return;
          setDrawerVisible(false);
          openEdit(detail);
        })}
        supplementaryTitle={
          detail?.connection_type === 'mqtt' ? t('app.kuaiiot.tab.recentMessages') : undefined
        }
        supplementary={
          detail?.connection_type === 'mqtt' ? (
            <div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
                <Button
                  size="small"
                  loading={messagesLoading}
                  onClick={() => detail && void loadRecentMessages(detail, { notifyEmpty: true })}
                >
                  {t('app.kuaiiot.action.refreshMessages')}
                </Button>
              </div>
              <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
                {t('app.kuaiiot.message.recentMessagesHint')}
              </Typography.Paragraph>
              <Table<ConnectionRecentMessage>
                size="small"
                rowKey="uuid"
                loading={messagesLoading}
                pagination={false}
                dataSource={recentMessages}
                locale={{ emptyText: t('app.kuaiiot.message.recentMessagesEmpty') }}
                columns={[
                  {
                    title: t('app.kuaiiot.field.topicFilter'),
                    dataIndex: 'topic',
                    ellipsis: true,
                    width: 160,
                  },
                  {
                    title: t('app.kuaiiot.field.payloadFormat'),
                    dataIndex: 'payload_format',
                    width: 120,
                    render: (value) => translatePayloadFormat(t, value),
                  },
                  {
                    title: t('common.createdAt'),
                    dataIndex: 'received_at',
                    width: 160,
                    render: (value) => (value ? formatDateTimeBySiteSetting(value) : '-'),
                  },
                  {
                    title: t('app.kuaiiot.field.messageBody'),
                    dataIndex: 'payload',
                    ellipsis: true,
                    render: (_, row) => {
                      const preview = JSON.stringify(row.payload ?? {});
                      return preview.length > 80 ? `${preview.slice(0, 80)}...` : preview;
                    },
                  },
                  {
                    title: t('common.action'),
                    key: 'action',
                    width: 80,
                    render: (_, row) => (
                      <Button type="link" size="small" onClick={() => setMessageDetail(row)}>
                        {t('app.kuaiiot.action.viewMessageBody')}
                      </Button>
                    ),
                  },
                ]}
              />
            </div>
          ) : undefined
        }
      />

      <Modal
        open={!!messageDetail}
        title={t('app.kuaiiot.field.messageBody')}
        onCancel={() => setMessageDetail(null)}
        footer={null}
        width={720}
        destroyOnHidden
      >
        {messageDetail ? (
          <>
            <Typography.Paragraph>
              <strong>{t('app.kuaiiot.field.payloadFormat')}:</strong>{' '}
              {translatePayloadFormat(t, messageDetail.payload_format)}
            </Typography.Paragraph>
            {messageDetail.error ? (
              <Typography.Paragraph type="danger">{messageDetail.error}</Typography.Paragraph>
            ) : null}
            {messageDetail.ingest_summary && Object.keys(messageDetail.ingest_summary).length > 0 ? (
              <>
                <Typography.Title level={5}>{t('app.kuaiiot.field.ingestSummary')}</Typography.Title>
                <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 160, overflow: 'auto' }}>
                  {JSON.stringify(messageDetail.ingest_summary, null, 2)}
                </pre>
              </>
            ) : null}
            <Typography.Title level={5}>{t('app.kuaiiot.field.messageBody')}</Typography.Title>
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, maxHeight: 420, overflow: 'auto' }}>
              {JSON.stringify(messageDetail.payload, null, 2)}
            </pre>
          </>
        ) : null}
      </Modal>

      <Modal
        open={open}
        title={editing ? t('common.edit') : t('common.create')}
        onCancel={() => setOpen(false)}
        onOk={handleSubmit}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label={t('common.code')} rules={[{ required: !editing }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="connection_type" label={t('app.kuaiiot.field.type')} rules={[{ required: true }]}>
            <Select options={connectionTypeOptions} />
          </Form.Item>
          {(connectionType === 'thingsboard' || connectionType === 'jetlinks') && (
            <>
              <Form.Item name="base_url" label={t('app.kuaiiot.field.baseUrl')}>
                <Input />
              </Form.Item>
              <Form.Item name="username" label={t('app.kuaiiot.field.username')}>
                <Input />
              </Form.Item>
              <Form.Item name="password" label={t('app.kuaiiot.field.password')}>
                <Input.Password />
              </Form.Item>
              <Form.Item name="token" label={t('app.kuaiiot.field.token')}>
                <Input />
              </Form.Item>
            </>
          )}
          {connectionType === 'mqtt' && (
            <>
              <Form.Item name="broker_host" label={t('app.kuaiiot.field.brokerHost')} rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item name="broker_port" label={t('app.kuaiiot.field.brokerPort')}>
                <InputNumber min={1} max={65535} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="topic_filter" label={t('app.kuaiiot.field.topicFilter')}>
                <Input placeholder={t('app.kuaiiot.placeholder.topicFilter')} />
              </Form.Item>
              <Form.Item name="qos" label={t('app.kuaiiot.field.qos')}>
                <Select options={QOS_OPTIONS} />
              </Form.Item>
              <Form.Item name="payload_format" label={t('app.kuaiiot.field.payloadFormat')}>
                <Select options={payloadFormatOptions} />
              </Form.Item>
              <Form.Item name="client_id" label={t('app.kuaiiot.field.clientId')}>
                <Input placeholder={t('app.kuaiiot.placeholder.clientId')} />
              </Form.Item>
              <Form.Item name="username" label={t('app.kuaiiot.field.username')}>
                <Input />
              </Form.Item>
              <Form.Item name="password" label={t('app.kuaiiot.field.password')}>
                <Input.Password />
              </Form.Item>
              <Form.Item name="use_tls" label={t('app.kuaiiot.field.useTls')} valuePropName="checked">
                <Switch />
              </Form.Item>
            </>
          )}
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

export default ConnectionsPage;
