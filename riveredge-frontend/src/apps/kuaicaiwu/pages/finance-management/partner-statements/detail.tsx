/**
 * 往来对账单详情页（快制造财务管理；启用轻财务后由 kuaicaiwu 托管菜单）
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Descriptions,
  Dropdown,
  Input,
  Space,
  Spin,
  Table,
  Typography,
  message,
} from 'antd';
import { DownOutlined } from '@ant-design/icons';
import MergeFinanceDocsModal, {
  type MergeFinanceSourceRow,
} from '../../../components/MergeFinanceDocsModal';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  DOCUMENT_DETAIL_PAGE_HEADER_STYLE,
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  uniTabsChildPageVerticalInsetStyle,
} from '../../../../../components/layout-templates';
import {
  partnerStatementService,
  PartnerStatement,
  PartnerStatementAmountBasis,
  PartnerStatementLine,
  downloadBlob,
} from '../../../services/finance/partnerStatement';
import {
  partnerStatementExpandableProps,
  usePartnerStatementInboundDetail,
} from '../../../components/PartnerStatementInboundDetail';
import {
  buildPartnerStatementStatusEnum,
  formatSentChannel,
  shouldShowPartnerStatementReviewApprovedBadge,
} from '../../../utils/financeSharedOptions';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { formatDateTime, formatCurrencyAmount } from '../../../../../utils/format';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import {
  buildLineAmountPayload,
  patchLineStatementAmount,
  previewLineKey,
  recalcPartnerStatementLines,
} from '../../../utils/partnerStatementAmountUtils';
import { usePartnerStatementLineColumns } from '../../../utils/partnerStatementLineColumns';
import { useFinanceVoucherDetail } from '../../../components/FinanceVoucherDetailProvider';
import { resolvePartnerStatementVoucherTarget } from '../../../utils/financeVoucherDocType';
import { getAntdModal } from '../../../../../utils/antdAppApis';
import { pullPaymentApplicationFromReconciliation } from '../../../../kuaizhizao/services/payment-application';
import { purchaseInvoiceService } from '../../../services/finance/purchase-invoice';
import {
  collectStatementInvoiceLines,
  invoiceSourceDocTypeForMode,
} from '../../../utils/partnerStatementInvoicePull';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { PartnerStatementSettingsBar } from './PartnerStatementSettingsBar';

const PS = 'app.kuaicaiwu.partnerStatement';
const PARTNER_STATEMENT_RESOURCE = 'kuaicaiwu:partner-statement';
const PARTNER_STATEMENT_ENTITY = 'partner_statement';

function linePushAmount(ln: PartnerStatementLine): number {
  return Number(ln.statement_amount ?? ln.doc_amount ?? 0);
}

function collectPayableStatementLines(lines: PartnerStatementLine[]): PartnerStatementLine[] {
  return lines.filter((ln) => {
    if (String(ln.doc_type || '').trim() !== '应付单') return false;
    if (ln.doc_id == null) return false;
    if (Number(ln.tree_level ?? 0) > 0) return false;
    return linePushAmount(ln) > 0;
  });
}

function statementInvoiceEmptyMessageKey(
  partnerType: string,
  ledgerPostingMode?: string | null,
): string {
  if (partnerType === 'Supplier') {
    return ledgerPostingMode === 'by_invoice'
      ? `${PS}.detail.pushSelectPurchaseReceipt`
      : `${PS}.detail.pushSelectPayable`;
  }
  return `${PS}.detail.pushSelectReceivable`;
}

const money = (v: number | string | undefined) =>
  formatCurrencyAmount(v ?? 0);

function resolveStatementAmountBasis(
  data: PartnerStatement | null,
): PartnerStatementAmountBasis {
  const basis = data?.transaction_details?.amount_basis;
  return basis === 'tax_exclusive' ? 'tax_exclusive' : 'tax_inclusive';
}

function resolveStatementLedgerMode(data: PartnerStatement | null): 'immediate' | 'by_invoice' {
  return data?.ledger_posting_mode === 'by_invoice' ? 'by_invoice' : 'immediate';
}

function PartnerStatementHeaderControls({
  data,
  editable,
  linesDirty,
  headerBusy,
  onLedgerChange,
  onAmountBasisChange,
}: {
  data: PartnerStatement;
  editable: boolean;
  linesDirty: boolean;
  headerBusy: boolean;
  onLedgerChange: (mode: 'immediate' | 'by_invoice') => void;
  onAmountBasisChange: (basis: PartnerStatementAmountBasis) => void;
}) {
  if (!editable) {
    return null;
  }
  return (
    <PartnerStatementSettingsBar
      showLedger={data.partner_uses_statement_ledger === true}
      ledgerMode={resolveStatementLedgerMode(data)}
      amountBasis={resolveStatementAmountBasis(data)}
      headerBusy={headerBusy}
      blockAmountBasisChange={linesDirty}
      onLedgerChange={onLedgerChange}
      onAmountBasisChange={onAmountBasisChange}
    />
  );
}

const PartnerStatementDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const statementPerms = useResourcePermissions(PARTNER_STATEMENT_RESOURCE);
  const paymentApplicationPerms = useResourcePermissions('kuaizhizao:payment-application');
  const purchaseInvoicePerms = useResourcePermissions('kuaicaiwu:purchase-invoice');
  const partnerStatementAuditEnabled = useAuditRequired(PARTNER_STATEMENT_ENTITY, false);
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const printRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<PartnerStatement | null>(null);
  const [localLines, setLocalLines] = useState<PartnerStatementLine[]>([]);
  const [localSummary, setLocalSummary] = useState<{
    opening_balance?: number;
    debit_total?: number;
    credit_total?: number;
    closing_balance?: number;
  } | null>(null);
  const [linesDirty, setLinesDirty] = useState(false);
  const linesDirtyRef = useRef(false);
  linesDirtyRef.current = linesDirty;
  const [savingLines, setSavingLines] = useState(false);
  const [exporting, setExporting] = useState<'xlsx' | 'pdf' | null>(null);
  const [pushingPaymentApp, setPushingPaymentApp] = useState(false);
  const [pushingInvoice, setPushingInvoice] = useState(false);
  const [mergeInvoiceOpen, setMergeInvoiceOpen] = useState(false);
  const [mergeInvoiceSources, setMergeInvoiceSources] = useState<MergeFinanceSourceRow[]>([]);
  const [headerBusy, setHeaderBusy] = useState(false);
  const { cache: lineDetailCache, loadLineDetail, clearCache: clearLineDetailCache } = usePartnerStatementInboundDetail();

  const statusEnum = useMemo(() => buildPartnerStatementStatusEnum(t), [t]);

  const hydrateWorkingLinesFromStatement = useCallback((statement: PartnerStatement) => {
    const opening = Number(
      statement.transaction_details?.summary?.opening_balance ?? statement.opening_balance ?? 0,
    );
    const srcLines = statement.transaction_details?.lines || [];
    const recalc = recalcPartnerStatementLines(opening, srcLines);
    setLocalLines(recalc.lines);
    setLocalSummary({
      opening_balance: opening,
      debit_total: recalc.debitTotal,
      credit_total: recalc.creditTotal,
      closing_balance: recalc.closingBalance,
    });
  }, []);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    clearLineDetailCache();
    try {
      const res = await partnerStatementService.get(Number(id));
      setData(res);
      // 工作中副本唯一由 hydrate 写入；有未保存改数时禁止用接口回包覆盖
      if (!linesDirtyRef.current) {
        hydrateWorkingLinesFromStatement(res);
      }
    } catch (e: any) {
      message.error(e?.message || t('common.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [clearLineDetailCache, hydrateWorkingLinesFromStatement, id, message, t]);

  useEffect(() => {
    if (!id) {
      setData(null);
      setLocalLines([]);
      setLocalSummary(null);
      setLinesDirty(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      clearLineDetailCache();
      try {
        const res = await partnerStatementService.get(Number(id));
        if (cancelled) return;
        setData(res);
        hydrateWorkingLinesFromStatement(res);
        setLinesDirty(false);
      } catch (e: unknown) {
        if (!cancelled) {
          const err = e as { message?: string };
          message.error(err?.message || t('common.loadFailed'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [clearLineDetailCache, hydrateWorkingLinesFromStatement, id, message, t]);

  const reviewEditable =
    !data?.review_status ||
    ['草稿', 'draft', '驳回', '已驳回', 'rejected'].includes(String(data.review_status).trim());
  const linesEditable =
    !!data &&
    (data.status === 'Draft' ||
      data.status === 'Disputed' ||
      (data.status === 'Confirmed' && reviewEditable)) &&
    reviewEditable &&
    statementPerms.canUpdate;

  const handleStatementAmountChange = useCallback(
    (lineKey: string, amount: number) => {
      setLinesDirty(true);
      setLocalLines((prev) => {
        let hit = false;
        const patched = prev.map((ln, idx) => {
          if (previewLineKey(ln, idx) !== lineKey) return ln;
          hit = true;
          return patchLineStatementAmount(ln, amount);
        });
        if (!hit) return prev;
        const opening = Number(
          localSummary?.opening_balance ??
            data?.transaction_details?.summary?.opening_balance ??
            data?.opening_balance ??
            0,
        );
        const recalc = recalcPartnerStatementLines(opening, patched);
        setLocalSummary({
          opening_balance: opening,
          debit_total: recalc.debitTotal,
          credit_total: recalc.creditTotal,
          closing_balance: recalc.closingBalance,
        });
        return recalc.lines;
      });
    },
    [
      data?.opening_balance,
      data?.transaction_details?.summary?.opening_balance,
      localSummary?.opening_balance,
    ],
  );

  const lineKeyFn = useCallback(
    (ln: PartnerStatementLine, idx?: number) => previewLineKey(ln, idx),
    [],
  );

  const lines = localLines;
  const summary = localSummary || {
    opening_balance: data?.opening_balance,
    debit_total: data?.debit_total,
    credit_total: data?.credit_total,
    closing_balance: data?.closing_balance,
  };
  const balanceLabel = useMemo(() => {
    if (data?.transaction_details?.balance_label) {
      return data.transaction_details.balance_label;
    }
    return data?.partner_type === 'Customer'
      ? t(`${PS}.detail.receivableBalance`)
      : t(`${PS}.detail.payableBalance`);
  }, [data, t]);
  const snap = data?.transaction_details?.partner_snapshot || {};

  const { openFinanceVoucherDetail } = useFinanceVoucherDetail();

  const handleDocCodeClick = useCallback(
    (line: PartnerStatementLine) => {
      const target = resolvePartnerStatementVoucherTarget(line);
      if (target) openFinanceVoucherDetail(target);
    },
    [openFinanceVoucherDetail],
  );

  const lineColumns = usePartnerStatementLineColumns({
    t,
    balanceLabel,
    editable: linesEditable,
    onStatementAmountChange: handleStatementAmountChange,
    lineKey: lineKeyFn,
    onDocCodeClick: handleDocCodeClick,
  });

  const handleLedgerPostingModeChange = useCallback(
    (mode: 'immediate' | 'by_invoice') => {
      if (!data) return;
      if (mode === resolveStatementLedgerMode(data)) {
        return;
      }
      void (async () => {
        setHeaderBusy(true);
        try {
          await partnerStatementService.updateHeader(data.id, { ledger_posting_mode: mode });
          message.success(t('common.saveSuccess'));
          await load();
        } catch (e: unknown) {
          const err = e as { message?: string };
          message.error(err.message || t('common.saveFailed'));
        } finally {
          setHeaderBusy(false);
        }
      })();
    },
    [data, load, t],
  );

  const handleAmountBasisChange = useCallback(
    (next: PartnerStatementAmountBasis) => {
      if (!data) return;
      getAntdModal().confirm({
        title: t(`${PS}.detail.refreshPreviewTitle`),
        content: t(`${PS}.detail.refreshPreviewContent`),
        onOk: async () => {
          setHeaderBusy(true);
          try {
            const res = await partnerStatementService.refreshPreview(data.id, { amount_basis: next });
            if (res.warnings.length > 0) {
              message.warning(res.warnings.join('；'));
            } else {
              message.success(t('common.saveSuccess'));
            }
            setData(res.statement);
            hydrateWorkingLinesFromStatement(res.statement);
            setLinesDirty(false);
          } catch (e: unknown) {
            const err = e as { message?: string };
            message.error(err.message || t('common.saveFailed'));
            throw e;
          } finally {
            setHeaderBusy(false);
          }
        },
      });
    },
    [data, hydrateWorkingLinesFromStatement, t],
  );

  const handleSaveLines = async () => {
    if (!data) return;
    setSavingLines(true);
    try {
      await partnerStatementService.updateLines(data.id, buildLineAmountPayload(localLines));
      message.success(t(`${PS}.detail.linesSaved`));
      setLinesDirty(false);
      await load();
    } catch (e: any) {
      message.error(e?.message || t('common.saveFailed'));
    } finally {
      setSavingLines(false);
    }
  };

  const handleDispute = () => {
    if (!data) return;
    let reason = '';
    getAntdModal().confirm({
      title: t(`${PS}.detail.disputeTitle`),
      content: (
        <Input.TextArea
          rows={3}
          placeholder={t(`${PS}.detail.disputePlaceholder`)}
          onChange={(e) => { reason = e.target.value; }}
        />
      ),
      onOk: async () => {
        if (!reason.trim()) {
          message.warning(t(`${PS}.detail.disputeMissing`));
          return Promise.reject();
        }
        await partnerStatementService.dispute(data.id, reason.trim());
        message.success(t(`${PS}.detail.disputeRecorded`));
        load();
      },
    });
  };

  const handleExport = async (format: 'xlsx' | 'pdf') => {
    if (!data) return;
    setExporting(format);
    try {
      const blob = await partnerStatementService.exportFile(data.id, format);
      const ext = format === 'pdf' && blob.type.includes('html') ? 'html' : format;
      downloadBlob(blob, t(`${PS}.detail.exportFilename`, { code: data.statement_code, ext }));
      message.success(t(`${PS}.detail.exportSuccess`));
    } catch (e: any) {
      message.error(e?.message || t('common.exportFailed'));
    } finally {
      setExporting(null);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const canPushDownstream =
    !!data &&
    data.partner_type === 'Supplier' &&
    (data.status === 'Confirmed' || data.status === 'Sent');

  const handlePushPaymentApplication = useCallback(async () => {
    if (!data) return;
    if (data.partner_type !== 'Supplier') {
      message.warning(t(`${PS}.detail.pushSupplierOnly`));
      return;
    }
    if (data.status !== 'Confirmed' && data.status !== 'Sent') {
      message.warning(t(`${PS}.detail.pushNeedConfirmed`));
      return;
    }
    const payableLines = collectPayableStatementLines(localLines);
    if (!payableLines.length) {
      message.warning(t(`${PS}.detail.pushSelectPayable`));
      return;
    }
    setPushingPaymentApp(true);
    try {
      const app = await pullPaymentApplicationFromReconciliation({
        supplierId: data.partner_id,
        items: payableLines.map((ln) => ({
          doc_type: 'payable',
          doc_id: Number(ln.doc_id),
          amount: linePushAmount(ln),
        })),
      });
      message.success(
        t(`${PS}.detail.paymentApplicationCreated`, { code: app.applicationCode || '' }),
      );
      navigate('/apps/kuaizhizao/purchase-management/payment-applications');
    } catch (e: unknown) {
      const err = e as { message?: string };
      message.error(err.message || t(`${PS}.detail.paymentApplicationFailed`));
    } finally {
      setPushingPaymentApp(false);
    }
  }, [data, localLines, navigate, t]);

  const handlePushPurchaseInvoice = useCallback(async () => {
    if (!data) return;
    if (data.partner_type !== 'Supplier') {
      message.warning(t(`${PS}.detail.pushSupplierOnly`));
      return;
    }
    if (data.status !== 'Confirmed' && data.status !== 'Sent') {
      message.warning(t(`${PS}.detail.pushNeedConfirmed`));
      return;
    }
    const invoiceLines = collectStatementInvoiceLines(
      localLines,
      data.partner_type,
      data.ledger_posting_mode,
    );
    if (!invoiceLines.length) {
      message.warning(t(statementInvoiceEmptyMessageKey(data.partner_type, data.ledger_posting_mode)));
      return;
    }
    const byInvoice = data.ledger_posting_mode === 'by_invoice';
    setPushingInvoice(true);
    try {
      const sources: MergeFinanceSourceRow[] = [];
      for (const ln of invoiceLines) {
        const sourceId = Number(ln.doc_id);
        const preview = byInvoice
          ? await purchaseInvoiceService.previewPullFromPurchaseReceipt(sourceId)
          : await purchaseInvoiceService.previewPullFromPayable(sourceId);
        if (preview.has_blocking_issues) {
          continue;
        }
        const pushable = Number(preview.items?.[0]?.max_push_quantity ?? 0);
        const stmtAmt = linePushAmount(ln);
        const amount = Math.min(stmtAmt, pushable > 0 ? pushable : stmtAmt);
        if (!(amount > 0)) continue;
        sources.push({
          id: sourceId,
          code: String(ln.doc_code || sourceId),
          partnerId: Number(data.partner_id),
          partnerName: String(data.partner_name || ''),
          availableAmount: amount,
        });
      }
      if (!sources.length) {
        message.warning(t(`${PS}.detail.purchaseInvoiceNoEligible`));
        return;
      }
      setMergeInvoiceSources(sources);
      setMergeInvoiceOpen(true);
    } catch (e: unknown) {
      const err = e as { message?: string };
      message.error(err.message || t(`${PS}.detail.purchaseInvoiceFailed`));
    } finally {
      setPushingInvoice(false);
    }
  }, [data, localLines, t]);

  const pushMenuItems = useMemo(() => {
    const items: Array<{ key: string; label: string; disabled?: boolean; onClick: () => void }> = [];
    if (paymentApplicationPerms.canCreate) {
      items.push({
        key: 'payment-application',
        label: t(`${PS}.detail.pushPaymentApplication`),
        disabled: pushingPaymentApp,
        onClick: () => void handlePushPaymentApplication(),
      });
    }
    if (purchaseInvoicePerms.canCreate) {
      items.push({
        key: 'purchase-invoice',
        label: t(`${PS}.detail.pushPurchaseInvoice`),
        disabled: pushingInvoice,
        onClick: () => void handlePushPurchaseInvoice(),
      });
    }
    return items;
  }, [
    handlePushPaymentApplication,
    handlePushPurchaseInvoice,
    paymentApplicationPerms.canCreate,
    purchaseInvoicePerms.canCreate,
    pushingInvoice,
    pushingPaymentApp,
    t,
  ]);

  if (!id) return null;

  const statusMeta = data ? statusEnum[data.status as keyof typeof statusEnum] : null;
  const statusColorMap: Record<string, string> = {
    Draft: 'default',
    Confirmed: 'processing',
    Sent: 'success',
    Disputed: 'warning',
  };
  const ledgerModeLabel =
    data?.ledger_posting_mode === 'by_invoice'
      ? t(`${PS}.ledgerPostingMode.byInvoice`)
      : t(`${PS}.ledgerPostingMode.immediate`);
  const amountBasisLabel =
    resolveStatementAmountBasis(data) === 'tax_exclusive'
      ? t(`${PS}.amountBasis.taxExclusive`)
      : t(`${PS}.amountBasis.taxInclusive`);
  const showHeaderSettingReadonly = !linesEditable;

  const headerStatusBadge =
    data &&
    (shouldShowPartnerStatementReviewApprovedBadge(data)
      ? renderDocumentStatusTag(t('reviewStatus.approved'), '已审核')
      : statusMeta ? (
          <MarkerTag color={statusColorMap[data.status] || 'default'}>{statusMeta.text}</MarkerTag>
        ) : null);

  const pageActions = data ? (
    <>
      {headerStatusBadge}
      <Button onClick={() => navigate('/apps/kuaicaiwu/finance-management/partner-statements')}>{t('common.back')}</Button>
      {linesEditable ? (
        <Button loading={savingLines} disabled={!linesDirty} onClick={() => void handleSaveLines()}>
          {t(`${PS}.detail.saveLines`)}
        </Button>
      ) : null}
      {linesEditable && linesDirty ? (
        <Typography.Text type="warning">{t(`${PS}.detail.unsavedLinesHint`)}</Typography.Text>
      ) : null}
      <UniWorkflowActions
        record={data}
        entityType={PARTNER_STATEMENT_ENTITY}
        auditNodeKey={PARTNER_STATEMENT_ENTITY}
        workflowAuditEnabled={partnerStatementAuditEnabled}
        resourcePrefix={PARTNER_STATEMENT_RESOURCE}
        entityName={t(`${PS}.entityName`)}
        statusField="status"
        reviewStatusField="review_status"
        draftStatuses={['草稿', 'draft']}
        pendingStatuses={['待审核']}
        approvedStatuses={['已审核']}
        rejectedStatuses={['已驳回', '驳回']}
        theme="default"
        size="medium"
        beforeAction={async (action) => {
          if (
            (action === 'submit' || action === 'submit_review') &&
            linesDirty
          ) {
            return t(`${PS}.detail.saveLinesBeforeConfirm`);
          }
          return null;
        }}
        onSuccess={() => void load()}
      />
      {canPushDownstream && pushMenuItems.length > 0 ? (
        <Dropdown menu={{ items: pushMenuItems }} trigger={['click']}>
          <Button loading={pushingPaymentApp || pushingInvoice}>
            {t('components.uniPush.push')} <DownOutlined />
          </Button>
        </Dropdown>
      ) : null}
      {(data.status === 'Sent' || data.status === 'Confirmed') && statementPerms.canUpdate ? (
        <Button danger onClick={handleDispute}>{t(`${PS}.detail.recordDispute`)}</Button>
      ) : null}
      {data.sent_channel ? (
        <Typography.Text type="secondary">
          {t(`${PS}.detail.sentAt`, {
            channel: formatSentChannel(data.sent_channel, t),
            time: data.sent_at ? ` - ${formatDateTime(data.sent_at, 'YYYY-MM-DD HH:mm')}` : '',
          })}
        </Typography.Text>
      ) : null}
      {statementPerms.canExport ? (
        <>
          <Button loading={exporting === 'xlsx'} onClick={() => void handleExport('xlsx')}>{t(`${PS}.detail.exportExcel`)}</Button>
          <Button loading={exporting === 'pdf'} onClick={() => void handleExport('pdf')}>{t(`${PS}.detail.exportPdf`)}</Button>
        </>
      ) : null}
      <Button onClick={handlePrint}>{t('common.print')}</Button>
    </>
  ) : null;

  return (
    <div style={uniTabsChildPageVerticalInsetStyle()} className="partner-statement-detail">
      <style>{`
        @media print {
          body * { visibility: hidden; }
          .partner-statement-detail, .partner-statement-detail * { visibility: visible; }
          .partner-statement-detail { position: absolute; left: 0; top: 0; width: 100%; }
          .no-print { display: none !important; }
        }
      `}</style>
      <div style={DOCUMENT_DETAIL_PAGE_HEADER_STYLE} className="no-print">
        <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
          {t(`${PS}.pageTitle`)} {data?.statement_code || ''}
        </Typography.Title>
        {pageActions ? (
          <Space wrap size={8} align="center">
            {pageActions}
          </Space>
        ) : null}
      </div>

      {loading && !data ? (
        <div style={{ padding: 48, textAlign: 'center' }}><Spin size="large" /></div>
      ) : !data ? (
        <Typography.Text type="secondary">{t(`${PS}.detailNotFound`)}</Typography.Text>
      ) : (
        <div ref={printRef}>
          <Typography.Title level={4} style={{ textAlign: 'center', display: 'none' }} className="print-only">
            {t(`${PS}.detail.printTitle`, { company: data.company_name || t(`${PS}.detail.ourCompany`) })}
          </Typography.Title>
          {data && linesEditable ? (
            <PartnerStatementHeaderControls
              data={data}
              editable={linesEditable}
              linesDirty={linesDirty}
              headerBusy={headerBusy}
              onLedgerChange={handleLedgerPostingModeChange}
              onAmountBasisChange={handleAmountBasisChange}
            />
          ) : null}

          <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
            <Descriptions.Item label={t(`${PS}.col.code`)}>{data.statement_code}</Descriptions.Item>
            <Descriptions.Item label={t(`${PS}.col.partner`)}>{data.partner_name}</Descriptions.Item>
            <Descriptions.Item label={t(`${PS}.col.period`)}>
              {data.start_date} ~ {data.end_date}（{data.statement_period}）
            </Descriptions.Item>
            <Descriptions.Item label={t(`${PS}.detail.partnerType`)}>
              {data.partner_type === 'Customer'
                ? t(`${PS}.partnerType.customer`)
                : t(`${PS}.partnerType.supplier`)}
            </Descriptions.Item>
            {showHeaderSettingReadonly ? (
              <Descriptions.Item label={t(`${PS}.ledgerPostingMode`)}>{ledgerModeLabel}</Descriptions.Item>
            ) : null}
            {showHeaderSettingReadonly ? (
              <Descriptions.Item label={t(`${PS}.amountBasis`)}>{amountBasisLabel}</Descriptions.Item>
            ) : null}
            {data.ledger_posted_at ? (
              <Descriptions.Item label={t(`${PS}.detail.ledgerPostedAt`)}>
                {formatDateTime(data.ledger_posted_at, 'YYYY-MM-DD HH:mm')}
              </Descriptions.Item>
            ) : null}
            {(snap as any).finance_contact_name ? (
              <Descriptions.Item label={t(`${PS}.detail.financeContact`)} span={2}>
                {(snap as any).finance_contact_name} {(snap as any).finance_contact_phone || ''}
              </Descriptions.Item>
            ) : null}
            <Descriptions.Item label={t(`${PS}.col.openingBalance`)}>{money(summary?.opening_balance)}</Descriptions.Item>
            <Descriptions.Item label={t(`${PS}.col.closingBalance`)}>{money(summary?.closing_balance)}</Descriptions.Item>
            <Descriptions.Item label={t(`${PS}.col.debitTotal`)}>{money(summary?.debit_total)}</Descriptions.Item>
            <Descriptions.Item label={t(`${PS}.col.creditTotal`)}>{money(summary?.credit_total)}</Descriptions.Item>
            {data.dispute_reason ? (
              <Descriptions.Item label={t(`${PS}.detail.disputeReason`)} span={2}>{data.dispute_reason}</Descriptions.Item>
            ) : null}
            {data.notes ? (
              <Descriptions.Item label={t('common.remark')} span={2}>{data.notes}</Descriptions.Item>
            ) : null}
          </Descriptions>

          <Alert type="info" showIcon title={t(`${PS}.dataSourceNote`)} style={{ marginBottom: 12 }} />
          {linesEditable && linesDirty ? (
            <Alert
              type="warning"
              showIcon
              title={t(`${PS}.detail.unsavedLinesHint`)}
              style={{ marginBottom: 12 }}
            />
          ) : null}

          <Table
            size="small"
            rowKey={previewLineKey}
            pagination={false}
            dataSource={lines}
            scroll={{ x: 1400 }}
            columns={lineColumns}
            expandable={partnerStatementExpandableProps(lineDetailCache, loadLineDetail)}
          />

          <Typography.Paragraph type="secondary" style={{ marginTop: 16, fontSize: 12 }}>
            {t(`${PS}.detail.footer`)}
          </Typography.Paragraph>
        </div>
      )}
      <MergeFinanceDocsModal
        open={mergeInvoiceOpen}
        mode="merge_purchase_invoice"
        sources={mergeInvoiceSources}
        onOpenChange={setMergeInvoiceOpen}
      />
    </div>
  );
};

export default PartnerStatementDetailPage;
