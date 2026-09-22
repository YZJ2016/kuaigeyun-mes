import React, { useCallback, useMemo, useRef, useState } from 'react';
import { Button, Form, Input, Modal, Tag, message } from 'antd';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { industryMoldApi, type MoldProgramSheet } from '../../services/industryMoldApi';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';

export default function MoldProgramSheetsPage() {
  const { t } = useTranslation();
  const actionRef = useRef<ActionType>(null);
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const perms = useResourcePermissions('ind-mold:program');

  const columns: ProColumns<MoldProgramSheet>[] = useMemo(
    () => [
      { title: t('app.ind-mold.programSheet.code'), dataIndex: 'code', width: 160 },
      { title: t('app.ind-mold.programSheet.workOrderCode'), dataIndex: 'work_order_code', width: 140 },
      { title: t('app.ind-mold.programSheet.programName'), dataIndex: 'program_name', ellipsis: true },
      {
        title: t('app.ind-mold.programSheet.status'),
        dataIndex: 'program_status',
        width: 100,
        render: (_, row) => (
          <Tag variant="filled">
            {row.program_status === 'programmed'
              ? t('app.ind-mold.programSheet.statusProgrammed')
              : t('app.ind-mold.programSheet.statusPending')}
          </Tag>
        ),
      },
      { title: t('app.ind-mold.programSheet.ncFile'), dataIndex: 'nc_file_path', ellipsis: true },
    ],
    [t]
  );

  const handleCreate = useCallback(async () => {
    const values = await form.validateFields();
    await industryMoldApi.createProgramSheet(values);
    message.success(t('app.ind-mold.programSheet.createSuccess'));
    setOpen(false);
    form.resetFields();
    actionRef.current?.reload();
  }, [form, t]);

  return (
    <ListPageTemplate>
      <UniTable<MoldProgramSheet>
        actionRef={actionRef}
        rowKey="id"
        createButtonText={t('app.ind-mold.programSheet.createButton')}
        onCreateClick={perms.canCreate ? () => setOpen(true) : undefined}
        columns={columns}
        request={async () => {
          const items = await industryMoldApi.listProgramSheets();
          return { data: items, success: true, total: items.length };
        }}
      />
      <Modal
        open={open}
        title={t('app.ind-mold.programSheet.createTitle')}
        onCancel={() => setOpen(false)}
        onOk={() => void handleCreate()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <Form.Item name="work_order_id" label={t('app.ind-mold.programSheet.workOrderId')} rules={[{ required: true }]}>
            <Input type="number" />
          </Form.Item>
          <Form.Item name="work_order_code" label={t('app.ind-mold.programSheet.workOrderCode')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="program_name" label={t('app.ind-mold.programSheet.programName')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="nc_file_path" label={t('app.ind-mold.programSheet.ncFile')}>
            <Input />
          </Form.Item>
          <Form.Item name="remarks" label={t('common.remarks')}>
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </ListPageTemplate>
  );
}
