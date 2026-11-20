import React, { useEffect, useState } from 'react';
import { DeleteOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import {
  App,
  Alert,
  Button,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Switch,
  Table,
  Tabs,
} from 'antd';
import type { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import {
  qualityQmsApi,
  QmsSystemDocument,
  QmsSystemDocumentCirculation,
  QmsSystemDocumentCirculationType,
} from '../../../services/quality-qms';

type Props = {
  open: boolean;
  document: QmsSystemDocument | null;
  canUpdate: boolean;
  onClose: () => void;
  onChanged: () => void;
};

type FormValues = {
  party_name?: string;
  copies?: number;
  event_on?: Dayjs;
  signer_name?: string;
  signed_on?: Dayjs;
  destroyed?: boolean;
  completed?: boolean;
  training_ref?: string;
};

type CirculationTabKey = 'issue' | 'recall' | 'briefing';

function dateText(value?: string | null) {
  if (!value) return '-';
  return value.slice(0, 10);
}

const SystemDocumentCirculationModal: React.FC<Props> = ({
  open,
  document,
  canUpdate,
  onClose,
  onChanged,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [activeTab, setActiveTab] = useState<CirculationTabKey>('issue');
  const [saving, setSaving] = useState<QmsSystemDocumentCirculationType | null>(null);
  const [issueForm] = Form.useForm<FormValues>();
  const [recallForm] = Form.useForm<FormValues>();
  const [briefingForm] = Form.useForm<FormValues>();
  const documentId = document?.id;
  const canRegister = canUpdate && document?.status === 'effective';

  useEffect(() => {
    if (open) setActiveTab('issue');
  }, [open]);

  const { data, isFetching, refetch } = useQuery({
    queryKey: ['qms-system-document-circulations', documentId],
    enabled: open && documentId != null,
    queryFn: () => qualityQmsApi.systemDocuments.circulations(documentId as number),
  });

  const items = data?.items ?? [];
  const yesNo = (value?: boolean) => (value ? t('common.yes') : t('common.no'));

  const outstandingHint = (
    <div style={{ marginBottom: 12 }}>
      {t('app.kuaizhizao.quality.qms.circulation.outstanding', {
        count: data?.outstanding_copies ?? 0,
      })}
    </div>
  );

  const submit = async (recordType: QmsSystemDocumentCirculationType, values: FormValues) => {
    if (documentId == null || !values.event_on) return;
    setSaving(recordType);
    try {
      await qualityQmsApi.systemDocuments.createCirculation(documentId, {
        record_type: recordType,
        party_name: values.party_name || '',
        copies: recordType === 'briefing' ? undefined : values.copies,
        event_on: values.event_on.format('YYYY-MM-DD'),
        signer_name: recordType === 'issue' ? values.signer_name : undefined,
        signed_on:
          recordType === 'issue' && values.signed_on
            ? values.signed_on.format('YYYY-MM-DD')
            : undefined,
        destroyed: recordType === 'recall' ? !!values.destroyed : false,
        completed: recordType === 'briefing' ? !!values.completed : false,
        training_ref: recordType === 'briefing' ? values.training_ref : undefined,
      });
      messageApi.success(t('app.kuaizhizao.quality.qms.circulation.saved'));
      if (recordType === 'issue') issueForm.resetFields();
      if (recordType === 'recall') recallForm.resetFields();
      if (recordType === 'briefing') briefingForm.resetFields();
      await refetch();
      onChanged();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.operationFailed'));
    } finally {
      setSaving(null);
    }
  };

  const remove = async (row: QmsSystemDocumentCirculation) => {
    if (documentId == null) return;
    try {
      await qualityQmsApi.systemDocuments.deleteCirculation(documentId, row.id);
      messageApi.success(t('common.deleteSuccess'));
      await refetch();
      onChanged();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.operationFailed'));
    }
  };

  const removeColumn = canUpdate
    ? [
        {
          title: t('common.actions'),
          width: 48,
          render: (_: unknown, row: QmsSystemDocumentCirculation) => (
            <Popconfirm
              title={t('app.kuaizhizao.quality.qms.circulation.deleteConfirm')}
              okText={t('common.confirm')}
              cancelText={t('common.cancel')}
              onConfirm={() => remove(row)}
            >
              <Button type="link" danger size="small" icon={<DeleteOutlined />} />
            </Popconfirm>
          ),
        },
      ]
    : [];

  const issuePanel = (
    <>
      {outstandingHint}
      {canRegister ? (
        <Form
          form={issueForm}
          onFinish={(values) => submit('issue', values)}
          style={{ marginBottom: 8 }}
        >
          <Row gutter={12}>
            <Col span={6}>
              <Form.Item
                name="party_name"
                rules={[{ required: true, message: t('app.kuaizhizao.quality.qms.circulation.partyRequired') }]}
              >
                <Input placeholder={t('app.kuaizhizao.quality.qms.circulation.party')} />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item
                name="copies"
                rules={[{ required: true, message: t('app.kuaizhizao.quality.qms.circulation.copiesRequired') }]}
              >
                <InputNumber min={1} precision={0} style={{ width: '100%' }} placeholder={t('app.kuaizhizao.quality.qms.circulation.copies')} />
              </Form.Item>
            </Col>
            <Col span={5}>
              <Form.Item
                name="event_on"
                rules={[{ required: true, message: t('app.kuaizhizao.quality.qms.circulation.dateRequired') }]}
              >
                <DatePicker style={{ width: '100%' }} placeholder={t('app.kuaizhizao.quality.qms.circulation.issueDate')} />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name="signer_name">
                <Input placeholder={t('app.kuaizhizao.quality.qms.circulation.signer')} />
              </Form.Item>
            </Col>
            <Col span={5}>
              <Form.Item name="signed_on">
                <DatePicker style={{ width: '100%' }} placeholder={t('app.kuaizhizao.quality.qms.circulation.signedOn')} />
              </Form.Item>
            </Col>
          </Row>
          <Button type="primary" htmlType="submit" loading={saving === 'issue'}>
            {t('app.kuaizhizao.quality.qms.circulation.register')}
          </Button>
        </Form>
      ) : null}
      <Table
        size="small"
        rowKey="id"
        loading={isFetching}
        pagination={false}
        dataSource={items.filter((row) => row.record_type === 'issue')}
        columns={[
          { title: t('app.kuaizhizao.quality.qms.circulation.party'), dataIndex: 'party_name' },
          { title: t('app.kuaizhizao.quality.qms.circulation.copies'), dataIndex: 'copies', width: 72 },
          {
            title: t('app.kuaizhizao.quality.qms.circulation.issueDate'),
            dataIndex: 'event_on',
            width: 120,
            render: (value) => dateText(value),
          },
          { title: t('app.kuaizhizao.quality.qms.circulation.signer'), dataIndex: 'signer_name', width: 100 },
          {
            title: t('app.kuaizhizao.quality.qms.circulation.signedOn'),
            dataIndex: 'signed_on',
            width: 120,
            render: (value) => dateText(value),
          },
          { title: t('app.kuaizhizao.quality.qms.version'), dataIndex: 'document_version', width: 72 },
          ...removeColumn,
        ]}
      />
    </>
  );

  const recallPanel = (
    <>
      {outstandingHint}
      {canRegister ? (
        <Form
          form={recallForm}
          onFinish={(values) => submit('recall', values)}
          style={{ marginBottom: 8 }}
        >
          <Row gutter={12}>
            <Col span={6}>
              <Form.Item
                name="party_name"
                rules={[{ required: true, message: t('app.kuaizhizao.quality.qms.circulation.recallerRequired') }]}
              >
                <Input placeholder={t('app.kuaizhizao.quality.qms.circulation.recaller')} />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item
                name="copies"
                rules={[{ required: true, message: t('app.kuaizhizao.quality.qms.circulation.copiesRequired') }]}
              >
                <InputNumber min={1} precision={0} style={{ width: '100%' }} placeholder={t('app.kuaizhizao.quality.qms.circulation.copies')} />
              </Form.Item>
            </Col>
            <Col span={5}>
              <Form.Item
                name="event_on"
                rules={[{ required: true, message: t('app.kuaizhizao.quality.qms.circulation.dateRequired') }]}
              >
                <DatePicker style={{ width: '100%' }} placeholder={t('app.kuaizhizao.quality.qms.circulation.recallDate')} />
              </Form.Item>
            </Col>
            <Col span={5}>
              <Form.Item name="destroyed" label={t('app.kuaizhizao.quality.qms.circulation.destroyed')} valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>
          <Button type="primary" htmlType="submit" loading={saving === 'recall'}>
            {t('app.kuaizhizao.quality.qms.circulation.register')}
          </Button>
        </Form>
      ) : null}
      <Table
        size="small"
        rowKey="id"
        loading={isFetching}
        pagination={false}
        dataSource={items.filter((row) => row.record_type === 'recall')}
        columns={[
          { title: t('app.kuaizhizao.quality.qms.circulation.recaller'), dataIndex: 'party_name' },
          { title: t('app.kuaizhizao.quality.qms.circulation.copies'), dataIndex: 'copies', width: 72 },
          {
            title: t('app.kuaizhizao.quality.qms.circulation.recallDate'),
            dataIndex: 'event_on',
            width: 120,
            render: (value) => dateText(value),
          },
          {
            title: t('app.kuaizhizao.quality.qms.circulation.destroyed'),
            dataIndex: 'destroyed',
            width: 88,
            render: (value) => yesNo(value),
          },
          { title: t('app.kuaizhizao.quality.qms.version'), dataIndex: 'document_version', width: 72 },
          ...removeColumn,
        ]}
      />
    </>
  );

  const briefingPanel = (
    <>
      {canRegister ? (
        <Form
          form={briefingForm}
          onFinish={(values) => submit('briefing', values)}
          style={{ marginBottom: 8 }}
        >
          <Row gutter={12}>
            <Col span={6}>
              <Form.Item
                name="party_name"
                rules={[{ required: true, message: t('app.kuaizhizao.quality.qms.circulation.audienceRequired') }]}
              >
                <Input placeholder={t('app.kuaizhizao.quality.qms.circulation.audience')} />
              </Form.Item>
            </Col>
            <Col span={5}>
              <Form.Item
                name="event_on"
                rules={[{ required: true, message: t('app.kuaizhizao.quality.qms.circulation.dateRequired') }]}
              >
                <DatePicker style={{ width: '100%' }} placeholder={t('app.kuaizhizao.quality.qms.circulation.briefingDate')} />
              </Form.Item>
            </Col>
            <Col span={5}>
              <Form.Item name="training_ref">
                <Input placeholder={t('app.kuaizhizao.quality.qms.circulation.trainingRef')} />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name="completed" label={t('app.kuaizhizao.quality.qms.circulation.completed')} valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          </Row>
          <Button type="primary" htmlType="submit" loading={saving === 'briefing'}>
            {t('app.kuaizhizao.quality.qms.circulation.register')}
          </Button>
        </Form>
      ) : null}
      <Table
        size="small"
        rowKey="id"
        loading={isFetching}
        pagination={false}
        dataSource={items.filter((row) => row.record_type === 'briefing')}
        columns={[
          { title: t('app.kuaizhizao.quality.qms.circulation.audience'), dataIndex: 'party_name' },
          {
            title: t('app.kuaizhizao.quality.qms.circulation.briefingDate'),
            dataIndex: 'event_on',
            width: 120,
            render: (value) => dateText(value),
          },
          {
            title: t('app.kuaizhizao.quality.qms.circulation.completed'),
            dataIndex: 'completed',
            width: 88,
            render: (value) => yesNo(value),
          },
          { title: t('app.kuaizhizao.quality.qms.circulation.trainingRef'), dataIndex: 'training_ref' },
          { title: t('app.kuaizhizao.quality.qms.version'), dataIndex: 'document_version', width: 72 },
          ...removeColumn,
        ]}
      />
    </>
  );

  return (
    <Modal
      title={
        document
          ? t('app.kuaizhizao.quality.qms.circulation.title', { code: document.document_code })
          : t('app.kuaizhizao.quality.qms.circulation.action')
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={960}
      destroyOnHidden
      styles={{ body: { maxHeight: 'min(72vh, 720px)', overflowY: 'auto' } }}
    >
      {document && document.status !== 'effective' ? (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('app.kuaizhizao.quality.qms.circulation.effectiveOnly')}
        />
      ) : null}

      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as CirculationTabKey)}
        items={[
          {
            key: 'issue',
            label: t('app.kuaizhizao.quality.qms.circulation.issue'),
            children: issuePanel,
          },
          {
            key: 'recall',
            label: t('app.kuaizhizao.quality.qms.circulation.recall'),
            children: recallPanel,
          },
          {
            key: 'briefing',
            label: t('app.kuaizhizao.quality.qms.circulation.briefing'),
            children: briefingPanel,
          },
        ]}
      />
    </Modal>
  );
};

export default SystemDocumentCirculationModal;
