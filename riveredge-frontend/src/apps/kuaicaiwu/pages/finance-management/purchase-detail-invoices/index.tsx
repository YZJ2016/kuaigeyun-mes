/**
 * 采购明细收票列表页（settlement_mode=detail，与汇总「采购发票」分菜单）
 */
import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { rowActionKind, rowActionFillInvoiceNumber } from '../../../../../components/uni-action';
import { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button, Empty, Modal, Form, Row, Col, Input, InputNumber, Table, Typography, theme } from 'antd';

import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { apiRequest, formatApiErrorDetail } from '../../../../../services/api';
import {
  purchaseInvoiceService,
  type PurchaseInvoicePullCandidate,
  type PurchaseInvoicePullPreview,
} from '../../../services/finance/purchase-invoice';
import {
  PurchaseInvoice,
  type PurchaseInvoiceCreateData,
} from '../../../types/finance/purchase-invoice';
import { useNavigate, useLocation } from 'react-router-dom';
import { UniTable } from '../../../../../components/uni-table';
import {
  UniBatchMenuButton,
  type UniBatchMenuItem,
  pickCapability,
  runCapabilityBatchLoop,
  useAuditBatchRunner,
} from '../../../../../components/uni-batch';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { UniLifecycle } from '../../../../../components/uni-lifecycle';
import {
  ListPageTemplate,
  MODAL_CONFIG,
  MODAL_NESTED_ABOVE_PARENT_OFFSET,
  FormModalGridBlock,
  FORM_LAYOUT,
} from '../../../../../components/layout-templates';
import {
  financeColFifth,
  financeColFull,
  financeColHalf,
  financeFormGridProps,
} from '../../../utils/financeFormLayout';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import {
  UniPullQueryModal,
  composePullRowDisabled,
  isPullRowBlockedByPartnerLock,
  resolvePullConfirmNumericIds,
  resolvePullQueryAnchorPartnerKey,
  resolvePullQueryPartnerKey,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import { loadFinancePullCandidatePage } from '../shared/loadFinancePullCandidatePage';
import { getChineseInvoiceLifecycle } from '../../../utils/financeLifecycle';
import {
  canDeletePurchaseInvoice,
  canFillPurchaseInvoiceNumber,
  faceInvoiceNumberForEdit,
  purchaseInvoiceReviewRaw,
} from '../../../utils/purchaseInvoiceUi';
import { isPendingReviewStatus } from '../../../../kuaizhizao/constants/documentStatus';
import {
  ModalForm,
  ProForm,
  ProFormDatePicker,
  ProFormDigit,
  ProFormField,
  ProFormMoney,
  ProFormSelect,
  ProFormSwitch,
  ProFormItem,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import {
  convertInvoiceAmountBetweenModes,
  invoiceExclFromIncl,
  moneyExceedsMax,
  quantizeMoney,
  recalcEnteredAmountOnTaxRateChange,
  resolveInvoiceAmountsForSubmit,
  type InvoiceAmountInputMode,
} from '../../../utils/invoiceAmountInput';
import { TaxRatePercentInput } from '../../../../kuaizhizao/components/document-detail-table/documentDetailTable';
import {
  buildPurchaseDetailItemsFromPullLines,
  initPullReceiptLineSelection,
  pullReceiptDetailLineRowKey,
  pullReceiptSelectedIdsAsRowKeys,
  sumPullReceiptLineAmounts,
  reconcilePullReceiptLinesForHeaderAmount,
  syncPullReceiptLineQuantitiesFromAmounts,
  seedPullReceiptLineInvoiceNumbers,
  applyHeaderInvoiceNumberToPullLines,
  type PullReceiptFinanceDetailLine,
} from '../../../../kuaizhizao/utils/pullReceiptFinanceLines';
import {
  FINANCE_PULL_PREVIEW_DETAIL_BETWEEN_FORM_CLASS,
  FINANCE_PULL_PREVIEW_DETAIL_TABLE_CLASS,
  FINANCE_PULL_PREVIEW_DETAIL_TITLE_CLASS,
  FINANCE_PULL_PREVIEW_FORM_CLASS,
} from '../shared/financePullPreviewLayout';
import '../shared/financePullPreview.less';
import { buildPurchaseDetailInvoicePullLineColumns } from '../shared/purchaseDetailInvoicePullLineColumns';
import { FinanceInvoiceSettlementModeAlert } from '../shared/FinanceInvoiceSettlementModeAlert';
import dayjs from 'dayjs';
import { buildKuaicaiwuPullCreateMenuItems, getKuaicaiwuDocumentAction } from '../../../constants/documentActionRegistry';
import DocumentAttachmentsField from '../../../../kuaizhizao/components/DocumentAttachmentsField';
import { mapAttachmentsToUploadList, normalizeDocumentAttachments } from '../../../../kuaizhizao/utils/documentAttachments';
import { getStatusDisplay } from '../../../../kuaizhizao/constants/documentStatus';
import {
  assertBankAccountForPaymentMethod,
  BANK_TRANSFER_PAYMENT_METHOD,
  buildReviewStatusEnum,
  getChineseInvoiceTypeOptions,
  getPaymentMethodOptions,
} from '../../../utils/financeSharedOptions';
import {
  LedgerAccountFormFields,
  resolveLedgerAccountNote,
} from '../../../components/LedgerAccountFormFields';
import { bankAccountService, type BankAccount } from '../../../services/finance/bank-account';
import { purchaseInvoiceCapabilityReasonMessage } from '../../../utils/purchaseInvoiceCapabilityMessages';
import { formatDateTime, formatCurrencyAmount, formatAmount, formatQuantity } from '../../../../../utils/format';
import {
  FINANCE_INVOICE_PINNED_REVIEW_FIELD,
  financeDocCodePartnerSearchColumns,
  financeDocCreatedUpdatedColumns,
  financeInvoiceNumberSearchColumn,
  resolvePurchaseInvoiceListParams,
} from '../../../utils/financeListCore';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import type { PurchaseInvoiceListParams } from '../../../types/finance/purchase-invoice';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { createListAuditPhaseColumn } from '../../../../kuaizhizao/pages/sales-management/shared/listAuditPhaseColumn';
import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import {
  PurchaseDepartmentFormField,
  resolvePurchaseDepartmentFromApplicant,
  resolvePurchaseDepartmentPayload,
  usePurchaseDepartmentOptions,
} from '../../../../kuaizhizao/pages/purchase-management/shared/PurchaseDepartmentFormField';
import {
  fetchPurchaseInvoicePartnerStatementPullPreview,
  fetchPurchaseInvoicePullPreview,
  resolvePurchaseInvoicePullPreviewCap,
  type PurchaseInvoicePullPreviewKind,
} from '../shared/purchaseInvoicePullPreviewKernel';

const P = 'app.kuaicaiwu.purchaseInvoice';
const PAGE = 'app.kuaicaiwu.purchaseDetailInvoice';
const DETAIL_LIST_BASE = '/apps/kuaicaiwu/finance-management/purchase-detail-invoices';

const formatPullMoney = (value: number) => formatCurrencyAmount(value || 0);

function resolveApiErrorMessage(error: unknown, fallback: string): string {
  const err = error as { response?: { data?: { detail?: unknown } }; message?: string };
  return (
    formatApiErrorDetail(err?.response?.data?.detail)
    || err?.message
    || fallback
  );
}
const PURCHASE_INVOICE_RESOURCE = 'kuaicaiwu:purchase-invoice';

const TAX_RATE_OPTIONS = [
  { label: '13%', value: 13 },
  { label: '9%', value: 9 },
  { label: '6%', value: 6 },
  { label: '1%', value: 1 },
  { label: '0%', value: 0 },
];

type PullPreviewKind = PurchaseInvoicePullPreviewKind;

const PurchaseInvoiceList: React.FC = () => {
  const actionRef = useRef<ActionType>();
  const lastListParamsRef = useRef<Record<string, string | number | boolean | undefined>>({});
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editVisible, setEditVisible] = useState(false);
  const [editingRecord, setEditingRecord] = useState<PurchaseInvoice | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [pullSubmitting, setPullSubmitting] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [tableRows, setTableRows] = useState<PurchaseInvoice[]>([]);
  const [pullPreviewOpen, setPullPreviewOpen] = useState(false);
  const [pullPreviewLoading, setPullPreviewLoading] = useState(false);
  const [pullPreviewData, setPullPreviewData] = useState<PurchaseInvoicePullPreview | null>(null);
  const [pullPreviewSourceIds, setPullPreviewSourceIds] = useState<number[]>([]);
  const [pullPreviewKind, setPullPreviewKind] = useState<PullPreviewKind | null>(null);
  const [pullReceiptSelectedIds, setPullReceiptSelectedIds] = useState<number[]>([]);
  const [pullReceiptLineAmounts, setPullReceiptLineAmounts] = useState<Record<number, number>>({});
  const [pullReceiptLineQuantities, setPullReceiptLineQuantities] = useState<Record<number, number>>({});
  const [pullReceiptLineInvoiceNumbers, setPullReceiptLineInvoiceNumbers] = useState<Record<number, string>>({});
  const [pullForm] = Form.useForm();
  const [createForm] = Form.useForm();
  const pullAmountModeRef = useRef<InvoiceAmountInputMode>('tax_inclusive');
  const pullTaxRateRef = useRef<number>(13);
  const createAmountModeRef = useRef<InvoiceAmountInputMode>('tax_inclusive');
  const createTaxRateRef = useRef<number>(13);
  /** 拉单带入含税金额 A（优惠前），用于 I=A-D */
  const pullBroughtAmountRef = useRef<number>(0);
  const pullHeaderInvoiceNumberRef = useRef<string>('');
  const pullFromPurchaseOrderCloseRef = useRef<(() => void) | null>(null);
  const pullFromPurchaseOrderOpenRef = useRef<(() => void) | null>(null);
  const pullFromPurchaseReceiptCloseRef = useRef<(() => void) | null>(null);
  const pullFromPurchaseReceiptOpenRef = useRef<(() => void) | null>(null);
  const pullFromPayableCloseRef = useRef<(() => void) | null>(null);
  const pullFromPayableOpenRef = useRef<(() => void) | null>(null);
  const pullFromPartnerStatementCloseRef = useRef<(() => void) | null>(null);
  const pullFromPartnerStatementOpenRef = useRef<(() => void) | null>(null);
  const pullPartnerStatementIdsRef = useRef<number[]>([]);
  const pullPartnerStatementCodesRef = useRef<string[]>([]);
  const pullApplicantDepartmentUuidRef = useRef<string | undefined>(undefined);
  const [supplierOptions, setSupplierOptions] = useState<{ label: string; value: number }[]>([]);
  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const { message: messageApi } = App.useApp();
  const { token } = theme.useToken();
  const { t } = useTranslation();
  const pullQueryModalZIndex = token.zIndexPopupBase + MODAL_NESTED_ABOVE_PARENT_OFFSET;
  const pullPreviewZIndex = pullQueryModalZIndex + MODAL_NESTED_ABOVE_PARENT_OFFSET;

  const showPullFlowNotice = useCallback(
    (kind: 'warning' | 'error', content: string, title?: string) => {
      const resolvedTitle =
        title ?? (kind === 'error' ? t('common.operationFailed') : t('common.hint'));
      const modalProps = {
        title: resolvedTitle,
        content,
        centered: true,
        zIndex: pullQueryModalZIndex + 100,
      };
      if (kind === 'error') {
        Modal.error(modalProps);
      } else {
        Modal.warning(modalProps);
      }
      messageApi.open({ type: kind, content, duration: 6 });
    },
    [messageApi, pullQueryModalZIndex, t],
  );
  const navigate = useNavigate();
  const location = useLocation();
  const invoiceTypeOptions = useMemo(
    () => getChineseInvoiceTypeOptions(t, { includeOther: true, includeReceipt: false }),
    [t],
  );
  const paymentMethodOptions = useMemo(() => getPaymentMethodOptions(t), [t]);
  const currentUser = useCurrentUser();
  const {
    options: departmentOptions,
    loading: departmentOptionsLoading,
    resolveName: resolveDepartmentName,
  } = usePurchaseDepartmentOptions();
  const ledgerPostingModeOptions = useMemo(
    () => [
      {
        label: t('app.kuaicaiwu.partnerStatement.ledgerPostingMode.immediate'),
        value: 'immediate',
      },
      {
        label: t('app.kuaicaiwu.partnerStatement.ledgerPostingMode.byInvoice'),
        value: 'by_invoice',
      },
    ],
    [t],
  );
  const pullFromPurchaseOrderAction = getKuaicaiwuDocumentAction('purchase_invoice.pull_from_purchase_order');
  const pullFromPurchaseReceiptAction = getKuaicaiwuDocumentAction('purchase_invoice.pull_from_purchase_receipt');
  const pullFromPayableAction = getKuaicaiwuDocumentAction('purchase_invoice.pull_from_payable');
  const pullFromPartnerStatementAction = getKuaicaiwuDocumentAction('purchase_invoice.pull_from_partner_statement');

  const purchaseInvoiceAuditEnabled = useAuditRequired('purchase_invoice', false);
  const purchaseInvoiceAuditColumn = useMemo(
    () => createListAuditPhaseColumn<PurchaseInvoice>({ t, auditEnabled: purchaseInvoiceAuditEnabled }),
    [t, purchaseInvoiceAuditEnabled],
  );
  const purchaseInvoicePerms = useResourcePermissions(PURCHASE_INVOICE_RESOURCE);
  const paymentPerms = useResourcePermissions('kuaicaiwu:payment');
  const concurrentPaymentEnabled = Form.useWatch('concurrent_payment_enabled', pullForm);
  const canConcurrentPayment =
    pullPreviewKind === 'payable'
    && pullPreviewSourceIds.length === 1
    && paymentPerms.canCreate
    && Number(pullPreviewData?.remaining_settle_amount ?? 0) > 0;
  const pullReceiptLineSelectEnabled = useMemo(
    () =>
      (
        pullPreviewKind === 'purchase_receipt'
        || pullPreviewKind === 'payable'
        || pullPreviewKind === 'purchase_order'
        || pullPreviewKind === 'outsource_order_receipt'
      )
      && (pullPreviewData?.detail_lines?.length ?? 0) > 0,
    [pullPreviewKind, pullPreviewData],
  );
  const selectedRecordsForBatch = useMemo(
    () => tableRows.filter((row) => row.id != null && selectedRowKeys.includes(row.id)),
    [tableRows, selectedRowKeys],
  );
  const handlePurchaseInvoiceAuditBatchSuccess = () => {
    setSelectedRowKeys([]);
    actionRef.current?.reload();
  };
  const {
    runAction: runPurchaseInvoiceAuditBatch,
    auditModal: purchaseInvoiceAuditModal,
  } = useAuditBatchRunner<PurchaseInvoice>({
    permGates: purchaseInvoicePerms,
    handlers: {
      approve: (id) => purchaseInvoiceService.approvePurchaseInvoice(id),
      revoke: (id) => purchaseInvoiceService.revokePurchaseInvoice(id),
      withdraw: (id) => purchaseInvoiceService.withdrawPurchaseInvoice(id),
    },
    onBatchComplete: handlePurchaseInvoiceAuditBatchSuccess,
    auditEntity: {
      entityType: 'purchase_invoice',
      entityName: t(`${P}.entityName`),
    },
  });
  const purchaseInvoiceToolbarAuditMenus = useMemo(() => {
    const reviewOf = (row: PurchaseInvoice) => purchaseInvoiceReviewRaw(row);
    const allowed = (row: PurchaseInvoice, key: string) => pickCapability(row, key)?.allowed === true;
    const run = (
      records: PurchaseInvoice[],
      capabilityKey: string,
      permAllowed: boolean,
      onRun: (id: number) => Promise<unknown>,
      notAllowedMessage?: string,
    ) =>
      runCapabilityBatchLoop({
        keys: records.map((row) => Number(row.id)),
        records,
        capabilityKey,
        permAllowed,
        notAllowedMessage,
        onRun,
        onSuccess: handlePurchaseInvoiceAuditBatchSuccess,
        message: messageApi,
        t,
      });
    const submitRows = selectedRecordsForBatch.filter((row) => allowed(row, 'submit'));
    const committedRows = selectedRecordsForBatch.filter(
      (row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'withdraw_submit'),
    );
    const pendingRows = selectedRecordsForBatch.filter((row) => {
      const review = reviewOf(row);
      return review !== 'SUBMITTED' && isPendingReviewStatus(review) && allowed(row, 'withdraw_submit');
    });
    const reviewRows = selectedRecordsForBatch.filter((row) => allowed(row, 'submit_review'));
    const approveRows = selectedRecordsForBatch.filter(
      (row) => reviewOf(row) !== 'SUBMITTED' && isPendingReviewStatus(reviewOf(row)) && allowed(row, 'approve'),
    );
    const revokeRows = selectedRecordsForBatch.filter((row) => allowed(row, 'revoke_approval'));
    const canSubmit = purchaseInvoicePerms.canAction?.('submit') ?? false;
    const canApprove =
      (purchaseInvoicePerms.canAction?.('approve') ?? false)
      || (purchaseInvoicePerms.canAction?.('audit') ?? false);
    const canRevoke = purchaseInvoicePerms.canAction?.('revoke') ?? false;
    const hasSelection = selectedRecordsForBatch.length > 0;
    const submitDisabled = hasSelection && !(canSubmit && submitRows.length > 0);
    const submitItems: UniBatchMenuItem[] = [
      {
        key: 'submit',
        label: t('common.submit'),
        disabled: submitDisabled,
        onClick: () =>
          run(submitRows, 'submit', canSubmit, (id) => purchaseInvoiceService.commitPurchaseInvoice(id)),
      },
      {
        key: 'withdraw-submit',
        label: t(`${P}.toolbar.withdrawSubmit`),
        disabled: hasSelection && committedRows.length === 0,
        onClick: () =>
          run(
            committedRows,
            'withdraw_submit',
            canSubmit,
            (id) => purchaseInvoiceService.withdrawPurchaseInvoice(id),
          ),
      },
      {
        key: 'submit-review',
        label: t(`${P}.toolbar.submitReview`),
        disabled: hasSelection && !(canSubmit && reviewRows.length > 0),
        onClick: () =>
          run(
            reviewRows,
            'submit_review',
            canSubmit,
            (id) => purchaseInvoiceService.submitPurchaseInvoiceForReview(id),
            t(`${P}.toolbar.submitReviewNotAllowed`),
          ),
      },
    ];
    const documentCommitAndSubmitReview = {
      disabled: submitDisabled,
      commitRecords: submitRows,
      permAllowed: canSubmit,
      commit: (id: number) => purchaseInvoiceService.commitPurchaseInvoice(id),
      submitReview: (id: number) => purchaseInvoiceService.submitPurchaseInvoiceForReview(id),
      onSuccess: handlePurchaseInvoiceAuditBatchSuccess,
    };
    const auditItems: UniBatchMenuItem[] = [
      {
        key: 'approve',
        label: t('components.uniAction.audit'),
        disabled: hasSelection && !(canApprove && approveRows.length > 0),
        onClick: () =>
          void runPurchaseInvoiceAuditBatch(
            'approve',
            approveRows.map((row) => Number(row.id)),
            approveRows,
            purchaseInvoiceAuditEnabled,
          ),
      },
      {
        key: 'withdraw-review',
        label: t(`${P}.toolbar.withdrawReview`),
        disabled: hasSelection && pendingRows.length === 0,
        onClick: () =>
          run(
            pendingRows,
            'withdraw_submit',
            canSubmit,
            (id) => purchaseInvoiceService.withdrawPurchaseInvoice(id),
          ),
      },
      {
        key: 'revoke',
        label: t(`${P}.toolbar.revoke`),
        disabled: hasSelection && !(canRevoke && revokeRows.length > 0),
        onClick: () =>
          run(
            revokeRows,
            'revoke_approval',
            canRevoke,
            (id) => purchaseInvoiceService.revokePurchaseInvoice(id),
          ),
      },
    ];
    return { submitItems, auditItems, documentCommitAndSubmitReview };
  }, [
    messageApi,
    purchaseInvoicePerms,
    purchaseInvoiceAuditEnabled,
    runPurchaseInvoiceAuditBatch,
    selectedRecordsForBatch,
    t,
  ]);

  const executeDelete = async (record: PurchaseInvoice) => {
    try {
      await purchaseInvoiceService.delete(Number(record.id));
      messageApi.success(t('common.deleteSuccess'));
      actionRef.current?.reload();
    } catch (e: unknown) {
      messageApi.error(resolveApiErrorMessage(e, t('common.operationFailed')));
    }
  };

  const openEditModal = (record: PurchaseInvoice) => {
    setEditingRecord(record);
    setEditVisible(true);
  };

  const handleEditSubmit = async (values: {
    invoice_number?: string;
    invoice_date?: unknown;
    attachments?: unknown;
  }) => {
    if (!editingRecord?.id) return false;
    setEditSubmitting(true);
    try {
      const updateData: {
        invoice_number: string;
        invoice_date?: string;
        attachments: ReturnType<typeof normalizeDocumentAttachments>;
      } = {
        invoice_number: String(values.invoice_number ?? '').trim(),
        attachments: normalizeDocumentAttachments(values.attachments),
      };
      if (!['已审核', '已开票'].includes(String(editingRecord.status ?? '').trim())) {
        updateData.invoice_date = formatDateTime(
          values.invoice_date || editingRecord.invoice_date || dayjs(),
          'YYYY-MM-DD',
        );
      }
      await purchaseInvoiceService.update(Number(editingRecord.id), updateData);
      messageApi.success(t(`${P}.editNumberSuccess`));
      setEditVisible(false);
      setEditingRecord(null);
      actionRef.current?.reload();
      return true;
    } catch (e: unknown) {
      messageApi.error(resolveApiErrorMessage(e, t('common.saveFailed')));
      return false;
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleBatchDelete = async (keys: React.Key[]) => {
    try {
      for (const id of keys) {
        await purchaseInvoiceService.delete(Number(id));
      }
      messageApi.success(t(`${P}.batchDeleteSuccess`, { count: keys.length }));
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    } catch (error: unknown) {
      messageApi.error(resolveApiErrorMessage(error, t('common.batchDeleteFailed')));
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiRequest<unknown>('/apps/master-data/supply-chain/suppliers', {
          params: { limit: 1000, is_active: true },
        });
        const list = Array.isArray(res) ? res : (res as any)?.data ?? (res as any)?.items ?? [];
        setSupplierOptions(
          (Array.isArray(list) ? list : []).map((s: any) => ({
            label: s.name || s.supplier_name || s.code || String(s.id),
            value: s.id,
          })),
        );
      } catch {
        setSupplierOptions([]);
      }
    };
    load();
    bankAccountService
      .list({ limit: 200, is_active: true })
      .then((res) => setBankAccounts(res.data))
      .catch(() => setBankAccounts([]));
  }, []);

  const handleRegister = async (_values: any) => {
    messageApi.warning(t(`${P}.detailRegisterFromSourceOnly`));
    return false;
  };

  const resetPullPreview = () => {
    setPullPreviewOpen(false);
    setPullPreviewSourceIds([]);
    setPullPreviewData(null);
    setPullPreviewKind(null);
    setPullReceiptSelectedIds([]);
    setPullReceiptLineAmounts({});
    setPullReceiptLineQuantities({});
    setPullReceiptLineInvoiceNumbers({});
    pullHeaderInvoiceNumberRef.current = '';
    pullForm.resetFields();
  };

  const syncPullReceiptSumToInvoiceForm = useCallback(
    (sumIncl: number) => {
      if (sumIncl <= 0) return;
      const taxRate = Number(pullForm.getFieldValue('tax_rate') ?? pullTaxRateRef.current ?? 13);
      const mode = (pullForm.getFieldValue('amount_input_mode') || pullAmountModeRef.current) as InvoiceAmountInputMode;
      const discount = Number(pullForm.getFieldValue('discount_amount')) || 0;
      pullBroughtAmountRef.current = sumIncl + discount;
    if (mode === 'tax_inclusive') {
        pullForm.setFieldsValue({ invoice_amount: sumIncl });
      } else {
        pullForm.setFieldsValue({ invoice_amount: invoiceExclFromIncl(sumIncl, taxRate) });
      }
    },
    [pullForm],
  );

  const openPullPreview = async (
    kind: PullPreviewKind,
    sourceIdsInput: number | number[],
    options?: {
      closeSourceModal?: () => void;
      reopenSourceModal?: () => void;
      /** 从往来对账单加载时传入，用于放行月结入库阻断 */
      partnerStatementIds?: number[];
      partnerStatementCodes?: string[];
    },
  ) => {
    pullPartnerStatementIdsRef.current = options?.partnerStatementIds?.length
      ? [...options.partnerStatementIds]
      : [];
    pullPartnerStatementCodesRef.current = options?.partnerStatementCodes?.length
      ? [...options.partnerStatementCodes]
      : [];
    const sourceIds = (Array.isArray(sourceIdsInput) ? sourceIdsInput : [sourceIdsInput])
      .map((id) => Number(id))
      .filter((id) => Number.isFinite(id) && id > 0);
    if (!sourceIds.length) {
      const sourceLabel =
        kind === 'purchase_order'
          ? pullFromPurchaseOrderAction.sourceLabel
          : kind === 'purchase_receipt' || kind === 'outsource_order_receipt'
            ? pullFromPurchaseReceiptAction.sourceLabel
            : pullFromPayableAction.sourceLabel;
      showPullFlowNotice('warning', t(`${P}.selectSource`, { label: sourceLabel }));
      return;
    }
    // 预览成功后再关取单窗；失败时保留取单窗并提示，避免关窗后又重开像「按钮无反应」
    setPullPreviewKind(kind);
    setPullPreviewOpen(false);
    setPullPreviewLoading(true);
    setPullPreviewData(null);
    setPullPreviewSourceIds(sourceIds);
    const hideLoading = messageApi.loading(t(`${P}.pullPreviewLoading`), 0);
    try {
      const data = await fetchPurchaseInvoicePullPreview(
        kind,
        sourceIds,
        pullPartnerStatementIdsRef.current,
      );
      if (data.has_blocking_issues) {
        const blockedText =
          purchaseInvoiceCapabilityReasonMessage(data.blocking_reason, t)
          || (data.summary ? String(data.summary) : '')
          || t(`${P}.pullPreviewBlocked`);
        showPullFlowNotice('warning', blockedText, t(`${P}.pullPreviewBlocked`));
        resetPullPreview();
        return;
      }
      const maxPush = resolvePurchaseInvoicePullPreviewCap(data);
      if (maxPush <= 0) {
        const noAmtText = (data.summary ? String(data.summary) : '') || t(`${P}.pullNoInvoiceableAmount`);
        showPullFlowNotice('warning', noAmtText, t(`${P}.pullNoInvoiceableAmount`));
        resetPullPreview();
        return;
      }
      options?.closeSourceModal?.();
      setPullPreviewData(data);
      setPullPreviewOpen(true);
    } catch (e: unknown) {
      showPullFlowNotice('error', resolveApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
      resetPullPreview();
    } finally {
      hideLoading();
      setPullPreviewLoading(false);
    }
  };

  const isPullPurchaseInvoiceSelectable = useCallback(
    (record: PurchaseInvoicePullCandidate) =>
      record.capabilities?.pull_purchase_invoice?.allowed === true,
    [],
  );

  const basePullPurchaseInvoiceRowDisabled = useCallback(
    (record: PurchaseInvoicePullCandidate) => !isPullPurchaseInvoiceSelectable(record),
    [isPullPurchaseInvoiceSelectable],
  );

  const pullQueryScopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const pullFromPurchaseOrderQuery = useUniPullQuery<PurchaseInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: basePullPurchaseInvoiceRowDisabled,
    loadData: async (params) => {
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          isPullPurchaseInvoiceSelectable,
          (api) => purchaseInvoiceService.listPurchaseOrderPullCandidates(api),
        );
      } catch (e: any) {
        messageApi.error(
          e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t(`${P}.loadSourceFailed`),
        );
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selectedIds = resolvePullConfirmNumericIds(keys, rows, 'id');
      if (!selectedIds.length) {
        showPullFlowNotice(
          'warning',
          t(`${P}.selectSource`, { label: pullFromPurchaseOrderAction.sourceLabel }),
        );
        return;
      }
      const selectedIdSet = new Set(selectedIds);
      const partnerKeys = new Set(
        rows
          .filter((x) => selectedIdSet.has(Number(x.id)))
          .map((x) => resolvePullQueryPartnerKey(x))
          .filter(Boolean),
      );
      if (partnerKeys.size > 1) {
        showPullFlowNotice('warning', t(`${P}.pull.sameSupplierRequired`));
        return;
      }
      await openPullPreview('purchase_order', selectedIds, {
        closeSourceModal: () => pullFromPurchaseOrderCloseRef.current?.(),
        reopenSourceModal: () => pullFromPurchaseOrderOpenRef.current?.(),
      });
    },
    onConfirmFailed: (error) => {
      showPullFlowNotice('error', resolveApiErrorMessage(error, t(`${P}.loadSourceFailed`)));
    },
  });
  pullFromPurchaseOrderCloseRef.current = pullFromPurchaseOrderQuery.closeModal;
  pullFromPurchaseOrderOpenRef.current = pullFromPurchaseOrderQuery.openModal;

  const orderPullRowDisabled = useCallback(
    (record: PurchaseInvoicePullCandidate) =>
      composePullRowDisabled(record, {
        baseDisabled: basePullPurchaseInvoiceRowDisabled,
        selectedRows: pullFromPurchaseOrderQuery.selectedRows,
      }),
    [basePullPurchaseInvoiceRowDisabled, pullFromPurchaseOrderQuery.selectedRows],
  );

  const warnOrderPullDisabledRow = useCallback(
    (record: PurchaseInvoicePullCandidate) => {
      const anchor = resolvePullQueryAnchorPartnerKey(pullFromPurchaseOrderQuery.selectedRows);
      if (
        !basePullPurchaseInvoiceRowDisabled(record)
        && anchor
        && isPullRowBlockedByPartnerLock(record, anchor)
      ) {
        messageApi.warning(t(`${P}.pull.sameSupplierRequired`));
        return;
      }
      messageApi.warning(
        purchaseInvoiceCapabilityReasonMessage(
          record.capabilities?.pull_purchase_invoice?.reason,
          t,
        ) || t(`${P}.pullPreviewBlocked`),
      );
    },
    [
      basePullPurchaseInvoiceRowDisabled,
      messageApi,
      pullFromPurchaseOrderQuery.selectedRows,
      t,
    ],
  );

  const pullFromPurchaseReceiptQuery = useUniPullQuery<PurchaseInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: basePullPurchaseInvoiceRowDisabled,
    loadData: async (params) => {
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          isPullPurchaseInvoiceSelectable,
          (api) => purchaseInvoiceService.listPurchaseReceiptPullCandidates(api),
        );
      } catch (e: any) {
        messageApi.error(
          e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t(`${P}.loadSourceFailed`),
        );
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selectedIds = resolvePullConfirmNumericIds(keys, rows, 'id');
      if (!selectedIds.length) {
        messageApi.warning(t(`${P}.selectSource`, { label: pullFromPurchaseReceiptAction.sourceLabel }));
        return;
      }
      const selectedIdSet = new Set(selectedIds);
      const partnerKeys = new Set(
        rows
          .filter((x) => selectedIdSet.has(Number(x.id)))
          .map((x) => resolvePullQueryPartnerKey(x))
          .filter(Boolean),
      );
      if (partnerKeys.size > 1) {
        messageApi.warning(t(`${P}.pull.sameSupplierRequired`));
        return;
      }
      await openPullPreview('purchase_receipt', selectedIds, {
        closeSourceModal: () => pullFromPurchaseReceiptCloseRef.current?.(),
        reopenSourceModal: () => pullFromPurchaseReceiptOpenRef.current?.(),
      });
    },
  });
  pullFromPurchaseReceiptCloseRef.current = pullFromPurchaseReceiptQuery.closeModal;
  pullFromPurchaseReceiptOpenRef.current = pullFromPurchaseReceiptQuery.openModal;

  const receiptPullRowDisabled = useCallback(
    (record: PurchaseInvoicePullCandidate) =>
      composePullRowDisabled(record, {
        baseDisabled: basePullPurchaseInvoiceRowDisabled,
        selectedRows: pullFromPurchaseReceiptQuery.selectedRows,
      }),
    [basePullPurchaseInvoiceRowDisabled, pullFromPurchaseReceiptQuery.selectedRows],
  );

  const warnReceiptPullDisabledRow = useCallback(
    (record: PurchaseInvoicePullCandidate) => {
      const anchor = resolvePullQueryAnchorPartnerKey(pullFromPurchaseReceiptQuery.selectedRows);
      if (
        !basePullPurchaseInvoiceRowDisabled(record)
        && anchor
        && isPullRowBlockedByPartnerLock(record, anchor)
      ) {
        messageApi.warning(t(`${P}.pull.sameSupplierRequired`));
        return;
      }
      messageApi.warning(
        purchaseInvoiceCapabilityReasonMessage(
          record.capabilities?.pull_purchase_invoice?.reason,
          t,
        ) || t(`${P}.pullPreviewBlocked`),
      );
    },
    [
      basePullPurchaseInvoiceRowDisabled,
      messageApi,
      pullFromPurchaseReceiptQuery.selectedRows,
      t,
    ],
  );

  const pullFromPayableQuery = useUniPullQuery<PurchaseInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => !isPullPurchaseInvoiceSelectable(record),
    loadData: async (params) => {
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          isPullPurchaseInvoiceSelectable,
          (api) => purchaseInvoiceService.listPayablePullCandidates(api),
        );
      } catch (e: any) {
        messageApi.error(
          e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t(`${P}.loadSourceFailed`),
        );
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selectedIds = resolvePullConfirmNumericIds(keys, rows, 'id');
      if (!selectedIds.length) {
        messageApi.warning(t(`${P}.selectSource`, { label: pullFromPayableAction.sourceLabel }));
        return;
      }
      const selectedIdSet = new Set(selectedIds);
      const partnerKeys = new Set(
        rows
          .filter((x) => selectedIdSet.has(Number(x.id)))
          .map((x) => resolvePullQueryPartnerKey(x))
          .filter(Boolean),
      );
      if (partnerKeys.size > 1) {
        messageApi.warning(t('app.kuaicaiwu.mergeFinance.sameSupplierRequired'));
        return;
      }
      await openPullPreview('payable', selectedIds, {
        closeSourceModal: () => pullFromPayableCloseRef.current?.(),
        reopenSourceModal: () => pullFromPayableOpenRef.current?.(),
      });
    },
  });
  pullFromPayableCloseRef.current = pullFromPayableQuery.closeModal;
  pullFromPayableOpenRef.current = pullFromPayableQuery.openModal;

  const pullFromPartnerStatementQuery = useUniPullQuery<PurchaseInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => !isPullPurchaseInvoiceSelectable(record),
    loadData: async (params) => {
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          isPullPurchaseInvoiceSelectable,
          (api) => purchaseInvoiceService.listPartnerStatementPullCandidates(api),
        );
      } catch (e: any) {
        messageApi.error(
          e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t(`${P}.loadSourceFailed`),
        );
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selectedIds = resolvePullConfirmNumericIds(keys, rows, 'id');
      if (!selectedIds.length) {
        messageApi.warning(t(`${P}.selectSource`, { label: pullFromPartnerStatementAction.sourceLabel }));
        return;
      }
      const selectedIdSet = new Set(selectedIds);
      const selected = rows.filter((x) => selectedIdSet.has(Number(x.id)));
      const partnerKeys = new Set(
        selected.map((x) => resolvePullQueryPartnerKey(x)).filter(Boolean),
      );
      if (partnerKeys.size > 1) {
        messageApi.warning(t(`${P}.pull.sameSupplierRequired`));
        return;
      }
      const ledgerModes = new Set(
        selected.map((x) => (x.ledger_posting_mode === 'by_invoice' ? 'by_invoice' : 'immediate')),
      );
      if (ledgerModes.size > 1) {
        messageApi.warning(t(`${P}.pull.partnerStatementSameLedgerModeRequired`));
        return;
      }
      const mode = ledgerModes.values().next().value as 'by_invoice' | 'immediate';
      if (mode === 'by_invoice') {
        const receiptIds = Array.from(
          new Set(
            selected.flatMap((row) =>
              (row.receipt_ids || []).map((id) => Number(id)).filter((id) => id > 0),
            ),
          ),
        );
        const outsourceReceiptIds = Array.from(
          new Set(
            selected.flatMap((row) =>
              (row.outsource_order_receipt_ids || [])
                .map((id) => Number(id))
                .filter((id) => id > 0),
            ),
          ),
        );
        if (!receiptIds.length && !outsourceReceiptIds.length) {
          messageApi.warning(t('app.kuaicaiwu.partnerStatement.detail.pushSelectInvoiceSource'));
          return;
        }
        const partnerStatementCodes = selected
          .map((row) => String(row.statement_code || row.doc_code || '').trim())
          .filter(Boolean);
        const openOpts = {
          closeSourceModal: () => pullFromPartnerStatementCloseRef.current?.(),
          reopenSourceModal: () => pullFromPartnerStatementOpenRef.current?.(),
          partnerStatementIds: selectedIds,
          partnerStatementCodes,
        };
        if (receiptIds.length && outsourceReceiptIds.length) {
          setPullPreviewKind('purchase_receipt');
          setPullPreviewOpen(false);
          setPullPreviewLoading(true);
          setPullPreviewData(null);
          const allIds = [...receiptIds, ...outsourceReceiptIds];
          setPullPreviewSourceIds(allIds);
          pullPartnerStatementIdsRef.current = [...selectedIds];
          pullPartnerStatementCodesRef.current = partnerStatementCodes;
          const hideLoading = messageApi.loading(t(`${P}.pullPreviewLoading`), 0);
          try {
            const data = await fetchPurchaseInvoicePartnerStatementPullPreview({
              receiptIds,
              outsourceOrderReceiptIds: outsourceReceiptIds,
              partnerStatementIds: selectedIds,
            });
            if (data.has_blocking_issues) {
              const blockedText =
                purchaseInvoiceCapabilityReasonMessage(data.blocking_reason, t)
                || (data.summary ? String(data.summary) : '')
                || t(`${P}.pullPreviewBlocked`);
              showPullFlowNotice('warning', blockedText, t(`${P}.pullPreviewBlocked`));
              resetPullPreview();
              return;
            }
            const maxPush = resolvePurchaseInvoicePullPreviewCap(data);
            if (maxPush <= 0) {
              showPullFlowNotice('warning', t(`${P}.pullNoInvoiceableAmount`));
              resetPullPreview();
              return;
            }
            openOpts.closeSourceModal?.();
            setPullPreviewData(data);
            setPullPreviewOpen(true);
          } catch (e: unknown) {
            showPullFlowNotice('error', resolveApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
            resetPullPreview();
          } finally {
            hideLoading();
            setPullPreviewLoading(false);
          }
          return;
        }
        if (outsourceReceiptIds.length) {
          await openPullPreview('outsource_order_receipt', outsourceReceiptIds, openOpts);
          return;
        }
        await openPullPreview('purchase_receipt', receiptIds, openOpts);
        return;
      }
      const payableIds = Array.from(
        new Set(
          selected.flatMap((row) =>
            (row.payable_ids || []).map((id) => Number(id)).filter((id) => id > 0),
          ),
        ),
      );
      if (!payableIds.length) {
        messageApi.warning(t('app.kuaicaiwu.partnerStatement.detail.pushSelectPayable'));
        return;
      }
      await openPullPreview('payable', payableIds, {
        closeSourceModal: () => pullFromPartnerStatementCloseRef.current?.(),
        reopenSourceModal: () => pullFromPartnerStatementOpenRef.current?.(),
        partnerStatementIds: selectedIds,
        partnerStatementCodes: selected.map((row) =>
          String(row.statement_code || row.doc_code || '').trim(),
        ).filter(Boolean),
      });
    },
  });
  pullFromPartnerStatementCloseRef.current = pullFromPartnerStatementQuery.closeModal;
  pullFromPartnerStatementOpenRef.current = pullFromPartnerStatementQuery.openModal;

  const handlePullCreateSubmit = async (values: any) => {
    if (!pullPreviewData || !pullPreviewSourceIds.length || !pullPreviewKind) {
      messageApi.warning(t(`${P}.pullPreviewIncomplete`));
      return false;
    }
    if (pullPreviewData.has_blocking_issues) {
      messageApi.warning(
        purchaseInvoiceCapabilityReasonMessage(pullPreviewData.blocking_reason, t)
          || t(`${P}.pullPreviewBlocked`),
      );
      return false;
    }
    const maxPush = resolvePurchaseInvoicePullPreviewCap(pullPreviewData);
    const enteredAmount = Number(values.invoice_amount) || 0;
    if (enteredAmount <= 0) {
      messageApi.warning(t(`${P}.amountRequired`));
      return false;
    }
    const taxRate = Number(values.tax_rate) || 13;
    const amountMode = (values.amount_input_mode || 'tax_inclusive') as InvoiceAmountInputMode;
    const { invoiceAmountExcl: invoiceAmount, totalIncl: estimatedTotal } = resolveInvoiceAmountsForSubmit(
      enteredAmount,
      taxRate,
      amountMode,
      { maxTotalIncl: maxPush },
    );
    const discountAmount = Number(values.discount_amount) || 0;
    const occupancyTotal = estimatedTotal + discountAmount;
    if (moneyExceedsMax(occupancyTotal, maxPush)) {
      messageApi.warning(t(`${P}.pullExceedMax`, { max: formatCurrencyAmount(maxPush) }));
      return false;
    }
    let detailItems: PurchaseInvoiceCreateData['detail_items'];
    if (pullReceiptLineSelectEnabled) {
      if (pullReceiptSelectedIds.length === 0) {
        messageApi.warning(t(`${P}.pull.selectAtLeastOneLine`));
        return false;
      }
      const detailLines = (pullPreviewData.detail_lines ?? []) as PullReceiptFinanceDetailLine[];
      const reconciled = reconcilePullReceiptLinesForHeaderAmount(
        pullReceiptSelectedIds,
        detailLines,
        occupancyTotal,
        pullReceiptLineAmounts,
      );
      if (reconciled.selectedItemIds.length === 0) {
        messageApi.warning(t(`${P}.pull.selectAtLeastOneLine`));
        return false;
      }
      if (Math.abs(reconciled.lineSum - occupancyTotal) > 0.009) {
        messageApi.warning(t(`${P}.pull.lineAmountMismatch`));
        return false;
      }
      if (!pullPartnerStatementIdsRef.current.length) {
        const detailById = new Map(detailLines.map((row) => [row.purchase_receipt_item_id, row]));
        for (const id of reconciled.selectedItemIds) {
          const cap = Number(detailById.get(id)?.max_push_amount ?? 0);
          const amt = Number(reconciled.amounts[id] ?? 0);
          if (amt <= 0 || amt > cap + 0.009) {
            messageApi.warning(t(`${P}.pull.lineExceedMax`));
            return false;
          }
        }
      }
      const qtyMap = syncPullReceiptLineQuantitiesFromAmounts(
        reconciled.selectedItemIds,
        reconciled.amounts,
        detailLines,
      );
      const detailByIdForQty = new Map(detailLines.map((row) => [row.purchase_receipt_item_id, row]));
      for (const id of reconciled.selectedItemIds) {
        const line = detailByIdForQty.get(id);
        const explicitQty = pullReceiptLineQuantities[id];
        if (explicitQty != null && Number(explicitQty) > 0) {
          qtyMap[id] = Number(explicitQty);
        }
        const maxQty = Number(line?.max_push_quantity ?? 0);
        const qty = Number(qtyMap[id] ?? 0);
        if (!(qty > 0)) {
          messageApi.warning(t(`${PAGE}.pull.lineQtyRequired`));
          return false;
        }
        if (maxQty > 0 && qty > maxQty + 0.00009) {
          messageApi.warning(t(`${PAGE}.pull.lineQtyExceedMax`));
          return false;
        }
      }
      const headerInvoiceNumber = String(values.invoice_number ?? '').trim();
      for (const id of reconciled.selectedItemIds) {
        const lineNum = String(pullReceiptLineInvoiceNumbers[id] ?? headerInvoiceNumber).trim();
        if (!lineNum) {
          messageApi.warning(t(`${PAGE}.pull.lineInvoiceNumberRequired`));
          return false;
        }
      }
      const fallbackDocId = pullPreviewSourceIds[0];
      const fallbackType =
        pullPreviewKind === 'outsource_order_receipt'
          ? 'outsource_order_receipt'
          : pullPreviewKind === 'purchase_order'
            ? 'purchase_order'
            : pullPreviewKind === 'payable'
              ? 'payable'
              : 'purchase_receipt';
      detailItems = buildPurchaseDetailItemsFromPullLines(
        reconciled.selectedItemIds,
        reconciled.amounts,
        detailLines,
        taxRate,
        fallbackType,
        Number(fallbackDocId || 0),
        qtyMap,
        pullReceiptLineInvoiceNumbers,
        headerInvoiceNumber,
      );
      if (!detailItems.length) {
        messageApi.warning(t(`${P}.pull.selectAtLeastOneLine`));
        return false;
      }
    }
    if (
      pullPreviewKind
      && (pullPreviewKind === 'purchase_receipt'
        || pullPreviewKind === 'payable'
        || pullPreviewKind === 'purchase_order'
        || pullPreviewKind === 'outsource_order_receipt')
      && !(detailItems?.length)
    ) {
      messageApi.warning(t(`${P}.detailPullRequiresDetailLines`));
      return false;
    }
    const sourceLabel =
      pullPreviewKind === 'purchase_order'
        ? pullFromPurchaseOrderAction.sourceLabel
        : pullPreviewKind === 'purchase_receipt' || pullPreviewKind === 'outsource_order_receipt'
          ? pullFromPurchaseReceiptAction.sourceLabel
          : pullFromPayableAction.sourceLabel;
    const targetLabel =
      pullPreviewKind === 'purchase_order'
        ? pullFromPurchaseOrderAction.targetLabel
        : pullPreviewKind === 'purchase_receipt' || pullPreviewKind === 'outsource_order_receipt'
          ? pullFromPurchaseReceiptAction.targetLabel
          : pullFromPayableAction.targetLabel;
    const wantPayment =
      Boolean(values.concurrent_payment_enabled)
      && pullPreviewKind === 'payable'
      && pullPreviewSourceIds.length === 1;
    if (wantPayment) {
      if (!paymentPerms.canCreate) {
        messageApi.warning(t(`${P}.concurrentPaymentNoPermission`));
        return false;
      }
      const settleAmt = Number(values.settle_amount) || 0;
      const maxSettle = Number(pullPreviewData.remaining_settle_amount ?? 0);
      if (settleAmt <= 0) {
        messageApi.warning(t(`${P}.concurrentPaymentAmountRequired`));
        return false;
      }
      if (settleAmt > maxSettle) {
        messageApi.warning(t(`${P}.concurrentPaymentExceedMax`, { max: formatCurrencyAmount(maxSettle) }));
        return false;
      }
      try {
        assertBankAccountForPaymentMethod(values.payment_method, values.bank_account_id, t);
      } catch (e: unknown) {
        messageApi.warning(e instanceof Error ? e.message : t(`${P}.concurrentPaymentAccountRequired`));
        return false;
      }
    }
    const departmentPayload = resolvePurchaseDepartmentPayload(
      values.department_id,
      resolveDepartmentName,
      values.department_name,
    );
    const pullLedgerMode =
      pullPreviewData.ledger_posting_mode === 'by_invoice' ? 'by_invoice' : 'immediate';
    setPullSubmitting(true);
    try {
      await purchaseInvoiceService.create({
        settlement_mode: 'detail',
        purchase_order_id: pullPreviewData.purchase_order_id ?? undefined,
        purchase_order_code: pullPreviewData.purchase_order_code ?? undefined,
        payable_id:
          pullPreviewKind === 'payable' ? pullPreviewSourceIds[0] : pullPreviewData.payable_id,
        payable_code: pullPreviewKind === 'payable' ? pullPreviewData.source_code : pullPreviewData.payable_code,
        supplier_id: Number(pullPreviewData.supplier_id || 0),
        supplier_name: pullPreviewData.supplier_name || '',
        settlement_closing_date: formatDateTime(
          values.settlement_closing_date || values.invoice_date || dayjs(),
          'YYYY-MM-DD',
        ),
        department_id: departmentPayload.department_id,
        department_name: departmentPayload.department_name,
        ledger_posting_mode: pullLedgerMode,
        source_type: pullPreviewKind,
        source_id: pullPreviewSourceIds[0],
        source_ids:
          (pullPreviewKind === 'payable'
            || pullPreviewKind === 'purchase_receipt'
            || pullPreviewKind === 'purchase_order'
            || pullPreviewKind === 'outsource_order_receipt')
          && pullPreviewSourceIds.length > 1
            ? pullPreviewSourceIds
            : undefined,
        invoice_number: String(values.invoice_number ?? '').trim(),
        invoice_date: formatDateTime(values.invoice_date || dayjs(), 'YYYY-MM-DD'),
        invoice_type: values.invoice_type || '增值税专用发票',
        tax_rate: taxRate,
        invoice_amount: invoiceAmount,
        // 始终传价税合计，与后端含税真源一致；不含税录入在分位钳制后也须走合计反算
        total_amount: estimatedTotal,
        discount_amount: discountAmount,
        adjust_payable:
          pullPreviewKind === 'payable'
          && discountAmount !== 0
          && Boolean(values.adjust_payable),
        notes:
          String(values.notes ?? '').trim() ||
          (pullPartnerStatementIdsRef.current.length
            ? t('app.kuaicaiwu.common.createdFromSourceNote', {
                source: pullFromPartnerStatementAction.sourceLabel,
                code: (pullPartnerStatementCodesRef.current.length
                  ? pullPartnerStatementCodesRef.current
                  : pullPartnerStatementIdsRef.current.map(String)
                ).join('、'),
              })
            : t('app.kuaicaiwu.common.createdFromSourceNote', {
                source: sourceLabel,
                code: pullPreviewData.source_code,
              })),
        status: '未审核',
        review_status: '草稿',
        attachments: normalizeDocumentAttachments(values.attachments),
        detail_items: detailItems,
        ...(pullPartnerStatementIdsRef.current.length
          ? { partner_statement_ids: pullPartnerStatementIdsRef.current }
          : {}),
        ...(wantPayment
          ? {
              concurrent_settlement: {
                enabled: true,
                total_amount: Number(values.settle_amount),
                payment_method: values.payment_method,
                bank_account_id: values.bank_account_id,
                bank_account: resolveLedgerAccountNote(
                  bankAccounts,
                  values.bank_account_id,
                  values.bank_account,
                ),
                voucher_date: formatDateTime(values.settle_date || dayjs(), 'YYYY-MM-DD'),
                notes: String(values.settle_notes ?? '').trim() || undefined,
              },
            }
          : {}),
      });
      messageApi.success(
        wantPayment
          ? t(`${P}.pullCreateWithPaymentSuccess`, { target: targetLabel })
          : t(`${P}.pullCreateSuccess`, { target: targetLabel }),
      );
      resetPullPreview();
      actionRef.current?.reload();
      return true;
    } catch (e: unknown) {
      messageApi.error(resolveApiErrorMessage(e, t('common.createFailed')));
      return false;
    } finally {
      setPullSubmitting(false);
    }
  };

  const reviewStatusEnum = useMemo(() => buildReviewStatusEnum(t), [t]);

  const columns: ProColumns<PurchaseInvoice>[] = useMemo(
    () => [
      ...financeDocCodePartnerSearchColumns({
        docCodeLabel: t(`${P}.col.code`),
        docCodeField: 'invoice_code',
        partnerLabel: t('app.kuaicaiwu.common.supplier'),
        partnerIdField: 'supplier_id',
        partnerNameField: 'supplier_name',
        partnerOptions: supplierOptions,
      }),
      financeInvoiceNumberSearchColumn(t(`${P}.col.invoiceNumber`)),
      {
        title: t(`${P}.col.code`),
        key: 'finance_doc_partner_stacked',
        dataIndex: 'invoice_code',
        width: 240,
        minWidth: 240,
        uniTableKeepWidth: true,
        uniTablePrimaryFlex: false,
        resizable: false,
        fixed: 'left',
        hideInSearch: true,
        sorter: true,
        ellipsis: false,
        render: (_, entity) => (
          <UniTableStackedPrimaryCell
            primary={String(entity.supplier_name ?? '')}
            secondary={String(entity.invoice_code ?? '')}
            onSecondaryClick={() =>
              navigate(`${DETAIL_LIST_BASE}/${entity.id}`)
            }
          />
        ),
      },
      {
        title: t('app.kuaicaiwu.common.supplier'),
        dataIndex: 'supplier_name',
        hideInTable: true,
      },
      {
        title: t(`${P}.col.purchaseOrder`),
        dataIndex: 'purchase_order_code',
        width: 150,
        minWidth: 150,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
      },
      {
        title: t(`${P}.col.invoiceNumber`),
        dataIndex: 'invoice_number',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
      },
      {
        title: t(`${P}.col.taxRate`),
        dataIndex: 'tax_rate',
        width: 88,
        minWidth: 88,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
        render: (_, r) => `${r.tax_rate}%`,
      },
      {
        title: t(`${P}.col.exclTax`),
        dataIndex: 'invoice_amount',
        valueType: 'money',
        align: 'right',
        width: 130,
        minWidth: 130,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
      },
      {
        title: t(`${P}.col.taxAmount`),
        dataIndex: 'tax_amount',
        valueType: 'money',
        align: 'right',
        width: 110,
        minWidth: 110,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
      },
      {
        title: t(`${P}.col.discountAmount`),
        dataIndex: 'discount_amount',
        valueType: 'money',
        align: 'right',
        width: 110,
        minWidth: 110,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
      },
      {
        title: t(`${P}.form.billingAmount`),
        dataIndex: 'total_amount',
        valueType: 'money',
        align: 'right',
        width: 130,
        minWidth: 130,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
      },
      {
        title: t('app.kuaicaiwu.common.invoiceDate'),
        key: 'finance_invoice_date',
        dataIndex: 'invoice_date',
        valueType: 'date',
        width: 120,
        minWidth: 120,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
      },
      {
        title: t('app.kuaicaiwu.common.invoiceDate'),
        dataIndex: 'invoice_date_range',
        valueType: 'dateRange',
        hideInTable: true,
        order: 20,
        formItemProps: formDateRangeFormItemProps,
      },
      {
        title: t('common.remark'),
        dataIndex: 'notes',
        minWidth: 160,
        uniTableRemainderFlex: true,
        uniTablePrimaryFlex: true,
        resizable: false,
        hideInSearch: true,
        ellipsis: true,
        render: (_, r) => r.notes || '—',
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        hideInTable: true,
        order: 21,
        valueEnum: {
          未审核: { text: t('app.kuaicaiwu.financeLifecycle.voucherDraft') },
          已开票: { text: t('app.kuaicaiwu.receivable.invoiceStatus.issuedFull') },
          已驳回: { text: t('app.kuaicaiwu.financeStatus.review.rejected') },
          已作废: { text: t('app.kuaicaiwu.financeStatus.voucher.cancelled') },
        },
      },
      {
        title: t('app.kuaicaiwu.common.reviewStatus'),
        dataIndex: 'review_status',
        hideInTable: true,
        order: 22,
        valueEnum: reviewStatusEnum,
      },
      ...financeDocCreatedUpdatedColumns<PurchaseInvoice>(t),
      ...(purchaseInvoiceAuditColumn ? [purchaseInvoiceAuditColumn] : []),
      {
        title: t('app.kuaicaiwu.common.lifecycle'),
        key: 'lifecycle',
        dataIndex: 'lifecycle_stage',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) => {
          const lc = getChineseInvoiceLifecycle(record as unknown as Record<string, unknown>, t);
          return (
            <UniLifecycle
              percent={lc.percent}
              stageName={lc.stageName}
              status={lc.status}
              subStages={lc.subStages}
              showLabel
              size="small"
              showCircleTooltip={false}
            />
          );
        },
      },
      {
        title: t('common.actions'),
        key: 'action',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) => {
          const acts: React.ReactNode[] = [];
          if (canFillPurchaseInvoiceNumber(record) && purchaseInvoicePerms.canUpdate) {
            acts.push(
              <Button
                key="edit"
                {...rowActionFillInvoiceNumber('update')}
                onClick={() => openEditModal(record)}
              />,
            );
          }
          acts.push(
            <Button
              key="det"
              {...rowActionKind('read')}
              onClick={() => navigate(`${DETAIL_LIST_BASE}/${record.id}`)}
            />,
          );
          if (canDeletePurchaseInvoice(record) && purchaseInvoicePerms.canDelete) {
            acts.push(
              <ActionConfirmPopconfirm
                key="del"
                title={t(`${P}.deleteTitle`)}
                description={t(`${P}.deleteContent`, {
                  number: record.invoice_number?.trim() || record.invoice_code || record.id,
                })}
                onConfirm={() => executeDelete(record)}
              >
                <Button {...rowActionKind('delete')} onClick={(e) => e.stopPropagation()} />
              </ActionConfirmPopconfirm>,
            );
          }
          return acts;
        },
      },
    ],
    [
      t,
      navigate,
      supplierOptions,
      reviewStatusEnum,
      purchaseInvoicePerms.canDelete,
      purchaseInvoicePerms.canUpdate,
      purchaseInvoiceAuditColumn,
    ],
  );


  const pullReceiptColumns = useMemo(
    () => [
      {
        title: t(`${P}.pull.col.receiptDate`),
        dataIndex: 'source_date',
        width: 120,
        render: (v: unknown) => (v ? formatDateTime(String(v), 'YYYY-MM-DD') : '-'),
      },
      {
        title: t(`${P}.pull.col.receiptCode`),
        dataIndex: 'receipt_code',
        width: 168,
        ellipsis: true,
        render: (_: unknown, row: PurchaseInvoicePullCandidate) =>
          row.receipt_code || row.doc_code || row.code,
      },
      {
        title: t('app.kuaicaiwu.payable.col.supplierName'),
        dataIndex: 'supplier_name',
        width: 160,
        ellipsis: true,
      },
      {
        title: t(`${P}.pull.col.detailLineCount`),
        dataIndex: 'detail_line_count',
        width: 88,
        align: 'center' as const,
        render: (v: unknown) => (v != null && Number(v) >= 0 ? Number(v) : '-'),
      },
      {
        title: t(`${P}.pull.col.invoicedLineCount`),
        dataIndex: 'invoiced_line_count',
        width: 88,
        align: 'center' as const,
        render: (v: unknown) => (v != null && Number(v) >= 0 ? Number(v) : '-'),
      },
      {
        title: t(`${P}.pull.col.invoiceableAmount`),
        dataIndex: 'invoiceable_amount',
        width: 120,
        align: 'right' as const,
        render: (_: unknown, row: PurchaseInvoicePullCandidate) =>
          formatCurrencyAmount(row.invoiceable_amount ?? row.amount ?? 0),
      },
      {
        title: t(`${P}.pull.col.invoicedAmount`),
        dataIndex: 'invoiced_amount',
        width: 120,
        align: 'right' as const,
        render: (v: unknown) => formatCurrencyAmount(v || 0),
      },
    ],
    [t],
  );

  const pullPayableColumns = useMemo(
    () => [
      {
        title: t('components.uniPullQuery.documentDateColumn'),
        dataIndex: 'source_date',
        width: 120,
        render: (v: unknown) => (v ? formatDateTime(String(v), 'YYYY-MM-DD') : '-'),
      },
      {
        title: t(`${P}.pull.col.payableCode`),
        dataIndex: 'payable_code',
        width: 168,
        ellipsis: true,
        render: (_: unknown, row: PurchaseInvoicePullCandidate) =>
          row.payable_code || row.doc_code || row.code,
      },
      {
        title: t('app.kuaicaiwu.payable.col.supplierName'),
        dataIndex: 'supplier_name',
        width: 160,
        ellipsis: true,
      },
      {
        title: t(`${P}.pull.col.detailLineCount`),
        dataIndex: 'detail_line_count',
        width: 88,
        align: 'center' as const,
        render: (v: unknown) => (v != null && Number(v) >= 0 ? Number(v) : '-'),
      },
      {
        title: t(`${P}.pull.col.invoicedLineCount`),
        dataIndex: 'invoiced_line_count',
        width: 88,
        align: 'center' as const,
        render: (v: unknown) => (v != null && Number(v) >= 0 ? Number(v) : '-'),
      },
      {
        title: t(`${P}.pull.col.invoiceableAmount`),
        dataIndex: 'invoiceable_amount',
        width: 120,
        align: 'right' as const,
        render: (_: unknown, row: PurchaseInvoicePullCandidate) =>
          formatCurrencyAmount(row.invoiceable_amount ?? row.amount ?? 0),
      },
      {
        title: t(`${P}.pull.col.invoicedAmount`),
        dataIndex: 'invoiced_amount',
        width: 120,
        align: 'right' as const,
        render: (v: unknown) => formatCurrencyAmount(v || 0),
      },
    ],
    [t],
  );

  const pullStatementColumns = useMemo(
    () => [
      {
        title: t('components.uniPullQuery.documentDateColumn'),
        dataIndex: 'source_date',
        width: 120,
        render: (v: unknown) => (v ? formatDateTime(String(v), 'YYYY-MM-DD') : '-'),
      },
      {
        title: t('app.kuaicaiwu.partnerStatement.col.code'),
        dataIndex: 'statement_code',
        width: 168,
        ellipsis: true,
        render: (_: unknown, row: PurchaseInvoicePullCandidate) =>
          row.statement_code || row.doc_code || row.code,
      },
      {
        title: t('app.kuaicaiwu.partnerStatement.col.supplierName'),
        dataIndex: 'supplier_name',
        width: 160,
        ellipsis: true,
      },
      {
        title: t(`${P}.pull.col.detailLineCount`),
        dataIndex: 'detail_line_count',
        width: 88,
        align: 'center' as const,
        render: (v: unknown) => (v != null && Number(v) >= 0 ? Number(v) : '-'),
      },
      {
        title: t(`${P}.pull.col.invoicedLineCount`),
        dataIndex: 'invoiced_line_count',
        width: 88,
        align: 'center' as const,
        render: (v: unknown) => (v != null && Number(v) >= 0 ? Number(v) : '-'),
      },
      {
        title: t('app.kuaicaiwu.partnerStatement.col.statementAmount'),
        dataIndex: 'period_amount',
        width: 128,
        align: 'right' as const,
        render: (_: unknown, row: PurchaseInvoicePullCandidate) =>
          formatCurrencyAmount(row.period_amount ?? row.amount ?? 0),
      },
      {
        title: t(`${P}.pull.col.invoiceableAmount`),
        dataIndex: 'invoiceable_amount',
        width: 120,
        align: 'right' as const,
        render: (v: unknown) => formatCurrencyAmount(v || 0),
      },
      {
        title: t(`${P}.pull.col.invoicedAmount`),
        dataIndex: 'invoiced_amount',
        width: 120,
        align: 'right' as const,
        render: (v: unknown) => formatCurrencyAmount(v || 0),
      },
      {
        title: t('app.kuaicaiwu.partnerStatement.col.amountBasis'),
        dataIndex: 'amount_basis',
        width: 88,
        render: (v: unknown) =>
          v === 'tax_exclusive'
            ? t('app.kuaicaiwu.partnerStatement.amountBasis.taxExclusive')
            : t('app.kuaicaiwu.partnerStatement.amountBasis.taxInclusive'),
      },
    ],
    [t],
  );

  const pullTableColumns = useMemo(
    () => [
      { title: t(`${P}.pull.col.sourceCode`), dataIndex: 'code', width: 220, ellipsis: true },
      { title: t('app.kuaicaiwu.common.supplier'), dataIndex: 'supplier_name', width: 220, ellipsis: true },
      {
        title: t(`${P}.pull.col.detailLineCount`),
        dataIndex: 'detail_line_count',
        width: 88,
        align: 'center' as const,
        render: (v: unknown) => (v != null && Number(v) >= 0 ? Number(v) : '-'),
      },
      {
        title: t(`${P}.pull.col.invoicedLineCount`),
        dataIndex: 'invoiced_line_count',
        width: 88,
        align: 'center' as const,
        render: (v: unknown) => (v != null && Number(v) >= 0 ? Number(v) : '-'),
      },
      {
        title: t(`${P}.pull.col.docStatus`),
        dataIndex: 'source_status',
        width: 130,
        align: 'center' as const,
        render: (v: unknown) => {
          const { text, color } = getStatusDisplay(v);
          return text === '-' ? '-' : <MarkerTag color={color}>{text}</MarkerTag>;
        },
      },
      {
        title: t('app.kuaicaiwu.common.businessDate'),
        dataIndex: 'source_date',
        width: 130,
        render: (v: unknown) => (v ? formatDateTime(String(v), 'YYYY-MM-DD') : '-'),
      },
      {
        title: t(`${P}.col.amount`),
        dataIndex: 'amount',
        width: 140,
        align: 'right' as const,
        render: (v: unknown) => formatCurrencyAmount(v || 0),
      },
    ],
    [t],
  );

  const pullPreviewMaxPush = resolvePurchaseInvoicePullPreviewCap(pullPreviewData);
  const pullPreviewTargetLabel =
    pullPreviewKind === 'purchase_receipt'
      ? pullFromPurchaseReceiptAction.targetLabel
      : pullPreviewKind === 'payable'
        ? pullFromPayableAction.targetLabel
        : pullFromPurchaseOrderAction.targetLabel;

  const pullFormInitialValues = useMemo(() => {
    if (!pullPreviewData || !pullPreviewKind) return undefined;
    const maxPush = resolvePurchaseInvoicePullPreviewCap(pullPreviewData);
    const taxRate = 13;
    // 默认含税：录入金额取可开票价税合计上限
    const defaultIncl = maxPush > 0 ? maxPush : undefined;
    const sourceLabel =
      pullPreviewKind === 'purchase_order'
        ? pullFromPurchaseOrderAction.sourceLabel
        : pullPreviewKind === 'purchase_receipt'
          ? pullFromPurchaseReceiptAction.sourceLabel
          : pullFromPayableAction.sourceLabel;
    const defaultNote =
      pullPartnerStatementIdsRef.current.length
        ? t('app.kuaicaiwu.common.createdFromSourceNote', {
            source: pullFromPartnerStatementAction.sourceLabel,
            code: (pullPartnerStatementCodesRef.current.length
              ? pullPartnerStatementCodesRef.current
              : pullPartnerStatementIdsRef.current.map(String)
            ).join('、'),
          })
        : t('app.kuaicaiwu.common.createdFromSourceNote', {
            source: sourceLabel,
            code: pullPreviewData.source_code,
          });
    const remainingSettle = Number(pullPreviewData.remaining_settle_amount ?? 0);
    const ledgerMode =
      pullPreviewData.ledger_posting_mode === 'by_invoice' ? 'by_invoice' : 'immediate';
    const deptUuid = currentUser?.department?.uuid;
    if (deptUuid) {
      pullApplicantDepartmentUuidRef.current = deptUuid;
    }
    const deptDefaults = resolvePurchaseDepartmentFromApplicant(deptUuid, departmentOptions);
    const invoiceDay = dayjs();
    return {
      invoice_date: invoiceDay,
      settlement_closing_date: invoiceDay,
      ledger_posting_mode: ledgerMode,
      ...deptDefaults,
      invoice_type: '增值税专用发票',
      tax_rate: taxRate,
      amount_input_mode: 'tax_inclusive' as InvoiceAmountInputMode,
      invoice_amount: defaultIncl,
      notes: defaultNote,
      discount_amount: 0,
      adjust_payable: false,
      concurrent_payment_enabled: false,
      settle_amount: remainingSettle > 0 ? remainingSettle : undefined,
      settle_date: dayjs(),
      payment_method: BANK_TRANSFER_PAYMENT_METHOD,
      bank_account_id: undefined,
      bank_account: undefined,
      settle_notes: undefined,
    };
  }, [
    pullPreviewData,
    pullPreviewKind,
    pullFromPurchaseOrderAction.sourceLabel,
    pullFromPurchaseReceiptAction.sourceLabel,
    pullFromPayableAction.sourceLabel,
    pullFromPartnerStatementAction.sourceLabel,
    t,
    currentUser?.department?.uuid,
    departmentOptions,
  ]);

  useEffect(() => {
    if (!departmentOptions.length) return;
    const pendingUuid = String(pullApplicantDepartmentUuidRef.current ?? '').trim();
    if (!pendingUuid) return;
    if (!pullPreviewOpen) return;
    const existing = pullForm.getFieldValue('department_id');
    if (existing != null && existing !== '') return;
    const payload = resolvePurchaseDepartmentFromApplicant(pendingUuid, departmentOptions);
    if (payload.department_id == null) return;
    pullForm.setFieldsValue(payload);
  }, [departmentOptions, pullPreviewOpen, pullForm]);

  useEffect(() => {
    const state = (location.state ?? null) as {
      pullPayableId?: number;
      openPurchaseInvoicePullFromPartnerStatement?: boolean;
    } | null;
    if (state?.openPurchaseInvoicePullFromPartnerStatement) {
      pullFromPartnerStatementQuery.openModal();
      navigate(location.pathname, { replace: true, state: null });
      return;
    }
    const pullPayableId = state?.pullPayableId;
    if (!pullPayableId) return;
    void openPullPreview('payable', pullPayableId);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.state, location.pathname, navigate, pullFromPartnerStatementQuery]);

  useEffect(() => {
    if (!pullPreviewOpen || pullPreviewLoading || !pullFormInitialValues) return;
    pullAmountModeRef.current = 'tax_inclusive';
    pullTaxRateRef.current = Number(pullFormInitialValues.tax_rate) || 13;
    pullBroughtAmountRef.current = Number(pullFormInitialValues.invoice_amount) || 0;
    pullForm.setFieldsValue(pullFormInitialValues);
  }, [pullPreviewOpen, pullPreviewLoading, pullFormInitialValues, pullForm]);

  useEffect(() => {
    if (!pullPreviewOpen || !pullPreviewData) return;
    if (
      pullPreviewKind !== 'purchase_receipt'
      && pullPreviewKind !== 'payable'
      && pullPreviewKind !== 'purchase_order'
      && pullPreviewKind !== 'outsource_order_receipt'
    ) {
      return;
    }
    const lines = (pullPreviewData.detail_lines ?? []) as PullReceiptFinanceDetailLine[];
    if (!lines.length) {
      setPullReceiptSelectedIds([]);
      setPullReceiptLineAmounts({});
      setPullReceiptLineQuantities({});
      setPullReceiptLineInvoiceNumbers({});
      return;
    }
    const { selectedItemIds, amounts, quantities } = initPullReceiptLineSelection(lines);
    let effectiveIds = selectedItemIds;
    let effectiveAmounts = amounts;
    const headerCap = resolvePurchaseInvoicePullPreviewCap(pullPreviewData);
    let sum = sumPullReceiptLineAmounts(selectedItemIds, amounts);
    if (pullPartnerStatementIdsRef.current.length > 0 && headerCap > sum + 0.009) {
      const reconciled = reconcilePullReceiptLinesForHeaderAmount(
        selectedItemIds,
        lines,
        headerCap,
        amounts,
      );
      effectiveIds = reconciled.selectedItemIds;
      effectiveAmounts = reconciled.amounts;
      sum = reconciled.lineSum;
    }
    setPullReceiptSelectedIds(effectiveIds);
    setPullReceiptLineAmounts(effectiveAmounts);
    setPullReceiptLineQuantities(
      syncPullReceiptLineQuantitiesFromAmounts(effectiveIds, effectiveAmounts, lines),
    );
    syncPullReceiptSumToInvoiceForm(sum > 0 ? sum : headerCap);
  }, [pullPreviewOpen, pullPreviewKind, pullPreviewData, syncPullReceiptSumToInvoiceForm]);

  const pullAmountInputMode = Form.useWatch('amount_input_mode', pullForm) as InvoiceAmountInputMode | undefined;
  const pullTaxRateWatch = Form.useWatch('tax_rate', pullForm);
  const pullInvoiceAmountWatch = Form.useWatch('invoice_amount', pullForm);
  const pullInvoiceNumberWatch = Form.useWatch('invoice_number', pullForm);
  const pullDiscountWatch = Form.useWatch('discount_amount', pullForm);

  useEffect(() => {
    if (!pullPreviewOpen || pullReceiptSelectedIds.length === 0) return;
    const header = String(pullInvoiceNumberWatch ?? '').trim();
    const prevHeader = pullHeaderInvoiceNumberRef.current;
    setPullReceiptLineInvoiceNumbers((prev) => {
      let next = prev;
      if (prevHeader !== header) {
        next = applyHeaderInvoiceNumberToPullLines(
          pullReceiptSelectedIds,
          header,
          next,
          prevHeader,
        );
        pullHeaderInvoiceNumberRef.current = header;
      }
      return seedPullReceiptLineInvoiceNumbers(pullReceiptSelectedIds, header, next);
    });
  }, [pullPreviewOpen, pullReceiptSelectedIds, pullInvoiceNumberWatch]);

  const createAmountInputMode = Form.useWatch('amount_input_mode', createForm) as
    | InvoiceAmountInputMode
    | undefined;
  const createTaxRateWatch = Form.useWatch('tax_rate', createForm);
  const createInvoiceAmountWatch = Form.useWatch('invoice_amount', createForm);
  const createDiscountWatch = Form.useWatch('discount_amount', createForm);

  const createResolvedAmounts = useMemo(() => {
    const entered = Number(createInvoiceAmountWatch || 0);
    const taxRate = Number(createTaxRateWatch) || 13;
    const discount = Number(createDiscountWatch) || 0;
    const mode = (createAmountInputMode || 'tax_inclusive') as InvoiceAmountInputMode;
    if (!(entered > 0)) {
      return { mode, counterpartHint: '', billingAmount: null as number | null };
    }
    const base = resolveInvoiceAmountsForSubmit(entered, taxRate, mode);
    const counterpartHint =
      mode === 'tax_inclusive'
        ? t(`${P}.form.amountHintExcl`, { amount: formatAmount(base.invoiceAmountExcl) })
        : t(`${P}.form.amountHintIncl`, { amount: formatAmount(base.totalIncl) });
    // 开票金额始终为含税票面 I = A_incl − D（与录入口径无关）
    const faceIncl = quantizeMoney(base.totalIncl - discount);
    if (!(faceIncl > 0)) {
      return { mode, counterpartHint, billingAmount: null as number | null };
    }
    return { mode, counterpartHint, billingAmount: faceIncl };
  }, [
    createAmountInputMode,
    createInvoiceAmountWatch,
    createTaxRateWatch,
    createDiscountWatch,
    t,
  ]);

  useEffect(() => {
    if (!pullPreviewOpen) return;
    const mode = (pullForm.getFieldValue('amount_input_mode') || 'tax_inclusive') as InvoiceAmountInputMode;
    if (mode !== 'tax_inclusive') return;
    const brought = pullBroughtAmountRef.current;
    if (!(brought > 0)) return;
    const discount = Number(pullDiscountWatch) || 0;
    const faceIncl = brought - discount;
    if (faceIncl <= 0) return;
    const current = Number(pullForm.getFieldValue('invoice_amount')) || 0;
    if (Math.abs(current - faceIncl) <= 0.009) return;
    pullForm.setFieldValue('invoice_amount', faceIncl);
  }, [pullDiscountWatch, pullPreviewOpen, pullForm]);

  useEffect(() => {
    if (!pullPreviewOpen || !pullReceiptLineSelectEnabled || !pullPreviewData) return;
    if (pullReceiptSelectedIds.length === 0) return;
    const entered = Number(pullInvoiceAmountWatch || 0);
    if (!(entered > 0)) return;
    const taxRate = Number(pullTaxRateWatch) || 13;
    const mode = (pullAmountInputMode || 'tax_inclusive') as InvoiceAmountInputMode;
    const { totalIncl } = resolveInvoiceAmountsForSubmit(entered, taxRate, mode, {
      maxTotalIncl: pullPreviewMaxPush,
    });
    const discount = Number(pullDiscountWatch) || 0;
    const occupancyIncl = totalIncl + discount;
    const detailLines = (pullPreviewData.detail_lines ?? []) as PullReceiptFinanceDetailLine[];
    const currentSum = sumPullReceiptLineAmounts(pullReceiptSelectedIds, pullReceiptLineAmounts);
    if (Math.abs(currentSum - occupancyIncl) <= 0.009) return;
    const reconciled = reconcilePullReceiptLinesForHeaderAmount(
      pullReceiptSelectedIds,
      detailLines,
      occupancyIncl,
    );
    setPullReceiptLineAmounts(reconciled.amounts);
    setPullReceiptLineQuantities(
      syncPullReceiptLineQuantitiesFromAmounts(
        reconciled.selectedItemIds,
        reconciled.amounts,
        detailLines,
      ),
    );
    if (reconciled.selectedItemIds.join(',') !== pullReceiptSelectedIds.join(',')) {
      setPullReceiptSelectedIds(reconciled.selectedItemIds);
    }
  }, [
    pullPreviewOpen,
    pullReceiptLineSelectEnabled,
    pullPreviewData,
    pullReceiptSelectedIds,
    pullReceiptLineAmounts,
    pullInvoiceAmountWatch,
    pullAmountInputMode,
    pullTaxRateWatch,
    pullDiscountWatch,
    pullPreviewMaxPush,
  ]);

  const pullAmountCounterpartHint = useMemo(() => {
    const entered = Number(pullInvoiceAmountWatch || 0);
    const taxRate = Number(pullTaxRateWatch) || 13;
    if (!(entered > 0)) return '';
    const mode = (pullAmountInputMode || 'tax_inclusive') as InvoiceAmountInputMode;
    const resolved = resolveInvoiceAmountsForSubmit(entered, taxRate, mode, {
      maxTotalIncl: pullPreviewMaxPush,
    });
    if (mode === 'tax_inclusive') {
      return t(`${P}.form.amountHintExcl`, { amount: formatAmount(resolved.invoiceAmountExcl) });
    }
    return t(`${P}.form.amountHintIncl`, {
      amount: formatAmount(resolved.totalIncl),
    });
  }, [pullAmountInputMode, pullInvoiceAmountWatch, pullTaxRateWatch, pullPreviewMaxPush, t]);

  const purchaseDetailPullLineColumns = useMemo(
    () =>
      buildPurchaseDetailInvoicePullLineColumns({
        t,
        pullReceiptSelectedIds,
        pullReceiptLineAmounts,
        setPullReceiptLineAmounts,
        pullReceiptLineQuantities,
        setPullReceiptLineQuantities,
        pullReceiptLineInvoiceNumbers,
        setPullReceiptLineInvoiceNumbers,
        headerInvoiceNumber: String(pullInvoiceNumberWatch ?? '').trim(),
        syncPullReceiptSumToInvoiceForm,
        formatMoney: formatPullMoney,
        formatPercent: (rate) => (rate != null && Number.isFinite(Number(rate)) ? `${Number(rate)}%` : '-'),
        formatQty: (qty) => (qty != null && Number(qty) > 0 ? formatQuantity(qty) : '-'),
      }),
    [
      t,
      pullReceiptSelectedIds,
      pullReceiptLineAmounts,
      pullReceiptLineQuantities,
      pullReceiptLineInvoiceNumbers,
      pullInvoiceNumberWatch,
      syncPullReceiptSumToInvoiceForm,
    ],
  );

  const pullDetailLineSumIncl = useMemo(
    () => sumPullReceiptLineAmounts(pullReceiptSelectedIds, pullReceiptLineAmounts),
    [pullReceiptSelectedIds, pullReceiptLineAmounts],
  );

  const pullDetailTotalInclHint = useMemo(() => {
    if (!pullReceiptLineSelectEnabled || !(pullDetailLineSumIncl > 0)) {
      return '';
    }
    const discount = Number(pullDiscountWatch) || 0;
    const total = quantizeMoney(pullDetailLineSumIncl - discount);
    if (!(total > 0)) {
      return t(`${PAGE}.form.totalInclNonPositive`);
    }
    return t(`${PAGE}.form.totalInclFromLines`, { total: formatAmount(total) });
  }, [pullReceiptLineSelectEnabled, pullDetailLineSumIncl, pullDiscountWatch, t]);

  const handlePullPreviewOk = async () => {
    if (pullPreviewLoading || !pullPreviewData) {
      messageApi.warning(t(`${P}.pullPreviewIncomplete`));
      return;
    }
    if (pullPreviewData.has_blocking_issues) {
      messageApi.warning(
        purchaseInvoiceCapabilityReasonMessage(pullPreviewData.blocking_reason, t)
          || t(`${P}.pullPreviewBlocked`),
      );
      return;
    }
    if (pullPreviewMaxPush <= 0) {
      messageApi.warning(t(`${P}.pullNoInvoiceableAmount`));
      return;
    }
    let values: Record<string, unknown>;
    try {
      values = await pullForm.validateFields();
    } catch {
      messageApi.warning(t(`${P}.pullFormValidationFailed`));
      return;
    }
    await handlePullCreateSubmit(values);
  };

  return (
    <>
    <FinanceInvoiceSettlementModeAlert pageMode="detail" kind="purchase">
    <ListPageTemplate>
      <UniTable<PurchaseInvoice>
        headerTitle={t(`${PAGE}.pageTitle`)}
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.purchaseInvoice)}
        actionRef={actionRef}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        onTableDataChange={setTableRows}
        columns={alignProColumns(columns, SALES_DOC_LIST_FIELD_RANK)}
        columnPersistenceId="apps.kuaicaiwu.pages.finance-management.purchase-detail-invoices.list-v1"
        showAdvancedSearch
        request={async (params, sort, _filter, searchFormValues) => {
          const listParams = resolvePurchaseInvoiceListParams(searchFormValues, sort);
          lastListParamsRef.current = listParams;
          const apiParams: PurchaseInvoiceListParams = {
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize || 20,
            settlement_mode: 'detail',
            ...listParams,
          };
          try {
            const res = await purchaseInvoiceService.list(apiParams);
            return {
              data: res.items || [],
              total: res.total || 0,
              success: true,
            };
          } catch (error: any) {
            messageApi.error(error?.message || t('app.kuaicaiwu.common.loadListFailed'));
            return { data: [], total: 0, success: false };
          }
        }}
        skipFuzzyPinyinClientFilter
        pinnedTabsField={FINANCE_INVOICE_PINNED_REVIEW_FIELD}
        rowKey="id"
        showCreateButton={false}
        createButtonText={t(`${P}.createButton`)}
        onCreate={() => setCreateModalVisible(true)}
        showDeleteButton
        deleteButtonText={t('common.delete')}
        onDelete={handleBatchDelete}
        deleteConfirmTitle={t('app.kuaicaiwu.common.confirmBatchDelete')}
        deleteConfirmDescription={(count) => t(`${P}.batchDeleteConfirm`, { count })}
        toolBarActions={[
          <UniBatchMenuButton
            key="purchase-invoice-submit"
            selectedRowKeys={selectedRowKeys}
            buttonText={t('common.submit')}
            menuItems={purchaseInvoiceToolbarAuditMenus.submitItems}
            documentCommitAndSubmitReview={
              purchaseInvoiceToolbarAuditMenus.documentCommitAndSubmitReview
            }
          />,
          <UniBatchMenuButton
            key="purchase-invoice-audit"
            selectedRowKeys={selectedRowKeys}
            buttonText={t('components.uniAction.audit')}
            menuItems={purchaseInvoiceToolbarAuditMenus.auditItems}
          />,
        ]}
        toolBarRender={() => [
          <UniPullCreateToolbar
            compactKey="create-purchase-detail-invoice-with-pull"
            createIcon={<PlusOutlined />}
            createLabel={t(`${PAGE}.createTitle`)}
            onCreate={() => messageApi.warning(t(`${P}.detailRegisterFromSourceOnly`))}
            menuItems={buildKuaicaiwuPullCreateMenuItems([
              {
                key: 'pull-from-pr',
                actionKey: 'purchase_invoice.pull_from_purchase_receipt',
                onClick: pullFromPurchaseReceiptQuery.openModal,
              },
              {
                key: 'pull-from-statement',
                actionKey: 'purchase_invoice.pull_from_partner_statement',
                onClick: pullFromPartnerStatementQuery.openModal,
              },
              {
                key: 'pull-from-payable',
                actionKey: 'purchase_invoice.pull_from_payable',
                onClick: pullFromPayableQuery.openModal,
              },
            ])}
          />,
        ]}
      />

      <UniPullQueryModal<PurchaseInvoicePullCandidate>
        open={pullFromPurchaseOrderQuery.open}
        title={pullFromPurchaseOrderAction.label}
        onCancel={pullFromPurchaseOrderQuery.closeModal}
        onOk={pullFromPurchaseOrderQuery.handleConfirm}
        zIndex={pullQueryModalZIndex}
        rowKey="id"
        columns={pullTableColumns}
        dataSource={pullFromPurchaseOrderQuery.dataSource}
        loading={pullFromPurchaseOrderQuery.loading}
        confirmLoading={pullFromPurchaseOrderQuery.confirmLoading}
        selectionType={pullFromPurchaseOrderQuery.selectionType}
        selectedRowKeys={pullFromPurchaseOrderQuery.selectedRowKeys}
        selectedRows={pullFromPurchaseOrderQuery.selectedRows}
        onSelectedRowKeysChange={pullFromPurchaseOrderQuery.handleSelectedRowKeysChange}
        isRowDisabled={orderPullRowDisabled}
        onDisabledRowClick={warnOrderPullDisabledRow}
        searchDraft={pullFromPurchaseOrderQuery.searchDraft}
        onSearchDraftChange={pullFromPurchaseOrderQuery.setSearchDraft}
        onSearchApply={pullFromPurchaseOrderQuery.handleSearchApply}
        onSearchClear={pullFromPurchaseOrderQuery.handleSearchClear}
        appliedKeyword={pullFromPurchaseOrderQuery.appliedKeyword}
        searchPlaceholder={t(`${P}.pull.searchPlaceholder`)}
        page={pullFromPurchaseOrderQuery.page}
        pageSize={pullFromPurchaseOrderQuery.pageSize}
        total={pullFromPurchaseOrderQuery.total}
        onPageChange={pullFromPurchaseOrderQuery.handlePageChange}
        scopeOptions={pullFromPurchaseOrderQuery.scopeOptions}
        scope={pullFromPurchaseOrderQuery.scope}
        onScopeChange={pullFromPurchaseOrderQuery.handleScopeChange}
        pullQuery={pullFromPurchaseOrderQuery.pullQuery}
        okText={pullFromPurchaseOrderAction.targetLabel}
      />

      <UniPullQueryModal<PurchaseInvoicePullCandidate>
        open={pullFromPurchaseReceiptQuery.open}
        title={pullFromPurchaseReceiptAction.label}
        onCancel={pullFromPurchaseReceiptQuery.closeModal}
        onOk={() => {
          void pullFromPurchaseReceiptQuery.handleConfirm();
        }}
        rowKey="id"
        columns={pullReceiptColumns}
        dataSource={pullFromPurchaseReceiptQuery.dataSource}
        loading={pullFromPurchaseReceiptQuery.loading}
        confirmLoading={pullFromPurchaseReceiptQuery.confirmLoading}
        selectionType={pullFromPurchaseReceiptQuery.selectionType}
        selectedRowKeys={pullFromPurchaseReceiptQuery.selectedRowKeys}
        selectedRows={pullFromPurchaseReceiptQuery.selectedRows}
        onSelectedRowKeysChange={pullFromPurchaseReceiptQuery.handleSelectedRowKeysChange}
        isRowDisabled={receiptPullRowDisabled}
        onDisabledRowClick={warnReceiptPullDisabledRow}
        searchDraft={pullFromPurchaseReceiptQuery.searchDraft}
        onSearchDraftChange={pullFromPurchaseReceiptQuery.setSearchDraft}
        onSearchApply={pullFromPurchaseReceiptQuery.handleSearchApply}
        onSearchClear={pullFromPurchaseReceiptQuery.handleSearchClear}
        appliedKeyword={pullFromPurchaseReceiptQuery.appliedKeyword}
        searchPlaceholder={t(`${P}.pull.searchPlaceholder`)}
        page={pullFromPurchaseReceiptQuery.page}
        pageSize={pullFromPurchaseReceiptQuery.pageSize}
        total={pullFromPurchaseReceiptQuery.total}
        onPageChange={pullFromPurchaseReceiptQuery.handlePageChange}
        scopeOptions={pullFromPurchaseReceiptQuery.scopeOptions}
        scope={pullFromPurchaseReceiptQuery.scope}
        onScopeChange={pullFromPurchaseReceiptQuery.handleScopeChange}
        pullQuery={pullFromPurchaseReceiptQuery.pullQuery}
        okText={pullFromPurchaseReceiptAction.targetLabel}
      />

      <UniPullQueryModal<PurchaseInvoicePullCandidate>
        open={pullFromPayableQuery.open}
        title={pullFromPayableAction.label}
        onCancel={pullFromPayableQuery.closeModal}
        onOk={() => {
          void pullFromPayableQuery.handleConfirm();
        }}
        rowKey="id"
        columns={pullPayableColumns}
        dataSource={pullFromPayableQuery.dataSource}
        loading={pullFromPayableQuery.loading}
        confirmLoading={pullFromPayableQuery.confirmLoading}
        selectionType={pullFromPayableQuery.selectionType}
        selectedRowKeys={pullFromPayableQuery.selectedRowKeys}
        selectedRows={pullFromPayableQuery.selectedRows}
        onSelectedRowKeysChange={pullFromPayableQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromPayableQuery.isRowDisabled}
        searchDraft={pullFromPayableQuery.searchDraft}
        onSearchDraftChange={pullFromPayableQuery.setSearchDraft}
        onSearchApply={pullFromPayableQuery.handleSearchApply}
        onSearchClear={pullFromPayableQuery.handleSearchClear}
        appliedKeyword={pullFromPayableQuery.appliedKeyword}
        searchPlaceholder={t(`${P}.pull.searchPlaceholder`)}
        page={pullFromPayableQuery.page}
        pageSize={pullFromPayableQuery.pageSize}
        total={pullFromPayableQuery.total}
        onPageChange={pullFromPayableQuery.handlePageChange}
        scopeOptions={pullFromPayableQuery.scopeOptions}
        scope={pullFromPayableQuery.scope}
        onScopeChange={pullFromPayableQuery.handleScopeChange}
        pullQuery={pullFromPayableQuery.pullQuery}
        okText={pullFromPayableAction.targetLabel}
      />

      <UniPullQueryModal<PurchaseInvoicePullCandidate>
        open={pullFromPartnerStatementQuery.open}
        title={pullFromPartnerStatementAction.label}
        onCancel={pullFromPartnerStatementQuery.closeModal}
        onOk={() => {
          void pullFromPartnerStatementQuery.handleConfirm();
        }}
        zIndex={pullQueryModalZIndex}
        rowKey="id"
        columns={pullStatementColumns}
        dataSource={pullFromPartnerStatementQuery.dataSource}
        loading={pullFromPartnerStatementQuery.loading}
        confirmLoading={pullFromPartnerStatementQuery.confirmLoading}
        selectionType={pullFromPartnerStatementQuery.selectionType}
        selectedRowKeys={pullFromPartnerStatementQuery.selectedRowKeys}
        selectedRows={pullFromPartnerStatementQuery.selectedRows}
        onSelectedRowKeysChange={pullFromPartnerStatementQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromPartnerStatementQuery.isRowDisabled}
        searchDraft={pullFromPartnerStatementQuery.searchDraft}
        onSearchDraftChange={pullFromPartnerStatementQuery.setSearchDraft}
        onSearchApply={pullFromPartnerStatementQuery.handleSearchApply}
        onSearchClear={pullFromPartnerStatementQuery.handleSearchClear}
        appliedKeyword={pullFromPartnerStatementQuery.appliedKeyword}
        searchPlaceholder={t(`${P}.pull.searchPlaceholder`)}
        page={pullFromPartnerStatementQuery.page}
        pageSize={pullFromPartnerStatementQuery.pageSize}
        total={pullFromPartnerStatementQuery.total}
        onPageChange={pullFromPartnerStatementQuery.handlePageChange}
        scopeOptions={pullFromPartnerStatementQuery.scopeOptions}
        scope={pullFromPartnerStatementQuery.scope}
        onScopeChange={pullFromPartnerStatementQuery.handleScopeChange}
        pullQuery={pullFromPartnerStatementQuery.pullQuery}
        okText={pullFromPartnerStatementAction.targetLabel}
      />

      <Modal
        title={t(`${P}.pullFormTitle`)}
        open={pullPreviewOpen}
        destroyOnHidden
        width={
          pullReceiptLineSelectEnabled
            ? MODAL_CONFIG.EXTRA_LARGE_WIDTH
            : MODAL_CONFIG.STANDARD_WIDTH
        }
        zIndex={pullPreviewZIndex}
        onCancel={resetPullPreview}
        okText={pullPreviewTargetLabel}
        cancelText={t('common.cancel')}
        confirmLoading={pullSubmitting}
        onOk={() => {
          void handlePullPreviewOk();
        }}
        okButtonProps={{
          disabled: !pullPreviewData || pullPreviewMaxPush <= 0,
        }}
      >
        {pullPreviewData ? (
          <div>
            <ProForm
            key={`pull-purchase-invoice-${pullPreviewKind}-${pullPreviewSourceIds.join('-')}`}
            className={FINANCE_PULL_PREVIEW_FORM_CLASS}
            form={pullForm}
            initialValues={pullFormInitialValues}
            submitter={false}
            onFinish={handlePullCreateSubmit}
            layout="vertical"
            {...financeFormGridProps}
          >
                <ProFormText
                  name="invoice_number"
                  label={t(`${P}.col.invoiceNumber`)}
                  rules={[{ required: true, message: t(`${P}.form.invoiceNumberRequired`) }]}
                  placeholder={t(`${P}.form.invoiceNumberPlaceholder`)}
                  colProps={financeColFifth}
                />
                <ProFormSelect
                  name="invoice_type"
                  label={t(`${P}.col.invoiceType`)}
                  options={invoiceTypeOptions}
                  rules={[{ required: true, message: t(`${P}.form.invoiceTypeRequired`) }]}
                  colProps={financeColFifth}
                />
                <ProFormDatePicker
                  name="invoice_date"
                  label={t('app.kuaicaiwu.common.invoiceDate')}
                  tooltip={t('app.kuaicaiwu.common.invoiceDateTip')}
                  rules={[{ required: true, message: t(`${P}.form.invoiceDateRequired`) }]}
                  fieldProps={{ style: { width: '100%' }, format: 'YYYY-MM-DD' }}
                  colProps={financeColFifth}
                />
                <ProFormDatePicker
                  name="settlement_closing_date"
                  label={t(`${P}.col.settlementClosingDate`)}
                  tooltip={t(`${P}.form.settlementClosingDateTip`)}
                  rules={[{ required: true, message: t(`${P}.form.settlementClosingDateRequired`) }]}
                  fieldProps={{ style: { width: '100%' }, format: 'YYYY-MM-DD' }}
                  colProps={financeColFifth}
                />
                <ProFormItem label={t('app.kuaicaiwu.common.supplier')} colProps={financeColFifth}>
                  <Input disabled value={pullPreviewData.supplier_name || ''} placeholder="—" />
                </ProFormItem>
                <ProFormSelect
                  name="ledger_posting_mode"
                  label={t('app.kuaicaiwu.partnerStatement.ledgerPostingMode')}
                  tooltip={t(`${P}.form.ledgerPostingModePullHint`)}
                  options={ledgerPostingModeOptions}
                  disabled
                  rules={[{ required: true }]}
                  colProps={financeColFifth}
                />
                <PurchaseDepartmentFormField
                  options={departmentOptions}
                  loading={departmentOptionsLoading}
                  colProps={financeColFifth}
                />
                <ProFormSelect
                  name="tax_rate"
                  label={t(`${P}.col.taxRate`)}
                  options={TAX_RATE_OPTIONS}
                  rules={[{ required: true, message: t(`${P}.form.taxRateRequired`) }]}
                  colProps={financeColFifth}
                  fieldProps={{
                    onChange: (nextRate: number) => {
                      const prevRate = pullTaxRateRef.current;
                      const mode = (pullForm.getFieldValue('amount_input_mode')
                        || 'tax_inclusive') as InvoiceAmountInputMode;
                      const current = Number(pullForm.getFieldValue('invoice_amount')) || 0;
                      const next = Number(nextRate) || 0;
                      if (current > 0) {
                        pullForm.setFieldValue(
                          'invoice_amount',
                          recalcEnteredAmountOnTaxRateChange(current, prevRate, next, mode),
                        );
                      }
                      pullTaxRateRef.current = next;
                    },
                  }}
                />
                <ProFormItem name="amount_input_mode" label={t(`${P}.form.amountInputMode`)} colProps={financeColFifth}>
                  <ThemedSegmented
                    className="form-field-segmented"
                    block
                    options={[
                      { label: t(`${P}.form.amountModeExcl`), value: 'tax_exclusive' },
                      { label: t(`${P}.form.amountModeIncl`), value: 'tax_inclusive' },
                    ]}
                    onChange={(next) => {
                      const nextMode = next as InvoiceAmountInputMode;
                      const prevMode = pullAmountModeRef.current;
                      const taxRate = Number(pullForm.getFieldValue('tax_rate')) || 13;
                      const current = Number(pullForm.getFieldValue('invoice_amount')) || 0;
                      if (current > 0 && prevMode && prevMode !== nextMode) {
                        pullForm.setFieldValue(
                          'invoice_amount',
                          convertInvoiceAmountBetweenModes(current, taxRate, prevMode, nextMode),
                        );
                      }
                      pullAmountModeRef.current = nextMode;
                    }}
                  />
                </ProFormItem>
                <ProFormDigit
                  name="invoice_amount"
                  label={
                    (pullAmountInputMode || 'tax_inclusive') === 'tax_inclusive'
                      ? t(`${P}.form.amountModeIncl`)
                      : t(`${P}.form.amountModeExcl`)
                  }
                  min={0}
                  rules={[{ required: true, message: t(`${P}.amountRequired`) }]}
                  extra={pullAmountCounterpartHint || undefined}
                  colProps={financeColFifth}
                  fieldProps={{ precision: 2, style: { width: '100%' } }}
                />
                <ProFormDigit
                  name="discount_amount"
                  label={t(`${P}.form.discountAmount`)}
                  tooltip={t(`${P}.form.discountAmountTip`)}
                  extra={pullDetailTotalInclHint || undefined}
                  colProps={financeColFifth}
                  fieldProps={{
                    precision: 2,
                    style: { width: '100%' },
                    min: Number.NEGATIVE_INFINITY,
                  }}
                />
                {pullPreviewKind === 'payable' && Math.abs(Number(pullDiscountWatch) || 0) > 0.0009 ? (
                  <ProFormSwitch
                    name="adjust_payable"
                    label={t(`${P}.form.adjustPayable`)}
                    tooltip={t(`${P}.form.adjustPayableTip`)}
                    colProps={financeColFifth}
                  />
                ) : null}
                {pullReceiptLineSelectEnabled ? (
                  <FormModalGridBlock span={24}>
                    <div className={FINANCE_PULL_PREVIEW_DETAIL_BETWEEN_FORM_CLASS}>
                      <Typography.Paragraph strong className={FINANCE_PULL_PREVIEW_DETAIL_TITLE_CLASS}>
                        {t(`${P}.pull.detailTitle`)}
                      </Typography.Paragraph>
                      {(pullPreviewData.detail_lines?.length ?? 0) > 0 ? (
                        <div className={FINANCE_PULL_PREVIEW_DETAIL_TABLE_CLASS}>
                          <Table<PullReceiptFinanceDetailLine>
                            size="small"
                            dataSource={pullPreviewData.detail_lines as PullReceiptFinanceDetailLine[]}
                            rowKey={pullReceiptDetailLineRowKey}
                            pagination={false}
                            scroll={{ x: 2208, y: 260 }}
                            rowSelection={{
                              selectedRowKeys: pullReceiptSelectedIdsAsRowKeys(pullReceiptSelectedIds),
                              onChange: (keys) => {
                                const ids = keys.map((k) => Number(k)).filter((id) => id > 0);
                                setPullReceiptSelectedIds(ids);
                                const header = String(pullForm.getFieldValue('invoice_number') ?? '').trim();
                                setPullReceiptLineInvoiceNumbers((prev) =>
                                  seedPullReceiptLineInvoiceNumbers(ids, header, prev),
                                );
                                const sum = sumPullReceiptLineAmounts(ids, pullReceiptLineAmounts);
                                if (sum > 0) {
                                  syncPullReceiptSumToInvoiceForm(sum);
                                }
                              },
                              getCheckboxProps: (row) => ({
                                disabled: Number(row.max_push_amount ?? 0) <= 0,
                              }),
                            }}
                            columns={purchaseDetailPullLineColumns}
                          />
                        </div>
                      ) : (
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description={t(`${P}.pull.detailEmpty`)}
                        />
                      )}
                    </div>
                  </FormModalGridBlock>
                ) : null}
                <ProFormTextArea
                  name="notes"
                  label={t('common.remark')}
                  fieldProps={{ rows: 2 }}
                  colProps={financeColFull}
                />
            {canConcurrentPayment ? (
              <>
                <Row gutter={FORM_LAYOUT.GRID_GUTTER}>
                  <Col span={24}>
                    <ProFormSwitch
                      name="concurrent_payment_enabled"
                      label={t(`${P}.concurrentPayment`)}
                      extra={t(`${P}.concurrentPaymentHint`, {
                        max: formatAmount(pullPreviewData.remaining_settle_amount || 0),
                      })}
                    />
                  </Col>
                </Row>
                {concurrentPaymentEnabled ? (
                  <>
                    <Row gutter={FORM_LAYOUT.GRID_GUTTER}>
                      <Col span={12}>
                        <ProFormMoney
                          name="settle_amount"
                          label={t(`${P}.concurrentPaymentAmount`)}
                          min={0.01}
                          rules={[
                            { required: true, message: t(`${P}.concurrentPaymentAmountRequired`) },
                          ]}
                        />
                      </Col>
                      <Col span={12}>
                        <ProFormDatePicker
                          name="settle_date"
                          label={t('app.kuaicaiwu.payment.col.paymentDate')}
                          rules={[{ required: true }]}
                          fieldProps={{ style: { width: '100%' } }}
                        />
                      </Col>
                    </Row>
                    <Row gutter={FORM_LAYOUT.GRID_GUTTER}>
                      <Col span={12}>
                        <ProFormSelect
                          name="payment_method"
                          label={t('app.kuaicaiwu.payment.col.paymentMethod')}
                          options={paymentMethodOptions}
                          rules={[
                            {
                              required: true,
                              message: t('app.kuaicaiwu.payment.selectPaymentMethod'),
                            },
                          ]}
                        />
                      </Col>
                    </Row>
                    <LedgerAccountFormFields
                      accounts={bankAccounts}
                      accountLabel={t('app.kuaicaiwu.payment.outBankAccount')}
                      noteLabel={t('app.kuaicaiwu.payment.outAccountNote')}
                      omitColProps
                      rowNestedSpans={{ account: 12, note: 12 }}
                    />
                    <Row gutter={FORM_LAYOUT.GRID_GUTTER}>
                      <Col span={24}>
                        <ProFormTextArea
                          name="settle_notes"
                          label={t(`${P}.concurrentPaymentNotes`)}
                          fieldProps={{ rows: 2 }}
                        />
                      </Col>
                    </Row>
                  </>
                ) : null}
              </>
            ) : null}
            <DocumentAttachmentsField category="purchase_invoice_attachments" />
          </ProForm>
          </div>
        ) : null}
      </Modal>

      <ModalForm
        title={
          editingRecord?.invoice_code
            ? t(`${P}.editNumberTitleWithCode`, { code: editingRecord.invoice_code })
            : t(`${P}.editNumberTitle`)
        }
        open={editVisible}
        onOpenChange={(open) => {
          if (editSubmitting) return;
          setEditVisible(open);
          if (!open) setEditingRecord(null);
        }}
        onFinish={handleEditSubmit}
        width={480}
        modalProps={{ destroyOnHidden: true }}
        submitter={{ submitButtonProps: { loading: editSubmitting } }}
        initialValues={{
          invoice_number: faceInvoiceNumberForEdit(editingRecord?.invoice_number),
          invoice_date: editingRecord?.invoice_date ? dayjs(editingRecord.invoice_date) : dayjs(),
          attachments: mapAttachmentsToUploadList((editingRecord as { attachments?: unknown })?.attachments),
        }}
      >
        <ProFormText
          name="invoice_number"
          label={t(`${P}.col.invoiceNumber`)}
          rules={[{ required: true, message: t(`${P}.form.invoiceNumberRequired`) }]}
          placeholder={t(`${P}.form.invoiceNumberPlaceholder`)}
        />
        <ProFormDatePicker
          name="invoice_date"
          label={t('app.kuaicaiwu.common.invoiceDate')}
          tooltip={t('app.kuaicaiwu.common.invoiceDateTip')}
          rules={[{ required: true, message: t(`${P}.form.invoiceDateRequired`) }]}
          fieldProps={{ style: { width: '100%' }, format: 'YYYY-MM-DD' }}
        />
        <DocumentAttachmentsField category="purchase_invoice_attachments" />
      </ModalForm>

      <ModalForm
        title={t(`${P}.createTitle`)}
        open={createModalVisible}
        form={createForm}
        onOpenChange={(open) => {
          setCreateModalVisible(open);
          if (open) {
            createAmountModeRef.current = 'tax_inclusive';
            createTaxRateRef.current = 13;
          }
        }}
        onFinish={handleRegister}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        modalProps={{ destroyOnHidden: true }}
        initialValues={{
          invoice_type: '增值税专用发票',
          invoice_date: dayjs(),
          tax_rate: 13,
          amount_input_mode: 'tax_inclusive' as InvoiceAmountInputMode,
          discount_amount: 0,
        }}
        {...financeFormGridProps}
      >
        <FormModalGridBlock>
          <p style={{ color: '#8c8c8c', fontSize: 13, marginBottom: 0 }}>{t(`${P}.createHint`)}</p>
        </FormModalGridBlock>
        <ProFormSelect
          name="supplier_id"
          label={t('app.kuaicaiwu.common.supplier')}
          options={supplierOptions}
          rules={[{ required: true, message: t('app.kuaicaiwu.common.selectSupplier') }]}
          placeholder={t('app.kuaicaiwu.common.selectSupplier')}
          showSearch
          colProps={financeColHalf}
        />
        <ProFormText
          name="invoice_number"
          label={t(`${P}.col.invoiceNumber`)}
          rules={[{ required: true, message: t(`${P}.form.invoiceNumberRequired`) }]}
          placeholder={t(`${P}.form.invoiceNumberPlaceholder`)}
          colProps={financeColHalf}
        />
        <ProFormSelect
          name="invoice_type"
          label={t(`${P}.col.invoiceType`)}
          options={invoiceTypeOptions}
          rules={[{ required: true, message: t(`${P}.form.invoiceTypeRequired`) }]}
          colProps={financeColHalf}
        />
        <ProFormDatePicker
          name="invoice_date"
          label={t('app.kuaicaiwu.common.invoiceDate')}
          tooltip={t('app.kuaicaiwu.common.invoiceDateTip')}
          rules={[{ required: true, message: t(`${P}.form.invoiceDateRequired`) }]}
          fieldProps={{ style: { width: '100%' }, format: 'YYYY-MM-DD' }}
          colProps={financeColHalf}
        />
        <ProFormField
          name="tax_rate"
          label={t(`${P}.col.taxRate`)}
          rules={[{ required: true, message: t(`${P}.form.taxRateRequired`) }]}
          colProps={financeColHalf}
          renderFormItem={(_, { value, onChange }) => (
            <TaxRatePercentInput
              value={value}
              onChange={(next) => {
                const prevRate = createTaxRateRef.current;
                const mode = (createForm.getFieldValue('amount_input_mode')
                  || 'tax_inclusive') as InvoiceAmountInputMode;
                const current = Number(createForm.getFieldValue('invoice_amount')) || 0;
                const nextRate = Number(next) || 0;
                if (current > 0) {
                  createForm.setFieldValue(
                    'invoice_amount',
                    recalcEnteredAmountOnTaxRateChange(current, prevRate, nextRate, mode),
                  );
                }
                createTaxRateRef.current = nextRate;
                onChange?.(next);
              }}
            />
          )}
        />
        <ProFormField
          name="amount_input_mode"
          label={t(`${P}.form.amountInputMode`)}
          colProps={financeColHalf}
          renderFormItem={(_, { value, onChange }) => (
            <ThemedSegmented
              className="form-field-segmented"
              style={{ width: 'fit-content', maxWidth: '100%' }}
              value={value}
              options={[
                { label: t(`${P}.form.amountModeExcl`), value: 'tax_exclusive' },
                { label: t(`${P}.form.amountModeIncl`), value: 'tax_inclusive' },
              ]}
              onChange={(next) => {
                const nextMode = next as InvoiceAmountInputMode;
                const prevMode = createAmountModeRef.current;
                const taxRate = Number(createForm.getFieldValue('tax_rate')) || 13;
                const current = Number(createForm.getFieldValue('invoice_amount')) || 0;
                if (current > 0 && prevMode && prevMode !== nextMode) {
                  createForm.setFieldValue(
                    'invoice_amount',
                    convertInvoiceAmountBetweenModes(current, taxRate, prevMode, nextMode),
                  );
                }
                createAmountModeRef.current = nextMode;
                onChange?.(nextMode);
              }}
            />
          )}
        />
        <ProFormDigit
          name="invoice_amount"
          label={
            (createAmountInputMode || 'tax_inclusive') === 'tax_inclusive'
              ? t(`${P}.form.amountModeIncl`)
              : t(`${P}.form.amountModeExcl`)
          }
          min={0}
          rules={[{ required: true, message: t(`${P}.amountRequired`) }]}
          extra={createResolvedAmounts.counterpartHint || undefined}
          fieldProps={{ precision: 2, style: { width: '100%' } }}
          colProps={financeColHalf}
        />
        <ProFormDigit
          name="discount_amount"
          label={t(`${P}.form.discountAmount`)}
          tooltip={t(`${P}.form.discountAmountTip`)}
          fieldProps={{
            precision: 2,
            style: { width: '100%' },
            // 优惠可正可负（与后端 discount_amount 含税口径一致）
            min: Number.NEGATIVE_INFINITY,
          }}
          colProps={financeColHalf}
        />
        <ProFormField
          label={t(`${P}.form.billingAmount`)}
          tooltip={t(`${P}.form.billingAmountTip`)}
          colProps={financeColHalf}
          renderFormItem={() => (
            <InputNumber
              value={createResolvedAmounts.billingAmount}
              precision={2}
              disabled
              style={{ width: '100%' }}
              placeholder="—"
            />
          )}
        />
        <ProFormTextArea name="notes" label={t('common.remark')} colProps={financeColFull} />
        <DocumentAttachmentsField category="purchase_invoice_attachments" />
      </ModalForm>
    </ListPageTemplate>
    </FinanceInvoiceSettlementModeAlert>
    {purchaseInvoiceAuditModal}
  </>
  );
};

export default PurchaseInvoiceList;
