import React, { useEffect, useRef, useState } from 'react';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { Button, Form, Input, InputNumber, Modal, Select, Switch, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { rowActionKind, rowActionLabelKeep } from '../../../../components/uni-action';
import { UniBatchMenuButton } from '../../../../components/uni-batch';
import { MultiTabListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { buildSeverityOptions, OPERATOR_OPTIONS } from '../../constants/formOptions';
import {
  IOT_LIST_COL,
  renderIotAlertStatusTag,
  renderIotRuleTypeMarker,
  renderIotSeverityMarker,
} from '../../utils/iotListPresentation';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';
import {
  acknowledgeAlert,
  createAlertRule,
  deleteAlertRule,
  listAlertRules,
  listAlerts,
  listDevices,
  listEquipmentOptions,
  listTags,
  updateAlertRule,
  type AlertRecord,
  type AlertRule,
  type Device,
  type TagDefinition,
} from '../../services/kuaiiot';

const AlertsPage: React.FC = () => {
  const { t } = useTranslation();
  const rulePerms = useResourcePermissions('kuaiiot:alert');
  const [activeTabKey, setActiveTabKey] = useState('rules');
  const [alertSelectedKeys, setAlertSelectedKeys] = useState<React.Key[]>([]);
  const ruleActionRef = useRef<ActionType>();
  const alertActionRef = useRef<ActionType>();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<AlertRule | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [equipmentOptions, setEquipmentOptions] = useState<{ label: string; value: string }[]>([]);
  const [deviceTags, setDeviceTags] = useState<TagDefinition[]>([]);
  const selectedDeviceId = Form.useWatch('device_id', form);
  const severityOptions = buildSeverityOptions(t);
  const deviceLabelMap = Object.fromEntries(devices.map((item) => [item.id, `${item.code} - ${item.name}`]));

  useEffect(() => {
    (async () => {
      const [deviceRes, equipmentRes] = await Promise.all([
        listDevices({ page: 1, page_size: 500 }),
        listEquipmentOptions().catch(() => []),
      ]);
      setDevices(deviceRes.items);
      setEquipmentOptions(equipmentRes);
    })();
  }, []);

  useEffect(() => {
    if (!selectedDeviceId) {
      setDeviceTags([]);
      return;
    }
    let cancelled = false;
    (async () => {
      const res = await listTags({ page: 1, page_size: 500, device_id: selectedDeviceId });
      if (!cancelled) {
        setDeviceTags(res.items);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedDeviceId]);

  const ruleColumns: ProColumns<AlertRule>[] = alignProColumns(
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
        title: t('app.kuaiiot.field.ruleType'),
        dataIndex: 'rule_type',
        ...IOT_LIST_COL.markerMd,
        render: (_, row) => renderIotRuleTypeMarker(t, row.rule_type),
      },
      {
        title: t('app.kuaiiot.field.device'),
        dataIndex: 'device_id',
        ...IOT_LIST_COL.ref,
        render: (_, row) => deviceLabelMap[row.device_id || 0] || row.equipment_uuid || '-',
      },
      {
        title: t('app.kuaiiot.field.tagKey'),
        dataIndex: 'tag_key',
        ...IOT_LIST_COL.tagKey,
      },
      {
        title: t('app.kuaiiot.field.operator'),
        dataIndex: 'operator',
        ...IOT_LIST_COL.marker,
      },
      {
        title: t('app.kuaiiot.field.threshold'),
        ...IOT_LIST_COL.markerMd,
        render: (_, row) => row.threshold_number ?? row.threshold_text ?? '-',
      },
      {
        title: t('app.kuaiiot.field.severity'),
        dataIndex: 'severity',
        ...IOT_LIST_COL.marker,
        render: (_, row) => renderIotSeverityMarker(t, row.severity),
      },
      {
        title: t('common.action'),
        key: 'action',
        fixed: 'right',
        hideInSearch: true,
        render: (_, row) => {
          const nodes: React.ReactNode[] = [];
          if (rulePerms.canUpdate) {
            nodes.push(
              <Button key="edit" {...rowActionKind('update')} onClick={() => openEdit(row)} />,
            );
          }
          if (rulePerms.canDelete) {
            nodes.push(
              <Button
                key="delete"
                {...rowActionKind('delete')}
                onClick={async () => {
                  await deleteAlertRule(row.uuid);
                  message.success(t('common.deleteSuccess'));
                  ruleActionRef.current?.reload();
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

  const alertColumns: ProColumns<AlertRecord>[] = alignProColumns(
    [
      {
        title: t('app.kuaiiot.field.device'),
        dataIndex: 'device_id',
        ...IOT_LIST_COL.ref,
        render: (_, row) => deviceLabelMap[row.device_id] || row.device_id,
      },
      {
        title: t('app.kuaiiot.field.tagKey'),
        dataIndex: 'tag_key',
        ...IOT_LIST_COL.tagKey,
      },
      {
        title: t('app.kuaiiot.field.severity'),
        dataIndex: 'severity',
        ...IOT_LIST_COL.marker,
        render: (_, row) => renderIotSeverityMarker(t, row.severity),
      },
      {
        title: t('app.kuaiiot.field.message'),
        dataIndex: 'message',
        ...IOT_LIST_COL.message,
      },
      {
        title: t('common.status'),
        key: 'lifecycle',
        dataIndex: 'status',
        fixed: 'right',
        render: (_, row) => renderIotAlertStatusTag(t, row.status),
      },
      {
        title: t('common.action'),
        key: 'action',
        fixed: 'right',
        hideInSearch: true,
        render: (_, row) =>
          row.status === 'open' && rulePerms.canUpdate ? (
            <Button
              key="ack"
              {...rowActionKind('skip')}
              {...rowActionLabelKeep()}
              onClick={async () => {
                await acknowledgeAlert(row.uuid);
                message.success(t('common.updateSuccess'));
                alertActionRef.current?.reload();
              }}
            >
              确认
            </Button>
          ) : null,
      },
    ],
    GLOBAL_DOC_LIST_FIELD_RANK,
  );

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      severity: 'warning',
      cooldown_seconds: 300,
      operator: 'gt',
      rule_type: 'threshold',
      notify_enabled: true,
      is_enabled: true,
    });
    setOpen(true);
  };

  const openEdit = (row: AlertRule) => {
    setEditing(row);
    form.setFieldsValue(row);
    setOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    if (editing) {
      await updateAlertRule(editing.uuid, values);
      message.success(t('common.updateSuccess'));
    } else {
      await createAlertRule(values);
      message.success(t('common.createSuccess'));
    }
    setOpen(false);
    ruleActionRef.current?.reload();
  };

  const handleBatchAcknowledge = async (keys: React.Key[]) => {
    await Promise.all(keys.map((key) => acknowledgeAlert(String(key))));
    message.success(t('common.updateSuccess'));
    setAlertSelectedKeys([]);
    alertActionRef.current?.reload();
  };

  const tagKeyOptions = deviceTags.map((item) => ({
    label: `${item.tag_key} - ${item.name}`,
    value: item.tag_key,
  }));

  return (
    <>
      <MultiTabListPageTemplate
        activeTabKey={activeTabKey}
        onTabChange={setActiveTabKey}
        preserveMounted
        tabs={[
          {
            key: 'rules',
            label: t('app.kuaiiot.tab.alertRules'),
            children: (
              <UniTable<AlertRule>
        viewTypes={['table', 'help']}
          helpViewConfig={buildListPageHelpViewConfig('kuaiiot.alerts')}
                actionRef={ruleActionRef}
                columns={ruleColumns}
                rowKey="uuid"
                columnPersistenceId="apps.kuaiiot.pages.alerts.rules.list-v3"
                request={async (params) => {
                  const res = await listAlertRules({
                    page: params.current,
                    page_size: params.pageSize,
                    q: params.keyword as string | undefined,
                  });
                  return { data: res.items, total: res.total, success: true };
                }}
                showCreateButton={rulePerms.canCreate}
                createButtonText={t('app.kuaiiot.action.createAlertRule')}
                onCreate={openCreate}
                enableRowSelection={rulePerms.canDelete}
                showDeleteButton={rulePerms.canDelete}
                onDelete={async (keys) => {
                  await Promise.all(keys.map((key) => deleteAlertRule(String(key))));
                  message.success(t('common.batchDeleteSuccess', { count: keys.length }));
                  ruleActionRef.current?.reload();
                }}
              />
            ),
          },
          {
            key: 'records',
            label: t('app.kuaiiot.tab.alertRecords'),
            children: (
              <UniTable<AlertRecord>
                actionRef={alertActionRef}
                columns={alertColumns}
                rowKey="uuid"
                columnPersistenceId="apps.kuaiiot.pages.alerts.records.list-v3"
                request={async (params) => {
                  const res = await listAlerts({ page: params.current, page_size: params.pageSize });
                  return { data: res.items, total: res.total, success: true };
                }}
                enableRowSelection={rulePerms.canUpdate}
                selectedRowKeys={alertSelectedKeys}
                onRowSelectionChange={setAlertSelectedKeys}
                toolBarActionsAfterDelete={
                  rulePerms.canUpdate
                    ? [
                        <UniBatchMenuButton
                          key="batch-ack"
                          selectedRowKeys={alertSelectedKeys}
                          buttonText={t('app.kuaiiot.action.batchAcknowledge')}
                          menuItems={[
                            {
                              key: 'acknowledge',
                              label: t('app.kuaiiot.action.acknowledge'),
                              onClick: handleBatchAcknowledge,
                            },
                          ]}
                        />,
                      ]
                    : []
                }
              />
            ),
          },
        ]}
      />

      <Modal open={open} title={editing ? t('common.edit') : t('common.create')} onCancel={() => setOpen(false)} onOk={handleSubmit} destroyOnHidden width={720}>
        <Form form={form} layout="vertical">
          <Form.Item name="code" label={t('common.code')} rules={[{ required: !editing }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="rule_type" label={t('app.kuaiiot.field.ruleType')} rules={[{ required: true }]}>
            <Select
              options={[
                { label: t('app.kuaiiot.ruleType.threshold'), value: 'threshold' },
                { label: t('app.kuaiiot.ruleType.offline'), value: 'offline' },
              ]}
            />
          </Form.Item>
          <Form.Item name="device_id" label={t('app.kuaiiot.field.device')}>
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={devices.map((item) => ({ label: `${item.code} - ${item.name}`, value: item.id }))}
            />
          </Form.Item>
          <Form.Item name="equipment_uuid" label={t('app.kuaiiot.field.equipment')}>
            <Select allowClear showSearch optionFilterProp="label" options={equipmentOptions} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.rule_type !== cur.rule_type || prev.device_id !== cur.device_id}>
            {({ getFieldValue }) =>
              getFieldValue('rule_type') === 'offline' ? null : (
                <>
                  <Form.Item name="tag_key" label={t('app.kuaiiot.field.tagKey')} rules={[{ required: true }]}>
                    <Select
                      showSearch
                      optionFilterProp="label"
                      options={tagKeyOptions}
                      placeholder={
                        !getFieldValue('device_id')
                          ? t('app.kuaiiot.message.selectDeviceFirst')
                          : tagKeyOptions.length
                            ? undefined
                            : t('app.kuaiiot.message.noTagsForDevice')
                      }
                      disabled={!getFieldValue('device_id')}
                    />
                  </Form.Item>
                  <Form.Item name="operator" label={t('app.kuaiiot.field.operator')} rules={[{ required: true }]}>
                    <Select options={OPERATOR_OPTIONS} />
                  </Form.Item>
                  <Form.Item name="threshold_number" label={t('app.kuaiiot.field.thresholdNumber')}>
                    <InputNumber style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="threshold_text" label={t('app.kuaiiot.field.thresholdText')}>
                    <Input />
                  </Form.Item>
                </>
              )
            }
          </Form.Item>
          <Form.Item name="severity" label={t('app.kuaiiot.field.severity')}>
            <Select options={severityOptions} />
          </Form.Item>
          <Form.Item name="cooldown_seconds" label={t('app.kuaiiot.field.cooldownSeconds')}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="remark" label={t('common.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="notify_enabled" label={t('app.kuaiiot.field.notifyEnabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="is_enabled" label={t('common.enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default AlertsPage;
