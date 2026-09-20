import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Button, Form, Input, InputNumber, Modal, Tag, message } from 'antd';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { industryMoldApi, type MoldMaterialArrival } from '../../services/industryMoldApi';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';

function statusLabel(status: string, t: (key: string) => string) {
  if (status === 'arrived') return t('app.ind-mold.materialArrival.statusArrived');
  if (status === 'void') return t('app.ind-mold.materialArrival.statusVoid');
  return t('app.ind-mold.materialArrival.statusPending');
}

export default function MoldMaterialArrivalsPage() {
  const { t } = useTranslation();
  const actionRef = useRef<ActionType>(null);
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const perms = useResourcePermissions('ind-mold:arrival');

  const columns: ProColumns<MoldMaterialArrival>[] = useMemo(
    () => [
      { title: t('app.ind-mold.materialArrival.code'), dataIndex: 'code', width: 160 },
      { title: t('app.ind-mold.materialArrival.workOrderCode'), dataIndex: 'work_order_code', width: 140 },
      { title: t('app.ind-mold.materialArrival.materialName'), dataIndex: 'material_name', ellipsis: true },
      { title: t('app.ind-mold.materialArrival.materialSpec'), dataIndex: 'material_spec', width: 140 },
      { title: t('app.ind-mold.materialArrival.weight'), dataIndex: 'weight', width: 100, align: 'right' },
      {
        title: t('app.ind-mold.materialArrival.status'),
        dataIndex: 'status',
        width: 100,
        render: (_, row) => <Tag variant="filled">{statusLabel(row.status, t)}</Tag>,
      },
      {
        title: t('common.actions'),
        valueType: 'option',
        width: 100,
        render: (_, row) =>
          row.status === 'pending' && perms.canUpdate ? (
            <Button
              type="link"
              danger
              size="small"
              onClick={async () => {
                await industryMoldApi.voidMaterialArrival(row.id);
                message.success(t('app.ind-mold.materialArrival.voidSuccess'));
                actionRef.current?.reload();
              }}
            >
              {t('app.ind-mold.materialArrival.void')}
            </Button>
          ) : null,
      },
    ],
    [perms.canUpdate, t]
  );

  const handleCreate = useCallback(async () => {
    const values = await form.validateFields();
    await industryMoldApi.createMaterialArrival(values);
    message.success(t('app.ind-mold.materialArrival.createSuccess'));
    setOpen(false);
    form.resetFields();
    actionRef.current?.reload();
  }, [form, t]);

  return (
    <ListPageTemplate>
      <UniTable<MoldMaterialArrival>
        actionRef={actionRef}
        rowKey="id"
        createButtonText={t('app.ind-mold.materialArrival.createButton')}
        onCreateClick={perms.canCreate ? () => setOpen(true) : undefined}
        columns={columns}
        request={async () => {
          const items = await industryMoldApi.listMaterialArrivals();
          return { data: items, success: true, total: items.length };
        }}
      />
      <Modal
        open={open}
        title={t('app.ind-mold.materialArrival.createTitle')}
        onCancel={() => setOpen(false)}
        onOk={() => void handleCreate()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="work_order_id" label={t('app.ind-mold.materialArrival.workOrderId')}>
            <Input type="number" />
          </Form.Item>
          <Form.Item name="work_order_code" label={t('app.ind-mold.materialArrival.workOrderCode')}>
            <Input />
          </Form.Item>
          <Form.Item name="material_name" label={t('app.ind-mold.materialArrival.materialName')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="material_spec" label={t('app.ind-mold.materialArrival.materialSpec')}>
            <Input />
          </Form.Item>
          <Form.Item name="weight" label={t('app.ind-mold.materialArrival.weight')}>
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
          <Form.Item name="remarks" label={t('common.remarks')}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageTemplate>
  );
}
