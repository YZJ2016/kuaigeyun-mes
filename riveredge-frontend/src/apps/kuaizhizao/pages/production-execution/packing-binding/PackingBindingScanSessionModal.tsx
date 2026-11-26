import React, { useCallback, useEffect, useRef, useState } from 'react';
import { App, Button, Input, Modal, Space, Table, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { packingBindingApi } from '../../../services/packing-binding';

export type PackingScanSessionSource = {
  source_type: 'sales_delivery' | 'finished_goods_receipt';
  source_id: number;
  source_line_id: number;
  product_id: number;
  product_code?: string;
  product_name?: string;
};

type Props = {
  open: boolean;
  source: PackingScanSessionSource | null;
  onClose: () => void;
  onCompleted?: () => void;
};

export function PackingBindingScanSessionModal({ open, source, onClose, onCompleted }: Props) {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [bindingId, setBindingId] = useState<number | null>(null);
  const [boxNo, setBoxNo] = useState('');
  const [scanValue, setScanValue] = useState('');
  const [lines, setLines] = useState<Array<{ id: number; product_serial_no: string; quantity: number | string }>>(
    [],
  );
  const [loading, setLoading] = useState(false);
  const [sealStatus, setSealStatus] = useState<string>('bound');
  const scanRef = useRef<any>(null);

  const reset = useCallback(() => {
    setBindingId(null);
    setBoxNo('');
    setScanValue('');
    setLines([]);
    setSealStatus('bound');
  }, []);

  useEffect(() => {
    if (!open) {
      reset();
    }
  }, [open, reset]);

  const refreshBinding = useCallback(async (id: number) => {
    const detail = (await packingBindingApi.get(String(id))) as {
      seal_status?: string;
      box_no?: string;
      lines?: Array<{ id: number; product_serial_no: string; quantity: number | string }>;
    };
    setSealStatus(detail.seal_status || 'bound');
    setBoxNo(detail.box_no || '');
    setLines(detail.lines || []);
  }, []);

  const handleOpenBox = async () => {
    if (!source) return;
    setLoading(true);
    try {
      const created = (await packingBindingApi.openSession({
        source_type: source.source_type,
        source_id: source.source_id,
        product_id: source.product_id,
        source_line_id: source.source_line_id,
      })) as { id?: number; box_no?: string };
      if (!created?.id) {
        messageApi.error(t('app.kuaizhizao.packingBinding.sessionOpenFailed'));
        return;
      }
      setBindingId(created.id);
      setBoxNo(created.box_no || '');
      messageApi.success(t('app.kuaizhizao.packingBinding.sessionOpenSuccess', { box: created.box_no || '' }));
      scanRef.current?.focus?.();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('common.operationFailed');
      messageApi.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleScan = async () => {
    if (!bindingId) return;
    const sn = scanValue.trim();
    if (!sn) return;
    setLoading(true);
    try {
      await packingBindingApi.scanSession(bindingId, { serial_number: sn, quantity: 1 });
      setScanValue('');
      await refreshBinding(bindingId);
      scanRef.current?.focus?.();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('common.operationFailed');
      messageApi.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleSeal = async () => {
    if (!bindingId) return;
    setLoading(true);
    try {
      await packingBindingApi.seal(String(bindingId));
      await refreshBinding(bindingId);
      messageApi.success(t('app.kuaizhizao.packingBinding.sealSuccess'));
      onCompleted?.();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('common.operationFailed');
      messageApi.error(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title={t('app.kuaizhizao.packingBinding.sessionTitle')}
      open={open}
      onCancel={onClose}
      width={720}
      footer={null}
      destroyOnHidden
    >
      {source ? (
        <Typography.Paragraph type="secondary">
          {source.product_code} {source.product_name}
        </Typography.Paragraph>
      ) : null}
      <Space orientation="vertical" style={{ width: '100%' }} size="medium">
        {!bindingId ? (
          <Button type="primary" loading={loading} onClick={() => void handleOpenBox()} disabled={!source}>
            {t('app.kuaizhizao.packingBinding.sessionOpenBox')}
          </Button>
        ) : (
          <>
            <Typography.Text>
              {t('app.kuaizhizao.packingBinding.sessionBoxNo')}: {boxNo || '-'}
            </Typography.Text>
            {sealStatus !== 'sealed' ? (
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  ref={scanRef}
                  value={scanValue}
                  onChange={(e) => setScanValue(e.target.value)}
                  placeholder={t('app.kuaizhizao.packingBinding.sessionScanPlaceholder')}
                  onPressEnter={() => void handleScan()}
                />
                <Button type="primary" loading={loading} onClick={() => void handleScan()}>
                  {t('app.kuaizhizao.packingBinding.sessionScan')}
                </Button>
              </Space.Compact>
            ) : null}
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={lines}
              columns={[
                { title: t('app.kuaizhizao.packingBinding.colSerialNo'), dataIndex: 'product_serial_no' },
                { title: t('app.kuaizhizao.packingBinding.colQuantity'), dataIndex: 'quantity', width: 100 },
              ]}
            />
            {sealStatus !== 'sealed' ? (
              <Button loading={loading} onClick={() => void handleSeal()}>
                {t('app.kuaizhizao.packingBinding.sessionSeal')}
              </Button>
            ) : (
              <Typography.Text type="success">{t('app.kuaizhizao.packingBinding.sessionSealed')}</Typography.Text>
            )}
          </>
        )}
      </Space>
    </Modal>
  );
}
