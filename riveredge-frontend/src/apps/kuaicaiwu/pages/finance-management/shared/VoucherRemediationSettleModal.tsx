/**
 * 收/付款单列表补救核销：本页 Modal 选对应付/应收并完成核销，不跳转往来核销页。
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  App,
  Button,
  Divider,
  Empty,
  InputNumber,
  Modal,
  Space,
  Spin,
  Table,
  Typography,
} from 'antd';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { UniTable } from '../../../../../components/uni-table';
import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';
import { MODAL_CONFIG } from '../../../../../components/layout-templates';
import { useNumericPrecisionPlaces } from '../../../../../hooks/useNumericPrecision';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { formatAmount, formatCurrencyAmount } from '../../../../../utils/format';
import {
  settlementService,
  type SettlementPreview,
} from '../../../services/finance/settlement';
import { payableService } from '../../../services/finance/payable';
import { receivableService } from '../../../services/finance/receivable';
import type { PayableListParams } from '../../../types/finance/payable';
import type { ReceivableListParams } from '../../../types/finance/receivable';
import {
  financeDocCreatedUpdatedColumns,
  resolvePayableListParams,
  resolveReceivableListParams,
} from '../../../utils/financeListCore';
import { settlementCapabilityReasonMessage } from '../../../utils/settlementCapabilityMessages';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';

const SETTLEMENT_P = 'app.kuaicaiwu.settlement';
const SETTLEMENT_RESOURCE = 'kuaicaiwu:settlement';
const C = 'app.kuaicaiwu.common';

export type RemediationVoucherSide = 'payment' | 'receipt';

export type RemediationVoucherSnapshot = {
  id: number;
  code: string;
  partnerId: number | null;
  partnerName: string;
  unsettledAmount: number;
};

type Props = {
  open: boolean;
  side: RemediationVoucherSide;
  voucher: RemediationVoucherSnapshot | null;
  onClose: () => void;
  onSuccess: () => void;
};

const formatSettleMoney = (value: number) => formatCurrencyAmount(value || 0);

export const VoucherRemediationSettleModal: React.FC<Props> = ({
  open,
  side,
  voucher,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const amountDecimals = useNumericPrecisionPlaces('amount');
  const settlementPerms = useResourcePermissions(SETTLEMENT_RESOURCE);
  const counterActionRef = useRef<ActionType>();

  const [selectedCounter, setSelectedCounter] = useState<Record<string, unknown> | null>(null);
  const [preview, setPreview] = useState<SettlementPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [settleAmount, setSettleAmount] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  const maxSettle = Number(preview?.max_settle_quantity ?? 0);
  const isPayment = side === 'payment';
  const partnerLabel = t(isPayment ? 'app.kuaicaiwu.common.supplier' : 'app.kuaicaiwu.common.customer');

  const resetCounter = useCallback(() => {
    setSelectedCounter(null);
    setPreview(null);
    setSettleAmount(0);
  }, []);

  useEffect(() => {
    if (!open) {
      resetCounter();
      return;
    }
    counterActionRef.current?.reload();
  }, [open, resetCounter, voucher?.id]);

  useEffect(() => {
    if (!open || selectedCounter || !voucher?.partnerId) return;
    let cancelled = false;
    const tryAutoPickSingleCounter = async () => {
      try {
        if (isPayment) {
          const res = await payableService.listPayables({
            skip: 0,
            limit: 2,
            pending_settlement: true,
            supplier_id: voucher.partnerId!,
          });
          const rows = (res?.items ?? []) as unknown as Record<string, unknown>[];
          if (!cancelled && rows.length === 1) {
            setSelectedCounter(rows[0]);
          }
          return;
        }
        const res = await receivableService.listReceivables({
          skip: 0,
          limit: 2,
          pending_settlement: true,
          customer_id: voucher.partnerId!,
        });
        const rows = (res?.items ?? []) as unknown as Record<string, unknown>[];
        if (!cancelled && rows.length === 1) {
          setSelectedCounter(rows[0]);
        }
      } catch {
        /* 列表失败时仍可在表格中点选 */
      }
    };
    void tryAutoPickSingleCounter();
    return () => {
      cancelled = true;
    };
  }, [open, selectedCounter, voucher?.partnerId, isPayment]);

  useEffect(() => {
    if (!open || !voucher?.id || !selectedCounter?.id) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setPreviewLoading(true);
      setPreview(null);
      try {
        const data = isPayment
          ? await settlementService.previewPayableSettle(
              Number(selectedCounter.id),
              voucher.id,
            )
          : await settlementService.previewReceivableSettle(
              Number(selectedCounter.id),
              voucher.id,
            );
        if (cancelled) return;
        setPreview(data);
        const maxPush = Number(data.max_settle_quantity ?? 0);
        setSettleAmount(maxPush > 0 ? maxPush : 0);
      } catch (error: unknown) {
        if (!cancelled) {
          const err = error as { response?: { data?: { detail?: { message?: string } | string } }; message?: string };
          message.error(
            (typeof err.response?.data?.detail === 'object'
              ? err.response?.data?.detail?.message
              : err.response?.data?.detail) ||
              err.message ||
              t(`${SETTLEMENT_P}.previewFailed`),
          );
          resetCounter();
        }
      } finally {
        if (!cancelled) setPreviewLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [open, voucher?.id, selectedCounter?.id, isPayment, message, resetCounter, t]);

  const handleSubmit = async () => {
    if (!settlementPerms.canUpdate || !voucher || !selectedCounter || !preview || preview.has_blocking_issues) {
      message.error(t(`${SETTLEMENT_P}.invalidAmount`));
      return;
    }
    if (settleAmount <= 0 || settleAmount > maxSettle) {
      message.error(t(`${SETTLEMENT_P}.pullExceedMax`, { max: formatAmount(maxSettle) }));
      return;
    }
    setSubmitting(true);
    try {
      if (isPayment) {
        await settlementService.settlePayable(
          Number(selectedCounter.id),
          voucher.id,
          settleAmount,
        );
      } else {
        await settlementService.settleReceivable(
          Number(selectedCounter.id),
          voucher.id,
          settleAmount,
        );
      }
      message.success(t(`${SETTLEMENT_P}.settleSuccess`));
      onSuccess();
      onClose();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: { message?: string } | string } }; message?: string };
      message.error(
        (typeof err.response?.data?.detail === 'object'
          ? err.response?.data?.detail?.message
          : err.response?.data?.detail) ||
          err.message ||
          t(`${SETTLEMENT_P}.settleFailed`, { message: '' }),
      );
    } finally {
      setSubmitting(false);
    }
  };

  const counterColumns: ProColumns<Record<string, unknown>>[] = useMemo(
    () => [
      {
        title: t(`${C}.code`),
        key: 'finance_doc_partner_stacked',
        dataIndex: isPayment ? 'payable_code' : 'receivable_code',
        minWidth: 160,
        uniTableRemainderFlex: true,
        uniTablePrimaryFlex: true,
        fixed: 'left',
        hideInSearch: true,
        render: (_, r) => (
          <UniTableStackedPrimaryCell
            primary={String((isPayment ? r.supplier_name : r.customer_name) ?? '')}
            secondary={String((isPayment ? r.payable_code : r.receivable_code) ?? '')}
          />
        ),
      },
      {
        title: isPayment ? t(`${SETTLEMENT_P}.col.pendingPay`) : t(`${SETTLEMENT_P}.col.balance`),
        dataIndex: isPayment ? 'remaining_amount' : 'remaining_amount',
        valueType: 'money',
        align: 'right',
        width: 120,
        minWidth: 120,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
      },
      ...financeDocCreatedUpdatedColumns<Record<string, unknown>>(t),
    ],
    [isPayment, t],
  );

  const previewBody = () => {
    if (previewLoading) {
      return (
        <div
          style={{
            minHeight: 120,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 12,
          }}
        >
          <Spin />
          <div style={{ color: 'var(--ant-color-primary)' }}>{t(`${SETTLEMENT_P}.loadingPreview`)}</div>
        </div>
      );
    }
    if (!preview) return null;
    return (
      <Space orientation="vertical" style={{ width: '100%' }} size={12}>
        <Typography.Paragraph style={{ marginBottom: 0, fontWeight: 500 }}>{preview.summary}</Typography.Paragraph>
        {preview.has_blocking_issues && preview.blocking_reason ? (
          <Alert
            type="warning"
            showIcon
            title={settlementCapabilityReasonMessage(preview.blocking_reason, t)}
          />
        ) : null}
        {preview.items?.length ? (
          <Table
            size="small"
            dataSource={(preview.items ?? []) as unknown as Array<Record<string, unknown>>}
            rowKey={(row) => `${row.doc_type}-${row.item_id}`}
            pagination={false}
            scroll={{ x: 800 }}
            columns={[
              {
                title: t(`${SETTLEMENT_P}.preview.col.docType`),
                dataIndex: 'doc_type',
                width: 100,
                render: (v: string) => t(`${SETTLEMENT_P}.preview.docType.${v}`, { defaultValue: v }),
              },
              { title: t(`${C}.code`), dataIndex: 'source_code', width: 140, ellipsis: true },
              { title: partnerLabel, dataIndex: 'partner_name', width: 160, ellipsis: true },
              {
                title: t(`${SETTLEMENT_P}.preview.col.docAmount`),
                dataIndex: 'quantity',
                width: 120,
                align: 'right',
                render: (v: number) => formatSettleMoney(v),
              },
              {
                title: t(`${SETTLEMENT_P}.preview.col.settledAmount`),
                dataIndex: 'pushed_quantity',
                width: 120,
                align: 'right',
                render: (v: number) => formatSettleMoney(v),
              },
              {
                title: t(`${SETTLEMENT_P}.preview.col.settleableAmount`),
                dataIndex: 'max_push_quantity',
                width: 120,
                align: 'right',
                render: (v: number) => formatSettleMoney(v),
              },
            ]}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t(`${SETTLEMENT_P}.previewNoLines`)} />
        )}
        {preview.tip ? (
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {preview.tip}
          </Typography.Paragraph>
        ) : null}
        {!preview.has_blocking_issues && Number(preview.max_settle_quantity) > 0 ? (
          <>
            <Divider style={{ margin: '8px 0' }} />
            <Typography.Text>{t(`${SETTLEMENT_P}.settleAmount`)}</Typography.Text>
            <InputNumber
              style={{ width: '100%' }}
              value={settleAmount}
              min={0.01}
              max={Number(preview.max_settle_quantity)}
              precision={amountDecimals}
              onChange={(val) => setSettleAmount(val || 0)}
            />
          </>
        ) : null}
      </Space>
    );
  };

  const title = isPayment
    ? t('app.kuaicaiwu.payment.remediationSettleModalTitle')
    : t('app.kuaicaiwu.receipt.remediationSettleModalTitle');

  return (
    <Modal
      title={title}
      open={open}
      width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
      destroyOnHidden
      onCancel={onClose}
      footer={[
        <Button key="cancel" onClick={onClose}>
          {t('common.cancel')}
        </Button>,
        selectedCounter ? (
          <Button key="reselect" onClick={resetCounter}>
            {t(`${SETTLEMENT_P}.remediationReselectCounter`)}
          </Button>
        ) : null,
        <Button
          key="ok"
          type="primary"
          loading={submitting}
          disabled={
            !settlementPerms.canUpdate ||
            !selectedCounter ||
            previewLoading ||
            !preview ||
            !!preview?.has_blocking_issues ||
            maxSettle <= 0 ||
            settleAmount <= 0
          }
          onClick={() => void handleSubmit()}
        >
          {t(`${SETTLEMENT_P}.confirmSettle`)}
        </Button>,
      ]}
    >
      <Alert type="warning" showIcon style={{ marginBottom: 16 }} title={t(`${SETTLEMENT_P}.remediationModeAlert`)} />
      {voucher ? (
        <Typography.Paragraph style={{ marginBottom: 16 }}>
          {t(`${SETTLEMENT_P}.remediationVoucherSummary`, {
            voucherLabel: isPayment
              ? t('app.kuaicaiwu.payment.entityName')
              : t('app.kuaicaiwu.receipt.entityName'),
            code: voucher.code,
            partner: voucher.partnerName,
            unsettled: formatSettleMoney(voucher.unsettledAmount),
          })}
        </Typography.Paragraph>
      ) : null}

      {!selectedCounter ? (
        <UniTable
          headerTitle={
            isPayment ? t(`${SETTLEMENT_P}.pendingPayables`) : t(`${SETTLEMENT_P}.pendingReceivables`)
          }
          actionRef={counterActionRef}
          rowKey="id"
          viewTypes={['table']}
          columnPersistenceId={`apps.kuaicaiwu.pages.finance-management.voucher-remediation-${side}-v1`}
          showAdvancedSearch={false}
          request={async (params, sort, _filter, searchFormValues) => {
            if (!voucher?.partnerId) {
              return { data: [], total: 0, success: true };
            }
            const { current, pageSize } = params;
            try {
              if (isPayment) {
                const listParams = resolvePayableListParams(searchFormValues, sort);
                const apiParams: PayableListParams = {
                  skip: ((current || 1) - 1) * (pageSize || 20),
                  limit: pageSize || 20,
                  pending_settlement: true,
                  supplier_id: voucher.partnerId,
                  ...listParams,
                };
                const res = await payableService.listPayables(apiParams);
                return {
                  data: (res?.items || []) as unknown as Record<string, unknown>[],
                  total: res?.total || 0,
                  success: true,
                };
              }
              const listParams = resolveReceivableListParams(searchFormValues, sort);
              const apiParams: ReceivableListParams = {
                skip: ((current || 1) - 1) * (pageSize || 20),
                limit: pageSize || 20,
                pending_settlement: true,
                customer_id: voucher.partnerId,
                ...listParams,
              };
              const res = await receivableService.listReceivables(apiParams);
              return {
                data: (res?.items || []) as unknown as Record<string, unknown>[],
                total: res?.total || 0,
                success: true,
              };
            } catch (error: unknown) {
              const err = error as { message?: string };
              message.error(err?.message || t('app.kuaicaiwu.common.loadListFailed'));
              return { data: [], total: 0, success: false };
            }
          }}
          columns={alignProColumns(counterColumns, SALES_DOC_LIST_FIELD_RANK)}
          scroll={{ y: 320 }}
          onRow={(record) => ({
            onClick: () => setSelectedCounter(record as Record<string, unknown>),
            style: { cursor: 'pointer' },
          })}
        />
      ) : (
        <>
          <Alert
            type="success"
            showIcon
            style={{ marginBottom: 16 }}
            title={t(
              isPayment ? `${SETTLEMENT_P}.selectedPayable` : `${SETTLEMENT_P}.selectedReceivable`,
              {
                code: String(
                  (isPayment ? selectedCounter.payable_code : selectedCounter.receivable_code) ?? '',
                ),
              },
            )}
          />
          {previewBody()}
        </>
      )}
    </Modal>
  );
};

export function toPaymentRemediationSnapshot(record: {
  id?: number;
  payment_code?: string;
  supplier_id?: number | null;
  supplier_name?: string | null;
  unsettled_amount?: number | null;
}): RemediationVoucherSnapshot | null {
  if (record.id == null) return null;
  return {
    id: Number(record.id),
    code: String(record.payment_code ?? record.id),
    partnerId: record.supplier_id != null ? Number(record.supplier_id) : null,
    partnerName: String(record.supplier_name ?? ''),
    unsettledAmount: Number(record.unsettled_amount ?? 0),
  };
}

export function toReceiptRemediationSnapshot(record: {
  id?: number;
  receipt_code?: string;
  customer_id?: number | null;
  customer_name?: string | null;
  unsettled_amount?: number | null;
}): RemediationVoucherSnapshot | null {
  if (record.id == null) return null;
  return {
    id: Number(record.id),
    code: String(record.receipt_code ?? record.id),
    partnerId: record.customer_id != null ? Number(record.customer_id) : null,
    partnerName: String(record.customer_name ?? ''),
    unsettledAmount: Number(record.unsettled_amount ?? 0),
  };
}
