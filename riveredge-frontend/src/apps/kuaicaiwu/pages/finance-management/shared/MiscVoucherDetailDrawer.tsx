/**
 * 其他收入 / 其他费用支出 / 费用申请 详情抽屉（业务单据规范壳）。
 */

import React, { useMemo } from 'react';
import { Button, Descriptions, Result, Table } from 'antd';
import type { ProDescriptionsItemProps } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import {
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  detailDrawerBasicColumn,
  useDetailDrawerDescriptionItems,
} from '../../../../../components/layout-templates';
import { UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import {
  GLOBAL_DOC_DETAIL_BASIC_FIELD_RANK,
  alignDescriptionColumns,
} from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { getFinanceVoucherLifecycle } from '../../../utils/financeLifecycle';
import {
  formatPaymentMethod,
  isEmployeeAdvancePaymentMethod,
} from '../../../utils/financeSharedOptions';
import { formatCurrencyAmount } from '../../../../../utils/format';
import {
  DocumentAttachmentsReadonly,
  documentAttachmentsFromRecord,
} from '../../../../kuaizhizao/components/DocumentAttachmentsReadonly';
import { formatPayeeAccountFields } from '../../../utils/partnerPayeeAccounts';
import type { RelatedPurchaseReceiptRef } from '../../../services/finance/other-expense';

export type MiscVoucherDetailRecord = {
  id: number;
  income_code?: string;
  expense_code?: string;
  application_code?: string;
  business_date?: string;
  total_amount?: number;
  status?: string;
  review_status?: string;
  counterparty_kind?: string;
  counterparty_name?: string;
  payment_method?: string;
  notes?: string;
  department_name?: string;
  counterparty_account_name?: string;
  counterparty_bank_name?: string;
  counterparty_bank_account?: string;
  bank_account_id?: number;
  related_purchase_receipts?: RelatedPurchaseReceiptRef[] | null;
  attachments?: Array<Record<string, unknown>>;
  lines?: Array<{
    category_name?: string;
    description?: string;
    amount?: number;
    payee_name?: string;
  }>;
  receivable_id?: number | null;
  receivable_code?: string | null;
  receipt_id?: number | null;
  receipt_code?: string | null;
  payable_id?: number | null;
  payable_code?: string | null;
  payment_id?: number | null;
  payment_code?: string | null;
};

export type MiscVoucherDetailDrawerProps = {
  open: boolean;
  onClose: () => void;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  record: MiscVoucherDetailRecord | null;
  codeField: 'income_code' | 'expense_code' | 'application_code';
  i18nPrefix: string;
  kind: 'income' | 'expense';
  isExpenseApplication: boolean;
  isOtherExpenseDoc: boolean;
  bankAccountLabel?: string;
  documentType: string;
  extra?: React.ReactNode;
  renderDocumentStatus: (row: MiscVoucherDetailRecord) => React.ReactNode;
  onOpenLinkedDocument?: (type: string, id: number) => void;
};

const PLACEHOLDER: MiscVoucherDetailRecord = {
  id: 0,
  business_date: '',
  total_amount: 0,
  status: '',
};

function resolveCode(
  row: MiscVoucherDetailRecord,
  codeField: 'income_code' | 'expense_code' | 'application_code',
): string {
  return String(row[codeField] ?? '').trim();
}

export const MiscVoucherDetailDrawer: React.FC<MiscVoucherDetailDrawerProps> = ({
  open,
  onClose,
  loading = false,
  error = null,
  onRetry,
  record,
  codeField,
  i18nPrefix,
  kind,
  isExpenseApplication,
  isOtherExpenseDoc,
  bankAccountLabel,
  documentType,
  extra,
  renderDocumentStatus,
  onOpenLinkedDocument,
}) => {
  const { t } = useTranslation();

  const contentReady = Boolean(record);
  const showError = Boolean(error) && !contentReady && !loading;
  const showLoading = loading || (!contentReady && !showError);
  const effective = record ?? PLACEHOLDER;
  const code = resolveCode(effective, codeField);
  const title = code || t('app.uniDetail.sectionBasic');

  const basicColumns = useMemo(() => {
    const cols: ProDescriptionsItemProps<MiscVoucherDetailRecord>[] = [
      {
        key: 'document_code',
        title: t(`${i18nPrefix}.col.code`),
        dataIndex: codeField,
      },
      {
        key: 'business_date',
        title: t(`${i18nPrefix}.col.businessDate`),
        dataIndex: 'business_date',
        valueType: 'date',
      },
      {
        key: 'lifecycle',
        title: t('common.status'),
        dataIndex: 'review_status',
        render: () => (contentReady ? renderDocumentStatus(effective) : '—'),
      },
      {
        key: 'total_amount',
        title: t(`${i18nPrefix}.col.amount`),
        dataIndex: 'total_amount',
        render: (_, row) => formatCurrencyAmount(row.total_amount),
      },
      {
        key: 'counterparty_name',
        title: t(`${i18nPrefix}.col.counterparty`),
        dataIndex: 'counterparty_name',
        render: (_, row) => row.counterparty_name || '—',
      },
    ];

    if (
      kind === 'expense'
      && !isEmployeeAdvancePaymentMethod(effective.payment_method)
      && ['supplier', 'employee'].includes(String(effective.counterparty_kind ?? ''))
    ) {
      cols.push({
        key: 'counterparty_account',
        title: t('app.kuaicaiwu.payment.counterpartyAccountPick'),
        render: () =>
          formatPayeeAccountFields(
            effective.counterparty_account_name,
            effective.counterparty_bank_name,
            effective.counterparty_bank_account,
          ) || '—',
      });
    }

    cols.push({
      key: 'department_name',
      title: isOtherExpenseDoc
        ? t('app.kuaicaiwu.otherExpense.field.applicationDepartment')
        : t(`${i18nPrefix}.field.department`),
      dataIndex: 'department_name',
      render: (_, row) => row.department_name || '—',
    });

    if (!isExpenseApplication) {
      cols.push({
        key: 'payment_method',
        title: t(`${i18nPrefix}.field.paymentMethod`),
        dataIndex: 'payment_method',
        render: (_, row) => formatPaymentMethod(row.payment_method, t),
      });
    }

    if (isOtherExpenseDoc) {
      cols.push({
        key: 'employee_advance',
        title: t('app.kuaicaiwu.otherExpense.field.employeeAdvance'),
        render: () =>
          isEmployeeAdvancePaymentMethod(effective.payment_method)
            ? t('common.yes')
            : t('common.no'),
      });
      if (isEmployeeAdvancePaymentMethod(effective.payment_method)) {
        cols.push({
          key: 'advance_payee',
          title: t('app.kuaicaiwu.payment.advancePayee'),
          render: () =>
            effective.lines?.find((l) => l.payee_name)?.payee_name || '—',
        });
      }
    }

    if (kind === 'income' && bankAccountLabel) {
      cols.push({
        key: 'bank_account',
        title: t(`${i18nPrefix}.field.bankAccount`),
        render: () => bankAccountLabel || '—',
      });
    }

    if (kind === 'expense') {
      cols.push({
        key: 'related_purchase_receipts',
        title: t(`${i18nPrefix}.relatedPurchaseReceipts`),
        span: 3,
        render: () => {
          const items = effective.related_purchase_receipts;
          if (!Array.isArray(items) || items.length === 0) return '—';
          return (
            <>
              {items.map((item) => (
                <Button
                  key={item.id}
                  type="link"
                  size="small"
                  style={{ padding: 0, height: 'auto', marginRight: 8 }}
                  onClick={() => onOpenLinkedDocument?.('purchase_receipt', Number(item.id))}
                >
                  {item.code || item.id}
                </Button>
              ))}
            </>
          );
        },
      });
    }

    cols.push({
      key: 'attachments',
      title: t(`${i18nPrefix}.field.attachments`),
      span: 3,
      render: () => (
        <DocumentAttachmentsReadonly
          attachments={documentAttachmentsFromRecord(effective)}
          showEmpty
          variant="list"
        />
      ),
    });

    if (kind === 'income' && effective.receivable_id) {
      cols.push({
        key: 'receivable_link',
        title: t('app.kuaicaiwu.otherIncome.finance.receivable'),
        render: () => (
          <Button
            type="link"
            size="small"
            style={{ padding: 0, height: 'auto' }}
            onClick={() => onOpenLinkedDocument?.('receivable', Number(effective.receivable_id))}
          >
            {effective.receivable_code || effective.receivable_id}
          </Button>
        ),
      });
    }
    if (kind === 'income' && effective.receipt_id) {
      cols.push({
        key: 'receipt_link',
        title: t('app.kuaicaiwu.otherIncome.finance.receipt'),
        render: () => (
          <Button
            type="link"
            size="small"
            style={{ padding: 0, height: 'auto' }}
            onClick={() => onOpenLinkedDocument?.('receipt', Number(effective.receipt_id))}
          >
            {effective.receipt_code || effective.receipt_id}
          </Button>
        ),
      });
    }
    if (kind === 'expense' && effective.payable_id) {
      cols.push({
        key: 'payable_link',
        title: t('app.kuaicaiwu.otherExpense.finance.payable'),
        render: () => (
          <Button
            type="link"
            size="small"
            style={{ padding: 0, height: 'auto' }}
            onClick={() => onOpenLinkedDocument?.('payable', Number(effective.payable_id))}
          >
            {effective.payable_code || effective.payable_id}
          </Button>
        ),
      });
    }
    if (kind === 'expense' && effective.payment_id) {
      cols.push({
        key: 'payment_link',
        title: t('app.kuaicaiwu.otherExpense.finance.payment'),
        render: () => (
          <Button
            type="link"
            size="small"
            style={{ padding: 0, height: 'auto' }}
            onClick={() => onOpenLinkedDocument?.('payment', Number(effective.payment_id))}
          >
            {effective.payment_code || effective.payment_id}
          </Button>
        ),
      });
    }

    cols.push({
      key: 'notes',
      title: t(`${i18nPrefix}.field.notes`),
      dataIndex: 'notes',
      span: 3,
      render: (_, row) => row.notes || '—',
    });

    return alignDescriptionColumns(cols, GLOBAL_DOC_DETAIL_BASIC_FIELD_RANK);
  }, [
    bankAccountLabel,
    codeField,
    contentReady,
    effective,
    i18nPrefix,
    isExpenseApplication,
    isOtherExpenseDoc,
    kind,
    onOpenLinkedDocument,
    renderDocumentStatus,
    t,
  ]);

  const basicItems = useDetailDrawerDescriptionItems(
    basicColumns,
    contentReady ? effective : null,
    documentType,
  );

  const lifecycle = getFinanceVoucherLifecycle(effective as unknown as Record<string, unknown>, t);
  const steps = lifecycle.mainStages ?? [];

  const lineColumns = useMemo(
    () => [
      { title: t(`${i18nPrefix}.line.category`), dataIndex: 'category_name' },
      { title: t(`${i18nPrefix}.line.description`), dataIndex: 'description' },
      {
        title: isExpenseApplication
          ? t('app.kuaicaiwu.otherExpenseApplication.line.estimatedAmount')
          : t(`${i18nPrefix}.line.amount`),
        dataIndex: 'amount',
        render: (v: number) => formatCurrencyAmount(v),
      },
    ],
    [i18nPrefix, isExpenseApplication, t],
  );

  if (!open) return null;

  return (
    <DetailDrawerTemplate
      title={title}
      open={open}
      onClose={onClose}
      size={DRAWER_CONFIG.HALF_WIDTH}
      loading={showLoading}
      extra={contentReady ? extra ?? null : null}
      plainBody={
        showError ? (
          <Result
            status="error"
            title={error}
            extra={
              onRetry ? (
                <Button type="primary" onClick={onRetry}>
                  {t('common.retry', { defaultValue: '重试' })}
                </Button>
              ) : null
            }
          />
        ) : undefined
      }
      basic={
        contentReady ? (
          <Descriptions column={detailDrawerBasicColumn(false)} size="small" items={basicItems} />
        ) : showError ? null : (
          <div style={{ minHeight: 80 }} />
        )
      }
      collaborationTitle={t('app.kuaicaiwu.common.lifecycle')}
      collaborationLifecycle={
        contentReady && steps.length > 0 ? (
          <UniLifecycleStepper
            steps={steps}
            showLabels
            status={lifecycle.status}
            nextStepSuggestions={lifecycle.nextStepSuggestions}
            hideNextStepSuggestions
          />
        ) : undefined
      }
      linesTitle={t('app.uniDetail.sectionLines')}
      linesVisible={contentReady && (effective.lines?.length ?? 0) > 0}
      lines={
        contentReady && (effective.lines?.length ?? 0) > 0 ? (
          <Table
            size="small"
            pagination={false}
            rowKey={(_, i) => String(i)}
            dataSource={effective.lines ?? []}
            columns={lineColumns}
          />
        ) : undefined
      }
    />
  );
};