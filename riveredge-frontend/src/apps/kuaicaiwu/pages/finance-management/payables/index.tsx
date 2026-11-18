/**
 * 应付单列表页
 */
import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { rowActionKind, rowActionMakePayment, rowActionIssueInvoice } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button, Typography, Modal, Alert, Table, Empty, Form, InputNumber, theme } from 'antd';
import { ModalForm, ProForm, ProFormDatePicker, ProFormMoney, ProFormSelect, ProFormText, ProFormTextArea } from '@ant-design/pro-components';
import type { ProFormInstance } from '@ant-design/pro-components';
import { PlusOutlined } from '@ant-design/icons';
import { apiRequest } from '../../../../../services/api';
import {
    payableService,
    type PayablePullCandidate,
    type PayablePullPreview,
} from '../../../services/finance/payable';
import { Payable, PayableCreateData } from '../../../types/finance/payable';
import { importInChunksViaPerItemCreate } from '../../../../../utils/chunkedBulkImport';
import { buildFutureDateShortcutFieldProps } from '../../../../../utils/futureDatePickerShortcuts';
import { useTranslation } from 'react-i18next';
import {
  buildFactoryImportTemplate,
  resolveFactoryImportHeaderIndexMap,
} from '../../../../../utils/spreadsheetImportTemplate';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { UniTable } from '../../../../../components/uni-table';
import { UniAuditBatchMenuButton, createUniAuditBatchHandlers } from '../../../../../components/uni-batch';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { UniLifecycle } from '../../../../../components/uni-lifecycle';
import {
    ListPageTemplate,
    MODAL_CONFIG,
    MODAL_NESTED_ABOVE_PARENT_OFFSET,
} from '../../../../../components/layout-templates';
import { financeColFull, financeColHalf, financeFormGridProps } from '../../../utils/financeFormLayout';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import {
  UniPullQueryModal,
  filterByPullScope,
  paginatePullRows,
  UNI_PULL_QUERY_MAX_FETCH_LIMIT,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { getPayableLifecycle } from '../../../utils/financeLifecycle';
import {
  isPurchaseReturnOffsetPayable,
  payableDisplayTotalAmount,
} from '../../../utils/payableOffset';
import { buildPayableStatusEnum, buildReviewStatusEnum } from '../../../utils/financeSharedOptions';
import { buildKuaicaiwuPullCreateMenuItems, getKuaicaiwuDocumentAction } from '../../../constants/documentActionRegistry';
import { payableCapabilityReasonMessage } from '../../../utils/payableCapabilityMessages';
import {
  initPullReceiptLineSelection,
  reconcilePullReceiptLinesForHeaderAmount,
  sumPullReceiptLineAmounts,
  type PullReceiptFinanceDetailLine,
} from '../../../../kuaizhizao/utils/pullReceiptFinanceLines';
import { renderRefundExecutionMarker } from '../../../utils/financeUiLabels';
import dayjs from 'dayjs';
import DocumentAttachmentsField from '../../../../kuaizhizao/components/DocumentAttachmentsField';
import { normalizeDocumentAttachments } from '../../../../kuaizhizao/utils/documentAttachments';
import { formatDateTime, todaySiteDateString, formatCurrencyAmount, formatAmount } from '../../../../../utils/format';
import {
  FINANCE_DOC_PINNED_STATUS_FIELD,
  financeDocCodePartnerSearchColumns,
  financeDocCreatedUpdatedColumns,
  parseFinanceAgingUrlFilters,
  resolvePayableListParams,
} from '../../../utils/financeListCore';
import { formatAgingBucket } from '../../../utils/financeUiLabels';
import type { PayableListParams } from '../../../types/finance/payable';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import {
  DocumentPushProgressBar,
  DOCUMENT_PROGRESS_COLUMN_DEFAULTS,
} from '../../../../kuaizhizao/pages/sales-management/shared/DocumentPushProgressBar';
import { payablePaymentPushPercent, payableInvoicePushPercent } from '../../../../kuaizhizao/pages/sales-management/shared/pushProgress';
import { renderPayableInvoiceStatusTag } from '../../../utils/financeInvoiceStatusUi';
import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { fetchAllListItems } from '../../../../../utils/fetchAllListPages';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import { LinkedDocumentCode } from '../../../../../components/linked-document-code/LinkedDocumentCode';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import MergeFinanceDocsModal, {
  type MergeFinanceMode,
  type MergeFinanceSourceRow,
} from '../../../components/MergeFinanceDocsModal';

const P = 'app.kuaicaiwu.payable';
const PAYABLE_RESOURCE = 'kuaicaiwu:payable';
const PAYMENT_RESOURCE = 'kuaicaiwu:payment';
const PURCHASE_INVOICE_RESOURCE = 'kuaicaiwu:purchase-invoice';

type PullPreviewKind = 'purchase_order' | 'purchase_receipt';

const formatPullMoney = (value: number) =>
  formatCurrencyAmount(value || 0);

function canCorrectPayableRow(record: Payable): boolean {
  if (isPurchaseReturnOffsetPayable(record)) return false;
  if (Number(record.paid_amount ?? 0) > 0) return false;
  if (Number(record.refunded_amount ?? 0) > 0) return false;
  const refundExec = String(record.refund_execution_status || '').trim();
  if (refundExec === '部分退款' || refundExec === '全部退款') return false;
  return true;
}

const PayableList: React.FC = () => {
    const actionRef = useRef<ActionType>();
    const lastListParamsRef = useRef<Record<string, string | number | boolean | undefined>>({});
    const createFormRef = useRef<ProFormInstance>(null);
    const [pullForm] = Form.useForm();
    const [createModalVisible, setCreateModalVisible] = useState(false);
    const [createSeed, setCreateSeed] = useState<Record<string, unknown> | undefined>(undefined);
    const [editingRecord, setEditingRecord] = useState<Payable | null>(null);
    const [pullPreviewOpen, setPullPreviewOpen] = useState(false);
    const [pullPreviewLoading, setPullPreviewLoading] = useState(false);
    const [pullSubmitting, setPullSubmitting] = useState(false);
    const [pullPreviewData, setPullPreviewData] = useState<PayablePullPreview | null>(null);
    const [pullPreviewSourceIds, setPullPreviewSourceIds] = useState<number[]>([]);
    const [pullPreviewKind, setPullPreviewKind] = useState<PullPreviewKind | null>(null);
    const [pullReceiptSelectedIds, setPullReceiptSelectedIds] = useState<number[]>([]);
    const [pullReceiptLineAmounts, setPullReceiptLineAmounts] = useState<Record<number, number>>({});
    const pullFromPurchaseOrderCloseRef = useRef<(() => void) | null>(null);
    const pullFromPurchaseOrderOpenRef = useRef<(() => void) | null>(null);
    const pullFromPurchaseReceiptCloseRef = useRef<(() => void) | null>(null);
    const pullFromPurchaseReceiptOpenRef = useRef<(() => void) | null>(null);
    const { token } = theme.useToken();
    const pullPreviewZIndex = token.zIndexPopupBase + MODAL_NESTED_ABOVE_PARENT_OFFSET * 2;
    const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
    const [tableRows, setTableRows] = useState<Payable[]>([]);
    const [supplierOptions, setSupplierOptions] = useState<{ label: string; value: number }[]>([]);
    const { message: messageApi } = App.useApp();
    const { t, i18n } = useTranslation();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const urlAgingFilters = useMemo(() => parseFinanceAgingUrlFilters(searchParams), [searchParams]);
    const pullFromPurchaseOrderAction = getKuaicaiwuDocumentAction('payable.pull_from_purchase_order');
    const pullFromPurchaseReceiptAction = getKuaicaiwuDocumentAction('payable.pull_from_purchase_receipt');

    const payableAuditEnabled = useAuditRequired('payable', false);
    const payablePerms = useResourcePermissions(PAYABLE_RESOURCE);
    const paymentPerms = useResourcePermissions(PAYMENT_RESOURCE);
    const purchaseInvoicePerms = useResourcePermissions(PURCHASE_INVOICE_RESOURCE);
    const payableAuditBatchHandlers = useMemo(
        () => createUniAuditBatchHandlers('payable'),
        [],
    );
    const selectedRecordsForBatch = useMemo(
        () => tableRows.filter((row) => row.id != null && selectedRowKeys.includes(row.id)),
        [tableRows, selectedRowKeys],
    );
    const [mergeModalOpen, setMergeModalOpen] = useState(false);
    const [mergeMode, setMergeMode] = useState<MergeFinanceMode>('merge_payment');
    const [mergeSources, setMergeSources] = useState<MergeFinanceSourceRow[]>([]);
    const handlePayableAuditBatchSuccess = () => {
        setSelectedRowKeys([]);
    actionRef.current?.reload();
    };

    useEffect(() => {
    actionRef.current?.reload();
    }, [urlAgingFilters.aging_bucket, urlAgingFilters.overdue_only]);

    const agingFilterDescription = useMemo(() => {
        const parts: string[] = [];
        if (urlAgingFilters.aging_bucket) {
            parts.push(formatAgingBucket(urlAgingFilters.aging_bucket, t));
        }
        if (urlAgingFilters.overdue_only) {
            parts.push(t('app.kuaicaiwu.financeUi.aging.overdueOnly'));
        }
        return parts.join(' / ');
    }, [t, urlAgingFilters.aging_bucket, urlAgingFilters.overdue_only]);

    const openMergeModal = (mode: MergeFinanceMode) => {
        const selected = selectedRecordsForBatch;
        if (selected.length === 0) {
            messageApi.warning(t('app.kuaicaiwu.mergeFinance.needSelection'));
            return;
        }
        const partnerIds = new Set(selected.map((r) => Number(r.supplier_id)));
        if (partnerIds.size !== 1) {
            messageApi.error(t('app.kuaicaiwu.mergeFinance.sameSupplierRequired'));
            return;
        }
        const sources: MergeFinanceSourceRow[] = [];
        for (const row of selected) {
            const isInvoice = mode === 'merge_purchase_invoice';
            const available = isInvoice
                ? Number(row.remaining_invoice_amount ?? row.total_amount ?? 0)
                : Number(row.remaining_amount ?? 0);
            const pushAllowed = isInvoice
                ? row.capabilities?.push_purchase_invoice?.allowed !== false
                : row.capabilities?.push_payment?.allowed !== false;
            if (!(available > 0) || !pushAllowed) {
                messageApi.error(
                    t('app.kuaicaiwu.mergeFinance.sourceNotEligible', {
                        code: row.payable_code || row.id,
                    }),
                );
                return;
            }
            sources.push({
                id: Number(row.id),
                code: String(row.payable_code || row.id),
                partnerId: Number(row.supplier_id),
                partnerName: String(row.supplier_name || ''),
                availableAmount: available,
            });
        }
        setMergeMode(mode);
        setMergeSources(sources);
        setMergeModalOpen(true);
    };

    const mergePaymentDisabled =
        !paymentPerms.canCreate ||
        selectedRecordsForBatch.length === 0 ||
        selectedRecordsForBatch.some((r) => isPurchaseReturnOffsetPayable(r)) ||
        new Set(selectedRecordsForBatch.map((r) => Number(r.supplier_id))).size !== 1;
    const mergeInvoiceDisabled =
        !purchaseInvoicePerms.canCreate ||
        selectedRecordsForBatch.length === 0 ||
        selectedRecordsForBatch.some((r) => isPurchaseReturnOffsetPayable(r)) ||
        new Set(selectedRecordsForBatch.map((r) => Number(r.supplier_id))).size !== 1;

    const payableImportTemplate = useMemo(
        () =>
            buildFactoryImportTemplate(
                t,
                [
                    {
                        field: 'supplier',
                        required: true,
                        labelKey: `${P}.import.supplierName`,
                        aliases: ['供应商名称', '供应商'],
                    },
                    {
                        field: 'amount',
                        required: true,
                        labelKey: `${P}.import.amount`,
                        aliases: ['应付金额', '金额'],
                    },
                    { field: 'dueDate', labelKey: `${P}.import.dueDate`, aliases: ['到期日期'] },
                    { field: 'businessDate', labelKey: `${P}.import.businessDate`, aliases: ['业务日期'] },
                    { field: 'notes', labelKey: 'common.remark', aliases: ['备注'] },
                ],
                [
                    t(`${P}.importExample.supplierName`),
                    t(`${P}.importExample.amount`),
                    t(`${P}.importExample.dueDate`),
                    t(`${P}.importExample.businessDate`),
                    '',
                ],
            ),
        [t, i18n.language],
    );

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
    }, []);

    const handleCreate = async (values: any) => {
        const today = formatDateTime(dayjs(), 'YYYY-MM-DD');
        const data: PayableCreateData = {
            source_type: '手工',
            source_id: 0,
            source_code: '手工',
            supplier_id: values.supplier_id,
            supplier_name: supplierOptions.find(o => o.value === values.supplier_id)?.label || '',
            total_amount: values.total_amount,
            paid_amount: 0,
            remaining_amount: values.total_amount,
            due_date: values.due_date || today,
            business_date: values.business_date || today,
            status: '未付款',
            review_status: '草稿',
            notes: values.notes,
            attachments: normalizeDocumentAttachments(values.attachments),
        };
        const created = await payableService.createPayable(data);
        messageApi.success(t('common.createSuccess'));
        setCreateModalVisible(false);
    actionRef.current?.reload();
        if (created?.id) {
            navigate(`/apps/kuaicaiwu/finance-management/payables/${created.id}`);
        }
        return true;
    };

    const openEdit = (record: Payable) => {
        setEditingRecord(record);
    };

    const executeDeleteOne = async (record: Payable) => {
        try {
            await payableService.deletePayable(record.id);
            messageApi.success(t('common.deleteSuccess'));
            actionRef.current?.reload();
        } catch (error: any) {
            messageApi.error(error?.message || t('common.deleteFailed'));
        }
    };

    const handleUpdate = async (values: any) => {
        if (!editingRecord) return false;
        const today = formatDateTime(dayjs(), 'YYYY-MM-DD');
        try {
            await payableService.updatePayable(editingRecord.id, {
                supplier_id: values.supplier_id,
                supplier_name:
                    supplierOptions.find((o) => o.value === values.supplier_id)?.label ||
                    editingRecord.supplier_name,
                total_amount: values.total_amount,
                due_date: values.due_date || today,
                business_date: values.business_date || today,
                notes: values.notes,
                attachments: normalizeDocumentAttachments(values.attachments),
            });
            messageApi.success(t('common.updateSuccess'));
            setEditingRecord(null);
            actionRef.current?.reload();
            return true;
        } catch (error: any) {
            messageApi.error(error?.message || t('common.updateFailed'));
            return false;
        }
    };

    const resetPullPreview = () => {
        setPullPreviewOpen(false);
        setPullPreviewSourceIds([]);
        setPullPreviewData(null);
        setPullPreviewKind(null);
        setPullReceiptSelectedIds([]);
        setPullReceiptLineAmounts({});
        pullForm.resetFields();
    };

    const openPullPreview = async (
        kind: PullPreviewKind,
        sourceIdsInput: number | number[],
        options?: { closeSourceModal?: () => void; reopenSourceModal?: () => void },
    ) => {
        const sourceIds = (Array.isArray(sourceIdsInput) ? sourceIdsInput : [sourceIdsInput])
            .map((id) => Number(id))
            .filter((id) => Number.isFinite(id) && id > 0);
        if (!sourceIds.length) return;
        options?.closeSourceModal?.();
        setPullPreviewKind(kind);
        setPullPreviewOpen(false);
        setPullPreviewLoading(true);
        setPullPreviewData(null);
        setPullPreviewSourceIds(sourceIds);
        const hideLoading = messageApi.loading(t(`${P}.pullPreviewLoading`), 0);
        try {
            const data =
                kind === 'purchase_order'
                    ? await payableService.previewPullFromPurchaseOrder(sourceIds[0])
                    : sourceIds.length === 1
                      ? await payableService.previewPullFromPurchaseReceipt(sourceIds[0])
                      : await payableService.previewPullFromPurchaseReceipts(sourceIds);
            setPullPreviewData(data);
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

    const isPullPayableSelectable = useCallback(
        (record: PayablePullCandidate) => record.capabilities?.pull_payable?.allowed !== false,
        [],
    );

    const pullQueryScopeOptions = useMemo(
        () => [
            { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
            { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
        ],
        [t],
    );

    const pullFromPurchaseOrderQuery = useUniPullQuery<PayablePullCandidate>({
        rowKey: 'id',
        selectionType: 'checkbox',
        scopeOptions: pullQueryScopeOptions,
        defaultScope: 'pullable',
        isRowDisabled: (record) => !isPullPayableSelectable(record),
        loadData: async ({ keyword, page, pageSize, scope }) => {
            try {
                const res = await payableService.listPurchaseOrderPullCandidates({
                    skip: 0,
                    limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
                    keyword: keyword.trim() || undefined,
                });
                const rows = res.data || [];
                const filtered = filterByPullScope(rows, scope, isPullPayableSelectable);
                return paginatePullRows(filtered, page, pageSize);
            } catch (e: any) {
                messageApi.error(
                    e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t(`${P}.loadSourceFailed`),
                );
                return { data: [], total: 0 };
            }
        },
        onConfirm: async (keys, rows) => {
            const selectedIds = rows
                .filter((x) => keys.some((k) => String(k) === String(x.id)))
                .map((x) => Number(x.id))
                .filter((id) => Number.isFinite(id) && id > 0);
            if (!selectedIds.length) {
                messageApi.warning(t(`${P}.selectSource`, { label: pullFromPurchaseOrderAction.sourceLabel }));
                return;
            }
            await openPullPreview('purchase_order', selectedIds[0], {
                closeSourceModal: () => pullFromPurchaseOrderCloseRef.current?.(),
                reopenSourceModal: () => pullFromPurchaseOrderOpenRef.current?.(),
            });
            if (selectedIds.length > 1) {
                messageApi.info(t(`${P}.pull.multiSelectedFirstOnly`));
            }
        },
    });
    pullFromPurchaseOrderCloseRef.current = pullFromPurchaseOrderQuery.closeModal;
    pullFromPurchaseOrderOpenRef.current = pullFromPurchaseOrderQuery.openModal;

    const pullFromPurchaseReceiptQuery = useUniPullQuery<PayablePullCandidate>({
        rowKey: 'id',
        selectionType: 'checkbox',
        scopeOptions: pullQueryScopeOptions,
        defaultScope: 'pullable',
        isRowDisabled: (record) => !isPullPayableSelectable(record),
        loadData: async ({ keyword, page, pageSize, scope }) => {
            try {
                const res = await payableService.listPurchaseReceiptPullCandidates({
                    skip: 0,
                    limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
                    keyword: keyword.trim() || undefined,
                });
                const rows = res.data || [];
                const filtered = filterByPullScope(rows, scope, isPullPayableSelectable);
                return paginatePullRows(filtered, page, pageSize);
            } catch (e: any) {
                messageApi.error(
                    e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || t(`${P}.loadSourceFailed`),
                );
                return { data: [], total: 0 };
            }
        },
        onConfirm: async (keys, rows) => {
            const selectedIds = rows
                .filter((x) => keys.some((k) => String(k) === String(x.id)))
                .map((x) => Number(x.id))
                .filter((id) => Number.isFinite(id) && id > 0);
            if (!selectedIds.length) {
                messageApi.warning(t(`${P}.selectSource`, { label: pullFromPurchaseReceiptAction.sourceLabel }));
                return;
            }
            const supplierIds = new Set(
                rows
                    .filter((x) => selectedIds.includes(Number(x.id)))
                    .map((x) => Number(x.supplier_id ?? 0))
                    .filter((id) => id > 0),
            );
            if (supplierIds.size > 1) {
                messageApi.warning(t('app.kuaicaiwu.mergeFinance.sameSupplierRequired'));
                return;
            }
            pullFromPurchaseReceiptCloseRef.current?.();
            await openPullPreview('purchase_receipt', selectedIds);
        },
    });
    pullFromPurchaseReceiptCloseRef.current = pullFromPurchaseReceiptQuery.closeModal;
    pullFromPurchaseReceiptOpenRef.current = pullFromPurchaseReceiptQuery.openModal;

    const handlePullCreateSubmit = async (values: any) => {
        if (!pullPreviewData || !pullPreviewSourceIds.length || !pullPreviewKind) {
            messageApi.warning(t(`${P}.pullPreviewIncomplete`));
            return false;
        }
        if (pullPreviewData.has_blocking_issues) {
            messageApi.warning(
                payableCapabilityReasonMessage(pullPreviewData.blocking_reason, t)
                    || t(`${P}.pullPreviewBlocked`),
            );
            return false;
        }
        const maxPush =
            Number(
                pullPreviewData.max_push_total ??
                    (pullPreviewData.items || []).reduce(
                        (sum, row) => sum + Number(row.max_push_quantity ?? 0),
                        0,
                    ),
            ) || 0;
        const totalAmount = Number(values.total_amount) || 0;
        if (totalAmount <= 0) {
            messageApi.warning(t(`${P}.amountRequired`));
            return false;
        }
        if (totalAmount > maxPush) {
            messageApi.warning(t(`${P}.pullExceedMax`, { max: formatAmount(maxPush) }));
            return false;
        }
        let pullReceiptLines: PayableCreateData['pull_receipt_lines'];
        if (
            pullPreviewKind === 'purchase_receipt'
            && (pullPreviewData.detail_lines?.length ?? 0) > 0
        ) {
            if (pullReceiptSelectedIds.length === 0) {
                messageApi.warning(t(`${P}.pull.selectAtLeastOneLine`));
                return false;
            }
            const detailLines = pullPreviewData.detail_lines ?? [];
            const reconciled = reconcilePullReceiptLinesForHeaderAmount(
                pullReceiptSelectedIds,
                detailLines,
                totalAmount,
                pullReceiptLineAmounts,
            );
            if (reconciled.selectedItemIds.length === 0) {
                messageApi.warning(t(`${P}.pull.selectAtLeastOneLine`));
                return false;
            }
            if (Math.abs(reconciled.lineSum - totalAmount) > 0.009) {
                messageApi.warning(t(`${P}.pull.lineAmountMismatch`));
                return false;
            }
            const detailById = new Map(detailLines.map((row) => [row.purchase_receipt_item_id, row]));
            for (const id of reconciled.selectedItemIds) {
                const cap = Number(detailById.get(id)?.max_push_amount ?? 0);
                const amt = Number(reconciled.amounts[id] ?? 0);
                if (amt <= 0 || amt > cap + 0.009) {
                    messageApi.warning(t(`${P}.pull.lineExceedMax`));
                    return false;
                }
            }
            pullReceiptLines = reconciled.payload;
        }
        const sourceLabel =
            pullPreviewKind === 'purchase_order'
                ? pullFromPurchaseOrderAction.sourceLabel
                : pullFromPurchaseReceiptAction.sourceLabel;
        setPullSubmitting(true);
        try {
            await payableService.createPayable({
                source_type: pullPreviewKind,
                source_id: pullPreviewSourceIds[0],
                source_code: pullPreviewData.source_code || '',
                pull_source_type: pullPreviewKind,
                pull_source_id: pullPreviewSourceIds[0],
                pull_source_ids:
                    pullPreviewKind === 'purchase_receipt' && pullPreviewSourceIds.length > 1
                        ? pullPreviewSourceIds
                        : undefined,
                supplier_id: Number(pullPreviewData.supplier_id || 0),
                supplier_name: pullPreviewData.supplier_name || '',
                total_amount: totalAmount,
                paid_amount: 0,
                remaining_amount: totalAmount,
                due_date: formatDateTime(values.due_date || dayjs().add(30, 'day'), 'YYYY-MM-DD'),
                business_date: formatDateTime(values.business_date || dayjs(), 'YYYY-MM-DD'),
                status: '未付款',
                review_status: '草稿',
                notes:
                    String(values.notes ?? '').trim() ||
                    t('app.kuaicaiwu.common.createdFromSourceNote', {
                        source: sourceLabel,
                        code: pullPreviewData.source_code,
                    }),
                attachments: normalizeDocumentAttachments(values.attachments),
                pull_receipt_lines: pullReceiptLines,
            });
            messageApi.success(t(`${P}.pullCreateSuccess`, { target: pullFromPurchaseOrderAction.targetLabel }));
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

    const pullPreviewMaxPush =
        Number(
            pullPreviewData?.max_push_total ??
                (pullPreviewData?.items || []).reduce(
                    (sum, row) => sum + Number(row.max_push_quantity ?? 0),
                    0,
                ),
        ) || 0;
    const pullPreviewTargetLabel = pullFromPurchaseOrderAction.targetLabel;

    const pullFormInitialValues = useMemo(() => {
        if (!pullPreviewData || !pullPreviewKind) return undefined;
        const maxPush =
            Number(
                pullPreviewData.max_push_total ??
                    (pullPreviewData.items || []).reduce(
                        (sum, row) => sum + Number(row.max_push_quantity ?? 0),
                        0,
                    ),
            ) || 0;
        const sourceLabel =
            pullPreviewKind === 'purchase_order'
                ? pullFromPurchaseOrderAction.sourceLabel
                : pullFromPurchaseReceiptAction.sourceLabel;
        return {
            source_code: pullPreviewData.source_code,
            supplier_name: pullPreviewData.supplier_name,
            total_amount: maxPush > 0 ? maxPush : undefined,
            due_date: dayjs().add(30, 'day'),
            business_date: dayjs(),
            notes: t('app.kuaicaiwu.common.createdFromSourceNote', {
                source: sourceLabel,
                code: pullPreviewData.source_code,
            }),
        };
    }, [
        pullPreviewData,
        pullPreviewKind,
        pullFromPurchaseOrderAction.sourceLabel,
        pullFromPurchaseReceiptAction.sourceLabel,
        t,
    ]);

    useEffect(() => {
        if (!pullPreviewOpen || pullPreviewLoading || !pullFormInitialValues) return;
        pullForm.setFieldsValue(pullFormInitialValues);
    }, [pullPreviewOpen, pullPreviewLoading, pullFormInitialValues, pullForm]);

    useEffect(() => {
        if (!pullPreviewOpen || pullPreviewKind !== 'purchase_receipt' || !pullPreviewData) return;
        const lines = (pullPreviewData.detail_lines ?? []) as PullReceiptFinanceDetailLine[];
        if (!lines.length) {
            setPullReceiptSelectedIds([]);
            setPullReceiptLineAmounts({});
            return;
        }
        const { selectedItemIds, amounts } = initPullReceiptLineSelection(lines);
        setPullReceiptSelectedIds(selectedItemIds);
        setPullReceiptLineAmounts(amounts);
        const sum = sumPullReceiptLineAmounts(selectedItemIds, amounts);
        if (sum > 0) {
            pullForm.setFieldsValue({ total_amount: sum });
        }
    }, [pullPreviewOpen, pullPreviewKind, pullPreviewData, pullForm]);

    const pullTotalAmountWatch = Form.useWatch('total_amount', pullForm);

    useEffect(() => {
        if (!pullPreviewOpen || pullPreviewKind !== 'purchase_receipt' || !pullPreviewData) return;
        if (pullReceiptSelectedIds.length === 0) return;
        const target = Number(pullTotalAmountWatch || 0);
        if (!(target > 0)) return;
        const detailLines = (pullPreviewData.detail_lines ?? []) as PullReceiptFinanceDetailLine[];
        const currentSum = sumPullReceiptLineAmounts(pullReceiptSelectedIds, pullReceiptLineAmounts);
        if (Math.abs(currentSum - target) <= 0.009) return;
        const reconciled = reconcilePullReceiptLinesForHeaderAmount(
            pullReceiptSelectedIds,
            detailLines,
            target,
        );
        setPullReceiptLineAmounts(reconciled.amounts);
        if (reconciled.selectedItemIds.join(',') !== pullReceiptSelectedIds.join(',')) {
            setPullReceiptSelectedIds(reconciled.selectedItemIds);
        }
    }, [
        pullPreviewOpen,
        pullPreviewKind,
        pullPreviewData,
        pullReceiptSelectedIds,
        pullReceiptLineAmounts,
        pullTotalAmountWatch,
    ]);

    const handlePullPreviewOk = async () => {
        if (pullPreviewLoading || !pullPreviewData) {
            messageApi.warning(t(`${P}.pullPreviewIncomplete`));
            return;
        }
        if (pullPreviewData.has_blocking_issues) {
            messageApi.warning(
                payableCapabilityReasonMessage(pullPreviewData.blocking_reason, t)
                    || t(`${P}.pullPreviewBlocked`),
            );
            return;
        }
        if (pullPreviewMaxPush <= 0) {
            messageApi.warning(t(`${P}.pullNoPayableAmount`));
            return;
        }
        try {
            const values = await pullForm.validateFields();
            await handlePullCreateSubmit(values);
        } catch {
            messageApi.warning(t(`${P}.pullFormValidationFailed`));
        }
    };

    const pullTableColumns: ProColumns<PayablePullCandidate>[] = useMemo(
        () => [
            { title: t(`${P}.pullCol.sourceCode`), dataIndex: 'code', width: 220, ellipsis: true },
            { title: t('app.kuaicaiwu.common.supplier'), dataIndex: 'supplier_name', width: 160, ellipsis: true },
            { title: t(`${P}.pullCol.sourceStatus`), dataIndex: 'source_status', width: 100, ellipsis: true },
            { title: t(`${P}.pullCol.sourceDate`), dataIndex: 'source_date', width: 120, ellipsis: true },
            { title: t(`${P}.pullCol.docAmount`), dataIndex: 'amount', valueType: 'money', width: 120, align: 'right' },
        ],
        [t],
    );

    const handleBatchDelete = async (keys: React.Key[]) => {
        try {
            for (const id of keys) {
                await payableService.deletePayable(Number(id));
            }
    messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
            setSelectedRowKeys([]);
    actionRef.current?.reload();
        } catch (error: any) {
            messageApi.error(error?.message || t('common.deleteFailed'));
        }
    };

    const columns: ProColumns<Payable>[] = useMemo(() => [
        ...financeDocCodePartnerSearchColumns({
            docCodeLabel: t('app.kuaicaiwu.common.code'),
            docCodeField: 'payable_code',
            partnerLabel: t('app.kuaicaiwu.common.supplier', '供应商'),
            partnerIdField: 'supplier_id',
            partnerNameField: 'supplier_name',
            partnerOptions: supplierOptions,
        }),
        {
            title: t('app.kuaicaiwu.common.code'),
            key: 'finance_doc_partner_stacked',
            dataIndex: 'payable_code',
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
                    secondary={String(entity.payable_code ?? '')}
                    onSecondaryClick={() =>
                        navigate(`/apps/kuaicaiwu/finance-management/payables/${entity.id}`)
                    }
                    primaryExtra={
                        (() => {
                            const tags: React.ReactNode[] = [];
                            if (isPurchaseReturnOffsetPayable(entity)) {
                                tags.push(
                                    <MarkerTag key="offset" color="geekblue">
                                        {t(`${P}.offsetMarker`)}
                                    </MarkerTag>,
                                );
                            }
                            const refundExec = String(entity.refund_execution_status || '').trim();
                            if (refundExec === '部分退款' || refundExec === '全部退款') {
                                const { label, color } = renderRefundExecutionMarker(refundExec, t);
                                tags.push(
                                    <MarkerTag key="refund" color={color}>
                                        {label}
                                    </MarkerTag>,
                                );
                            }
                            if (tags.length === 0) return null;
                            return <span style={{ display: 'inline-flex', gap: 4, flexWrap: 'wrap' }}>{tags}</span>;
                        })()
                    }
                />
            ),
        },
        {
            title: t(`${P}.col.supplierName`),
            dataIndex: 'supplier_name',
            hideInTable: true,
        },
        {
            title: t(`${P}.col.sourceCode`),
            dataIndex: 'source_code',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, record) => (
                <LinkedDocumentCode
                    documentType={record.source_type}
                    documentId={record.source_id}
                    code={record.source_code}
                />
            ),
        },
        {
            title: t(`${P}.col.invoiceStatus`),
            key: 'invoice_status',
            dataIndex: 'invoice_status',
            ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
            hideInSearch: true,
            render: (_, record) => renderPayableInvoiceStatusTag(record.invoice_status, t),
        },
        {
            title: t(`${P}.col.totalAmount`),
            dataIndex: 'total_amount',
            valueType: 'money',
            align: 'right',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            sorter: true,
            render: (_, record) => {
                const amount = payableDisplayTotalAmount(record);
                return (
                    <span style={amount < 0 ? { color: '#cf1322' } : undefined}>
                        {new Intl.NumberFormat('zh-CN', {
                            style: 'currency',
                            currency: 'CNY',
                        }).format(amount)}
                    </span>
                );
            },
        },
        {
            title: t(`${P}.col.paidAmount`),
            dataIndex: 'paid_amount',
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
            title: t(`${P}.col.remainingAmount`),
            dataIndex: 'remaining_amount',
            valueType: 'money',
            align: 'right',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            sorter: true,
            render: (_, record) => (
                <span style={{ color: record.remaining_amount > 0 ? 'red' : 'inherit', fontWeight: 'bold' }}>
                    {record.remaining_amount != null
                        ? formatCurrencyAmount(record.remaining_amount)
                        : '-'}
                </span>
            ),
        },
        {
            title: t(`${P}.col.invoicedAmount`),
            dataIndex: 'invoiced_amount',
            valueType: 'money',
            align: 'right',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
        },
        {
            title: t(`${P}.col.remainingInvoiceAmount`),
            dataIndex: 'remaining_invoice_amount',
            valueType: 'money',
            align: 'right',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, record) => (
                <span
                    style={{
                        color: Number(record.remaining_invoice_amount ?? 0) > 0 ? '#1677ff' : 'inherit',
                        fontWeight: Number(record.remaining_invoice_amount ?? 0) > 0 ? 'bold' : 'normal',
                    }}
                >
                    {record.remaining_invoice_amount != null
                        ? formatCurrencyAmount(record.remaining_invoice_amount)
                        : '-'}
                </span>
            ),
        },
        {
            title: t(`${P}.col.paymentTerms`),
            dataIndex: 'payment_terms',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            ellipsis: true,
            render: (_, record) => record.payment_terms || '-',
        },
        {
            title: t('app.kuaicaiwu.common.businessDate'),
            key: 'finance_business_date',
            dataIndex: 'business_date',
            valueType: 'date',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            sorter: true,
        },
        {
            title: t('app.kuaicaiwu.common.businessDate'),
            dataIndex: 'business_date_range',
            valueType: 'dateRange',
            hideInTable: true,
            order: 20,
        },
        {
            title: t('app.kuaicaiwu.common.dueDate'),
            key: 'finance_due_date',
            dataIndex: 'due_date',
            valueType: 'date',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            sorter: true,
        },
        {
            title: t('app.kuaicaiwu.common.dueDate'),
            dataIndex: 'due_date_range',
            valueType: 'dateRange',
            hideInTable: true,
            order: 21,
        },
        {
            title: t('common.status'),
            dataIndex: 'status',
            hideInTable: true,
            order: 22,
            valueEnum: buildPayableStatusEnum(t),
        },
        {
            title: t('app.kuaicaiwu.common.reviewStatus'),
            dataIndex: 'review_status',
            hideInTable: true,
            order: 23,
            valueEnum: buildReviewStatusEnum(t),
        },
        {
            title: t('app.kuaizhizao.salesManagement.pushProgress.title'),
            dataIndex: 'payment_push_progress',
            ...DOCUMENT_PROGRESS_COLUMN_DEFAULTS,
            render: (_, record) => {
                const percent = payablePaymentPushPercent(record.paid_amount, record.total_amount);
                return (
                    <DocumentPushProgressBar
                        percent={percent}
                        tooltip={t('app.kuaizhizao.salesManagement.pushProgress.percentOnly', {
                            percent: Math.round(percent),
                        })}
                    />
                );
            },
        },
        {
            title: t(`${P}.col.invoicePushProgress`),
            dataIndex: 'invoice_push_progress',
            ...DOCUMENT_PROGRESS_COLUMN_DEFAULTS,
            render: (_, record) => {
                const percent = payableInvoicePushPercent(record.invoiced_amount, record.total_amount);
                return (
                    <DocumentPushProgressBar
                        percent={percent}
                        tooltip={t(`${P}.col.invoicePushProgressTooltip`, {
                            percent: Math.round(percent),
                        })}
                    />
                );
            },
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
            render: (_, record) => record.notes || '—',
        },
        ...financeDocCreatedUpdatedColumns<Payable>(t),
        {
            title: t('app.kuaicaiwu.common.lifecycle'),
            key: 'lifecycle',
            dataIndex: 'lifecycle_stage',
            fixed: 'right',
            hideInSearch: true,
            render: (_, record) => {
                const lc = getPayableLifecycle(record as unknown as Record<string, unknown>, t);
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
            uniActionRenderOptions: { directMax: 2, minPrimaryVisible: 1 },
            render: (_, record) => {
                const acts: React.ReactNode[] = [
                    <Button
                        key="det"
                        {...rowActionKind('read')}
                        onClick={() => navigate(`/apps/kuaicaiwu/finance-management/payables/${record.id}`)}
                    />,
                    <UniWorkflowActions
                        {...rowActionKind('skip')}
                        key="wf"
                        record={record}
                        apiPrefix="/apps/kuaicaiwu/payables"
                        entityType="payable"
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
                ];
                if (
                    !isPurchaseReturnOffsetPayable(record) &&
                    record.remaining_amount > 0 &&
                    record.capabilities?.push_payment?.allowed !== false &&
                    paymentPerms.canCreate
                ) {
                    acts.push(
                        <Button
                            key="pay"
                            {...rowActionMakePayment('skip')}
                            onClick={() =>
                                navigate('/apps/kuaicaiwu/finance-management/payments', {
                                    state: { pullPayableId: record.id },
                                })
                            }
                        />,
                    );
                }
                if (
                    !isPurchaseReturnOffsetPayable(record) &&
                    record.capabilities?.push_purchase_invoice?.allowed !== false &&
                    Number(record.remaining_invoice_amount ?? record.total_amount ?? 0) > 0 &&
                    purchaseInvoicePerms.canCreate
                ) {
                    acts.push(
                        <Button
                            key="invoice"
                            {...rowActionIssueInvoice('create')}
                            onClick={() =>
                                navigate('/apps/kuaicaiwu/finance-management/purchase-invoices', {
                                    state: { pullPayableId: record.id },
                                })
                            }
                        />,
                    );
                }
                if (canCorrectPayableRow(record) && payablePerms.canUpdate) {
                    acts.push(
                        <Button
                            key="ed"
                            {...rowActionKind('update')}
                            onClick={() => openEdit(record)}
                        />,
                    );
                }
                if (canCorrectPayableRow(record) && payablePerms.canDelete) {
                    acts.push(
                        <ActionConfirmPopconfirm
                            key="del-pc"
                            title={t(`${P}.deleteTitle`)}
                            description={t(`${P}.deleteContent`, { code: record.payable_code })}
                            okType="danger"
                            onConfirm={() => executeDeleteOne(record)}
                        >
                            <Button
                                key="del"
                                {...rowActionKind('delete')}
                                onClick={(e) => e.stopPropagation()}
                            />
                        </ActionConfirmPopconfirm>,
                    );
                }
                return acts;
            },
        },
    ], [t, navigate, supplierOptions, paymentPerms, purchaseInvoicePerms, payablePerms]);


    return (
        <ListPageTemplate>
            {(urlAgingFilters.aging_bucket || urlAgingFilters.overdue_only) ? (
                <Alert
                    type="info"
                    showIcon
                    closable={{ onClose: () => setSearchParams({}) }}
                    style={{ marginBottom: 16 }}
                    title={t('app.kuaicaiwu.financeUi.aging.listFilterActive', {
                        filter: agingFilterDescription,
                    })}
                />
            ) : null}
            <UniTable<Payable>
                headerTitle={t(`${P}.pageTitle`)}
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.payable)}
                actionRef={actionRef}
                columns={alignProColumns(columns, SALES_DOC_LIST_FIELD_RANK)}
                columnPersistenceId="apps.kuaicaiwu.pages.finance-management.payables.list-v9"
                request={async (params, sort, _filter, searchFormValues) => {
                    const { current, pageSize } = params;
                    const listParams = resolvePayableListParams(searchFormValues, sort, urlAgingFilters);
                    lastListParamsRef.current = listParams;
                    const apiParams: PayableListParams = {
                        skip: ((current || 1) - 1) * (pageSize || 20),
                        limit: pageSize || 20,
                        ...listParams,
                    };

                    try {
                        const res = await payableService.listPayables(apiParams);
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
                pinnedTabsField={FINANCE_DOC_PINNED_STATUS_FIELD}
                rowKey="id"
                showCreateButton={false}
                createButtonText={t(`${P}.createTitle`)}
                onCreate={() => setCreateModalVisible(true)}
                toolBarRender={() => [
                    <UniPullCreateToolbar
                        key="create-payable-with-pull"
                        createIcon={<PlusOutlined />}
                        createLabel={t(`${P}.createTitle`)}
                        onCreate={() => {
                            setCreateSeed(undefined);
                            setCreateModalVisible(true);
                        }}
                        menuItems={[
                            ...buildKuaicaiwuPullCreateMenuItems([
                                {
                                    key: 'pull-from-purchase-order',
                                    actionKey: 'payable.pull_from_purchase_order',
                                    onClick: () => {
                                        pullFromPurchaseOrderQuery.openModal();
                                    },
                                },
                                {
                                    key: 'pull-from-purchase-receipt',
                                    actionKey: 'payable.pull_from_purchase_receipt',
                                    onClick: () => {
                                        pullFromPurchaseReceiptQuery.openModal();
                                    },
                                },
                            ]),
                            { type: 'divider', key: 'copy-selected-divider' },
                            {
                                key: 'copy-selected',
                                label: t(`${P}.copySelectedCreate`),
                                disabled:
                                    selectedRecordsForBatch.length !== 1
                                    || isPurchaseReturnOffsetPayable(selectedRecordsForBatch[0]),
                                onClick: () => {
                                    const row = selectedRecordsForBatch[0];
                                    if (!row || isPurchaseReturnOffsetPayable(row)) return;
                                    setCreateSeed({
                                        supplier_id: row.supplier_id,
                                        total_amount: row.total_amount,
                                        business_date: dayjs(),
                                        due_date: row.due_date ? dayjs(row.due_date) : dayjs().add(30, 'day'),
                                        notes: row.notes,
                                    });
                                    setCreateModalVisible(true);
                                },
                            },
                        ]}
                    />,
                ]}
                enableRowSelection
                selectedRowKeys={selectedRowKeys}
                onRowSelectionChange={setSelectedRowKeys}
                onTableDataChange={setTableRows}
                showDeleteButton
                deleteButtonText={t('common.batchDelete')}
                onDelete={handleBatchDelete}
                deleteConfirmTitle={t('app.kuaicaiwu.common.confirmBatchDelete')}
                deleteConfirmDescription={(count) => t(`${P}.deleteConfirm`, { count })}
                toolBarActionsAfterDelete={[
                    <UniAuditBatchMenuButton
                        key="payable-batch-audit"
                        selectedRowKeys={selectedRowKeys}
                        selectedRecords={selectedRecordsForBatch}
                        auditEnabled={payableAuditEnabled}
                        permGates={payablePerms}
                        handlers={payableAuditBatchHandlers}
                        onSuccess={handlePayableAuditBatchSuccess}
                        toolBarButtonSize="medium"
                    />,
                    <Button
                        key="merge-payment"
                        size="medium"
                        disabled={mergePaymentDisabled}
                        onClick={() => openMergeModal('merge_payment')}
                    >
                        {t('app.kuaicaiwu.mergeFinance.mergePayment')}
                    </Button>,
                    <Button
                        key="merge-purchase-invoice"
                        size="medium"
                        disabled={mergeInvoiceDisabled}
                        onClick={() => openMergeModal('merge_purchase_invoice')}
                    >
                        {t('app.kuaicaiwu.mergeFinance.mergePurchaseInvoice')}
                    </Button>,
                ]}
                showAdvancedSearch={true}
                showImportButton
                onImport={async (data) => {
                    if (!data || data.length < 2) {
                        messageApi.warning(t('app.kuaicaiwu.common.importEmpty'));
                        return;
                    }
                    const headers = (data[0] || []).map((h: any) => String(h || '').trim());
                    const headerIndexMap = resolveFactoryImportHeaderIndexMap(
                        headers,
                        payableImportTemplate.importHeaderMap,
                    );
                    if (headerIndexMap.supplier === undefined || headerIndexMap.amount === undefined) {
                        messageApi.error(t(`${P}.importHeaderError`));
                        return;
                    }
                    const items: PayableCreateData[] = [];
                    const importRows = data.slice(2).filter((row: any[]) =>
                        row?.some((c: any) => c != null && String(c).trim() !== ''),
                    );
                    for (const row of importRows) {
                        const suppLabel = String(row[headerIndexMap.supplier] ?? '').trim();
                        const suppOpt = supplierOptions.find(o => (o.label || '').trim() === suppLabel) ?? supplierOptions.find(o => (o.label || '').includes(suppLabel));
                        const suppId = suppOpt?.value;
                        const amount = Number(row[headerIndexMap.amount]) || 0;
                        if (!suppId || amount <= 0) continue;
                        const today = formatDateTime(dayjs(), 'YYYY-MM-DD');
                        const dueDate =
                            headerIndexMap.dueDate !== undefined && row[headerIndexMap.dueDate]
                                ? formatDateTime(row[headerIndexMap.dueDate], 'YYYY-MM-DD')
                                : today;
                        const bizDate =
                            headerIndexMap.businessDate !== undefined && row[headerIndexMap.businessDate]
                                ? formatDateTime(row[headerIndexMap.businessDate], 'YYYY-MM-DD')
                                : today;
                        items.push({
                            source_type: '手工',
                            source_id: 0,
                            source_code: '手工',
                            supplier_id: suppId,
                            supplier_name: suppOpt?.label || suppLabel,
                            total_amount: amount,
                            paid_amount: 0,
                            remaining_amount: amount,
                            due_date: dueDate,
                            business_date: bizDate,
                            notes:
                              headerIndexMap.notes !== undefined && row[headerIndexMap.notes]
                                ? String(row[headerIndexMap.notes]).trim() || undefined
                                : undefined,
                            status: '未付款',
                            review_status: '草稿',
                        });
                    }
                    if (items.length === 0) {
                        messageApi.warning(t('app.kuaicaiwu.common.importNoValidRows'));
                        return;
                    }
                    const result = await importInChunksViaPerItemCreate({
                        items,
                        createOne: async (item, _index) => payableService.createPayable(item),
                        title: t(`${P}.importTitle`),
                        chunkSize: 100,
                        concurrency: 4,
                    });
                    if (result.successCount > 0) {
                        messageApi.success(t(`${P}.importSuccess`, { count: result.successCount }));
    actionRef.current?.reload();
                    }
                    if (result.failureCount > 0) {
                        messageApi.warning(t('app.kuaicaiwu.common.importPartialFail', { count: result.failureCount }));
                    }
                }}
                importHeaders={payableImportTemplate.importHeaders}
                importExampleRow={payableImportTemplate.importExampleRow}
                importColumnOptions={payableImportTemplate.importColumnOptions}
                importFieldMap={payableImportTemplate.importHeaderMap}
                showExportButton
                onExport={async (type, keys, pageData) => {
                    try {
                        let items: Payable[] =
                            type === 'currentPage' && pageData?.length
                                ? pageData
                                : await fetchAllListItems((p) =>
                                      payableService.listPayables({
                                          ...p,
                                          ...lastListParamsRef.current,
                                      }),
                                  );
                        if (type === 'selected' && keys?.length) {
                            items = items.filter((d: Payable) => d.id != null && keys.includes(d.id));
                        }
                        if (items.length === 0) {
                            messageApi.warning(t('common.exportNoData'));
                            return;
                        }
                        await downloadRecordsAsXlsx(
                          items as Array<Record<string, unknown>>,
                          `payables-${todaySiteDateString()}.xlsx`,
                        );
                        messageApi.success(t('common.exportCountSuccess', { count: items.length }));
                    } catch (error: any) {
                        messageApi.error(error?.message || t('common.exportFailed'));
                    }
                }}
            />

            <UniPullQueryModal<PayablePullCandidate>
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

            <UniPullQueryModal<PayablePullCandidate>
                open={pullFromPurchaseReceiptQuery.open}
                title={pullFromPurchaseReceiptAction.label}
                onCancel={pullFromPurchaseReceiptQuery.closeModal}
                onOk={() => {
                    void pullFromPurchaseReceiptQuery.handleConfirm();
                }}
                rowKey="id"
                columns={pullTableColumns}
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

            <Modal
                title={t(`${P}.pullFormTitle`)}
                open={pullPreviewOpen}
                destroyOnHidden
                width={
                    pullPreviewKind === 'purchase_receipt' && (pullPreviewData?.detail_lines?.length ?? 0) > 0
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
                        <p style={{ marginBottom: 12, fontWeight: 500 }}>{pullPreviewData.summary}</p>
                        {pullPreviewData.has_blocking_issues && pullPreviewData.blocking_reason ? (
                            <Alert
                                type="warning"
                                showIcon
                                style={{ marginBottom: 12 }}
                                title={payableCapabilityReasonMessage(pullPreviewData.blocking_reason, t)}
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
                                        title: t(`${P}.pull.col.payableAmount`),
                                        dataIndex: 'pushed_quantity',
                                        width: 120,
                                        align: 'right',
                                        render: (v: number) => formatPullMoney(v),
                                    },
                                    {
                                        title: t(`${P}.pull.col.payableableAmount`),
                                        dataIndex: 'max_push_quantity',
                                        width: 120,
                                        align: 'right',
                                        render: (v: number) => formatPullMoney(v),
                                    },
                                ]}
                            />
                        ) : (
                            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.purchaseReturn.pull.previewNoLines')} />
                        )}
                        {pullPreviewKind === 'purchase_receipt' ? (
                            <>
                                <Typography.Paragraph strong style={{ marginTop: 16, marginBottom: 8 }}>
                                    {t(`${P}.pull.detailTitle`)}
                                </Typography.Paragraph>
                                {(pullPreviewData.detail_lines?.length ?? 0) > 0 ? (
                                    <Table<PullReceiptFinanceDetailLine>
                                        size="small"
                                        dataSource={pullPreviewData.detail_lines as PullReceiptFinanceDetailLine[]}
                                        rowKey={(row) => String(row.purchase_receipt_item_id)}
                                        pagination={false}
                                        scroll={{ x: 980, y: 240 }}
                                        rowSelection={{
                                            selectedRowKeys: pullReceiptSelectedIds,
                                            onChange: (keys) => {
                                                const ids = keys.map((k) => Number(k)).filter((id) => id > 0);
                                                setPullReceiptSelectedIds(ids);
                                                const sum = sumPullReceiptLineAmounts(ids, pullReceiptLineAmounts);
                                                if (sum > 0) {
                                                    pullForm.setFieldsValue({ total_amount: sum });
                                                }
                                            },
                                            getCheckboxProps: (row) => ({
                                                disabled: Number(row.max_push_amount ?? 0) <= 0,
                                            }),
                                        }}
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
                                                width: 140,
                                                ellipsis: true,
                                            },
                                            {
                                                title: t(`${P}.pull.col.lineAmount`),
                                                dataIndex: 'amount',
                                                width: 100,
                                                align: 'right',
                                                render: (v: number) => formatPullMoney(v),
                                            },
                                            {
                                                title: t(`${P}.pull.col.occupiedAmount`),
                                                dataIndex: 'occupied_amount',
                                                width: 100,
                                                align: 'right',
                                                render: (v: number) => formatPullMoney(v),
                                            },
                                            {
                                                title: t(`${P}.pull.col.payableableAmount`),
                                                dataIndex: 'max_push_amount',
                                                width: 100,
                                                align: 'right',
                                                render: (v: number) => formatPullMoney(v),
                                            },
                                            {
                                                title: t(`${P}.pull.col.thisPayableAmount`),
                                                width: 130,
                                                align: 'right',
                                                render: (_, row) => {
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
                                                                    const sum = sumPullReceiptLineAmounts(
                                                                        pullReceiptSelectedIds,
                                                                        merged,
                                                                    );
                                                                    pullForm.setFieldsValue({ total_amount: sum });
                                                                    return merged;
                                                                });
                                                            }}
                                                            style={{ width: '100%' }}
                                                        />
                                                    );
                                                },
                                            },
                                        ]}
                                    />
                                ) : (
                                    <Empty
                                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                                        description={t(`${P}.pull.detailEmpty`)}
                                    />
                                )}
                            </>
                        ) : null}
                        {pullPreviewData.tip ? (
                            <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 16 }}>
                                {pullPreviewData.tip}
                            </Typography.Paragraph>
                        ) : null}
                        {!pullPreviewData.has_blocking_issues && pullPreviewMaxPush > 0 ? (
                            <ProForm
                                key={`pull-payable-${pullPreviewKind}-${pullPreviewSourceIds.join('-')}`}
                                form={pullForm}
                                initialValues={pullFormInitialValues}
                                submitter={false}
                                onFinish={handlePullCreateSubmit}
                                layout="vertical"
                                {...financeFormGridProps}
                            >
                                <ProFormText name="source_code" label={t(`${P}.pullCol.sourceCode`)} readonly colProps={financeColHalf} />
                                <ProFormText name="supplier_name" label={t('app.kuaicaiwu.common.supplier')} readonly colProps={financeColHalf} />
                                <ProFormMoney
                                    name="total_amount"
                                    label={t(`${P}.col.amount`)}
                                    min={0.01}
                                    max={pullPreviewMaxPush}
                                    rules={[{ required: true, message: t(`${P}.amountRequired`) }]}
                                    colProps={financeColFull}
                                />
                                <ProFormDatePicker
                                    name="business_date"
                                    label={t('app.kuaicaiwu.common.businessDate')}
                                    fieldProps={{ style: { width: '100%' } }}
                                    colProps={financeColHalf}
                                />
                                <ProFormDatePicker
                                    name="due_date"
                                    label={t('app.kuaicaiwu.common.dueDate')}
                                    rules={[{ required: true }]}
                                    colProps={financeColHalf}
                                    fieldProps={buildFutureDateShortcutFieldProps({
                                        getForm: () => pullForm,
                                        fieldName: 'due_date',
                                        baseFieldName: 'business_date',
                                        t,
                                    })}
                                />
                                <ProFormTextArea name="notes" label={t('common.remark')} colProps={financeColFull} />
                                <DocumentAttachmentsField category="payable_attachments" />
                            </ProForm>
                        ) : null}
                    </div>
                ) : null}
            </Modal>

            <ModalForm
                key={createSeed ? 'create-payable-copy' : 'create-payable'}
                title={t(`${P}.createTitle`)}
                open={createModalVisible}
                onOpenChange={(open) => {
                    setCreateModalVisible(open);
                    if (!open) setCreateSeed(undefined);
                }}
                initialValues={createSeed}
                onFinish={handleCreate}
                formRef={createFormRef}
                width={MODAL_CONFIG.STANDARD_WIDTH}
                {...financeFormGridProps}
            >
                <ProFormSelect
                    name="supplier_id"
                    label={t('app.kuaicaiwu.common.supplier')}
                    options={supplierOptions}
                    rules={[{ required: true, message: t('app.kuaicaiwu.common.selectSupplier') }]}
                    placeholder={t('app.kuaicaiwu.common.selectSupplier')}
                    colProps={financeColHalf}
                />
                <ProFormMoney
                    name="total_amount"
                    label={t(`${P}.col.amount`)}
                    min={0.01}
                    rules={[{ required: true }]}
                    colProps={financeColHalf}
                />
                <ProFormDatePicker
                    name="business_date"
                    label={t('app.kuaicaiwu.common.businessDate')}
                    fieldProps={{ style: { width: '100%' } }}
                    colProps={financeColHalf}
                />
                <ProFormDatePicker
                    name="due_date"
                    label={t('app.kuaicaiwu.common.dueDate')}
                    rules={[{ required: true }]}
                    colProps={financeColHalf}
                    fieldProps={buildFutureDateShortcutFieldProps({
                        getForm: () => createFormRef.current,
                        fieldName: 'due_date',
                        baseFieldName: 'business_date',
                        t,
                    })}
                />
                <ProFormTextArea name="notes" label={t('common.remark')} colProps={financeColFull} />
                <DocumentAttachmentsField category="payable_attachments" />
            </ModalForm>

            <ModalForm
                key={editingRecord ? `edit-payable-${editingRecord.id}` : 'edit-payable'}
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
                              business_date: editingRecord.business_date
                                  ? dayjs(editingRecord.business_date)
                                  : dayjs(),
                              due_date: editingRecord.due_date ? dayjs(editingRecord.due_date) : undefined,
                              notes: editingRecord.notes,
                          }
                        : undefined
                }
                onFinish={handleUpdate}
                width={MODAL_CONFIG.STANDARD_WIDTH}
                {...financeFormGridProps}
            >
                <ProFormSelect
                    name="supplier_id"
                    label={t('app.kuaicaiwu.common.supplier')}
                    options={supplierOptions}
                    rules={[{ required: true, message: t('app.kuaicaiwu.common.selectSupplier') }]}
                    placeholder={t('app.kuaicaiwu.common.selectSupplier')}
                    colProps={financeColHalf}
                />
                <ProFormMoney
                    name="total_amount"
                    label={t(`${P}.col.amount`)}
                    min={0.01}
                    rules={[{ required: true }]}
                    colProps={financeColHalf}
                />
                <ProFormDatePicker
                    name="business_date"
                    label={t('app.kuaicaiwu.common.businessDate')}
                    fieldProps={{ style: { width: '100%' } }}
                    colProps={financeColHalf}
                />
                <ProFormDatePicker
                    name="due_date"
                    label={t('app.kuaicaiwu.common.dueDate')}
                    rules={[{ required: true }]}
                    colProps={financeColHalf}
                />
                <ProFormTextArea name="notes" label={t('common.remark')} colProps={financeColFull} />
                <DocumentAttachmentsField category="payable_attachments" />
            </ModalForm>

            <MergeFinanceDocsModal
                open={mergeModalOpen}
                mode={mergeMode}
                sources={mergeSources}
                onOpenChange={setMergeModalOpen}
                onSuccess={() => {
                    setSelectedRowKeys([]);
    actionRef.current?.reload();
                }}
            />
        </ListPageTemplate>
    );
};

export default PayableList;
