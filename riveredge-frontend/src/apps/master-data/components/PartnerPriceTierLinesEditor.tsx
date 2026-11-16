import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, InputNumber, Space, Switch, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React from 'react';
import { useTranslation } from 'react-i18next';

export type PartnerPriceTierLineFormValue = {
  minQuantity?: number;
  maxQuantity?: number | null;
  unitPrice?: number;
};

type PartnerPriceTierLinesEditorProps = {
  name?: string | (string | number)[];
  priceDecimals?: number;
  /** 价格本等场景：表头旁「启用阶梯价」开关 */
  showEnableSwitch?: boolean;
  enabledName?: string | (string | number)[];
  sectionTitle?: string;
};

const TIER_COL_WIDTH = {
  minQty: 140,
  maxQty: 140,
  unitPrice: 160,
  action: 48,
};

/** 数量阶梯价编辑（价本 / 物料默认值共用） */
export const PartnerPriceTierLinesEditor: React.FC<PartnerPriceTierLinesEditorProps> = ({
  name = 'tierPrices',
  priceDecimals = 4,
  showEnableSwitch = false,
  enabledName = 'tierPricesEnabled',
  sectionTitle,
}) => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const tierEnabled = Form.useWatch(showEnableSwitch ? enabledName : undefined, form);

  const handleEnableChange = (checked: boolean) => {
    if (!checked) {
      form.setFieldValue(name, []);
      return;
    }
    const rows = form.getFieldValue(name);
    if (!Array.isArray(rows) || rows.length === 0) {
      form.setFieldValue(name, [{ minQuantity: 1 }]);
    }
  };

  const enabled = !showEnableSwitch || tierEnabled === true;

  return (
    <div>
      {(sectionTitle != null || showEnableSwitch) && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
            marginBottom: enabled ? 8 : 0,
          }}
        >
          {sectionTitle ? (
            <Typography.Title level={5} style={{ margin: 0 }}>
              {sectionTitle}
            </Typography.Title>
          ) : (
            <span />
          )}
          {showEnableSwitch ? (
            <Space size={8} align="center">
              <Typography.Text>{t('app.master-data.priceBook.tierPricesEnable')}</Typography.Text>
              <Form.Item name={enabledName} valuePropName="checked" noStyle>
                <Switch
                  checkedChildren={t('common.enabled')}
                  unCheckedChildren={t('common.disabled')}
                  onChange={handleEnableChange}
                />
              </Form.Item>
            </Space>
          ) : null}
        </div>
      )}

      {enabled ? (
        <Form.List name={name}>
          {(fields, { add, remove }) => {
            const columns: ColumnsType<(typeof fields)[number]> = [
              {
                title: (
                  <span>
                    <span style={{ color: 'var(--ant-color-error)' }}>* </span>
                    {t('app.master-data.priceBook.tierMinQty')}
                  </span>
                ),
                width: TIER_COL_WIDTH.minQty,
                render: (_, field) => (
                  <Form.Item
                    name={[field.name, 'minQuantity']}
                    rules={[{ required: true, message: t('app.master-data.priceBook.tierMinQtyRequired') }]}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={0.0001} precision={priceDecimals} style={{ width: '100%' }} />
                  </Form.Item>
                ),
              },
              {
                title: t('app.master-data.priceBook.tierMaxQty'),
                width: TIER_COL_WIDTH.maxQty,
                render: (_, field) => (
                  <Form.Item name={[field.name, 'maxQuantity']} style={{ marginBottom: 0 }}>
                    <InputNumber
                      min={0.0001}
                      precision={priceDecimals}
                      style={{ width: '100%' }}
                      placeholder="∞"
                    />
                  </Form.Item>
                ),
              },
              {
                title: (
                  <span>
                    <span style={{ color: 'var(--ant-color-error)' }}>* </span>
                    {t('app.master-data.priceBook.tierUnitPrice')}
                  </span>
                ),
                width: TIER_COL_WIDTH.unitPrice,
                render: (_, field) => (
                  <Form.Item
                    name={[field.name, 'unitPrice']}
                    rules={[{ required: true, message: t('app.master-data.priceBook.tierUnitPriceRequired') }]}
                    style={{ marginBottom: 0 }}
                  >
                    <InputNumber min={0.0001} precision={priceDecimals} style={{ width: '100%' }} />
                  </Form.Item>
                ),
              },
              {
                title: t('common.actions'),
                width: TIER_COL_WIDTH.action,
                align: 'center',
                render: (_, field) => (
                  <Button
                    type="link"
                    danger
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={() => remove(field.name)}
                  />
                ),
              },
            ];

            return (
              <div>
                <Table
                  size="small"
                  pagination={false}
                  dataSource={fields}
                  rowKey="key"
                  columns={columns}
                  scroll={{
                    x:
                      TIER_COL_WIDTH.minQty +
                      TIER_COL_WIDTH.maxQty +
                      TIER_COL_WIDTH.unitPrice +
                      TIER_COL_WIDTH.action,
                  }}
                  locale={{ emptyText: t('app.master-data.priceBook.tierTableEmpty') }}
                />
                <Button
                  type="dashed"
                  onClick={() => add({ minQuantity: 1 })}
                  block
                  icon={<PlusOutlined />}
                  style={{ marginTop: 8 }}
                >
                  {t('app.master-data.priceBook.tierAddLine')}
                </Button>
              </div>
            );
          }}
        </Form.List>
      ) : showEnableSwitch ? (
        <Typography.Text type="secondary">{t('app.master-data.priceBook.tierPricesDisabledHint')}</Typography.Text>
      ) : null}
    </div>
  );
};

export function normalizeTierPricesForSubmit(
  rows: PartnerPriceTierLineFormValue[] | undefined,
): PartnerPriceTierLineFormValue[] | undefined {
  if (!Array.isArray(rows) || rows.length === 0) return undefined;
  const cleaned = rows
    .map((row) => ({
      minQuantity: Number(row.minQuantity),
      maxQuantity:
        row.maxQuantity == null || row.maxQuantity === '' || Number.isNaN(Number(row.maxQuantity))
          ? undefined
          : Number(row.maxQuantity),
      unitPrice: Number(row.unitPrice),
    }))
    .filter(
      (row) =>
        Number.isFinite(row.minQuantity) &&
        row.minQuantity > 0 &&
        Number.isFinite(row.unitPrice) &&
        row.unitPrice > 0,
    );
  return cleaned.length ? cleaned : undefined;
}
