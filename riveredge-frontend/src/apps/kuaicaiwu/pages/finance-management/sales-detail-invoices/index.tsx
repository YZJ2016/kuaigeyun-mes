/**
 * 销售明细开票列表页（settlement_mode=detail，与汇总「销售发票」分菜单）
 */
import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { rowActionKind, rowActionFillInvoiceNumber } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { ActionType, ProColumns, type ProFormInstance } from '@ant-design/pro-components';
import { App, Button, Empty, Form, Input, Modal, Table, theme, Typography } from 'antd';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ModalForm,
  ProForm,
  ProFormDatePicker,
  ProFormDigit,
  ProFormItem,
  ProFormMoney,
  ProFormSelect,
  ProFormSwitch,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import { PlusOutlined, DownOutlined } from '@ant-design/icons';
import { apiRequest, formatApiErrorDetail } from '../../../../../services/api';
import {
  LedgerAccountFormFields,
  resolveLedgerAccountNote,
} from '../../../components/LedgerAccountFormFields';
import { bankAccountService, type BankAccount } from '../../../services/finance/bank-account';
import {
  assertBankAccountForPaymentMethod,
  BANK_TRANSFER_PAYMENT_METHOD,
  getPaymentMethodOptions,
} from '../../../utils/financeSharedOptions';
import { UniTable } from '../../../../../components/uni-table';
import {
  UniBatchMenuButton,
  pickCapability,
  runCapabilityBatchLoop,
  useAuditBatchRunner,
  withDocumentSubmitCombinedItem,
  type UniBatchMenuItem,
} from '../../../../../components/uni-batch';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { isPendingReviewStatus } from '../../../../kuaizhizao/constants/documentStatus';
import { UniLifecycle } from '../../../../../components/uni-lifecycle';
import {
  ListPageTemplate,
  MODAL_CONFIG,
  MODAL_NESTED_ABOVE_PARENT_OFFSET,
  FormModalGridBlock,
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
  buildReviewStatusEnum,
  formatChineseInvoiceType,
  getChineseInvoiceTypeOptions,
} from '../../../utils/financeSharedOptions';
import {
  displaySalesInvoiceListCode,
  canDeleteSalesInvoice,
  canFillSalesInvoiceNumber,
  faceInvoiceNumberForEdit,
  salesInvoiceReviewRaw,
} from '../../../utils/salesInvoiceUi';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { buildKuaicaiwuPullCreateMenuItems, getKuaicaiwuDocumentAction } from '../../../constants/documentActionRegistry';
import {
  salesInvoiceService,
  type SalesInvoice,
  type SalesInvoiceListParams,
  type SalesInvoicePullCandidate,
  type SalesInvoicePullPreview,
} from '../../../services/finance/sales-invoice';
import { salesInvoiceCapabilityReasonMessage } from '../../../utils/salesInvoiceCapabilityMessages';
import {
  convertInvoiceAmountBetweenModes,
  moneyExceedsMax,
  recalcEnteredAmountOnTaxRateChange,
  resolveInvoiceAmountsForSubmit,
  type InvoiceAmountInputMode,
} from '../../../utils/invoiceAmountInput';
import DocumentAttachmentsField from '../../../../kuaizhizao/components/DocumentAttachmentsField';
import { mapAttachmentsToUploadList, normalizeDocumentAttachments } from '../../../../kuaizhizao/utils/documentAttachments';
import { getStatusDisplay } from '../../../../kuaizhizao/constants/documentStatus';
import { formatDateTime, formatCurrencyAmount, formatAmount, formatQuantity } from '../../../../../utils/format';
import {
  FINANCE_INVOICE_PINNED_REVIEW_FIELD,
  financeDocCodePartnerSearchColumns,
  financeDocCreatedUpdatedColumns,
  financeInvoiceNumberSearchColumn,
  resolveSalesInvoiceListParams,
} from '../../../utils/financeListCore';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { renderFinanceTypeMarker } from '../../../utils/financeListPresentation';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { SalesInvoicePartnerBankInfoField } from '../shared/SalesInvoicePartnerBankInfoField';
import { FinanceInvoiceSettlementModeAlert } from '../shared/FinanceInvoiceSettlementModeAlert';
import {
  buildPurchaseDetailItemsFromPullLines,
  initPullReceiptLineSelection,
  pullReceiptDetailLineRowKey,
  pullReceiptSelectedIdsAsRowKeys,
  reconcilePullReceiptLinesForHeaderAmount,
  sumPullReceiptLineAmounts,
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
import { buildSalesDetailInvoicePullLineColumns } from '../shared/salesDetailInvoicePullLineColumns';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import {
  PurchaseDepartmentFormField,
  resolvePurchaseDepartmentFromApplicant,
  resolvePurchaseDepartmentPayload,
  usePurchaseDepartmentOptions,
} from '../../../../kuaizhizao/pages/purchase-management/shared/PurchaseDepartmentFormField';
import {
  fetchSalesInvoicePullPreview,
  resolveSalesInvoicePullPreviewCap,
  type SalesInvoicePullPreviewKind,
} from '../shared/salesInvoicePullPreviewKernel';

type PullPreviewKind = SalesInvoicePullPreviewKind;

const formatPullMoney = (value: number) => formatCurrencyAmount(value || 0);

const TAX_RATE_OPTIONS = [
  { label: '13%', value: 13 },
  { label: '9%', value: 9 },
  { label: '6%', value: 6 },
  { label: '1%', value: 1 },
  { label: '0%', value: 0 },
];

const P = 'app.kuaicaiwu.salesInvoice';
const PAGE = 'app.kuaicaiwu.salesDetailInvoice';
const DETAIL_LIST_BASE = '/apps/kuaicaiwu/finance-management/sales-detail-invoices';
const SALES_INVOICE_RESOURCE = 'kuaicaiwu:sales-invoice';

function resolveApiErrorMessage(error: unknown, fallback: string): string {
  const err = error as { response?: { data?: { detail?: unknown } }; message?: string };
  return (
    formatApiErrorDetail(err?.response?.data?.detail)
    || err?.message
    || fallback
  );
}

const SalesInvoicesPage: React.FC = () => {
  const actionRef = useRef<ActionType>();
  const createFormRef = useRef<ProFormInstance>();
  const lastListParamsRef = useRef<Record<string, string | number | boolean | undefined>>({});
  const tableRowsRef = useRef<SalesInvoice[]>([]);
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation();
  const invoiceTypeOptions = useMemo(() => getChineseInvoiceTypeOptions(t), [t]);
  const reviewStatusEnum = useMemo(
    () => ({
      草稿: { text: t('app.kuaicaiwu.financeLifecycle.voucherDraft') },
      SUBMITTED: { text: t('common.submitted') },
      ...buildReviewStatusEnum(t),
      已作废: { text: t('app.kuaicaiwu.financeLifecycle.voided') },
      已红冲: { text: t('app.kuaicaiwu.financeLifecycle.redFlushed') },
    }),
    [t],
  );
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [createSeed, setCreateSeed] = useState<Record<string, unknown> | undefined>();
  const [editVisible, setEditVisible] = useState(false);
  const [editingRecord, setEditingRecord] = useState<SalesInvoice | null>(null);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [pullSubmitting, setPullSubmitting] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [pullPreviewOpen, setPullPreviewOpen] = useState(false);
  const [pullPreviewLoading, setPullPreviewLoading] = useState(false);
  const [pullPreviewData, setPullPreviewData] = useState<SalesInvoicePullPreview | null>(null);
  const [pullPreviewSourceId, setPullPreviewSourceId] = useState<number | null>(null);
  const [pullPreviewSourceIds, setPullPreviewSourceIds] = useState<number[]>([]);
  const [pullPreviewKind, setPullPreviewKind] = useState<PullPreviewKind | null>(null);
  const [pullForm] = Form.useForm();
  const pullAmountModeRef = useRef<InvoiceAmountInputMode>('tax_inclusive');
  const pullTaxRateRef = useRef<number>(13);
  const pullFromSalesOrderCloseRef = useRef<(() => void) | null>(null);
  const pullFromSalesOrderOpenRef = useRef<(() => void) | null>(null);
  const pullFromSalesDeliveryCloseRef = useRef<(() => void) | null>(null);
  const pullFromSalesDeliveryOpenRef = useRef<(() => void) | null>(null);
  const pullFromReceivableCloseRef = useRef<(() => void) | null>(null);
  const pullFromReceivableOpenRef = useRef<(() => void) | null>(null);
  const pullFromPartnerStatementCloseRef = useRef<(() => void) | null>(null);
  const pullFromPartnerStatementOpenRef = useRef<(() => void) | null>(null);
  const pullPartnerStatementIdsRef = useRef<number[]>([]);
  const pullPartnerStatementCodesRef = useRef<string[]>([]);
  const pullApplicantDepartmentUuidRef = useRef<string | undefined>(undefined);
  const pullBroughtAmountRef = useRef(0);
  const pullHeaderInvoiceNumberRef = useRef('');
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
  const [pullReceiptSelectedIds, setPullReceiptSelectedIds] = useState<number[]>([]);
  const [pullReceiptLineAmounts, setPullReceiptLineAmounts] = useState<Record<number, number>>({});
  const [pullReceiptLineQuantities, setPullReceiptLineQuantities] = useState<Record<number, number>>({});
  const [pullReceiptLineInvoiceNumbers, setPullReceiptLineInvoiceNumbers] = useState<Record<number, string>>({});
  const pullReceiptLineSelectEnabled = useMemo(
    () =>
      (
        pullPreviewKind === 'sales_delivery'
        || pullPreviewKind === 'receivable'
        || pullPreviewKind === 'sales_order'
      )
      && (pullPreviewData?.detail_lines?.length ?? 0) > 0,
    [pullPreviewKind, pullPreviewData],
  );
  const { token } = theme.useToken();
  const pullQueryModalZIndex = token.zIndexPopupBase + MODAL_NESTED_ABOVE_PARENT_OFFSET;
  const pullPreviewZIndex = pullQueryModalZIndex + MODAL_NESTED_ABOVE_PARENT_OFFSET;
  const [customerOptions, setCustomerOptions] = useState<{ label: string; value: number }[]>([]);
  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const { message: messageApi } = App.useApp();

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
  const pullFromSalesOrderAction = getKuaicaiwuDocumentAction('sales_invoice.pull_from_sales_order');
  const pullFromSalesDeliveryAction = getKuaicaiwuDocumentAction('sales_invoice.pull_from_sales_delivery');
  const pullFromReceivableAction = getKuaicaiwuDocumentAction('sales_invoice.pull_from_receivable');
  const pullFromPartnerStatementAction = getKuaicaiwuDocumentAction('sales_invoice.pull_from_partner_statement');
  const salesInvoicePerms = useResourcePermissions(SALES_INVOICE_RESOURCE);
  const salesInvoiceAuditEnabled = useAuditRequired('sales_invoice', false);
  const receiptPerms = useResourcePermissions('kuaicaiwu:receipt');
  const handleSalesInvoiceAuditBatchSuccess = useCallback(() => {
    setSelectedRowKeys([]);
    actionRef.current?.reload();
  }, []);
  const {
    runAction: runSalesInvoiceAuditBatch,
    auditModal: salesInvoiceAuditModal,
  } = useAuditBatchRunner<SalesInvoice>({
    permGates: salesInvoicePerms,
    handlers: {
      approve: (id) => salesInvoiceService.approveSalesInvoice(id),
      revoke: (id) => salesInvoiceService.revokeSalesInvoice(id),
      withdraw: (id) => salesInvoiceService.withdrawSalesInvoice(id),
    },
    onBatchComplete: handleSalesInvoiceAuditBatchSuccess,
    auditEntity: {
      entityType: 'sales_invoice',
      entityName: t(`${P}.entityName`),
    },
  });
  const paymentMethodOptions = useMemo(() => getPaymentMethodOptions(t), [t]);
  const concurrentReceiptEnabled = Form.useWatch('concurrent_receipt_enabled', pullForm);
  const canConcurrentReceipt =
    pullPreviewKind === 'receivable' && receiptPerms.canCreate && Number(pullPreviewData?.remaining_settle_amount ?? 0) > 0;

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiRequest<unknown>('/apps/master-data/supply-chain/customers', { params: { limit: 1000, is_active: true } });
        const list = Array.isArray(res) ? res : (res as any)?.data ?? (res as any)?.items ?? [];
        setCustomerOptions((Array.isArray(list) ? list : []).map((c: any) => ({
          label: c.name || c.customer_name || c.code || String(c.id),
          value: c.id,
        })));
      } catch {
        setCustomerOptions([]);
      }
    };
    load();
    bankAccountService
      .list({ limit: 200, is_active: true })
      .then((res) => setBankAccounts(res.data))
      .catch(() => setBankAccounts([]));
  }, []);

  const syncPullReceiptSumToInvoiceForm = useCallback(
    (sumIncl: number) => {
      if (sumIncl <= 0) return;
      pullForm.setFieldValue('invoice_amount', sumIncl);
      pullBroughtAmountRef.current = sumIncl;
    },
    [pullForm],
  );

  const handleCreate = async (_values: any) => {
    messageApi.warning(t(`${P}.detailRegisterFromSourceOnly`));
    return false;
  };

  const resetPullPreview = () => {
    setPullPreviewOpen(false);
    setPullPreviewSourceId(null);
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

  const openPullPreview = async (
    kind: PullPreviewKind,
    sourceIdsInput: number | number[],
    options?: {
      closeSourceModal?: () => void;
      reopenSourceModal?: () => void;
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
        kind === 'sales_order'
          ? pullFromSalesOrderAction.sourceLabel
          : kind === 'sales_delivery'
            ? pullFromSalesDeliveryAction.sourceLabel
            : pullFromReceivableAction.sourceLabel;
      showPullFlowNotice('warning', t(`${P}.selectSource`, { label: sourceLabel }));
      return;
    }
    const sourceId = sourceIds[0];
    setPullPreviewKind(kind);
    setPullPreviewOpen(false);
    setPullPreviewLoading(true);
    setPullPreviewData(null);
    setPullPreviewSourceId(sourceId);
    setPullPreviewSourceIds(sourceIds);
    const hideLoading = messageApi.loading(t(`${P}.pullPreviewLoading`), 0);
    try {
      if (kind === 'sales_order' && sourceIds.length > 1) {
        showPullFlowNotice('warning', t(`${P}.pull.sameCustomerRequired`));
        resetPullPreview();
        return;
      }
      const data = await fetchSalesInvoicePullPreview(
        kind,
        sourceIds,
        pullPartnerStatementIdsRef.current,
      );
      if (data.has_blocking_issues) {
        const blockedText =
          salesInvoiceCapabilityReasonMessage(data.blocking_reason, t)
          || (data.summary ? String(data.summary) : '')
          || t(`${P}.pullPreviewBlocked`);
        showPullFlowNotice('warning', blockedText, t(`${P}.pullPreviewBlocked`));
        resetPullPreview();
        return;
      }
      const maxPush =
        Number(
          data.max_push_total
            ?? (data.items || []).reduce(
              (sum, row) => sum + Number(row.max_push_quantity ?? 0),
              0,
            ),
        ) || 0;
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

  const isPullSalesInvoiceSelectable = useCallback(
    (record: SalesInvoicePullCandidate) => record.capabilities?.pull_sales_invoice?.allowed === true,
    [],
  );

  const pullConfirmFailed = useCallback(
    (error: unknown) => {
      showPullFlowNotice('error', resolveApiErrorMessage(error, t(`${P}.loadSourceFailed`)));
    },
    [showPullFlowNotice, t],
  );

  const pullQueryScopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const basePullSalesInvoiceRowDisabled = useCallback(
    (record: SalesInvoicePullCandidate) => !isPullSalesInvoiceSelectable(record),
    [isPullSalesInvoiceSelectable],
  );

  const pullFromSalesOrderQuery = useUniPullQuery<SalesInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: basePullSalesInvoiceRowDisabled,
    loadData: async (params) => {
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          isPullSalesInvoiceSelectable,
          (api) => salesInvoiceService.listSalesOrderPullCandidates(api),
        );
      } catch (e: unknown) {
        messageApi.error(resolveApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const sourceIds = resolvePullConfirmNumericIds(keys, rows, 'id');
      if (!sourceIds.length) {
        showPullFlowNotice(
          'warning',
          t(`${P}.selectSource`, { label: pullFromSalesOrderAction.sourceLabel }),
        );
        return;
      }
      const selectedIdSet = new Set(sourceIds);
      const partnerKeys = new Set(
        rows
          .filter((x) => selectedIdSet.has(Number(x.id)))
          .map((x) => resolvePullQueryPartnerKey(x))
          .filter(Boolean),
      );
      if (partnerKeys.size > 1) {
        showPullFlowNotice('warning', t(`${P}.pull.sameCustomerRequired`));
        return;
      }
      await openPullPreview('sales_order', sourceIds, {
        closeSourceModal: () => pullFromSalesOrderCloseRef.current?.(),
        reopenSourceModal: () => pullFromSalesOrderOpenRef.current?.(),
      });
    },
    onConfirmFailed: pullConfirmFailed,
  });
  pullFromSalesOrderCloseRef.current = pullFromSalesOrderQuery.closeModal;
  pullFromSalesOrderOpenRef.current = pullFromSalesOrderQuery.openModal;

  const orderPullRowDisabled = useCallback(
    (record: SalesInvoicePullCandidate) =>
      composePullRowDisabled(record, {
        baseDisabled: basePullSalesInvoiceRowDisabled,
        selectedRows: pullFromSalesOrderQuery.selectedRows,
      }),
    [basePullSalesInvoiceRowDisabled, pullFromSalesOrderQuery.selectedRows],
  );

  const pullFromSalesDeliveryQuery = useUniPullQuery<SalesInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: basePullSalesInvoiceRowDisabled,
    loadData: async (params) => {
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          isPullSalesInvoiceSelectable,
          (api) => salesInvoiceService.listSalesDeliveryPullCandidates(api),
        );
      } catch (e: unknown) {
        messageApi.error(resolveApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const sourceIds = resolvePullConfirmNumericIds(keys, rows, 'id');
      if (!sourceIds.length) {
        showPullFlowNotice(
          'warning',
          t(`${P}.selectSource`, { label: pullFromSalesDeliveryAction.sourceLabel }),
        );
        return;
      }
      const selectedIdSet = new Set(sourceIds);
      const partnerKeys = new Set(
        rows
          .filter((x) => selectedIdSet.has(Number(x.id)))
          .map((x) => resolvePullQueryPartnerKey(x))
          .filter(Boolean),
      );
      if (partnerKeys.size > 1) {
        showPullFlowNotice('warning', t(`${P}.pull.sameCustomerRequired`));
        return;
      }
      await openPullPreview('sales_delivery', sourceIds, {
        closeSourceModal: () => pullFromSalesDeliveryCloseRef.current?.(),
        reopenSourceModal: () => pullFromSalesDeliveryOpenRef.current?.(),
      });
    },
    onConfirmFailed: pullConfirmFailed,
  });
  pullFromSalesDeliveryCloseRef.current = pullFromSalesDeliveryQuery.closeModal;
  pullFromSalesDeliveryOpenRef.current = pullFromSalesDeliveryQuery.openModal;

  const deliveryPullRowDisabled = useCallback(
    (record: SalesInvoicePullCandidate) =>
      composePullRowDisabled(record, {
        baseDisabled: basePullSalesInvoiceRowDisabled,
        selectedRows: pullFromSalesDeliveryQuery.selectedRows,
      }),
    [basePullSalesInvoiceRowDisabled, pullFromSalesDeliveryQuery.selectedRows],
  );

  const pullFromReceivableQuery = useUniPullQuery<SalesInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: basePullSalesInvoiceRowDisabled,
    loadData: async (params) => {
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          isPullSalesInvoiceSelectable,
          (api) => salesInvoiceService.listReceivablePullCandidates(api),
        );
      } catch (e: unknown) {
        messageApi.error(resolveApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const sourceIds = resolvePullConfirmNumericIds(keys, rows, 'id');
      if (!sourceIds.length) {
        showPullFlowNotice(
          'warning',
          t(`${P}.selectSource`, { label: pullFromReceivableAction.sourceLabel }),
        );
        return;
      }
      const selectedIdSet = new Set(sourceIds);
      const partnerKeys = new Set(
        rows
          .filter((x) => selectedIdSet.has(Number(x.id)))
          .map((x) => resolvePullQueryPartnerKey(x))
          .filter(Boolean),
      );
      if (partnerKeys.size > 1) {
        showPullFlowNotice('warning', t(`${P}.pull.sameCustomerRequired`));
        return;
      }
      await openPullPreview('receivable', sourceIds, {
        closeSourceModal: () => pullFromReceivableCloseRef.current?.(),
        reopenSourceModal: () => pullFromReceivableOpenRef.current?.(),
      });
    },
    onConfirmFailed: pullConfirmFailed,
  });
  pullFromReceivableCloseRef.current = pullFromReceivableQuery.closeModal;
  pullFromReceivableOpenRef.current = pullFromReceivableQuery.openModal;

  const receivablePullRowDisabled = useCallback(
    (record: SalesInvoicePullCandidate) =>
      composePullRowDisabled(record, {
        baseDisabled: basePullSalesInvoiceRowDisabled,
        selectedRows: pullFromReceivableQuery.selectedRows,
      }),
    [basePullSalesInvoiceRowDisabled, pullFromReceivableQuery.selectedRows],
  );

  const pullFromPartnerStatementQuery = useUniPullQuery<SalesInvoicePullCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: basePullSalesInvoiceRowDisabled,
    loadData: async (params) => {
      try {
        return await loadFinancePullCandidatePage(
          params,
          params.scope,
          isPullSalesInvoiceSelectable,
          (api) => salesInvoiceService.listPartnerStatementPullCandidates(api),
        );
      } catch (e: unknown) {
        messageApi.error(resolveApiErrorMessage(e, t(`${P}.loadSourceFailed`)));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const sourceIds = resolvePullConfirmNumericIds(keys, rows, 'id');
      if (!sourceIds.length) {
        showPullFlowNotice(
          'warning',
          t(`${P}.selectSource`, { label: pullFromPartnerStatementAction.sourceLabel }),
        );
        return;
      }
      const selectedIdSet = new Set(sourceIds);
      const selected = rows.filter((x) => selectedIdSet.has(Number(x.id)));
      const partnerKeys = new Set(
        selected.map((x) => resolvePullQueryPartnerKey(x)).filter(Boolean),
      );
      if (partnerKeys.size > 1) {
        showPullFlowNotice('warning', t(`${P}.pull.sameCustomerRequired`));
        return;
      }
      const ledgerModes = new Set(
        selected.map((x) => (x.ledger_posting_mode === 'by_invoice' ? 'by_invoice' : 'immediate')),
      );
      if (ledgerModes.size > 1) {
        showPullFlowNotice('warning', t(`${P}.pull.partnerStatementSameLedgerModeRequired`));
        return;
      }
      const mode = ledgerModes.values().next().value as 'by_invoice' | 'immediate';
      if (mode === 'by_invoice') {
        const deliveryIds = Array.from(
          new Set(
            selected.flatMap((row) =>
              (row.delivery_ids || []).map((id) => Number(id)).filter((id) => id > 0),
            ),
          ),
        );
        if (!deliveryIds.length) {
          showPullFlowNotice('warning', t('app.kuaicaiwu.partnerStatement.detail.pushSelectDelivery'));
          return;
        }
        await openPullPreview('sales_delivery', deliveryIds, {
          closeSourceModal: () => pullFromPartnerStatementCloseRef.current?.(),
          reopenSourceModal: () => pullFromPartnerStatementOpenRef.current?.(),
          partnerStatementIds: sourceIds,
          partnerStatementCodes: selected.map((row) =>
            String(row.statement_code || row.doc_code || '').trim(),
          ).filter(Boolean),
        });
        return;
      }
      const receivableIds = Array.from(
        new Set(
          selected.flatMap((row) =>
            (row.receivable_ids || []).map((id) => Number(id)).filter((id) => id > 0),
          ),
        ),
      );
      if (!receivableIds.length) {
        showPullFlowNotice('warning', t('app.kuaicaiwu.partnerStatement.detail.pushSelectReceivable'));
        return;
      }
      await openPullPreview('receivable', receivableIds, {
        closeSourceModal: () => pullFromPartnerStatementCloseRef.current?.(),
        reopenSourceModal: () => pullFromPartnerStatementOpenRef.current?.(),
        partnerStatementIds: sourceIds,
        partnerStatementCodes: selected.map((row) =>
          String(row.statement_code || row.doc_code || '').trim(),
        ).filter(Boolean),
      });
    },
    onConfirmFailed: pullConfirmFailed,
  });
  pullFromPartnerStatementCloseRef.current = pullFromPartnerStatementQuery.closeModal;
  pullFromPartnerStatementOpenRef.current = pullFromPartnerStatementQuery.openModal;

  const handlePullCreateSubmit = async (values: any) => {
    if (!pullPreviewData || !pullPreviewSourceId || !pullPreviewKind) {
      messageApi.warning(t(`${P}.pullPreviewIncomplete`));
      return false;
    }
    if (pullPreviewData.has_blocking_issues) {
      messageApi.warning(
        salesInvoiceCapabilityReasonMessage(pullPreviewData.blocking_reason, t)
          || t(`${P}.pullPreviewBlocked`),
      );
      return false;
    }
    const maxPush =
      Number(
        pullPreviewData.max_push_total
          ?? (pullPreviewData.items || []).reduce(
            (sum, row) => sum + Number(row.max_push_quantity ?? 0),
            0,
          ),
      ) || 0;
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
    if (moneyExceedsMax(estimatedTotal, maxPush)) {
      messageApi.warning(t(`${P}.pullExceedMax`, { max: formatCurrencyAmount(maxPush) }));
      return false;
    }
    let detailItems: Record<string, unknown>[] | undefined;
    if (pullReceiptLineSelectEnabled) {
      if (pullReceiptSelectedIds.length === 0) {
        messageApi.warning(t(`${P}.pull.selectAtLeastOneLine`));
        return false;
      }
      const detailLines = (pullPreviewData.detail_lines ?? []) as PullReceiptFinanceDetailLine[];
      const reconciled = reconcilePullReceiptLinesForHeaderAmount(
        pullReceiptSelectedIds,
        detailLines,
        estimatedTotal,
        pullReceiptLineAmounts,
      );
      if (reconciled.selectedItemIds.length === 0) {
        messageApi.warning(t(`${P}.pull.selectAtLeastOneLine`));
        return false;
      }
      if (Math.abs(reconciled.lineSum - estimatedTotal) > 0.009) {
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
      const fallbackDocId = pullPreviewSourceId ?? pullPreviewSourceIds[0];
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
      const fallbackType =
        pullPreviewKind === 'receivable'
          ? 'receivable'
          : pullPreviewKind === 'sales_order'
            ? 'sales_order'
            : 'sales_delivery';
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
      ) as Record<string, unknown>[];
      if (!detailItems.length) {
        messageApi.warning(t(`${P}.pull.selectAtLeastOneLine`));
        return false;
      }
    }
    if (
      pullPreviewKind
      && (pullPreviewKind === 'sales_delivery'
        || pullPreviewKind === 'receivable'
        || pullPreviewKind === 'sales_order')
      && !(detailItems?.length)
    ) {
      messageApi.warning(t(`${P}.detailPullRequiresDetailLines`));
      return false;
    }
    const wantReceipt = Boolean(values.concurrent_receipt_enabled) && pullPreviewKind === 'receivable';
    if (wantReceipt) {
      const settleAmt = Number(values.settle_amount) || 0;
      const maxSettle = Number(pullPreviewData.remaining_settle_amount ?? 0);
      if (settleAmt <= 0) {
        messageApi.warning(t(`${P}.concurrentReceiptAmountRequired`));
        return false;
      }
      if (settleAmt > maxSettle) {
        messageApi.warning(t(`${P}.concurrentReceiptExceedMax`, { max: formatCurrencyAmount(maxSettle) }));
        return false;
      }
      try {
        assertBankAccountForPaymentMethod(values.payment_method, values.bank_account_id, t);
      } catch (e: unknown) {
        messageApi.warning(e instanceof Error ? e.message : t(`${P}.concurrentReceiptAccountRequired`));
        return false;
      }
    }
    const sourceLabel =
      pullPreviewKind === 'sales_order'
        ? pullFromSalesOrderAction.sourceLabel
        : pullPreviewKind === 'sales_delivery'
          ? pullFromSalesDeliveryAction.sourceLabel
          : pullFromReceivableAction.sourceLabel;
    const departmentPayload = resolvePurchaseDepartmentPayload(
      values.department_id,
      resolveDepartmentName,
      values.department_name,
    );
    const pullLedgerMode =
      pullPreviewData.ledger_posting_mode === 'by_invoice' ? 'by_invoice' : 'immediate';
    setPullSubmitting(true);
    try {
      await apiRequest('/apps/kuaicaiwu/sales-invoices', {
        method: 'POST',
        data: {
          settlement_mode: 'detail',
          customer_id: pullPreviewData.customer_id,
          customer_name: pullPreviewData.customer_name || '',
          settlement_closing_date: formatDateTime(
            values.settlement_closing_date || values.invoice_date || dayjs(),
            'YYYY-MM-DD',
          ),
          department_id: departmentPayload.department_id,
          department_name: departmentPayload.department_name,
          ledger_posting_mode: pullLedgerMode,
          sales_order_id: pullPreviewData.sales_order_id ?? undefined,
          sales_order_code: pullPreviewData.sales_order_code ?? pullPreviewData.source_code,
          receivable_id: pullPreviewKind === 'receivable' ? pullPreviewSourceId : pullPreviewData.receivable_id,
          receivable_code: pullPreviewKind === 'receivable' ? pullPreviewData.source_code : pullPreviewData.receivable_code,
          source_type: pullPreviewKind,
          source_id: pullPreviewSourceId,
          detail_items: detailItems,
          invoice_number: String(values.invoice_number ?? '').trim(),
          invoice_date: formatDateTime(values.invoice_date || dayjs(), 'YYYY-MM-DD'),
          invoice_type: values.invoice_type || '增值税专用发票',
          tax_rate: taxRate,
          invoice_amount: invoiceAmount,
          total_amount: estimatedTotal,
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
              : t(`${P}.pullNotes`, { source: sourceLabel, code: pullPreviewData.source_code })),
          attachments: normalizeDocumentAttachments(values.attachments),
          ...(pullPartnerStatementIdsRef.current.length
            ? { partner_statement_ids: pullPartnerStatementIdsRef.current }
            : {}),
          ...(wantReceipt
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
        },
      });
      messageApi.success(
        wantReceipt
          ? t(`${P}.pullCreateWithReceiptSuccess`, { target: pullFromReceivableAction.targetLabel })
          : t(`${P}.pullCreateSuccess`, { target: pullFromSalesOrderAction.targetLabel }),
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

  const executeDelete = async (record: SalesInvoice) => {
    try {
      await apiRequest(`/apps/kuaicaiwu/sales-invoices/${record.id}`, { method: 'DELETE' });
      messageApi.success(t('common.deleteSuccess'));
      actionRef.current?.reload();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.operationFailed'));
    }
  };

  const handleBatchDelete = async (keys: React.Key[]) => {
    try {
      for (const id of keys) {
        await apiRequest(`/apps/kuaicaiwu/sales-invoices/${id}`, { method: 'DELETE' });
      }
      messageApi.success(t(`${P}.batchDeleteSuccess`, { count: keys.length }));
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error?.message || t('common.batchDeleteFailed'));
    }
  };

  const salesInvoiceToolbarAuditMenus = useMemo(() => {
    const selected = tableRowsRef.current.filter((row) => selectedRowKeys.includes(row.id));
    const reviewOf = (row: SalesInvoice) => salesInvoiceReviewRaw(row);
    const allowed = (row: SalesInvoice, key: string) => pickCapability(row, key)?.allowed === true;
    const run = (
      records: SalesInvoice[],
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
        onSuccess: () => {
          setSelectedRowKeys([]);
          actionRef.current?.reload();
        },
        message: messageApi,
        t,
      });
    const submitRows = selected.filter((row) => allowed(row, 'submit'));
    const canSubmit = Boolean(salesInvoicePerms.canAction?.('submit'));
    const submitDisabled = !selected.some((row) => allowed(row, 'submit'));
    const onBatchSuccess = () => {
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    };
    const submitItems: UniBatchMenuItem[] = withDocumentSubmitCombinedItem(
      [
        {
          key: 'submit',
          label: t('common.submit'),
          disabled: submitDisabled,
          onClick: () =>
            run(submitRows, 'submit', canSubmit, (id) => salesInvoiceService.commitSalesInvoice(id)),
        },
        {
          key: 'withdraw-submit',
          label: t(`${P}.toolbar.withdrawSubmit`),
          disabled: !selected.some((row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'withdraw_submit')),
          onClick: () =>
            run(
              selected.filter((row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'withdraw_submit')),
              'withdraw_submit',
              canSubmit,
              (id) => salesInvoiceService.withdrawSalesInvoice(id),
            ),
        },
        {
          key: 'submit-review',
          label: t(`${P}.toolbar.submitReview`),
          disabled: !selected.some((row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'submit_review')),
          onClick: () =>
            run(
              selected.filter((row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'submit_review')),
              'submit_review',
              canSubmit,
              (id) => salesInvoiceService.submitSalesInvoiceForReview(id),
              t(`${P}.toolbar.submitReviewNotAllowed`),
            ),
        },
      ],
      {
        t,
        message: messageApi,
        disabled: submitDisabled,
        commitRecords: submitRows,
        permAllowed: canSubmit,
        commit: (id) => salesInvoiceService.commitSalesInvoice(id),
        submitReview: (id) => salesInvoiceService.submitSalesInvoiceForReview(id),
        onSuccess: onBatchSuccess,
      },
    );
    const approveRows = selected.filter(
      (row) => reviewOf(row) !== 'SUBMITTED' && isPendingReviewStatus(reviewOf(row)) && allowed(row, 'approve'),
    );
    const auditItems: UniBatchMenuItem[] = [
      {
        key: 'approve',
        label: t('components.uniAction.audit'),
        disabled: !selected.some(
          (row) => reviewOf(row) !== 'SUBMITTED' && isPendingReviewStatus(reviewOf(row)) && allowed(row, 'approve'),
        ),
        onClick: () =>
          void runSalesInvoiceAuditBatch(
            'approve',
            approveRows.map((row) => Number(row.id)),
            approveRows,
            salesInvoiceAuditEnabled,
          ),
      },
      {
        key: 'withdraw-review',
        label: t(`${P}.toolbar.withdrawReview`),
        disabled: !selected.some(
          (row) => reviewOf(row) !== 'SUBMITTED' && isPendingReviewStatus(reviewOf(row)) && allowed(row, 'withdraw_submit'),
        ),
        onClick: () =>
          run(
            selected.filter(
              (row) => reviewOf(row) !== 'SUBMITTED' && isPendingReviewStatus(reviewOf(row)) && allowed(row, 'withdraw_submit'),
            ),
            'withdraw_submit',
            Boolean(salesInvoicePerms.canAction?.('submit')),
            (id) => salesInvoiceService.withdrawSalesInvoice(id),
          ),
      },
      {
        key: 'revoke',
        label: t(`${P}.toolbar.revoke`),
        disabled: !selected.some((row) => allowed(row, 'revoke_approval')),
        onClick: () =>
          run(
            selected.filter((row) => allowed(row, 'revoke_approval')),
            'revoke_approval',
            Boolean(salesInvoicePerms.canAction?.('revoke')),
            (id) => salesInvoiceService.revokeSalesInvoice(id),
          ),
      },
    ];
    return { submitItems, auditItems };
  }, [
    selectedRowKeys,
    salesInvoicePerms,
    salesInvoiceAuditEnabled,
    runSalesInvoiceAuditBatch,
    messageApi,
    t,
  ]);

  const openEditModal = (record: SalesInvoice) => {
    setEditingRecord(record);
    setEditVisible(true);
  };

  const handleEditSubmit = async (values: { invoice_number?: string; invoice_date?: unknown; attachments?: unknown }) => {
    if (!editingRecord) return false;
    setEditSubmitting(true);
    try {
      await apiRequest(`/apps/kuaicaiwu/sales-invoices/${editingRecord.id}`, {
        method: 'PUT',
        data: {
          invoice_number: String(values.invoice_number ?? '').trim(),
          invoice_date: formatDateTime(
            values.invoice_date || editingRecord.invoice_date || dayjs(),
            'YYYY-MM-DD',
          ),
          attachments: normalizeDocumentAttachments(values.attachments),
        },
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

  const columns: ProColumns<SalesInvoice>[] = useMemo(
    () => [
      ...financeDocCodePartnerSearchColumns({
        docCodeLabel: t(`${P}.col.internalCode`),
        docCodeField: 'invoice_code',
        partnerLabel: t('app.kuaicaiwu.common.customer'),
        partnerIdField: 'customer_id',
        partnerNameField: 'customer_name',
        partnerOptions: customerOptions,
      }),
      financeInvoiceNumberSearchColumn(t('app.kuaicaiwu.invoice.col.invoiceNumber')),
      {
        // 有 RemainderFlex：主标识叠列 KeepWidth
        title: t(`${P}.col.internalCode`),
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
        render: (_, r) => (
          <UniTableStackedPrimaryCell
            primary={String(r.customer_name ?? '')}
            secondary={String(r.invoice_code ?? displaySalesInvoiceListCode(r))}
            onSecondaryClick={() =>
              navigate(`${DETAIL_LIST_BASE}/${r.id}`)
            }
          />
        ),
      },
      {
        title: t('app.kuaicaiwu.common.customer'),
        dataIndex: 'customer_name',
        hideInTable: true,
      },
      {
        title: t('app.kuaicaiwu.invoice.col.invoiceNumber'),
        dataIndex: 'invoice_number',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
      },
      {
        title: t(`${P}.col.invoiceType`),
        dataIndex: 'invoice_type',
        width: 140,
        minWidth: 140,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
        render: (_, r) => renderFinanceTypeMarker(formatChineseInvoiceType(r.invoice_type, t)),
      },
      {
        title: t(`${P}.col.partnerTaxNo`),
        dataIndex: 'partner_tax_no',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        ellipsis: true,
        render: (_, r) => r.partner_tax_no || '—',
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
        title: t('app.kuaicaiwu.invoice.col.totalAmount'),
        dataIndex: 'total_amount',
        valueType: 'money',
        align: 'right',
        width: 130,
        minWidth: 130,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        sorter: true,
        render: (_, record) => (
          <span style={{ fontWeight: 'bold', color: '#1677ff' }}>
            {formatCurrencyAmount(record.total_amount)}
          </span>
        ),
      },
      {
        title: t(`${P}.col.linkedReceivable`),
        key: 'finance_linked_receivable',
        dataIndex: 'receivable_code',
        width: 140,
        minWidth: 140,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        render: (_, r) =>
          r.receivable_id != null && r.receivable_id !== undefined ? (
            <Typography.Link onClick={() => navigate(`/apps/kuaicaiwu/finance-management/receivables/${r.receivable_id}`)}>
              {r.receivable_code || `#${r.receivable_id}`}
            </Typography.Link>
          ) : (
            '—'
          ),
      },
      {
        // 备注长短不一：唯一 RemainderFlex
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
      ...financeDocCreatedUpdatedColumns<SalesInvoice>(t),
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
          if (canFillSalesInvoiceNumber(record) && salesInvoicePerms.canUpdate) {
            acts.push(
              <Button key="edit" {...rowActionFillInvoiceNumber('update')} onClick={() => openEditModal(record)} />,
            );
          }
          acts.push(
            <Button
              key="det"
              {...rowActionKind('read')}
              onClick={() => navigate(`${DETAIL_LIST_BASE}/${record.id}`)}
            />,
          );
          if (canDeleteSalesInvoice(record) && salesInvoicePerms.canDelete) {
            acts.push(
              <ActionConfirmPopconfirm title={t(`${P}.deleteTitle`)} description={t(`${P}.deleteContent`, {
        number: record.invoice_number?.trim() || displaySalesInvoiceListCode(record),
      })} onConfirm={() => executeDelete(record)}>
              <Button key="del" {...rowActionKind('delete')} onClick={(e) => e.stopPropagation()} />
            </ActionConfirmPopconfirm>,
            );
          }
          return acts;
        },
      },
    ],
    [t, navigate, reviewStatusEnum, customerOptions, salesInvoicePerms],
  );


  const pullDeliveryColumns = useMemo(
    () => [
      {
        title: t(`${P}.pull.col.deliveryDate`),
        dataIndex: 'source_date',
        width: 120,
        render: (v: string) => (v ? formatDateTime(v, 'YYYY-MM-DD') : '-'),
      },
      {
        title: t(`${P}.pull.col.deliveryCode`),
        dataIndex: 'delivery_code',
        width: 168,
        ellipsis: true,
        render: (_: unknown, row: SalesInvoicePullCandidate) =>
          row.delivery_code || row.doc_code || row.code,
      },
      {
        title: t('app.kuaicaiwu.common.customer'),
        dataIndex: 'customer_name',
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
        render: (_: unknown, row: SalesInvoicePullCandidate) =>
          formatCurrencyAmount(row.invoiceable_amount ?? row.amount ?? 0),
      },
      {
        title: t(`${P}.pull.col.invoicedAmount`),
        dataIndex: 'invoiced_amount',
        width: 120,
        align: 'right' as const,
        render: (v: number) => formatCurrencyAmount(v || 0),
      },
    ],
    [t],
  );

  const pullReceivableColumns = useMemo(
    () => [
      {
        title: t('components.uniPullQuery.documentDateColumn'),
        dataIndex: 'source_date',
        width: 120,
        render: (v: string) => (v ? formatDateTime(v, 'YYYY-MM-DD') : '-'),
      },
      {
        title: t(`${P}.pull.col.receivableCode`),
        dataIndex: 'receivable_code',
        width: 168,
        ellipsis: true,
        render: (_: unknown, row: SalesInvoicePullCandidate) =>
          row.receivable_code || row.doc_code || row.code,
      },
      {
        title: t('app.kuaicaiwu.common.customer'),
        dataIndex: 'customer_name',
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
        render: (_: unknown, row: SalesInvoicePullCandidate) =>
          formatCurrencyAmount(row.invoiceable_amount ?? row.amount ?? 0),
      },
      {
        title: t(`${P}.pull.col.invoicedAmount`),
        dataIndex: 'invoiced_amount',
        width: 120,
        align: 'right' as const,
        render: (v: number) => formatCurrencyAmount(v || 0),
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
        render: (v: string) => (v ? formatDateTime(v, 'YYYY-MM-DD') : '-'),
      },
      {
        title: t('app.kuaicaiwu.partnerStatement.col.code'),
        dataIndex: 'statement_code',
        width: 168,
        ellipsis: true,
        render: (_: unknown, row: SalesInvoicePullCandidate) =>
          row.statement_code || row.doc_code || row.code,
      },
      {
        title: t('app.kuaicaiwu.partnerStatement.col.customerName'),
        dataIndex: 'customer_name',
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
        render: (_: unknown, row: SalesInvoicePullCandidate) =>
          formatCurrencyAmount(row.period_amount ?? row.amount ?? 0),
      },
      {
        title: t(`${P}.pull.col.invoiceableAmount`),
        dataIndex: 'invoiceable_amount',
        width: 120,
        align: 'right' as const,
        render: (v: number) => formatCurrencyAmount(v || 0),
      },
      {
        title: t(`${P}.pull.col.invoicedAmount`),
        dataIndex: 'invoiced_amount',
        width: 120,
        align: 'right' as const,
        render: (v: number) => formatCurrencyAmount(v || 0),
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
      { title: t('app.kuaicaiwu.common.customer'), dataIndex: 'customer_name', width: 220, ellipsis: true },
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
        render: (v: string) => {
          const { text, color } = getStatusDisplay(v);
          return text === '-' ? '-' : <MarkerTag color={color}>{text}</MarkerTag>;
        },
      },
      {
        title: t('app.kuaicaiwu.common.businessDate'),
        dataIndex: 'source_date',
        width: 130,
        render: (v: string) => (v ? formatDateTime(v, 'YYYY-MM-DD') : '-'),
      },
      {
        title: t('app.kuaicaiwu.invoice.col.totalAmount'),
        dataIndex: 'amount',
        width: 140,
        align: 'right' as const,
        render: (v: number) => formatCurrencyAmount(v || 0),
      },
    ],
    [t],
  );

  const pullPreviewMaxPush =
    Number(
      pullPreviewData?.max_push_total
        ?? (pullPreviewData?.items || []).reduce(
          (sum, row) => sum + Number(row.max_push_quantity ?? 0),
          0,
        ),
    ) || 0;
  const pullPreviewTargetLabel =
    pullPreviewKind === 'sales_delivery'
      ? pullFromSalesDeliveryAction.targetLabel
      : pullPreviewKind === 'receivable'
        ? pullFromReceivableAction.targetLabel
        : pullFromSalesOrderAction.targetLabel;

  const pullFormInitialValues = useMemo(() => {
    if (!pullPreviewData || !pullPreviewKind) return undefined;
    const maxPush =
      Number(
        pullPreviewData.max_push_total
          ?? (pullPreviewData.items || []).reduce(
            (sum, row) => sum + Number(row.max_push_quantity ?? 0),
            0,
          ),
      ) || 0;
    const taxRate = 13;
    const defaultIncl = maxPush > 0 ? maxPush : undefined;
    const sourceLabel =
      pullPreviewKind === 'sales_order'
        ? pullFromSalesOrderAction.sourceLabel
        : pullPreviewKind === 'sales_delivery'
          ? pullFromSalesDeliveryAction.sourceLabel
          : pullFromReceivableAction.sourceLabel;
    const maxSettle = Number(pullPreviewData.remaining_settle_amount ?? 0);
    const ledgerMode =
      pullPreviewData.ledger_posting_mode === 'by_invoice' ? 'by_invoice' : 'immediate';
    const deptUuid = currentUser?.department?.uuid;
    if (deptUuid) {
      pullApplicantDepartmentUuidRef.current = deptUuid;
    }
    const deptDefaults = resolvePurchaseDepartmentFromApplicant(deptUuid, departmentOptions);
    const invoiceDay = dayjs();
    return {
      source_code: pullPreviewData.source_code,
      customer_name: pullPreviewData.customer_name,
      invoice_date: invoiceDay,
      settlement_closing_date: invoiceDay,
      ledger_posting_mode: ledgerMode,
      ...deptDefaults,
      invoice_type: '增值税专用发票',
      tax_rate: taxRate,
      amount_input_mode: 'tax_inclusive' as InvoiceAmountInputMode,
      invoice_amount: defaultIncl,
      notes:
        pullPartnerStatementIdsRef.current.length
          ? t('app.kuaicaiwu.common.createdFromSourceNote', {
              source: pullFromPartnerStatementAction.sourceLabel,
              code: (pullPartnerStatementCodesRef.current.length
                ? pullPartnerStatementCodesRef.current
                : pullPartnerStatementIdsRef.current.map(String)
              ).join('、'),
            })
          : t(`${P}.pullNotes`, { source: sourceLabel, code: pullPreviewData.source_code }),
      concurrent_receipt_enabled: false,
      settle_amount: maxSettle > 0 ? maxSettle : undefined,
      settle_date: dayjs(),
      payment_method: BANK_TRANSFER_PAYMENT_METHOD,
    };
  }, [
    pullPreviewData,
    pullPreviewKind,
    pullFromSalesOrderAction.sourceLabel,
    pullFromSalesDeliveryAction.sourceLabel,
    pullFromReceivableAction.sourceLabel,
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
      pullReceivableId?: number;
      openSalesInvoicePullFromPartnerStatement?: boolean;
    } | null;
    if (state?.openSalesInvoicePullFromPartnerStatement) {
      pullFromPartnerStatementQuery.openModal();
      navigate(location.pathname, { replace: true, state: null });
      return;
    }
    const pullReceivableId = state?.pullReceivableId;
    if (!pullReceivableId) return;
    void openPullPreview('receivable', pullReceivableId);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.state, location.pathname, navigate, pullFromPartnerStatementQuery]);

  useEffect(() => {
    if (!pullPreviewOpen || pullPreviewLoading || !pullFormInitialValues) return;
    pullAmountModeRef.current = 'tax_inclusive';
    pullTaxRateRef.current = Number(pullFormInitialValues.tax_rate) || 13;
    pullForm.setFieldsValue(pullFormInitialValues);
  }, [pullPreviewOpen, pullPreviewLoading, pullFormInitialValues, pullForm]);

  useEffect(() => {
    if (!pullPreviewOpen || !pullPreviewData) return;
    if (
      pullPreviewKind !== 'sales_delivery'
      && pullPreviewKind !== 'receivable'
      && pullPreviewKind !== 'sales_order'
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
    const { selectedItemIds, amounts } = initPullReceiptLineSelection(lines);
    let effectiveIds = selectedItemIds;
    let effectiveAmounts = amounts;
    const headerCap = resolveSalesInvoicePullPreviewCap(pullPreviewData);
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

  const salesDetailPullLineColumns = useMemo(
    () =>
      buildSalesDetailInvoicePullLineColumns({
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
        formatPercent: (rate) =>
          rate != null && Number.isFinite(Number(rate)) ? `${Number(rate)}%` : '-',
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
    const detailLines = (pullPreviewData.detail_lines ?? []) as PullReceiptFinanceDetailLine[];
    const currentSum = sumPullReceiptLineAmounts(pullReceiptSelectedIds, pullReceiptLineAmounts);
    if (Math.abs(currentSum - totalIncl) <= 0.009) return;
    const reconciled = reconcilePullReceiptLinesForHeaderAmount(
      pullReceiptSelectedIds,
      detailLines,
      totalIncl,
      pullReceiptLineAmounts,
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
    pullPreviewMaxPush,
  ]);

  const handlePullPreviewOk = async () => {
    if (pullPreviewLoading || !pullPreviewData) {
      messageApi.warning(t(`${P}.pullPreviewIncomplete`));
      return;
    }
    if (pullPreviewData.has_blocking_issues) {
      messageApi.warning(
        salesInvoiceCapabilityReasonMessage(pullPreviewData.blocking_reason, t)
          || t(`${P}.pullPreviewBlocked`),
      );
      return;
    }
    if (pullPreviewMaxPush <= 0) {
      messageApi.warning(t(`${P}.pullNoInvoiceableAmount`));
      return;
    }
    try {
      const values = await pullForm.validateFields();
      await handlePullCreateSubmit(values);
    } catch {
      messageApi.warning(t(`${P}.pullFormValidationFailed`));
    }
  };

  return (
    <>
    <FinanceInvoiceSettlementModeAlert pageMode="detail" kind="sales">
    <ListPageTemplate>
      <UniTable<SalesInvoice>
        headerTitle={t(`${PAGE}.pageTitle`)}
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.salesInvoice)}
        actionRef={actionRef}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        onTableDataChange={(rows) => {
          tableRowsRef.current = rows;
        }}
        rowKey="id"
        columnPersistenceId="apps.kuaicaiwu.pages.finance-management.sales-detail-invoices.list-v1"
        showAdvancedSearch
        showCreateButton={false}
        createButtonText={t(`${P}.createTitle`)}
        onCreate={() => setCreateModalVisible(true)}
        showDeleteButton
        deleteButtonText={t('common.delete')}
        onDelete={handleBatchDelete}
        toolBarActions={[
          <UniBatchMenuButton
            key="sales-invoice-submit"
            selectedRowKeys={selectedRowKeys}
            buttonText={t('common.submit')}
            menuItems={salesInvoiceToolbarAuditMenus.submitItems}
          />,
          <UniBatchMenuButton
            key="sales-invoice-audit"
            selectedRowKeys={selectedRowKeys}
            buttonText={t('components.uniAction.audit')}
            menuItems={salesInvoiceToolbarAuditMenus.auditItems}
          />,
        ]}
        deleteConfirmTitle={t('app.kuaicaiwu.common.confirmBatchDelete')}
        deleteConfirmDescription={(count) => t(`${P}.batchDeleteConfirm`, { count })}
        toolBarRender={() => [
          <UniPullCreateToolbar
            compactKey="create-sales-detail-invoice-with-pull"
            createIcon={<PlusOutlined />}
            createLabel={t(`${PAGE}.createTitle`)}
            onCreate={() => messageApi.warning(t(`${P}.detailRegisterFromSourceOnly`))}
            menuItems={[
              ...buildKuaicaiwuPullCreateMenuItems([
                {
                  key: 'pull-from-sales-order',
                  actionKey: 'sales_invoice.pull_from_sales_order',
                  onClick: () => {
                    pullFromSalesOrderQuery.openModal();
                  },
                },
                {
                  key: 'pull-from-sales-delivery',
                  actionKey: 'sales_invoice.pull_from_sales_delivery',
                  onClick: () => {
                    pullFromSalesDeliveryQuery.openModal();
                  },
                },
                {
                  key: 'pull-from-receivable',
                  actionKey: 'sales_invoice.pull_from_receivable',
                  onClick: () => {
                    pullFromReceivableQuery.openModal();
                  },
                },
              ]),
              { key: 'copy-divider', type: 'divider' },
              {
                key: 'copy-selected',
                label: t(`${P}.copySelectedCreate`),
                disabled: selectedRowKeys.length !== 1,
                onClick: () => {
                  const row = tableRowsRef.current.find((item) => selectedRowKeys.includes(item.id));
                  if (!row) return;
                  setCreateSeed({
                    customer_id: row.customer_id,
                    invoice_type: row.invoice_type,
                    tax_rate: row.tax_rate,
                    invoice_amount: row.invoice_amount,
                    invoice_date: dayjs(),
                    notes: row.notes,
                    partner_tax_no: row.partner_tax_no,
                    partner_bank_info: row.partner_bank_info,
                    partner_address_phone: row.partner_address_phone,
                  });
                  setCreateModalVisible(true);
                },
              },
            ]}
          />,
        ]}
        request={async (params, sort, _filter, searchFormValues) => {
          const listParams = resolveSalesInvoiceListParams(searchFormValues, sort);
          lastListParamsRef.current = listParams;
          const apiParams: SalesInvoiceListParams = {
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize || 20,
            settlement_mode: 'detail',
            ...listParams,
          };
          const res = await salesInvoiceService.list(apiParams);
          return {
            data: res?.items || [],
            total: res?.total || 0,
            success: true,
          };
        }}
        skipFuzzyPinyinClientFilter
        pinnedTabsField={FINANCE_INVOICE_PINNED_REVIEW_FIELD}
        columns={alignProColumns(columns, SALES_DOC_LIST_FIELD_RANK)}
      />

      <UniPullQueryModal<SalesInvoicePullCandidate>
        open={pullFromSalesOrderQuery.open}
        title={pullFromSalesOrderAction.label}
        onCancel={pullFromSalesOrderQuery.closeModal}
        onOk={pullFromSalesOrderQuery.handleConfirm}
        zIndex={pullQueryModalZIndex}
        rowKey="id"
        columns={pullTableColumns}
        dataSource={pullFromSalesOrderQuery.dataSource}
        loading={pullFromSalesOrderQuery.loading}
        confirmLoading={pullFromSalesOrderQuery.confirmLoading}
        selectionType={pullFromSalesOrderQuery.selectionType}
        selectedRowKeys={pullFromSalesOrderQuery.selectedRowKeys}
        selectedRows={pullFromSalesOrderQuery.selectedRows}
        onSelectedRowKeysChange={pullFromSalesOrderQuery.handleSelectedRowKeysChange}
        isRowDisabled={orderPullRowDisabled}
        searchDraft={pullFromSalesOrderQuery.searchDraft}
        onSearchDraftChange={pullFromSalesOrderQuery.setSearchDraft}
        onSearchApply={pullFromSalesOrderQuery.handleSearchApply}
        onSearchClear={pullFromSalesOrderQuery.handleSearchClear}
        appliedKeyword={pullFromSalesOrderQuery.appliedKeyword}
        searchPlaceholder={t(`${P}.pull.searchPlaceholder`)}
        page={pullFromSalesOrderQuery.page}
        pageSize={pullFromSalesOrderQuery.pageSize}
        total={pullFromSalesOrderQuery.total}
        onPageChange={pullFromSalesOrderQuery.handlePageChange}
        scopeOptions={pullFromSalesOrderQuery.scopeOptions}
        scope={pullFromSalesOrderQuery.scope}
        onScopeChange={pullFromSalesOrderQuery.handleScopeChange}
        pullQuery={pullFromSalesOrderQuery.pullQuery}
        okText={pullFromSalesOrderAction.targetLabel}
      />

      <UniPullQueryModal<SalesInvoicePullCandidate>
        open={pullFromSalesDeliveryQuery.open}
        title={pullFromSalesDeliveryAction.label}
        onCancel={pullFromSalesDeliveryQuery.closeModal}
        onOk={pullFromSalesDeliveryQuery.handleConfirm}
        zIndex={pullQueryModalZIndex}
        rowKey="id"
        columns={pullDeliveryColumns}
        dataSource={pullFromSalesDeliveryQuery.dataSource}
        loading={pullFromSalesDeliveryQuery.loading}
        confirmLoading={pullFromSalesDeliveryQuery.confirmLoading}
        selectionType={pullFromSalesDeliveryQuery.selectionType}
        selectedRowKeys={pullFromSalesDeliveryQuery.selectedRowKeys}
        selectedRows={pullFromSalesDeliveryQuery.selectedRows}
        onSelectedRowKeysChange={pullFromSalesDeliveryQuery.handleSelectedRowKeysChange}
        isRowDisabled={deliveryPullRowDisabled}
        searchDraft={pullFromSalesDeliveryQuery.searchDraft}
        onSearchDraftChange={pullFromSalesDeliveryQuery.setSearchDraft}
        onSearchApply={pullFromSalesDeliveryQuery.handleSearchApply}
        onSearchClear={pullFromSalesDeliveryQuery.handleSearchClear}
        appliedKeyword={pullFromSalesDeliveryQuery.appliedKeyword}
        searchPlaceholder={t(`${P}.pull.searchPlaceholder`)}
        page={pullFromSalesDeliveryQuery.page}
        pageSize={pullFromSalesDeliveryQuery.pageSize}
        total={pullFromSalesDeliveryQuery.total}
        onPageChange={pullFromSalesDeliveryQuery.handlePageChange}
        scopeOptions={pullFromSalesDeliveryQuery.scopeOptions}
        scope={pullFromSalesDeliveryQuery.scope}
        onScopeChange={pullFromSalesDeliveryQuery.handleScopeChange}
        pullQuery={pullFromSalesDeliveryQuery.pullQuery}
        okText={pullFromSalesDeliveryAction.targetLabel}
      />

      <UniPullQueryModal<SalesInvoicePullCandidate>
        open={pullFromReceivableQuery.open}
        title={pullFromReceivableAction.label}
        onCancel={pullFromReceivableQuery.closeModal}
        onOk={pullFromReceivableQuery.handleConfirm}
        zIndex={pullQueryModalZIndex}
        rowKey="id"
        columns={pullReceivableColumns}
        dataSource={pullFromReceivableQuery.dataSource}
        loading={pullFromReceivableQuery.loading}
        confirmLoading={pullFromReceivableQuery.confirmLoading}
        selectionType={pullFromReceivableQuery.selectionType}
        selectedRowKeys={pullFromReceivableQuery.selectedRowKeys}
        selectedRows={pullFromReceivableQuery.selectedRows}
        onSelectedRowKeysChange={pullFromReceivableQuery.handleSelectedRowKeysChange}
        isRowDisabled={receivablePullRowDisabled}
        searchDraft={pullFromReceivableQuery.searchDraft}
        onSearchDraftChange={pullFromReceivableQuery.setSearchDraft}
        onSearchApply={pullFromReceivableQuery.handleSearchApply}
        onSearchClear={pullFromReceivableQuery.handleSearchClear}
        appliedKeyword={pullFromReceivableQuery.appliedKeyword}
        searchPlaceholder={t(`${P}.pull.searchPlaceholder`)}
        page={pullFromReceivableQuery.page}
        pageSize={pullFromReceivableQuery.pageSize}
        total={pullFromReceivableQuery.total}
        onPageChange={pullFromReceivableQuery.handlePageChange}
        scopeOptions={pullFromReceivableQuery.scopeOptions}
        scope={pullFromReceivableQuery.scope}
        onScopeChange={pullFromReceivableQuery.handleScopeChange}
        pullQuery={pullFromReceivableQuery.pullQuery}
        okText={pullFromReceivableAction.targetLabel}
      />

      <UniPullQueryModal<SalesInvoicePullCandidate>
        open={pullFromPartnerStatementQuery.open}
        title={pullFromPartnerStatementAction.label}
        onCancel={pullFromPartnerStatementQuery.closeModal}
        onOk={pullFromPartnerStatementQuery.handleConfirm}
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
                key={`pull-sales-invoice-${pullPreviewKind}-${pullPreviewSourceId}`}
                className={FINANCE_PULL_PREVIEW_FORM_CLASS}
                form={pullForm}
                initialValues={pullFormInitialValues}
                submitter={false}
                onFinish={handlePullCreateSubmit}
                layout="vertical"
                {...financeFormGridProps}
              >
                <ProFormText
                  name="source_code"
                  label={t(`${P}.form.sourceCode`)}
                  readonly
                  colProps={financeColFifth}
                />
                <ProFormText
                  name="invoice_number"
                  label={t('app.kuaicaiwu.invoice.col.invoiceNumber')}
                  placeholder={t(`${P}.form.invoiceNumberOptional`)}
                  colProps={financeColFifth}
                />
                <ProFormSelect
                  name="invoice_type"
                  label={t(`${P}.col.invoiceType`)}
                  options={invoiceTypeOptions}
                  rules={[{ required: true, message: t(`${P}.form.selectInvoiceType`) }]}
                  colProps={financeColFifth}
                />
                <ProFormDatePicker
                  name="invoice_date"
                  label={t('app.kuaicaiwu.common.invoiceDate')}
                  tooltip={t('app.kuaicaiwu.common.invoiceDateTip')}
                  rules={[{ required: true, message: t(`${P}.form.selectInvoiceDate`) }]}
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
                <ProFormItem label={t('app.kuaicaiwu.common.customer')} colProps={financeColFifth}>
                  <Input disabled value={pullPreviewData.customer_name || ''} placeholder="—" />
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
                  label={t(`${P}.form.taxRate`)}
                  options={TAX_RATE_OPTIONS}
                  rules={[{ required: true, message: t(`${P}.form.selectTaxRate`) }]}
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
                            columns={salesDetailPullLineColumns}
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
                <ProFormTextArea name="notes" label={t('common.remark')} fieldProps={{ rows: 2 }} colProps={financeColFull} />
                {canConcurrentReceipt ? (
                  <>
                    <ProFormSwitch
                      name="concurrent_receipt_enabled"
                      label={t(`${P}.concurrentReceipt`)}
                      extra={t(`${P}.concurrentReceiptHint`, {
                        max: formatAmount(pullPreviewData.remaining_settle_amount || 0),
                      })}
                      colProps={financeColFull}
                    />
                    {concurrentReceiptEnabled ? (
                      <>
                        <ProFormMoney
                          name="settle_amount"
                          label={t(`${P}.concurrentReceiptAmount`)}
                          min={0.01}
                          rules={[{ required: true, message: t(`${P}.concurrentReceiptAmountRequired`) }]}
                          colProps={financeColHalf}
                        />
                        <ProFormDatePicker
                          name="settle_date"
                          label={t('app.kuaicaiwu.receipt.col.receiptDate')}
                          rules={[{ required: true }]}
                          fieldProps={{ style: { width: '100%' } }}
                          colProps={financeColHalf}
                        />
                        <ProFormSelect
                          name="payment_method"
                          label={t('app.kuaicaiwu.receipt.col.paymentMethod')}
                          options={paymentMethodOptions}
                          rules={[{ required: true, message: t('app.kuaicaiwu.receipt.selectPaymentMethod') }]}
                          colProps={financeColHalf}
                        />
                        <LedgerAccountFormFields
                          accounts={bankAccounts}
                          accountLabel={t('app.kuaicaiwu.receipt.bankAccount')}
                          noteLabel={t('app.kuaicaiwu.receipt.bankAccountNote')}
                        />
                        <ProFormTextArea
                          name="settle_notes"
                          label={t(`${P}.concurrentReceiptNotes`)}
                          fieldProps={{ rows: 2 }}
                          colProps={financeColFull}
                        />
                      </>
                    ) : null}
                  </>
                ) : null}
                <DocumentAttachmentsField category="sales_invoice_attachments" />
              </ProForm>
          </div>
        ) : null}
      </Modal>

      <ModalForm
        title={
          editingRecord?.invoice_code
            ? t(`${P}.editNumberTitleWithCode`, { code: displaySalesInvoiceListCode(editingRecord) })
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
          attachments: mapAttachmentsToUploadList((editingRecord as any)?.attachments),
        }}
      >
        <ProFormText
          name="invoice_number"
          label={t('app.kuaicaiwu.invoice.col.invoiceNumber')}
          rules={[{ required: true, message: t(`${P}.form.invoiceNumberRequired`) }]}
          placeholder={t(`${P}.form.invoiceNumberRequired`)}
        />
        <ProFormDatePicker
          name="invoice_date"
          label={t('app.kuaicaiwu.common.invoiceDate')}
          tooltip={t('app.kuaicaiwu.common.invoiceDateTip')}
          rules={[{ required: true, message: t(`${P}.form.selectInvoiceDate`) }]}
          fieldProps={{ style: { width: '100%' }, format: 'YYYY-MM-DD' }}
        />
        <DocumentAttachmentsField category="sales_invoice_attachments" />
      </ModalForm>

      <ModalForm
        key={createSeed ? 'create-sales-invoice-copy' : 'create-sales-invoice'}
        title={t(`${P}.createTitle`)}
        open={createModalVisible}
        onOpenChange={(open) => {
          setCreateModalVisible(open);
          if (!open) setCreateSeed(undefined);
        }}
        onFinish={handleCreate}
        formRef={createFormRef}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        modalProps={{ destroyOnHidden: true }}
        initialValues={createSeed}
        {...financeFormGridProps}
      >
        <ProFormSelect
          name="customer_id"
          label={t('app.kuaicaiwu.common.customer')}
          options={customerOptions}
          rules={[{ required: true, message: t('app.kuaicaiwu.common.selectCustomer') }]}
          placeholder={t('app.kuaicaiwu.common.selectCustomer')}
          showSearch
          colProps={financeColHalf}
          fieldProps={{
            onChange: async (customerId: number) => {
              if (!customerId) return;
              try {
                const customer = await apiRequest<Record<string, unknown>>(
                  `/apps/master-data/supply-chain/customers/${customerId}`,
                  { method: 'GET' },
                );
                const tax =
                  String(customer.taxRegistrationNo ?? customer.tax_registration_no ?? '').trim();
                const addressPhone = [customer.invoiceAddress ?? customer.invoice_address, customer.invoicePhone ?? customer.invoice_phone]
                  .map((v) => String(v ?? '').trim())
                  .filter(Boolean)
                  .join(' ');
                createFormRef.current?.setFieldsValue({
                  partner_tax_no: tax || undefined,
                  partner_address_phone: addressPhone || undefined,
                });
              } catch {
                /* 客户开票资料不可用时保留手工录入 */
              }
            },
          }}
        />
        <ProFormText
          name="invoice_number"
          label={t('app.kuaicaiwu.invoice.col.invoiceNumber')}
          placeholder={t(`${P}.form.invoiceNumberOptional`)}
          colProps={financeColHalf}
        />
        <ProFormSelect
          name="invoice_type"
          label={t(`${P}.col.invoiceType`)}
          options={invoiceTypeOptions}
          initialValue="增值税专用发票"
          rules={[{ required: true, message: t(`${P}.form.selectInvoiceType`) }]}
          colProps={financeColHalf}
        />
        <ProFormDatePicker
          name="invoice_date"
          label={t('app.kuaicaiwu.common.invoiceDate')}
          tooltip={t('app.kuaicaiwu.common.invoiceDateTip')}
          rules={[{ required: true, message: t(`${P}.form.selectInvoiceDate`) }]}
          initialValue={dayjs()}
          fieldProps={{ style: { width: '100%' }, format: 'YYYY-MM-DD' }}
          colProps={financeColHalf}
        />
        <ProFormSelect
          name="tax_rate"
          label={t(`${P}.form.taxRate`)}
          options={TAX_RATE_OPTIONS}
          initialValue={13}
          rules={[{ required: true, message: t(`${P}.form.selectTaxRate`) }]}
          colProps={financeColHalf}
        />
        <ProFormDigit
          name="invoice_amount"
          label={t(`${P}.col.exclTax`)}
          min={0}
          rules={[{ required: true, message: t(`${P}.amountRequired`) }]}
          fieldProps={{ precision: 2, style: { width: '100%' } }}
          colProps={financeColHalf}
        />
        <ProFormText
          name="partner_tax_no"
          label={t(`${P}.col.partnerTaxNo`)}
          colProps={financeColHalf}
        />
        <SalesInvoicePartnerBankInfoField />
        <ProFormText
          name="partner_address_phone"
          label={t(`${P}.col.partnerAddressPhone`)}
          colProps={financeColFull}
        />
        <ProFormTextArea name="notes" label={t('common.remark')} colProps={financeColFull} />
        <DocumentAttachmentsField category="sales_invoice_attachments" />
      </ModalForm>
    </ListPageTemplate>
    </FinanceInvoiceSettlementModeAlert>
    {salesInvoiceAuditModal}
    </>
  );
};

export default SalesInvoicesPage;
