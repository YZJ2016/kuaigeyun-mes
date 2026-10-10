import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns, ProDescriptionsItemProps } from '@ant-design/pro-components';
import { Button, Form, Input, Modal, Select, Switch, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { rowActionKind } from '../../../../components/uni-action';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { buildDetailDrawerEditExtra } from '../../../kuaizhizao/pages/equipment-management/shared/equipmentMasterDataDetail';
import { IotMasterDetailDrawer } from '../shared/iotMasterDetailDrawer';
import {
  buildCommonTagKeyOptions,
  buildFillTargetOptions,
  buildMapTargetOptions,
  buildValueTypeOptions,
  formatIotTagLabel,
} from '../../constants/formOptions';
import { IOT_LIST_COL, renderIotEnabledMarker, renderIotMapTargetMarker, renderIotValueTypeMarker } from '../../utils/iotListPresentation';
import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';
import {
  createTag,
  deleteTag,
  listDevices,
  listTags,
  updateTag,
  type Device,
  type TagDefinition,
} from '../../services/kuaiiot';

const TagsPage: React.FC = () => {
  const { t } = useTranslation();
  const perms = useResourcePermissions('kuaiiot:tag');
  const actionRef = useRef<ActionType>();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<TagDefinition | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [detail, setDetail] = useState<TagDefinition | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const deviceLabelMap = Object.fromEntries(devices.map((item) => [item.id, `${item.code} - ${item.name}`]));
  const valueTypeOptions = buildValueTypeOptions(t);
  const mapTargetOptions = buildMapTargetOptions(t);
  const fillTargetOptions = buildFillTargetOptions(t);
  const commonTagKeyOptions = buildCommonTagKeyOptions();

  useEffect(() => {
    (async () => {
      const res = await listDevices({ page: 1, page_size: 500 });
      setDevices(res.items);
    })();
  }, []);

  const columns: ProColumns<TagDefinition>[] = alignProColumns(
    [
      {
        title: t('app.kuaiiot.field.tagKey'),
        dataIndex: 'tag_key',
        ...IOT_LIST_COL.tagKey,
      },
      {
        title: t('common.name'),
        dataIndex: 'name',
        ...IOT_LIST_COL.name,
        render: (_, row) => formatIotTagLabel(row.name, row.tag_key),
      },
      {
        title: t('app.kuaiiot.field.device'),
        dataIndex: 'device_id',
        ...IOT_LIST_COL.ref,
        render: (_, row) => deviceLabelMap[row.device_id] || row.device_id,
      },
      {
        title: t('app.kuaiiot.field.valueType'),
        dataIndex: 'value_type',
        ...IOT_LIST_COL.markerMd,
        render: (_, row) => renderIotValueTypeMarker(t, row.value_type),
      },
      {
        title: t('app.kuaiiot.field.mapTarget'),
        dataIndex: 'map_target',
        ...IOT_LIST_COL.mapTarget,
        render: (_, row) => renderIotMapTargetMarker(t, row.map_target, row.name),
      },
      {
        title: t('app.kuaiiot.field.fillTarget'),
        dataIndex: 'fill_target',
        ...IOT_LIST_COL.fillTarget,
      },
      {
        title: t('common.unit'),
        dataIndex: 'unit',
        ...IOT_LIST_COL.unit,
      },
      {
        title: t('common.enabled'),
        dataIndex: 'is_enabled',
        ...IOT_LIST_COL.marker,
        hideInSearch: true,
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
                  await deleteTag(row.uuid);
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

  const detailColumns = useMemo<ProDescriptionsItemProps<TagDefinition>[]>(
    () => [
      { title: t('app.kuaiiot.field.tagKey'), dataIndex: 'tag_key', copyable: true },
      { title: t('common.name'), dataIndex: 'name' },
      {
        title: t('app.kuaiiot.field.device'),
        dataIndex: 'device_id',
        render: (_, row) => deviceLabelMap[row.device_id] || row.device_id,
      },
      {
        title: t('app.kuaiiot.field.valueType'),
        dataIndex: 'value_type',
        render: (_, row) => renderIotValueTypeMarker(t, row.value_type),
      },
      {
        title: t('app.kuaiiot.field.mapTarget'),
        dataIndex: 'map_target',
        render: (_, row) => renderIotMapTargetMarker(t, row.map_target, row.name),
      },
      { title: t('app.kuaiiot.field.fillTarget'), dataIndex: 'fill_target' },
      { title: t('common.unit'), dataIndex: 'unit' },
      {
        title: t('common.enabled'),
        dataIndex: 'is_enabled',
        render: (_, row) => renderIotEnabledMarker(t, row.is_enabled),
      },
    ],
    [deviceLabelMap, t],
  );

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ value_type: 'number', map_target: 'temperature', is_enabled: true });
    setOpen(true);
  };

  const openEdit = (row: TagDefinition) => {
    setEditing(row);
    form.setFieldsValue(row);
    setOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    if (editing) {
      await updateTag(editing.uuid, values);
      message.success(t('common.updateSuccess'));
    } else {
      await createTag(values);
      message.success(t('common.createSuccess'));
    }
    setOpen(false);
    actionRef.current?.reload();
  };

  return (
    <ListPageTemplate>
      <UniTable<TagDefinition>
        viewTypes={['table', 'help']}
          helpViewConfig={buildListPageHelpViewConfig('kuaiiot.tags')}
        actionRef={actionRef}
        columns={columns}
        rowKey="uuid"
        columnPersistenceId="apps.kuaiiot.pages.tags.list-v3"
        request={async (params) => {
          const res = await listTags({
            page: params.current,
            page_size: params.pageSize,
            q: params.keyword as string | undefined,
          });
          return { data: res.items, total: res.total, success: true };
        }}
        enableRowSelection={perms.canDelete}
        showDeleteButton={perms.canDelete}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => deleteTag(String(key))));
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

      <Modal open={open} title={editing ? t('common.edit') : t('common.create')} onCancel={() => setOpen(false)} onOk={handleSubmit} destroyOnHidden>
        <Form form={form} layout="vertical">
          <Form.Item name="device_id" label={t('app.kuaiiot.field.device')} rules={[{ required: !editing }]}>
            <Select
              disabled={!!editing}
              showSearch
              optionFilterProp="label"
              options={devices.map((item) => ({ label: `${item.code} - ${item.name}`, value: item.id }))}
            />
          </Form.Item>
          <Form.Item name="tag_key" label={t('app.kuaiiot.field.tagKey')} rules={[{ required: !editing }]}>
            {editing ? (
              <Input disabled />
            ) : (
              <Select showSearch allowClear options={commonTagKeyOptions} placeholder={t('app.kuaiiot.field.tagKey')} />
            )}
          </Form.Item>
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="value_type" label={t('app.kuaiiot.field.valueType')} rules={[{ required: true }]}>
            <Select options={valueTypeOptions} />
          </Form.Item>
          <Form.Item name="map_target" label={t('app.kuaiiot.field.mapTarget')} rules={[{ required: true }]}>
            <Select showSearch options={mapTargetOptions} />
          </Form.Item>
          <Form.Item name="fill_target" label={t('app.kuaiiot.field.fillTarget')}>
            <Select allowClear showSearch options={fillTargetOptions} />
          </Form.Item>
          <Form.Item name="unit" label={t('common.unit')}>
            <Input />
          </Form.Item>
          <Form.Item name="is_enabled" label={t('common.enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageTemplate>
  );
};

export default TagsPage;

