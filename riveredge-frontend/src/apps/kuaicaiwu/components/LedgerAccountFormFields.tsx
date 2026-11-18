/**
 * 收/付款单入账账户字段：按付款方式过滤银行账户 / 库存现金。
 */
import React, { useEffect, useRef } from 'react';
import { Col, Row } from 'antd';
import { FORM_LAYOUT } from '../../../components/layout-templates/constants';
import { ProForm, ProFormDependency, ProFormSelect, ProFormText } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import type { BankAccount } from '../services/finance/bank-account';
import {
  filterBankAccountsForPaymentMethod,
  formatBankAccountOptionLabel,
  isNotePaymentMethod,
  isCashPaymentMethod,
  requiresLedgerAccount,
} from '../utils/financeSharedOptions';
import { AcceptanceBillLinkFields } from './AcceptanceBillLinkFields';
import type { FinanceNoteDirection } from '../services/finance/note';

type Props = {
  accounts: BankAccount[];
  accountLabel: string;
  noteLabel: string;
  noteName?: string;
  accountColProps?: { span: number };
  noteColProps?: { span: number };
  /**
   * 父级已用 `grid={false}` + 手写 Row/Col 时开启：不再传 ProForm colProps，避免嵌套 Col 裁切标签。
   */
  omitColProps?: boolean;
  /** 与 `FinanceFormFieldGroup` 内 Row 联用：字段外包 Col，须同时 omitColProps */
  rowNestedSpans?: { account: number; note: number };
  /** 父级已包 Row 时：直接输出 Col 子项，不再套 Col24/内层 Row */
  parentProvidesRow?: boolean;
  /** 付款方式为「票据」时关联应收/应付票据台账 */
  acceptanceNoteDirection?: FinanceNoteDirection;
  partnerFieldName?: 'customer_id' | 'supplier_id';
};

function SyncLedgerAccountWithPaymentMethod({ accounts }: { accounts: BankAccount[] }) {
  const form = ProForm.useFormInstance();
  const paymentMethod = ProForm.useWatch('payment_method', form);
  const bankAccountId = ProForm.useWatch('bank_account_id', form);
  const prevPaymentMethodRef = useRef<string | undefined>();

  useEffect(() => {
    if (paymentMethod === undefined) return;

    const methodChanged = prevPaymentMethodRef.current !== paymentMethod;
    prevPaymentMethodRef.current = paymentMethod;

    const filtered = filterBankAccountsForPaymentMethod(accounts, paymentMethod);
    const validIds = new Set(filtered.map((a) => a.id));
    const currentId =
      bankAccountId != null && bankAccountId !== '' ? Number(bankAccountId) : null;

    if (currentId != null && !validIds.has(currentId)) {
      form.setFieldValue('bank_account_id', undefined);
      if (requiresLedgerAccount(paymentMethod) && filtered.length === 1) {
        form.setFieldValue('bank_account_id', filtered[0].id);
      }
      return;
    }

    if (
      methodChanged &&
      requiresLedgerAccount(paymentMethod) &&
      filtered.length === 1 &&
      currentId == null
    ) {
      form.setFieldValue('bank_account_id', filtered[0].id);
    }
  }, [paymentMethod, accounts, bankAccountId, form]);

  return null;
}

export const LedgerAccountFormFields: React.FC<Props> = ({
  accounts,
  accountLabel,
  noteLabel,
  noteName = 'bank_account',
  accountColProps = { span: 12 },
  noteColProps = { span: 12 },
  omitColProps = false,
  rowNestedSpans,
  parentProvidesRow = false,
  acceptanceNoteDirection,
  partnerFieldName = 'customer_id',
}) => {
  const { t } = useTranslation();
  const nested = rowNestedSpans != null;
  const inlineInParentRow = nested && parentProvidesRow;
  const accountCols = omitColProps || nested ? undefined : accountColProps;
  const noteCols = omitColProps || nested ? undefined : noteColProps;

  const wrapNested = (node: React.ReactNode, span: number) =>
    nested ? <Col span={span}>{node}</Col> : node;

  const layoutNested = (cols: React.ReactNode) => {
    if (!nested) return cols;
    if (inlineInParentRow) return cols;
    return (
      <Row gutter={FORM_LAYOUT.GRID_GUTTER} className="finance-form-field-group__row" wrap>
        {cols}
      </Row>
    );
  };

  const dependencyBody = (
    <ProFormDependency name={['payment_method']}>
      {({ payment_method }) => {
          if (isNotePaymentMethod(payment_method)) {
            if (acceptanceNoteDirection) {
              const acceptanceFields = (
                <AcceptanceBillLinkFields
                  direction={acceptanceNoteDirection}
                  partnerFieldName={partnerFieldName}
                  noteName={noteName}
                  colProps={noteCols}
                  rowNestedFieldSpan={nested ? 12 : undefined}
                />
              );
              return layoutNested(acceptanceFields);
            }
            return layoutNested(
              wrapNested(
                <ProFormText
                  name={noteName}
                  label={t('app.kuaicaiwu.common.referenceNumber')}
                  colProps={noteCols}
                  placeholder={t('app.kuaicaiwu.common.referenceNumberPlaceholder')}
                  rules={[{ required: true, message: t('app.kuaicaiwu.common.referenceNumberRequired') }]}
                />,
                rowNestedSpans?.note ?? 12,
              ),
            );
          }

          const filtered = filterBankAccountsForPaymentMethod(accounts, payment_method);
          const options = filtered.map((a) => ({
            label: formatBankAccountOptionLabel(a),
            value: a.id,
          }));
          const cash = isCashPaymentMethod(payment_method);
          const required = requiresLedgerAccount(payment_method);
          const emptyHint = cash
            ? t('app.kuaicaiwu.receipt.bankAccountCashEmptyHint')
            : t('app.kuaicaiwu.receipt.bankAccountEmptyHint');
          const placeholder = options.length === 0
            ? (cash
              ? t('app.kuaicaiwu.common.noCashAccountHint')
              : t('app.kuaicaiwu.common.noBankAccountHint'))
            : (cash
              ? t('app.kuaicaiwu.receipt.bankAccountCashPlaceholder')
              : t('app.kuaicaiwu.receipt.bankAccountPlaceholder'));
          return layoutNested(
            <>
              {wrapNested(
                <ProFormSelect
                  name="bank_account_id"
                  label={accountLabel}
                  colProps={accountCols}
                  options={options}
                  placeholder={placeholder}
                  showSearch
                  allowClear={!required}
                  fieldProps={{
                    optionFilterProp: 'label',
                    optionLabelProp: 'label',
                  }}
                  extra={options.length === 0 && required ? emptyHint : undefined}
                  rules={[
                    ({ getFieldValue }) => ({
                      validator: async (_, value) => {
                        if (requiresLedgerAccount(getFieldValue('payment_method')) && !value) {
                          if (isCashPaymentMethod(getFieldValue('payment_method'))) {
                            throw new Error(t('app.kuaicaiwu.common.bankAccountRequiredForCash'));
                          }
                          throw new Error(t('app.kuaicaiwu.common.bankAccountRequiredForTransfer'));
                        }
                      },
                    }),
                  ]}
                />,
                rowNestedSpans?.account ?? 12,
              )}
              {wrapNested(
                <ProFormText
                  name={noteName}
                  label={noteLabel}
                  colProps={noteCols}
                  placeholder={t('app.kuaicaiwu.receipt.bankAccountNotePlaceholder')}
                />,
                rowNestedSpans?.note ?? 12,
              )}
            </>,
          );
        }}
      </ProFormDependency>
  );

  return (
    <>
      <SyncLedgerAccountWithPaymentMethod accounts={accounts} />
      {dependencyBody}
    </>
  );
};

export function resolveLedgerAccountNote(
  accounts: BankAccount[],
  bankAccountId: unknown,
  fallback?: string,
): string | undefined {
  if (bankAccountId == null || bankAccountId === '') return fallback;
  const acc = accounts.find((a) => a.id === Number(bankAccountId));
  if (!acc) return fallback;
  return acc.account_number || acc.account_name || fallback;
}

export function resolveFinanceVoucherReferenceNote(
  accounts: BankAccount[],
  paymentMethod: string | null | undefined,
  bankAccountId: unknown,
  fallback?: string,
): string | undefined {
  if (isNotePaymentMethod(paymentMethod)) {
    const reference = String(fallback ?? '').trim();
    return reference || undefined;
  }
  return resolveLedgerAccountNote(accounts, bankAccountId, fallback);
}
