/**
 * 电子制造：出货装箱 ASN / 箱托层级汇总（调用通用 packing-asn API）
 */
import React, { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Alert, App, Button, InputNumber, Result, Space, Table, Typography } from 'antd';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { getApiErrorMessage } from '../../../../utils/errorHandler';
import {
  packingBindingApi,
  type PackingAsnResult,
} from '../../../kuaizhizao/services/packing-binding';

export default function IndElectronicsPackingAsnPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const perms = useResourcePermissions('kuaizhizao:production-execution-packing-binding');
  const [deliveryId, setDeliveryId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [asn, setAsn] = useState<PackingAsnResult | null>(null);

  const load = useCallback(async () => {
    if (!deliveryId || deliveryId <= 0) {
      message.warning(t('app.ind-electronics.packingAsn.needDeliveryId'));
      return;
    }
    setLoading(true);
    try {
      const data = await packingBindingApi.getAsn(deliveryId);
      setAsn(data);
    } catch (error) {
      setAsn(null);
      message.error(getApiErrorMessage(error, t('app.ind-electronics.packingAsn.fetchFailed')));
    } finally {
      setLoading(false);
    }
  }, [deliveryId, message, t]);

  if (perms.enabled && !perms.canRead) {
    return (
      <ListPageTemplate>
        <Result status="403" title={t('common.noPermission')} />
      </ListPageTemplate>
    );
  }

  return (
    <ListPageTemplate>
      <Space orientation="vertical" size="medium" style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          title={t('app.ind-electronics.packingAsn.hintTitle')}
          description={t('app.ind-electronics.packingAsn.hintBody')}
        />
        <Space wrap>
          <Typography.Text>{t('app.ind-electronics.packingAsn.deliveryId')}</Typography.Text>
          <InputNumber
            min={1}
            value={deliveryId ?? undefined}
            onChange={(v) => setDeliveryId(typeof v === 'number' ? v : null)}
            placeholder={t('app.ind-electronics.packingAsn.deliveryIdPlaceholder')}
            style={{ width: 200 }}
          />
          <Button type="primary" loading={loading} onClick={() => void load()}>
            {t('app.ind-electronics.packingAsn.load')}
          </Button>
        </Space>
        {asn ? (
          <>
            <Alert
              type="success"
              showIcon
              title={t('app.ind-electronics.packingAsn.summary', {
                code: asn.delivery_code || asn.sales_delivery_id,
                customer: asn.customer_name || '-',
                boxes: asn.box_count,
                qty: asn.total_quantity,
              })}
            />
            <Table
              rowKey={(r) => String(r.box_no ?? r.id ?? Math.random())}
              loading={loading}
              size="small"
              pagination={false}
              dataSource={asn.lines || []}
              columns={[
                {
                  title: t('app.kuaizhizao.packingBinding.colPalletNo'),
                  dataIndex: 'pallet_no',
                  width: 120,
                  render: (v) => v || '-',
                },
                {
                  title: t('app.kuaizhizao.packingBinding.colParentBoxNo'),
                  dataIndex: 'parent_box_no',
                  width: 120,
                  render: (v) => v || '-',
                },
                {
                  title: t('app.kuaizhizao.packingBinding.colBoxNo'),
                  dataIndex: 'box_no',
                  width: 140,
                },
                {
                  title: t('app.kuaizhizao.packingBinding.colPackingLevel'),
                  dataIndex: 'packing_level',
                  width: 90,
                },
                {
                  title: t('app.kuaizhizao.packingBinding.colProductCode'),
                  dataIndex: 'product_code',
                  width: 120,
                },
                {
                  title: t('app.kuaizhizao.packingBinding.colProductName'),
                  dataIndex: 'product_name',
                  ellipsis: true,
                },
                {
                  title: t('app.kuaizhizao.packingBinding.colPackingQty'),
                  dataIndex: 'packing_quantity',
                  width: 90,
                  align: 'right',
                },
                {
                  title: t('app.kuaizhizao.packingBinding.colSerialNumbers'),
                  dataIndex: 'serial_numbers',
                  width: 160,
                  render: (v: unknown) =>
                    Array.isArray(v) && v.length ? v.join(', ') : '-',
                },
                {
                  title: t('app.kuaizhizao.packingBinding.colSealStatus'),
                  dataIndex: 'seal_status',
                  width: 90,
                  render: (v: string) =>
                    v === 'sealed'
                      ? t('app.kuaizhizao.packingBinding.statusSealed')
                      : t('app.kuaizhizao.packingBinding.statusBound'),
                },
              ]}
              scroll={{ x: 1100 }}
            />
          </>
        ) : null}
      </Space>
    </ListPageTemplate>
  );
}
