/**
 * 付款单 FormModal：取应付 / 取付款申请合并明细
 */
import React, { useCallback, useMemo, useRef } from 'react';
import type { ProFormInstance } from '@ant-design/pro-components';
import { App, Button, Form, Input, InputNumber, Space } from 'antd';
import type { FormListFieldData } from 'antd/es/form';
import { useTranslation } from 'react-i18next';
import {
  UniPullQueryModal,
  filterByPullScope,
  paginatePullRows,
  renderPullQueryDocStatus,
  UNI_PULL_QUERY_MAX_FETCH_LIMIT,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import { formatCurrencyAmount } from '../../../../../utils/format';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import { getKuaicaiwuDocumentAction } from '../../../constants/documentActionRegistry';
import { paymentService, type PaymentPullCandidate } from '../../../services/finance/payment';
import { loadFinancePullCandidatePage } from './loadFinancePullCandidatePage';
import { financeAmountDigitFieldProps } from '../../../utils/financeFormLayout';
import { allocateAmountByWeights, roundBusinessAmount } from '../../../../kuaizhizao/utils/documentLineAmounts';
import { buildPaymentPayablePullQueryColumns } from './paymentPayablePullQueryColumns';
import { purchaseOrderCapabilityReasonMessage } from '../../../../../hooks/useDocumentCapabilities';
import { isPrepaymentOffsetPaymentMethod } from '../../../utils/financeSharedOptions';
import { formatBusinessDateOnly } from '../../../../../utils/format';
import { listPurchaseOrders } from '../../../../kuaizhizao/services/purchase';
import { resolvePurchaseOrderDisplayAmount } from '../../../../kuaizhizao/pages/purchase-management/shared/purchaseOrderAmounts';

const P = 'app.kuaicaiwu.payment';

type Props = {
  formRef: React.RefObject<ProFormInstance | undefined>;
};

export function pullLinesCompatibleWithSettlementType(
  items: unknown,
  settlementType: string,
): boolean {
  const rows = normalizeFormListItems<Record<string, unknown>>(items);
  if (!rows.length) return true;
  const st = String(settlementType || 'normal').trim() || 'normal';
  if (st === 'prepayment') {
    return rows.every((r) => {
      const src = String(r.sourceType || '').trim();
      return src === 'payment_application' || src === 'purchase_order';
    });
  }
  return rows.every((r) => {
    const src = String(r.sourceType || '').trim();
    return src === 'payable' || src === 'payment_application';
  });
}

export function syncPaymentTotalFromPullLines(formRef: React.RefObject<ProFormInstance | undefined>) {
  const lines = normalizeFormListItems<Record<string, unknown>>(
    formRef.current?.getFieldValue('pull_lines'),
  );
  const sum = lines.reduce((acc, row) => acc + Number(row.paymentAmount ?? 0), 0);
  if (sum > 0) {
    formRef.current?.setFieldsValue({ total_amount: sum });
  }
}

/** 预付抵扣：表头「本次抵扣金额」与预付款明细抵扣合计对齐。 */
export function syncPaymentHeaderFromOffsetPrepaymentLines(
  formRef: React.RefObject<ProFormInstance | undefined>,
) {
  const offsetRows = normalizeFormListItems<Record<string, unknown>>(
    formRef.current?.getFieldValue('offset_prepayment_lines'),
  );
  if (!offsetRows.length) {
    return;
  }
  const sum = offsetRows.reduce((acc, row) => acc + Number(row.offsetAmount ?? 0), 0);
  if (sum > 0) {
    formRef.current?.setFieldsValue({ total_amount: roundBusinessAmount(sum) });
  }
}

/** 手工改表头后：预付款行「本次抵扣金额」按表头分摊（受未核销余额上限约束）。 */
export function syncOffsetPrepaymentLinesToHeaderTotal(
  formRef: React.RefObject<ProFormInstance | undefined>,
) {
  const total = Number(formRef.current?.getFieldValue('total_amount') ?? 0);
  if (!(total > 0)) {
    return;
  }
  const offsetRows = normalizeFormListItems<Record<string, unknown>>(
    formRef.current?.getFieldValue('offset_prepayment_lines'),
  );
  if (!offsetRows.length) {
    return;
  }
  let budget = total;
  const nextRows = offsetRows.map((row, index) => {
    const cap = Number(row.maxUnsettled ?? row.offsetAmount ?? 0);
    const isLast = index === offsetRows.length - 1;
    let part: number;
    if (isLast) {
      part = budget;
    } else if (cap > 0) {
      part = Math.min(budget, cap);
    } else {
      part = 0;
    }
    if (cap > 0 && part > cap) {
      part = cap;
    }
    if (part < 0) {
      part = 0;
    }
    budget -= part;
    return { ...row, offsetAmount: roundBusinessAmount(part) };
  });
  formRef.current?.setFieldsValue({ offset_prepayment_lines: nextRows });
}

export function applyPaymentHeaderAmountToPullLines(
  headerAmount: number,
  rows: Record<string, unknown>[],
): Record<string, unknown>[] {
  if (!rows.length) {
    return rows;
  }
  if (rows.length === 1) {
    return [{ ...rows[0], paymentAmount: headerAmount }];
  }
  const weights = rows.map((row) => {
    const w = Number(row.maxAmount ?? row.paymentAmount ?? 0);
    return w > 0 ? w : 1;
  });
  const parts = allocateAmountByWeights(headerAmount, weights);
  return rows.map((row, index) => {
    const cap = Number(row.maxAmount ?? 0);
    let part = parts[index] ?? 0;
    if (cap > 0 && part > cap) {
      part = cap;
    }
    return { ...row, paymentAmount: part };
  });
}

export function handlePaymentVoucherFormValuesChange(
  formRef: React.RefObject<ProFormInstance | undefined>,
  changedValues: Record<string, unknown>,
  allValues: Record<string, unknown>,
) {
  const offsetMode = isPrepaymentOffsetPaymentMethod(String(allValues.payment_method || ''));
  if (Object.prototype.hasOwnProperty.call(changedValues, 'pull_lines')) {
    syncPaymentTotalFromPullLines(formRef);
    if (offsetMode) {
      syncOffsetPrepaymentLinesToHeaderTotal(formRef);
    }
    return;
  }
  if (Object.prototype.hasOwnProperty.call(changedValues, 'offset_prepayment_lines')) {
    if (offsetMode) {
      syncPaymentHeaderFromOffsetPrepaymentLines(formRef);
    }
    return;
  }
  if (!Object.prototype.hasOwnProperty.call(changedValues, 'total_amount')) {
    return;
  }
  if (offsetMode) {
    const nextAmount = Number(changedValues.total_amount);
    if (!Number.isFinite(nextAmount)) {
      return;
    }
    const pullRows = normalizeFormListItems<Record<string, unknown>>(allValues.pull_lines);
    if (pullRows.length) {
      formRef.current?.setFieldsValue({
        pull_lines: applyPaymentHeaderAmountToPullLines(nextAmount, pullRows),
      });
    }
    syncOffsetPrepaymentLinesToHeaderTotal(formRef);
    return;
  }
  const rows = normalizeFormListItems<Record<string, unknown>>(allValues.pull_lines);
  if (!rows.length) {
    return;
  }
  const nextAmount = Number(changedValues.total_amount);
  if (!Number.isFinite(nextAmount)) {
    return;
  }
  formRef.current?.setFieldsValue({
    pull_lines: applyPaymentHeaderAmountToPullLines(nextAmount, rows),
  });
}

export function readPaymentPullLineFormFields(row: Record<string, unknown>) {
  const paymentAmount = Number(row.paymentAmount ?? row.amount ?? 0);
  return {
    sourceType: String(row.sourceType ?? row.source_type ?? '').trim(),
    sourceId: Number(row.sourceId ?? row.source_id ?? 0),
    sourceCode: String(row.sourceCode ?? row.source_code ?? '').trim(),
    paymentAmount: Number.isFinite(paymentAmount) ? paymentAmount : 0,
  };
}

export function filterValidPaymentPullFormLines(items: unknown): Record<string, unknown>[] {
  return normalizeFormListItems<Record<string, unknown>>(items).filter((row) => {
    const f = readPaymentPullLineFormFields(row);
    return f.sourceType.length > 0 && f.sourceId > 0 && f.paymentAmount > 0;
  });
}

export function mapFormPullLinesToApi(items: unknown):
  | Array<{
      source_type: string;
      source_id: number;
      source_code?: string;
      amount: number;
    }>
  | undefined {
  const rows = normalizeFormListItems<Record<string, unknown>>(items);
  if (!rows.length) return undefined;
  return rows.map((row) => ({
    source_type: String(row.sourceType || '').trim(),
    source_id: Number(row.sourceId),
    source_code: String(row.sourceCode || '').trim() || undefined,
    amount: Number(row.paymentAmount ?? 0),
  }));
}

export function requirePaymentPullLinesForNormalSettlement(
  settlementType: unknown,
  items: unknown,
  totalAmount: number,
  t: (key: string, opts?: Record<string, unknown>) => string,
  paymentMethod?: unknown,
): string | null {
  const st = String(settlementType || 'normal').trim() || 'normal';
  if (st === 'refund') {
    return null;
  }
  if (isPrepaymentOffsetPaymentMethod(String(paymentMethod || ''))) {
    const rows = normalizeFormListItems<Record<string, unknown>>(items);
    if (!rows.length) {
      return t(`${P}.pullLines.requiredForPrepaymentOffset`);
    }
    return validatePaymentPullLinesBeforeSubmit(items, totalAmount, t);
  }
  if (st === 'prepayment') {
    return null;
  }
  const rows = normalizeFormListItems<Record<string, unknown>>(items);
  if (!rows.length) {
    return t(`${P}.pullLines.requiredForNormalSettlement`);
  }
  return validatePaymentPullLinesBeforeSubmit(items, totalAmount, t);
}

export function validatePaymentPullLinesBeforeSubmit(
  items: unknown,
  totalAmount: number,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string | null {
  const rows = normalizeFormListItems<Record<string, unknown>>(items);
  if (!rows.length) return null;
  const types = new Set(rows.map((r) => String(r.sourceType || '').trim()).filter(Boolean));
  if (types.size > 1) {
    return t(`${P}.pullLines.mixedSourceForbidden`);
  }
  const sum = rows.reduce((acc, row) => acc + Number(row.paymentAmount ?? 0), 0);
  if (Math.abs(sum - Number(totalAmount || 0)) > 0.009) {
    return t(`${P}.pullLines.totalMustMatchLines`);
  }
  for (const row of rows) {
    const maxAmt = Number(row.maxAmount ?? 0);
    const payAmt = Number(row.paymentAmount ?? 0);
    if (maxAmt > 0 && payAmt > maxAmt + 0.009) {
      return t(`${P}.pullLines.exceedsMax`);
    }
    if (!(payAmt > 0)) {
      return t(`${P}.amountMustPositive`);
    }
  }
  return null;
}

function sourceTypeLabel(t: (key: string) => string, sourceType: unknown): string {
  const st = String(sourceType || '').trim();
  if (st === 'payment_application') {
    return t(`${P}.pullLines.sourcePaymentApplication`);
  }
  if (st === 'purchase_order') {
    return t(`${P}.pullLines.sourcePurchaseOrder`);
  }
  if (st === 'payable') {
    return t(`${P}.pullLines.sourcePayable`);
  }
  return st || '—';
}

type PoPullRow = {
  id: number;
  code: string;
  documentDate?: string | null;
  partnerName?: string;
  amount?: number;
  status?: string;
  pullable?: boolean;
  disableReason?: string;
};

function mapPoPreviewLineToPaymentPullRow(
  poId: number,
  poCode: string,
  line: Record<string, unknown>,
): Record<string, unknown> {
  const payAmt = Number(line.requestAmount ?? line.request_amount ?? 0);
  return {
    lineKind: 'prepayment',
    sourceType: 'purchase_order',
    sourceId: poId,
    sourceCode: String(line.sourceCode ?? line.source_code ?? poCode),
    maxAmount: payAmt,
    paymentAmount: payAmt,
    materialName: line.materialName ?? line.material_name,
    materialSpec: line.materialSpec ?? line.material_spec,
    quantity: line.quantity != null && line.quantity !== '' ? Number(line.quantity) : undefined,
    materialUnit: line.materialUnit ?? line.material_unit,
    sourceLineId:
      line.sourceLineId != null || line.source_line_id != null
        ? Number(line.sourceLineId ?? line.source_line_id)
        : undefined,
  };
}

export function usePaymentVoucherFormLinePull({ formRef }: Props) {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const closePayableRef = useRef<(() => void) | null>(null);
  const closeAppRef = useRef<(() => void) | null>(null);
  const closePoRef = useRef<(() => void) | null>(null);

  const pullFromPayableAction = getKuaicaiwuDocumentAction('payment.pull_from_payable');
  const pullFromAppAction = getKuaicaiwuDocumentAction('payment.pull_from_payment_application');
  const pullFromPoAction = getKuaicaiwuDocumentAction('payment.pull_from_purchase_order');

  const scopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const pullColumns = useMemo(() => buildPaymentPayablePullQueryColumns(t), [t]);

  const appColumns = useMemo(
    () => [
      { title: t('common.code'), dataIndex: 'code', width: 220, ellipsis: true },
      {
        title: t('app.kuaicaiwu.common.supplier'),
        dataIndex: 'supplier_name',
        width: 180,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.paymentApplication.remainingAmount'),
        dataIndex: 'remaining_amount',
        width: 120,
        align: 'right' as const,
        render: (v: unknown) => formatCurrencyAmount(v ?? 0),
      },
    ],
    [t],
  );

  const mergePullLines = useCallback(
    (incoming: Record<string, unknown>[], replace: boolean) => {
      const existing = replace
        ? []
        : normalizeFormListItems<Record<string, unknown>>(
            formRef.current?.getFieldValue('pull_lines'),
          );
      formRef.current?.setFieldsValue({ pull_lines: [...existing, ...incoming] });
      syncPaymentTotalFromPullLines(formRef);
    },
    [formRef],
  );

  const assertSupplierSelected = useCallback(() => {
    const supplierId = Number(formRef.current?.getFieldValue('supplier_id'));
    if (!Number.isFinite(supplierId) || supplierId <= 0) {
      messageApi.warning(t(`${P}.pullLines.selectSupplierFirst`));
      return null;
    }
    return supplierId;
  }, [formRef, messageApi, t]);

  const assertNoMixedSource = useCallback(
    (nextType: 'payable' | 'payment_application' | 'purchase_order') => {
      const existing = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('pull_lines'),
      );
      if (!existing.length) return true;
      const currentType = String(existing[0]?.sourceType || '').trim();
      if (currentType && currentType !== nextType) {
        messageApi.warning(t(`${P}.pullLines.mixedSourceForbidden`));
        return false;
      }
      if (nextType === 'payment_application' && existing.length > 0) {
        messageApi.warning(t(`${P}.pullLines.singleApplicationOnly`));
        return false;
      }
      return true;
    },
    [formRef, messageApi, t],
  );

  const isPullPaymentSelectable = useCallback(
    (record: PaymentPullCandidate) => record.capabilities?.pull_payment?.allowed !== false,
    [],
  );

  const pullPayableQuery = useUniPullQuery<PaymentPullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => record.capabilities?.pull_payment?.allowed === false,
    loadData: async (params) => {
      const supplierId = assertSupplierSelected();
      if (supplierId == null) return { data: [], total: 0 };
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          (row) => row.capabilities?.pull_payment?.allowed !== false,
          (api) => paymentService.listPayablePullCandidates(api),
          { supplierId },
        );
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const settlementType = String(formRef.current?.getFieldValue('settlement_type') || 'normal');
      if (settlementType === 'prepayment') {
        messageApi.warning(t(`${P}.pullLines.prepaymentNoPayable`));
        return;
      }
      if (!assertNoMixedSource('payable')) return;

      const selectedRows = rows.filter((row) =>
        keys.some((k) => String(k) === String(row.id)),
      );
      const selectedIds = selectedRows.map((r) => Number(r.id)).filter((id) => id > 0);
      if (!selectedIds.length) {
        messageApi.warning(t(`${P}.selectSource`, { label: pullFromPayableAction.sourceLabel }));
        return;
      }
      const supplierIds = new Set(
        selectedRows.map((r) => Number(r.supplier_id ?? 0)).filter((id) => id > 0),
      );
      if (supplierIds.size > 1) {
        messageApi.warning(t(`${P}.sameSupplierRequired`));
        return;
      }

      try {
        const preview =
          selectedIds.length === 1
            ? await paymentService.previewPullFromPayable(selectedIds[0])
            : await paymentService.previewPullFromPayables(selectedIds);
        if (preview.has_blocking_issues) {
          messageApi.warning(t(`${P}.loadSourceFailed`));
          return;
        }
        const existing = normalizeFormListItems<Record<string, unknown>>(
          formRef.current?.getFieldValue('pull_lines'),
        );
        const usedIds = new Set(
          existing.map((r) => Number(r.sourceId)).filter((id) => id > 0),
        );
        const newLines: Record<string, unknown>[] = [];
        for (const item of preview.items ?? []) {
          const sourceId = Number(item.item_id ?? item.payable_id ?? 0);
          if (!sourceId || usedIds.has(sourceId)) continue;
          const maxAmount = Number(item.max_push_quantity ?? 0);
          if (!(maxAmount > 0)) continue;
          usedIds.add(sourceId);
          newLines.push({
            sourceType: 'payable',
            sourceId,
            sourceCode: String(item.source_code ?? sourceId),
            maxAmount,
            paymentAmount: maxAmount,
          });
        }
        if (!newLines.length) {
          messageApi.warning(t(`${P}.pullLines.noNewLines`));
          return;
        }
        mergePullLines(newLines, false);
        closePayableRef.current?.();
        messageApi.success(t(`${P}.pullLines.merged`, { count: newLines.length }));
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
      }
    },
  });
  closePayableRef.current = pullPayableQuery.closeModal;

  const pullAppQuery = useUniPullQuery<PaymentPullCandidate>({
    rowKey: 'id',
    selectionType: 'radio',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => !isPullPaymentSelectable(record),
    loadData: async (params) => {
      const supplierId = assertSupplierSelected();
      if (supplierId == null) return { data: [], total: 0 };
      const settlementType =
        String(formRef.current?.getFieldValue('settlement_type') || 'normal').trim() || 'normal';
      const paymentMethod = String(formRef.current?.getFieldValue('payment_method') || '');
      let applicationKind = settlementType === 'prepayment' ? 'prepayment' : 'goods';
      if (isPrepaymentOffsetPaymentMethod(paymentMethod)) {
        applicationKind = 'goods';
      }
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          isPullPaymentSelectable,
          (api) =>
            paymentService.listPaymentApplicationPullCandidates({
              ...api,
              application_kind: applicationKind,
            }),
          { supplierId },
        );
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      if (!assertNoMixedSource('payment_application')) return;
      const selected = rows.find((x) => String(x.id) === String(keys[0]));
      if (!selected?.id) {
        messageApi.warning(t(`${P}.selectSource`, { label: pullFromAppAction.sourceLabel }));
        return;
      }
      try {
        const preview = await paymentService.previewPullFromPaymentApplication(selected.id);
        if (preview.has_blocking_issues) {
          messageApi.warning(t(`${P}.loadSourceFailed`));
          return;
        }
        const maxAmount = Number(
          preview.max_push_total ??
            (preview.items ?? []).reduce(
              (sum, row) => sum + Number(row.max_push_quantity ?? 0),
              0,
            ),
        );
        if (!(maxAmount > 0)) {
          messageApi.warning(t(`${P}.pullLines.noNewLines`));
          return;
        }
        mergePullLines(
          [
            {
              sourceType: 'payment_application',
              sourceId: selected.id,
              sourceCode: String(preview.source_code ?? selected.id),
              maxAmount,
              paymentAmount: maxAmount,
            },
          ],
          true,
        );
        formRef.current?.setFieldsValue({
          counterparty_account_name: preview.counterparty_account_name ?? undefined,
          counterparty_bank_name: preview.counterparty_bank_name ?? undefined,
          counterparty_bank_account: preview.counterparty_bank_account ?? undefined,
          payment_method: preview.payment_method ?? formRef.current?.getFieldValue('payment_method'),
          advance_payee_id: preview.advance_payee_id ?? undefined,
          advance_payee_name: preview.advance_payee_name ?? undefined,
        });
        closeAppRef.current?.();
        messageApi.success(t(`${P}.pullLines.applicationMerged`));
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
      }
    },
  });
  closeAppRef.current = pullAppQuery.closeModal;

  const poPullColumns = useMemo(
    () => [
      { title: t('common.code'), dataIndex: 'code', width: 160, ellipsis: true },
      {
        title: t('components.uniPullQuery.documentDateColumn'),
        dataIndex: 'documentDate',
        width: 112,
        render: (v?: string | null) => (v ? formatBusinessDateOnly(String(v)) : '—'),
      },
      { title: t('app.kuaicaiwu.common.supplier'), dataIndex: 'partnerName', ellipsis: true },
      {
        title: t(`${P}.pullLines.col.maxAmount`),
        dataIndex: 'amount',
        width: 120,
        align: 'right' as const,
        render: (v?: number) => (v != null && v > 0 ? formatCurrencyAmount(v) : '—'),
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 100,
        render: (v: unknown) => renderPullQueryDocStatus(t, v),
      },
    ],
    [t],
  );

  const isPoPullable = useCallback((row: PoPullRow) => row.pullable === true, []);

  const pullPoQuery = useUniPullQuery<PoPullRow>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (row) => !isPoPullable(row),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      const supplierId = assertSupplierSelected();
      if (supplierId == null) return { data: [], total: 0 };
      try {
        const res = await listPurchaseOrders({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
          supplier_id: supplierId,
        });
        const items = res.data ?? [];
        const rows: PoPullRow[] = items
          .filter((o) => Number(o.supplier_id) === supplierId)
          .map((o) => {
            const cap = o.capabilities?.push_payment_application;
            const prepay = Number(o.prepayment_amount ?? 0);
            const orderTotal = resolvePurchaseOrderDisplayAmount(o);
            const displayAmount = prepay > 0 ? prepay : orderTotal;
            const orderDate = o.order_date ? String(o.order_date).slice(0, 10) : null;
            const reasonCode = cap?.reason ? String(cap.reason) : '';
            return {
              id: Number(o.id),
              code: String(o.order_code ?? o.id),
              documentDate: orderDate,
              partnerName: String(o.supplier_name ?? ''),
              amount: displayAmount > 0 ? displayAmount : undefined,
              status: String(o.status ?? o.review_status ?? ''),
              pullable: cap?.allowed === true,
              disableReason: reasonCode
                ? purchaseOrderCapabilityReasonMessage(reasonCode, t)
                : t(`${P}.pullLines.poNotSelectable`),
            };
          });
        return paginatePullRows(filterByPullScope(rows, scope, isPoPullable), page, pageSize);
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (_keys, rows) => {
      if (!assertNoMixedSource('purchase_order')) return;
      const existing = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('pull_lines'),
      );
      const usedPoIds = new Set(
        existing
          .filter((r) => String(r.sourceType || '').trim() === 'purchase_order')
          .map((r) => Number(r.sourceId))
          .filter((id) => id > 0),
      );
      const newLines: Record<string, unknown>[] = [];
      let skipped = 0;
      for (const row of rows) {
        const poId = Number(row.id);
        if (!poId || usedPoIds.has(poId)) continue;
        try {
          const preview = await paymentService.previewPullFromPurchaseOrder(poId);
          if (preview.has_blocking_issues) {
            skipped += 1;
            continue;
          }
          const items = (preview.items as Record<string, unknown>[] | undefined) ?? [];
          if (!items.length) {
            skipped += 1;
            continue;
          }
          const poCode = String(preview.source_code ?? row.code ?? poId);
          usedPoIds.add(poId);
          for (const ln of items) {
            newLines.push(mapPoPreviewLineToPaymentPullRow(poId, poCode, ln));
          }
        } catch {
          skipped += 1;
        }
      }
      if (!newLines.length) {
        messageApi.warning(
          skipped > 0 ? t(`${P}.pullLines.poAllSkipped`) : t(`${P}.pullLines.noNewLines`),
        );
        return;
      }
      mergePullLines(newLines, false);
      closePoRef.current?.();
      if (skipped > 0) {
        messageApi.warning(t(`${P}.pullLines.poPartialSkip`, { count: skipped }));
      }
      messageApi.success(t(`${P}.pullLines.merged`, { count: newLines.length }));
    },
  });
  closePoRef.current = pullPoQuery.closeModal;

  const openPullPayable = useCallback(() => {
    if (assertSupplierSelected() == null) return;
    pullPayableQuery.openModal();
  }, [assertSupplierSelected, pullPayableQuery]);

  const openPullApplication = useCallback(() => {
    if (assertSupplierSelected() == null) return;
    pullAppQuery.openModal();
  }, [assertSupplierSelected, pullAppQuery]);

  const openPullPurchaseOrder = useCallback(() => {
    if (assertSupplierSelected() == null) return;
    pullPoQuery.openModal();
  }, [assertSupplierSelected, pullPoQuery]);

  const renderPullLineHeaderActions = useCallback(
    () => (
      <Form.Item
        noStyle
        shouldUpdate={(prev, cur) =>
          prev.settlement_type !== cur.settlement_type || prev.payment_method !== cur.payment_method
        }
      >
        {({ getFieldValue }) => {
          const settlementType = String(getFieldValue('settlement_type') || 'normal').trim() || 'normal';
          const paymentMethod = String(getFieldValue('payment_method') || '');
          const isOffset = isPrepaymentOffsetPaymentMethod(paymentMethod);
          const showPayablePull = settlementType === 'normal';
          const showPoPrepayPull = settlementType === 'prepayment' && !isOffset;
          const showAppPull = settlementType === 'normal';
          const payableBtnLabel = isOffset
            ? t(`${P}.pullLines.offsetLoadFromPayable`)
            : t(`${P}.pullLines.loadFromPayable`);
          const appBtnLabel = isOffset
            ? t(`${P}.pullLines.offsetLoadFromApplication`)
            : t(`${P}.pullLines.loadFromApplication`);
          return (
            <Space size={8} wrap>
              {showPayablePull ? (
                <Button size="small" onClick={openPullPayable}>
                  {payableBtnLabel}
                </Button>
              ) : null}
              {showPoPrepayPull ? (
                <Button size="small" onClick={openPullPurchaseOrder}>
                  {pullFromPoAction.label}
                </Button>
              ) : null}
              {showAppPull ? (
                <Button size="small" onClick={openPullApplication}>
                  {appBtnLabel}
                </Button>
              ) : null}
            </Space>
          );
        }}
      </Form.Item>
    ),
    [
      openPullApplication,
      openPullPayable,
      openPullPurchaseOrder,
      pullFromPoAction.label,
      t,
    ],
  );

  const renderPullModals = () => (
    <>
      <UniPullQueryModal<PaymentPullCandidate>
        open={pullPayableQuery.open}
        title={t(`${P}.pullLines.modalSelectPayable`)}
        onCancel={pullPayableQuery.closeModal}
        onOk={() => void pullPayableQuery.handleConfirm()}
        rowKey="id"
        columns={pullColumns}
        dataSource={pullPayableQuery.dataSource}
        loading={pullPayableQuery.loading}
        confirmLoading={pullPayableQuery.confirmLoading}
        selectionType={pullPayableQuery.selectionType}
        selectedRowKeys={pullPayableQuery.selectedRowKeys}
        selectedRows={pullPayableQuery.selectedRows}
        onSelectedRowKeysChange={pullPayableQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullPayableQuery.isRowDisabled}
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
        pullQuery={pullPayableQuery.pullQuery}
        searchPlaceholder={t(`${P}.pullSearchPlaceholder`)}
        okText={t('common.confirm')}
      />
      <UniPullQueryModal<PaymentPullCandidate>
        open={pullAppQuery.open}
        title={t(`${P}.pullLines.modalSelectApplication`)}
        onCancel={pullAppQuery.closeModal}
        onOk={() => void pullAppQuery.handleConfirm()}
        rowKey="id"
        columns={appColumns}
        dataSource={pullAppQuery.dataSource}
        loading={pullAppQuery.loading}
        confirmLoading={pullAppQuery.confirmLoading}
        selectionType={pullAppQuery.selectionType}
        selectedRowKeys={pullAppQuery.selectedRowKeys}
        selectedRows={pullAppQuery.selectedRows}
        onSelectedRowKeysChange={pullAppQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullAppQuery.isRowDisabled}
        searchDraft={pullAppQuery.searchDraft}
        onSearchDraftChange={pullAppQuery.setSearchDraft}
        onSearchApply={pullAppQuery.handleSearchApply}
        onSearchClear={pullAppQuery.handleSearchClear}
        appliedKeyword={pullAppQuery.appliedKeyword}
        page={pullAppQuery.page}
        pageSize={pullAppQuery.pageSize}
        total={pullAppQuery.total}
        onPageChange={pullAppQuery.handlePageChange}
        scopeOptions={pullAppQuery.scopeOptions}
        scope={pullAppQuery.scope}
        onScopeChange={pullAppQuery.handleScopeChange}
        pullQuery={pullAppQuery.pullQuery}
        searchPlaceholder={t(`${P}.pullSearchPlaceholder`)}
        okText={t('common.confirm')}
      />
      <UniPullQueryModal<PoPullRow>
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
        pullQuery={pullPoQuery.pullQuery}
        searchPlaceholder={t(`${P}.pullSearchPlaceholder`)}
        okText={t('common.confirm')}
        footerHint={t(`${P}.pullLines.poPullHint`)}
      />
    </>
  );

  const pullLineColumns = useMemo(
    () => [
      {
        title: t(`${P}.pullLines.col.sourceType`),
        dataIndex: 'sourceType',
        width: 120,
        render: (_: unknown, field: FormListFieldData) => (
          <>
            <Form.Item name={[field.name, 'sourceType']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={[field.name, 'sourceId']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={[field.name, 'sourceCode']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={[field.name, 'maxAmount']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={[field.name, 'materialName']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={[field.name, 'materialSpec']} hidden>
              <Input />
            </Form.Item>
            <Form.Item name={[field.name, 'lineKind']} hidden>
              <Input />
            </Form.Item>
            <Form.Item shouldUpdate style={{ margin: 0 }}>
              {() =>
                sourceTypeLabel(
                  t,
                  formRef.current?.getFieldValue(['pull_lines', field.name, 'sourceType']),
                )
              }
            </Form.Item>
          </>
        ),
      },
      {
        title: t(`${P}.pullLines.col.sourceCode`),
        dataIndex: 'sourceCode',
        width: 160,
        render: (_: unknown, field: FormListFieldData) => (
          <Form.Item shouldUpdate style={{ margin: 0 }}>
            {() =>
              String(
                formRef.current?.getFieldValue(['pull_lines', field.name, 'sourceCode']) || '—',
              )
            }
          </Form.Item>
        ),
      },
      {
        title: t(`${P}.pullLines.col.material`),
        dataIndex: 'materialName',
        ellipsis: true,
        render: (_: unknown, field: FormListFieldData) => (
          <Form.Item shouldUpdate style={{ margin: 0 }}>
            {() => {
              const name = String(
                formRef.current?.getFieldValue(['pull_lines', field.name, 'materialName']) || '',
              ).trim();
              if (!name) return '—';
              const spec = String(
                formRef.current?.getFieldValue(['pull_lines', field.name, 'materialSpec']) || '',
              ).trim();
              return spec ? `${name} ${spec}` : name;
            }}
          </Form.Item>
        ),
      },
      {
        title: t(`${P}.pullLines.col.maxAmount`),
        dataIndex: 'maxAmount',
        width: 120,
        align: 'right' as const,
        render: (_: unknown, field: FormListFieldData) => (
          <Form.Item shouldUpdate style={{ margin: 0 }}>
            {() => {
              const maxAmt = Number(
                formRef.current?.getFieldValue(['pull_lines', field.name, 'maxAmount']) ?? 0,
              );
              return maxAmt > 0 ? formatCurrencyAmount(maxAmt) : '—';
            }}
          </Form.Item>
        ),
      },
      {
        title: t(`${P}.pullLines.col.paymentAmount`),
        dataIndex: 'paymentAmount',
        width: 140,
        render: (_: unknown, field: FormListFieldData) => (
          <Form.Item
            name={[field.name, 'paymentAmount']}
            rules={[{ required: true, message: t(`${P}.amountMustPositive`) }]}
            style={{ margin: 0 }}
          >
            <InputNumber
              min={0.01}
              onChange={() => syncPaymentTotalFromPullLines(formRef)}
              {...financeAmountDigitFieldProps}
            />
          </Form.Item>
        ),
      },
    ],
    [formRef, t],
  );

  return {
    pullLineColumns,
    renderPullLineHeaderActions,
    renderPullModals,
    pullLinesCompatibleWithSettlementType,
  };
}
