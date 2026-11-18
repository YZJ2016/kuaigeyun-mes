/**
 * 收款单 FormModal：从应收单 / 销售订单加载明细
 */
import React, { useCallback, useMemo, useRef } from 'react';
import type { ProFormInstance } from '@ant-design/pro-components';
import { App, Button, Form, Input, InputNumber, Space } from 'antd';
import type { FormListFieldData } from 'antd/es/form';
import { useTranslation } from 'react-i18next';
import {
  UniPullQueryModal,
  renderPullQueryDocStatus,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import { formatCurrencyAmount } from '../../../../../utils/format';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import { getKuaicaiwuDocumentAction } from '../../../constants/documentActionRegistry';
import {
  receiptService,
  type ReceiptPullCandidate,
  type ReceiptSalesOrderPrepaymentPullCandidate,
} from '../../../services/finance/receipt';
import { loadFinancePullCandidatePage } from './loadFinancePullCandidatePage';
import { financeAmountDigitFieldProps } from '../../../utils/financeFormLayout';
import { allocateAmountByWeights, roundBusinessAmount } from '../../../../kuaizhizao/utils/documentLineAmounts';
import { formatBusinessDateOnly } from '../../../../../utils/format';
import { salesOrderCapabilityReasonMessage } from '../../../../../hooks/useDocumentCapabilities';

const R = 'app.kuaicaiwu.receipt';

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
    return rows.every((r) => String(r.sourceType || '').trim() === 'sales_order');
  }
  return rows.every((r) => String(r.sourceType || '').trim() === 'receivable');
}

export function syncReceiptTotalFromPullLines(formRef: React.RefObject<ProFormInstance | undefined>) {
  const lines = normalizeFormListItems<Record<string, unknown>>(
    formRef.current?.getFieldValue('pull_lines'),
  );
  const sum = lines.reduce((acc, row) => acc + Number(row.receiptAmount ?? 0), 0);
  if (sum > 0) {
    formRef.current?.setFieldsValue({ total_amount: roundBusinessAmount(sum) });
  }
}

export function applyReceiptHeaderAmountToPullLines(
  headerAmount: number,
  rows: Record<string, unknown>[],
): Record<string, unknown>[] {
  if (!rows.length) return rows;
  if (rows.length === 1) {
    return [{ ...rows[0], receiptAmount: headerAmount }];
  }
  const weights = rows.map((row) => {
    const w = Number(row.maxAmount ?? row.receiptAmount ?? 0);
    return w > 0 ? w : 1;
  });
  const parts = allocateAmountByWeights(headerAmount, weights);
  return rows.map((row, index) => {
    const cap = Number(row.maxAmount ?? 0);
    let part = parts[index] ?? 0;
    if (cap > 0 && part > cap) part = cap;
    return { ...row, receiptAmount: part };
  });
}

export function handleReceiptVoucherFormValuesChange(
  formRef: React.RefObject<ProFormInstance | undefined>,
  changedValues: Record<string, unknown>,
  allValues: Record<string, unknown>,
) {
  if (Object.prototype.hasOwnProperty.call(changedValues, 'pull_lines')) {
    syncReceiptTotalFromPullLines(formRef);
    return;
  }
  if (!Object.prototype.hasOwnProperty.call(changedValues, 'total_amount')) return;
  const rows = normalizeFormListItems<Record<string, unknown>>(allValues.pull_lines);
  if (!rows.length) return;
  const nextAmount = Number(changedValues.total_amount);
  if (!Number.isFinite(nextAmount)) return;
  formRef.current?.setFieldsValue({
    pull_lines: applyReceiptHeaderAmountToPullLines(nextAmount, rows),
  });
}

export function readReceiptPullLineFormFields(row: Record<string, unknown>) {
  const receiptAmount = Number(row.receiptAmount ?? row.amount ?? 0);
  return {
    sourceType: String(row.sourceType ?? row.source_type ?? '').trim(),
    sourceId: Number(row.sourceId ?? row.source_id ?? 0),
    sourceCode: String(row.sourceCode ?? row.source_code ?? '').trim(),
    receiptAmount: Number.isFinite(receiptAmount) ? receiptAmount : 0,
  };
}

export function filterValidReceiptPullFormLines(items: unknown): Record<string, unknown>[] {
  return normalizeFormListItems<Record<string, unknown>>(items).filter((row) => {
    const f = readReceiptPullLineFormFields(row);
    return f.sourceType.length > 0 && f.sourceId > 0 && f.receiptAmount > 0;
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
  const rows = filterValidReceiptPullFormLines(items);
  if (!rows.length) return undefined;
  return rows.map((row) => {
    const f = readReceiptPullLineFormFields(row);
    return {
      source_type: f.sourceType,
      source_id: f.sourceId,
      source_code: f.sourceCode || undefined,
      amount: f.receiptAmount,
    };
  });
}

export function validateReceiptPullLinesBeforeSubmit(
  items: unknown,
  totalAmount: number,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string | null {
  const rows = filterValidReceiptPullFormLines(items);
  if (!rows.length) return null;
  const types = new Set(rows.map((r) => readReceiptPullLineFormFields(r).sourceType));
  if (types.size > 1) return t(`${R}.pullLines.mixedSourceForbidden`);
  const sum = rows.reduce((acc, row) => acc + readReceiptPullLineFormFields(row).receiptAmount, 0);
  if (Math.abs(sum - Number(totalAmount || 0)) > 0.009) {
    return t(`${R}.pullLines.totalMustMatchLines`);
  }
  for (const row of rows) {
    const maxAmt = Number(row.maxAmount ?? 0);
    const payAmt = readReceiptPullLineFormFields(row).receiptAmount;
    if (maxAmt > 0 && payAmt > maxAmt + 0.009) return t(`${R}.pullLines.exceedsMax`);
    if (!(payAmt > 0)) return t(`${R}.amountRequired`);
  }
  return null;
}

export function requireReceiptPullLinesForNormalSettlement(
  settlementType: unknown,
  items: unknown,
  totalAmount: number,
  t: (key: string) => string,
): string | null {
  const st = String(settlementType || 'normal').trim() || 'normal';
  if (st === 'refund' || st === 'prepayment') return null;
  const rows = normalizeFormListItems<Record<string, unknown>>(items);
  if (!rows.length) return t(`${R}.pullLines.requiredForNormalSettlement`);
  return validateReceiptPullLinesBeforeSubmit(items, totalAmount, t);
}

function sourceTypeLabel(t: (key: string) => string, sourceType: unknown): string {
  const st = String(sourceType || '').trim();
  if (st === 'sales_order') return t(`${R}.pullLines.sourceSalesOrder`);
  if (st === 'receivable') return t(`${R}.pullLines.sourceReceivable`);
  return st || '—';
}

type SoPullRow = ReceiptSalesOrderPrepaymentPullCandidate & {
  pullable?: boolean;
  disableReason?: string;
};

function mapSoPreviewLineToReceiptPullRow(
  soId: number,
  soCode: string,
  line: Record<string, unknown>,
): Record<string, unknown> {
  const receiptAmt = Number(line.requestAmount ?? line.request_amount ?? 0);
  return {
    lineKind: 'prepayment',
    sourceType: 'sales_order',
    sourceId: soId,
    sourceCode: String(line.sourceCode ?? line.source_code ?? soCode),
    maxAmount: receiptAmt,
    receiptAmount: receiptAmt,
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

export function useReceiptVoucherFormLinePull({ formRef }: Props) {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const closeReceivableRef = useRef<(() => void) | null>(null);
  const closeSoRef = useRef<(() => void) | null>(null);

  const pullFromReceivableAction = getKuaicaiwuDocumentAction('receipt.pull_from_receivable');

  const scopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const pullColumns = useMemo(
    () => [
      { title: t(`${R}.pullCol.receivableCode`), dataIndex: 'code', width: 148, ellipsis: true },
      { title: t('app.kuaicaiwu.common.customer'), dataIndex: 'customer_name', width: 160, ellipsis: true },
      {
        title: t('app.kuaicaiwu.receivable.col.remainingAmount'),
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
      syncReceiptTotalFromPullLines(formRef);
    },
    [formRef],
  );

  const assertCustomerSelected = useCallback(() => {
    const customerId = Number(formRef.current?.getFieldValue('customer_id'));
    if (!Number.isFinite(customerId) || customerId <= 0) {
      messageApi.warning(t(`${R}.pullLines.selectCustomerFirst`));
      return null;
    }
    return customerId;
  }, [formRef, messageApi, t]);

  const assertNoMixedSource = useCallback(
    (nextType: 'receivable' | 'sales_order') => {
      const existing = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('pull_lines'),
      );
      if (!existing.length) return true;
      const currentType = String(existing[0]?.sourceType || '').trim();
      if (currentType && currentType !== nextType) {
        messageApi.warning(t(`${R}.pullLines.mixedSourceForbidden`));
        return false;
      }
      return true;
    },
    [formRef, messageApi, t],
  );

  const pullReceivableQuery = useUniPullQuery<ReceiptPullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => record.capabilities?.pull_receipt?.allowed === false,
    loadData: async (params) => {
      const customerId = assertCustomerSelected();
      if (customerId == null) return { data: [], total: 0 };
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          (row) => row.capabilities?.pull_receipt?.allowed !== false,
          (api) => receiptService.listReceivablePullCandidates(api),
          {},
        );
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${R}.loadSourceFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const settlementType = String(formRef.current?.getFieldValue('settlement_type') || 'normal');
      if (settlementType === 'prepayment') {
        messageApi.warning(t(`${R}.pullLines.prepaymentNoReceivable`));
        return;
      }
      if (!assertNoMixedSource('receivable')) return;

      const selectedRows = rows.filter((row) => keys.some((k) => String(k) === String(row.id)));
      const selectedIds = selectedRows.map((r) => Number(r.id)).filter((id) => id > 0);
      if (!selectedIds.length) {
        messageApi.warning(t(`${R}.selectSource`, { label: pullFromReceivableAction.sourceLabel }));
        return;
      }
      const customerIds = new Set(
        selectedRows.map((r) => Number(r.customer_id ?? 0)).filter((id) => id > 0),
      );
      if (customerIds.size > 1) {
        messageApi.warning(t(`${R}.sameCustomerRequired`));
        return;
      }
      try {
        const preview =
          selectedIds.length === 1
            ? await receiptService.previewPullFromReceivable(selectedIds[0])
            : await receiptService.previewPullFromReceivables(selectedIds);
        if (preview.has_blocking_issues) {
          messageApi.warning(t(`${R}.loadSourceFailed`));
          return;
        }
        const existing = normalizeFormListItems<Record<string, unknown>>(
          formRef.current?.getFieldValue('pull_lines'),
        );
        const usedIds = new Set(existing.map((r) => Number(r.sourceId)).filter((id) => id > 0));
        const newLines: Record<string, unknown>[] = [];
        for (const item of preview.items ?? []) {
          const raw = item as { item_id?: number; receivable_id?: number; max_push_quantity?: number; source_code?: string };
          const sourceId = Number(raw.item_id ?? raw.receivable_id ?? 0);
          if (!sourceId || usedIds.has(sourceId)) continue;
          const maxAmount = Number(raw.max_push_quantity ?? 0);
          if (!(maxAmount > 0)) continue;
          usedIds.add(sourceId);
          newLines.push({
            sourceType: 'receivable',
            sourceId,
            sourceCode: String(raw.source_code ?? sourceId),
            maxAmount,
            receiptAmount: maxAmount,
          });
        }
        if (!newLines.length) {
          messageApi.warning(t(`${R}.pullLines.noNewLines`));
          return;
        }
        if (preview.customer_id) {
          formRef.current?.setFieldsValue({ customer_id: preview.customer_id });
        }
        mergePullLines(newLines, false);
        closeReceivableRef.current?.();
        messageApi.success(t(`${R}.pullLines.merged`, { count: newLines.length }));
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${R}.loadSourceFailed`)));
      }
    },
  });
  closeReceivableRef.current = pullReceivableQuery.closeModal;

  const soPullColumns = useMemo(
    () => [
      { title: t('common.code'), dataIndex: 'code', width: 160, ellipsis: true },
      {
        title: t('components.uniPullQuery.documentDateColumn'),
        dataIndex: 'documentDate',
        width: 112,
        render: (v?: string | null) => (v ? formatBusinessDateOnly(String(v)) : '—'),
      },
      { title: t('app.kuaicaiwu.common.customer'), dataIndex: 'partnerName', ellipsis: true },
      {
        title: t(`${R}.pullLines.col.maxAmount`),
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

  const isSoPullable = useCallback(
    (row: SoPullRow) => row.capabilities?.pull_prepayment?.allowed === true,
    [],
  );

  const pullSoQuery = useUniPullQuery<SoPullRow>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (row) => !isSoPullable(row),
    loadData: async (params) => {
      const customerId = assertCustomerSelected();
      if (customerId == null) return { data: [], total: 0 };
      try {
        const pageResult = await loadFinancePullCandidatePage<ReceiptSalesOrderPrepaymentPullCandidate>(
          params,
          params.scope,
          (row) => row.capabilities?.pull_prepayment?.allowed === true,
          (api) =>
            receiptService.listSalesOrderPrepaymentPullCandidates({
              ...api,
              customer_id: customerId,
            }),
        );
        const rows: SoPullRow[] = pageResult.data.map((o) => {
          const reasonCode = String(o.capabilities?.pull_prepayment?.reason ?? '');
          return {
            ...o,
            partnerName: String(o.partnerName ?? o.customer_name ?? ''),
            documentDate:
              o.documentDate != null
                ? String(o.documentDate).slice(0, 10)
                : null,
            pullable: o.capabilities?.pull_prepayment?.allowed === true,
            disableReason: reasonCode
              ? salesOrderCapabilityReasonMessage(reasonCode, t)
              : t(`${R}.pullLines.soNotSelectable`),
          };
        });
        return { data: rows, total: pageResult.total };
      } catch (e) {
        messageApi.error(getApiErrorMessage(e, t(`${R}.loadSourceFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (_keys, rows) => {
      if (!assertNoMixedSource('sales_order')) return;
      const existing = normalizeFormListItems<Record<string, unknown>>(
        formRef.current?.getFieldValue('pull_lines'),
      );
      const usedSoIds = new Set(
        existing
          .filter((r) => String(r.sourceType || '').trim() === 'sales_order')
          .map((r) => Number(r.sourceId))
          .filter((id) => id > 0),
      );
      const newLines: Record<string, unknown>[] = [];
      let skipped = 0;
      for (const row of rows) {
        const soId = Number(row.id);
        if (!soId || usedSoIds.has(soId)) continue;
        try {
          const preview = await receiptService.previewPullFromSalesOrder(soId);
          if (preview.has_blocking_issues) {
            skipped += 1;
            continue;
          }
          const items = (preview.items as unknown as Record<string, unknown>[] | undefined) ?? [];
          if (!items.length) {
            skipped += 1;
            continue;
          }
          const soCode = String(preview.source_code ?? row.code ?? soId);
          usedSoIds.add(soId);
          for (const ln of items) {
            newLines.push(mapSoPreviewLineToReceiptPullRow(soId, soCode, ln));
          }
          if (preview.customer_id) {
            formRef.current?.setFieldsValue({ customer_id: preview.customer_id });
          }
        } catch {
          skipped += 1;
        }
      }
      if (!newLines.length) {
        messageApi.warning(
          skipped > 0 ? t(`${R}.pullLines.soAllSkipped`) : t(`${R}.pullLines.noNewLines`),
        );
        return;
      }
      mergePullLines(newLines, false);
      closeSoRef.current?.();
      if (skipped > 0) messageApi.warning(t(`${R}.pullLines.soPartialSkip`, { count: skipped }));
      messageApi.success(t(`${R}.pullLines.merged`, { count: newLines.length }));
    },
  });
  closeSoRef.current = pullSoQuery.closeModal;

  const openPullReceivable = useCallback(() => {
    if (assertCustomerSelected() == null) return;
    pullReceivableQuery.openModal();
  }, [assertCustomerSelected, pullReceivableQuery]);

  const openPullSalesOrder = useCallback(() => {
    if (assertCustomerSelected() == null) return;
    pullSoQuery.openModal();
  }, [assertCustomerSelected, pullSoQuery]);

  const renderPullLineHeaderActions = useCallback(
    () => (
      <Form.Item noStyle shouldUpdate={(prev, cur) => prev.settlement_type !== cur.settlement_type}>
        {({ getFieldValue }) => {
          const settlementType = String(getFieldValue('settlement_type') || 'normal').trim() || 'normal';
          const showReceivablePull = settlementType === 'normal';
          const showSoPrepayPull = settlementType === 'prepayment';
          return (
            <Space size={8} wrap>
              {showReceivablePull ? (
                <Button size="small" onClick={openPullReceivable}>
                  {t(`${R}.pullLines.loadFromReceivable`)}
                </Button>
              ) : null}
              {showSoPrepayPull ? (
                <Button size="small" onClick={openPullSalesOrder}>
                  {t(`${R}.pullLines.loadFromSalesOrder`)}
                </Button>
              ) : null}
            </Space>
          );
        }}
      </Form.Item>
    ),
    [openPullReceivable, openPullSalesOrder, t],
  );

  const renderPullModals = () => (
    <>
      <UniPullQueryModal<ReceiptPullCandidate>
        open={pullReceivableQuery.open}
        title={t(`${R}.pullLines.modalSelectReceivable`)}
        onCancel={pullReceivableQuery.closeModal}
        onOk={() => void pullReceivableQuery.handleConfirm()}
        rowKey="id"
        columns={pullColumns}
        dataSource={pullReceivableQuery.dataSource}
        loading={pullReceivableQuery.loading}
        confirmLoading={pullReceivableQuery.confirmLoading}
        selectionType={pullReceivableQuery.selectionType}
        selectedRowKeys={pullReceivableQuery.selectedRowKeys}
        selectedRows={pullReceivableQuery.selectedRows}
        onSelectedRowKeysChange={pullReceivableQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullReceivableQuery.isRowDisabled}
        searchDraft={pullReceivableQuery.searchDraft}
        onSearchDraftChange={pullReceivableQuery.setSearchDraft}
        onSearchApply={pullReceivableQuery.handleSearchApply}
        onSearchClear={pullReceivableQuery.handleSearchClear}
        appliedKeyword={pullReceivableQuery.appliedKeyword}
        page={pullReceivableQuery.page}
        pageSize={pullReceivableQuery.pageSize}
        total={pullReceivableQuery.total}
        onPageChange={pullReceivableQuery.handlePageChange}
        scopeOptions={pullReceivableQuery.scopeOptions}
        scope={pullReceivableQuery.scope}
        onScopeChange={pullReceivableQuery.handleScopeChange}
        pullQuery={pullReceivableQuery.pullQuery}
        searchPlaceholder={t(`${R}.pullSearchPlaceholder`)}
        okText={t('common.confirm')}
      />
      <UniPullQueryModal<SoPullRow>
        open={pullSoQuery.open}
        title={t(`${R}.pullLines.modalSelectSalesOrder`)}
        onCancel={pullSoQuery.closeModal}
        onOk={() => void pullSoQuery.handleConfirm()}
        rowKey="id"
        columns={soPullColumns}
        dataSource={pullSoQuery.dataSource}
        loading={pullSoQuery.loading}
        confirmLoading={pullSoQuery.confirmLoading}
        selectionType={pullSoQuery.selectionType}
        selectedRowKeys={pullSoQuery.selectedRowKeys}
        selectedRows={pullSoQuery.selectedRows}
        onSelectedRowKeysChange={pullSoQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullSoQuery.isRowDisabled}
        searchDraft={pullSoQuery.searchDraft}
        onSearchDraftChange={pullSoQuery.setSearchDraft}
        onSearchApply={pullSoQuery.handleSearchApply}
        onSearchClear={pullSoQuery.handleSearchClear}
        appliedKeyword={pullSoQuery.appliedKeyword}
        page={pullSoQuery.page}
        pageSize={pullSoQuery.pageSize}
        total={pullSoQuery.total}
        onPageChange={pullSoQuery.handlePageChange}
        scopeOptions={pullSoQuery.scopeOptions}
        scope={pullSoQuery.scope}
        onScopeChange={pullSoQuery.handleScopeChange}
        pullQuery={pullSoQuery.pullQuery}
        searchPlaceholder={t(`${R}.pullSearchPlaceholder`)}
        okText={t('common.confirm')}
        footerHint={t(`${R}.pullLines.soPullHint`)}
      />
    </>
  );

  const pullLineColumns = useMemo(
    () => [
      {
        title: t(`${R}.pullLines.col.sourceType`),
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
            <Form.Item name={[field.name, 'receiptAmount']} hidden>
              <InputNumber min={0.01} {...financeAmountDigitFieldProps} />
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
        title: t(`${R}.pullLines.col.sourceCode`),
        dataIndex: 'sourceCode',
        width: 160,
        render: (_: unknown, field: FormListFieldData) => (
          <Form.Item shouldUpdate style={{ margin: 0 }}>
            {() =>
              String(formRef.current?.getFieldValue(['pull_lines', field.name, 'sourceCode']) || '—')
            }
          </Form.Item>
        ),
      },
      {
        title: t(`${R}.pullLines.col.material`),
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
        title: t(`${R}.pullLines.col.maxAmount`),
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