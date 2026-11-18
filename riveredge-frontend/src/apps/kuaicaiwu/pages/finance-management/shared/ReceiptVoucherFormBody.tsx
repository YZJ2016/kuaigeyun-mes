/**
 * 收款单新建/编辑表单体（布局对齐付款单）
 */
import React, { useCallback } from 'react';
import { Col, Row } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ProForm,
  ProFormDatePicker,
  ProFormDependency,
  ProFormDigit,
  ProFormItem,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import { LedgerAccountFormFields } from '../../../components/LedgerAccountFormFields';
import DocumentAttachmentsField from '../../../../kuaizhizao/components/DocumentAttachmentsField';
import type { BankAccount } from '../../../services/finance/bank-account';
import { financeAmountDigitFieldProps } from '../../../utils/financeFormLayout';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import { ReceiptCounterpartyPayerFormSection } from './ReceiptCounterpartyPayerFormSection';
import { pullLinesCompatibleWithSettlementType } from './useReceiptVoucherFormLinePull';

const R = 'app.kuaicaiwu.receipt';

export type ReceiptVoucherFormBodyMode = 'create' | 'edit' | 'pull';

export type ReceiptVoucherFormBodyProps = {
  mode: ReceiptVoucherFormBodyMode;
  bankAccounts: BankAccount[];
  customerOptions: Array<{ label: string; value: number }>;
  paymentMethodOptions: Array<{ label: string; value: string }>;
  settlementTypeOptions: Array<{ label: string; value: string }>;
  showPullLines?: boolean;
  pullLineColumns?: ColumnsType<any>;
  pullLineHeaderExtra?: React.ReactNode;
  pullSourceCodeLabel?: string;
  fixedSettlementType?: 'prepayment';
};

export function ReceiptVoucherFormBody({
  mode,
  bankAccounts,
  customerOptions,
  paymentMethodOptions,
  settlementTypeOptions,
  showPullLines,
  pullLineColumns,
  pullLineHeaderExtra,
  pullSourceCodeLabel,
  fixedSettlementType,
}: ReceiptVoucherFormBodyProps) {
  const { t } = useTranslation();
  const form = ProForm.useFormInstance();

  const syncPullLinesAfterSettlementChange = useCallback(
    (settlementType: string) => {
      if (!form) return;
      const items = form.getFieldValue('pull_lines');
      if (!pullLinesCompatibleWithSettlementType(items, settlementType)) {
        form.setFieldsValue({ pull_lines: [] });
      }
    },
    [form],
  );

  const onSettlementTypeChange = useCallback(
    (value: string) => {
      const next = String(value || 'normal').trim() || 'normal';
      syncPullLinesAfterSettlementChange(next);
    },
    [syncPullLinesAfterSettlementChange],
  );

  return (
    <>
      {mode === 'pull' ? (
        <Row gutter={16}>
          <Col span={8}>
            <ProFormText
              name="source_code"
              label={pullSourceCodeLabel ?? t(`${R}.pullCol.receivableCode`)}
              readonly
            />
          </Col>
          <Col span={8}>
            <ProFormText name="customer_id" hidden />
            <ProFormText
              name="customer_name"
              label={t('app.kuaicaiwu.common.customer')}
              readonly
            />
          </Col>
        </Row>
      ) : (
        <Row gutter={16}>
          <Col span={8}>
            <ProFormSelect
              name="customer_id"
              label={t('app.kuaicaiwu.common.customer')}
              options={customerOptions}
              rules={[{ required: true, message: t('app.kuaicaiwu.common.selectCustomer') }]}
              placeholder={t('app.kuaicaiwu.common.selectCustomer')}
              fieldProps={{ showSearch: true, optionFilterProp: 'label' }}
            />
          </Col>
          <Col span={8}>
            <ProFormDatePicker
              name="receipt_date"
              label={t(`${R}.col.receiptDate`)}
              rules={[{ required: true }]}
              fieldProps={{ style: { width: '100%' } }}
            />
          </Col>
          <Col span={8}>
            <ProFormSelect
              name="payment_method"
              label={t(`${R}.col.paymentMethod`)}
              options={paymentMethodOptions}
              rules={[{ required: true, message: t(`${R}.selectPaymentMethod`) }]}
              placeholder={t(`${R}.selectPaymentMethod`)}
            />
          </Col>
        </Row>
      )}

      {mode === 'pull' ? null : (
        <Row gutter={16}>
          <Col span={8}>
            <ProFormDigit
              name="total_amount"
              label={t(`${R}.col.amount`)}
              min={0.01}
              rules={[{ required: true }]}
              fieldProps={financeAmountDigitFieldProps}
            />
          </Col>
          {fixedSettlementType === 'prepayment' ? (
            <>
              <ProFormSelect name="settlement_type" hidden initialValue="prepayment" />
              <Col span={8}>
                <ProFormItem label={t(`${R}.settlementType.label`)}>
                  {t(`${R}.settlementType.prepayment`)}
                </ProFormItem>
              </Col>
            </>
          ) : (
            <Col span={8}>
              <ProFormItem
                name="settlement_type"
                label={t(`${R}.settlementType.label`)}
                initialValue="normal"
                rules={[{ required: true }]}
              >
                <ThemedSegmented
                  className="form-field-segmented"
                  style={{ width: 'fit-content', maxWidth: '100%' }}
                  options={settlementTypeOptions.map((o) => ({
                    label: o.label,
                    value: o.value,
                  }))}
                  onChange={(value) => onSettlementTypeChange(String(value ?? 'normal'))}
                />
              </ProFormItem>
            </Col>
          )}
        </Row>
      )}

      {showPullLines && pullLineColumns ? (
        <UniTableDetail
          name="pull_lines"
          title={t(`${R}.pullLines.sectionTitle`)}
          required={false}
          disabledAdd
          headerExtra={pullLineHeaderExtra}
          columns={pullLineColumns}
        />
      ) : null}

      <LedgerAccountFormFields
        accounts={bankAccounts}
        accountLabel={t(`${R}.bankAccount`)}
        noteLabel={t(`${R}.bankAccountNote`)}
        omitColProps
        rowNestedSpans={{ account: 8, note: 8 }}
        acceptanceNoteDirection="receivable"
        partnerFieldName="customer_id"
      />

      <ReceiptCounterpartyPayerFormSection />

      <Row gutter={16}>
        <Col span={24}>
          <ProFormTextArea name="notes" label={t('common.remark')} fieldProps={{ rows: 2 }} />
        </Col>
      </Row>

      <DocumentAttachmentsField category="receipt_attachments" />
    </>
  );
}