/**
 * 预付抵扣：预付款付款单明细取单与表格列
 */
import React, { useCallback, useMemo, useRef } from 'react';
import type { ProFormInstance } from '@ant-design/pro-components';
import { App, Button, Form, Input, InputNumber } from 'antd';
import type { FormListFieldData } from 'antd/es/form';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import { UniPullQueryModal, useUniPullQuery } from '../../../../../components/uni-pull-query';
import { formatCurrencyAmount } from '../../../../../utils/format';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import {
  paymentService,
  type PrepaymentPaymentPullCandidate,
} from '../../../services/finance/payment';
import { loadFinancePullCandidatePage } from './loadFinancePullCandidatePage';
import { financeAmountDigitFieldProps } from '../../../utils/financeFormLayout';
import { buildPrepaymentPaymentPullQueryColumns } from './prepaymentPaymentPullQueryColumns';
import { syncPaymentHeaderFromOffsetPrepaymentLines } from './usePaymentVoucherFormLinePull';

const P = 'app.kuaicaiwu.payment';

type Props = {
  formRef: React.RefObject<ProFormInstance | undefined>;
};

function isPrepaymentPullSelectable(record: PrepaymentPaymentPullCandidate): boolean {
  return record.capabilities?.pull_payment?.allowed !== false;
}

export function usePaymentVoucherFormPrepaymentOffsetLines({ formRef }: Props) {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const closeModalRef = useRef<(() => void) | null>(null);

  const assertSupplierSelected = useCallback((): number | null => {
    const supplierId = Number(formRef.current?.getFieldValue('supplier_id'));
    if (!Number.isFinite(supplierId) || supplierId <= 0) {
      messageApi.warning(t(`${P}.selectSupplierFirst`));
      return null;
    }
    return supplierId;
  }, [formRef, messageApi, t]);

  const scopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' as const },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' as const },
    ],
    [t],
  );

  const pullQuery = useUniPullQuery<PrepaymentPaymentPullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => !isPrepaymentPullSelectable(record),
    loadData: async (params) => {
      const supplierId = assertSupplierSelected();
      if (supplierId == null) return { data: [], total: 0 };
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          isPrepaymentPullSelectable,
          (api) =>
            paymentService.listPrepaymentPaymentPullCandidates({
              ...api,
              supplier_id: supplierId,
            }),
          { supplierId },
        );
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (_keys, rows) => {
      const existing = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('offset_prepayment_lines'),
      );
      const usedIds = new Set(
        existing.map((r) => Number(r.prepaymentPaymentId ?? 0)).filter((id) => id > 0),
      );
      const newLines: Record<string, unknown>[] = [];
      for (const row of rows) {
        const prepId = Number(row.prepayment_payment_id ?? row.id);
        if (!prepId || usedIds.has(prepId)) continue;
        const unsettled = Number(row.unsettled_amount ?? row.remaining_amount ?? 0);
        if (!(unsettled > 0)) continue;
        usedIds.add(prepId);
        const pullLines = normalizeFormListItems<Record<string, unknown>>(
          formRef.current?.getFieldValue('pull_lines'),
        );
        const pullSum = pullLines.reduce(
          (acc, line) => acc + Number(line.paymentAmount ?? 0),
          0,
        );
        const headerTotal = Number(formRef.current?.getFieldValue('total_amount') ?? 0);
        const targetTotal =
          pullSum > 0 ? pullSum : headerTotal > 0 ? headerTotal : unsettled;
        const offsetAmount = Math.min(unsettled, targetTotal > 0 ? targetTotal : unsettled);
        newLines.push({
          prepaymentPaymentId: prepId,
          sourceCode: String(row.payment_code ?? row.code ?? prepId),
          purchaseOrderCode: row.purchase_order_code ?? '',
          maxUnsettled: unsettled,
          offsetAmount: Number(offsetAmount.toFixed(2)),
        });
      }
      if (!newLines.length) {
        messageApi.warning(t(`${P}.pullLines.noNewLines`));
        return;
      }
      formRef.current?.setFieldsValue({
        offset_prepayment_lines: [...existing, ...newLines],
      });
      syncPaymentHeaderFromOffsetPrepaymentLines(formRef);
      closeModalRef.current?.();
      messageApi.success(t(`${P}.pullLines.offsetPrepaymentMerged`, { count: newLines.length }));
    },
  });
  closeModalRef.current = pullQuery.closeModal;

  const openSelectPrepayment = useCallback(() => {
    if (assertSupplierSelected() == null) return;
    pullQuery.openModal();
  }, [assertSupplierSelected, pullQuery]);

  const renderOffsetPrepaymentHeaderActions = useCallback(
    () => (
      <Button size="small" onClick={openSelectPrepayment}>
        {t(`${P}.pullLines.selectPrepaymentPayment`)}
      </Button>
    ),
    [openSelectPrepayment, t],
  );

  const prepaymentPullColumns = useMemo(() => buildPrepaymentPaymentPullQueryColumns(t), [t]);

  const renderOffsetPullModals = () => (
    <UniPullQueryModal<PrepaymentPaymentPullCandidate>
      open={pullQuery.open}
      title={t(`${P}.pullLines.modalSelectPrepaymentPayment`)}
      onCancel={pullQuery.closeModal}
      onOk={() => void pullQuery.handleConfirm()}
      rowKey="id"
      columns={prepaymentPullColumns}
      dataSource={pullQuery.dataSource}
      loading={pullQuery.loading}
      confirmLoading={pullQuery.confirmLoading}
      selectionType={pullQuery.selectionType}
      selectedRowKeys={pullQuery.selectedRowKeys}
      selectedRows={pullQuery.selectedRows}
      onSelectedRowKeysChange={pullQuery.handleSelectedRowKeysChange}
      isRowDisabled={pullQuery.isRowDisabled}
      searchDraft={pullQuery.searchDraft}
      onSearchDraftChange={pullQuery.setSearchDraft}
      onSearchApply={pullQuery.handleSearchApply}
      onSearchClear={pullQuery.handleSearchClear}
      appliedKeyword={pullQuery.appliedKeyword}
      page={pullQuery.page}
      pageSize={pullQuery.pageSize}
      total={pullQuery.total}
      onPageChange={pullQuery.handlePageChange}
      scopeOptions={pullQuery.scopeOptions}
      scope={pullQuery.scope}
      onScopeChange={pullQuery.handleScopeChange}
      pullQuery={pullQuery.pullQuery}
      searchPlaceholder={t('app.kuaicaiwu.paymentRefund.pullSearchPlaceholder')}
      okText={t('common.confirm')}
    />
  );

  const offsetPrepaymentLineColumns = useMemo(
    () => [
      {
        title: t(`${P}.pullLines.col.prepaymentCode`),
        dataIndex: 'sourceCode',
        width: 140,
        render: (_: unknown, field: FormListFieldData) => (
          <>
            <Form.Item name={[field.name, 'prepaymentPaymentId']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={[field.name, 'sourceCode']} noStyle>
              <Input readOnly variant="borderless" />
            </Form.Item>
          </>
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.orderCode'),
        dataIndex: 'purchaseOrderCode',
        width: 140,
        render: (_: unknown, field: FormListFieldData) => (
          <Form.Item name={[field.name, 'purchaseOrderCode']} noStyle>
            <Input readOnly variant="borderless" />
          </Form.Item>
        ),
      },
      {
        title: t(`${P}.pullLines.col.unsettledBalance`),
        dataIndex: 'maxUnsettled',
        width: 120,
        align: 'right' as const,
        render: (_: unknown, field: FormListFieldData) => (
          <Form.Item name={[field.name, 'maxUnsettled']} noStyle>
            <InputNumber
              readOnly
              variant="borderless"
              precision={2}
              formatter={(v) => formatCurrencyAmount(Number(v ?? 0))}
            />
          </Form.Item>
        ),
      },
      {
        title: t(`${P}.pullLines.col.offsetAmount`),
        dataIndex: 'offsetAmount',
        width: 140,
        align: 'right' as const,
        render: (_: unknown, field: FormListFieldData) => (
          <Form.Item
            name={[field.name, 'offsetAmount']}
            rules={[{ required: true, message: t(`${P}.pullLines.offsetAmountRequired`) }]}
            noStyle
          >
            <InputNumber
              {...financeAmountDigitFieldProps}
              min={0.01}
              style={{ width: '100%' }}
              onChange={() => {
                syncPaymentHeaderFromOffsetPrepaymentLines(formRef);
              }}
            />
          </Form.Item>
        ),
      },
    ] as unknown as ColumnsType<Record<string, unknown>>,
    [t],
  );

  return {
    offsetPrepaymentLineColumns,
    renderOffsetPrepaymentHeaderActions,
    renderOffsetPullModals,
  };
}
