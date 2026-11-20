/**
 * 付款申请 FormModal：按结算类型从应付单 / 采购订单取单合并明细
 */
import React, { useCallback, useMemo, useRef } from 'react';
import type { ProFormInstance } from '@ant-design/pro-components';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  UniPullQueryModal,
  filterByPullScope,
  paginatePullRows,
  UNI_PULL_QUERY_MAX_FETCH_LIMIT,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import { resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import { listPurchaseOrders } from '../../../services/purchase';
import {
  buildPaymentApplicationPoPullQueryColumns,
  mapPurchaseOrderToPaymentApplicationPullRow,
  type PaymentApplicationPoPullRow,
} from './paymentApplicationPoPullQueryColumns';
import {
  buildPaymentApplicationPayablePullQueryColumns,
  mapPayablePullLineToPaymentApplicationPayableRow,
  type PaymentApplicationPayablePullRow,
} from './paymentApplicationPayablePullQueryColumns';
import { listPayablesForPaymentApplication } from '../../../services/payment-application';
import { collectPaymentApplicationItemsFromPurchaseOrderRows } from './paymentApplicationPoPullMerge';

type Props = {
  formRef: React.RefObject<ProFormInstance | undefined>;
  getApplicationKind: () => 'goods' | 'prepayment';
};

export function itemsCompatibleWithApplicationKind(
  items: unknown,
  kind: 'goods' | 'prepayment',
): boolean {
  const rows = normalizeFormListItems<Record<string, unknown>>(items);
  if (!rows.length) return true;
  if (kind === 'prepayment') {
    return rows.every((r) => String(r.lineKind || '').trim() === 'prepayment');
  }
  return rows.every((r) => String(r.lineKind || '').trim() !== 'prepayment');
}

export function usePaymentApplicationFormLinePull({ formRef, getApplicationKind }: Props) {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const closePayableRef = useRef<(() => void) | null>(null);
  const closePoRef = useRef<(() => void) | null>(null);

  const pullFromPayableAction = resolveKuaizhizaoDocumentAction(
    t,
    'payment_application.pull_from_payable',
  );
  const pullFromPoAction = resolveKuaizhizaoDocumentAction(
    t,
    'payment_application.pull_from_purchase_order',
  );

  const scopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const payablePullColumns = useMemo(() => buildPaymentApplicationPayablePullQueryColumns(t), [t]);

  const poPullColumns = useMemo(() => buildPaymentApplicationPoPullQueryColumns(t), [t]);

  const isPullable = useCallback(
    (row: PaymentApplicationPayablePullRow) => row.pullable === true,
    [],
  );

  const warnDisabledRow = useCallback(
    (row: PaymentApplicationPayablePullRow) => {
      const reason = String(row.disableReason || '').trim();
      if (reason) {
        messageApi.warning(reason);
        return;
      }
      messageApi.warning(t('app.kuaizhizao.paymentApplication.pullSourceNotSelectable'));
    },
    [messageApi, t],
  );

  const mergeItems = useCallback(
    (incoming: Record<string, unknown>[]) => {
      const existing = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('items'),
      );
      formRef.current?.setFieldsValue({ items: [...existing, ...incoming] });
    },
    [formRef],
  );

  const pullPayableQuery = useUniPullQuery<PaymentApplicationPayablePullRow>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (row) => !isPullable(row),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      const supplierId = Number(formRef.current?.getFieldValue('supplierId'));
      if (!Number.isFinite(supplierId) || supplierId <= 0) {
        return { data: [], total: 0 };
      }
      try {
        const res = await listPayablesForPaymentApplication(supplierId, {
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
        });
        const disableReason = t('app.kuaizhizao.paymentApplication.pullSourceNotSelectable');
        const rows = (res.data ?? []).map((row) =>
          mapPayablePullLineToPaymentApplicationPayableRow(row, disableReason),
        );
        return paginatePullRows(filterByPullScope(rows, scope, isPullable), page, pageSize);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.loadFailed')));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (_keys, rows) => {
      const existing = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('items'),
      );
      const usedPayableIds = new Set(
        existing.map((r) => Number(r.payableId)).filter((id) => id > 0),
      );
      const newLines: Record<string, unknown>[] = [];
      for (const row of rows) {
        const payableId = Number(row.id);
        if (!payableId || usedPayableIds.has(payableId)) continue;
        usedPayableIds.add(payableId);
        const maxRequest = Number(row.amount ?? 0);
        if (!(maxRequest > 0)) continue;
        newLines.push({
          lineKind: 'goods',
          sourceType: 'payable',
          sourceId: payableId,
          sourceCode: row.code,
          payableId,
          payableCode: row.code,
          requestAmount: maxRequest,
        });
      }
      if (!newLines.length) {
        messageApi.warning(t('app.kuaizhizao.paymentApplication.formPullNoNewLines'));
        return;
      }
      mergeItems(newLines);
      closePayableRef.current?.();
      messageApi.success(
        t('app.kuaizhizao.paymentApplication.formPullMerged', { count: newLines.length }),
      );
    },
  });
  closePayableRef.current = pullPayableQuery.closeModal;

  const pullPoQuery = useUniPullQuery<PaymentApplicationPoPullRow>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (row) => !isPullable(row),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      const supplierId = Number(formRef.current?.getFieldValue('supplierId'));
      if (!Number.isFinite(supplierId) || supplierId <= 0) {
        return { data: [], total: 0 };
      }
      try {
        const res = await listPurchaseOrders({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
          supplier_id: supplierId,
        });
        const items = res.data ?? [];
        const rows = items
          .filter((o) => Number(o.supplier_id) === supplierId)
          .map((o) => mapPurchaseOrderToPaymentApplicationPullRow(o, t));
        return paginatePullRows(filterByPullScope(rows, scope, isPullable), page, pageSize);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.loadFailed')));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (_keys, rows) => {
      const existing = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('items'),
      );
      const usedPoIds = new Set(
        existing
          .filter((r) => String(r.sourceType || '').trim() === 'purchase_order')
          .map((r) => Number(r.sourceId))
          .filter((id) => id > 0),
      );
      const { newLines, skipped } = await collectPaymentApplicationItemsFromPurchaseOrderRows(
        rows,
        usedPoIds,
      );
      if (!newLines.length) {
        messageApi.warning(
          skipped > 0
            ? t('app.kuaizhizao.paymentApplication.formPullPoAllSkipped')
            : t('app.kuaizhizao.paymentApplication.formPullNoNewLines'),
        );
        return;
      }
      mergeItems(newLines);
      closePoRef.current?.();
      if (skipped > 0) {
        messageApi.warning(t('app.kuaizhizao.paymentApplication.formPullPoPartialSkip', { count: skipped }));
      }
      messageApi.success(
        t('app.kuaizhizao.paymentApplication.formPullMerged', { count: newLines.length }),
      );
    },
  });
  closePoRef.current = pullPoQuery.closeModal;

  const openAddDetailPull = useCallback(() => {
    const supplierId = Number(formRef.current?.getFieldValue('supplierId'));
    if (!Number.isFinite(supplierId) || supplierId <= 0) {
      messageApi.warning(t('app.kuaizhizao.paymentApplication.selectSupplierFirst'));
      return;
    }
    const kind = getApplicationKind();
    if (kind === 'prepayment') {
      pullPoQuery.openModal();
    } else {
      pullPayableQuery.openModal();
    }
  }, [formRef, getApplicationKind, messageApi, pullPayableQuery, pullPoQuery, t]);

  const renderPullModals = () => (
    <>
      <UniPullQueryModal<PaymentApplicationPayablePullRow>
        open={pullPayableQuery.open}
        title={pullFromPayableAction.label}
        onCancel={pullPayableQuery.closeModal}
        onOk={() => void pullPayableQuery.handleConfirm()}
        rowKey="id"
        columns={payablePullColumns}
        dataSource={pullPayableQuery.dataSource}
        loading={pullPayableQuery.loading}
        confirmLoading={pullPayableQuery.confirmLoading}
        selectionType={pullPayableQuery.selectionType}
        selectedRowKeys={pullPayableQuery.selectedRowKeys}
        selectedRows={pullPayableQuery.selectedRows}
        onSelectedRowKeysChange={pullPayableQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullPayableQuery.isRowDisabled}
        onDisabledRowClick={warnDisabledRow}
        searchDraft={pullPayableQuery.searchDraft}
        onSearchDraftChange={pullPayableQuery.setSearchDraft}
        onSearchApply={pullPayableQuery.handleSearchApply}
        onSearchClear={pullPayableQuery.handleSearchClear}
        appliedKeyword={pullPayableQuery.appliedKeyword}
        page={pullPayableQuery.page}
        pageSize={pullPayableQuery.pageSize}
        total={pullPayableQuery.total}
        onPageChange={pullPayableQuery.handlePageChange}
        scopeOptions={pullPayableQuery.scopeOptions}
        scope={pullPayableQuery.scope}
        onScopeChange={pullPayableQuery.handleScopeChange}
      />
      <UniPullQueryModal<PaymentApplicationPoPullRow>
        open={pullPoQuery.open}
        title={pullFromPoAction.label}
        onCancel={pullPoQuery.closeModal}
        onOk={() => void pullPoQuery.handleConfirm()}
        rowKey="id"
        columns={poPullColumns}
        dataSource={pullPoQuery.dataSource}
        loading={pullPoQuery.loading}
        confirmLoading={pullPoQuery.confirmLoading}
        selectionType={pullPoQuery.selectionType}
        selectedRowKeys={pullPoQuery.selectedRowKeys}
        selectedRows={pullPoQuery.selectedRows}
        onSelectedRowKeysChange={pullPoQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullPoQuery.isRowDisabled}
        onDisabledRowClick={warnDisabledRow}
        searchDraft={pullPoQuery.searchDraft}
        onSearchDraftChange={pullPoQuery.setSearchDraft}
        onSearchApply={pullPoQuery.handleSearchApply}
        onSearchClear={pullPoQuery.handleSearchClear}
        appliedKeyword={pullPoQuery.appliedKeyword}
        page={pullPoQuery.page}
        pageSize={pullPoQuery.pageSize}
        total={pullPoQuery.total}
        onPageChange={pullPoQuery.handlePageChange}
        scopeOptions={pullPoQuery.scopeOptions}
        scope={pullPoQuery.scope}
        onScopeChange={pullPoQuery.handleScopeChange}
        footerHint={t('app.kuaizhizao.paymentApplication.pullFromPoHint')}
      />
    </>
  );

  return { openAddDetailPull, renderPullModals };
}
