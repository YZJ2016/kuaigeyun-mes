/**
 * 付款申请列表「新建」旁下拉：多来源上拉创建（应付/采购订单/入库/对账单/其他费用支出）
 */
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { App, Select } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import {
  UniPullQueryModal,
  composePullRowDisabled,
  filterByPullScope,
  isPullRowBlockedByPartnerLock,
  paginatePullRows,
  resolvePullQueryAnchorPartnerKey,
  UNI_PULL_QUERY_MAX_FETCH_LIMIT,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import { purchaseOrderCapabilityReasonMessage } from '../../../../../hooks/useDocumentCapabilities';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import {
  KUAIZHIZAO_DOC_HOST,
  loadSupplierFormReferenceList,
} from '../../../../../utils/documentFormReferenceLoad';
import {
  buildKuaizhizaoPullCreateMenuItems,
  resolveKuaizhizaoDocumentAction,
} from '../../../constants/documentActionRegistry';
import { listPurchaseOrders } from '../../../services/purchase';
import { resolvePurchaseReceiptDisplayAmount } from '../shared/purchaseOrderAmounts';
import {
  buildPaymentApplicationPoPullQueryColumns,
  mapPurchaseOrderToPaymentApplicationPullRow,
  type PaymentApplicationPoPullRow,
} from './paymentApplicationPoPullQueryColumns';
import { buildPaymentApplicationSourcePullQueryColumns } from './paymentApplicationSourcePullQueryColumns';
import {
  buildPaymentApplicationPayablePullQueryColumns,
  mapPayablePullLineToPaymentApplicationPayableRow,
  type PaymentApplicationPayablePullRow,
} from './paymentApplicationPayablePullQueryColumns';
import { warehouseApi } from '../../../services/warehouse-execution';
import { partnerStatementService } from '../../../../kuaicaiwu/services/finance/partnerStatement';
import { otherExpenseService, type OtherExpenseVoucher } from '../../../../kuaicaiwu/services/finance/other-expense';
import {
  createPaymentApplication,
  listPayablesForPaymentApplication,
  pullPaymentApplicationFromPurchaseOrders,
  pullPaymentApplicationFromPurchaseReceipts,
  pullPaymentApplicationFromReconciliation,
} from '../../../services/payment-application';

type PullRow = {
  id: number;
  code: string;
  /** 来源单据日期 YYYY-MM-DD */
  documentDate?: string | null;
  supplierId?: number;
  partnerName?: string;
  amount?: number;
  status?: string;
  pullable?: boolean;
  disableReason?: string;
};

function selectedPullRows(keys: React.Key[], rows: PullRow[]): PullRow[] {
  return rows.filter((row) => keys.some((k) => String(k) === String(row.id)));
}

function assertSameSupplierSelected(rows: PullRow[]): boolean {
  const supplierIds = new Set(
    rows.map((r) => Number(r.supplierId ?? 0)).filter((id) => id > 0),
  );
  if (supplierIds.size > 1) return false;
  if (supplierIds.size === 1) return true;
  const names = new Set(
    rows.map((r) => String(r.partnerName ?? '').trim()).filter((n) => n.length > 0),
  );
  return names.size <= 1;
}

type ExpenseWithFinance = OtherExpenseVoucher & {
  payable_id?: number;
  payable_code?: string;
};

type Props = {
  /** 下推建单成功后回调；传入新建付款申请 id 时由列表页跳转编辑 Tab */
  onCreated: (applicationId?: number) => void;
};

function isPurchaseReceiptPosted(status: string): boolean {
  const s = String(status || '').trim();
  const sl = s.toLowerCase();
  return (
    s === '已入库'
    || s === '已完成'
    || s === '已确认'
    || sl === 'completed'
    || sl === 'posted'
  );
}

export function usePaymentApplicationPullMenus({ onCreated }: Props) {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [payablePullSupplierId, setPayablePullSupplierId] = useState<number | null>(null);
  const [payableSupplierOptions, setPayableSupplierOptions] = useState<
    Array<{ id: number; name: string }>
  >([]);
  const [payableSuppliersLoading, setPayableSuppliersLoading] = useState(false);
  const closePoRef = useRef<(() => void) | null>(null);
  const closePayableRef = useRef<(() => void) | null>(null);
  const closeReceiptRef = useRef<(() => void) | null>(null);
  const closeStatementRef = useRef<(() => void) | null>(null);
  const closeExpenseRef = useRef<(() => void) | null>(null);

  const pullFromPoAction = resolveKuaizhizaoDocumentAction(t, 'payment_application.pull_from_purchase_order');
  const pullFromReceiptAction = resolveKuaizhizaoDocumentAction(
    t,
    'payment_application.pull_from_purchase_receipt',
  );
  const pullFromStatementAction = resolveKuaizhizaoDocumentAction(
    t,
    'payment_application.pull_from_partner_statement',
  );
  const pullFromExpenseAction = resolveKuaizhizaoDocumentAction(
    t,
    'payment_application.pull_from_other_expense',
  );
  const pullFromPayableAction = resolveKuaizhizaoDocumentAction(
    t,
    'payment_application.pull_from_payable',
  );

  const scopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const poPullColumns = useMemo(() => buildPaymentApplicationPoPullQueryColumns(t), [t]);

  const columns = useMemo(() => buildPaymentApplicationSourcePullQueryColumns(t), [t]);
  const payablePullColumns = useMemo(() => buildPaymentApplicationPayablePullQueryColumns(t), [t]);

  const isPullable = useCallback((row: PullRow) => row.pullable === true, []);

  const makeSameSupplierPullDisabledHandler = useCallback(
    (selectedRows: PullRow[], baseDisabled: (row: PullRow) => boolean) =>
      (row: PullRow) =>
        composePullRowDisabled(row, { baseDisabled, selectedRows }),
    [],
  );

  const warnPullSourceNotSelectable = useCallback(
    (row: PullRow) => {
      const reason = String(row.disableReason || '').trim();
      if (reason) {
        messageApi.warning(reason);
        return;
      }
      messageApi.warning(t('app.kuaizhizao.paymentApplication.pullSourceNotSelectable'));
    },
    [messageApi, t],
  );

  const makeWarnDisabledRow = useCallback(
    (selectedRows: PullRow[], baseDisabled: (row: PullRow) => boolean) =>
      (row: PullRow) => {
        const anchor = resolvePullQueryAnchorPartnerKey(selectedRows);
        if (
          !baseDisabled(row)
          && anchor
          && isPullRowBlockedByPartnerLock(row, anchor)
        ) {
          messageApi.warning(t('app.kuaicaiwu.payment.sameSupplierRequired'));
          return;
        }
        warnPullSourceNotSelectable(row);
      },
    [messageApi, t, warnPullSourceNotSelectable],
  );

  const basePoRowDisabled = useCallback(
    (row: PaymentApplicationPoPullRow) => !isPullable(row),
    [isPullable],
  );
  const baseReceiptRowDisabled = useCallback((row: PullRow) => !isPullable(row), [isPullable]);

  const ensurePayableSupplierOptions = useCallback(async () => {
    if (payableSupplierOptions.length) {
      return;
    }
    setPayableSuppliersLoading(true);
    try {
      const list = await loadSupplierFormReferenceList(KUAIZHIZAO_DOC_HOST.paymentApplication);
      setPayableSupplierOptions(list.map((s) => ({ id: s.id, name: s.name })));
    } catch (e) {
      messageApi.error(getApiErrorMessage(e, t('common.loadFailed')));
    } finally {
      setPayableSuppliersLoading(false);
    }
  }, [messageApi, payableSupplierOptions.length, t]);

  const pullFromPayableQuery = useUniPullQuery<PaymentApplicationPayablePullRow>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (row) => !isPullable(row),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      if (!payablePullSupplierId) {
        return { data: [], total: 0 };
      }
      try {
        const res = await listPayablesForPaymentApplication(payablePullSupplierId, {
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
    onConfirm: async (keys, rows) => {
      if (!payablePullSupplierId) {
        messageApi.warning(t('app.kuaizhizao.paymentApplication.selectSupplierFirst'));
        return;
      }
      const selectedRows = selectedPullRows(keys, rows);
      if (!selectedRows.length) {
        messageApi.warning(t('common.required'));
        return;
      }
      const supplier = payableSupplierOptions.find((s) => s.id === payablePullSupplierId);
      const items = selectedRows.map((row, index) => ({
        sourceType: 'payable',
        sourceId: row.id,
        sourceCode: row.code,
        payableId: row.id,
        payableCode: row.code,
        lineKind: 'goods',
        requestAmount: Number(row.amount ?? 0),
        lineNo: index + 1,
      }));
      try {
        const created = await createPaymentApplication({
          supplierId: payablePullSupplierId,
          supplierName: supplier?.name,
          items,
        });
        messageApi.success(t('common.createSuccess'));
        closePayableRef.current?.();
        setPayablePullSupplierId(null);
        onCreated(created.id);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('app.kuaizhizao.paymentApplication.createFailed')));
      }
    },
  });
  closePayableRef.current = pullFromPayableQuery.closeModal;

  const openPullFromPayable = useCallback(() => {
    void ensurePayableSupplierOptions().then(() => pullFromPayableQuery.openModal());
  }, [ensurePayableSupplierOptions, pullFromPayableQuery]);

  const pullFromPoQuery = useUniPullQuery<PaymentApplicationPoPullRow>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: basePoRowDisabled,
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const res = await listPurchaseOrders({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
          view: 'options',
          pull_target: 'payment_application',
          ...(scope === 'pullable' ? { pullable_only: true } : {}),
        });
        const items = res.data ?? [];
        const rows = items.map((o) => mapPurchaseOrderToPaymentApplicationPullRow(o, t));
        return paginatePullRows(filterByPullScope(rows, scope, isPullable), page, pageSize);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.loadFailed')));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selectedRows = selectedPullRows(keys, rows);
      if (!selectedRows.length) {
        messageApi.warning(t('common.required'));
        return;
      }
      if (!assertSameSupplierSelected(selectedRows)) {
        messageApi.warning(t('app.kuaicaiwu.payment.sameSupplierRequired'));
        return;
      }
      const orderIds = selectedRows.map((r) => Number(r.id)).filter((id) => id > 0);
      try {
        const app = await pullPaymentApplicationFromPurchaseOrders(orderIds);
        messageApi.success(
          t('app.kuaizhizao.paymentApplication.createFromSourceSuccess', {
            code: app.applicationCode,
            source: pullFromPoAction.sourceLabel,
          }),
        );
        closePoRef.current?.();
        onCreated(Number(app.id));
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('app.kuaizhizao.paymentApplication.createFailed')));
      }
    },
  });
  closePoRef.current = pullFromPoQuery.closeModal;

  const pullFromReceiptQuery = useUniPullQuery<PullRow>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: baseReceiptRowDisabled,
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const res = await warehouseApi.purchaseReceipt.list({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
          receipt_type: 'purchase',
        });
        const items = Array.isArray(res)
          ? res
          : ((res as { data?: unknown[]; items?: unknown[] }).data
            ?? (res as { items?: unknown[] }).items
            ?? []);
        const rows: PullRow[] = (items as Array<Record<string, unknown>>).map((o) => {
          const caps = (o.capabilities || {}) as Record<string, { allowed?: boolean; reason?: string }>;
          const status = String(o.status ?? '');
          const pushCap = caps.push_payment_application;
          const posted = isPurchaseReceiptPosted(status);
          const pullable = posted && pushCap?.allowed === true;
          let disableReason = t('app.kuaizhizao.paymentApplication.pullSourceNotSelectable');
          if (!posted) {
            disableReason = purchaseOrderCapabilityReasonMessage(
              'purchase_receipt.push_payment_application.not_posted',
              t,
            );
          } else if (pushCap?.reason) {
            disableReason = purchaseOrderCapabilityReasonMessage(String(pushCap.reason), t);
          }
          const receiptTime = o.receipt_time ?? o.receiptTime;
          const documentDate = receiptTime ? String(receiptTime).slice(0, 10) : null;
          const supplierIdRaw = o.supplier_id ?? o.supplierId;
          return {
            id: Number(o.id),
            code: String(o.receipt_code ?? o.receiptCode ?? o.id),
            documentDate,
            supplierId: Number(supplierIdRaw ?? 0) || undefined,
            partnerName: String(o.supplier_name ?? o.supplierName ?? ''),
            amount: Number(o.total_amount ?? o.totalAmount ?? 0) || undefined,
            status,
            pullable,
            disableReason,
          };
        });
        return paginatePullRows(filterByPullScope(rows, scope, isPullable), page, pageSize);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.loadFailed')));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selectedRows = selectedPullRows(keys, rows);
      if (!selectedRows.length) {
        messageApi.warning(t('common.required'));
        return;
      }
      if (!assertSameSupplierSelected(selectedRows)) {
        messageApi.warning(t('app.kuaicaiwu.payment.sameSupplierRequired'));
        return;
      }
      const receiptIds = selectedRows.map((r) => Number(r.id)).filter((id) => id > 0);
      try {
        const app = await pullPaymentApplicationFromPurchaseReceipts(receiptIds);
        messageApi.success(
          t('app.kuaizhizao.paymentApplication.createFromReceiptSuccess', {
            code: app.applicationCode,
          }),
        );
        closeReceiptRef.current?.();
        onCreated(Number(app.id));
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('app.kuaizhizao.paymentApplication.createFailed')));
      }
    },
  });
  closeReceiptRef.current = pullFromReceiptQuery.closeModal;

  const pullFromStatementQuery = useUniPullQuery<PullRow>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (row) => !isPullable(row),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const res = await partnerStatementService.list({
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          partner_type: 'Supplier',
          keyword: keyword.trim() || undefined,
        });
        const items = res.items || [];
        const rows: PullRow[] = items.map((s) => {
          const ok = s.status === 'Confirmed' || s.status === 'Sent';
          const documentDate = s.end_date ? String(s.end_date).slice(0, 10) : null;
          return {
            id: s.id,
            code: s.statement_code,
            documentDate,
            partnerName: s.partner_name,
            amount: Number(s.closing_balance ?? s.debit_total ?? 0) || undefined,
            status: s.status,
            pullable: ok,
            disableReason: t('app.kuaizhizao.paymentApplication.pullStatementNotConfirmed'),
          };
        });
        return paginatePullRows(filterByPullScope(rows, scope, isPullable), page, pageSize);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.loadFailed')));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selectedRows = selectedPullRows(keys, rows);
      if (!selectedRows.length) {
        messageApi.warning(t('common.required'));
        return;
      }
      try {
        let lastCode = '';
        let lastId: number | undefined;
        let created = 0;
        for (const selected of selectedRows) {
          const stmt = await partnerStatementService.get(selected.id);
          if (stmt.partner_type !== 'Supplier') {
            messageApi.warning(t('app.kuaicaiwu.partnerStatement.detail.pushSupplierOnly'));
            continue;
          }
          const lines = stmt.transaction_details?.lines || [];
          const payableItems = lines
            .filter(
              (ln) =>
                String(ln.doc_type || '').trim() === '应付单'
                && ln.doc_id != null
                && Number(ln.tree_level ?? 0) === 0
                && Number(ln.statement_amount ?? ln.debit ?? 0) > 0,
            )
            .map((ln) => ({
              doc_type: 'payable',
              doc_id: Number(ln.doc_id),
              amount: Number(
                ln.statement_amount ?? ln.remaining_amount ?? ln.doc_amount ?? ln.debit ?? 0,
              ),
            }))
            .filter((it) => it.amount > 0);
          if (!payableItems.length) {
            messageApi.warning(t('app.kuaicaiwu.partnerStatement.detail.pushSelectPayable'));
            continue;
          }
          const app = await pullPaymentApplicationFromReconciliation({
            supplierId: stmt.partner_id,
            items: payableItems,
          });
          lastCode = app.applicationCode;
          lastId = Number(app.id);
          created += 1;
        }
        if (!created) {
          return;
        }
        messageApi.success(
          t('app.kuaizhizao.paymentApplication.createFromSourceSuccess', {
            code: lastCode,
            source: pullFromStatementAction.sourceLabel,
          }),
        );
        closeStatementRef.current?.();
        onCreated(lastId);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('app.kuaizhizao.paymentApplication.createFailed')));
      }
    },
  });
  closeStatementRef.current = pullFromStatementQuery.closeModal;

  const pullFromExpenseQuery = useUniPullQuery<PullRow>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (row) => !isPullable(row),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const res = await otherExpenseService.list({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
        });
        const items = (res.items || []) as ExpenseWithFinance[];
        const rows: PullRow[] = items
          .filter((e) => String(e.counterparty_kind || '') === 'supplier' && e.counterparty_id)
          .map((e) => ({
            id: e.id,
            code: e.expense_code,
            documentDate: e.business_date ? String(e.business_date).slice(0, 10) : null,
            partnerName: e.counterparty_name,
            amount: Number(e.total_amount || 0) || undefined,
            status: e.status,
            pullable: Number(e.payable_id || 0) > 0,
            disableReason: t('app.kuaizhizao.paymentApplication.otherExpenseNoPayable'),
          }));
        return paginatePullRows(filterByPullScope(rows, scope, isPullable), page, pageSize);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('common.loadFailed')));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selectedRows = selectedPullRows(keys, rows);
      if (!selectedRows.length) {
        messageApi.warning(t('common.required'));
        return;
      }
      try {
        let lastCode = '';
        let lastId: number | undefined;
        let created = 0;
        for (const selected of selectedRows) {
          const detail = (await otherExpenseService.get(selected.id)) as ExpenseWithFinance;
          const payableId = Number(detail.payable_id || 0);
          const supplierId = Number(detail.counterparty_id || 0);
          if (!payableId || !supplierId) {
            messageApi.warning(t('app.kuaizhizao.paymentApplication.otherExpenseNoPayable'));
            continue;
          }
          const payables = await listPayablesForPaymentApplication(supplierId, { limit: 200 });
          const match = (payables.data ?? []).find((row) => Number(row.payable_id) === payableId);
          const amount = Number(match?.max_request_amount ?? detail.total_amount ?? 0);
          if (!(amount > 0)) {
            messageApi.warning(t('app.kuaizhizao.paymentApplication.otherExpenseNoOpenAmount'));
            continue;
          }
          const app = await createPaymentApplication({
            supplierId,
            supplierName: String(detail.counterparty_name ?? selected.partnerName ?? ''),
            items: [
              {
                sourceType: 'other_expense',
                sourceId: selected.id,
                sourceCode: selected.code,
                payableId,
                payableCode: String(detail.payable_code ?? match?.payable_code ?? ''),
                lineKind: 'goods',
                requestAmount: amount,
                lineNo: 1,
              },
            ],
          });
          lastCode = app.applicationCode;
          lastId = Number(app.id);
          created += 1;
        }
        if (!created) {
          return;
        }
        messageApi.success(
          t('app.kuaizhizao.paymentApplication.createFromSourceSuccess', {
            code: lastCode,
            source: pullFromExpenseAction.sourceLabel,
          }),
        );
        closeExpenseRef.current?.();
        onCreated(lastId);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t('app.kuaizhizao.paymentApplication.createFailed')));
      }
    },
  });
  closeExpenseRef.current = pullFromExpenseQuery.closeModal;

  const menuItems = useMemo(
    () =>
      buildKuaizhizaoPullCreateMenuItems(t, [
        {
          key: 'pull-from-payable',
          actionKey: 'payment_application.pull_from_payable',
          onClick: openPullFromPayable,
        },
        {
          key: 'pull-from-po',
          actionKey: 'payment_application.pull_from_purchase_order',
          onClick: pullFromPoQuery.openModal,
        },
        {
          key: 'pull-from-receipt',
          actionKey: 'payment_application.pull_from_purchase_receipt',
          onClick: pullFromReceiptQuery.openModal,
        },
        {
          key: 'pull-from-statement',
          actionKey: 'payment_application.pull_from_partner_statement',
          onClick: pullFromStatementQuery.openModal,
        },
        {
          key: 'pull-from-other-expense',
          actionKey: 'payment_application.pull_from_other_expense',
          onClick: pullFromExpenseQuery.openModal,
        },
      ]),
    [openPullFromPayable, pullFromPoQuery.openModal, pullFromReceiptQuery.openModal, pullFromStatementQuery.openModal, t],
  );

  const payablePullFilterExtra = useMemo(
    () => (
      <Select
        style={{ minWidth: 260 }}
        placeholder={t('app.kuaizhizao.paymentApplication.supplierName')}
        loading={payableSuppliersLoading}
        showSearch
        optionFilterProp="label"
        options={payableSupplierOptions.map((s) => ({ label: s.name, value: s.id }))}
        value={payablePullSupplierId ?? undefined}
        onChange={(v) => {
          setPayablePullSupplierId(Number(v));
          pullFromPayableQuery.reloadCurrent();
        }}
      />
    ),
    [
      payablePullSupplierId,
      payableSupplierOptions,
      payableSuppliersLoading,
      pullFromPayableQuery,
      t,
    ],
  );

  const renderPullModals = () => (
  <>
      <UniPullQueryModal<PaymentApplicationPayablePullRow>
        open={pullFromPayableQuery.open}
        title={pullFromPayableAction.label}
        onCancel={() => {
          pullFromPayableQuery.closeModal();
          setPayablePullSupplierId(null);
        }}
        onOk={() => void pullFromPayableQuery.handleConfirm()}
        rowKey="id"
        columns={payablePullColumns}
        dataSource={pullFromPayableQuery.dataSource}
        loading={pullFromPayableQuery.loading}
        confirmLoading={pullFromPayableQuery.confirmLoading}
        selectionType={pullFromPayableQuery.selectionType}
        selectedRowKeys={pullFromPayableQuery.selectedRowKeys}
        selectedRows={pullFromPayableQuery.selectedRows}
        onSelectedRowKeysChange={pullFromPayableQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromPayableQuery.isRowDisabled}
        onDisabledRowClick={warnPullSourceNotSelectable}
        searchDraft={pullFromPayableQuery.searchDraft}
        onSearchDraftChange={pullFromPayableQuery.setSearchDraft}
        onSearchApply={pullFromPayableQuery.handleSearchApply}
        onSearchClear={pullFromPayableQuery.handleSearchClear}
        appliedKeyword={pullFromPayableQuery.appliedKeyword}
        page={pullFromPayableQuery.page}
        pageSize={pullFromPayableQuery.pageSize}
        total={pullFromPayableQuery.total}
        onPageChange={pullFromPayableQuery.handlePageChange}
        scopeOptions={pullFromPayableQuery.scopeOptions}
        scope={pullFromPayableQuery.scope}
        onScopeChange={pullFromPayableQuery.handleScopeChange}
        filterExtra={payablePullFilterExtra}
        filterExtraPlacement="block"
      />
      <UniPullQueryModal<PaymentApplicationPoPullRow>
        open={pullFromPoQuery.open}
        title={pullFromPoAction.label}
        onCancel={pullFromPoQuery.closeModal}
        onOk={() => void pullFromPoQuery.handleConfirm()}
        rowKey="id"
        columns={poPullColumns}
        dataSource={pullFromPoQuery.dataSource}
        loading={pullFromPoQuery.loading}
        confirmLoading={pullFromPoQuery.confirmLoading}
        selectionType={pullFromPoQuery.selectionType}
        selectedRowKeys={pullFromPoQuery.selectedRowKeys}
        selectedRows={pullFromPoQuery.selectedRows}
        onSelectedRowKeysChange={pullFromPoQuery.handleSelectedRowKeysChange}
        isRowDisabled={makeSameSupplierPullDisabledHandler(
          pullFromPoQuery.selectedRows,
          basePoRowDisabled,
        )}
        onDisabledRowClick={makeWarnDisabledRow(
          pullFromPoQuery.selectedRows,
          basePoRowDisabled,
        )}
        searchDraft={pullFromPoQuery.searchDraft}
        onSearchDraftChange={pullFromPoQuery.setSearchDraft}
        onSearchApply={pullFromPoQuery.handleSearchApply}
        onSearchClear={pullFromPoQuery.handleSearchClear}
        appliedKeyword={pullFromPoQuery.appliedKeyword}
        page={pullFromPoQuery.page}
        pageSize={pullFromPoQuery.pageSize}
        total={pullFromPoQuery.total}
        onPageChange={pullFromPoQuery.handlePageChange}
        scopeOptions={pullFromPoQuery.scopeOptions}
        scope={pullFromPoQuery.scope}
        onScopeChange={pullFromPoQuery.handleScopeChange}
        footerHint={t('app.kuaizhizao.paymentApplication.pullFromPoHint')}
      />
      <UniPullQueryModal<PullRow>
        open={pullFromReceiptQuery.open}
        title={pullFromReceiptAction.label}
        onCancel={pullFromReceiptQuery.closeModal}
        onOk={() => void pullFromReceiptQuery.handleConfirm()}
        rowKey="id"
        columns={columns}
        dataSource={pullFromReceiptQuery.dataSource}
        loading={pullFromReceiptQuery.loading}
        confirmLoading={pullFromReceiptQuery.confirmLoading}
        selectionType={pullFromReceiptQuery.selectionType}
        selectedRowKeys={pullFromReceiptQuery.selectedRowKeys}
        selectedRows={pullFromReceiptQuery.selectedRows}
        onSelectedRowKeysChange={pullFromReceiptQuery.handleSelectedRowKeysChange}
        isRowDisabled={makeSameSupplierPullDisabledHandler(
          pullFromReceiptQuery.selectedRows,
          baseReceiptRowDisabled,
        )}
        onDisabledRowClick={makeWarnDisabledRow(
          pullFromReceiptQuery.selectedRows,
          baseReceiptRowDisabled,
        )}
        searchDraft={pullFromReceiptQuery.searchDraft}
        onSearchDraftChange={pullFromReceiptQuery.setSearchDraft}
        onSearchApply={pullFromReceiptQuery.handleSearchApply}
        onSearchClear={pullFromReceiptQuery.handleSearchClear}
        appliedKeyword={pullFromReceiptQuery.appliedKeyword}
        page={pullFromReceiptQuery.page}
        pageSize={pullFromReceiptQuery.pageSize}
        total={pullFromReceiptQuery.total}
        onPageChange={pullFromReceiptQuery.handlePageChange}
        scopeOptions={pullFromReceiptQuery.scopeOptions}
        scope={pullFromReceiptQuery.scope}
        onScopeChange={pullFromReceiptQuery.handleScopeChange}
      />
      <UniPullQueryModal<PullRow>
        open={pullFromStatementQuery.open}
        title={pullFromStatementAction.label}
        onCancel={pullFromStatementQuery.closeModal}
        onOk={() => void pullFromStatementQuery.handleConfirm()}
        rowKey="id"
        columns={columns}
        dataSource={pullFromStatementQuery.dataSource}
        loading={pullFromStatementQuery.loading}
        confirmLoading={pullFromStatementQuery.confirmLoading}
        selectionType={pullFromStatementQuery.selectionType}
        selectedRowKeys={pullFromStatementQuery.selectedRowKeys}
        selectedRows={pullFromStatementQuery.selectedRows}
        onSelectedRowKeysChange={pullFromStatementQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromStatementQuery.isRowDisabled}
        onDisabledRowClick={warnPullSourceNotSelectable}
        searchDraft={pullFromStatementQuery.searchDraft}
        onSearchDraftChange={pullFromStatementQuery.setSearchDraft}
        onSearchApply={pullFromStatementQuery.handleSearchApply}
        onSearchClear={pullFromStatementQuery.handleSearchClear}
        appliedKeyword={pullFromStatementQuery.appliedKeyword}
        page={pullFromStatementQuery.page}
        pageSize={pullFromStatementQuery.pageSize}
        total={pullFromStatementQuery.total}
        onPageChange={pullFromStatementQuery.handlePageChange}
        scopeOptions={pullFromStatementQuery.scopeOptions}
        scope={pullFromStatementQuery.scope}
        onScopeChange={pullFromStatementQuery.handleScopeChange}
      />
      <UniPullQueryModal<PullRow>
        open={pullFromExpenseQuery.open}
        title={pullFromExpenseAction.label}
        onCancel={pullFromExpenseQuery.closeModal}
        onOk={() => void pullFromExpenseQuery.handleConfirm()}
        rowKey="id"
        columns={columns}
        dataSource={pullFromExpenseQuery.dataSource}
        loading={pullFromExpenseQuery.loading}
        confirmLoading={pullFromExpenseQuery.confirmLoading}
        selectionType={pullFromExpenseQuery.selectionType}
        selectedRowKeys={pullFromExpenseQuery.selectedRowKeys}
        selectedRows={pullFromExpenseQuery.selectedRows}
        onSelectedRowKeysChange={pullFromExpenseQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromExpenseQuery.isRowDisabled}
        onDisabledRowClick={warnPullSourceNotSelectable}
        searchDraft={pullFromExpenseQuery.searchDraft}
        onSearchDraftChange={pullFromExpenseQuery.setSearchDraft}
        onSearchApply={pullFromExpenseQuery.handleSearchApply}
        onSearchClear={pullFromExpenseQuery.handleSearchClear}
        appliedKeyword={pullFromExpenseQuery.appliedKeyword}
        page={pullFromExpenseQuery.page}
        pageSize={pullFromExpenseQuery.pageSize}
        total={pullFromExpenseQuery.total}
        onPageChange={pullFromExpenseQuery.handlePageChange}
        scopeOptions={pullFromExpenseQuery.scopeOptions}
        scope={pullFromExpenseQuery.scope}
        onScopeChange={pullFromExpenseQuery.handleScopeChange}
      />
    </>
  );

  return { menuItems, renderPullModals };
}
