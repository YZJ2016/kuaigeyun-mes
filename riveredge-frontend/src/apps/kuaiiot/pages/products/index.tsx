import React, { useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns, ProDescriptionsItemProps } from '@ant-design/pro-components';
import { Button, Form, Input, InputNumber, Modal, Select, Space, Typography, message } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { rowActionKind } from '../../../../components/uni-action';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { buildDetailDrawerEditExtra } from '../../../kuaizhizao/pages/equipment-management/shared/equipmentMasterDataDetail';
import { IotMasterDetailDrawer } from '../shared/iotMasterDetailDrawer';
import { IOT_LIST_COL } from '../../utils/iotListPresentation';
import {
  createProduct,
  deleteProduct,
  loadBuiltinProductPresets,
  listProducts,
  updateProduct,
  type Product,
  type ProductFunctionDefinition,
  type ProductTagDefinition,
} from '../../services/kuaiiot';

import { buildListPageHelpViewConfig } from '../../../../components/page-help-wiki';
import {
  buildCommonTagKeyOptions,
  buildEventLevelOptions,
  buildMapTargetOptions,
  buildValueTypeOptions,
} from '../../constants/formOptions';

const ProductsPage: React.FC = () => {
  const { t } = useTranslation();
  const perms = useResourcePermissions('kuaiiot:product');
  const actionRef = useRef<ActionType>();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);
  const [detail, setDetail] = useState<Product | null>(null);
  const [presetLoading, setPresetLoading] = useState(false);
  const valueTypeOptions = buildValueTypeOptions(t);
  const mapTargetOptions = buildMapTargetOptions(t);
  const commonTagKeyOptions = buildCommonTagKeyOptions();
  const eventLevelOptions = buildEventLevelOptions(t);

  const columns: ProColumns<Product>[] = alignProColumns(
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
        title: t('common.remark'),
        dataIndex: 'description',
        ...IOT_LIST_COL.text,
      },
      {
        title: t('app.kuaiiot.field.tagCount'),
        ...IOT_LIST_COL.count,
        render: (_, row) => row.tags?.length ?? 0,
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
              <Button key="detail" {...rowActionKind('read')} onClick={() => openDetail(row)} />,
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
                  await deleteProduct(row.uuid);
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

  const openDetail = (row: Product) => {
    setDetail(row);
    setDrawerVisible(true);
  };

  const detailColumns = useMemo<ProDescriptionsItemProps<Product>[]>(
    () => [
      { title: t('common.code'), dataIndex: 'code', copyable: true },
      { title: t('common.name'), dataIndex: 'name' },
      { title: t('common.remark'), dataIndex: 'description' },
      { title: t('app.kuaiiot.field.tagCount'), dataIndex: 'tags', render: (_, row) => row.tags?.length ?? 0 },
      { title: t('common.remark'), dataIndex: 'remark' },
    ],
    [t],
  );

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ tags: [{ value_type: 'number', map_target: 'temperature' }], events: [], functions: [] });
    setOpen(true);
  };

  const openEdit = (row: Product) => {
    setEditing(row);
    form.setFieldsValue({
      ...row,
      tags: row.tags?.length ? row.tags : [{ value_type: 'number', map_target: 'temperature' }],
      events: row.events || [],
      functions: row.functions || [],
    });
    setOpen(true);
  };

  const handleSubmit = async () => {
    const values = await form.validateFields();
    const payload = {
      ...values,
      tags: (values.tags || []) as ProductTagDefinition[],
      events: values.events || [],
      functions: (values.functions || []) as ProductFunctionDefinition[],
    };
    if (editing) {
      await updateProduct(editing.uuid, payload);
      message.success(t('common.updateSuccess'));
    } else {
      await createProduct(payload);
      message.success(t('common.createSuccess'));
    }
    setOpen(false);
    actionRef.current?.reload();
  };

  const handleLoadPresets = async () => {
    setPresetLoading(true);
    try {
      const res = await loadBuiltinProductPresets();
      message.success(
        t('app.kuaiiot.message.productPresetsLoaded', {
          created: res.created,
          skipped: res.skipped,
          total: res.total,
        }),
      );
      actionRef.current?.reload();
    } finally {
      setPresetLoading(false);
    }
  };

  return (
    <ListPageTemplate>
      <UniTable<Product>
        viewTypes={['table', 'help']}
          helpViewConfig={buildListPageHelpViewConfig('kuaiiot.products')}
        actionRef={actionRef}
        columns={columns}
        rowKey="uuid"
        columnPersistenceId="apps.kuaiiot.pages.products.list-v3"
        request={async (params) => {
          const res = await listProducts({
            page: params.current,
            page_size: params.pageSize,
            q: params.keyword as string | undefined,
          });
          return { data: res.items, total: res.total, success: true };
        }}
        toolBarActionsAfterCreate={
          perms.canCreate
            ? [
                <Button key="presets" loading={presetLoading} onClick={handleLoadPresets}>
                  {t('app.kuaiiot.action.loadProductPresets')}
                </Button>,
              ]
            : []
        }
        showCreateButton
        createButtonText={t('app.kuaiiot.action.createProduct')}
        onCreate={openCreate}
        enableRowSelection={perms.canDelete}
        showDeleteButton={perms.canDelete}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => deleteProduct(String(key))));
          message.success(t('common.batchDeleteSuccess', { count: keys.length }));
    actionRef.current?.reload();
        }}
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

      <Modal
        open={open}
        width={880}
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
          <Form.Item name="description" label={t('common.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.List name="tags">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Space key={field.key} align="baseline" wrap style={{ display: 'flex', marginBottom: 8 }}>
                    <Form.Item {...field} name={[field.name, 'tag_key']} rules={[{ required: true }]}>
                      <Select showSearch allowClear options={commonTagKeyOptions} placeholder={t('app.kuaiiot.field.tagKey')} style={{ width: 140 }} />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'name']} rules={[{ required: true }]}>
                      <Input placeholder={t('common.name')} />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'value_type']} rules={[{ required: true }]}>
                      <Select style={{ width: 120 }} options={valueTypeOptions} />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'map_target']} rules={[{ required: true }]}>
                      <Select style={{ width: 160 }} options={mapTargetOptions} />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'unit']}>
                      <Input placeholder={t('common.unit')} style={{ width: 100 }} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(field.name)} />
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add({ value_type: 'number', map_target: 'temperature' })} icon={<PlusOutlined />}>
                  {t('app.kuaiiot.action.addTagRow')}
                </Button>
              </>
            )}
          </Form.List>
          <Typography.Text strong>{t('app.kuaiiot.section.events')}</Typography.Text>
          <Form.List name="events">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Space key={field.key} align="baseline" wrap style={{ display: 'flex', marginBottom: 8 }}>
                    <Form.Item {...field} name={[field.name, 'event_key']} rules={[{ required: true }]}>
                      <Input placeholder={t('app.kuaiiot.field.eventKey')} style={{ width: 140 }} />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'name']} rules={[{ required: true }]}>
                      <Input placeholder={t('common.name')} />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'level']} initialValue="info" rules={[{ required: true }]}>
                      <Select style={{ width: 120 }} options={eventLevelOptions} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(field.name)} />
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add({ level: 'info' })} icon={<PlusOutlined />}>
                  {t('app.kuaiiot.action.addEventRow')}
                </Button>
              </>
            )}
          </Form.List>
          <Typography.Text strong>{t('app.kuaiiot.section.functions')}</Typography.Text>
          <Form.List name="functions">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Space key={field.key} align="baseline" wrap style={{ display: 'flex', marginBottom: 8 }}>
                    <Form.Item {...field} name={[field.name, 'function_key']} rules={[{ required: true }]}>
                      <Input placeholder={t('app.kuaiiot.field.functionKey')} style={{ width: 140 }} />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'name']} rules={[{ required: true }]}>
                      <Input placeholder={t('common.name')} />
                    </Form.Item>
                    <Form.Item {...field} name={[field.name, 'timeout_seconds']} initialValue={30}>
                      <InputNumber min={1} max={3600} placeholder={t('app.kuaiiot.field.timeoutSeconds')} />
                    </Form.Item>
                    <MinusCircleOutlined onClick={() => remove(field.name)} />
                  </Space>
                ))}
                <Button type="dashed" onClick={() => add({ timeout_seconds: 30, params: [] })} icon={<PlusOutlined />}>
                  {t('app.kuaiiot.action.addFunctionRow')}
                </Button>
              </>
            )}
          </Form.List>
          <Form.Item name="remark" label={t('common.remark')}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageTemplate>
  );
};

export default ProductsPage;
