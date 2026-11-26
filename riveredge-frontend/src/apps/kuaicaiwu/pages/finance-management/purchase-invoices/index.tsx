/**
 * 采购发票列表页
 */
import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { rowActionKind, rowActionFillInvoiceNumber } from '../../../../../components/uni-action';
import { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button, Modal, Typography, Alert, Spin, Table, Empty, Form, Row, Col, InputNumber, theme } from 'antd';
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
import { UniAuditBatchMenuButton, createUniAuditBatchHandlers } from '../../../../../components/uni-batch';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { UniLifecycle } from '../../../../../components/uni-lifecycle';
import { ListPageTemplate, MODAL_CONFIG, MODAL_NESTED_ABOVE_PARENT_OFFSET, FormModalGridBlock } from '../../../../../components/layout-templates';
import { financeColFull, financeColHalf, financeFormGridProps } from '../../../utils/financeFormLayout';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import {
  UniPullQueryModal,
  filterByPullScope,
  paginatePullRows,
  UNI_PULL_QUERY_MAX_FETCH_LIMIT,
  resolvePullConfirmNumericIds,
  resolvePullQueryPartnerKey,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import { loadFinancePullCandidatePage } from '../shared/loadFinancePullCandidatePage';
import { getChineseInvoiceLifecycle } from '../../../utils/financeLifecycle';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { canDeletePurchaseInvoice, canFillPurchaseInvoiceNumber, faceInvoiceNumberForEdit } from '../../../utils/purchaseInvoiceUi';
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
import {
  initPullReceiptLineSelection,
  reconcilePullReceiptLinesForHeaderAmount,
  sumPullReceiptLineAmounts,
  buildPurchaseDetailItemsFromPullLines,
  type PullReceiptFinanceDetailLine,
} from '../../../../kuaizhizao/utils/pullReceiptFinanceLines';
import { formatDateTime, formatCurrencyAmount, formatAmount } from '../../../../../utils/format';
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
import { TaxRatePercentInput } from '../../../../kuaizhizao/components/document-detail-table/documentDetailTable';
import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { useQuery } from '@tanstack/react-query';
import { getBusinessConfig } from '../../../../../services/businessConfig';
import { orgFinanceInvoiceSettlementMode } from '../../../../../utils/documentLedgerRecognition';

const P = 'app.kuaicaiwu.purchaseInvoice';

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

type PullPreviewKind = 'purchase_order' | 'purchase_receipt' | 'payable' | 'outsource_order_receipt';

function resolvePullPreviewInvoiceCap(data: PurchaseInvoicePullPreview | null | undefined): number {
  if (!data) return 0;
  const budget = Number(data.partner_statement_invoice_budget);
  if (budget > 0) return budget;
  const total = Number(data.max_push_total);
  if (total > 0) return total;
  return (
    (data.items || []).reduce((sum, row) => sum + Number(row.max_push_quantity ?? 0), 0) || 0
  );
}

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
  const [pullPreviewSourceId, setPullPreviewSourceId] = useState<number | null>(null);
  const [pullPreviewSourceIds, setPullPreviewSourceIds] = useState<number[]>([]);
  const [pullReceiptSelectedIds, setPullReceiptSelectedIds] = useState<number[]>([]);
  const [pullReceiptLineAmounts, setPullReceiptLineAmounts] = useState<Record<number, number>>({});
  const { data: financeBusinessConfig } = useQuery({
    queryKey: ['businessConfigFinanceInvoiceSettlement'],
    queryFn: getBusinessConfig,
    staleTime: 60_000,
  });
  const tenantInvoiceSettlementMode = useMemo(
    () => orgFinanceInvoiceSettlementMode(financeBusinessConfig),
    [financeBusinessConfig],
  );
  const [pullPreviewKind, setPullPreviewKind] = useState<PullPreviewKind | null>(null);
  const [pullForm] = Form.useForm();
  const [createForm] = Form.useForm();
  const pullAmountModeRef = useRef<InvoiceAmountInputMode>('tax_inclusive');
  const pullTaxRateRef = useRef<number>(13);
  const createAmountModeRef = useRef<InvoiceAmountInputMode>('tax_inclusive');
  const createTaxRateRef = useRef<number>(13);
  /** 拉单带入含税金额 A（优惠前），用于 I=A-D */
  const pullBroughtAmountRef = useRef<number>(0);
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
  const [supplierOptions, setSupplierOptions] = useState<{ label: string; value: number }[]>([]);
  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const { message: messageApi } = App.useApp();
  const { token } = theme.useToken();
  const pullQueryModalZIndex = token.zIndexPopupBase + MODAL_NESTED_ABOVE_PARENT_OFFSET;
  const pullPreviewZIndex = pullQueryModalZIndex + MODAL_NESTED_ABOVE_PARENT_OFFSET;
  const { t } = useTranslation();

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
  const pullFromPurchaseOrderAction = getKuaicaiwuDocumentAction('purchase_invoice.pull_from_purchase_order');
  const pullFromPurchaseReceiptAction = getKuaicaiwuDocumentAction('purchase_invoice.pull_from_purchase_receipt');
  const pullFromPayableAction = getKuaicaiwuDocumentAction('purchase_invoice.pull_from_payable');
  const pullFromPartnerStatementAction = getKuaicaiwuDocumentAction('purchase_invoice.pull_from_partner_statement');

  const purchaseInvoiceAuditEnabled = useAuditRequired('purchase_invoice', false);
  const purchaseInvoicePerms = useResourcePermissions(PURCHASE_INVOICE_RESOURCE);
  const paymentPerms = useResourcePermissions('kuaicaiwu:payment');
  const concurrentPaymentEnabled = Form.useWatch('concurrent_payment_enabled', pullForm);
  const canConcurrentPayment =
    pullPreviewKind === 'payable'
    && pullPreviewSourceIds.length === 1
    && paymentPerms.canCreate
    && Number(pullPreviewData?.remaining_settle_amount ?? 0) > 0;
  const purchaseInvoiceAuditBatchHandlers = useMemo(
    () => createUniAuditBatchHandlers('purchase_invoice'),
    [],
  );
  const pullReceiptLineSelectEnabled = useMemo(
    () =>
      (pullPreviewKind === 'purchase_receipt'
        || pullPreviewKind === 'outsource_order_receipt'
        || pullPreviewKind === 'payable')
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
      await purchaseInvoiceService.update(Number(editingRecord.id), {
        invoice_number: String(values.invoice_number ?? '').trim(),
        invoice_date: formatDateTime(values.invoice_date || editingRecord.invoice_date || dayjs(), 'YYYY-MM-DD'),
        attachments: normalizeDocumentAttachments(values.attachments),
      });
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

  const handleRegister = async (values: any) => {
    try {
      const enteredAmount = Number(values.invoice_amount) || 0;
      const taxRate = Number(values.tax_rate) || 13;
      const discountAmount = Number(values.discount_amount) || 0;
      if (enteredAmount <= 0) {
        messageApi.warning(t(`${P}.amountRequired`));
        return false;
      }
      const amountMode = (values.amount_input_mode || 'tax_inclusive') as InvoiceAmountInputMode;
      // 录入金额 A（按口径折合含税）− 优惠 D（含税）= 票面开票金额 I
      const { totalIncl: baseIncl } = resolveInvoiceAmountsForSubmit(
        enteredAmount,
        taxRate,
        amountMode,
      );
      const faceIncl = quantizeMoney(baseIncl - discountAmount);
      if (!(faceIncl > 0)) {
        messageApi.warning(t(`${P}.form.billingAmountInvalid`));
        return false;
      }
      const { invoiceAmountExcl, totalIncl, taxAmount } = resolveInvoiceAmountsForSubmit(
        faceIncl,
        taxRate,
        'tax_inclusive',
      );

      const data: PurchaseInvoiceCreateData = {
        settlement_mode: tenantInvoiceSettlementMode,
        supplier_id: values.supplier_id,
        supplier_name: supplierOptions.find((o) => o.value === values.supplier_id)?.label || '',
        invoice_number: values.invoice_number,
        invoice_date: formatDateTime(values.invoice_date || dayjs(), 'YYYY-MM-DD'),
        invoice_type: values.invoice_type || '增值税专用发票',
        tax_rate: taxRate,
        invoice_amount: invoiceAmountExcl,
        tax_amount: taxAmount,
        total_amount: totalIncl,
        discount_amount: discountAmount,
        notes: values.notes,
        status: '未审核',
        review_status: '草稿',
        attachments: normalizeDocumentAttachments(values.attachments),
      };

      await purchaseInvoiceService.create(data);
      messageApi.success(t(`${P}.createSuccess`));
      setCreateModalVisible(false);
      actionRef.current?.reload();
      return true;
    } catch (error: unknown) {
      messageApi.error(resolveApiErrorMessage(error, t(`${P}.registerFailed`)));
      return false;
    }
  };

  const resetPullPreview = () => {
    setPullPreviewOpen(false);
    setPullPreviewSourceId(null);
    setPullPreviewSourceIds([]);
    setPullPreviewData(null);
    setPullPreviewKind(null);
    setPullReceiptSelectedIds([]);
    setPullReceiptLineAmounts({});
    pullForm.resetFields();
  };

  const syncPullReceiptSumToInvoiceForm = useCallback(
    (sumIncl: number) => {
      if (sumIncl <= 0) return;
      const taxRate = Number(pullForm.getFieldValue('tax_rate') ?? pullTaxRateRef.current ?? 13);
      const mode = (pullForm.getFieldValue('amount_input_mode') || pullAmountModeRef.current) as InvoiceAmountInputMode;
      pullBroughtAmountRef.current = sumIncl;
      const faceIncl = sumIncl - (Number(pullForm.getFieldValue('discount_amount')) || 0);
      if (mode === 'tax_inclusive') {
        pullForm.setFieldsValue({ invoice_amount: faceIncl });
      } else {
        pullForm.setFieldsValue({ invoice_amount: invoiceExclFromIncl(faceIncl, taxRate) });
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
    setPullPreviewSourceIds(sourceIds);
    setPullPreviewSourceId(sourceIds[0]);
    setPullReceiptSelectedIds([]);
    setPullReceiptLineAmounts({});
    setPullPreviewOpen(true);
    setPullPreviewLoading(true);
    setPullPreviewData(null);
    const hideLoading = messageApi.loading(t(`${P}.pullPreviewLoading`), 0);
    try {
      const data =
        kind === 'purchase_order'
          ? sourceIds.length === 1
            ? await purchaseInvoiceService.previewPullFromPurchaseOrder(sourceIds[0])
            : await purchaseInvoiceService.previewPullFromPurchaseOrders(sourceIds)
          : kind === 'purchase_receipt'
            ? sourceIds.length === 1
              ? await purchaseInvoiceService.previewPullFromPurchaseReceipt(
                  sourceIds[0],
                  pullPartnerStatementIdsRef.current,
                )
              : await purchaseInvoiceService.previewPullFromPurchaseReceipts(
                  sourceIds,
                  pullPartnerStatementIdsRef.current,
                )
            : kind === 'outsource_order_receipt'
              ? sourceIds.length === 1
                ? await purchaseInvoiceService.previewPullFromOutsourceOrderReceipt(
                    sourceIds[0],
                    pullPartnerStatementIdsRef.current,
                  )
                : await purchaseInvoiceService.previewPullFromOutsourceOrderReceipts(
                    sourceIds,
                    pullPartnerStatementIdsRef.current,
                  )
              : sourceIds.length === 1
                ? await purchaseInvoiceService.previewPullFromPayable(sourceIds[0])
                : await purchaseInvoiceService.previewPullFromPayables(sourceIds);
      if (data.has_blocking_issues) {
        const blockedText =
          purchaseInvoiceCapabilityReasonMessage(data.blocking_reason, t)
          || (data.summary ? String(data.summary) : '')
          || t(`${P}.pullPreviewBlocked`);
        showPullFlowNotice('warning', blockedText, t(`${P}.pullPreviewBlocked`));
        resetPullPreview();
        return;
      }
      const maxPush = resolvePullPreviewInvoiceCap(data);
      if (maxPush <= 0) {
        const noAmtText = (data.summary ? String(data.summary) : '') || t(`${P}.pullNoInvoiceableAmount`);
        showPullFlowNotice('warning', noAmtText, t(`${P}.pullNoInvoiceableAmount`));
        resetPullPreview();
        return;
      }
      options?.closeSourceModal?.();
      setPullPreviewData(data);
    } catch (e: unknown) {
      messageApi.error(resolveApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
      resetPullPreview();
      options?.reopenSourceModal?.();
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

  const pullQueryScopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const pullFromPurchaseOrderQuery = useUniPullQuery<PurchaseInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'radio',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => !isPullPurchaseInvoiceSelectable(record),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const res = await purchaseInvoiceService.listPurchaseOrderPullCandidates({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
        });
        const rows = res.data || [];
        const filtered = filterByPullScope(rows, scope, isPullPurchaseInvoiceSelectable);
        return paginatePullRows(filtered, page, pageSize);
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
        messageApi.warning(t(`${P}.selectSource`, { label: pullFromPurchaseOrderAction.sourceLabel }));
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

  const pullFromPurchaseReceiptQuery = useUniPullQuery<PurchaseInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => !isPullPurchaseInvoiceSelectable(record),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const res = await purchaseInvoiceService.listPurchaseReceiptPullCandidates({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
        });
        const rows = res.data || [];
        const filtered = filterByPullScope(rows, scope, isPullPurchaseInvoiceSelectable);
        return paginatePullRows(filtered, page, pageSize);
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
    onConfirmFailed: (error) => {
      showPullFlowNotice('error', resolveApiErrorMessage(error, t(`${P}.loadSourceFailed`)));
    },
  });
  pullFromPurchaseReceiptCloseRef.current = pullFromPurchaseReceiptQuery.closeModal;
  pullFromPurchaseReceiptOpenRef.current = pullFromPurchaseReceiptQuery.openModal;

  const pullFromPayableQuery = useUniPullQuery<PurchaseInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => !isPullPurchaseInvoiceSelectable(record),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const res = await purchaseInvoiceService.listPayablePullCandidates({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
        });
        const rows = res.data || [];
        const filtered = filterByPullScope(rows, scope, isPullPurchaseInvoiceSelectable);
        return paginatePullRows(filtered, page, pageSize);
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
    onConfirmFailed: (error) => {
      showPullFlowNotice('error', resolveApiErrorMessage(error, t(`${P}.loadSourceFailed`)));
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
            const data = await purchaseInvoiceService.previewPullFromPartnerStatementSupplierSources({
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
            const maxPush = resolvePullPreviewInvoiceCap(data);
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
    onConfirmFailed: (error) => {
      showPullFlowNotice('error', resolveApiErrorMessage(error, t(`${P}.loadSourceFailed`)));
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
    const maxPush = resolvePullPreviewInvoiceCap(pullPreviewData);
    const enteredAmount = Number(values.invoice_amount) || 0;
    if (enteredAmount <= 0) {
      messageApi.warning(t(`${P}.amountRequired`));
      return false;
    }
    const taxRate = Number(values.tax_rate) || 13;
    const amountMode = (values.amount_input_mode || 'tax_exclusive') as InvoiceAmountInputMode;
    const discountAmount = Number(values.discount_amount) || 0;
    const { invoiceAmountExcl: invoiceAmount, totalIncl: estimatedTotal } = resolveInvoiceAmountsForSubmit(
      enteredAmount,
      taxRate,
      amountMode,
      { maxTotalIncl: maxPush - discountAmount },
    );
    const occupancyTotal = estimatedTotal + discountAmount;
    if (moneyExceedsMax(occupancyTotal, maxPush)) {
      messageApi.warning(t(`${P}.pullExceedMax`, { max: formatCurrencyAmount(maxPush) }));
      return false;
    }
    const useDetailSettlement =
      tenantInvoiceSettlementMode === 'detail' && pullReceiptLineSelectEnabled;
    let pullReceiptLines: PurchaseInvoiceCreateData['pull_receipt_lines'];
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
      if (useDetailSettlement) {
        const fallbackDocId =
          pullPreviewKind === 'payable'
            ? Number(pullPreviewData.purchase_receipt_id || pullPreviewData.receipt_ids?.[0] || 0)
            : pullPreviewSourceIds[0];
        const fallbackType =
          pullPreviewKind === 'outsource_order_receipt'
            ? 'outsource_order_receipt'
            : 'purchase_receipt';
        detailItems = buildPurchaseDetailItemsFromPullLines(
          reconciled.selectedItemIds,
          reconciled.amounts,
          detailLines,
          taxRate,
          fallbackType,
          Number(fallbackDocId || 0),
        );
        if (!detailItems.length) {
          messageApi.warning(t(`${P}.pull.selectAtLeastOneLine`));
          return false;
        }
      } else {
        pullReceiptLines = reconciled.payload;
      }
    } else if (tenantInvoiceSettlementMode === 'detail') {
      messageApi.warning('当前组织已锁定「明细发票」模式，请从含明细行的采购入库单/委外收货单/应付单加载开票');
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
    const wantPayment = Boolean(values.concurrent_payment_enabled) && pullPreviewKind === 'payable';
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
    setPullSubmitting(true);
    try {
      await purchaseInvoiceService.create({
        settlement_mode: tenantInvoiceSettlementMode,
        purchase_order_id: pullPreviewData.purchase_order_id ?? undefined,
        purchase_order_code: pullPreviewData.purchase_order_code ?? undefined,
        payable_id:
          pullPreviewKind === 'payable' ? pullPreviewSourceIds[0] : pullPreviewData.payable_id,
        payable_code: pullPreviewKind === 'payable' ? pullPreviewData.source_code : pullPreviewData.payable_code,
        supplier_id: Number(pullPreviewData.supplier_id || 0),
        supplier_name: pullPreviewData.supplier_name || '',
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
        pull_receipt_lines: useDetailSettlement ? undefined : pullReceiptLines,
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
              navigate(`/apps/kuaicaiwu/finance-management/purchase-invoices/${entity.id}`)
            }
          />
        ),
      },
      {
        title: t(`${P}.settlementMode`),
        dataIndex: 'settlement_mode',
        width: 96,
        minWidth: 96,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        render: (_, record) => {
          const mode = String(record.settlement_mode || 'summary');
          const text =
            mode === 'detail'
              ? t(`${P}.settlementMode.detail`)
              : t(`${P}.settlementMode.summary`);
          return <MarkerTag variant="filled">{text}</MarkerTag>;
        },
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
      },
      {
        title: t('app.kuaicaiwu.common.reviewStatus'),
        dataIndex: 'review_status',
        hideInTable: true,
        order: 22,
        valueEnum: reviewStatusEnum,
      },
      ...financeDocCreatedUpdatedColumns<PurchaseInvoice>(t),
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
              onClick={() => navigate(`/apps/kuaicaiwu/finance-management/purchase-invoices/${record.id}`)}
            />,
            <UniWorkflowActions
              {...rowActionKind('skip')}
              key="wf"
              record={record}
              apiPrefix="/apps/kuaicaiwu/purchase-invoices"
              entityType="purchase_invoice"
              entityName={t(`${P}.entityName`)}
              statusField="status"
              reviewStatusField="review_status"
              draftStatuses={['草稿', 'draft']}
              pendingStatuses={['待审核']}
              approvedStatuses={['已审核']}
              rejectedStatuses={['已驳回', '驳回']}
              theme="link"
              size="small"
              onSuccess={() => actionRef.current?.reload()}
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
    [t, navigate, supplierOptions, reviewStatusEnum, purchaseInvoicePerms.canDelete, purchaseInvoicePerms.canUpdate],
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
        title: t('app.kuaicaiwu.partnerStatement.col.closingBalance'),
        dataIndex: 'closing_balance',
        width: 120,
        align: 'right' as const,
        render: (_: unknown, row: PurchaseInvoicePullCandidate) =>
          formatCurrencyAmount(row.closing_balance ?? row.amount ?? 0),
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

  const pullTableColumns = useMemo(
    () => [
      { title: t(`${P}.pull.col.sourceCode`), dataIndex: 'code', width: 220, ellipsis: true },
      { title: t('app.kuaicaiwu.common.supplier'), dataIndex: 'supplier_name', width: 220, ellipsis: true },
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

  const pullPreviewMaxPush = resolvePullPreviewInvoiceCap(pullPreviewData);
  const formatPullMoney = (v: number) =>
    formatCurrencyAmount(v || 0);
  const pullPreviewTargetLabel =
    pullPreviewKind === 'purchase_receipt'
      ? pullFromPurchaseReceiptAction.targetLabel
      : pullPreviewKind === 'payable'
        ? pullFromPayableAction.targetLabel
        : pullFromPurchaseOrderAction.targetLabel;

  const pullFormInitialValues = useMemo(() => {
    if (!pullPreviewData || !pullPreviewKind) return undefined;
    const maxPush = resolvePullPreviewInvoiceCap(pullPreviewData);
    const taxRate = 13;
    // 默认取含税可开票上限，避免默认值正算再超 0.01
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
    return {
      source_code: pullPreviewData.source_code,
      supplier_name: pullPreviewData.supplier_name,
      invoice_date: dayjs(),
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
  ]);

  useEffect(() => {
    const pullPayableId = (location.state as { pullPayableId?: number } | null)?.pullPayableId;
    if (!pullPayableId) return;
    void openPullPreview('payable', pullPayableId);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.state, location.pathname, navigate]);

  useEffect(() => {
    if (!pullPreviewOpen || pullPreviewLoading || !pullFormInitialValues) return;
    pullAmountModeRef.current = 'tax_exclusive';
    pullTaxRateRef.current = Number(pullFormInitialValues.tax_rate) || 13;
    pullBroughtAmountRef.current = Number(pullPreviewData?.items?.[0]?.max_push_quantity) || 0;
    pullForm.setFieldsValue(pullFormInitialValues);
  }, [pullPreviewOpen, pullPreviewLoading, pullFormInitialValues, pullForm]);

  useEffect(() => {
    if (!pullPreviewOpen || !pullPreviewData) return;
    if (pullPreviewKind !== 'purchase_receipt' && pullPreviewKind !== 'payable') return;
    const lines = (pullPreviewData.detail_lines ?? []) as PullReceiptFinanceDetailLine[];
    if (!lines.length) {
      setPullReceiptSelectedIds([]);
      setPullReceiptLineAmounts({});
      return;
    }
    const { selectedItemIds, amounts } = initPullReceiptLineSelection(lines);
    let effectiveIds = selectedItemIds;
    let effectiveAmounts = amounts;
    const headerCap = resolvePullPreviewInvoiceCap(pullPreviewData);
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
    syncPullReceiptSumToInvoiceForm(sum > 0 ? sum : headerCap);
  }, [pullPreviewOpen, pullPreviewKind, pullPreviewData, syncPullReceiptSumToInvoiceForm]);

  const pullAmountInputMode = Form.useWatch('amount_input_mode', pullForm) as InvoiceAmountInputMode | undefined;
  const pullTaxRateWatch = Form.useWatch('tax_rate', pullForm);
  const pullInvoiceAmountWatch = Form.useWatch('invoice_amount', pullForm);
  const pullDiscountWatch = Form.useWatch('discount_amount', pullForm);

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
    if (!pullPreviewOpen || !(pullBroughtAmountRef.current > 0)) return;
    const faceIncl = pullBroughtAmountRef.current - (Number(pullDiscountWatch) || 0);
    if (faceIncl <= 0) return;
    const mode = (pullForm.getFieldValue('amount_input_mode') || 'tax_exclusive') as InvoiceAmountInputMode;
    const taxRate = Number(pullForm.getFieldValue('tax_rate')) || 13;
    const next = mode === 'tax_inclusive' ? faceIncl : invoiceExclFromIncl(faceIncl, taxRate);
    const current = Number(pullForm.getFieldValue('invoice_amount')) || 0;
    if (Math.abs(current - next) > 0.009) {
      pullForm.setFieldValue('invoice_amount', next);
    }
  }, [pullDiscountWatch, pullPreviewOpen, pullForm]);

  useEffect(() => {
    if (!pullPreviewOpen || !pullReceiptLineSelectEnabled || !pullPreviewData) return;
    if (pullReceiptSelectedIds.length === 0) return;
    const entered = Number(pullInvoiceAmountWatch || 0);
    if (!(entered > 0)) return;
    const taxRate = Number(pullTaxRateWatch) || 13;
    const mode = (pullAmountInputMode || 'tax_exclusive') as InvoiceAmountInputMode;
    const { totalIncl } = resolveInvoiceAmountsForSubmit(entered, taxRate, mode, {
      maxTotalIncl: pullPreviewMaxPush - (Number(pullDiscountWatch) || 0),
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
    pullDiscountWatch,
    pullAmountInputMode,
    pullTaxRateWatch,
    pullDiscountWatch,
    pullPreviewMaxPush,
    syncPullReceiptSumToInvoiceForm,
  ]);

  const pullAmountCounterpartHint = useMemo(() => {
    const entered = Number(pullInvoiceAmountWatch || 0);
    const taxRate = Number(pullTaxRateWatch) || 13;
    if (!(entered > 0)) return '';
    const mode = (pullAmountInputMode || 'tax_exclusive') as InvoiceAmountInputMode;
    const resolved = resolveInvoiceAmountsForSubmit(entered, taxRate, mode, {
      maxTotalIncl: pullPreviewMaxPush - (Number(pullDiscountWatch) || 0),
    });
    if (mode === 'tax_inclusive') {
      return t(`${P}.form.amountHintExcl`, { amount: formatAmount(resolved.invoiceAmountExcl) });
    }
    return t(`${P}.form.amountHintIncl`, {
      amount: formatAmount(resolved.totalIncl),
    });
  }, [pullAmountInputMode, pullInvoiceAmountWatch, pullDiscountWatch, pullTaxRateWatch, pullPreviewMaxPush, t]);

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
    <ListPageTemplate>
      <UniTable<PurchaseInvoice>
        headerTitle={t(`${P}.pageTitle`)}
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.purchaseInvoice)}
        actionRef={actionRef}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        onTableDataChange={setTableRows}
        columns={alignProColumns(columns, SALES_DOC_LIST_FIELD_RANK)}
        columnPersistenceId="apps.kuaicaiwu.pages.finance-management.purchase-invoices.list-v8-line-settlement"
        showAdvancedSearch
        request={async (params, sort, _filter, searchFormValues) => {
          const listParams = resolvePurchaseInvoiceListParams(searchFormValues, sort);
          lastListParamsRef.current = listParams;
          const apiParams: PurchaseInvoiceListParams = {
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize || 20,
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
        onDelete={handleBatchDelete}
        deleteConfirmTitle={t('app.kuaicaiwu.common.confirmBatchDelete')}
        deleteConfirmDescription={(count) => t(`${P}.batchDeleteConfirm`, { count })}
        toolBarActionsAfterDelete={[
          <UniAuditBatchMenuButton
            key="purchase-invoice-batch-audit"
            selectedRowKeys={selectedRowKeys}
            selectedRecords={selectedRecordsForBatch}
            auditEnabled={purchaseInvoiceAuditEnabled}
            permGates={purchaseInvoicePerms}
            handlers={purchaseInvoiceAuditBatchHandlers}
            onSuccess={handlePurchaseInvoiceAuditBatchSuccess}
            toolBarButtonSize="medium"
          />,
        ]}
        toolBarRender={() => [
          <UniPullCreateToolbar
            compactKey="create-purchase-invoice-with-pull"
            createIcon={<PlusOutlined />}
            createLabel={t(`${P}.createButton`)}
            onCreate={() => setCreateModalVisible(true)}
            menuItems={buildKuaicaiwuPullCreateMenuItems([
              {
                key: 'pull-from-po',
                actionKey: 'purchase_invoice.pull_from_purchase_order',
                onClick: pullFromPurchaseOrderQuery.openModal,
              },
              {
                key: 'pull-from-pr',
                actionKey: 'purchase_invoice.pull_from_purchase_receipt',
                onClick: pullFromPurchaseReceiptQuery.openModal,
              },
              {
                key: 'pull-from-payable',
                actionKey: 'purchase_invoice.pull_from_payable',
                onClick: pullFromPayableQuery.openModal,
              },
              {
                key: 'pull-from-partner-statement',
                actionKey: 'purchase_invoice.pull_from_partner_statement',
                onClick: pullFromPartnerStatementQuery.openModal,
              },
            ])}
          />,
        ]}
      />

      <UniPullQueryModal<PurchaseInvoicePullCandidate>
        open={pullFromPurchaseOrderQuery.open}
        title={pullFromPurchaseOrderAction.label}
        onCancel={pullFromPurchaseOrderQuery.closeModal}
        onOk={() => {
          void pullFromPurchaseOrderQuery.handleConfirm();
        }}
        rowKey="id"
        columns={pullTableColumns}
        dataSource={pullFromPurchaseOrderQuery.dataSource}
        loading={pullFromPurchaseOrderQuery.loading}
        confirmLoading={pullFromPurchaseOrderQuery.confirmLoading}
        selectionType={pullFromPurchaseOrderQuery.selectionType}
        selectedRowKeys={pullFromPurchaseOrderQuery.selectedRowKeys}
        selectedRows={pullFromPurchaseOrderQuery.selectedRows}
        onSelectedRowKeysChange={pullFromPurchaseOrderQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromPurchaseOrderQuery.isRowDisabled}
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
        isRowDisabled={pullFromPurchaseReceiptQuery.isRowDisabled}
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
        width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
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
        {!pullPreviewData ? (
          <div>
            <Spin />
            <div style={{ color: 'var(--ant-color-primary)' }}>
              {t('app.kuaizhizao.salesOrder.loadingPreview')}
            </div>
          </div>
        ) : (
          <div>
            <p style={{ marginBottom: 12, fontWeight: 500 }}>{pullPreviewData.summary}</p>
            {pullPreviewData.has_blocking_issues && pullPreviewData.blocking_reason ? (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                title={purchaseInvoiceCapabilityReasonMessage(pullPreviewData.blocking_reason, t)}
              />
            ) : null}
            {pullPreviewData.items?.length > 0 ? (
              <Table
                size="small"
                dataSource={pullPreviewData.items}
                rowKey={(row) => String(row.item_id)}
                pagination={false}
                scroll={{ x: 720 }}
                columns={[
                  { title: t(`${P}.pull.col.sourceCode`), dataIndex: 'source_code', width: 140, ellipsis: true },
                  { title: t('app.kuaicaiwu.common.supplier'), dataIndex: 'supplier_name', width: 160, ellipsis: true },
                  {
                    title: t(`${P}.pull.col.docAmount`),
                    dataIndex: 'quantity',
                    width: 120,
                    align: 'right',
                    render: (v: number) => formatPullMoney(v),
                  },
                  {
                    title: t(`${P}.pull.col.invoicedAmount`),
                    dataIndex: 'pushed_quantity',
                    width: 120,
                    align: 'right',
                    render: (v: number) => formatPullMoney(v),
                  },
                  {
                    title: t(`${P}.pull.col.invoiceableAmount`),
                    dataIndex: 'max_push_quantity',
                    width: 120,
                    align: 'right',
                    render: (v: number) => formatPullMoney(v),
                  },
                ]}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('app.kuaizhizao.purchaseReturn.pull.previewNoLines')}
              />
            )}
            <Typography.Paragraph strong style={{ marginTop: 16, marginBottom: 8 }}>
              {t(`${P}.pull.detailTitle`)}
            </Typography.Paragraph>
            {(pullPreviewData.detail_lines?.length ?? 0) > 0 ? (
              <Table<PullReceiptFinanceDetailLine>
                size="small"
                dataSource={pullPreviewData.detail_lines as PullReceiptFinanceDetailLine[]}
                rowKey={(row) => String(row.purchase_receipt_item_id ?? row.line_no)}
                pagination={false}
                scroll={{ x: pullReceiptLineSelectEnabled ? 980 : 880, y: 240 }}
                rowSelection={
                  pullReceiptLineSelectEnabled
                    ? {
                        selectedRowKeys: pullReceiptSelectedIds,
                        onChange: (keys) => {
                          const ids = keys.map((k) => Number(k)).filter((id) => id > 0);
                          setPullReceiptSelectedIds(ids);
                          const sum = sumPullReceiptLineAmounts(ids, pullReceiptLineAmounts);
                          syncPullReceiptSumToInvoiceForm(sum);
                        },
                        getCheckboxProps: (row) => ({
                          disabled: Number(row.max_push_amount ?? 0) <= 0,
                        }),
                      }
                    : undefined
                }
                columns={[
                  {
                    title: t(`${P}.pull.col.lineNo`),
                    dataIndex: 'line_no',
                    width: 56,
                    align: 'center',
                  },
                  {
                    title: t(`${P}.pull.col.materialCode`),
                    dataIndex: 'material_code',
                    width: 120,
                    ellipsis: true,
                  },
                  {
                    title: t(`${P}.pull.col.materialName`),
                    dataIndex: 'material_name',
                    width: 160,
                    ellipsis: true,
                  },
                  {
                    title: t(`${P}.pull.col.materialSpec`),
                    dataIndex: 'material_spec',
                    width: 120,
                    ellipsis: true,
                    render: (v: string | null | undefined) => v || '',
                  },
                  {
                    title: t('common.unit'),
                    dataIndex: 'unit',
                    width: 64,
                    ellipsis: true,
                  },
                  {
                    title: t('common.quantity'),
                    dataIndex: 'quantity',
                    width: 100,
                    align: 'right',
                    render: (v: number) => formatAmount(v || 0),
                  },
                  {
                    title: t(`${P}.pull.col.unitPrice`),
                    dataIndex: 'unit_price',
                    width: 110,
                    align: 'right',
                    render: (v: number) => formatPullMoney(v),
                  },
                  {
                    title: t(`${P}.pull.col.lineAmount`),
                    dataIndex: 'amount',
                    width: 120,
                    align: 'right',
                    render: (v: number) => formatPullMoney(v),
                  },
                  ...(pullReceiptLineSelectEnabled
                    ? [
                        {
                          title: t(`${P}.pull.col.occupiedAmount`),
                          dataIndex: 'occupied_amount',
                          width: 100,
                          align: 'right' as const,
                          render: (v: number) => formatPullMoney(v),
                        },
                        {
                          title: t(`${P}.pull.col.invoiceableAmount`),
                          dataIndex: 'max_push_amount',
                          width: 100,
                          align: 'right' as const,
                          render: (v: number) => formatPullMoney(v),
                        },
                        {
                          title: t(`${P}.pull.col.thisInvoiceAmount`),
                          width: 130,
                          align: 'right' as const,
                          render: (_: unknown, row: PullReceiptFinanceDetailLine) => {
                            const id = row.purchase_receipt_item_id;
                            const selected = pullReceiptSelectedIds.includes(id);
                            const cap = Number(row.max_push_amount ?? 0);
                            return (
                              <InputNumber
                                size="small"
                                min={0}
                                max={cap}
                                precision={2}
                                disabled={!selected || cap <= 0}
                                value={pullReceiptLineAmounts[id]}
                                onChange={(val) => {
                                  const next = Number(val ?? 0);
                                  setPullReceiptLineAmounts((prev) => {
                                    const merged = { ...prev, [id]: next };
                                    const sum = sumPullReceiptLineAmounts(pullReceiptSelectedIds, merged);
                                    syncPullReceiptSumToInvoiceForm(sum);
                                    return merged;
                                  });
                                }}
                                style={{ width: '100%' }}
                              />
                            );
                          },
                        },
                      ]
                    : []),
                ]}
              />
            ) : (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t(`${P}.pull.detailEmpty`)}
              />
            )}
            {pullPreviewData.tip ? (
              <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 16 }}>
                {pullPreviewData.tip}
              </Typography.Paragraph>
            ) : null}
            {!pullPreviewData.has_blocking_issues && pullPreviewMaxPush > 0 ? (
              <ProForm
                key={`pull-purchase-invoice-${pullPreviewKind}-${pullPreviewSourceIds.join('-')}`}
                form={pullForm}
                initialValues={pullFormInitialValues}
                submitter={false}
                onFinish={handlePullCreateSubmit}
                layout="vertical"
                {...financeFormGridProps}
              >
                <ProFormText name="source_code" label={t('app.kuaicaiwu.common.sourceDoc')} readonly colProps={financeColHalf} />
                <ProFormText name="supplier_name" label={t('app.kuaicaiwu.common.supplier')} readonly colProps={financeColHalf} />
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
                <ProFormSelect
                  name="tax_rate"
                  label={t(`${P}.col.taxRate`)}
                  options={TAX_RATE_OPTIONS}
                  rules={[{ required: true, message: t(`${P}.form.taxRateRequired`) }]}
                  colProps={financeColHalf}
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
                <FormModalGridBlock span={12}>
                  <ProFormItem
                    name="amount_input_mode"
                    label={t(`${P}.form.amountInputMode`)}
                  >
                    <ThemedSegmented
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
                </FormModalGridBlock>
                <ProFormDigit
                  name="invoice_amount"
                  label={
                    (pullAmountInputMode || 'tax_exclusive') === 'tax_inclusive'
                      ? t(`${P}.form.amountModeIncl`)
                      : t(`${P}.form.amountModeExcl`)
                  }
                  min={0}
                  rules={[{ required: true, message: t(`${P}.amountRequired`) }]}
                  extra={pullAmountCounterpartHint || undefined}
                  colProps={financeColHalf}
                  fieldProps={{ precision: 2, style: { width: '100%' } }}
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
                />
                {pullPreviewKind === 'payable' && Math.abs(Number(pullDiscountWatch) || 0) > 0.0009 ? (
                  <ProFormSwitch
                    name="adjust_payable"
                    label={t(`${P}.form.adjustPayable`)}
                    tooltip={t(`${P}.form.adjustPayableTip`)}
                    colProps={financeColHalf}
                  />
                ) : null}
                <ProFormTextArea name="notes" label={t('common.remark')} fieldProps={{ rows: 2 }} colProps={financeColFull} />
                {canConcurrentPayment ? (
                  <>
                    <ProFormSwitch
                      name="concurrent_payment_enabled"
                      label={t(`${P}.concurrentPayment`)}
                      extra={t(`${P}.concurrentPaymentHint`, {
                        max: formatAmount(pullPreviewData.remaining_settle_amount || 0),
                      })}
                      colProps={financeColFull}
                    />
                    {concurrentPaymentEnabled ? (
                      <>
                        <ProFormMoney
                          name="settle_amount"
                          label={t(`${P}.concurrentPaymentAmount`)}
                          min={0.01}
                          rules={[{ required: true, message: t(`${P}.concurrentPaymentAmountRequired`) }]}
                          colProps={financeColHalf}
                        />
                        <ProFormDatePicker
                          name="settle_date"
                          label={t('app.kuaicaiwu.payment.col.paymentDate')}
                          rules={[{ required: true }]}
                          fieldProps={{ style: { width: '100%' } }}
                          colProps={financeColHalf}
                        />
                        <ProFormSelect
                          name="payment_method"
                          label={t('app.kuaicaiwu.payment.col.paymentMethod')}
                          options={paymentMethodOptions}
                          rules={[{ required: true, message: t('app.kuaicaiwu.payment.selectPaymentMethod') }]}
                          colProps={financeColHalf}
                        />
                        <LedgerAccountFormFields
                          accounts={bankAccounts}
                          accountLabel={t('app.kuaicaiwu.payment.outBankAccount')}
                          noteLabel={t('app.kuaicaiwu.payment.outAccountNote')}
                        />
                        <ProFormTextArea
                          name="settle_notes"
                          label={t(`${P}.concurrentPaymentNotes`)}
                          fieldProps={{ rows: 2 }}
                          colProps={financeColFull}
                        />
                      </>
                    ) : null}
                  </>
                ) : null}
            <DocumentAttachmentsField category="purchase_invoice_attachments" />
          </ProForm>
            ) : null}
          </div>
        )}
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
  );
};

export default PurchaseInvoiceList;
