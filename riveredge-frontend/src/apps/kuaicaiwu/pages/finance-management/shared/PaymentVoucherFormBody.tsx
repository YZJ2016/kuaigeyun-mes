/**
 * 付款单新建/编辑/取单预览表单体（布局对齐付款申请 FormModal）
 */
import React, { useCallback } from 'react';
import { Col, Row, Typography } from 'antd';
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
import {
  financeAmountDigitFieldProps,
} from '../../../utils/financeFormLayout';
import {
  BANK_TRANSFER_PAYMENT_METHOD,
  EMPLOYEE_ADVANCE_PAYMENT_METHOD,
  PREPAYMENT_OFFSET_PAYMENT_METHOD,
  hidesSupplierPayeeAccount,
  isPrepaymentOffsetPaymentMethod,
} from '../../../utils/financeSharedOptions';
import { PaymentAdvancePayeeField } from './PaymentAdvancePayeeField';
import { PaymentCounterpartyFormSection } from './PaymentCounterpartyFormSection';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import { pullLinesCompatibleWithSettlementType } from './usePaymentVoucherFormLinePull';

const P = 'app.kuaicaiwu.payment';

export type PaymentVoucherFormBodyMode = 'create' | 'edit' | 'pull';

export type PaymentVoucherFormBodyProps = {
  mode: PaymentVoucherFormBodyMode;
  bankAccounts: BankAccount[];
  supplierOptions: Array<{ label: string; value: number }>;
  paymentMethodOptions: Array<{ label: string; value: string }>;
  settlementTypeOptions: Array<{ label: string; value: string }>;
  attachmentsRequired?: boolean;
  attachmentsRequiredMessage?: string;
  /** 付款明细（取应付/取申请） */
  showPullLines?: boolean;
  pullLineColumns?: ColumnsType<Record<string, unknown>>;
  pullLineHeaderExtra?: React.ReactNode;
  /** 预付抵扣：预付款明细 */
  offsetPrepaymentLineColumns?: ColumnsType<Record<string, unknown>>;
  offsetPrepaymentHeaderExtra?: React.ReactNode;
  /** 取单预览：来源单号字段标签（默认应付单） */
  pullSourceCodeLabel?: string;
  /** 锁定结算类型为预付（采购订单下推预付付款单） */
  fixedSettlementType?: 'prepayment';
  hideCounterpartySection?: boolean;
  showAttachments?: boolean;
};

export function PaymentVoucherFormBody({
  mode,
  bankAccounts,
  supplierOptions,
  paymentMethodOptions,
  settlementTypeOptions,
  attachmentsRequired,
  attachmentsRequiredMessage,
  showPullLines,
  pullLineColumns,
  pullLineHeaderExtra,
  offsetPrepaymentLineColumns,
  offsetPrepaymentHeaderExtra,
  pullSourceCodeLabel,
  fixedSettlementType,
  hideCounterpartySection = false,
  showAttachments = true,
}: PaymentVoucherFormBodyProps) {
  const { t } = useTranslation();
  const form = ProForm.useFormInstance();

  const syncPullLinesAfterSettlementOrMethodChange = useCallback(
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
      if (!form) return;
      const next = String(value || 'normal').trim() || 'normal';
      if (
        next === 'prepayment' &&
        isPrepaymentOffsetPaymentMethod(form.getFieldValue('payment_method'))
      ) {
        form.setFieldsValue({
          payment_method: BANK_TRANSFER_PAYMENT_METHOD,
          bank_account_id: undefined,
          bank_account: undefined,
        });
      }
      syncPullLinesAfterSettlementOrMethodChange(next);
    },
    [form, syncPullLinesAfterSettlementOrMethodChange],
  );

  const onPaymentMethodChange = useCallback(
    (method: string) => {
      if (!form) return;
      const normalized = String(method || '').trim();
      if (isPrepaymentOffsetPaymentMethod(normalized)) {
        form.setFieldsValue({
          settlement_type: 'normal',
          bank_account_id: undefined,
          bank_account: undefined,
          offset_prepayment_lines: [],
        });
        syncPullLinesAfterSettlementOrMethodChange('normal');
      } else {
        form.setFieldsValue({ offset_prepayment_lines: [] });
      }
      if (hidesSupplierPayeeAccount(normalized)) {
        form.setFieldsValue({
          counterparty_account_name: undefined,
          counterparty_bank_name: undefined,
          counterparty_bank_account: undefined,
        });
      }
    },
    [form, syncPullLinesAfterSettlementOrMethodChange],
  );

  const prepaymentSettlementField =
    fixedSettlementType === 'prepayment' ? (
      <>
        <ProFormText name="settlement_type" hidden initialValue="prepayment" />
        <Col span={8}>
          <ProFormItem label={t(`${P}.settlementType.label`)}>
            <Typography.Text>{t('app.kuaicaiwu.payment.settlementType.prepayment')}</Typography.Text>
          </ProFormItem>
        </Col>
      </>
    ) : null;

  const paymentAmountField = (
    <ProFormDependency name={['payment_method']}>
      {({ payment_method: payMethod }) => {
        const offsetMode = isPrepaymentOffsetPaymentMethod(payMethod);
        return (
          <Col span={8}>
            <ProFormDigit
              name="total_amount"
              label={
                offsetMode ? t(`${P}.col.prepaymentOffsetTotal`) : t(`${P}.col.amount`)
              }
              min={0.01}
              rules={[{ required: true }]}
              fieldProps={financeAmountDigitFieldProps}
            />
          </Col>
        );
      }}
    </ProFormDependency>
  );

  return (
    <>
      {mode === 'pull' ? (
        <>
          <ProFormText name="supplier_id" hidden />
          <Row gutter={16}>
            <Col span={8}>
              <ProFormText
                name="source_code"
                label={pullSourceCodeLabel ?? t(`${P}.sourcePayable`)}
                readonly
              />
            </Col>
            <Col span={8}>
              <ProFormText
                name="supplier_name"
                label={t('app.kuaicaiwu.common.supplier')}
                readonly
              />
            </Col>
            {fixedSettlementType === 'prepayment' ? prepaymentSettlementField : null}
          </Row>
          {fixedSettlementType === 'prepayment' ? (
            <Row gutter={16}>
              <Col span={8}>
                <ProFormSelect
                  name="payment_method"
                  label={t(`${P}.col.paymentMethod`)}
                  options={paymentMethodOptions}
                  rules={[{ required: true, message: t(`${P}.selectPaymentMethod`) }]}
                  placeholder={t(`${P}.selectPaymentMethod`)}
                  fieldProps={{
                    onChange: (value: string) => onPaymentMethodChange(String(value ?? '')),
                  }}
                />
              </Col>
              {paymentAmountField}
              <Col span={8}>
                <ProFormDatePicker
                  name="payment_date"
                  label={t(`${P}.col.paymentDate`)}
                  rules={[{ required: true }]}
                  fieldProps={{ style: { width: '100%' } }}
                />
              </Col>
            </Row>
          ) : (
            <Row gutter={16}>
              <Col span={8}>
                <ProFormSelect
                  name="payment_method"
                  label={t(`${P}.col.paymentMethod`)}
                  options={paymentMethodOptions}
                  rules={[{ required: true, message: t(`${P}.selectPaymentMethod`) }]}
                  placeholder={t(`${P}.selectPaymentMethod`)}
                  fieldProps={{
                    onChange: (value: string) => onPaymentMethodChange(String(value ?? '')),
                  }}
                />
              </Col>
              {paymentAmountField}
              <Col span={8}>
                <ProFormDatePicker
                  name="payment_date"
                  label={t(`${P}.col.paymentDate`)}
                  rules={[{ required: true }]}
                  fieldProps={{ style: { width: '100%' } }}
                />
              </Col>
            </Row>
          )}
        </>
      ) : (
        <Row gutter={16}>
          <Col span={8}>
            <ProFormSelect
              name="supplier_id"
              label={t('app.kuaicaiwu.common.supplier')}
              options={supplierOptions}
              rules={[{ required: true, message: t('app.kuaicaiwu.common.selectSupplier') }]}
              placeholder={t('app.kuaicaiwu.common.selectSupplier')}
              fieldProps={{ showSearch: true, optionFilterProp: 'label' }}
            />
          </Col>
          <Col span={8}>
            <ProFormDatePicker
              name="payment_date"
              label={t(`${P}.col.paymentDate`)}
              rules={[{ required: true }]}
              fieldProps={{ style: { width: '100%' } }}
            />
          </Col>
        </Row>
      )}

      {mode === 'pull' && fixedSettlementType === 'prepayment' ? (
        <ProFormDependency name={['payment_method']}>
          {({ payment_method: method }) =>
            method === EMPLOYEE_ADVANCE_PAYMENT_METHOD ? (
              <Row gutter={16}>
                <Col span={8}>
                  <PaymentAdvancePayeeField colProps={false} />
                </Col>
              </Row>
            ) : null
          }
        </ProFormDependency>
      ) : (
        <Row gutter={16}>
          {mode === 'pull' ? null : (
            <ProFormDependency name={['settlement_type']}>
              {({ settlement_type: settlementType }) => {
                const st = String(settlementType || 'normal').trim() || 'normal';
                const methodOptions =
                  st === 'prepayment'
                    ? paymentMethodOptions.filter(
                        (o) => o.value !== PREPAYMENT_OFFSET_PAYMENT_METHOD,
                      )
                    : paymentMethodOptions;
                return (
                  <Col span={8}>
                    <ProFormSelect
                      name="payment_method"
                      label={t(`${P}.col.paymentMethod`)}
                      options={methodOptions}
                      rules={[{ required: true, message: t(`${P}.selectPaymentMethod`) }]}
                      placeholder={t(`${P}.selectPaymentMethod`)}
                      fieldProps={{
                        onChange: (value: string) => onPaymentMethodChange(String(value ?? '')),
                      }}
                    />
                  </Col>
                );
              }}
            </ProFormDependency>
          )}
          {mode === 'pull' ? null : paymentAmountField}
          {fixedSettlementType === 'prepayment' ? null : (
            <ProFormDependency name={['payment_method']}>
              {({ payment_method: payMethod }) => {
                const prepayOffsetLocked = isPrepaymentOffsetPaymentMethod(payMethod);
                if (prepayOffsetLocked) {
                  return (
                    <>
                      <ProFormText name="settlement_type" hidden initialValue="normal" />
                      <Col span={8}>
                        <ProFormItem label={t(`${P}.settlementType.label`)}>
                          <Typography.Text>
                            {t('app.kuaicaiwu.payment.settlementType.normal')}
                          </Typography.Text>
                        </ProFormItem>
                      </Col>
                    </>
                  );
                }
                return (
                  <Col span={8}>
                    <ProFormItem
                      name="settlement_type"
                      label={t(`${P}.settlementType.label`)}
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
                );
              }}
            </ProFormDependency>
          )}
          <ProFormDependency name={['payment_method']}>
            {({ payment_method: method }) =>
              method === EMPLOYEE_ADVANCE_PAYMENT_METHOD ? (
                <Col span={8}>
                  <PaymentAdvancePayeeField colProps={false} />
                </Col>
              ) : null
            }
          </ProFormDependency>
        </Row>
      )}

      <ProFormDependency name={['payment_method']}>
        {({ payment_method: method }) =>
          isPrepaymentOffsetPaymentMethod(method) ? null : (
            <LedgerAccountFormFields
              accounts={bankAccounts}
              accountLabel={t(`${P}.outBankAccount`)}
              noteLabel={t(`${P}.outAccountNote`)}
              omitColProps
              rowNestedSpans={{ account: 8, note: 8 }}
              acceptanceNoteDirection="payable"
              partnerFieldName="supplier_id"
              forceAccountRequired
            />
          )
        }
      </ProFormDependency>

      {showPullLines && pullLineColumns ? (
        <ProFormDependency name={['payment_method']}>
          {({ payment_method: method }) => {
            const offsetMode = isPrepaymentOffsetPaymentMethod(method);
            return (
              <>
                <UniTableDetail
                  name="pull_lines"
                  title={
                    offsetMode
                      ? t(`${P}.pullLines.offsetPayableSectionTitle`)
                      : t(`${P}.pullLines.sectionTitle`)
                  }
                  required={false}
                  disabledAdd
                  headerExtra={pullLineHeaderExtra}
                  columns={pullLineColumns}
                />
                {offsetMode && offsetPrepaymentLineColumns ? (
                  <>
                    <UniTableDetail
                      name="offset_prepayment_lines"
                      title={t(`${P}.pullLines.offsetPrepaymentSectionTitle`)}
                      required={false}
                      disabledAdd
                      headerExtra={offsetPrepaymentHeaderExtra}
                      columns={offsetPrepaymentLineColumns}
                    />
                    <Typography.Paragraph type="secondary" style={{ marginTop: 4, marginBottom: 8 }}>
                      {t(`${P}.pullLines.prepaymentOffsetHint`)}
                    </Typography.Paragraph>
                  </>
                ) : null}
              </>
            );
          }}
        </ProFormDependency>
      ) : null}

      {hideCounterpartySection ? null : <PaymentCounterpartyFormSection />}

      <Row gutter={16}>
        <Col span={24}>
          <ProFormTextArea name="notes" label={t('common.remark')} fieldProps={{ rows: 2 }} />
        </Col>
      </Row>

      {showAttachments ? (
        <DocumentAttachmentsField
          category="payment_attachments"
          required={attachmentsRequired}
          requiredMessage={attachmentsRequiredMessage}
        />
      ) : null}
    </>
  );
}
