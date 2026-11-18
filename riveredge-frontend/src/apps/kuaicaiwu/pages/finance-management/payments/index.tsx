/**
 * 付款单列表页
 *
 * 记录向供应商支付的款项，可用于核销应付单。
 */
import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { rowActionKind, rowActionSettleVoucher, rowActionCreateRefund, rowActionLabelKeep } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button, Modal, Form, theme, Typography } from 'antd';
import { ModalForm, ProForm, ProFormDatePicker, ProFormDigit, ProFormSelect, ProFormText, ProFormTextArea } from '@ant-design/pro-components';
import type { ProFormInstance } from '@ant-design/pro-components';
import { PlusOutlined, PrinterOutlined } from '@ant-design/icons';
import { apiRequest } from '../../../../../services/api';
import { useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { UniTable } from '../../../../../components/uni-table';
import { UniBatchMenuButton, UniCapabilityBatchButton } from '../../../../../components/uni-batch';
import { UniLifecycle } from '../../../../../components/uni-lifecycle';
import { DetailDrawerActions, ListPageTemplate, MODAL_CONFIG, MODAL_NESTED_ABOVE_PARENT_OFFSET } from '../../../../../components/layout-templates';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { FinanceVoucherDetailDrawer } from '../shared/FinanceVoucherDetailDrawer';
import {
  mapFormPullLinesToApi,
  mapFormOffsetPrepaymentLinesToApi,
  usePaymentVoucherFormLinePull,
  requirePaymentPullLinesForNormalSettlement,
  handlePaymentVoucherFormValuesChange,
  applyPaymentHeaderAmountToPullLines,
} from '../shared/usePaymentVoucherFormLinePull';
import { usePaymentVoucherFormPrepaymentOffsetLines } from '../shared/usePaymentVoucherFormPrepaymentOffsetLines';
import { PaymentVoucherFormBody } from '../shared/PaymentVoucherFormBody';
import {
  toPaymentRemediationSnapshot,
  VoucherRemediationSettleModal,
  type RemediationVoucherSnapshot,
} from '../shared/VoucherRemediationSettleModal';
import { shouldOpenManualRemediationAfterRepairFailure } from '../shared/financeRemediationSettle';
import { resolveFormListFieldForSubmit } from '../../../../../utils/formListItems';
import {
  PaymentAdvancePayeeField,
  resolveAdvancePayeeName,
} from '../shared/PaymentAdvancePayeeField';
import { PaymentCounterpartyFormSection } from '../shared/PaymentCounterpartyFormSection';
import { useQuery } from '@tanstack/react-query';
import { loadUserFormReferenceOptions } from '../../../../../utils/documentFormReferenceLoad';
import { useKuaizhizaoPrintModal } from '../../../../kuaizhizao/hooks/useKuaizhizaoPrintModal';
import { fetchAllListItems } from '../../../../../utils/fetchAllListPages';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import {
  financeAmountDigitFieldProps,
  financeColFull,
  financeColHalf,
  financeFormGridProps,
} from '../../../utils/financeFormLayout';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import {
  UniPullQueryModal,
  filterByPullScope,
  paginatePullRows,
  renderPullQueryReviewStatus,
  UNI_PULL_QUERY_MAX_FETCH_LIMIT,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import dayjs from 'dayjs';
import { getFinanceVoucherLifecycle } from '../../../utils/financeLifecycle';
import {
  paymentService,
  type PaymentPullCandidate,
  type PaymentPullPreview,
  type PaymentVoucher,
  type PaymentListParams,
} from '../../../services/finance/payment';
import { buildKuaicaiwuPullCreateMenuItems, getKuaicaiwuDocumentAction } from '../../../constants/documentActionRegistry';
import {
  buildVoucherStatusEnum,
  formatPaymentMethod,
  getPaymentMethodOptions,
  getPaymentSettlementTypeOptions,
  formatPaymentSettlementType,
  assertBankAccountForPaymentMethod,
  formatBankAccountOptionLabel,
  BANK_TRANSFER_PAYMENT_METHOD,
  isNotePaymentMethod,
  isPrepaymentOffsetPaymentMethod,
  isEmployeeAdvancePaymentMethod,
} from '../../../utils/financeSharedOptions';
import {
  LedgerAccountFormFields,
  resolveFinanceVoucherReferenceNote,
} from '../../../components/LedgerAccountFormFields';
import { linkAcceptanceNoteAfterVoucherCreate } from '../../../components/AcceptanceBillLinkFields';
import { financeNoteService, type FinanceNote } from '../../../services/finance/note';
import DocumentAttachmentsField from '../../../../kuaizhizao/components/DocumentAttachmentsField';
import {
  mapAttachmentsToUploadList,
  normalizeDocumentAttachments,
} from '../../../../kuaizhizao/utils/documentAttachments';
import { bankAccountService, type BankAccount } from '../../../services/finance/bank-account';
import { getStatusDisplay } from '../../../../kuaizhizao/constants/documentStatus';
import { paymentCapabilityReasonMessage } from '../../../utils/paymentCapabilityMessages';
import { formatDateTime, formatCurrencyAmount, todaySiteDateString } from '../../../../../utils/format';
import {
  FINANCE_DOC_PINNED_STATUS_FIELD,
  financeDocCodePartnerSearchColumns,
  financeDocCreatedUpdatedColumns,
  resolvePaymentListParams,
} from '../../../utils/financeListCore';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import { renderRefundExecutionMarker } from '../../../utils/financeUiLabels';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import {
  buildFinanceVoucherLinkHandlers,
  FinanceVoucherDetailProvider,
  useFinanceVoucherDetail,
} from '../../../components/FinanceVoucherDetailProvider';
import { canCorrectFinanceVoucher, canCreateRefundFromVoucher, isFinanceVoucherCorrectionBlockedByRefund } from '../../../utils/financeVoucherDocType';
import { PAYMENT_REFUND_RESOURCE } from '../../../services/finance/payment-refund';
type PullPayableCandidate = PaymentPullCandidate;

const P = 'app.kuaicaiwu.payment';
const PAYMENT_RESOURCE = 'kuaicaiwu:payment';

const PaymentsPage: React.FC = () => {
  const actionRef = useRef<ActionType>();
  const lastListParamsRef = useRef<Record<string, string | number | boolean | undefined>>({});
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [editingRecord, setEditingRecord] = useState<PaymentVoucher | null>(null);
  const [pullPreviewOpen, setPullPreviewOpen] = useState(false);
  const [pullPreviewLoading, setPullPreviewLoading] = useState(false);
  const [pullPreviewData, setPullPreviewData] = useState<PaymentPullPreview | null>(null);
  const [pullPreviewSourceId, setPullPreviewSourceId] = useState<number | null>(null);
  const [pullForm] = Form.useForm();
  const pullFromPayableCloseRef = useRef<(() => void) | null>(null);
  const pullFromPayableOpenRef = useRef<(() => void) | null>(null);
  const pullFromPaymentApplicationOpenRef = useRef<(() => void) | null>(null);
  const { token } = theme.useToken();
  const pullPreviewZIndex = token.zIndexPopupBase + MODAL_NESTED_ABOVE_PARENT_OFFSET * 2;
  const [pullSubmitting, setPullSubmitting] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [supplierOptions, setSupplierOptions] = useState<{ label: string; value: number }[]>([]);
  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [remediationVoucher, setRemediationVoucher] = useState<RemediationVoucherSnapshot | null>(null);
  const [detailRecord, setDetailRecord] = useState<PaymentVoucher | null>(null);
  const [linkedNote, setLinkedNote] = useState<FinanceNote | null>(null);
  const detailRetryIdRef = useRef<number | null>(null);
  const { message: messageApi } = App.useApp();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const pullFromPayableAction = getKuaicaiwuDocumentAction('payment.pull_from_payable');
  const pullFromPaymentApplicationAction = getKuaicaiwuDocumentAction(
    'payment.pull_from_payment_application',
  );
  const [pullSourceKind, setPullSourceKind] = useState<'payable' | 'payment_application'>('payable');
  const createPaymentFormRef = useRef<ProFormInstance>();
  const editPaymentFormRef = useRef<ProFormInstance>();
  const createLinePull = usePaymentVoucherFormLinePull({ formRef: createPaymentFormRef });
  const editLinePull = usePaymentVoucherFormLinePull({ formRef: editPaymentFormRef });
  const createOffsetLines = usePaymentVoucherFormPrepaymentOffsetLines({
    formRef: createPaymentFormRef,
  });
  const editOffsetLines = usePaymentVoucherFormPrepaymentOffsetLines({ formRef: editPaymentFormRef });
  const [createWriteoffLoading, setCreateWriteoffLoading] = useState(false);
  const [editWriteoffLoading, setEditWriteoffLoading] = useState(false);
  const paymentPerms = useResourcePermissions(PAYMENT_RESOURCE);
  const paymentRefundPerms = useResourcePermissions(PAYMENT_REFUND_RESOURCE);
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const { openFinanceVoucherDetail } = useFinanceVoucherDetail();
  const voucherLinkHandlers = useMemo(
    () =>
      buildFinanceVoucherLinkHandlers({
        openVoucher: openFinanceVoucherDetail,
        navigate,
      }),
    [navigate, openFinanceVoucherDetail],
  );

  const paymentMethodOptions = useMemo(() => getPaymentMethodOptions(t), [t]);
  const { data: advancePayeeUserOptions = [] } = useQuery({
    queryKey: ['payment-advance-payee-users'],
    queryFn: () => loadUserFormReferenceOptions(),
    staleTime: 60_000,
  });
  const paymentSettlementTypeOptions = useMemo(() => getPaymentSettlementTypeOptions(t), [t]);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await apiRequest<unknown>('/apps/master-data/supply-chain/suppliers', { params: { limit: 1000, is_active: true } });
        const list = Array.isArray(res) ? res : (res as any)?.data ?? (res as any)?.items ?? [];
        setSupplierOptions((Array.isArray(list) ? list : []).map((s: any) => ({
          label: s.name || s.supplier_name || s.code || String(s.id),
          value: s.id,
        })));
      } catch {
        setSupplierOptions([]);
      }
    };
    load();
    bankAccountService.list({ limit: 200, is_active: true }).then((res) => setBankAccounts(res.data)).catch(() => setBankAccounts([]));
  }, []);

  const resolveBankLabel = (id?: number) => {
    if (!id) return '—';
    const acc = bankAccounts.find((a) => a.id === id);
    return acc ? formatBankAccountOptionLabel(acc) : `#${id}`;
  };

  const loadDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    setDetailError(null);
    setLinkedNote(null);
    try {
      const record = await paymentService.getPayment(id);
      setDetailRecord(record);
      if (isNotePaymentMethod(record.payment_method)) {
        const noteRes = await financeNoteService.list('payable', { payment_id: id, limit: 1 });
        setLinkedNote(noteRes.data?.[0] ?? null);
      }
    } catch (error) {
      setDetailRecord(null);
      setLinkedNote(null);
      setDetailError(getApiErrorMessage(error, t(`${P}.loadDetailFailed`)));
    } finally {
      setDetailLoading(false);
    }
  }, [t]);

  const openDetail = useCallback((record: PaymentVoucher) => {
    detailRetryIdRef.current = record.id;
    setDetailOpen(true);
    setDetailRecord(null);
    setDetailError(null);
    void loadDetail(record.id);
  }, [loadDetail]);

  const closeDetail = () => {
    setDetailOpen(false);
    setDetailRecord(null);
    setLinkedNote(null);
    setDetailError(null);
  };

  const refreshOpenDetail = () => {
    const id = detailRetryIdRef.current;
    if (detailOpen && id != null) void loadDetail(id);
  };

  const syncPaymentFormPullLinesFromHeader = (values: Record<string, unknown>) => {
    const total = Number(values.total_amount);
    const rows = values.pull_lines;
    if (!Array.isArray(rows) || !rows.length || !Number.isFinite(total) || total <= 0) {
      return values;
    }
    return {
      ...values,
      pull_lines: applyPaymentHeaderAmountToPullLines(
        total,
        rows as Record<string, unknown>[],
      ),
    };
  };

  const handleCreate = async (values: any, opts?: { confirmAfter?: boolean }) => {
    values = {
      ...(values as Record<string, unknown>),
      pull_lines: resolveFormListFieldForSubmit(
        createPaymentFormRef,
        values as Record<string, unknown>,
        'pull_lines',
      ),
    };
    values = syncPaymentFormPullLinesFromHeader(values as Record<string, unknown>);
    const prepayOffset = isPrepaymentOffsetPaymentMethod(values.payment_method);
    if (!prepayOffset) {
      try {
        assertBankAccountForPaymentMethod(values.payment_method, values.bank_account_id, t);
      } catch (e: unknown) {
        messageApi.warning((e as Error).message);
        return false;
      }
    }
    const pullLineError = requirePaymentPullLinesForNormalSettlement(
      values.settlement_type,
      values.pull_lines,
      values.total_amount,
      t,
      values.payment_method,
      values.offset_prepayment_lines,
    );
    if (pullLineError) {
      messageApi.warning(pullLineError);
      return false;
    }
    const pull_lines = mapFormPullLinesToApi(values.pull_lines);
    const offset_prepayment_lines = prepayOffset
      ? mapFormOffsetPrepaymentLinesToApi(values.offset_prepayment_lines)
      : undefined;
    const data = {
      supplier_id: values.supplier_id,
      supplier_name: supplierOptions.find(o => o.value === values.supplier_id)?.label || '',
      total_amount: values.total_amount,
      pull_lines,
      ...(offset_prepayment_lines ? { offset_prepayment_lines } : {}),
      payment_date: formatDateTime(values.payment_date || dayjs(), 'YYYY-MM-DD'),
      payment_method: values.payment_method,
      bank_account_id: prepayOffset ? undefined : values.bank_account_id,
      bank_account: prepayOffset
        ? undefined
        : resolveFinanceVoucherReferenceNote(
            bankAccounts,
            values.payment_method,
            values.bank_account_id,
            values.bank_account,
          ),
      settlement_type: prepayOffset ? 'normal' : values.settlement_type || 'normal',
      counterparty_account_name: values.counterparty_account_name,
      counterparty_bank_name: values.counterparty_bank_name,
      counterparty_bank_account: values.counterparty_bank_account,
      advance_payee_id: isEmployeeAdvancePaymentMethod(values.payment_method)
        ? values.advance_payee_id
        : null,
      advance_payee_name: isEmployeeAdvancePaymentMethod(values.payment_method)
        ? resolveAdvancePayeeName(values.advance_payee_id, advancePayeeUserOptions)
        : null,
      notes: values.notes,
      attachments: normalizeDocumentAttachments(values.attachments),
    };
    try {
      const created = await paymentService.create(data);
      try {
        await linkAcceptanceNoteAfterVoucherCreate(
          'payable',
          values.note_id,
          created.id,
          'payment',
        );
      } catch (linkError) {
        messageApi.warning(getApiErrorMessage(linkError, t('app.kuaicaiwu.notes.linkFailed')));
      }
      if (opts?.confirmAfter) {
        await paymentService.confirmPayment(created.id);
        messageApi.success(t(`${P}.writeoffConfirmSuccess`));
      } else {
        messageApi.success(t(`${P}.createSuccess`));
      }
      setCreateModalVisible(false);
      actionRef.current?.reload();
    } catch (error) {
      messageApi.error(
        getApiErrorMessage(
          error,
          opts?.confirmAfter ? t(`${P}.writeoffConfirmFailed`) : t('common.createFailed'),
        ),
      );
      return false;
    }
    return true;
  };

  const submitCreateAndConfirm = async () => {
    const inst = createPaymentFormRef.current;
    if (!inst) return;
    setCreateWriteoffLoading(true);
    try {
      const values = await inst.validateFields();
      const merged = {
        ...(inst.getFieldsValue(true) as Record<string, unknown>),
        ...values,
      };
      await handleCreate(merged, { confirmAfter: true });
    } catch {
      // validateFields 已提示
    } finally {
      setCreateWriteoffLoading(false);
    }
  };

  const resetPullPreview = () => {
    setPullPreviewOpen(false);
    setPullPreviewSourceId(null);
    setPullPreviewData(null);
    pullForm.resetFields();
  };

  const openPullPreview = async (
    sourceId: number,
    kind: 'payable' | 'payment_application' = 'payable',
    options?: { closeSourceModal?: () => void; reopenSourceModal?: () => void },
  ) => {
    setPullSourceKind(kind);
    setPullPreviewOpen(false);
    setPullPreviewLoading(true);
    setPullPreviewData(null);
    setPullPreviewSourceId(sourceId);
    const sourceAction =
      kind === 'payment_application' ? pullFromPaymentApplicationAction : pullFromPayableAction;
    const hideLoading = messageApi.loading(t(`${P}.pullPreviewLoading`), 0);
    try {
      const data =
        kind === 'payment_application'
          ? await paymentService.previewPullFromPaymentApplication(sourceId)
          : await paymentService.previewPullFromPayable(sourceId);
      setPullPreviewData(data);
      const maxPush = Number(data.items?.[0]?.max_push_quantity ?? 0);
      pullForm.setFieldsValue({
        source_code: data.source_code,
        supplier_id: data.supplier_id,
        supplier_name: data.supplier_name,
        total_amount: maxPush > 0 ? maxPush : undefined,
        payment_date: dayjs(),
        payment_method: data.payment_method || BANK_TRANSFER_PAYMENT_METHOD,
        settlement_type: 'normal',
        counterparty_account_name: data.counterparty_account_name,
        counterparty_bank_name: data.counterparty_bank_name,
        counterparty_bank_account: data.counterparty_bank_account,
        advance_payee_id: data.advance_payee_id,
        notes: t('app.kuaicaiwu.common.createdFromSourceNote', {
          source: sourceAction.sourceLabel,
          code: data.source_code,
        }),
      });
      setPullPreviewOpen(true);
    } catch (e: any) {
      messageApi.error(
        e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t(`${P}.loadSourceFailed`),
      );
      resetPullPreview();
      options?.reopenSourceModal?.();
    } finally {
      hideLoading();
      setPullPreviewLoading(false);
    }
  };

  const isPullPaymentSelectable = useCallback(
    (record: PullPayableCandidate) => record.capabilities?.pull_payment?.allowed !== false,
    [],
  );

  const pullQueryScopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const pullFromPayableQuery = useUniPullQuery<PullPayableCandidate>({
    rowKey: 'id',
    selectionType: 'radio',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => !isPullPaymentSelectable(record),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const res = await paymentService.listPayablePullCandidates({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
        });
        const rows = res.data || [];
        const filtered = filterByPullScope(rows, scope, isPullPaymentSelectable);
        return paginatePullRows(filtered, page, pageSize);
      } catch (e: any) {
        messageApi.error(
          e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t(`${P}.loadSourceFailed`),
        );
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selected = rows.find((x) => String(x.id) === String(keys[0]));
      if (!selected?.id) {
        messageApi.warning(t(`${P}.selectSource`, { label: pullFromPayableAction.sourceLabel }));
        return;
      }
      pullFromPayableCloseRef.current?.();
      await openPullPreview(selected.id, 'payable');
    },
  });
  pullFromPayableCloseRef.current = pullFromPayableQuery.closeModal;
  pullFromPayableOpenRef.current = pullFromPayableQuery.openModal;

  const pullFromPaymentApplicationQuery = useUniPullQuery<PaymentPullCandidate>({
    rowKey: 'id',
    selectionType: 'radio',
    scopeOptions: pullQueryScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => record.capabilities?.pull_payment?.allowed === false,
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const res = await paymentService.listPaymentApplicationPullCandidates({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
        });
        const rows = res.data || [];
        const isSelectable = (record: PaymentPullCandidate) =>
          record.capabilities?.pull_payment?.allowed !== false;
        const filtered = filterByPullScope(rows, scope, isSelectable);
        return paginatePullRows(filtered, page, pageSize);
      } catch (e: any) {
        messageApi.error(
          e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t(`${P}.loadSourceFailed`),
        );
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selected = rows.find((x) => String(x.id) === String(keys[0]));
      if (!selected?.id) {
        messageApi.warning(
          t(`${P}.selectSource`, { label: pullFromPaymentApplicationAction.sourceLabel }),
        );
        return;
      }
      await openPullPreview(selected.id, 'payment_application', {
        closeSourceModal: () => pullFromPaymentApplicationCloseRef.current?.(),
        reopenSourceModal: () => pullFromPaymentApplicationOpenRef.current?.(),
      });
    },
  });
  const pullFromPaymentApplicationCloseRef = useRef<(() => void) | null>(null);
  pullFromPaymentApplicationCloseRef.current = pullFromPaymentApplicationQuery.closeModal;
  pullFromPaymentApplicationOpenRef.current = pullFromPaymentApplicationQuery.openModal;

  useEffect(() => {
    const pullPayableId = (location.state as { pullPayableId?: number } | null)?.pullPayableId;
    if (!pullPayableId) return;
    void openPullPreview(pullPayableId);
    navigate(location.pathname, { replace: true, state: null });
  }, [location.state, location.pathname, navigate]);

  const handlePullCreateSubmit = async (values: any) => {
    if (!pullPreviewData || !pullPreviewSourceId) return false;
    if (pullPreviewData.has_blocking_issues) return false;
    try {
      assertBankAccountForPaymentMethod(values.payment_method, values.bank_account_id, t);
    } catch (e: unknown) {
      messageApi.warning((e as Error).message);
      return false;
    }
    const maxPush = Number(pullPreviewData.items?.[0]?.max_push_quantity ?? 0);
    const totalAmount = Number(values.total_amount) || 0;
    if (totalAmount <= 0) {
      messageApi.warning(t(`${P}.amountMustPositive`));
      return false;
    }
    if (totalAmount > maxPush) {
      messageApi.warning(t(`${P}.pullExceedMax`, { max: formatCurrencyAmount(maxPush) }));
      return false;
    }
    setPullSubmitting(true);
    try {
      const pullAction =
        pullSourceKind === 'payment_application'
          ? pullFromPaymentApplicationAction
          : pullFromPayableAction;
      const created = await paymentService.create({
        supplier_id: Number(pullPreviewData.supplier_id || 0),
        supplier_name: pullPreviewData.supplier_name || '',
        source_type: pullSourceKind,
        source_id: pullPreviewSourceId,
        total_amount: totalAmount,
        payment_date: formatDateTime(values.payment_date || dayjs(), 'YYYY-MM-DD'),
        payment_method: values.payment_method || '银行转账',
        bank_account_id: values.bank_account_id,
        bank_account: resolveFinanceVoucherReferenceNote(
          bankAccounts,
          values.payment_method,
          values.bank_account_id,
          values.bank_account,
        ),
        settlement_type: values.settlement_type || 'normal',
        notes:
          String(values.notes ?? '').trim() ||
          t('app.kuaicaiwu.common.createdFromSourceNote', {
            source: pullAction.sourceLabel,
            code: pullPreviewData.source_code,
          }),
        require_payment_voucher: Boolean(pullPreviewData.require_payment_voucher),
        counterparty_account_name: values.counterparty_account_name,
        counterparty_bank_name: values.counterparty_bank_name,
        counterparty_bank_account: values.counterparty_bank_account,
        advance_payee_id: isEmployeeAdvancePaymentMethod(values.payment_method)
          ? values.advance_payee_id
          : null,
        advance_payee_name: isEmployeeAdvancePaymentMethod(values.payment_method)
          ? resolveAdvancePayeeName(values.advance_payee_id, advancePayeeUserOptions)
          : null,
        attachments: normalizeDocumentAttachments(values.attachments),
      });
      if (pullSourceKind === 'payable') {
        try {
          await linkAcceptanceNoteAfterVoucherCreate(
            'payable',
            values.note_id,
            created.id,
            'payment',
          );
        } catch (linkError) {
          messageApi.warning(getApiErrorMessage(linkError, t('app.kuaicaiwu.notes.linkFailed')));
        }
      }
      messageApi.success(t(`${P}.pullCreateSuccess`, { target: pullAction.targetLabel }));
      resetPullPreview();
      actionRef.current?.reload();
      return true;
    } catch (e: any) {
      messageApi.error(
        e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t('common.createFailed'),
      );
      return false;
    } finally {
      setPullSubmitting(false);
    }
  };

  const paymentHasAttachments = (record: PaymentVoucher) => {
    const list = Array.isArray(record.attachments) ? record.attachments : [];
    return list.length > 0;
  };

  const executeConfirm = async (record: PaymentVoucher) => {
    if (record.require_payment_voucher && !paymentHasAttachments(record)) {
      messageApi.warning(t(`${P}.requirePaymentVoucherMissing`));
      return;
    }
    try {
      let pullLines = record.pull_lines;
      let offsetPrepaymentLines = record.offset_prepayment_lines;
      if (
        String(record.settlement_type || 'normal') === 'normal' &&
        ((!pullLines || pullLines.length === 0) ||
          (isPrepaymentOffsetPaymentMethod(record.payment_method) &&
            (!offsetPrepaymentLines || offsetPrepaymentLines.length === 0)))
      ) {
        const detail = await paymentService.getPayment(record.id);
        pullLines = detail.pull_lines;
        offsetPrepaymentLines = detail.offset_prepayment_lines;
      }
      const pullGateError = requirePaymentPullLinesForNormalSettlement(
        record.settlement_type,
        pullLines?.map((line) => ({
          sourceType: line.source_type,
          paymentAmount: line.amount,
          maxAmount: line.max_amount,
        })),
        Number(record.total_amount ?? 0),
        t,
        record.payment_method,
        offsetPrepaymentLines?.map((line) => ({
          prepaymentPaymentId: line.prepayment_payment_id,
          offsetAmount: line.amount,
        })),
      );
      if (pullGateError) {
        messageApi.warning(pullGateError);
        return;
      }
      await paymentService.confirmPayment(record.id);
      messageApi.success(t(`${P}.confirmSuccess`));
      actionRef.current?.reload();
      refreshOpenDetail();
    } catch (e: any) {
      messageApi.error(
        e?.response?.data?.detail?.message ||
          e?.response?.data?.detail ||
          e?.message ||
          t('common.operationFailed'),
      );
      // 过账中途失败时库内状态可能已变，刷新避免界面仍显示草稿
      actionRef.current?.reload();
      refreshOpenDetail();
    }
  };

  const executeCancelVoucher = async (record: PaymentVoucher) => {
    try {
          await paymentService.cancelPayment(record.id);
          messageApi.success(t(`${P}.voidSuccess`));
    actionRef.current?.reload();
          refreshOpenDetail();
        } catch (e: any) {
          messageApi.error(e?.message || t('common.operationFailed'));
        }
  };

  const executeRepairSettle = async (record: PaymentVoucher) => {
    try {
      await paymentService.repairSettlement(record.id);
      messageApi.success(t(`${P}.repairSettleSuccess`));
      actionRef.current?.reload();
      refreshOpenDetail();
    } catch (e: unknown) {
      const msg = getApiErrorMessage(e, t('common.operationFailed'));
      if (shouldOpenManualRemediationAfterRepairFailure(msg, 'payment')) {
        try {
          const detail = await paymentService.getPayment(record.id);
          const snap = toPaymentRemediationSnapshot(detail);
          if (snap) {
            setRemediationVoucher(snap);
            messageApi.info(t(`${P}.repairSettleManualFallback`));
            return;
          }
        } catch {
          // fall through
        }
      }
      messageApi.error(msg);
    }
  };

  const executeUnconfirm = async (record: PaymentVoucher) => {
    try {
      await paymentService.unconfirmPayment(record.id);
      messageApi.success(t(`${P}.unconfirmSuccess`));
      actionRef.current?.reload();
      refreshOpenDetail();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.operationFailed'));
    }
  };

  const executeDelete = async (record: PaymentVoucher) => {
    try {
      await paymentService.deletePayment(record.id);
      messageApi.success(t('common.deleteSuccess'));
      actionRef.current?.reload();
      if (detailRetryIdRef.current === record.id) closeDetail();
    } catch (e: any) {
      messageApi.error(e?.message || t('common.operationFailed'));
    }
  };

  const openEdit = async (record: PaymentVoucher) => {
    try {
      const full = await paymentService.getPayment(record.id);
      setEditingRecord(full);
    } catch (e: any) {
      messageApi.error(
        e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t('common.loadFailed'),
      );
    }
  };

  const handleUpdate = async (values: any, opts?: { confirmAfter?: boolean }) => {
    if (!editingRecord) return false;
    values = {
      ...(values as Record<string, unknown>),
      pull_lines: resolveFormListFieldForSubmit(
        editPaymentFormRef,
        values as Record<string, unknown>,
        'pull_lines',
      ),
    };
    values = syncPaymentFormPullLinesFromHeader(values as Record<string, unknown>);
    const prepayOffset = isPrepaymentOffsetPaymentMethod(values.payment_method);
    if (!prepayOffset) {
      try {
        assertBankAccountForPaymentMethod(values.payment_method, values.bank_account_id, t);
      } catch (e: unknown) {
        messageApi.warning((e as Error).message);
        return false;
      }
    }
    if (editingRecord.status === 'Draft') {
      const pullLineError = requirePaymentPullLinesForNormalSettlement(
        values.settlement_type,
        values.pull_lines,
        values.total_amount,
        t,
        values.payment_method,
        values.offset_prepayment_lines,
      );
      if (pullLineError) {
        messageApi.warning(pullLineError);
        return false;
      }
    }
    try {
      await paymentService.updatePayment(editingRecord.id, {
        supplier_id: values.supplier_id,
        supplier_name: supplierOptions.find((o) => o.value === values.supplier_id)?.label || '',
        total_amount: values.total_amount,
        payment_date: formatDateTime(values.payment_date || dayjs(), 'YYYY-MM-DD'),
        payment_method: values.payment_method,
        bank_account_id: prepayOffset ? undefined : values.bank_account_id,
        bank_account: prepayOffset
          ? undefined
          : resolveFinanceVoucherReferenceNote(
              bankAccounts,
              values.payment_method,
              values.bank_account_id,
              values.bank_account,
            ),
        settlement_type: prepayOffset ? 'normal' : values.settlement_type || 'normal',
        counterparty_account_name: values.counterparty_account_name,
        counterparty_bank_name: values.counterparty_bank_name,
        counterparty_bank_account: values.counterparty_bank_account,
        advance_payee_id: isEmployeeAdvancePaymentMethod(values.payment_method)
          ? values.advance_payee_id
          : null,
        advance_payee_name: isEmployeeAdvancePaymentMethod(values.payment_method)
          ? resolveAdvancePayeeName(values.advance_payee_id, advancePayeeUserOptions)
          : null,
        ...(editingRecord.status === 'Draft'
          ? {
              pull_lines: mapFormPullLinesToApi(values.pull_lines) ?? [],
              ...(prepayOffset
                ? {
                    offset_prepayment_lines:
                      mapFormOffsetPrepaymentLinesToApi(values.offset_prepayment_lines) ?? [],
                  }
                : {}),
            }
          : {}),
        notes: values.notes,
        attachments: normalizeDocumentAttachments(values.attachments),
      });
      if (opts?.confirmAfter) {
        await paymentService.confirmPayment(editingRecord.id);
        messageApi.success(t(`${P}.writeoffConfirmSuccess`));
      } else {
        messageApi.success(t('common.updateSuccess'));
      }
      setEditingRecord(null);
      actionRef.current?.reload();
      refreshOpenDetail();
      return true;
    } catch (e: any) {
      messageApi.error(
        getApiErrorMessage(
          e,
          opts?.confirmAfter ? t(`${P}.writeoffConfirmFailed`) : t('common.updateFailed'),
        ),
      );
      return false;
    }
  };

  const submitEditAndConfirm = async () => {
    const inst = editPaymentFormRef.current;
    if (!inst || !editingRecord) return;
    setEditWriteoffLoading(true);
    try {
      const values = await inst.validateFields();
      const merged = {
        ...(inst.getFieldsValue(true) as Record<string, unknown>),
        ...values,
      };
      await handleUpdate(merged, { confirmAfter: true });
    } catch {
      // validateFields 已提示
    } finally {
      setEditWriteoffLoading(false);
    }
  };

  const handleBatchDelete = async (keys: React.Key[]) => {
    try {
      for (const key of keys) {
        await paymentService.deletePayment(Number(key));
      }
      messageApi.success(t(`${P}.batchDeleted`, { count: keys.length }));
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error?.message || t('common.deleteFailed'));
    }
  };

  const handleBatchConfirm = async (keys: React.Key[]) => {
    try {
      for (const key of keys) {
      await paymentService.confirmPayment(Number(key));
      }
      messageApi.success(t(`${P}.batchConfirmed`, { count: keys.length }));
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error?.message || t('app.kuaicaiwu.common.batchConfirmFailed'));
    }
  };

  const handleBatchCancel = async (keys: React.Key[]) => {
    try {
      for (const key of keys) {
      await paymentService.cancelPayment(Number(key));
      }
      messageApi.success(t(`${P}.batchVoided`, { count: keys.length }));
      setSelectedRowKeys([]);
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error?.message || t('app.kuaicaiwu.common.batchVoidFailed'));
    }
  };

  const pullTableColumns = useMemo(
    () => [
      { title: t(`${P}.pullCol.payableCode`), dataIndex: 'code', width: 220, ellipsis: true },
      { title: t('app.kuaicaiwu.common.supplier'), dataIndex: 'supplier_name', width: 200, ellipsis: true },
      {
        title: t(`${P}.pullCol.docStatus`),
        dataIndex: 'source_status',
        width: 120,
        align: 'center' as const,
        render: (v: unknown) => {
          const { text, color } = getStatusDisplay(v == null ? undefined : String(v));
          return text === '-' ? '-' : <MarkerTag color={color}>{text}</MarkerTag>;
        },
      },
      {
        title: t('app.kuaicaiwu.common.reviewStatus'),
        dataIndex: 'review_status',
        width: 120,
        align: 'center' as const,
        render: (v) => renderPullQueryReviewStatus(t, v),
      },
      {
        title: t('app.kuaicaiwu.common.dueDate'),
        dataIndex: 'source_date',
        width: 120,
        render: (v: unknown) => (v ? formatDateTime(String(v), 'YYYY-MM-DD') : '-'),
      },
      {
        title: t('app.kuaicaiwu.payable.col.remainingAmount'),
        dataIndex: 'remaining_amount',
        width: 140,
        align: 'right' as const,
        render: (v: unknown) => formatCurrencyAmount(v || 0),
      },
    ],
    [t],
  );

  const pullPreviewMaxPush = Number(pullPreviewData?.items?.[0]?.max_push_quantity ?? 0);
  const formatPullMoney = (v: number) =>
    formatCurrencyAmount(v || 0);

  const tableRowsRef = useRef<PaymentVoucher[]>([]);
  const selectedPaymentsForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
        .filter((row): row is PaymentVoucher => row != null),
    [selectedRowKeys],
  );

  const handleBatchCreateRefund = async (keys: React.Key[]) => {
    if (!paymentRefundPerms.canCreate) {
      messageApi.warning(t('app.kuaicaiwu.payment.batchRefundNoPermission'));
      return;
    }
    const ids = keys.map((k) => Number(k)).filter((id) => Number.isFinite(id) && id > 0);
    if (ids.length < 1) {
      messageApi.warning(t('app.kuaicaiwu.payment.batchRefundSelectRequired'));
      return;
    }
    const rows = tableRowsRef.current.filter((r) => ids.includes(Number(r.id)));
    if (!rows.length) {
      messageApi.warning(t('app.kuaicaiwu.payment.batchRefundRowsMissing'));
      return;
    }
    const supplierIds = new Set(rows.map((r) => Number(r.supplier_id || 0)).filter((id) => id > 0));
    if (supplierIds.size > 1) {
      messageApi.warning(t('app.kuaicaiwu.payment.batchRefundSameSupplier'));
      return;
    }
    const ineligible = rows.filter((r) => !canCreateRefundFromVoucher(r, 'payment'));
    if (ineligible.length) {
      messageApi.warning(t('app.kuaicaiwu.payment.batchRefundIneligible'));
      return;
    }
    navigate('/apps/kuaicaiwu/finance-management/payment-refunds', {
      state: { pullSourceIds: ids },
    });
    setSelectedRowKeys([]);
  };

  const batchMenuItems = useMemo(() => [
    {
      key: 'batch-confirm',
      label: t('app.kuaicaiwu.common.batchConfirm'),
      requireConfirm: true,
      confirmTitle: (count: number) => t(`${P}.batchConfirmTitle`, { count }),
      confirmDescription: t(`${P}.batchConfirmDesc`),
      onClick: handleBatchConfirm,
    },
    {
      key: 'batch-create-refund',
      label: t('app.kuaicaiwu.payment.batchCreateRefund'),
      onClick: handleBatchCreateRefund,
    },
    {
      key: 'batch-cancel',
      label: t('app.kuaicaiwu.common.batchVoid'),
      requireConfirm: true,
      confirmTitle: (count: number) => t(`${P}.batchVoidTitle`, { count }),
      confirmDescription: t(`${P}.batchVoidDesc`),
      onClick: handleBatchCancel,
    },
  ], [t, paymentRefundPerms.canCreate]);

  const columns: ProColumns<PaymentVoucher>[] = useMemo(() => [
    ...financeDocCodePartnerSearchColumns({
      docCodeLabel: t(`${P}.col.code`),
      docCodeField: 'payment_code',
      partnerLabel: t('app.kuaicaiwu.common.supplier'),
      partnerIdField: 'supplier_id',
      partnerNameField: 'supplier_name',
      partnerOptions: supplierOptions,
    }),
    {
      // 有 RemainderFlex：主标识叠列 KeepWidth
      title: t(`${P}.col.code`),
      key: 'finance_doc_partner_stacked',
      dataIndex: 'payment_code',
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
          primary={String(r.supplier_name ?? '')}
          secondary={String(r.payment_code ?? '')}
          onSecondaryClick={() => openDetail(r)}
        />
      ),
    },
    {
      title: t('app.kuaicaiwu.common.supplier'),
      dataIndex: 'supplier_name',
      hideInTable: true,
    },
    {
      title: t(`${P}.settlementType.label`),
      key: 'finance_payment_settlement_type',
      dataIndex: 'settlement_type',
      ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
      hideInSearch: true,
      render: (_, record) => {
        const raw = String(record.settlement_type || 'normal');
        const color =
          raw === 'prepayment' ? 'blue' : raw === 'refund' ? 'orange' : ('default' as const);
        return (
          <MarkerTag color={color}>
            {formatPaymentSettlementType(record.settlement_type, t)}
          </MarkerTag>
        );
      },
    },
    {
      title: t(`${P}.col.linkedPayableTotal`),
      key: 'linked_payable_total_amount',
      dataIndex: 'linked_payable_total_amount',
      align: 'right',
      width: 140,
      minWidth: 140,
      uniTableKeepWidth: true,
      resizable: false,
      hideInSearch: true,
      render: (_, record) => {
        const total = record.linked_payable_total_amount;
        if (total == null || !(Number(total) > 0)) {
          return '—';
        }
        const remaining = record.linked_payable_remaining_amount;
        const remainingText =
          remaining != null && Number.isFinite(Number(remaining))
            ? t(`${P}.col.linkedPayableRemainingLine`, {
                amount: formatCurrencyAmount(remaining),
              })
            : undefined;
        return (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'flex-end',
              width: '100%',
              gap: 2,
            }}
          >
            <span style={{ fontWeight: 500, lineHeight: 1.25, whiteSpace: 'nowrap' }}>
              {formatCurrencyAmount(total)}
            </span>
            {remainingText ? (
              <Typography.Text
                type="secondary"
                style={{ fontSize: 12, lineHeight: 1.2, whiteSpace: 'nowrap' }}
              >
                {remainingText}
              </Typography.Text>
            ) : null}
          </div>
        );
      },
    },
    {
      title: t(`${P}.col.totalAmount`),
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
      title: t(`${P}.col.settledAmount`),
      dataIndex: 'settled_amount',
      valueType: 'money',
      align: 'right',
      width: 120,
      minWidth: 120,
      uniTableKeepWidth: true,
      resizable: false,
      hideInSearch: true,
      sorter: true,
    },
    {
      title: t(`${P}.col.unsettledAmount`),
      dataIndex: 'unsettled_amount',
      align: 'right',
      width: 120,
      minWidth: 120,
      uniTableKeepWidth: true,
      resizable: false,
      hideInSearch: true,
      sorter: true,
      render: (_, record) => (
        <span style={{ color: record.unsettled_amount > 0 ? '#1677ff' : 'inherit', fontWeight: 'bold' }}>
          {formatCurrencyAmount(record.unsettled_amount)}
        </span>
      ),
    },
    {
      title: t('app.kuaicaiwu.financeUi.refundExecution.label'),
      dataIndex: 'refund_execution_status',
      ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
      hideInSearch: true,
      render: (_, record) => {
        const { label, color } = renderRefundExecutionMarker(record.refund_execution_status, t);
        return <MarkerTag color={color}>{label}</MarkerTag>;
      },
    },
    {
      title: t(`${P}.col.paymentDate`),
      key: 'finance_payment_date',
      dataIndex: 'payment_date',
      valueType: 'date',
      width: 120,
      minWidth: 120,
      uniTableKeepWidth: true,
      resizable: false,
      hideInSearch: true,
      sorter: true,
    },
    {
      title: t(`${P}.col.paymentDate`),
      dataIndex: 'payment_date_range',
      valueType: 'dateRange',
      hideInTable: true,
      order: 20,
      formItemProps: formDateRangeFormItemProps,
    },
    {
      title: t(`${P}.col.paymentMethod`),
      dataIndex: 'payment_method',
      width: 120,
      minWidth: 120,
      uniTableKeepWidth: true,
      resizable: false,
      hideInSearch: true,
      sorter: true,
      render: (_, record) => formatPaymentMethod(record.payment_method, t),
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
      render: (_, record) => record.notes || '—',
    },
    {
      title: t(`${P}.settlementType.label`),
      key: 'settlement_type_search',
      dataIndex: 'settlement_type',
      hideInTable: true,
      order: 15,
      valueType: 'select',
      fieldProps: {
        options: paymentSettlementTypeOptions,
        allowClear: true,
      },
    },
    {
      title: t('common.status'),
      dataIndex: 'status',
      hideInTable: true,
      order: 22,
      valueEnum: buildVoucherStatusEnum(t),
    },
    ...financeDocCreatedUpdatedColumns<PaymentVoucher>(t),
    {
      title: t('app.kuaicaiwu.common.lifecycle'),
      key: 'lifecycle',
      dataIndex: 'lifecycle_stage',
      fixed: 'right',
      hideInSearch: true,
      render: (_, record) => {
        const lc = getFinanceVoucherLifecycle(record as unknown as Record<string, unknown>, t);
        return (
          <UniLifecycle
            percent={lc.percent}
            stageName={lc.stageName}
            status={lc.status}
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
        const acts: React.ReactNode[] = [
          <Button key="det" {...rowActionKind('read')} onClick={() => openDetail(record)} />,
        ];
        if (record.status === 'Draft' && paymentPerms.canAction?.('audit')) {
          acts.push(
            <ActionConfirmPopconfirm title={t(`${P}.confirmTitle`)} description={t(`${P}.confirmContent`, { code: record.payment_code })} onConfirm={() => executeConfirm(record)}>
              <Button key="cf" {...rowActionKind('audit')} onClick={(e) => e.stopPropagation()} />
            </ActionConfirmPopconfirm>,
          );
        }
        if (record.status === 'Confirmed' && Number(record.unsettled_amount ?? 0) > 0) {
          acts.push(
            <ActionConfirmPopconfirm
              key="st"
              title={t(`${P}.repairSettleTitle`)}
              description={t(`${P}.repairSettleContent`, { code: record.payment_code })}
              onConfirm={() => executeRepairSettle(record)}
            >
              <Button
                {...rowActionSettleVoucher('submit')}
                title={t(`${P}.repairSettleHint`)}
                onClick={(e) => e.stopPropagation()}
              />
            </ActionConfirmPopconfirm>,
          );
        }
        if (
          record.status === 'Confirmed' &&
          canCreateRefundFromVoucher(record, 'payment') &&
          paymentRefundPerms.canCreate
        ) {
          acts.push(
            <Button
              key="refund"
              {...rowActionCreateRefund('create')}
              onClick={() =>
                navigate('/apps/kuaicaiwu/finance-management/payment-refunds', {
                  state: { pullSourceIds: [record.id] },
                })
              }
            />,
          );
        }
        if (
          record.status === 'Confirmed' &&
          isFinanceVoucherCorrectionBlockedByRefund(record) &&
          paymentRefundPerms.canRead
        ) {
          acts.push(
            <Button
              key="view-refunds"
              {...rowActionKind('read')}
              {...rowActionLabelKeep()}
              onClick={(e) => {
                e.stopPropagation();
                navigate('/apps/kuaicaiwu/finance-management/payment-refunds', {
                  state: { filterSourceId: record.id },
                });
              }}
            >
              {t(`${P}.viewRefunds`)}
            </Button>,
          );
        }
        if (record.status === 'Draft' && paymentPerms.canUpdate) {
          acts.push(
            <Button key="ed" {...rowActionKind('update')} onClick={() => openEdit(record)} />,
          );
        }
        if (
          record.status === 'Confirmed' &&
          canCorrectFinanceVoucher(record) &&
          paymentPerms.canAction?.('revoke')
        ) {
          acts.push(
            <ActionConfirmPopconfirm
              title={t(`${P}.unconfirmTitle`)}
              description={t(`${P}.unconfirmContent`, { code: record.payment_code })}
              onConfirm={() => executeUnconfirm(record)}
            >
              <Button key="uc" {...rowActionKind('revoke')} onClick={(e) => e.stopPropagation()} />
            </ActionConfirmPopconfirm>,
          );
        }
        if (
          record.status === 'Draft' &&
          canCorrectFinanceVoucher(record) &&
          paymentPerms.canAction?.('revoke')
        ) {
          acts.push(
            <ActionConfirmPopconfirm title={t(`${P}.voidTitle`)} description={t(`${P}.voidContent`, { code: record.payment_code })} onConfirm={() => executeCancelVoucher(record)}>
              <Button key="ca" {...rowActionKind('revoke')} onClick={(e) => e.stopPropagation()} />
            </ActionConfirmPopconfirm>,
          );
        }
        if (
          canCorrectFinanceVoucher(record) &&
          paymentPerms.canDelete &&
          (record.status === 'Draft' || record.status === 'Cancelled' || record.status === 'Confirmed')
        ) {
          acts.push(
            <ActionConfirmPopconfirm title={t(`${P}.deleteTitle`)} description={t(`${P}.deleteContent`, { code: record.payment_code })} okType="danger" onConfirm={() => executeDelete(record)}>
              <Button key="del" {...rowActionKind('delete')} onClick={(e) => e.stopPropagation()} />
            </ActionConfirmPopconfirm>,
          );
        }
        return acts;
      },
    },
  ], [t, supplierOptions, paymentPerms, paymentRefundPerms, navigate, openDetail, executeConfirm, executeRepairSettle, executeCancelVoucher, paymentSettlementTypeOptions]);



  return (
    <ListPageTemplate>
      <UniTable<PaymentVoucher>
        headerTitle={t(`${P}.pageTitle`)}
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.payment)}
        actionRef={actionRef}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        onTableDataChange={(rows) => {
          tableRowsRef.current = rows;
        }}
        rowKey="id"
        columnPersistenceId="apps.kuaicaiwu.pages.finance-management.payments.list-v9"
        showAdvancedSearch
        showCreateButton={false}
        createButtonText={t(`${P}.createTitle`)}
        onCreate={() => setCreateModalVisible(true)}
        showDeleteButton
        deleteButtonText={t('common.batchDelete')}
        onDelete={handleBatchDelete}
        deleteConfirmTitle={t('app.kuaicaiwu.common.confirmBatchDelete')}
        deleteConfirmDescription={(count) => t(`${P}.deleteConfirm`, { count })}
        toolBarActionsAfterDelete={[
          <UniBatchMenuButton
            key="payment-batch-actions"
            selectedRowKeys={selectedRowKeys}
            buttonText={t('components.uniBatch.batchActions')}
            menuItems={batchMenuItems}
          />,
        ]}
        rightToolBarActionsBeforeExport={[
          <UniCapabilityBatchButton
            key="payment-print"
            selectedRowKeys={selectedRowKeys}
            selectedRecords={selectedPaymentsForBatch}
            capabilityKey="print"
            permAllowed={paymentPerms.canPrint}
            batchAllowed={(records, perm) =>
              Boolean(perm) && records.some((record) => record.capabilities?.print?.allowed === true)
            }
            singleOnly
            onRun={async (id) => {
              openPrint({ documentType: 'finance_payment', documentId: id });
            }}
            labels={{
              single: t('components.uniAction.print'),
              batch: t('components.uniAction.print'),
            }}
            icon={<PrinterOutlined />}
            size="medium"
          />,
        ]}
        showExportButton
        onExport={async (type, keys, pageData) => {
          try {
            let items =
              type === 'currentPage'
                ? (pageData ?? [])
                : await fetchAllListItems((p) =>
                    paymentService.listPayments({
                      ...lastListParamsRef.current,
                      skip: p.skip,
                      limit: p.limit,
                    }),
                  );
            if (type === 'currentPage' && pageData?.length) {
              items = pageData;
            } else if (type === 'selected' && keys?.length) {
              items = items.filter(
                (d: PaymentVoucher) => d.id != null && keys.includes(d.id),
              );
            }
            if (items.length === 0) {
              messageApi.warning(t('common.noDataToExport'));
              return;
            }
            await downloadRecordsAsXlsx(
              items as unknown as Array<Record<string, unknown>>,
              `payments-${todaySiteDateString()}.xlsx`,
            );
            messageApi.success(t('common.exportSuccess', { count: items.length }));
          } catch (error: any) {
            messageApi.error(error?.message || t('common.exportFailed'));
          }
        }}
        toolBarRender={() => [
          <UniPullCreateToolbar
            compactKey="create-payment-with-pull"
            createIcon={<PlusOutlined />}
            createLabel={t(`${P}.createTitle`)}
            onCreate={() => setCreateModalVisible(true)}
            menuItems={buildKuaicaiwuPullCreateMenuItems([
              {
                key: 'pull-from-payable',
                actionKey: 'payment.pull_from_payable',
                onClick: pullFromPayableQuery.openModal,
              },
              {
                key: 'pull-from-payment-application',
                actionKey: 'payment.pull_from_payment_application',
                onClick: pullFromPaymentApplicationQuery.openModal,
              },
            ])}
          />,
        ]}
        request={async (params, sort, _filter, searchFormValues) => {
          const listParams = resolvePaymentListParams(searchFormValues, sort);
          lastListParamsRef.current = listParams;
          const apiParams: PaymentListParams = {
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize || 20,
            ...listParams,
          };
          const res = await paymentService.listPayments(apiParams);
          return {
            data: res?.items || [],
            total: res?.total || 0,
            success: true,
          };
        }}
        skipFuzzyPinyinClientFilter
        pinnedTabsField={FINANCE_DOC_PINNED_STATUS_FIELD}
        columns={alignProColumns(columns, SALES_DOC_LIST_FIELD_RANK)}
      />

      <UniPullQueryModal<PullPayableCandidate>
        open={pullFromPayableQuery.open}
        title={pullFromPayableAction.label}
        onCancel={pullFromPayableQuery.closeModal}
        onOk={() => {
          void pullFromPayableQuery.handleConfirm();
        }}
        rowKey="id"
        columns={pullTableColumns}
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
        searchPlaceholder={t(`${P}.pullSearchPlaceholder`)}
        page={pullFromPayableQuery.page}
        pageSize={pullFromPayableQuery.pageSize}
        total={pullFromPayableQuery.total}
        onPageChange={pullFromPayableQuery.handlePageChange}
        scopeOptions={pullFromPayableQuery.scopeOptions}
        scope={pullFromPayableQuery.scope}
        onScopeChange={pullFromPayableQuery.handleScopeChange}
        okText={pullFromPayableAction.targetLabel}
      />

      <UniPullQueryModal<PaymentPullCandidate>
        open={pullFromPaymentApplicationQuery.open}
        title={pullFromPaymentApplicationAction.label}
        onCancel={pullFromPaymentApplicationQuery.closeModal}
        onOk={() => {
          void pullFromPaymentApplicationQuery.handleConfirm();
        }}
        rowKey="id"
        columns={pullTableColumns}
        dataSource={pullFromPaymentApplicationQuery.dataSource}
        loading={pullFromPaymentApplicationQuery.loading}
        confirmLoading={pullFromPaymentApplicationQuery.confirmLoading}
        selectionType={pullFromPaymentApplicationQuery.selectionType}
        selectedRowKeys={pullFromPaymentApplicationQuery.selectedRowKeys}
        selectedRows={pullFromPaymentApplicationQuery.selectedRows}
        onSelectedRowKeysChange={pullFromPaymentApplicationQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromPaymentApplicationQuery.isRowDisabled}
        searchDraft={pullFromPaymentApplicationQuery.searchDraft}
        onSearchDraftChange={pullFromPaymentApplicationQuery.setSearchDraft}
        onSearchApply={pullFromPaymentApplicationQuery.handleSearchApply}
        onSearchClear={pullFromPaymentApplicationQuery.handleSearchClear}
        appliedKeyword={pullFromPaymentApplicationQuery.appliedKeyword}
        searchPlaceholder={t(`${P}.pullSearchPlaceholder`)}
        page={pullFromPaymentApplicationQuery.page}
        pageSize={pullFromPaymentApplicationQuery.pageSize}
        total={pullFromPaymentApplicationQuery.total}
        onPageChange={pullFromPaymentApplicationQuery.handlePageChange}
        scopeOptions={pullFromPaymentApplicationQuery.scopeOptions}
        scope={pullFromPaymentApplicationQuery.scope}
        onScopeChange={pullFromPaymentApplicationQuery.handleScopeChange}
        okText={pullFromPaymentApplicationAction.targetLabel}
      />

      <Modal
        title={t(`${P}.pullFormTitle`)}
        open={pullPreviewOpen}
        destroyOnHidden
        width={MODAL_CONFIG.LARGE_WIDTH}
        zIndex={pullPreviewZIndex}
        onCancel={resetPullPreview}
        okText={
          pullSourceKind === 'payment_application'
            ? pullFromPaymentApplicationAction.targetLabel
            : pullFromPayableAction.targetLabel
        }
        cancelText={t('common.cancel')}
        confirmLoading={pullSubmitting}
        onOk={() => void pullForm.submit()}
        okButtonProps={{
          disabled: !pullPreviewData || pullPreviewMaxPush <= 0,
        }}
      >
        {pullPreviewData ? (
              <ProForm
                key={`pull-payment-${pullPreviewSourceId}`}
                form={pullForm}
                submitter={false}
                onFinish={handlePullCreateSubmit}
                layout="vertical"
                {...financeFormGridProps}
              >
                <ProFormText name="source_code" label={t(`${P}.sourcePayable`)} readonly colProps={financeColHalf} />
                <ProFormText name="supplier_id" hidden />
                <ProFormText name="supplier_name" label={t('app.kuaicaiwu.common.supplier')} readonly colProps={financeColHalf} />
                <ProFormDigit
                  name="total_amount"
                  label={t(`${P}.col.amount`)}
                  min={0.01}
                  rules={[{ required: true }]}
                  fieldProps={financeAmountDigitFieldProps}
                  colProps={financeColHalf}
                />
                <ProFormDatePicker
                  name="payment_date"
                  label={t(`${P}.col.paymentDate`)}
                  rules={[{ required: true }]}
                  fieldProps={{ style: { width: '100%' } }}
                  colProps={financeColHalf}
                />
                <ProFormSelect
                  name="payment_method"
                  label={t(`${P}.col.paymentMethod`)}
                  options={paymentMethodOptions}
                  rules={[{ required: true, message: t(`${P}.selectPaymentMethod`) }]}
                  colProps={financeColHalf}
                />
                <PaymentAdvancePayeeField colProps={financeColHalf} />
                <ProFormSelect
                  name="settlement_type"
                  label={t(`${P}.settlementType.label`)}
                  options={paymentSettlementTypeOptions}
                  initialValue="normal"
                  colProps={financeColHalf}
                />
                <LedgerAccountFormFields
                  accounts={bankAccounts}
                  accountLabel={t(`${P}.outBankAccount`)}
                  noteLabel={t(`${P}.outAccountNote`)}
                  acceptanceNoteDirection="payable"
                  partnerFieldName="supplier_id"
                />
                <PaymentCounterpartyFormSection />
                <ProFormTextArea name="notes" label={t('common.remark')} fieldProps={{ rows: 3 }} colProps={financeColFull} />
                <DocumentAttachmentsField
                  category="payment_attachments"
                  required={Boolean(pullPreviewData?.require_payment_voucher)}
                  requiredMessage={t(`${P}.requirePaymentVoucherMissing`)}
                />
              </ProForm>
        ) : null}
      </Modal>

      <ModalForm
        title={t(`${P}.createTitle`)}
        open={createModalVisible}
        onOpenChange={setCreateModalVisible}
        onFinish={handleCreate}
        width={MODAL_CONFIG.LARGE_WIDTH}
        grid={false}
        formRef={createPaymentFormRef}
        initialValues={{ payment_date: dayjs(), settlement_type: 'normal' }}
        onValuesChange={(changedValues, allValues) => {
          handlePaymentVoucherFormValuesChange(
            createPaymentFormRef,
            changedValues as Record<string, unknown>,
            allValues as Record<string, unknown>,
          );
        }}
        submitter={{
          render: (_props, doms) => [
            <Button
              key="writeoff-confirm"
              loading={createWriteoffLoading}
              onClick={() => void submitCreateAndConfirm()}
            >
              {t(`${P}.writeoffAndConfirm`)}
            </Button>,
            ...doms,
          ],
        }}
      >
        <PaymentVoucherFormBody
          mode="create"
          bankAccounts={bankAccounts}
          supplierOptions={supplierOptions}
          paymentMethodOptions={paymentMethodOptions}
          settlementTypeOptions={paymentSettlementTypeOptions}
          showPullLines
          pullLineColumns={createLinePull.pullLineColumns}
          pullLineHeaderExtra={createLinePull.renderPullLineHeaderActions()}
          offsetPrepaymentLineColumns={createOffsetLines.offsetPrepaymentLineColumns}
          offsetPrepaymentHeaderExtra={createOffsetLines.renderOffsetPrepaymentHeaderActions()}
        />
        {createLinePull.renderPullModals()}
        {createOffsetLines.renderOffsetPullModals()}
      </ModalForm>

      <ModalForm
        key={editingRecord ? `edit-payment-${editingRecord.id}` : 'edit-payment'}
        title={t(`${P}.editTitle`)}
        open={Boolean(editingRecord)}
        onOpenChange={(open) => {
          if (!open) setEditingRecord(null);
        }}
        initialValues={
          editingRecord
            ? {
                supplier_id: editingRecord.supplier_id,
                total_amount: editingRecord.total_amount,
                payment_date: editingRecord.payment_date ? dayjs(editingRecord.payment_date) : dayjs(),
                payment_method: editingRecord.payment_method,
                settlement_type: editingRecord.settlement_type || 'normal',
                bank_account_id: editingRecord.bank_account_id,
                bank_account: editingRecord.bank_account,
                counterparty_account_name: editingRecord.counterparty_account_name,
                counterparty_bank_name: editingRecord.counterparty_bank_name,
                counterparty_bank_account: editingRecord.counterparty_bank_account,
                advance_payee_id: editingRecord.advance_payee_id,
                notes: editingRecord.notes,
                pull_lines: (editingRecord.pull_lines ?? []).map((line) => ({
                  sourceType: line.source_type,
                  sourceId: line.source_id,
                  sourceCode: line.source_code,
                  paymentAmount: line.amount,
                  maxAmount: line.max_amount,
                })),
                offset_prepayment_lines: (editingRecord.offset_prepayment_lines ?? []).map(
                  (line) => ({
                    prepaymentPaymentId: line.prepayment_payment_id,
                    sourceCode: line.source_code,
                    purchaseOrderCode: line.purchase_order_code,
                    maxUnsettled: line.unsettled_amount ?? line.amount,
                    offsetAmount: line.amount,
                  }),
                ),
                attachments: mapAttachmentsToUploadList(
                  editingRecord.attachments as Parameters<typeof mapAttachmentsToUploadList>[0],
                ),
              }
            : undefined
        }
        onFinish={handleUpdate}
        width={MODAL_CONFIG.LARGE_WIDTH}
        grid={false}
        formRef={editPaymentFormRef}
        onValuesChange={(changedValues, allValues) => {
          handlePaymentVoucherFormValuesChange(
            editPaymentFormRef,
            changedValues as Record<string, unknown>,
            allValues as Record<string, unknown>,
          );
        }}
        submitter={{
          render: (_props, doms) =>
            editingRecord?.status === 'Draft'
              ? [
                  <Button
                    key="writeoff-confirm"
                    loading={editWriteoffLoading}
                    onClick={() => void submitEditAndConfirm()}
                  >
                    {t(`${P}.writeoffAndConfirm`)}
                  </Button>,
                  ...doms,
                ]
              : doms,
        }}
      >
        <PaymentVoucherFormBody
          mode="edit"
          bankAccounts={bankAccounts}
          supplierOptions={supplierOptions}
          paymentMethodOptions={paymentMethodOptions}
          settlementTypeOptions={paymentSettlementTypeOptions}
          attachmentsRequired={Boolean(editingRecord?.require_payment_voucher)}
          attachmentsRequiredMessage={t(`${P}.requirePaymentVoucherMissing`)}
          showPullLines={editingRecord?.status === 'Draft'}
          pullLineColumns={editLinePull.pullLineColumns}
          pullLineHeaderExtra={editLinePull.renderPullLineHeaderActions()}
          offsetPrepaymentLineColumns={editOffsetLines.offsetPrepaymentLineColumns}
          offsetPrepaymentHeaderExtra={editOffsetLines.renderOffsetPrepaymentHeaderActions()}
        />
        {editingRecord?.status === 'Draft' ? editLinePull.renderPullModals() : null}
        {editingRecord?.status === 'Draft' ? editOffsetLines.renderOffsetPullModals() : null}
      </ModalForm>

      <FinanceVoucherDetailDrawer
        kind="payment"
        open={detailOpen}
        onClose={closeDetail}
        record={detailRecord}
        loading={detailLoading}
        error={detailError}
        onRetry={() => {
          const id = detailRetryIdRef.current;
          if (id != null) void loadDetail(id);
        }}
        bankAccountLabel={resolveBankLabel(detailRecord?.bank_account_id)}
        linkedNote={linkedNote}
        linkedNotePath="/apps/kuaicaiwu/finance-management/notes-payable"
        linkHandlers={voucherLinkHandlers}
        isRefund={false}
        extra={
          detailRecord ? (
            <DetailDrawerActions
              items={[
                {
                  key: 'print',
                  visible: Boolean(paymentPerms.canPrint) && detailRecord.id != null,
                  render: (
                    <Button
                      {...rowActionKind('print')}
                      icon={<PrinterOutlined />}
                      onClick={() =>
                        openPrint({
                          documentType: 'finance_payment',
                          documentId: detailRecord.id,
                        })
                      }
                    >
                      {t('components.uniAction.print')}
                    </Button>
                  ),
                },
                {
                  key: 'create-refund',
                  visible:
                    detailRecord.status === 'Confirmed'
                    && canCreateRefundFromVoucher(detailRecord, 'payment')
                    && Boolean(paymentRefundPerms.canCreate),
                  render: (
                    <Button
                      {...rowActionKind('submit')}
                      onClick={() =>
                        navigate('/apps/kuaicaiwu/finance-management/payment-refunds', {
                          state: { pullSourceIds: [detailRecord.id] },
                        })
                      }
                    >
                      {t('app.kuaicaiwu.paymentRefund.pullCreate')}
                    </Button>
                  ),
                },
                {
                  key: 'view-refunds',
                  visible:
                    detailRecord.status === 'Confirmed'
                    && isFinanceVoucherCorrectionBlockedByRefund(detailRecord)
                    && Boolean(paymentRefundPerms.canRead),
                  render: (
                    <Button
                      {...rowActionKind('read')}
                      {...rowActionLabelKeep()}
                      onClick={() =>
                        navigate('/apps/kuaicaiwu/finance-management/payment-refunds', {
                          state: { filterSourceId: detailRecord.id },
                        })
                      }
                    >
                      {t(`${P}.viewRefunds`)}
                    </Button>
                  ),
                },
                {
                  key: 'confirm',
                  visible: detailRecord.status === 'Draft' && Boolean(paymentPerms.canAction?.('audit')),
                  render: (
                    <ActionConfirmPopconfirm
                      title={t(`${P}.confirmTitle`)}
                      description={t(`${P}.confirmContent`, { code: detailRecord.payment_code })}
                      onConfirm={() => executeConfirm(detailRecord)}
                    >
                      <Button {...rowActionKind('audit')} onClick={(e) => e.stopPropagation()}>
                        {t('common.confirm')}
                      </Button>
                    </ActionConfirmPopconfirm>
                  ),
                },
                {
                  key: 'edit',
                  visible: detailRecord.status === 'Draft' && Boolean(paymentPerms.canUpdate),
                  render: (
                    <Button {...rowActionKind('update')} onClick={() => openEdit(detailRecord)}>
                      {t('common.edit')}
                    </Button>
                  ),
                },
                {
                  key: 'settle',
                  visible: detailRecord.status === 'Confirmed' && Number(detailRecord.unsettled_amount ?? 0) > 0,
                  render: (
                    <ActionConfirmPopconfirm
                      title={t(`${P}.repairSettleTitle`)}
                      description={t(`${P}.repairSettleContent`, { code: detailRecord.payment_code })}
                      onConfirm={() => executeRepairSettle(detailRecord)}
                    >
                      <Button
                        {...rowActionSettleVoucher('submit')}
                        title={t(`${P}.repairSettleHint`)}
                      >
                        {t('app.kuaicaiwu.common.settle')}
                      </Button>
                    </ActionConfirmPopconfirm>
                  ),
                },
                {
                  key: 'unconfirm',
                  visible:
                    detailRecord.status === 'Confirmed'
                    && canCorrectFinanceVoucher(detailRecord)
                    && Boolean(paymentPerms.canAction?.('revoke')),
                  render: (
                    <Button {...rowActionKind('revoke')} onClick={() => void executeUnconfirm(detailRecord)}>
                      {t(`${P}.unconfirm`)}
                    </Button>
                  ),
                },
                {
                  key: 'void',
                  visible:
                    detailRecord.status === 'Draft'
                    && canCorrectFinanceVoucher(detailRecord)
                    && Boolean(paymentPerms.canAction?.('revoke')),
                  render: (
                    <ActionConfirmPopconfirm
                      title={t(`${P}.voidTitle`)}
                      description={t(`${P}.voidContent`, { code: detailRecord.payment_code })}
                      onConfirm={() => executeCancelVoucher(detailRecord)}
                    >
                      <Button {...rowActionKind('revoke')} onClick={(e) => e.stopPropagation()}>
                        {t('app.kuaicaiwu.common.void')}
                      </Button>
                    </ActionConfirmPopconfirm>
                  ),
                },
                {
                  key: 'delete',
                  visible:
                    canCorrectFinanceVoucher(detailRecord)
                    && Boolean(paymentPerms.canDelete)
                    && (detailRecord.status === 'Draft'
                      || detailRecord.status === 'Cancelled'
                      || detailRecord.status === 'Confirmed'),
                  render: (
                    <ActionConfirmPopconfirm
                      title={t(`${P}.deleteTitle`)}
                      description={t(`${P}.deleteContent`, { code: detailRecord.payment_code })}
                      okType="danger"
                      onConfirm={() => executeDelete(detailRecord)}
                    >
                      <Button danger {...rowActionKind('delete')} onClick={(e) => e.stopPropagation()}>
                        {t('common.delete')}
                      </Button>
                    </ActionConfirmPopconfirm>
                  ),
                },
              ]}
            />
          ) : null
        }
      />
      {PrintModal}
      <VoucherRemediationSettleModal
        open={remediationVoucher != null}
        side="payment"
        voucher={remediationVoucher}
        onClose={() => setRemediationVoucher(null)}
        onSuccess={() => {
          actionRef.current?.reload();
          refreshOpenDetail();
        }}
      />
    </ListPageTemplate>
  );
};

/** 页级 Provider：与 hook 同模块实例，避免 HMR 后应用壳 Context 错位 */
const PaymentsPageRoute: React.FC = () => (
  <FinanceVoucherDetailProvider>
    <PaymentsPage />
  </FinanceVoucherDetailProvider>
);

export default PaymentsPageRoute;
