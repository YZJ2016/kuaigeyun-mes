/**
 * 交付节点关联单据：关联已有 / 直接新建
 */

import React, { useMemo, useState } from 'react';
import { Alert, Button, Form, Modal, Segmented, Select, Space } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import DeliveryNodeDocumentSelect from '../shared/DeliveryNodeDocumentSelect';
import {
  buildDeliveryNodeDocumentCreatePath,
  DELIVERY_NODE_DOCUMENT_AUTO_LINK_TYPES,
} from '../shared/deliveryNodeDocumentLink';
import {
  DELIVERY_NODE_DOCUMENT_TYPES,
  type DeliveryNodeDocumentKind,
} from '../../../services/delivery-project';

type LinkMode = 'existing' | 'create';

interface DeliveryNodeDocumentLinkModalProps {
  open: boolean;
  projectId: number;
  nodeId: number;
  returnPath: string;
  customerId?: number | null;
  salesOrderId?: number | null;
  onClose: () => void;
  onLinked: () => void | Promise<void>;
  onLinkExisting: (payload: {
    node_id: number;
    doc_type: string;
    doc_id: number;
    doc_code: string;
    title?: string;
  }) => Promise<void>;
}

const DeliveryNodeDocumentLinkModal: React.FC<DeliveryNodeDocumentLinkModalProps> = ({
  open,
  projectId,
  nodeId,
  returnPath,
  customerId,
  salesOrderId,
  onClose,
  onLinked,
  onLinkExisting,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [mode, setMode] = useState<LinkMode>('existing');
  const [createDocType, setCreateDocType] = useState<DeliveryNodeDocumentKind | undefined>();
  const [form] = Form.useForm();

  const typeOptions = useMemo(
    () =>
      Object.entries(DELIVERY_NODE_DOCUMENT_TYPES).map(([value, label]) => ({
        value,
        label,
      })),
    [],
  );

  const reset = () => {
    setMode('existing');
    setCreateDocType(undefined);
    form.resetFields();
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSaveExisting = async () => {
    const values = await form.validateFields();
    await onLinkExisting({
      node_id: values.node_id as number,
      doc_type: values.doc_type as string,
      doc_id: values.doc_id as number,
      doc_code: values.doc_code as string,
      title: values.title as string | undefined,
    });
    reset();
    await onLinked();
  };

  const handleGoCreate = () => {
    if (!createDocType) return;
    const path = buildDeliveryNodeDocumentCreatePath(createDocType, {
      projectId,
      nodeId,
      returnPath,
      salesOrderId,
    });
    if (!path) return;
    reset();
    onClose();
    navigate(path);
  };

  const createSupportsAutoLink = createDocType
    ? DELIVERY_NODE_DOCUMENT_AUTO_LINK_TYPES.has(createDocType)
    : false;

  return (
    <Modal
      title={t('app.kuaizhizao.deliveryProject.linkDocument')}
      open={open}
      onCancel={handleClose}
      destroyOnHidden
      footer={
        mode === 'existing' ? (
          <Space>
            <Button onClick={handleClose}>{t('common.cancel')}</Button>
            <Button type="primary" onClick={() => void handleSaveExisting()}>
              {t('common.confirm')}
            </Button>
          </Space>
        ) : (
          <Space>
            <Button onClick={handleClose}>{t('common.cancel')}</Button>
            <Button type="primary" icon={<PlusOutlined />} disabled={!createDocType} onClick={handleGoCreate}>
              {t('app.kuaizhizao.deliveryProject.nodeDocumentGoCreate')}
            </Button>
          </Space>
        )
      }
    >
      <Segmented
        block
        style={{ marginBottom: 16 }}
        value={mode}
        options={[
          { label: t('app.kuaizhizao.deliveryProject.nodeDocumentLinkExisting'), value: 'existing' },
          { label: t('app.kuaizhizao.deliveryProject.nodeDocumentCreateNew'), value: 'create' },
        ]}
        onChange={(value) => setMode(value as LinkMode)}
      />
      {mode === 'existing' ? (
        <Form form={form} layout="vertical">
          <DeliveryNodeDocumentSelect customerId={customerId} salesOrderId={salesOrderId} />
          <Form.Item name="node_id" hidden initialValue={nodeId}>
            <Select />
          </Form.Item>
        </Form>
      ) : (
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <Form.Item label={t('app.kuaizhizao.deliveryProject.fields.docType')} required style={{ marginBottom: 0 }}>
            <Select
              placeholder={t('app.kuaizhizao.deliveryProject.selectDocTypeFirst')}
              options={typeOptions}
              value={createDocType}
              onChange={setCreateDocType}
            />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            title={
              createSupportsAutoLink
                ? t('app.kuaizhizao.deliveryProject.nodeDocumentCreateAutoLinkHint')
                : t('app.kuaizhizao.deliveryProject.nodeDocumentCreateManualLinkHint')
            }
          />
        </Space>
      )}
    </Modal>
  );
};

export default DeliveryNodeDocumentLinkModal;
