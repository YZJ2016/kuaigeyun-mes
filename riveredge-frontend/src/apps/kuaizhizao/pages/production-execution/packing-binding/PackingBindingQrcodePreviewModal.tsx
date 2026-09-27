import React, { useCallback } from 'react';
import { Alert, App, Button, Col, Modal, Row, Spin, Typography } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  downloadQrcodePngFromDataUri,
  sanitizeQrcodeFileName,
} from '../../../../../utils/qrcodeDownload';

export interface PackingBindingQrcodePreviewItem {
  bindingId: number;
  boxNo: string;
  productCode?: string;
  qrcodeImage: string;
}

export interface PackingBindingQrcodePreviewModalProps {
  open: boolean;
  loading?: boolean;
  items: PackingBindingQrcodePreviewItem[];
  failedMessages?: string[];
  onClose: () => void;
}

export function PackingBindingQrcodePreviewModal({
  open,
  loading = false,
  items,
  failedMessages = [],
  onClose,
}: PackingBindingQrcodePreviewModalProps) {
  const { t } = useTranslation();
  const { message } = App.useApp();

  const downloadOne = useCallback(
    (item: PackingBindingQrcodePreviewItem) => {
      try {
        downloadQrcodePngFromDataUri(
          item.qrcodeImage,
          sanitizeQrcodeFileName(item.boxNo, item.bindingId),
        );
        message.success(t('app.kuaizhizao.packingBinding.qrcodeDownloadSuccess'));
      } catch (e: unknown) {
        const err = e as Error;
        message.error(err?.message || t('app.kuaizhizao.packingBinding.qrcodeDownloadFailed'));
      }
    },
    [message, t],
  );

  const downloadAll = useCallback(() => {
    if (items.length === 0) {
      message.warning(t('app.kuaizhizao.packingBinding.qrcodePreviewEmpty'));
      return;
    }
    try {
      items.forEach((item) => {
        downloadQrcodePngFromDataUri(
          item.qrcodeImage,
          sanitizeQrcodeFileName(item.boxNo, item.bindingId),
        );
      });
      message.success(
        t('app.kuaizhizao.packingBinding.qrcodeDownloadAllSuccess', { count: items.length }),
      );
    } catch (e: unknown) {
      const err = e as Error;
      message.error(err?.message || t('app.kuaizhizao.packingBinding.qrcodeDownloadFailed'));
    }
  }, [items, message, t]);

  return (
    <Modal
      title={t('app.kuaizhizao.packingBinding.qrcodePreviewTitle')}
      open={open}
      onCancel={onClose}
      width={920}
      footer={[
        <Button key="close" onClick={onClose}>
          {t('common.close')}
        </Button>,
        <Button
          key="download-all"
          type="primary"
          icon={<DownloadOutlined />}
          disabled={loading || items.length === 0}
          onClick={downloadAll}
        >
          {t('app.kuaizhizao.packingBinding.qrcodeDownloadAll')}
        </Button>,
      ]}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        title={t('app.kuaizhizao.packingBinding.qrcodePreviewHint')}
      />
      {failedMessages.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('app.kuaizhizao.packingBinding.qrcodePartial', {
            success: items.length,
            failed: failedMessages.length,
          })}
          description={
            <div style={{ maxHeight: 120, overflowY: 'auto' }}>
              {failedMessages.map((msg) => (
                <div key={msg}>{msg}</div>
              ))}
            </div>
          }
        />
      ) : null}
      <Spin spinning={loading}>
        {items.length === 0 && !loading ? (
          <Typography.Text type="secondary">
            {t('app.kuaizhizao.packingBinding.qrcodePreviewEmpty')}
          </Typography.Text>
        ) : (
          <Row gutter={[16, 16]}>
            {items.map((item) => (
              <Col key={item.bindingId} xs={24} sm={12} md={8}>
                <div
                  style={{
                    border: '1px solid rgba(0,0,0,0.06)',
                    borderRadius: 8,
                    padding: 12,
                    textAlign: 'center',
                    background: '#fafafa',
                  }}
                >
                  <Typography.Text strong copyable={{ text: item.boxNo }}>
                    {item.boxNo}
                  </Typography.Text>
                  {item.productCode ? (
                    <Typography.Paragraph
                      type="secondary"
                      style={{ marginBottom: 8, fontSize: 12 }}
                    >
                      {item.productCode}
                    </Typography.Paragraph>
                  ) : null}
                  <img
                    src={item.qrcodeImage}
                    alt={item.boxNo}
                    style={{ width: 140, height: 140, objectFit: 'contain' }}
                  />
                  <div style={{ marginTop: 8 }}>
                    <Button
                      size="small"
                      icon={<DownloadOutlined />}
                      onClick={() => downloadOne(item)}
                    >
                      {t('app.kuaizhizao.packingBinding.qrcodeDownloadOne')}
                    </Button>
                  </div>
                </div>
              </Col>
            ))}
          </Row>
        )}
      </Spin>
    </Modal>
  );
}
