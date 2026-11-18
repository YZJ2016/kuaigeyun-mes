/**
 * 付款申请单
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import {
  ModalForm,
  ProForm,
  ProFormDatePicker,
  ProFormDependency,
  ProFormDigit,
  ProFormItem,
  ProFormSelect,
  ProFormSwitch,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import {
  App,
  Button,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Typography,
} from 'antd';
import { ArrowLeftOutlined, PlusOutlined, PrinterOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import type { TFunction } from 'i18next';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import { buildUniPushMenuItems, buildUniPushToolbarDisabledReason, UniPushToolbarButton } from '../../../../../components/uni-push';
import { useLinkedDocumentDetail } from '../../../../../components/linked-document-detail';
import {
  type DocumentLineMaterialPreviewItem,
  renderDocumentLineMaterialsPreview,
} from '../../../../../components/document-line-materials-preview';
import { resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import { usePaymentApplicationPullMenus } from './usePaymentApplicationPullMenus';
import {
  itemsCompatibleWithApplicationKind,
  usePaymentApplicationFormLinePull,
} from './usePaymentApplicationFormLinePull';
import { PaymentApplicationSupplierPayeeSection } from './PaymentApplicationSupplierPayeeSection';
import type { FormListFieldData } from 'antd/es/form/FormList';
import dayjs from '../../../../../config/dayjs';
import { useTranslation } from 'react-i18next';
import { rowActionKind } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { UniTable } from '../../../../../components/uni-table';
import {
  ListPageTemplate,
  DetailDrawerTemplate,
  DetailDrawerLinesScroll,
  DRAWER_CONFIG,
  MODAL_CONFIG,
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageHeaderActions,
  DocumentFormPageLayout,
} from '../../../../../components/layout-templates';
import { useLeaveFormTab } from '../../../../../components/uni-tabs/navigateClosingTab';
import { useSubmitShortcut } from '../../../../../hooks/useSubmitShortcut';
import {
  UniBatchMenuButton,
  UniCapabilityBatchButton,
  defaultAuditBatchAllowed,
  pickCapability,
  runCapabilityBatchLoop,
  useAuditBatchRunner,
  withDocumentSubmitCombinedItem,
  type AuditBatchAction,
  type UniBatchMenuItem,
} from '../../../../../components/uni-batch';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { UniTableStackedPrimaryCell } from '../../../../../components/uni-table/stackedPrimaryColumn';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import {
  LedgerAccountFormFields,
} from '../../../../kuaicaiwu/components/LedgerAccountFormFields';
import {
  mapAttachmentsToUploadList,
  normalizeDocumentAttachments,
  openDocumentAttachment,
} from '../../../utils/documentAttachments';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';
import { MarkerTag } from '../../../../../constants/statusBadges';
import {
  UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
  UNI_TABLE_PAYMENT_SETTLEMENT_COLUMN_DEFAULTS,
} from '../../../../../utils/uniTableLayoutColumns';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { createListAuditPhaseColumn } from '../../sales-management/shared/listAuditPhaseColumn';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import {
  financeDocCodePartnerSearchColumns,
  resolvePaymentApplicationListParams,
} from '../../../../kuaicaiwu/utils/financeListCore';
import {
  assertBankAccountForPaymentMethod,
  BANK_TRANSFER_PAYMENT_METHOD,
  formatPaymentMethod,
  getPaymentMethodOptions,
  EMPLOYEE_ADVANCE_PAYMENT_METHOD,
  hidesSupplierPayeeAccount,
  isEmployeeAdvancePaymentMethod,
} from '../../../../kuaicaiwu/utils/financeSharedOptions';
import {
  PaymentAdvancePayeeField,
  resolveAdvancePayeeName,
} from '../../../../kuaicaiwu/pages/finance-management/shared/PaymentAdvancePayeeField';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import { loadUserFormReferenceOptions } from '../../../../../utils/documentFormReferenceLoad';
import { useQuery } from '@tanstack/react-query';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { getStatusLabel, isPendingReviewStatus } from '../../../constants/documentStatus';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useKuaizhizaoPrintModal } from '../../../hooks/useKuaizhizaoPrintModal';
import {
  formatCurrencyAmount,
  formatDateBySiteSetting,
  todaySiteDateString,
} from '../../../../../utils/format';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { coerceFormDate, toApiDateString } from '../../../../../utils/formDate';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import { fetchAllListItems } from '../../../../../utils/fetchAllListPages';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import {
  KUAIZHIZAO_DOC_HOST,
  loadSupplierFormReferenceList,
} from '../../../../../utils/documentFormReferenceLoad';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import {
  canOpenLinkedDocumentDetail,
  normalizeLinkedDocumentType,
} from '../../../utils/linkedDocumentDetail';
import { bankAccountService, type BankAccount } from '../../../../kuaicaiwu/services/finance/bank-account';
import {
  listPaymentApplications,
  getPaymentApplication,
  createPaymentApplication,
  updatePaymentApplication,
  deletePaymentApplication,
  submitPaymentApplication,
  submitPaymentApplicationForReview,
  withdrawPaymentApplication,
  revokePaymentApplication,
  approvePaymentApplication,
  pushPaymentApplicationToPayment,
  listPayablesForPaymentApplication,
  previewPullPaymentApplicationFromPurchaseOrder,
  type PaymentApplication,
  type PaymentApplicationLine,
  type PaymentApplicationPurchaseOrderSource,
} from '../../../services/payment-application';
import { getPurchaseOrder, type PurchaseOrderItem } from '../../../services/purchase';
import {
  PurchaseDepartmentFormField,
  resolvePurchaseDepartmentPayload,
  usePurchaseDepartmentOptions,
} from '../shared/PurchaseDepartmentFormField';
import { resolvePaymentApplicationSettlementDisplay } from './paymentApplicationListStatus';

const RESOURCE = 'kuaizhizao:payment-application';

/** 搜索行钉住 Tab：审批阶段 + 付款状态 */
const PAYMENT_APPLICATION_PINNED_TABS_FIELDS = ['approvalPhase', 'paymentSettlement'] as const;
const PAYMENT_APPLICATION_LIST_PATH = '/apps/kuaizhizao/purchase-management/payment-applications';
const PAYMENT_APPLICATION_CREATE_PATH = `${PAYMENT_APPLICATION_LIST_PATH}/new`;
const paymentApplicationEditPath = (id: number) => `${PAYMENT_APPLICATION_LIST_PATH}/${id}/edit`;

/** 详情明细列宽：来源类型最长「其他费用支出」，来源单号按采购单号整段展示 */
const PAYMENT_APPLICATION_DETAIL_LINE_WIDTH = {
  sourceType: 128,
  sourceCode: 200,
  lineMaterials: 280,
  quantity: 120,
  payableCode: 188,
  requestAmount: 128,
  paidAmount: 128,
} as const;

function isPurchaseOrderSourceType(sourceType: unknown): boolean {
  const raw = String(sourceType ?? '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_');
  return raw === 'purchase_order' || raw === 'purchaseorder';
}

function mapPurchaseOrderItemsToPreview(
  items: PurchaseOrderItem[] | PaymentApplicationPurchaseOrderSource['items'] | undefined,
): DocumentLineMaterialPreviewItem[] {
  if (!items?.length) return [];
  const out: DocumentLineMaterialPreviewItem[] = [];
  for (const it of items) {
    const row = it as Record<string, unknown>;
    const materialName = String(row.materialName ?? row.material_name ?? '').trim();
    const materialCode = String(row.materialCode ?? row.material_code ?? '').trim();
    const materialSpec = String(row.materialSpec ?? row.material_spec ?? '').trim();
    if (!materialName && !materialCode) continue;
    out.push({
      material_name: materialName || materialCode,
      material_code: materialCode || undefined,
      material_spec: materialSpec || undefined,
    });
  }
  return out;
}

function resolvePaymentApplicationLineMaterialPreview(
  row: PaymentApplicationLine,
  purchaseOrderSources: PaymentApplicationPurchaseOrderSource[] | undefined,
  poPreviewByOrderId: Record<number, DocumentLineMaterialPreviewItem[]>,
): DocumentLineMaterialPreviewItem[] {
  const name = String(row.materialName ?? '').trim();
  if (name) {
    return [
      {
        material_name: name,
        material_spec: row.materialSpec ?? undefined,
      },
    ];
  }
  if (!isPurchaseOrderSourceType(row.sourceType)) {
    return [];
  }
  const sid = row.sourceId != null ? Number(row.sourceId) : 0;
  const code = String(row.sourceCode ?? '').trim();
  const po =
    (sid > 0 ? purchaseOrderSources?.find((p) => Number(p.id) === sid) : undefined) ??
    (code ? purchaseOrderSources?.find((p) => String(p.orderCode).trim() === code) : undefined);
  if (po?.items?.length) {
    return mapPurchaseOrderItemsToPreview(po.items);
  }
  if (sid > 0 && poPreviewByOrderId[sid]?.length) {
    return poPreviewByOrderId[sid];
  }
  return [];
}

const PAYMENT_APPLICATION_DETAIL_LINES_MIN_WIDTH = Object.values(
  PAYMENT_APPLICATION_DETAIL_LINE_WIDTH,
).reduce((sum, width) => sum + width, 0);

const PAYMENT_APP_SOURCE_TYPE_KEYS = [
  'payable',
  'purchase_order',
  'purchase_receipt',
  'other_expense',
  'document_reconciliation',
] as const;

function paymentApplicationSourceTypeLabel(t: TFunction, sourceType: string | undefined): string {
  const st = String(sourceType || '').trim();
  if (!st) return '—';
  if ((PAYMENT_APP_SOURCE_TYPE_KEYS as readonly string[]).includes(st)) {
    return t(`app.kuaizhizao.paymentApplication.sourceType.${st}`);
  }
  return st;
}

/** 采购订单预付等明细尚无应付单，后端不要求 payable_id */
function paymentApplicationLineNeedsPayable(
  lineKind: string | undefined,
  sourceType: string | undefined,
): boolean {
  if (String(lineKind || '').trim() === 'prepayment') return false;
  if (String(sourceType || '').trim() === 'purchase_order') return false;
  return true;
}

/** 表单结算类型仅暴露普通付款/预付款；其余头类型按普通付款编辑 */
function formApplicationKind(kind: unknown): 'goods' | 'prepayment' {
  return String(kind || '').trim() === 'prepayment' ? 'prepayment' : 'goods';
}

function lineKindFromApplicationKind(kind: unknown): 'goods' | 'prepayment' {
  return formApplicationKind(kind);
}

function sumPaymentApplicationFormLineAmounts(items: unknown): number {
  const rows = normalizeFormListItems<Record<string, unknown>>(items);
  return rows.reduce((acc, row) => {
    const amount = Number(row.requestAmount);
    return acc + (Number.isFinite(amount) ? amount : 0);
  }, 0);
}

function sumPaymentApplicationFormLineOrderDisplayAmounts(
  items: unknown,
  applicationKind: unknown,
): number {
  const kind = formApplicationKind(applicationKind);
  const rows = normalizeFormListItems<Record<string, unknown>>(items);
  return rows.reduce((acc, row) => {
    if (isPrepaymentPurchaseOrderFormLine(row, kind)) {
      const orderAmount = Number(row.sourceOrderAmount ?? row.maxRequestAmount ?? row.requestAmount ?? 0);
      return acc + (Number.isFinite(orderAmount) ? orderAmount : 0);
    }
    const amount = Number(row.requestAmount);
    return acc + (Number.isFinite(amount) ? amount : 0);
  }, 0);
}

function isPrepaymentPurchaseOrderFormLine(
  row: Record<string, unknown>,
  applicationKind: unknown,
): boolean {
  return (
    formApplicationKind(applicationKind) === 'prepayment'
    && String(row.sourceType || '').trim() === 'purchase_order'
  );
}

async function buildPaymentApplicationEditFormItems(
  applicationKind: string,
  lines: PaymentApplicationLine[],
): Promise<Record<string, unknown>[]> {
  const kind = formApplicationKind(applicationKind);
  const baseRows = (lines ?? []).map((line) => ({
    lineKind: line.lineKind ?? 'goods',
    sourceType: line.sourceType || 'payable',
    sourceId: line.sourceId,
    sourceCode: line.sourceCode,
    payableId: line.payableId ?? (line.sourceType === 'payable' ? line.sourceId : undefined),
    payableCode: line.payableCode,
    maxRequestAmount: line.maxRequestAmount,
    requestAmount: line.requestAmount,
    materialName: line.materialName,
    materialSpec: line.materialSpec,
    quantity: line.quantity,
    materialUnit: line.materialUnit,
    sourceLineId: line.sourceLineId,
  }));
  if (kind !== 'prepayment') {
    return baseRows;
  }
  return Promise.all(
    baseRows.map(async (row) => {
      if (String(row.sourceType || '').trim() !== 'purchase_order' || !row.sourceId) {
        return row;
      }
      try {
        const preview = await previewPullPaymentApplicationFromPurchaseOrder(Number(row.sourceId));
        const sourceOrderAmount = Number(preview.source_order_amount ?? preview.sourceOrderAmount ?? 0);
        const maxRemaining = Number(preview.max_push_quantity ?? 0);
        return {
          ...row,
          sourceOrderAmount: sourceOrderAmount > 0 ? sourceOrderAmount : undefined,
          maxRequestAmount:
            maxRemaining > 0
              ? maxRemaining
              : row.maxRequestAmount,
        };
      } catch {
        return row;
      }
    }),
  );
}

function applyHeaderAmountToPrepaymentLines(
  headerAmount: number,
  rows: Record<string, unknown>[],
): Record<string, unknown>[] {
  if (!rows.length) {
    return rows;
  }
  if (rows.length === 1) {
    return [{ ...rows[0], requestAmount: headerAmount }];
  }
  const weights = rows.map((row) => {
    const w = Number(row.sourceOrderAmount ?? row.maxRequestAmount ?? 0);
    return w > 0 ? w : 1;
  });
  const weightSum = weights.reduce((acc, w) => acc + w, 0);
  let allocated = 0;
  return rows.map((row, index) => {
    const cap = Number(row.maxRequestAmount ?? 0);
    let part: number;
    if (index === rows.length - 1) {
      part = headerAmount - allocated;
    } else {
      part = Number(((headerAmount * weights[index]) / weightSum).toFixed(2));
      allocated += part;
    }
    if (cap > 0 && part > cap) {
      part = cap;
    }
    return { ...row, requestAmount: part };
  });
}

/** 明细表 6 列业务字段 + 订单/申请金额列 + 操作列 */
const PAYMENT_APPLICATION_LINE_SUMMARY_LABEL_COL_SPAN = 6;
const PAYMENT_APPLICATION_LINE_AMOUNT_COL_INDEX = 6;
const PAYMENT_APPLICATION_LINE_OP_COL_INDEX = 7;

function PaymentApplicationLinesSummaryRow() {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const items = Form.useWatch('items', form);
  const applicationKind = Form.useWatch('applicationKind', form);
  const rows = normalizeFormListItems<Record<string, unknown>>(items);
  if (!rows.length) {
    return null;
  }
  const total = sumPaymentApplicationFormLineOrderDisplayAmounts(items, applicationKind);
  return (
    <Table.Summary fixed>
      <Table.Summary.Row>
        <Table.Summary.Cell
          index={0}
          colSpan={PAYMENT_APPLICATION_LINE_SUMMARY_LABEL_COL_SPAN}
          align="left"
        >
          <span style={{ fontWeight: 600 }}>
            {t('app.kuaizhizao.paymentApplication.linesGrandTotal')}
          </span>
        </Table.Summary.Cell>
        <Table.Summary.Cell
          index={PAYMENT_APPLICATION_LINE_AMOUNT_COL_INDEX}
          align="right"
          className="uni-detail-fixed-amount-summary"
        >
          <span style={{ fontWeight: 600, whiteSpace: 'nowrap' }}>
            {formatCurrencyAmount(total)}
          </span>
        </Table.Summary.Cell>
        <Table.Summary.Cell index={PAYMENT_APPLICATION_LINE_OP_COL_INDEX} className="uni-detail-fixed-op-summary" />
      </Table.Summary.Row>
    </Table.Summary>
  );
}

function resolvePaymentApplicationLinkedDocType(sourceType: string): string {
  const st = normalizeLinkedDocumentType(sourceType);
  if (st === 'purchase_order' || st === 'purchase_receipt') return st;
  return st;
}

const PaymentApplicationsPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const isCreatePage = location.pathname.endsWith('/payment-applications/new');
  const editRouteMatch = location.pathname.match(/\/payment-applications\/(\d+)\/edit$/);
  const editRouteId = editRouteMatch ? Number(editRouteMatch[1]) : null;
  const isEditPage = editRouteId != null && Number.isFinite(editRouteId) && editRouteId > 0;
  const isFormPage = isCreatePage || isEditPage;
  const leavePaymentApplicationFormPage = useLeaveFormTab(PAYMENT_APPLICATION_LIST_PATH);
  const formPageInitKeyRef = useRef<string | null>(null);
  const [formPageLoading, setFormPageLoading] = useState(false);
  const { message: messageApi } = App.useApp();
  const linkedDetail = useLinkedDocumentDetail();
  const [pullPayableOpen, setPullPayableOpen] = useState(false);
  const [pullPayableSupplierId, setPullPayableSupplierId] = useState<number | null>(null);
  const [pullPayableRows, setPullPayableRows] = useState<
    Array<{ payableId: number; payableCode: string; maxRequestAmount: number }>
  >([]);
  const [pullPayableSelected, setPullPayableSelected] = useState<number[]>([]);
  const [pullPayableLoading, setPullPayableLoading] = useState(false);
  const [pullPayableSubmitting, setPullPayableSubmitting] = useState(false);
  const actionRef = useRef<ActionType>();
  const tableRowsRef = useRef<PaymentApplication[]>([]);
  const { menuItems: pullCreateMenuItems, renderPullModals } = usePaymentApplicationPullMenus({
    onCreated: () => actionRef.current?.reload(),
    onOpenPayablePull: () => setPullPayableOpen(true),
  });
  const perms = useResourcePermissions(RESOURCE);
  const {
    options: departmentOptions,
    loading: departmentOptionsLoading,
    resolveName: resolveDepartmentName,
  } = usePurchaseDepartmentOptions();
  const paymentApplicationApprovalPhaseEnum = useMemo(
    () =>
      ({
        draft: { text: t('app.kuaizhizao.paymentApplication.approvalPhase.draft') },
        submitted: { text: t('app.kuaizhizao.paymentApplication.approvalPhase.submitted') },
        pending_review: {
          text: t('app.kuaizhizao.paymentApplication.approvalPhase.pendingReview'),
        },
        approved: { text: t('app.kuaizhizao.paymentApplication.approvalPhase.approved') },
        rejected: { text: t('app.kuaizhizao.paymentApplication.approvalPhase.rejected') },
      }) as const,
    [t],
  );
  const paymentApplicationSettlementEnum = useMemo(
    () =>
      ({
        unpaid: { text: t('app.kuaizhizao.paymentApplication.settlement.unpaid') },
        partial: { text: t('app.kuaizhizao.paymentApplication.settlement.partial') },
        paid: { text: t('app.kuaizhizao.paymentApplication.settlement.paid') },
      }) as const,
    [t],
  );
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const auditEnabled = useAuditRequired('payment_application', true);
  const paymentApplicationAuditColumn = useMemo(
    () => createListAuditPhaseColumn<PaymentApplication>({ t, auditEnabled }),
    [t, auditEnabled],
  );
  const paymentApplicationWorkflowStatuses = useMemo(
    () => ({
      draftStatuses: ['草稿', 'draft', 'DRAFT'],
      pendingStatuses: ['待审核', 'pending_review', 'PENDING_REVIEW', 'PENDING'],
      approvedStatuses: ['已批准', '部分付款', '已通过', 'APPROVED', 'AUDITED', '已审核'],
      rejectedStatuses: ['已驳回', 'rejected', 'REJECTED'],
    }),
    [],
  );
  const paymentMethodOptions = useMemo(() => getPaymentMethodOptions(t), [t]);
  const { data: advancePayeeUserOptions = [] } = useQuery({
    queryKey: ['payment-advance-payee-users'],
    queryFn: () => loadUserFormReferenceOptions(),
    staleTime: 60_000,
  });
  const invoiceStatusOptions = useMemo(
    () => [
      {
        value: '有发票',
        label: t('app.kuaizhizao.paymentApplication.invoiceStatus.hasInvoice'),
      },
      {
        value: '无发票',
        label: t('app.kuaizhizao.paymentApplication.invoiceStatus.noInvoice'),
      },
      {
        value: '发票后补',
        label: t('app.kuaizhizao.paymentApplication.invoiceStatus.later'),
      },
    ],
    [t],
  );
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  const selectedApplicationsForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
        .filter((row): row is PaymentApplication => row != null),
    [selectedRowKeys],
  );

  const selectedApplicationForToolbar = useMemo(() => {
    if (selectedApplicationsForBatch.length !== 1) return null;
    return selectedApplicationsForBatch[0] ?? null;
  }, [selectedApplicationsForBatch]);

  const paymentApplicationAuditBatchHandlers = useMemo(
    () => ({
      submit: (id: number) => submitPaymentApplication(id),
      approve: (id: number) => approvePaymentApplication(id, { approved: true }),
      withdraw: (id: number) => withdrawPaymentApplication(id),
      revoke: (id: number) => revokePaymentApplication(id),
    }),
    [],
  );

  const handlePaymentApplicationAuditBatchSuccess = useCallback(() => {
    setSelectedRowKeys([]);
    actionRef.current?.reload();
  }, []);

  const {
    runAction: runPaymentApplicationAuditBatch,
    auditModal: paymentApplicationAuditModal,
  } = useAuditBatchRunner<PaymentApplication>({
    permGates: perms,
    handlers: paymentApplicationAuditBatchHandlers,
    onBatchComplete: handlePaymentApplicationAuditBatchSuccess,
    auditEntity: {
      entityType: 'payment_application',
      entityName: t('app.kuaizhizao.paymentApplication.entityName'),
    },
  });

  const paymentApplicationToolbarAuditMenus = useMemo(() => {
    const canPerm = (action: AuditBatchAction) => {
      const perm = action === 'approve' ? 'audit' : action === 'submit' ? 'submit' : 'revoke';
      return perms.canAction?.(perm) ?? false;
    };
    const item = (
      key: string,
      action: AuditBatchAction,
      label: string,
      capKey: string,
      rows: PaymentApplication[],
    ): UniBatchMenuItem => ({
      key,
      label,
      disabled:
        selectedApplicationsForBatch.length > 0
        && !defaultAuditBatchAllowed(rows, canPerm(action), capKey, (row) => row),
      onClick: (keys) => {
        const idSet = new Set(rows.map((row) => String(row.id)));
        return runPaymentApplicationAuditBatch(
          action,
          keys.filter((rowKey) => idSet.has(String(rowKey))),
          rows,
          auditEnabled,
        );
      },
    });
    const capOn = (row: PaymentApplication, capKey: string) => pickCapability(row, capKey)?.allowed === true;
    const submittedRows = selectedApplicationsForBatch.filter(
      (row) => String(row.status || '').trim() === 'SUBMITTED' && capOn(row, 'withdraw_submit'),
    );
    const pendingRows = selectedApplicationsForBatch.filter((row) => {
      const status = String(row.status || '').trim();
      return status !== 'SUBMITTED' && isPendingReviewStatus(status) && capOn(row, 'withdraw_submit');
    });
    const submitReviewRows = selectedApplicationsForBatch.filter((row) =>
      (row.audit?.allowed_actions ?? []).includes('submit_review'),
    );
    const canSubmitReview = perms.canAction?.('submit') ?? false;
    const submitRows = selectedApplicationsForBatch.filter((row) => capOn(row, 'submit'));
    const submitMenuItem = item('submit', 'submit', t('common.submit'), 'submit', submitRows);
    const submitDisabled = Boolean(submitMenuItem.disabled);
    return {
      submit: withDocumentSubmitCombinedItem(
        [
          submitMenuItem,
          item('withdraw-submit', 'withdraw', t('app.kuaizhizao.paymentApplication.toolbar.withdrawSubmit'), 'withdraw_submit', submittedRows),
          {
            key: 'submit-review',
            label: t('app.kuaizhizao.paymentApplication.toolbar.submitReview'),
            disabled: selectedApplicationsForBatch.length > 0 && !(canSubmitReview && submitReviewRows.length > 0),
            onClick: (keys: React.Key[]) => runCapabilityBatchLoop({
              keys,
              records: submitReviewRows,
              capabilityKey: 'submit_review',
              permAllowed: canSubmitReview,
              notAllowedMessage: t('app.kuaizhizao.paymentApplication.toolbar.submitReviewNotAllowed'),
              onRun: (id) => submitPaymentApplicationForReview(id),
              message: messageApi,
              t,
              onSuccess: handlePaymentApplicationAuditBatchSuccess,
            }),
          },
        ],
        {
          t,
          message: messageApi,
          disabled: submitDisabled,
          commitRecords: submitRows,
          permAllowed: canSubmitReview,
          commit: (id) => submitPaymentApplication(id),
          submitReview: (id) => submitPaymentApplicationForReview(id),
          onSuccess: handlePaymentApplicationAuditBatchSuccess,
        },
      ),
      audit: [
        item('approve', 'approve', t('components.uniAction.audit'), 'approve', selectedApplicationsForBatch.filter((row) => capOn(row, 'approve'))),
        item('withdraw-review', 'withdraw', t('app.kuaizhizao.paymentApplication.toolbar.withdrawReview'), 'withdraw_submit', pendingRows),
        item('revoke', 'revoke', t('app.kuaizhizao.paymentApplication.toolbar.revoke'), 'revoke_approval', selectedApplicationsForBatch.filter((row) => capOn(row, 'revoke_approval'))),
      ] satisfies UniBatchMenuItem[],
    };
  }, [
    auditEnabled,
    handlePaymentApplicationAuditBatchSuccess,
    messageApi,
    perms,
    runPaymentApplicationAuditBatch,
    selectedApplicationsForBatch,
    t,
  ]);

  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<PaymentApplication | null>(null);
  const [poLinePreviewByOrderId, setPoLinePreviewByOrderId] = useState<
    Record<number, DocumentLineMaterialPreviewItem[]>
  >({});
  const [editId, setEditId] = useState<number | null>(null);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const commitAfterSaveRef = useRef(false);
  const [paymentFormBusy, setPaymentFormBusy] = useState(false);
  const [pushPaymentOpen, setPushPaymentOpen] = useState(false);
  const [pushPaymentSubmitting, setPushPaymentSubmitting] = useState(false);
  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const formRef = useRef<ProFormInstance>();
  const pushPaymentFormRef = useRef<ProFormInstance>();
  const getApplicationKind = useCallback(
    () => formApplicationKind(formRef.current?.getFieldValue('applicationKind')),
    [],
  );
  const formLinePull = usePaymentApplicationFormLinePull({ formRef, getApplicationKind });
  /** 复制新建：在 Tab 表单页挂载前缓存初值，由 initPaymentApplicationCreateForm 写入 */
  const pendingEditValuesRef = useRef<Record<string, unknown> | null>(null);
  const [supplierOptions, setSupplierOptions] = useState<Array<{ id: number; name: string }>>([]);
  const [payableOptions, setPayableOptions] = useState<
    Array<{ payableId: number; payableCode: string; maxRequestAmount: number }>
  >([]);
  const [payableSupplierId, setPayableSupplierId] = useState<number | null>(null);
  const [payablesLoading, setPayablesLoading] = useState(false);

  useEffect(() => {
    void bankAccountService
      .list({ limit: 200, is_active: true })
      .then((res) => setBankAccounts(res.data || []))
      .catch(() => setBankAccounts([]));
  }, []);

  const openPushPaymentModal = useCallback(() => {
    if (!detail) return;
    setPushPaymentOpen(true);
  }, [detail]);

  const onSupplierChange = useCallback(
    async (supplierId: number, opts?: { silentEmpty?: boolean }) => {
      if (!Number.isFinite(supplierId) || supplierId <= 0) {
        setPayableSupplierId(null);
        setPayableOptions([]);
        return;
      }
      setPayableSupplierId(supplierId);
      setPayablesLoading(true);
      try {
        const res = await listPayablesForPaymentApplication(supplierId, { limit: 200 });
        const options = (res.data ?? []).map((row) => ({
          payableId: Number(row.payable_id),
          payableCode: String(row.payable_code ?? ''),
          maxRequestAmount: Number(row.max_request_amount ?? 0),
        }));
        setPayableOptions(options.filter((o) => o.payableId > 0 && o.maxRequestAmount > 0));
        // 编辑打开时静默：已有明细不代表还能再拉新应付；仅用户改供应商时提示
        if (options.length === 0 && !opts?.silentEmpty) {
          messageApi.info(t('app.kuaizhizao.paymentApplication.noPayablesForSupplier'));
        }
      } catch (err: unknown) {
        setPayableOptions([]);
        const msg = err instanceof Error ? err.message : t('common.loadFailed');
        messageApi.error(msg);
      } finally {
        setPayablesLoading(false);
      }
    },
    [messageApi, t],
  );

  const openDetail = useCallback(async (record: PaymentApplication) => {
    const full = await getPaymentApplication(record.id);
    setDetail(full);
    setDetailOpen(true);
  }, []);

  useEffect(() => {
    if (!detailOpen || !detail?.items?.length) {
      setPoLinePreviewByOrderId({});
      return;
    }
    const sources = detail.purchaseOrderSources ?? [];
    const seeded: Record<number, DocumentLineMaterialPreviewItem[]> = {};
    for (const po of sources) {
      const mapped = mapPurchaseOrderItemsToPreview(po.items);
      if (mapped.length) {
        seeded[Number(po.id)] = mapped;
      }
    }
    setPoLinePreviewByOrderId(seeded);

    const needFetch = new Set<number>();
    for (const row of detail.items) {
      if (String(row.materialName ?? '').trim()) continue;
      if (!isPurchaseOrderSourceType(row.sourceType)) continue;
      const sid = row.sourceId != null ? Number(row.sourceId) : 0;
      if (sid <= 0 || seeded[sid]?.length) continue;
      needFetch.add(sid);
    }
    if (!needFetch.size) {
      return;
    }
    let cancelled = false;
    void (async () => {
      const fetched: Record<number, DocumentLineMaterialPreviewItem[]> = {};
      await Promise.all(
        [...needFetch].map(async (id) => {
          try {
            const po = await getPurchaseOrder(id);
            const mapped = mapPurchaseOrderItemsToPreview(po.items);
            if (mapped.length) {
              fetched[id] = mapped;
            }
          } catch {
            /* 无读权限或单据已删：保持占位 */
          }
        }),
      );
      if (cancelled) return;
      setPoLinePreviewByOrderId((prev) => ({ ...prev, ...fetched }));
    })();
    return () => {
      cancelled = true;
    };
  }, [detailOpen, detail?.id, detail?.items, detail?.purchaseOrderSources]);

  const loadPaymentApplicationEditForm = useCallback(
    async (id: number) => {
      setFormPageLoading(true);
      try {
        const full = await getPaymentApplication(id);
        const suppliers = await loadSupplierFormReferenceList(KUAIZHIZAO_DOC_HOST.paymentApplication);
        setSupplierOptions(suppliers.map((s) => ({ id: s.id, name: s.name })));
        setEditId(full.id);
        setEditingStatus(full.status ?? null);
        const formItems = await buildPaymentApplicationEditFormItems(
          full.applicationKind,
          full.items ?? [],
        );
        formRef.current?.resetFields();
        formRef.current?.setFieldsValue({
          supplierId: full.supplierId,
          department_id: full.departmentId,
          applicationDate: coerceFormDate(full.applicationDate) ?? dayjs(),
          expectedPaymentDate: coerceFormDate(full.expectedPaymentDate),
          paymentMethod: full.paymentMethod || BANK_TRANSFER_PAYMENT_METHOD,
          advancePayeeId: full.advancePayeeId,
          applicationKind: formApplicationKind(full.applicationKind),
          invoiceStatus: full.invoiceStatus,
          supplierAccountName: full.supplierAccountName,
          supplierBankName: full.supplierBankName,
          supplierBankAccount: full.supplierBankAccount,
          notes: full.notes,
          requirePaymentVoucher: Boolean(full.requirePaymentVoucher),
          attachments: mapAttachmentsToUploadList(
            full.attachments as Parameters<typeof mapAttachmentsToUploadList>[0],
          ),
          headerRequestAmount: full.totalRequestAmount,
          items: formItems,
        });
        await onSupplierChange(Number(full.supplierId), { silentEmpty: true });
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('common.loadFailed')));
        leavePaymentApplicationFormPage();
      } finally {
        setFormPageLoading(false);
      }
    },
    [leavePaymentApplicationFormPage, messageApi, onSupplierChange, t],
  );

  const openEdit = useCallback(
    (record: PaymentApplication) => {
      if (record.capabilities?.update?.allowed === false) {
        messageApi.warning(t('common.updateFailed'));
        return;
      }
      navigate(paymentApplicationEditPath(record.id));
    },
    [messageApi, navigate, t],
  );

  const initPaymentApplicationCreateForm = useCallback(async () => {
    setEditId(null);
    setEditingStatus(null);
    const suppliers = await loadSupplierFormReferenceList(KUAIZHIZAO_DOC_HOST.paymentApplication);
    setSupplierOptions(suppliers.map((s) => ({ id: s.id, name: s.name })));
    setPayableOptions([]);
    setPayableSupplierId(null);
    formRef.current?.resetFields();
    const pending = pendingEditValuesRef.current;
    if (pending) {
      pendingEditValuesRef.current = null;
      formRef.current?.setFieldsValue(pending);
      const supplierId = pending.supplierId;
      if (supplierId != null && Number(supplierId) > 0) {
        await onSupplierChange(Number(supplierId), { silentEmpty: true });
      }
      return;
    }
    formRef.current?.setFieldsValue({
      applicationDate: dayjs(),
      paymentMethod: BANK_TRANSFER_PAYMENT_METHOD,
      applicationKind: 'goods',
      requirePaymentVoucher: false,
      attachments: [],
      items: [],
    });
  }, [onSupplierChange]);

  useEffect(() => {
    if (!isFormPage) {
      formPageInitKeyRef.current = null;
      return;
    }
    const initKey = isCreatePage ? 'create' : `edit-${editRouteId}`;
    if (formPageInitKeyRef.current === initKey) return;
    formPageInitKeyRef.current = initKey;
    if (isCreatePage) {
      void initPaymentApplicationCreateForm();
    } else if (editRouteId != null) {
      void loadPaymentApplicationEditForm(editRouteId);
    }
  }, [
    editRouteId,
    initPaymentApplicationCreateForm,
    isCreatePage,
    isFormPage,
    loadPaymentApplicationEditForm,
  ]);

  const executeDeleteOne = useCallback(
    async (row: PaymentApplication) => {
      try {
        await deletePaymentApplication(row.id);
        messageApi.success(t('app.kuaizhizao.paymentApplication.deleteSuccess'));
        if (detail?.id === row.id) {
          setDetail(null);
          setDetailOpen(false);
        }
        actionRef.current?.reload();
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(error) || t('app.kuaizhizao.paymentApplication.deleteFailed'),
        );
      }
    },
    [detail?.id, messageApi, t],
  );

  const columns: ProColumns<PaymentApplication>[] = useMemo(
    () =>
      alignProColumns<PaymentApplication>(
        [
          ...financeDocCodePartnerSearchColumns({
            docCodeLabel: t('app.kuaizhizao.paymentApplication.applicationCode'),
            docCodeField: 'applicationCode',
            partnerLabel: t('app.kuaizhizao.paymentApplication.supplierName'),
            partnerIdField: 'supplierId',
            partnerNameField: 'supplierName',
            partnerRequest: async ({ keyWords }) => {
              const list = await loadSupplierFormReferenceList(KUAIZHIZAO_DOC_HOST.paymentApplication);
              const kw = String(keyWords ?? '')
                .trim()
                .toLowerCase();
              const filtered = kw
                ? list.filter(
                    (s) =>
                      String(s.name ?? '')
                        .toLowerCase()
                        .includes(kw) ||
                      String(s.code ?? '')
                        .toLowerCase()
                        .includes(kw),
                  )
                : list;
              return filtered.slice(0, 50).map((s) => ({ label: s.name, value: s.id }));
            },
          }),
          {
            title: t('app.kuaizhizao.paymentApplication.col.supplierAndCode'),
            key: 'finance_doc_partner_stacked',
            dataIndex: 'applicationCode',
            width: 240,
            minWidth: 240,
            uniTableKeepWidth: true,
            uniTablePrimaryFlex: false,
            resizable: false,
            fixed: 'left',
            hideInSearch: true,
            ellipsis: false,
            render: (_, r) => (
              <UniTableStackedPrimaryCell
                primary={String(r.supplierName ?? '')}
                secondary={String(r.applicationCode ?? '')}
                onSecondaryClick={() => void openDetail(r)}
              />
            ),
          },
          {
            title: t('app.kuaizhizao.paymentApplication.supplierName'),
            dataIndex: 'supplierName',
            hideInTable: true,
          },
          {
            title: t('app.kuaizhizao.paymentApplication.applicationKind'),
            key: 'finance_payment_settlement_type',
            dataIndex: 'applicationKind',
            ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
            hideInSearch: true,
            render: (_, r) => {
              const kind = formApplicationKind(r.applicationKind);
              return (
                <MarkerTag color={kind === 'prepayment' ? 'blue' : 'default'}>
                  {kind === 'prepayment'
                    ? t('app.kuaizhizao.paymentApplication.applicationKind.prepayment')
                    : t('app.kuaizhizao.paymentApplication.applicationKind.goods')}
                </MarkerTag>
              );
            },
          },
          {
            title: t('app.kuaizhizao.paymentApplication.totalRequestAmount'),
            key: 'total_amount',
            dataIndex: 'totalRequestAmount',
            align: 'right',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, r) => formatCurrencyAmount(r.totalRequestAmount),
          },
          {
            title: t('app.kuaizhizao.paymentApplication.remainingAmount'),
            key: 'remaining_amount',
            dataIndex: 'remainingAmount',
            align: 'right',
            width: 132,
            minWidth: 132,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, r) => formatCurrencyAmount(r.remainingAmount),
          },
          {
            title: t('app.kuaizhizao.paymentApplication.applicationDate'),
            key: 'application_date',
            dataIndex: 'applicationDate',
            valueType: 'date',
            width: 132,
            minWidth: 132,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, r) => (r.applicationDate ? formatDateBySiteSetting(r.applicationDate) : '—'),
          },
          {
            title: t('app.kuaizhizao.paymentApplication.notes'),
            dataIndex: 'notes',
            minWidth: 160,
            uniTableRemainderFlex: true,
            uniTablePrimaryFlex: true,
            resizable: false,
            hideInSearch: true,
            ellipsis: true,
            render: (_, r) => r.notes?.trim() || '—',
          },
          ...buildDocumentAuditColumns<PaymentApplication>(t),
          ...(paymentApplicationAuditColumn ? [paymentApplicationAuditColumn] : []),
          {
            title: t('app.kuaizhizao.paymentApplication.col.approvalStatus'),
            key: 'approval_phase',
            dataIndex: 'approvalPhase',
            hideInTable: true,
            valueType: 'select',
            valueEnum: paymentApplicationApprovalPhaseEnum,
          },
          {
            title: t('app.kuaizhizao.paymentApplication.col.paymentSettlement'),
            key: 'payment_settlement',
            dataIndex: 'paymentSettlement',
            ...UNI_TABLE_PAYMENT_SETTLEMENT_COLUMN_DEFAULTS,
            fixed: 'right',
            valueType: 'select',
            valueEnum: paymentApplicationSettlementEnum,
            render: (_, r) => {
              const settlement = resolvePaymentApplicationSettlementDisplay(r);
              if (!settlement) return '—';
              return renderDocumentStatusTag(settlement.label, settlement.raw);
            },
          },
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => {
              const nodes: React.ReactNode[] = [];
              if (perms.canRead) {
                nodes.push(
                  <Button key="detail" {...rowActionKind('read')} onClick={() => void openDetail(row)} />,
                );
              }
              if (perms.canUpdate && row.capabilities?.update?.allowed) {
                nodes.push(
                  <Button key="edit" {...rowActionKind('update')} onClick={() => void openEdit(row)} />,
                );
              }
              return nodes;
            },
          },
        ],
        SALES_DOC_LIST_FIELD_RANK,
      ),
    [
      openDetail,
      openEdit,
      paymentApplicationAuditColumn,
      paymentApplicationApprovalPhaseEnum,
      paymentApplicationSettlementEnum,
      perms.canRead,
      perms.canUpdate,
      t,
    ],
  );

  const openCreate = () => {
    pendingEditValuesRef.current = null;
    navigate(PAYMENT_APPLICATION_CREATE_PATH);
  };

  const handleBatchDelete = async (keys: React.Key[]) => {
    if (!keys.length) return;
    const rows = keys
      .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
      .filter((row): row is PaymentApplication => row != null);
    const deletable = rows.filter((row) => row.capabilities?.delete?.allowed === true);
    if (deletable.length === 0) {
      messageApi.warning(t('app.kuaizhizao.paymentApplication.batchDeleteNoneDeletable'));
      return;
    }
    if (deletable.length < rows.length) {
      messageApi.warning(t('app.kuaizhizao.paymentApplication.batchDeletePartial'));
    }
    for (const row of deletable) {
      await deletePaymentApplication(row.id);
    }
    messageApi.success(t('app.kuaizhizao.paymentApplication.batchDeleteSuccess', { count: deletable.length }));
    setSelectedRowKeys([]);
    if (detail?.id != null && deletable.some((row) => row.id === detail.id)) {
      setDetail(null);
      setDetailOpen(false);
    }
    actionRef.current?.reload();
  };

  const handleSave = async (values: Record<string, unknown>) => {
    const shouldCommit = commitAfterSaveRef.current;
    commitAfterSaveRef.current = false;
    const wasEdit = editId != null;
    const supplier = supplierOptions.find((s) => s.id === values.supplierId);
    const items: PaymentApplicationLine[] = normalizeFormListItems<Record<string, unknown>>(
      values.items,
    ).map((row: Record<string, unknown>, index: number) => {
      const payableId = row.payableId as number | undefined;
      const opt = payableOptions.find((p) => p.payableId === payableId);
      const sourceType = String(row.sourceType || 'payable').trim() || 'payable';
      const sourceId =
        row.sourceId != null && Number(row.sourceId) > 0
          ? Number(row.sourceId)
          : payableId;
      const sourceCode =
        (row.sourceCode as string | undefined)?.trim()
        || opt?.payableCode
        || (row.payableCode as string | undefined);
      return {
        sourceType,
        sourceId,
        sourceCode,
        payableId,
        payableCode: opt?.payableCode || (row.payableCode as string | undefined),
        lineKind: String(row.lineKind || 'goods'),
        requestAmount: Number(row.requestAmount),
        materialName: (row.materialName as string | undefined) || undefined,
        materialSpec: (row.materialSpec as string | undefined) || undefined,
        quantity: row.quantity != null && row.quantity !== '' ? Number(row.quantity) : undefined,
        materialUnit: (row.materialUnit as string | undefined) || undefined,
        sourceLineId: row.sourceLineId != null ? Number(row.sourceLineId) : undefined,
        lineNo: index + 1,
      };
    });
    const employeeAdvance = isEmployeeAdvancePaymentMethod(values.paymentMethod);
    const hidePayeeAccount = hidesSupplierPayeeAccount(values.paymentMethod);
    const applicationKind = formApplicationKind(values.applicationKind);
    const deptPayload = resolvePurchaseDepartmentPayload(
      values.department_id,
      resolveDepartmentName,
    );
    const payload = {
      supplierId: values.supplierId,
      supplierName: supplier?.name ?? values.supplierName,
      departmentId: deptPayload.department_id,
      departmentName: deptPayload.department_name,
      applicationKind,
      applicationDate: toApiDateString(values.applicationDate),
      expectedPaymentDate: toApiDateString(values.expectedPaymentDate),
      paymentMethod: values.paymentMethod,
      advancePayeeId: employeeAdvance ? values.advancePayeeId : undefined,
      advancePayeeName: employeeAdvance
        ? resolveAdvancePayeeName(values.advancePayeeId, advancePayeeUserOptions)
        : undefined,
      invoiceStatus: values.invoiceStatus,
      supplierAccountName: hidePayeeAccount ? undefined : values.supplierAccountName,
      supplierBankName: hidePayeeAccount ? undefined : values.supplierBankName,
      supplierBankAccount: hidePayeeAccount ? undefined : values.supplierBankAccount,
      notes: values.notes,
      requirePaymentVoucher: Boolean(values.requirePaymentVoucher),
      attachments: normalizeDocumentAttachments(values.attachments),
      items: items.map((line) => ({
        ...line,
        lineKind:
          applicationKind === 'prepayment'
            ? 'prepayment'
            : String(line.lineKind || '').trim() === 'prepayment'
              ? 'goods'
              : line.lineKind || 'goods',
      })),
    };
    setPaymentFormBusy(true);
    let savedId = editId;
    try {
      if (editId) {
        await updatePaymentApplication(editId, payload);
      } else {
        const created = await createPaymentApplication(payload);
        savedId = created.id;
        setEditId(created.id);
      }
      if (shouldCommit && savedId != null) {
        try {
          await submitPaymentApplication(savedId);
        } catch (error) {
          setEditId(savedId);
          messageApi.error(getApiErrorMessage(error, t('common.saveFailed')));
          actionRef.current?.reload();
          return;
        }
        messageApi.success(t('app.kuaizhizao.paymentApplication.committed'));
      } else if (wasEdit) {
        messageApi.success(t('common.updateSuccess'));
      } else {
        messageApi.success(t('common.createSuccess'));
      }
      leavePaymentApplicationFormPage();
      setEditId(null);
      setEditingStatus(null);
      actionRef.current?.reload();
    } finally {
      setPaymentFormBusy(false);
    }
  };

  const paymentApplicationCanCommit =
    isCreatePage
    || editId == null
    || ['', '草稿', 'draft', 'DRAFT', '已驳回', 'REJECTED', 'rejected'].includes(
      String(editingStatus || '').trim(),
    );

  const toolbarPushMenuItems = useMemo(
    () => buildUniPushMenuItems([
      {
        key: 'push-payment',
        label: t('app.kuaizhizao.paymentApplication.pushPayment'),
        targetDocumentType: 'payment',
        disabledReason:
          selectedApplicationForToolbar
          && (
            perms.canAction?.('push') !== true
            || selectedApplicationForToolbar.capabilities?.push_payment?.allowed !== true
          )
            ? t('app.kuaizhizao.paymentApplication.toolbar.pushNotAllowed')
            : undefined,
        onClick: () => {
          const row = selectedApplicationForToolbar;
          if (!row?.id) return;
          void getPaymentApplication(row.id).then((full) => {
            setDetail(full);
            setPushPaymentOpen(true);
          }).catch((error: unknown) => {
            messageApi.error(getApiErrorMessage(error, t('common.loadFailed')));
          });
        },
      },
    ]),
    [messageApi, perms, selectedApplicationForToolbar, t],
  );

  const toolbarPushDisabledReason = buildUniPushToolbarDisabledReason(t, {
    selectedCount: selectedRowKeys.length,
    hasSelectedRecord: Boolean(selectedApplicationForToolbar),
  });

  async function handleCopySelectedPaymentApplication() {
    const row = selectedApplicationForToolbar;
    if (!row?.id) {
      messageApi.warning(t('app.kuaizhizao.paymentApplication.selectToCopy'));
      return;
    }
    try {
      const full = await getPaymentApplication(row.id);
      const formItems = (await buildPaymentApplicationEditFormItems(
        full.applicationKind,
        full.items ?? [],
      )).map((line) => ({
        lineKind: line.lineKind,
        requestAmount: line.requestAmount,
        materialName: line.materialName,
        materialSpec: line.materialSpec,
        quantity: line.quantity,
        materialUnit: line.materialUnit,
      }));
      pendingEditValuesRef.current = {
        supplierId: full.supplierId,
        applicationDate: dayjs(),
        expectedPaymentDate: coerceFormDate(full.expectedPaymentDate),
        paymentMethod: full.paymentMethod || BANK_TRANSFER_PAYMENT_METHOD,
        advancePayeeId: full.advancePayeeId,
        applicationKind: formApplicationKind(full.applicationKind),
        invoiceStatus: full.invoiceStatus,
        supplierAccountName: full.supplierAccountName,
        supplierBankName: full.supplierBankName,
        supplierBankAccount: full.supplierBankAccount,
        notes: full.notes,
        requirePaymentVoucher: Boolean(full.requirePaymentVoucher),
        attachments: mapAttachmentsToUploadList(
          full.attachments as Parameters<typeof mapAttachmentsToUploadList>[0],
        ),
        headerRequestAmount: full.totalRequestAmount,
        items: formItems,
      };
      formPageInitKeyRef.current = null;
      navigate(PAYMENT_APPLICATION_CREATE_PATH);
    } catch (error) {
      messageApi.error(getApiErrorMessage(error, t('common.loadFailed')));
    }
  }

  const handlePaymentFormValuesChange = useCallback(
    (changedValues: Record<string, unknown>, allValues: Record<string, unknown>) => {
      if (Object.prototype.hasOwnProperty.call(changedValues, 'items')) {
        const sum = sumPaymentApplicationFormLineAmounts(allValues.items);
        const rows = normalizeFormListItems<Record<string, unknown>>(allValues.items);
        if (rows.length > 0) {
          formRef.current?.setFieldsValue({
            headerRequestAmount: sum > 0 ? sum : undefined,
          });
        }
        return;
      }
      if (!Object.prototype.hasOwnProperty.call(changedValues, 'headerRequestAmount')) {
        return;
      }
      const rows = normalizeFormListItems<Record<string, unknown>>(allValues.items);
      if (!rows.length) {
        return;
      }
      const kind = formApplicationKind(allValues.applicationKind);
      const nextAmount = Number(changedValues.headerRequestAmount);
      if (!Number.isFinite(nextAmount)) {
        return;
      }
      if (
        kind === 'prepayment'
        && rows.every((row) => isPrepaymentPurchaseOrderFormLine(row, kind))
      ) {
        formRef.current?.setFieldsValue({
          items: applyHeaderAmountToPrepaymentLines(nextAmount, rows),
        });
        return;
      }
      if (rows.length !== 1) {
        return;
      }
      formRef.current?.setFieldsValue({
        items: [{ ...rows[0], requestAmount: nextAmount }],
      });
    },
    [formRef],
  );

  const triggerPaymentApplicationCommit = useCallback(() => {
    commitAfterSaveRef.current = true;
    void formRef.current
      ?.validateFields()
      .then((values) => handleSave(values as Record<string, unknown>))
      .catch((error: unknown) => {
        commitAfterSaveRef.current = false;
        if (error && typeof error === 'object' && 'errorFields' in (error as object)) return;
        messageApi.error(getApiErrorMessage(error, t('common.saveFailed')));
      });
  }, [formRef, handleSave, messageApi, t]);

  useSubmitShortcut(() => {
    void formRef.current
      ?.validateFields()
      .then((values) => handleSave(values as Record<string, unknown>))
      .catch(() => {});
  }, isFormPage);

  if (isFormPage) {
    return (
      <>
        <DocumentFormPageLayout
          header={
            <>
              <Space align="center" size={8}>
                <Button
                  type="text"
                  icon={<ArrowLeftOutlined />}
                  aria-label={t('common.back')}
                  onClick={leavePaymentApplicationFormPage}
                />
                <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
                  {isCreatePage
                    ? t('app.kuaizhizao.paymentApplication.create')
                    : t('app.kuaizhizao.paymentApplication.editTitle')}
                </Typography.Title>
              </Space>
              <DocumentFormPageHeaderActions
                onCancel={leavePaymentApplicationFormPage}
                onSaveDraft={() => {
                  void formRef.current
                    ?.validateFields()
                    .then((values) => handleSave(values as Record<string, unknown>))
                    .catch((error: unknown) => {
                      if (error && typeof error === 'object' && 'errorFields' in (error as object)) return;
                      messageApi.error(getApiErrorMessage(error, t('common.saveFailed')));
                    });
                }}
                onPrimarySubmit={() => {
                  void formRef.current
                    ?.validateFields()
                    .then((values) => handleSave(values as Record<string, unknown>))
                    .catch((error: unknown) => {
                      if (error && typeof error === 'object' && 'errorFields' in (error as object)) return;
                      messageApi.error(getApiErrorMessage(error, t('common.saveFailed')));
                    });
                }}
                isCreatePage={isCreatePage}
                showSaveDraft={false}
                canSubmitAfterSave={false}
                showCommitSubmit={paymentApplicationCanCommit}
                saveDraftLoading={paymentFormBusy}
                commitSubmitLoading={paymentFormBusy}
                onCommitSubmit={triggerPaymentApplicationCommit}
              />
            </>
          }
        >
          <Spin spinning={formPageLoading || paymentFormBusy}>
            <div className="form-modal-content-inner">
              <ProForm
                formRef={formRef}
                layout="vertical"
                submitter={false}
                onFinish={async (values) => {
                  try {
                    await handleSave(values as Record<string, unknown>);
                  } catch (error) {
                    messageApi.error(getApiErrorMessage(error, t('common.saveFailed')));
                  }
                }}
                onValuesChange={handlePaymentFormValuesChange}
              >
        <Row gutter={16}>
          <Col span={8}>
            <ProFormSelect
              name="supplierId"
              label={t('app.kuaizhizao.paymentApplication.supplierName')}
              rules={[{ required: true }]}
              options={supplierOptions.map((s) => ({ value: s.id, label: s.name }))}
              fieldProps={{
                showSearch: true,
                optionFilterProp: 'label',
                onChange: (v) => {
                  void onSupplierChange(Number(v));
                  formRef.current?.setFieldsValue({ items: [] });
                },
              }}
            />
          </Col>
          <Col span={8}>
            <ProFormDatePicker
              name="applicationDate"
              label={t('app.kuaizhizao.paymentApplication.applicationDate')}
              rules={[{ required: true }]}
              fieldProps={{ style: { width: '100%' } }}
            />
          </Col>
          <Col span={8}>
            <ProFormDatePicker
              name="expectedPaymentDate"
              label={t('app.kuaizhizao.paymentApplication.expectedPaymentDate')}
              fieldProps={{ style: { width: '100%' } }}
            />
          </Col>
          <Col span={8}>
            <PurchaseDepartmentFormField
              required
              options={departmentOptions}
              loading={departmentOptionsLoading}
            />
          </Col>
          <Col span={8}>
            <ProFormSelect
              name="paymentMethod"
              label={t('app.kuaizhizao.paymentApplication.paymentMethod')}
              rules={[{ required: true }]}
              options={paymentMethodOptions}
            />
          </Col>
          <Col span={8}>
            <ProFormSelect
              name="invoiceStatus"
              label={t('app.kuaizhizao.paymentApplication.invoiceStatus')}
              rules={[{ required: true, message: t('common.required') }]}
              options={invoiceStatusOptions}
            />
          </Col>
          <Col span={8}>
            <ProFormDigit
              name="headerRequestAmount"
              label={t('app.kuaizhizao.paymentApplication.totalRequestAmount')}
              min={0.01}
              fieldProps={{ precision: 2, style: { width: '100%' } }}
            />
          </Col>
          <Col span={8}>
            <ProFormItem
              name="applicationKind"
              label={t('app.kuaizhizao.paymentApplication.applicationKind')}
              initialValue="goods"
              rules={[{ required: true }]}
            >
              <ThemedSegmented
                className="form-field-segmented"
                style={{ width: 'fit-content', maxWidth: '100%' }}
                options={[
                  {
                    label: t('app.kuaizhizao.paymentApplication.applicationKind.goods'),
                    value: 'goods',
                  },
                  {
                    label: t('app.kuaizhizao.paymentApplication.applicationKind.prepayment'),
                    value: 'prepayment',
                  },
                ]}
                onChange={(next) => {
                  const lineKind = lineKindFromApplicationKind(next);
                  const items = normalizeFormListItems<Record<string, unknown>>(
                    formRef.current?.getFieldValue('items'),
                  );
                  if (!itemsCompatibleWithApplicationKind(items, lineKind)) {
                    formRef.current?.setFieldsValue({
                      applicationKind: lineKind,
                      items: [],
                    });
                    messageApi.info(t('app.kuaizhizao.paymentApplication.settlementTypeClearedLines'));
                    return;
                  }
                  formRef.current?.setFieldsValue({
                    applicationKind: lineKind,
                    items: items.map((row) => ({ ...row, lineKind })),
                  });
                }}
              />
            </ProFormItem>
          </Col>
          <ProFormDependency name={['paymentMethod']}>
            {({ paymentMethod: method }) =>
              method === EMPLOYEE_ADVANCE_PAYMENT_METHOD ? (
                <Col span={8}>
                  <PaymentAdvancePayeeField
                    methodField="paymentMethod"
                    payeeIdField="advancePayeeId"
                    colProps={false}
                  />
                </Col>
              ) : null
            }
          </ProFormDependency>
        </Row>
        <UniTableDetail
          name="items"
          title={t('app.kuaizhizao.paymentApplication.lines')}
          required
          disabledAdd
          onBatchSelect={formLinePull.openAddDetailPull}
          batchSelectText={t('common.addDetail')}
          summary={() => <PaymentApplicationLinesSummaryRow />}
          columns={[
            {
              title: t('app.kuaizhizao.paymentApplication.sourceType'),
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
                  <Form.Item name={[field.name, 'payableCode']} hidden>
                    <Input />
                  </Form.Item>
                  <Form.Item name={[field.name, 'lineKind']} hidden>
                    <Input />
                  </Form.Item>
                  <Form.Item shouldUpdate style={{ margin: 0 }}>
                    {() => {
                      const st = formRef.current?.getFieldValue(['items', field.name, 'sourceType']);
                      return paymentApplicationSourceTypeLabel(t, st);
                    }}
                  </Form.Item>
                </>
              ),
            },
            {
              title: t('app.kuaizhizao.paymentApplication.sourceCode'),
              dataIndex: 'sourceCode',
              width: 160,
              render: (_: unknown, field: FormListFieldData) => (
                <Form.Item shouldUpdate style={{ margin: 0 }}>
                  {() => {
                    const code = formRef.current?.getFieldValue(['items', field.name, 'sourceCode']);
                    const payableCode = formRef.current?.getFieldValue([
                      'items',
                      field.name,
                      'payableCode',
                    ]);
                    return String(code || payableCode || '—');
                  }}
                </Form.Item>
              ),
            },
            {
              title: t('app.kuaizhizao.paymentApplication.materialName'),
              dataIndex: 'materialName',
              width: 140,
              render: (_: unknown, field: FormListFieldData) => (
                <>
                  <Form.Item name={[field.name, 'materialName']} hidden>
                    <Input />
                  </Form.Item>
                  <Form.Item name={[field.name, 'materialSpec']} hidden>
                    <Input />
                  </Form.Item>
                  <Form.Item name={[field.name, 'quantity']} hidden>
                    <Input />
                  </Form.Item>
                  <Form.Item name={[field.name, 'materialUnit']} hidden>
                    <Input />
                  </Form.Item>
                  <Form.Item name={[field.name, 'sourceLineId']} hidden>
                    <Input />
                  </Form.Item>
                  <Form.Item shouldUpdate style={{ margin: 0 }}>
                    {() => {
                      const name = formRef.current?.getFieldValue([
                        'items',
                        field.name,
                        'materialName',
                      ]);
                      return String(name || '—');
                    }}
                  </Form.Item>
                </>
              ),
            },
            {
              title: t('app.kuaizhizao.paymentApplication.materialSpec'),
              dataIndex: 'materialSpec',
              width: 120,
              render: (_: unknown, field: FormListFieldData) => (
                <Form.Item shouldUpdate style={{ margin: 0 }}>
                  {() => {
                    const spec = formRef.current?.getFieldValue([
                      'items',
                      field.name,
                      'materialSpec',
                    ]);
                    return String(spec || '—');
                  }}
                </Form.Item>
              ),
            },
            {
              title: t('app.kuaizhizao.paymentApplication.quantity'),
              dataIndex: 'quantity',
              width: 100,
              render: (_: unknown, field: FormListFieldData) => (
                <Form.Item shouldUpdate style={{ margin: 0 }}>
                  {() => {
                    const qty = formRef.current?.getFieldValue(['items', field.name, 'quantity']);
                    const unit = formRef.current?.getFieldValue([
                      'items',
                      field.name,
                      'materialUnit',
                    ]);
                    if (qty == null || qty === '') return '—';
                    const unitText = unit ? ` ${unit}` : '';
                    return `${qty}${unitText}`;
                  }}
                </Form.Item>
              ),
            },
            {
              title: t('app.kuaizhizao.paymentApplication.payableCode'),
              dataIndex: 'payableId',
              width: 200,
              render: (_: unknown, field: FormListFieldData) => (
                <>
                  <Form.Item name={[field.name, 'payableId']} hidden>
                    <Input />
                  </Form.Item>
                  <Form.Item
                    noStyle
                    dependencies={[
                      ['items', field.name, 'lineKind'],
                      ['items', field.name, 'sourceType'],
                      ['items', field.name, 'payableCode'],
                    ]}
                  >
                    {() => {
                      const lineKind = formRef.current?.getFieldValue(['items', field.name, 'lineKind']);
                      const sourceType = formRef.current?.getFieldValue([
                        'items',
                        field.name,
                        'sourceType',
                      ]);
                      const needsPayable = paymentApplicationLineNeedsPayable(lineKind, sourceType);
                      if (!needsPayable) {
                        return (
                          <span style={{ color: 'var(--ant-color-text-secondary)' }}>
                            {t('app.kuaizhizao.paymentApplication.payableOptionalPrepayment')}
                          </span>
                        );
                      }
                      const payableCode = formRef.current?.getFieldValue([
                        'items',
                        field.name,
                        'payableCode',
                      ]);
                      return String(payableCode || '—');
                    }}
                  </Form.Item>
                </>
              ),
            },
            {
              title: (
                <Form.Item noStyle shouldUpdate>
                  {() => {
                    const kind = formApplicationKind(formRef.current?.getFieldValue('applicationKind'));
                    return kind === 'prepayment'
                      ? t('app.kuaizhizao.paymentApplication.orderOriginalAmount')
                      : t('app.kuaizhizao.paymentApplication.requestAmount');
                  }}
                </Form.Item>
              ),
              dataIndex: 'requestAmount',
              width: 140,
              align: 'right',
              fixed: 'right',
              onHeaderCell: () => ({ className: 'uni-detail-fixed-amount-header' }),
              render: (_: unknown, field: FormListFieldData) => (
                <Form.Item
                  noStyle
                  shouldUpdate={(prev, cur) =>
                    prev.applicationKind !== cur.applicationKind || prev.items !== cur.items
                  }
                >
                  {() => {
                    const kind = formApplicationKind(formRef.current?.getFieldValue('applicationKind'));
                    const row = normalizeFormListItems<Record<string, unknown>>(
                      formRef.current?.getFieldValue('items'),
                    )[field.name];
                    const prepayPo =
                      row != null && isPrepaymentPurchaseOrderFormLine(row, kind);
                    if (prepayPo) {
                      const displayAmount = Number(
                        row.sourceOrderAmount ?? row.maxRequestAmount ?? row.requestAmount ?? 0,
                      );
                      return (
                        <>
                          <Form.Item name={[field.name, 'sourceOrderAmount']} hidden>
                            <Input />
                          </Form.Item>
                          <Form.Item name={[field.name, 'maxRequestAmount']} hidden>
                            <Input />
                          </Form.Item>
                          <Form.Item name={[field.name, 'requestAmount']} hidden rules={[{ required: true }]}>
                            <InputNumber min={0.01} precision={2} />
                          </Form.Item>
                          {displayAmount > 0 ? formatCurrencyAmount(displayAmount) : '—'}
                        </>
                      );
                    }
                    return (
                      <Form.Item
                        name={[field.name, 'requestAmount']}
                        style={{ margin: 0 }}
                        rules={[{ required: true }]}
                      >
                        <InputNumber size="small" min={0.01} precision={2} style={{ width: '100%' }} />
                      </Form.Item>
                    );
                  }}
                </Form.Item>
              ),
            },
          ]}
        />
        <PaymentApplicationSupplierPayeeSection />
        <Row gutter={16}>
          <Col span={24}>
            <ProFormTextArea
              name="notes"
              label={t('app.kuaizhizao.paymentApplication.notes')}
              fieldProps={{ rows: 2 }}
            />
          </Col>
          <Col span={24}>
            <DocumentAttachmentsField
              category="payment_application_attachments"
              label={t('app.kuaizhizao.paymentApplication.attachments')}
            />
          </Col>
          <Col span={24}>
            <ProFormSwitch
              name="requirePaymentVoucher"
              label={t('app.kuaizhizao.paymentApplication.requirePaymentVoucher')}
              extra={t('app.kuaizhizao.paymentApplication.requirePaymentVoucherHint')}
            />
          </Col>
        </Row>
              </ProForm>
            </div>
          </Spin>
        </DocumentFormPageLayout>
        {formLinePull.renderPullModals()}
      </>
    );
  }

  return (
    <>
      {paymentApplicationAuditModal}
      <ListPageTemplate>
        <UniTable<PaymentApplication>
          actionRef={actionRef}
          permissionResource={RESOURCE}
          pinnedTabsField={[...PAYMENT_APPLICATION_PINNED_TABS_FIELDS]}
          columnPersistenceId="apps.kuaizhizao.pages.purchase-management.payment-applications-width-v9"
          headerTitle={t('app.kuaizhizao.menu.purchase-management.payment-applications')}
          rowKey="id"
          columns={columns}
          showCreateButton={false}
          toolBarRender={() => [
            ...(perms.canCreate ? [
              <UniPullCreateToolbar
                key="create-payment-application-with-pull"
                compactKey="create-payment-application-with-pull"
                createIcon={<PlusOutlined />}
                createLabel={t('app.kuaizhizao.paymentApplication.create')}
                onCreate={() => void openCreate()}
                menuItems={[
                  ...pullCreateMenuItems,
                  { type: 'divider', key: 'copy-selected-divider' },
                  {
                    key: 'copy-selected',
                    label: t('app.kuaizhizao.paymentApplication.copySelectedCreate'),
                    disabled: !selectedApplicationForToolbar,
                    onClick: () => void handleCopySelectedPaymentApplication(),
                  },
                ]}
              />,
            ] : []),
            <UniPushToolbarButton
              key={`payment-application-push-${selectedApplicationForToolbar?.id ?? 'none'}`}
              menuItems={toolbarPushMenuItems}
              disabled={selectedRowKeys.length !== 1 || !selectedApplicationForToolbar}
              disabledReason={toolbarPushDisabledReason}
              sourceDocument={
                selectedApplicationForToolbar?.id
                  ? { type: 'payment_application', id: Number(selectedApplicationForToolbar.id) }
                  : null
              }
              pushTargets={{ 'push-payment': 'payment' }}
            />,
            <UniBatchMenuButton
              key="payment-application-submit"
              selectedRowKeys={selectedRowKeys}
              menuItems={paymentApplicationToolbarAuditMenus.submit}
              buttonText={t('common.submit')}
            />,
            <UniBatchMenuButton
              key="payment-application-audit"
              selectedRowKeys={selectedRowKeys}
              menuItems={paymentApplicationToolbarAuditMenus.audit}
              buttonText={t('components.uniAction.audit')}
            />,
          ]}
          enableRowSelection
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          showDeleteButton={perms.canDelete}
          deleteButtonText={t('common.delete')}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) =>
            t('app.kuaizhizao.paymentApplication.confirmBatchDelete', { count })
          }
          toolBarActionsAfterDelete={[]}
          rightToolBarActionsBeforeExport={[
            <UniCapabilityBatchButton
              key="payment-application-print"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedApplicationsForBatch}
              capabilityKey="print"
              permAllowed={perms.canPrint}
              batchAllowed={(records, perm) =>
                Boolean(perm) && records.some((record) => record.capabilities?.print?.allowed === true)
              }
              singleOnly
              onRun={async (id) => {
                openPrint({ documentType: 'payment_application', documentId: id });
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
                  : await fetchAllListItems((p) => listPaymentApplications(p));
              if (type === 'currentPage' && pageData?.length) {
                items = pageData;
              } else if (type === 'selected' && keys?.length) {
                items = items.filter(
                  (d: PaymentApplication) => d.id != null && keys.includes(d.id),
                );
              }
              if (items.length === 0) {
                messageApi.warning(t('common.noDataToExport'));
                return;
              }
              await downloadRecordsAsXlsx(
                items as Array<Record<string, unknown>>,
                `payment-applications-${todaySiteDateString()}.xlsx`,
              );
              messageApi.success(t('common.exportSuccess', { count: items.length }));
            } catch (error: any) {
              messageApi.error(error?.message || t('common.exportFailed'));
            }
          }}
          onTableDataChange={(rows) => {
            tableRowsRef.current = rows;
          }}
          skipFuzzyPinyinClientFilter
          request={async (params, _sort, _filter, searchFormValues) => {
            const listParams = resolvePaymentApplicationListParams(searchFormValues);
            const res = await listPaymentApplications({
              skip: ((params.current ?? 1) - 1) * (params.pageSize ?? 20),
              limit: params.pageSize ?? 20,
              ...listParams,
            });
            return { data: res.data, success: true, total: res.total };
          }}
        />
      </ListPageTemplate>

      <DetailDrawerTemplate
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        width={DRAWER_CONFIG.STANDARD_WIDTH}
        title={detail?.applicationCode}
        extra={
          detail ? (
            <Space>
              {perms.canDelete && detail.capabilities?.delete?.allowed === true ? (
                <ActionConfirmPopconfirm
                  {...rowActionKind('delete')}
                  title={t('app.kuaizhizao.paymentApplication.deleteTitle')}
                  description={t('app.kuaizhizao.paymentApplication.deleteContent', {
                    code: detail.applicationCode,
                  })}
                  okType="danger"
                  onConfirm={() => executeDeleteOne(detail)}
                >
                  <Button {...rowActionKind('delete')} danger onClick={(e) => e.stopPropagation()}>
                    {t('common.delete')}
                  </Button>
                </ActionConfirmPopconfirm>
              ) : null}
              <UniWorkflowActions
                record={detail}
                entityType="payment_application"
                entityName={t('app.kuaizhizao.paymentApplication.entityName')}
                statusField="status"
                reviewStatusField="reviewStatus"
                {...paymentApplicationWorkflowStatuses}
                theme="default"
                size="medium"
                onSuccess={() => {
                  void getPaymentApplication(detail.id).then(setDetail);
                  actionRef.current?.reload();
                }}
              />
              {detail.capabilities?.push_payment?.allowed && perms.canAction?.('push') ? (
                <Button type="primary" onClick={openPushPaymentModal}>
                  {t('app.kuaizhizao.paymentApplication.pushPayment')}
                </Button>
              ) : null}
            </Space>
          ) : null
        }
      >
        {detail ? (
          <>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.supplierName')}>
                {detail.supplierName}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.col.paymentSettlement')}>
                {(() => {
                  const settlement = resolvePaymentApplicationSettlementDisplay(detail);
                  if (!settlement) return '—';
                  return renderDocumentStatusTag(settlement.label, settlement.raw);
                })()}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.purchase.field.department')}>
                {detail.departmentName?.trim() || '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.invoiceStatus')}>
                {detail.invoiceStatus || '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.applicantName')}>
                {detail.applicantName || '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.reviewerName')}>
                {detail.reviewerName || '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.applicationDate')}>
                {detail.applicationDate ? formatDateBySiteSetting(detail.applicationDate) : '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.expectedPaymentDate')}>
                {detail.expectedPaymentDate
                  ? formatDateBySiteSetting(detail.expectedPaymentDate)
                  : '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.totalRequestAmount')}>
                {formatCurrencyAmount(detail.totalRequestAmount)}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.remainingAmount')}>
                {formatCurrencyAmount(detail.remainingAmount)}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.paymentMethod')}>
                {formatPaymentMethod(detail.paymentMethod, t)}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.applicationKind')}>
                {formApplicationKind(detail.applicationKind) === 'prepayment'
                  ? t('app.kuaizhizao.paymentApplication.applicationKind.prepayment')
                  : t('app.kuaizhizao.paymentApplication.applicationKind.goods')}
              </Descriptions.Item>
              {isEmployeeAdvancePaymentMethod(detail.paymentMethod) ? (
                <Descriptions.Item label={t('app.kuaicaiwu.payment.advancePayee')}>
                  {detail.advancePayeeName || '—'}
                </Descriptions.Item>
              ) : null}
              {!hidesSupplierPayeeAccount(detail.paymentMethod) ? (
                <>
                  <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.supplierAccountName')}>
                    {detail.supplierAccountName || '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.supplierBankName')}>
                    {detail.supplierBankName || '—'}
                  </Descriptions.Item>
                  <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.supplierBankAccount')}>
                    {detail.supplierBankAccount || '—'}
                  </Descriptions.Item>
                </>
              ) : null}
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.notes')} span={2}>
                {detail.notes?.trim() || '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.requirePaymentVoucher')}>
                {detail.requirePaymentVoucher ? t('common.yes') : t('common.no')}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.attachments')} span={2}>
                {Array.isArray(detail.attachments) && detail.attachments.length > 0 ? (
                  <Space wrap size={[8, 4]}>
                    {detail.attachments.map((file, idx) => {
                      const name = String(
                        (file as { name?: string; original_name?: string }).name
                          || (file as { original_name?: string }).original_name
                          || (file as { uid?: string }).uid
                          || idx + 1,
                      );
                      return (
                        <Button
                          key={String((file as { uid?: string }).uid || idx)}
                          type="link"
                          size="small"
                          style={{ padding: 0, height: 'auto' }}
                          onClick={() =>
                            void openDocumentAttachment(
                              file as Parameters<typeof openDocumentAttachment>[0],
                            )
                          }
                        >
                          {name}
                        </Button>
                      );
                    })}
                  </Space>
                ) : (
                  '—'
                )}
              </Descriptions.Item>
            </Descriptions>
            {detail.linkedPayments && detail.linkedPayments.length > 0 ? (
              <Descriptions column={1} size="small" style={{ marginTop: 16 }}>
                <Descriptions.Item label={t('app.kuaizhizao.paymentApplication.linkedPayments')}>
                  <Space wrap size={[8, 4]}>
                    {detail.linkedPayments.map((p) => {
                      const canOpen = canOpenLinkedDocumentDetail('payment');
                      return (
                        <Button
                          key={p.id}
                          type="link"
                          size="small"
                          style={{ padding: 0, height: 'auto' }}
                          onClick={() => {
                            if (!canOpen || !linkedDetail) {
                              messageApi.warning(t('app.kuaizhizao.paymentApplication.linkedPaymentOpenFailed'));
                              return;
                            }
                            const ok = linkedDetail.openLinkedDocumentDetail('payment', p.id);
                            if (!ok) {
                              messageApi.warning(t('app.kuaizhizao.paymentApplication.linkedPaymentOpenFailed'));
                            }
                          }}
                        >
                          {p.code || p.id}
                        </Button>
                      );
                    })}
                  </Space>
                </Descriptions.Item>
              </Descriptions>
            ) : null}
            {detail.purchaseOrderSources && detail.purchaseOrderSources.length > 0 ? (
              <div style={{ marginTop: 16 }}>
                <Typography.Text strong>
                  {t('app.kuaizhizao.paymentApplication.sourcePurchaseOrders')}
                </Typography.Text>
                {detail.purchaseOrderSources.map((po) => (
                  <div key={po.id} style={{ marginTop: 12 }}>
                    <Descriptions size="small" column={3} bordered>
                      <Descriptions.Item label={t('app.kuaizhizao.purchaseOrder.col.code')}>
                        {canOpenLinkedDocumentDetail('purchase_order') ? (
                          <Button
                            type="link"
                            size="small"
                            style={{ padding: 0, height: 'auto' }}
                            onClick={() =>
                              linkedDetail?.openLinkedDocumentDetail('purchase_order', po.id)
                            }
                          >
                            {po.orderCode}
                          </Button>
                        ) : (
                          po.orderCode
                        )}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('app.kuaizhizao.purchaseOrder.form.orderDate')}>
                        {po.orderDate ? formatDateBySiteSetting(po.orderDate) : '—'}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('app.kuaizhizao.purchaseOrder.form.orderType')}>
                        {po.orderType || '—'}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('app.kuaizhizao.purchaseOrder.form.buyer')}>
                        {po.buyerName || '—'}
                      </Descriptions.Item>
                      <Descriptions.Item label={t('app.kuaizhizao.salesOrder.totalAmountLabel')}>
                        {formatCurrencyAmount(po.totalAmount)}
                      </Descriptions.Item>
                    </Descriptions>
                    <Table
                      style={{ marginTop: 8 }}
                      size="small"
                      pagination={false}
                      rowKey="id"
                      dataSource={po.items}
                      columns={[
                        {
                          title: t('app.kuaizhizao.purchaseOrder.col.materialCode'),
                          dataIndex: 'materialCode',
                          width: 110,
                          ellipsis: true,
                        },
                        {
                          title: t('app.kuaizhizao.purchaseOrder.col.materialName'),
                          dataIndex: 'materialName',
                          width: 140,
                          ellipsis: true,
                        },
                        {
                          title: t('app.kuaizhizao.purchaseOrder.col.spec'),
                          dataIndex: 'materialSpec',
                          width: 100,
                          ellipsis: true,
                        },
                        {
                          title: t('common.quantity'),
                          key: 'qty',
                          width: 100,
                          align: 'right',
                          render: (_, row) =>
                            row.quantity ? `${row.quantity}${row.unit ? ` ${row.unit}` : ''}` : '—',
                        },
                        {
                          title: t('app.kuaizhizao.purchaseOrder.col.unitPrice'),
                          key: 'unitPrice',
                          width: 100,
                          align: 'right',
                          render: (_, row) => formatCurrencyAmount(row.unitPrice),
                        },
                        {
                          title: t('app.kuaizhizao.salesOrder.totalAmountLabel'),
                          dataIndex: 'totalPrice',
                          width: 110,
                          align: 'right',
                          render: (v) => formatCurrencyAmount(v),
                        },
                        {
                          title: t('common.remark'),
                          dataIndex: 'notes',
                          ellipsis: true,
                        },
                      ]}
                    />
                  </div>
                ))}
              </div>
            ) : null}
            <DetailDrawerLinesScroll style={{ marginTop: 16 }}>
              <Table
                size="small"
                pagination={false}
                rowKey="id"
                tableLayout="fixed"
                style={{ minWidth: PAYMENT_APPLICATION_DETAIL_LINES_MIN_WIDTH }}
                dataSource={detail.items}
                columns={[
                  {
                    title: t('app.kuaizhizao.paymentApplication.sourceType'),
                    key: 'sourceType',
                    width: PAYMENT_APPLICATION_DETAIL_LINE_WIDTH.sourceType,
                    render: (_, row) => paymentApplicationSourceTypeLabel(t, row.sourceType),
                  },
                  {
                    title: t('app.kuaizhizao.paymentApplication.sourceCode'),
                    key: 'source',
                    width: PAYMENT_APPLICATION_DETAIL_LINE_WIDTH.sourceCode,
                    render: (_, row) => {
                      const st = String(row.sourceType ?? '').trim();
                      const sid = row.sourceId;
                      const code = row.sourceCode || row.payableCode;
                      if (!code && sid == null) return '—';
                      const docType = resolvePaymentApplicationLinkedDocType(st);
                      if (sid != null && canOpenLinkedDocumentDetail(docType)) {
                        return (
                          <Button
                            type="link"
                            size="small"
                            style={{ padding: 0, height: 'auto', whiteSpace: 'nowrap' }}
                            onClick={() =>
                              linkedDetail?.openLinkedDocumentDetail(docType, Number(sid))
                            }
                          >
                            {code || sid}
                          </Button>
                        );
                      }
                      return code || String(sid ?? '—');
                    },
                  },
                  {
                    title: t('app.kuaizhizao.common.colLineMaterials'),
                    key: 'lineMaterials',
                    width: PAYMENT_APPLICATION_DETAIL_LINE_WIDTH.lineMaterials,
                    ellipsis: false,
                    render: (_, row) => {
                      const preview = resolvePaymentApplicationLineMaterialPreview(
                        row,
                        detail.purchaseOrderSources,
                        poLinePreviewByOrderId,
                      );
                      const node = renderDocumentLineMaterialsPreview(preview, t);
                      return preview.length > 0 ? node : '—';
                    },
                  },
                  {
                    title: t('app.kuaizhizao.paymentApplication.quantity'),
                    key: 'quantity',
                    width: PAYMENT_APPLICATION_DETAIL_LINE_WIDTH.quantity,
                    align: 'right',
                    render: (_, row) => {
                      if (row.quantity == null) return '—';
                      const unit = row.materialUnit ? ` ${row.materialUnit}` : '';
                      return `${row.quantity}${unit}`;
                    },
                  },
                  {
                    title: t('app.kuaizhizao.paymentApplication.payableCode'),
                    dataIndex: 'payableCode',
                    width: PAYMENT_APPLICATION_DETAIL_LINE_WIDTH.payableCode,
                    ellipsis: true,
                  },
                  {
                    title: t('app.kuaizhizao.paymentApplication.requestAmount'),
                    dataIndex: 'requestAmount',
                    width: PAYMENT_APPLICATION_DETAIL_LINE_WIDTH.requestAmount,
                    align: 'right',
                    render: (v) => formatCurrencyAmount(v),
                  },
                  {
                    title: t('app.kuaizhizao.paymentApplication.paidAmount'),
                    dataIndex: 'paidAmount',
                    width: PAYMENT_APPLICATION_DETAIL_LINE_WIDTH.paidAmount,
                    align: 'right',
                    render: (v) => formatCurrencyAmount(v),
                  },
                ]}
              />
            </DetailDrawerLinesScroll>
          </>
        ) : null}
      </DetailDrawerTemplate>

      <Modal
        open={pullPayableOpen}
        title={resolveKuaizhizaoDocumentAction(t, 'payment_application.pull_from_payable').label}
        width={720}
        confirmLoading={pullPayableSubmitting}
        onCancel={() => {
          setPullPayableOpen(false);
          setPullPayableSelected([]);
        }}
        onOk={async () => {
          if (!pullPayableSupplierId || pullPayableSelected.length === 0) {
            messageApi.warning(t('common.required'));
            return;
          }
          setPullPayableSubmitting(true);
          try {
            const supplier = supplierOptions.find((s) => s.id === pullPayableSupplierId);
            const items: PaymentApplicationLine[] = pullPayableSelected.map((payableId, index) => {
              const opt = pullPayableRows.find((p) => p.payableId === payableId);
              return {
                sourceType: 'payable',
                sourceId: payableId,
                sourceCode: opt?.payableCode,
                payableId,
                payableCode: opt?.payableCode,
                lineKind: 'goods',
                requestAmount: opt?.maxRequestAmount ?? 0,
                lineNo: index + 1,
              };
            });
            await createPaymentApplication({
              supplierId: pullPayableSupplierId,
              supplierName: supplier?.name,
              items,
            });
            messageApi.success(t('common.createSuccess'));
            setPullPayableOpen(false);
            setPullPayableSelected([]);
            actionRef.current?.reload();
          } catch (e) {
            messageApi.error(getApiErrorMessage(e, t('app.kuaizhizao.paymentApplication.createFailed')));
          } finally {
            setPullPayableSubmitting(false);
          }
        }}
      >
        <Select
          style={{ width: '100%', marginBottom: 12 }}
          placeholder={t('app.kuaizhizao.paymentApplication.supplierName')}
          options={supplierOptions.map((s) => ({ label: s.name, value: s.id }))}
          value={pullPayableSupplierId ?? undefined}
          showSearch
          optionFilterProp="label"
          onChange={async (supplierId: number) => {
            setPullPayableSupplierId(supplierId);
            setPullPayableSelected([]);
            setPullPayableLoading(true);
            try {
              const res = await listPayablesForPaymentApplication(supplierId, { limit: 200 });
              setPullPayableRows(
                (res.data ?? []).map((row) => ({
                  payableId: Number(row.payable_id),
                  payableCode: String(row.payable_code ?? ''),
                  maxRequestAmount: Number(row.max_request_amount ?? 0),
                })),
              );
            } finally {
              setPullPayableLoading(false);
            }
          }}
        />
        <Table
          size="small"
          loading={pullPayableLoading}
          rowKey="payableId"
          pagination={false}
          dataSource={pullPayableRows}
          rowSelection={{
            selectedRowKeys: pullPayableSelected,
            onChange: (keys) => setPullPayableSelected(keys.map((k) => Number(k))),
          }}
          columns={[
            { title: t('app.kuaizhizao.paymentApplication.payableCode'), dataIndex: 'payableCode' },
            {
              title: t('app.kuaizhizao.paymentApplication.requestAmount'),
              dataIndex: 'maxRequestAmount',
              render: (v) => formatCurrencyAmount(v),
            },
          ]}
        />
      </Modal>

      <ModalForm
        key={detail ? `push-payment-${detail.id}` : 'push-payment'}
        title={t('app.kuaizhizao.paymentApplication.pushPayment')}
        open={pushPaymentOpen}
        formRef={pushPaymentFormRef}
        initialValues={{
          payment_method: detail?.paymentMethod || BANK_TRANSFER_PAYMENT_METHOD,
          payment_date: dayjs(),
          notes: detail
            ? t('app.kuaizhizao.paymentApplication.pushPaymentDefaultNotes', {
                code: detail.applicationCode,
              })
            : undefined,
        }}
        modalProps={{
          destroyOnHidden: true,
          confirmLoading: pushPaymentSubmitting,
          mask: { closable: !pushPaymentSubmitting },
        }}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        grid
        onOpenChange={setPushPaymentOpen}
        onFinish={async (values) => {
          if (!detail) return false;
          try {
            assertBankAccountForPaymentMethod(
              values.payment_method as string,
              values.bank_account_id,
              t,
            );
          } catch (e) {
            messageApi.warning((e as Error).message);
            return false;
          }
          setPushPaymentSubmitting(true);
          try {
            const res = await pushPaymentApplicationToPayment(detail.id, {
              paymentMethod: values.payment_method,
              bankAccountId: values.bank_account_id,
              paymentDate: toApiDateString(values.payment_date),
              notes: values.notes,
            });
            messageApi.success(
              t('app.kuaizhizao.paymentApplication.pushPaymentSuccess', {
                code: String(res.payment_code ?? ''),
              }),
            );
            const full = await getPaymentApplication(detail.id);
            setDetail(full);
            actionRef.current?.reload();
            return true;
          } catch (e) {
            messageApi.error(
              getApiErrorMessage(e, t('app.kuaizhizao.paymentApplication.pushPaymentFailed')),
            );
            return false;
          } finally {
            setPushPaymentSubmitting(false);
          }
        }}
      >
        <ProFormSelect
          name="payment_method"
          label={t('app.kuaizhizao.paymentApplication.paymentMethod')}
          rules={[{ required: true }]}
          options={paymentMethodOptions}
          colProps={{ span: 12 }}
        />
        <ProFormDatePicker
          name="payment_date"
          label={t('app.kuaizhizao.paymentApplication.paymentDate')}
          rules={[{ required: true }]}
          fieldProps={{ style: { width: '100%' } }}
          colProps={{ span: 12 }}
        />
        <LedgerAccountFormFields
          accounts={bankAccounts}
          accountLabel={t('app.kuaicaiwu.payment.outBankAccount')}
          noteLabel={t('app.kuaicaiwu.payment.outAccountNote')}
        />
        <ProFormTextArea
          name="notes"
          label={t('app.kuaizhizao.paymentApplication.notes')}
          fieldProps={{ rows: 2 }}
          colProps={{ span: 24 }}
        />
      </ModalForm>

      {renderPullModals()}
      {PrintModal}
    </>
  );
};

export default PaymentApplicationsPage;
