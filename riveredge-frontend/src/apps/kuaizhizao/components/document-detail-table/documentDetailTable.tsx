/**
 * 单据明细表 UI 规范（标杆：报价单明细表 quotation-detail-table）
 *
 * 销售/采购等同构明细表复用本模块，与报价单外观与行为对齐。
 * 勿修改报价单页面本身；本文件为唯一共享真源。
 */

import React, { useState } from 'react';
import { Button, Form, Input, InputNumber, Popconfirm, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';

/** 与报价单明细表一致的 table className */
export const DOCUMENT_DETAIL_TABLE_CLASS = 'quotation-detail-table';

export const DOCUMENT_DETAIL_COL_WIDTH = {
  material: 280,
  variantAttributes: 240,
  spec: 140,
  unit: 108,
  quantity: 112,
  unitPrice: 132,
  exclAmount: 120,
  taxRate: 108,
  taxAmount: 112,
  lineAmount: 132,
  deliveryDate: 152,
  notes: 140,
} as const;

export const DOCUMENT_DETAIL_TEXT_COL = { align: 'left' as const };

export const DOCUMENT_DETAIL_NUM_COL = {
  align: 'right' as const,
  onHeaderCell: () => ({ style: { textAlign: 'left' as const } }),
};

export const DOCUMENT_DETAIL_AMOUNT_STYLE: React.CSSProperties = {
  display: 'block',
  textAlign: 'right',
};

export const DOCUMENT_DETAIL_DATE_PICKER_STYLE: React.CSSProperties = {
  width: '100%',
  minWidth: 140,
};

export const DOCUMENT_DETAIL_TABLE_PROPS = {
  className: DOCUMENT_DETAIL_TABLE_CLASS,
  size: 'medium' as const,
  style: { width: '100%', margin: 0 },
};

/** 明细表行内 Input / Select / DatePicker 等与 Table medium 对齐 */
export const DOCUMENT_DETAIL_CONTROL_SIZE = 'medium' as const;

/** 明细表行内文本框空值占位（规格/型号/伙伴料号等统一，禁止混用列标题文案） */
export const DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER = '—';

export type DocumentDetailLineTextInputProps = React.ComponentProps<typeof Input>;

/** 明细表行内文本：空值占位统一为 DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER */
export function DocumentDetailLineTextInput({
  readOnly,
  placeholder = DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER,
  size = DOCUMENT_DETAIL_CONTROL_SIZE,
  ...rest
}: DocumentDetailLineTextInputProps) {
  return <Input readOnly={readOnly} placeholder={placeholder} size={size} {...rest} />;
}

export function DocumentDetailLineReadonlyTextInput(
  props: Omit<DocumentDetailLineTextInputProps, 'readOnly' | 'placeholder'>,
) {
  return (
    <DocumentDetailLineTextInput
      readOnly
      placeholder={DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER}
      {...props}
    />
  );
}

const DOCUMENT_DETAIL_TABLE_STYLE_BLOCK = `
  .quotation-detail-table .quotation-material-cell .ant-form-item,
  .quotation-detail-table .quotation-material-cell .ant-form-item-control,
  .quotation-detail-table .quotation-material-cell .ant-form-item-control-input,
  .quotation-detail-table .quotation-material-cell .ant-select,
  .quotation-detail-table .uni-detail-material-cell .ant-form-item,
  .quotation-detail-table .uni-detail-material-cell .ant-form-item-control,
  .quotation-detail-table .uni-detail-material-cell .ant-form-item-control-input,
  .quotation-detail-table .uni-detail-material-cell .ant-select {
    width: 100% !important;
    min-width: 0;
  }
  .quotation-detail-table .ant-input-number-input::selection,
  .quotation-detail-table .ant-input::selection {
    background-color: var(--ant-color-primary, #1677ff);
    color: #fff;
    border-radius: 0;
  }
  .quotation-detail-table td.ant-table-cell-align-right .ant-input-number-input {
    text-align: right;
  }
  .quotation-detail-table td.quotation-tax-rate-col {
    overflow: hidden;
  }
  .quotation-detail-table .quotation-tax-rate-cell,
  .quotation-detail-table .quotation-tax-rate-cell .ant-form-item,
  .quotation-detail-table .quotation-tax-rate-cell .ant-form-item-control-input {
    max-width: 100%;
    min-width: 0;
  }
  .quotation-detail-table .quotation-tax-rate-cell .ant-input-number-group-wrapper {
    display: flex;
    width: 100%;
    max-width: 100%;
  }
  .quotation-detail-table .quotation-tax-rate-cell .ant-input-number {
    flex: 1 1 auto;
    min-width: 0;
    width: auto !important;
  }
  .quotation-detail-table .quotation-tax-rate-cell .ant-input-number-group-addon {
    flex: 0 0 auto;
    padding-inline: 6px;
  }
`;

export function DocumentDetailTableStyles() {
  return <style>{DOCUMENT_DETAIL_TABLE_STYLE_BLOCK}</style>;
}

const TAX_RATE_BATCH_POPCONFIRM_BODY: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 10,
  minWidth: 220,
  paddingTop: 2,
};

export function TaxRateBatchColumnTitle({ onBatch }: { onBatch: (rate: number) => void }) {
  const { t } = useTranslation();
  const [rate, setRate] = useState(13);

  return (
    <span style={{ whiteSpace: 'nowrap' }}>
      {t('app.kuaizhizao.salesOrder.taxRate')}
      <Popconfirm
        icon={null}
        title={t('app.kuaizhizao.salesOrder.taxRateBatchTitle')}
        description={
          <div style={TAX_RATE_BATCH_POPCONFIRM_BODY}>
            <Typography.Text type="secondary" style={{ fontSize: 12, lineHeight: 1.5 }}>
              {t('app.kuaizhizao.salesOrder.taxRateBatchHint')}
            </Typography.Text>
            <Space.Compact style={{ width: '100%' }}>
              <InputNumber
                min={0}
                max={100}
                precision={0}
                value={rate}
                onChange={(value) => setRate(typeof value === 'number' ? value : 13)}
                style={{ width: '100%' }}
              />
              <span style={TAX_RATE_PERCENT_SUFFIX_STYLE}>%</span>
            </Space.Compact>
          </div>
        }
        onConfirm={() => {
          const num = Math.round(Number(rate));
          if (!Number.isNaN(num) && num >= 0 && num <= 100) {
            onBatch(num);
          }
        }}
        onOpenChange={(open) => {
          if (open) setRate(13);
        }}
      >
        <Button
          type="link"
          size="small"
          style={{ padding: '0 4px', height: 'auto' }}
          onClick={(e) => e.stopPropagation()}
        >
          {t('app.kuaizhizao.salesOrder.batch')}
        </Button>
      </Popconfirm>
    </span>
  );
}

const TAX_RATE_PERCENT_SUFFIX_STYLE: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: '0 4px',
  color: 'var(--ant-color-text-secondary)',
  background: 'var(--ant-color-fill-alter)',
  border: '1px solid var(--ant-color-border)',
  borderLeft: 0,
  borderRadius: '0 var(--ant-border-radius) var(--ant-border-radius) 0',
  fontSize: 'inherit',
  flexShrink: 0,
};

/** Form.Item 子组件须接收 value/onChange；不可直接用 Space.Compact 包裹 InputNumber。值一律百分比整数（13=13%），禁止小数 0.13。 */
export function TaxRatePercentInput({
  value,
  onChange,
  size = DOCUMENT_DETAIL_CONTROL_SIZE,
  inputWidth = 64,
}: {
  value?: number | null;
  onChange?: (value: number | null) => void;
  size?: typeof DOCUMENT_DETAIL_CONTROL_SIZE | 'small' | 'large';
  inputWidth?: number;
}) {
  return (
    <Space.Compact style={{ width: 'auto', minWidth: 0 }}>
      <InputNumber
        value={value}
        onChange={onChange}
        placeholder="0"
        min={0}
        max={100}
        precision={0}
        controls={false}
        size={size}
        style={{ width: inputWidth, minWidth: 0 }}
      />
      <span style={TAX_RATE_PERCENT_SUFFIX_STYLE}>%</span>
    </Space.Compact>
  );
}

export function TaxRateDetailCell({ index }: { index: number }) {
  return (
    <div className="quotation-tax-rate-cell">
      <Form.Item name={[index, 'tax_rate']} style={{ margin: 0 }}>
        <TaxRatePercentInput />
      </Form.Item>
    </div>
  );
}

export const DOCUMENT_DETAIL_TAX_RATE_COL_BASE = {
  dataIndex: 'tax_rate',
  width: DOCUMENT_DETAIL_COL_WIDTH.taxRate,
  ...DOCUMENT_DETAIL_NUM_COL,
  onCell: () => ({ className: 'quotation-tax-rate-col' }),
};
