/**
 * 采购询价单
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { rowActionKind } from '../../../../../components/uni-action';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ActionType, ProColumns, ProDescriptionsItemProps, ProForm, ProFormDatePicker, ProFormDigit, ProFormSelect, ProFormText, ProFormTextArea } from '@ant-design/pro-components';
import { App, Button, Checkbox, Col, DatePicker, Descriptions, Empty, Form, Input, InputNumber, Modal, Row, Select, Space, Spin, Switch, Table, Tag, Tooltip, Typography, Alert } from 'antd';
import { ArrowLeftOutlined, CheckOutlined, EditOutlined, FormOutlined, PlusOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { DictionarySelect } from '../../../../../components/dictionary-select';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import {
  getChineseInvoiceTypeOptions,
  getPaymentMethodOptions,
} from '../../../../kuaicaiwu/utils/financeSharedOptions';
import { searchUserDisplay, type User } from '../../../../../services/user';
import { displayItemsToUsers, normalizeUserDisplayName } from '../../../../../utils/userDisplay';
import {
  listPurchaseDemandParties,
  type PurchaseDemandParty,
} from '../../../services/purchase-demand-party';
import { PurchaseDemandPartiesPanel } from '../purchase-demand-parties';
import { UniTable, readPersistedUniTableViewType } from '../../../../../components/uni-table';
import {
  UniBatchMenuButton,
  defaultAuditBatchAllowed,
  pickCapability,
  runCapabilityBatchLoop,
  useAuditBatchRunner,
  withDocumentSubmitCombinedItem,
  type AuditBatchAction,
  type UniBatchMenuItem,
} from '../../../../../components/uni-batch';
import {
  UniTableStackedPrimaryCell,
  UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
  MaterialStackedCell,
} from '../../../../../components/uni-table/stackedPrimaryColumn';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../../sales-management/shared/documentLineMaterialsPreview';
import {
  ListPageTemplate,
  DetailDrawerTemplate,
  DetailDrawerSection,
  DRAWER_CONFIG,
  FORM_LAYOUT,
  MODAL_CONFIG,
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageHeaderActions,
  DocumentFormPageLayout,
  useDetailDrawerDescriptionItems,
} from '../../../../../components/layout-templates';
import { useLeaveFormTab } from '../../../../../components/uni-tabs/navigateClosingTab';
import { useSubmitShortcut } from '../../../../../hooks/useSubmitShortcut';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { SourceDocumentCode } from '../../../../../components/linked-document-code/SourceDocumentCode';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { buildUniPushMenuItems, buildUniPushToolbarDisabledReason, UniPushToolbarButton } from '../../../../../components/uni-push';
import {
  UniPullQueryModal,
  isPullOpenLineSelectable,
  isPullRequisitionOpenLineSelectable,
  isPullableScope,
  renderPullCapabilityTag,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import { buildKuaizhizaoPullCreateMenuItems, resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import {
  PurchaseDepartmentFormField,
  resolvePurchaseDepartmentPayload,
  usePurchaseDepartmentOptions,
} from '../shared/PurchaseDepartmentFormField';
import { PurchaseSupplierContactPickInput } from '../shared/PurchaseSupplierContactFormFields';
import {
  resolveFullSupplierFromList,
  type SupplierLike,
} from '../shared/applySupplierFormFields';
import { buildSupplierContactPickOptions } from '../shared/partnerSupplierFormSnapshot';
import {
  handoffInquiryToPurchaseOrderCreate,
  handoffRequisitionToPurchaseInquiryCreate,
} from '../../../utils/documentFlowHandoff';
import {
  buildDocumentCreateDraftKey,
  clearDocumentFormDraft,
  getDocumentFormDraft,
} from '../../../../../utils/documentFormDraftCache';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import { DocumentTrackingTimelineBody, useDocumentTracking } from '../../../../../components/document-tracking-panel';
import { LIST_LIFECYCLE_STAGE_FIELD } from '../../../../../utils/listLifecycleStage';
import { buildFutureDateShortcutFieldProps, FutureDatePicker } from '../../../../../utils/futureDatePickerShortcuts';
import { ListUniLifecycleCell } from '../../sales-management/shared/ListUniLifecycleCell';
import { createListAuditPhaseColumn } from '../../sales-management/shared/listAuditPhaseColumn';
import {
  alignProColumns,
  alignDescriptionColumns,
  GLOBAL_DOC_DETAIL_TABLE_FIELD_RANK,
  SALES_DOC_LIST_FIELD_RANK,
} from '../../sales-management/shared/documentFieldAlignment';
import { DocumentPushProgressBar, DOCUMENT_PROGRESS_COLUMN_DEFAULTS, DETAIL_TABLE_PROGRESS_COLUMN_DEFAULTS } from '../../sales-management/shared/DocumentPushProgressBar';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import { flattenDocumentDetailRows, resolveDetailTableViewMode } from '../../shared/detailTableFlatRows';
import { useNumericPrecision } from '../../../../../hooks/useNumericPrecision';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { isPendingReviewStatus } from '../../../constants/documentStatus';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import {
  approvePurchaseInquiry,
  awardInquiryQuotes,
  closeInquiryQuoting,
  createPurchaseInquiry,
  deletePurchaseInquiry,
  getInquiryComparison,
  getPurchaseInquiry,
  listPurchaseInquiries,
  previewPushInquiryToPurchaseOrder,
  publishPurchaseInquiry,
  submitPurchaseInquiry,
  submitPurchaseInquiryForReview,
  updatePurchaseInquiry,
  upsertSupplierQuote,
  withdrawPurchaseInquirySubmit,
  withdrawPurchaseInquiryApproval,
  type ComparisonRow,
  type PurchaseInquiry,
  type PurchaseInquiryItem,
  type PurchaseInquiryVendor,
} from '../../../services/purchase-inquiry';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import { buildDocumentAttachmentsListColumn } from '../../../components/documentAttachmentsListColumn';
import {
  appendDocumentAttachmentsToSupplementary,
  documentAttachmentsFromRecord,
  hasDocumentAttachments,
} from '../../../components/DocumentAttachmentsReadonly';
import { DocumentApprovalRecordsPane } from '../../../components/DocumentApprovalRecordsPane';
import {
  isSystemDocumentAttachment,
  mapAttachmentsToUploadList,
  normalizeDocumentAttachments,
  resolveDocumentAttachmentFileUuid,
  type DocumentAttachmentFile,
} from '../../../utils/documentAttachments';
import {
  buildPurchaseInquiryLifecycleValueEnum,
  getPurchaseInquiryLifecycle,
  isInquiryDraft,
  isInquiryPendingCompare,
  isInquiryQuoting,
  isInquiryAwarded,
  resolvePurchaseInquiryListApiParams,
} from '../../../utils/purchaseInquiryLifecycle';
import {
  listPurchaseRequisitions,
  listPurchaseRequisitionPurchaseInquiryPullLines,
  type PurchaseRequisitionPullLine,
  type DocumentPushPreview,
} from '../../../services/purchase-requisition';
import {
  KUAIZHIZAO_DOC_HOST,
  loadSupplierFormReferenceList,
} from '../../../../../utils/documentFormReferenceLoad';
import { formatBusinessDateOnly, formatDateTime, formatDateBySiteSetting, formatNumber, formatQuantity, formatCurrencyAmount, formatPrice } from '../../../../../utils/format';
import { QuantityWithUnitDisplay } from '../../../../../components/quantity-with-unit';
import { extractProTableSort } from '../../../../../utils/tableQueryKey';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import {
  purchaseInquiryCapabilityReasonMessage,
} from '../../../../../hooks/useDocumentCapabilities';

type PullPurchaseRequisitionCandidate = PurchaseRequisitionPullLine;

const PURCHASE_INQUIRY_RESOURCE = 'kuaizhizao:purchase-inquiry';

type PurchaseInquiryItemRow = PurchaseInquiryItem & {
  _rowKey: string;
  inquiry_id: number;
  inquiry_code?: string;
  inquiry_name?: string;
  source_code?: string;
  buyer_name?: string;
  quote_deadline?: string;
  status?: string;
  review_status?: string;
};

const PURCHASE_INQUIRY_LIST_PERSISTENCE_ID =
  'apps.kuaizhizao.pages.purchase-management.purchase-inquiries-width-v1';
const PURCHASE_INQUIRY_LIST_PATH = '/apps/kuaizhizao/purchase-management/purchase-inquiries';
const PURCHASE_INQUIRY_CREATE_PATH = `${PURCHASE_INQUIRY_LIST_PATH}/new`;
const purchaseInquiryEditPath = (id: number) => `${PURCHASE_INQUIRY_LIST_PATH}/${id}/edit`;

const PurchaseInquiriesPage: React.FC = () => {
  const { t } = useTranslation();
  const { quantity: quantityDecimals, price: priceDecimals } = useNumericPrecision();
  const { message, modal } = App.useApp();
  const navigate = useNavigate();
  const location = useLocation();
  const isCreatePage = location.pathname.endsWith('/purchase-inquiries/new');
  const editRouteMatch = location.pathname.match(/\/purchase-inquiries\/(\d+)\/edit$/);
  const editRouteId = editRouteMatch ? Number(editRouteMatch[1]) : null;
  const isEditPage = editRouteId != null && Number.isFinite(editRouteId) && editRouteId > 0;
  const isFormPage = isCreatePage || isEditPage;
  const leavePurchaseInquiryFormPage = useLeaveFormTab(PURCHASE_INQUIRY_LIST_PATH);
  const formPageInitKeyRef = useRef<string | null>(null);
  const [formPageLoading, setFormPageLoading] = useState(false);
  const pendingEditFormValuesRef = useRef<Record<string, unknown> | null>(null);
  const inquiryFormDraftKey = useMemo(
    () =>
      isFormPage
        ? buildDocumentCreateDraftKey('kuaizhizao:purchase-inquiry', location.pathname, location.search)
        : null,
    [isFormPage, location.pathname, location.search],
  );
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    options: departmentOptions,
    loading: departmentOptionsLoading,
    resolveName: resolveDepartmentName,
  } = usePurchaseDepartmentOptions();
  const actionRef = useRef<ActionType>();
  const documentFlowSubmitExtrasRef = useRef<Record<string, unknown> | null>(null);
  const handoffFlowConsumedRef = useRef<string | null>(null);
  const tableRowsRef = useRef<PurchaseInquiry[]>([]);
  const [viewTypeState, setViewTypeState] = useState<'table' | 'detailTable' | 'help'>(() =>
    readPersistedUniTableViewType(PURCHASE_INQUIRY_LIST_PERSISTENCE_ID, 'table', [
      'table',
      'detailTable',
      'help',
    ]) as 'table' | 'detailTable' | 'help',
  );
  const dataViewMode = resolveDetailTableViewMode(viewTypeState);
  const dataViewModeRef = useRef(dataViewMode);
  useEffect(() => {
    dataViewModeRef.current = dataViewMode;
  }, [dataViewMode]);
  const auditEnabled = useAuditRequired('purchase_inquiry', false);
  const purchaseInquiryPerms = useResourcePermissions(PURCHASE_INQUIRY_RESOURCE);
  const demandPartyPerms = useResourcePermissions('kuaizhizao:purchase-demand-party');
  const pullFromRequisitionAction = resolveKuaizhizaoDocumentAction(t, 'purchase_inquiry.pull_from_requisition');
  const pushToPurchaseOrderAction = resolveKuaizhizaoDocumentAction(t, 'purchase_order.pull_from_inquiry');

  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<PurchaseInquiry | null>(null);
  const [inquiryTrackingRefreshKey, setInquiryTrackingRefreshKey] = useState(0);
  const [editForm] = Form.useForm();
  const [editItems, setEditItems] = useState<PurchaseInquiryItem[]>([]);
  const [editVendors, setEditVendors] = useState<PurchaseInquiryVendor[]>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingReviewStatus, setEditingReviewStatus] = useState<string | null>(null);
  const commitAfterSaveRef = useRef(false);
  const [inquiryFormBusy, setInquiryFormBusy] = useState(false);
  const [quoteOpen, setQuoteOpen] = useState(false);
  const [quoteForm] = Form.useForm();
  const [pendingQuoteFormValues, setPendingQuoteFormValues] = useState<Record<string, unknown> | null>(null);
  const [quoteSupplierId, setQuoteSupplierId] = useState<number | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareInquiryId, setCompareInquiryId] = useState<number | null>(null);
  const [compareRows, setCompareRows] = useState<ComparisonRow[]>([]);
  const [awardSelection, setAwardSelection] = useState<Record<number, number>>({});
  const [supplierOptions, setSupplierOptions] = useState<SupplierLike[]>([]);
  const [demandPartyOptions, setDemandPartyOptions] = useState<PurchaseDemandParty[]>([]);
  const [demandPartyOpen, setDemandPartyOpen] = useState(false);
  const [userList, setUserList] = useState<User[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const editFormRef = useRef(editForm);
  editFormRef.current = editForm;
  const paymentMethodOptions = useMemo(() => getPaymentMethodOptions(t), [t]);
  const invoiceTypeOptions = useMemo(() => getChineseInvoiceTypeOptions(t, { includeOther: true }), [t]);
  const taxRatePercentOptions = useMemo(
    () => [0, 1, 3, 6, 9, 13].map((n) => ({ label: `${n}%`, value: n })),
    [],
  );

  const pullSourceRequisitionIdRef = useRef<number | undefined>(undefined);
  const [pullSourceRequisitionId, setPullSourceRequisitionId] = useState<number | undefined>();
  const [pullSourceRequisitionOptions, setPullSourceRequisitionOptions] = useState<Array<{ value: number; label: string }>>([]);

  const [pushPoPreviewOpen, setPushPoPreviewOpen] = useState(false);
  const [pushPoPreviewLoading, setPushPoPreviewLoading] = useState(false);
  const [pushPoPreviewConfirming, setPushPoPreviewConfirming] = useState(false);
  const [pushPoPreviewData, setPushPoPreviewData] = useState<DocumentPushPreview | null>(null);
  const [pushPoTarget, setPushPoTarget] = useState<PurchaseInquiry | null>(null);
  const [pushPoSelectedItemIds, setPushPoSelectedItemIds] = useState<number[]>([]);

  const selectedInquiriesForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
        .filter((row): row is PurchaseInquiry => row != null),
    [selectedRowKeys],
  );

  const purchaseInquiryAuditBatchHandlers = useMemo(
    () => ({
      submit: (id: number) => submitPurchaseInquiry(id),
      withdraw: (id: number) => withdrawPurchaseInquirySubmit(id),
      approve: (id: number) => approvePurchaseInquiry(id, true),
      revoke: (id: number) => withdrawPurchaseInquiryApproval(id),
    }),
    [],
  );

  const handlePurchaseInquiryAuditBatchSuccess = useCallback(() => {
    setSelectedRowKeys([]);
    actionRef.current?.reload();
  }, []);

  const {
    runAction: runPurchaseInquiryAuditBatch,
    auditModal: purchaseInquiryAuditModal,
  } = useAuditBatchRunner<PurchaseInquiry>({
    permGates: purchaseInquiryPerms,
    handlers: purchaseInquiryAuditBatchHandlers,
    onBatchComplete: handlePurchaseInquiryAuditBatchSuccess,
    auditEntity: {
      entityType: 'purchase_inquiry',
      entityName: t('app.kuaizhizao.purchaseInquiry.entityName'),
    },
  });

  const purchaseInquiryToolbarAuditMenus = useMemo(() => {
    const canPerm = (action: AuditBatchAction) => {
      const perm = action === 'approve' ? 'audit' : action === 'submit' ? 'submit' : 'revoke';
      return purchaseInquiryPerms.canAction?.(perm) ?? false;
    };
    const item = (
      key: string,
      action: AuditBatchAction,
      label: string,
      capKey: string,
      rows: PurchaseInquiry[],
    ): UniBatchMenuItem => ({
      key,
      label,
      disabled:
        selectedInquiriesForBatch.length > 0
        && !defaultAuditBatchAllowed(rows, canPerm(action), capKey, (row) => row),
      onClick: (keys) => {
        const idSet = new Set(rows.map((row) => String(row.id)));
        return runPurchaseInquiryAuditBatch(
          action,
          keys.filter((rowKey) => idSet.has(String(rowKey))),
          rows,
          auditEnabled,
        );
      },
    });
    const capOn = (row: PurchaseInquiry, capKey: string) => pickCapability(row, capKey)?.allowed === true;
    const submittedRows = selectedInquiriesForBatch.filter(
      (row) => String(row.review_status || '').trim() === 'SUBMITTED' && capOn(row, 'withdraw_submit'),
    );
    const pendingRows = selectedInquiriesForBatch.filter((row) => {
      const review = String(row.review_status || '').trim();
      return review !== 'SUBMITTED' && isPendingReviewStatus(review) && capOn(row, 'withdraw_submit');
    });
    const submitReviewRows = selectedInquiriesForBatch.filter((row) =>
      (row.audit?.allowed_actions ?? []).includes('submit_review'),
    );
    const canSubmitReview = purchaseInquiryPerms.canAction?.('submit') ?? false;
    const submitRows = selectedInquiriesForBatch.filter((row) => capOn(row, 'submit'));
    const submitMenuItem = item('submit', 'submit', t('common.submit'), 'submit', submitRows);
    const submitDisabled = Boolean(submitMenuItem.disabled);
    return {
      submit: withDocumentSubmitCombinedItem(
        [
          submitMenuItem,
          item('withdraw-submit', 'withdraw', t('app.kuaizhizao.purchaseInquiry.toolbar.withdrawSubmit'), 'withdraw_submit', submittedRows),
          {
            key: 'submit-review',
            label: t('app.kuaizhizao.purchaseInquiry.toolbar.submitReview'),
            disabled: selectedInquiriesForBatch.length > 0 && !(canSubmitReview && submitReviewRows.length > 0),
            onClick: (keys: React.Key[]) => runCapabilityBatchLoop({
              keys,
              records: submitReviewRows,
              capabilityKey: 'submit_review',
              permAllowed: canSubmitReview,
              notAllowedMessage: t('app.kuaizhizao.purchaseInquiry.toolbar.submitReviewNotAllowed'),
              onRun: (id) => submitPurchaseInquiryForReview(id),
              message,
              t,
              onSuccess: handlePurchaseInquiryAuditBatchSuccess,
            }),
          },
        ],
        {
          t,
          message,
          disabled: submitDisabled,
          commitRecords: submitRows,
          permAllowed: canSubmitReview,
          commit: (id) => submitPurchaseInquiry(id),
          submitReview: (id) => submitPurchaseInquiryForReview(id),
          onSuccess: handlePurchaseInquiryAuditBatchSuccess,
        },
      ),
      audit: [
        item('approve', 'approve', t('components.uniAction.audit'), 'approve', selectedInquiriesForBatch.filter((row) => capOn(row, 'approve'))),
        item('withdraw-review', 'withdraw', t('app.kuaizhizao.purchaseInquiry.toolbar.withdrawReview'), 'withdraw_submit', pendingRows),
        item('revoke', 'revoke', t('app.kuaizhizao.purchaseInquiry.toolbar.revoke'), 'revoke_approval', selectedInquiriesForBatch.filter((row) => capOn(row, 'revoke_approval'))),
      ] satisfies UniBatchMenuItem[],
    };
  }, [
    auditEnabled,
    handlePurchaseInquiryAuditBatchSuccess,
    message,
    purchaseInquiryPerms,
    runPurchaseInquiryAuditBatch,
    selectedInquiriesForBatch,
    t,
  ]);

  const [addVendorModalOpen, setAddVendorModalOpen] = useState(false);
  const [selectedSupplierIdsForAdd, setSelectedSupplierIdsForAdd] = useState<number[]>([]);

  const availableSuppliersForAdd = useMemo(
    () => supplierOptions.filter((s) => !editVendors.some((v) => v.supplier_id === Number(s.id))),
    [supplierOptions, editVendors],
  );

  useEffect(() => {
    void loadSupplierFormReferenceList(KUAIZHIZAO_DOC_HOST.purchaseInquiry).then((list) =>
      setSupplierOptions(list.map((s) => ({ id: s.id!, name: s.name ?? '', code: s.code }))),
    );
    void listPurchaseDemandParties({ is_active: true, limit: 500 }).then((res) => {
      setDemandPartyOptions(res.data ?? []);
    }).catch(() => setDemandPartyOptions([]));
    const loadUsers = async () => {
      setUsersLoading(true);
      try {
        const res = await searchUserDisplay({ page_size: 200, is_active: true });
        setUserList(displayItemsToUsers(res.items || []));
      } catch {
        setUserList([]);
      } finally {
        setUsersLoading(false);
      }
    };
    void loadUsers();
  }, []);

  const openDetail = async (record: PurchaseInquiry) => {
    const full = await getPurchaseInquiry(record.id!);
    setDetail(full);
    setDetailOpen(true);
  };

  const hydratePurchaseInquiryEditForm = useCallback(
    (full: PurchaseInquiry) => {
      setEditingId(full.id!);
      setEditingReviewStatus(full.review_status ?? null);
      setEditItems(full.items ?? []);
      setEditVendors(full.vendors ?? []);
      const taxRatePercent =
        full.tax_rate != null && full.tax_rate !== undefined
          ? Number(full.tax_rate) * 100
          : undefined;
      editForm.setFieldsValue({
        inquiry_name: full.inquiry_name,
        inquiry_date: full.inquiry_date ? dayjs(full.inquiry_date) : undefined,
        quote_deadline: full.quote_deadline ? dayjs(full.quote_deadline) : undefined,
        demand_party_id: full.demand_party_id,
        demand_party_name: full.demand_party_name,
        buyer_id: full.buyer_id,
        buyer_name: full.buyer_name,
        buyer_phone: full.buyer_phone,
        department_id: full.department_id ?? undefined,
        department_name: full.department_name ?? undefined,
        currency: full.currency || 'CNY',
        exchange_rate: full.exchange_rate ?? 1,
        invoice_type: full.invoice_type,
        tax_rate_percent: taxRatePercent,
        payment_method: full.payment_method,
        payment_terms: full.payment_terms,
        trade_mode: full.trade_mode,
        notes: full.notes,
        attachments: mapAttachmentsToUploadList(full.attachments),
        __inquiry_edit_item: (full.items ?? []).map((item) => ({ material_id: item.material_id })),
      });
    },
    [editForm],
  );

  const loadPurchaseInquiryEditForm = useCallback(
    async (id: number) => {
      setFormPageLoading(true);
      try {
        const full = await getPurchaseInquiry(id);
        hydratePurchaseInquiryEditForm(full);
      } catch (error: unknown) {
        message.error(getApiErrorMessage(error, t('common.loadFailed')));
        leavePurchaseInquiryFormPage();
      } finally {
        setFormPageLoading(false);
      }
    },
    [hydratePurchaseInquiryEditForm, leavePurchaseInquiryFormPage, message, t],
  );

  const openEdit = (record: PurchaseInquiry) => {
    if (record.id) navigate(purchaseInquiryEditPath(record.id));
  };

  const handleSaveEdit = async () => {
    const shouldCommit = commitAfterSaveRef.current;
    commitAfterSaveRef.current = false;
    let values: Awaited<ReturnType<typeof editForm.validateFields>>;
    try {
      values = await editForm.validateFields();
    } catch {
      return;
    }
    setInquiryFormBusy(true);
    try {
    const taxRatePercent = Number(values.tax_rate_percent);
    const payload = {
      inquiry_name: values.inquiry_name,
      inquiry_date: values.inquiry_date?.format('YYYY-MM-DD'),
      quote_deadline: values.quote_deadline?.format('YYYY-MM-DD'),
      demand_party_id: values.demand_party_id,
      demand_party_name: values.demand_party_name,
      buyer_id: values.buyer_id,
      buyer_name: values.buyer_name,
      buyer_phone: values.buyer_phone,
      ...resolvePurchaseDepartmentPayload(
        values.department_id,
        resolveDepartmentName,
        values.department_name,
      ),
      currency: values.currency || 'CNY',
      exchange_rate: values.exchange_rate ?? 1,
      invoice_type: values.invoice_type,
      tax_rate: Number.isFinite(taxRatePercent) ? taxRatePercent / 100 : 0,
      payment_method: values.payment_method,
      payment_terms: values.payment_terms,
      trade_mode: values.trade_mode,
      notes: values.notes,
      attachments: normalizeDocumentAttachments(values.attachments),
      items: editItems.map((item) => ({
        material_id: item.material_id!,
        material_code: item.material_code!,
        material_name: item.material_name!,
        material_spec: item.material_spec,
        unit: item.unit ?? '件',
        quantity: item.quantity!,
        required_date: item.required_date,
        source_requisition_item_id: item.source_requisition_item_id,
        notes: item.notes,
      })),
      vendors: editVendors.map((v) => ({
        supplier_id: v.supplier_id!,
        supplier_name: v.supplier_name!,
        contact_name: v.contact_name,
        contact_phone: v.contact_phone,
        contact_email: v.contact_email,
        email_notify: Boolean(v.email_notify),
        notes: v.notes,
      })),
    };
    let savedId = editingId ?? undefined;
    if (editingId) {
      await updatePurchaseInquiry(editingId, payload);
      if (!shouldCommit) {
        message.success(t('common.updateSuccess'));
      }
    } else {
      const flowExtras = documentFlowSubmitExtrasRef.current;
      const createPayload = flowExtras ? { ...payload, ...flowExtras } : payload;
      const doc = await createPurchaseInquiry(createPayload);
      savedId = doc.id;
      if (flowExtras) {
        documentFlowSubmitExtrasRef.current = null;
      }
      if (!shouldCommit) {
        message.success(t('app.kuaizhizao.purchaseInquiry.created', { code: doc.inquiry_code }));
      }
    }
    if (shouldCommit && savedId) {
      try {
        await submitPurchaseInquiry(savedId);
        message.success(t('app.kuaizhizao.purchaseInquiry.committed'));
      } catch (submitError: unknown) {
        setEditingId(savedId);
        message.error(getApiErrorMessage(submitError, t('common.operationFailed')));
        actionRef.current?.reload();
        return;
      }
    }
    leavePurchaseInquiryFormPage();
    pendingEditFormValuesRef.current = null;
    actionRef.current?.reload();
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, t('common.saveFailed')));
    } finally {
      setInquiryFormBusy(false);
    }
  };

  const handleCreate = () => {
    pendingEditFormValuesRef.current = null;
    documentFlowSubmitExtrasRef.current = null;
    navigate(PURCHASE_INQUIRY_CREATE_PATH);
  };

  const initPurchaseInquiryCreateForm = useCallback(() => {
    setEditingId(null);
    setEditingReviewStatus(null);
    editForm.resetFields();
    const sp = new URLSearchParams(location.search || '');
    if (sp.get('flow') === 'purchase_requisition' && inquiryFormDraftKey) {
      const flowKey = `${location.pathname}?flow=purchase_requisition`;
      if (handoffFlowConsumedRef.current !== flowKey) {
        const handoffDraft = getDocumentFormDraft<Record<string, unknown>>(inquiryFormDraftKey);
        if (handoffDraft) {
          handoffFlowConsumedRef.current = flowKey;
          const {
            _documentFlowMeta: _meta,
            documentFlowSourceType,
            documentFlowRequisitionItemIds,
            items: draftItems,
            vendors: draftVendors,
            inquiry_name: draftInquiryName,
            inquiry_date: draftInquiryDate,
            quote_deadline: draftQuoteDeadline,
            notes: draftNotes,
            ...rest
          } = handoffDraft;
          void rest;
          documentFlowSubmitExtrasRef.current = {
            documentFlowSourceType,
            documentFlowRequisitionItemIds,
          };
          const items = Array.isArray(draftItems) ? (draftItems as PurchaseInquiryItem[]) : [];
          const vendors = Array.isArray(draftVendors) ? (draftVendors as PurchaseInquiryVendor[]) : [];
          setEditItems(items);
          setEditVendors(vendors);
          editForm.setFieldsValue({
            inquiry_name: draftInquiryName,
            inquiry_date: draftInquiryDate ? dayjs(draftInquiryDate as string) : dayjs(),
            quote_deadline: draftQuoteDeadline ? dayjs(draftQuoteDeadline as string) : undefined,
            notes: draftNotes,
            attachments: [],
            __inquiry_edit_item: items.map((item) => ({ material_id: item.material_id })),
          });
          clearDocumentFormDraft(inquiryFormDraftKey);
          navigate(location.pathname, { replace: true });
          return;
        }
      }
    }
    const pending = pendingEditFormValuesRef.current;
    if (pending) {
      setEditItems((pending.__editItems as PurchaseInquiryItem[]) ?? []);
      setEditVendors((pending.__editVendors as PurchaseInquiryVendor[]) ?? []);
      const { __editItems: _i, __editVendors: _v, ...formValues } = pending;
      void _i;
      void _v;
      editForm.setFieldsValue(formValues);
      pendingEditFormValuesRef.current = null;
      return;
    }
    setEditItems([]);
    setEditVendors([]);
    editForm.setFieldsValue({
      inquiry_date: dayjs(),
      currency: 'CNY',
      exchange_rate: 1,
      tax_rate_percent: 13,
      invoice_type: '增值税专用发票',
      attachments: [],
      __inquiry_edit_item: [],
    });
  }, [editForm, inquiryFormDraftKey, location.pathname, location.search, navigate]);

  useEffect(() => {
    if (!isFormPage) {
      formPageInitKeyRef.current = null;
      return;
    }
    const initKey = isCreatePage ? `create-${location.search}` : `edit-${editRouteId}`;
    if (formPageInitKeyRef.current === initKey) return;
    formPageInitKeyRef.current = initKey;
    if (isCreatePage) {
      initPurchaseInquiryCreateForm();
    } else if (editRouteId != null) {
      void loadPurchaseInquiryEditForm(editRouteId);
    }
  }, [
    editRouteId,
    initPurchaseInquiryCreateForm,
    isCreatePage,
    isFormPage,
    loadPurchaseInquiryEditForm,
    location.search,
  ]);

  const openQuoteEntry = (inquiry: PurchaseInquiry, supplierId: number) => {
    setQuoteSupplierId(supplierId);
    const existing = inquiry.quotes?.find((q) => q.supplier_id === supplierId);
    quoteForm.resetFields();
    const initial: Record<string, unknown> = {
      quote_date: existing?.quote_date ? dayjs(existing.quote_date) : dayjs(),
      valid_until: existing?.valid_until ? dayjs(existing.valid_until) : undefined,
      notes: existing?.notes,
    };
    (inquiry.items ?? []).forEach((item) => {
      const line = existing?.items?.find((i) => i.inquiry_item_id === item.id);
      initial[`qty_${item.id}`] = line?.quoted_quantity ?? item.quantity;
      initial[`price_${item.id}`] = line?.unit_price ?? 0;
      initial[`date_${item.id}`] = line?.delivery_date ? dayjs(line.delivery_date) : item.required_date ? dayjs(item.required_date) : undefined;
    });
    setPendingQuoteFormValues(initial);
    setQuoteOpen(true);
  };

  const saveQuote = async () => {
    if (!detail?.id || !quoteSupplierId) return;
    const values = await quoteForm.validateFields();
    const vendor = detail.vendors?.find((v) => v.supplier_id === quoteSupplierId);
    await upsertSupplierQuote(detail.id, {
      supplier_id: quoteSupplierId,
      supplier_name: vendor?.supplier_name,
      quote_date: values.quote_date?.format('YYYY-MM-DD'),
      valid_until: values.valid_until?.format('YYYY-MM-DD'),
      notes: values.notes,
      items: (detail.items ?? []).map((item) => ({
        inquiry_item_id: item.id!,
        quoted_quantity: values[`qty_${item.id}`],
        unit_price: values[`price_${item.id}`],
        delivery_date: values[`date_${item.id}`]?.format('YYYY-MM-DD'),
      })),
    });
    message.success(t('app.kuaizhizao.purchaseInquiry.quoteSaved'));
    setQuoteOpen(false);
    setDetail(await getPurchaseInquiry(detail.id));
    actionRef.current?.reload();
  };

  const openCompare = async (inquiry: PurchaseInquiry) => {
    const inquiryId = inquiry.id;
    if (!inquiryId) {
      message.warning(t('app.kuaizhizao.purchaseInquiry.compareAwardMissingInquiry'));
      return;
    }
    const matrix = await getInquiryComparison(inquiryId);
    setCompareInquiryId(inquiryId);
    setCompareRows(matrix.rows);
    const init: Record<number, number> = {};
    matrix.rows.forEach((row) => {
      const awarded = row.cells.find((c) => c.is_awarded && c.quote_item_id);
      if (awarded?.quote_item_id) init[row.inquiry_item_id] = awarded.quote_item_id;
      else {
        const lowest = row.cells.find((c) => c.is_lowest_price && c.quote_item_id);
        if (lowest?.quote_item_id) init[row.inquiry_item_id] = lowest.quote_item_id;
      }
    });
    setAwardSelection(init);
    setCompareOpen(true);
  };

  const confirmAward = async () => {
    if (!compareInquiryId) {
      message.warning(t('app.kuaizhizao.purchaseInquiry.compareAwardMissingInquiry'));
      return;
    }
    const rowCount = compareRows.length;
    const hasSelectableQuote = compareRows.some((row) =>
      row.cells.some((cell) => cell.quote_item_id),
    );
    if (!rowCount || !hasSelectableQuote) {
      message.warning(t('app.kuaizhizao.purchaseInquiry.selectAwardQuoteNoQuote'));
      return;
    }
    const awards = Object.entries(awardSelection)
      .filter(([inquiryItemId, quoteItemId]) => {
        if (!quoteItemId) return false;
        const row = compareRows.find((r) => r.inquiry_item_id === Number(inquiryItemId));
        return row?.cells.some((cell) => cell.quote_item_id);
      })
      .map(([inquiryItemId, quoteItemId]) => ({
        inquiry_item_id: Number(inquiryItemId),
        quote_item_id: Number(quoteItemId),
      }));
    if (!awards.length) {
      message.warning(t('app.kuaizhizao.purchaseInquiry.selectAwardQuote'));
      return;
    }
    try {
      await awardInquiryQuotes(compareInquiryId, awards);
      message.success(
        awards.length < rowCount
          ? t('app.kuaizhizao.purchaseInquiry.awardSuccessPartial', { selected: awards.length })
          : t('app.kuaizhizao.purchaseInquiry.awardSuccess'),
      );
      setCompareOpen(false);
      setCompareInquiryId(null);
      if (detail?.id === compareInquiryId) {
        setDetail(await getPurchaseInquiry(compareInquiryId));
      }
      actionRef.current?.reload();
    } catch (error: unknown) {
      const err = error as { message?: string; response?: { data?: { detail?: string } } };
      message.error(
        err?.response?.data?.detail || err?.message || t('app.kuaizhizao.purchaseInquiry.awardFailed'),
      );
    }
  };

  const pullDocumentScopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const pullFromRequisitionQuery = useUniPullQuery<PullPurchaseRequisitionCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullDocumentScopeOptions,
    defaultScope: 'pullable',
    onOpen: () => {
      pullSourceRequisitionIdRef.current = undefined;
      setPullSourceRequisitionId(undefined);
      void listPurchaseRequisitions({ skip: 0, limit: 100 })
        .then((res) => {
          setPullSourceRequisitionOptions(
            (res?.data ?? [])
              .filter(
                (row) =>
                  row.id != null &&
                  row.requisition_code &&
                  row.capabilities?.push_inquiry?.allowed === true,
              )
              .map((row) => ({ value: row.id!, label: String(row.requisition_code) })),
          );
        })
        .catch((error: unknown) => {
          message.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseInquiry.pull.loadSourceFailed')));
          setPullSourceRequisitionOptions([]);
        });
    },
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const listRes = await listPurchaseRequisitionPurchaseInquiryPullLines({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          keyword: keyword.trim() || undefined,
          requisition_id: pullSourceRequisitionIdRef.current,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        message.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseInquiry.loadRequisitionsFailed')));
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullRequisitionOpenLineSelectable(record),
    onConfirm: async (_keys, rows) => {
      const selectedIds = rows
        .filter((row) => isPullRequisitionOpenLineSelectable(row))
        .map((row) => Number(row.id))
        .filter((id) => id > 0);
      if (!selectedIds.length) {
        message.warning(t('app.kuaizhizao.purchaseInquiry.pull.selectLinesFirst'));
        return;
      }
      try {
        await handoffRequisitionToPurchaseInquiryCreate(navigate, { selected_item_ids: selectedIds });
        message.success(
          t('app.kuaizhizao.documentFlow.openedDownstreamCreate', {
            target: pullFromRequisitionAction.targetLabel,
          }),
        );
        pullFromRequisitionQuery.closeModal();
      } catch (error: unknown) {
        message.error(
          getApiErrorMessage(
            error,
            t('app.kuaizhizao.purchaseInquiry.createFromPullFailed', {
              source: pullFromRequisitionAction.sourceLabel,
              target: pullFromRequisitionAction.targetLabel,
            }),
          ),
        );
      }
    },
  });

  const resetPushPoPreviewModal = useCallback(() => {
    setPushPoPreviewOpen(false);
    setPushPoPreviewData(null);
    setPushPoTarget(null);
    setPushPoSelectedItemIds([]);
  }, []);

  const openPushPoPreview = useCallback(
    async (inquiry: PurchaseInquiry) => {
      if (!inquiry.id) return;
      setPushPoPreviewOpen(true);
      setPushPoPreviewLoading(true);
      setPushPoPreviewConfirming(false);
      setPushPoPreviewData(null);
      setPushPoTarget(inquiry);
      setPushPoSelectedItemIds([]);
      try {
        const preview = await previewPushInquiryToPurchaseOrder(inquiry.id);
        setPushPoPreviewData(preview);
        const ids = (preview.items || [])
          .filter((row) => Number(row.max_push_quantity ?? 0) > 0)
          .map((row) => Number(row.item_id));
        setPushPoSelectedItemIds(ids);
      } catch (error: unknown) {
        message.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseInquiry.push.previewFailed')));
        resetPushPoPreviewModal();
      } finally {
        setPushPoPreviewLoading(false);
      }
    },
    [message, resetPushPoPreviewModal, t],
  );

  const handlePushPoPreviewConfirm = useCallback(async () => {
    if (!pushPoTarget?.id || !pushPoPreviewData || pushPoPreviewData.has_blocking_issues) return;
    const rowById = new Map(
      (pushPoPreviewData.items || []).map((row) => [Number(row.item_id), row]),
    );
    const selectedIds = pushPoSelectedItemIds.filter((id) => {
      const row = rowById.get(id);
      return row && Number(row.max_push_quantity ?? 0) > 0;
    });
    if (!selectedIds.length) {
      message.warning(t('app.kuaizhizao.purchaseInquiry.push.selectLines'));
      return;
    }
    setPushPoPreviewConfirming(true);
    try {
      await handoffInquiryToPurchaseOrderCreate(navigate, { item_ids: selectedIds });
      message.success(
        t('app.kuaizhizao.documentFlow.openedDownstreamCreate', {
          target: t('app.kuaizhizao.menu.purchase-management.purchase-orders'),
        }),
      );
      resetPushPoPreviewModal();
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseInquiry.push.failed')));
    } finally {
      setPushPoPreviewConfirming(false);
    }
  }, [message, navigate, pushPoPreviewData, pushPoSelectedItemIds, pushPoTarget, resetPushPoPreviewModal, t]);

  const selectedInquiryForToolbar = useMemo(() => {
    if (selectedRowKeys.length !== 1) return null;
    const id = Number(selectedRowKeys[0]);
    if (!Number.isFinite(id) || id <= 0) return null;
    return tableRowsRef.current.find((row) => row.id === id) ?? null;
  }, [selectedRowKeys]);

  async function handleCopySelectedPurchaseInquiry() {
    const record = selectedInquiryForToolbar;
    if (!record?.id) {
      message.warning(t('app.kuaizhizao.purchaseInquiry.selectToCopy'));
      return;
    }
    try {
      const data = await getPurchaseInquiry(record.id);
      const items = (data.items ?? []).map((item) => {
        const {
          id: _id,
          inquiry_id: _inquiryId,
          awarded_supplier_id: _awardedSupplierId,
          awarded_quote_item_id: _awardedQuoteItemId,
          purchase_order_id: _purchaseOrderId,
          ...rest
        } = item;
        return rest;
      });
      const vendors = (data.vendors ?? []).map((vendor) => {
        const {
          id: _id,
          inquiry_id: _inquiryId,
          status: _status,
          quoted_at: _quotedAt,
          ...rest
        } = vendor;
        return rest;
      });
      const taxRatePercent =
        data.tax_rate != null && data.tax_rate !== undefined ? Number(data.tax_rate) * 100 : 13;
      documentFlowSubmitExtrasRef.current = null;
      setEditingId(null);
      setEditingReviewStatus(null);
      setEditItems(items);
      setEditVendors(vendors);
      pendingEditFormValuesRef.current = {
        inquiry_name: data.inquiry_name,
        inquiry_date: dayjs(),
        quote_deadline: data.quote_deadline ? dayjs(data.quote_deadline) : undefined,
        demand_party_id: data.demand_party_id,
        demand_party_name: data.demand_party_name,
        buyer_id: data.buyer_id,
        buyer_name: data.buyer_name,
        buyer_phone: data.buyer_phone,
        department_id: data.department_id ?? undefined,
        department_name: data.department_name ?? undefined,
        currency: data.currency || 'CNY',
        exchange_rate: data.exchange_rate ?? 1,
        invoice_type: data.invoice_type,
        tax_rate_percent: taxRatePercent,
        payment_method: data.payment_method,
        payment_terms: data.payment_terms,
        trade_mode: data.trade_mode,
        notes: data.notes,
        attachments: mapAttachmentsToUploadList(data.attachments),
        __inquiry_edit_item: items.map((item) => ({ material_id: item.material_id })),
        __editItems: items,
        __editVendors: vendors,
      };
      navigate(PURCHASE_INQUIRY_CREATE_PATH);
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, t('common.loadFailed')));
    }
  }

  const handleBatchDelete = async (keys: React.Key[]) => {
    if (!keys || keys.length === 0) return;
    let success = 0;
    let failed = 0;
    for (const key of keys) {
      const id = Number(key);
      if (!Number.isFinite(id) || id <= 0) {
        failed += 1;
        continue;
      }
      try {
        await deletePurchaseInquiry(id);
        success += 1;
      } catch {
        failed += 1;
      }
    }
    if (success > 0) message.success(t('app.kuaizhizao.purchaseInquiry.batchDeleteSuccess', { count: success }));
    if (failed > 0) message.warning(t('app.kuaizhizao.purchaseInquiry.batchDeletePartial', { count: failed }));
    setSelectedRowKeys([]);
    actionRef.current?.reload();
  };

  const canPushPurchaseOrder = !!selectedInquiryForToolbar?.capabilities?.push_purchase_order?.allowed;

  const toolbarPushDisabledReason = useMemo(() => {
    const base = buildUniPushToolbarDisabledReason(t, {
      selectedCount: selectedRowKeys.length,
      hasSelectedRecord: !!selectedInquiryForToolbar,
    });
    if (base) return base;
    if (selectedInquiryForToolbar && !canPushPurchaseOrder) {
      return (
        purchaseInquiryCapabilityReasonMessage(
          selectedInquiryForToolbar.capabilities?.push_purchase_order?.reason,
          t,
        ) || t('app.kuaizhizao.purchaseInquiry.push.notAwarded')
      );
    }
    return undefined;
  }, [canPushPurchaseOrder, selectedInquiryForToolbar, selectedRowKeys.length, t]);

  const toolbarPushMenuItems = useMemo(
    () =>
      buildUniPushMenuItems([
        {
          key: 'push-purchase-order',
          label: pushToPurchaseOrderAction.label,
          disabled: !selectedInquiryForToolbar || !canPushPurchaseOrder,
          title: !canPushPurchaseOrder && selectedInquiryForToolbar
            ? purchaseInquiryCapabilityReasonMessage(
                selectedInquiryForToolbar.capabilities?.push_purchase_order?.reason,
                t,
              )
            : undefined,
          onClick: () => {
            if (selectedInquiryForToolbar && canPushPurchaseOrder) {
              void openPushPoPreview(selectedInquiryForToolbar);
            }
          },
        },
      ]),
    [canPushPurchaseOrder, openPushPoPreview, pushToPurchaseOrderAction.label, selectedInquiryForToolbar, t],
  );

  useEffect(() => {
    const id = searchParams.get('inquiryId');
    const numId = id ? Number(id) : NaN;
    if (Number.isFinite(numId) && numId > 0) {
      navigate(purchaseInquiryEditPath(numId), { replace: true });
      searchParams.delete('inquiryId');
      setSearchParams(searchParams, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const purchaseInquiryLifecycleValueEnum = useMemo(
    () => buildPurchaseInquiryLifecycleValueEnum(t),
    [t],
  );
  const purchaseInquiryAuditColumn = useMemo(
    () => createListAuditPhaseColumn<PurchaseInquiry>({ t, auditEnabled }),
    [t, auditEnabled],
  );
  const resolveInquiryPushPercent = useCallback((record: PurchaseInquiry): number => {
    const stageName = String(getPurchaseInquiryLifecycle(record as Record<string, unknown>).stageName ?? '').trim();
    const status = String(record.status ?? '').trim();
    if (stageName === '已转单' || status === '已转单' || status === 'CONVERTED') return 100;
    return 0;
  }, []);

  const columns: ProColumns<PurchaseInquiry>[] = useMemo(
    () => alignProColumns<PurchaseInquiry>([
    {
      title: t('app.kuaizhizao.purchaseInquiry.colQuoteDeadline'),
      dataIndex: 'quote_deadline_range',
      valueType: 'dateRange',
      hideInTable: true,
      fieldProps: {
        placeholder: [t('app.kuaizhizao.quotation.dateRangeStart'), t('app.kuaizhizao.quotation.dateRangeEnd')],
      },
      formItemProps: formDateRangeFormItemProps,
    },
    {
      title: t('app.kuaizhizao.purchaseInquiry.colNameInquiryCode'),
      key: 'inquiry_code',
      dataIndex: 'inquiry_code',
      width: 240,
      minWidth: 240,
      uniTableKeepWidth: true,
      uniTablePrimaryFlex: false,
      resizable: false,
      fixed: 'left',
      sorter: true,
      render: (_, r) => (
        <UniTableStackedPrimaryCell
          primary={String(r.inquiry_name ?? '')}
          secondary={String(r.inquiry_code ?? '')}
        />
      ),
    },
    { title: t('app.kuaizhizao.purchaseInquiry.colInquiryCode'), dataIndex: 'inquiry_code', hideInTable: true, hideInSearch: false },
    { title: t('common.name'), dataIndex: 'inquiry_name', hideInTable: true, hideInSearch: false, ellipsis: true },
    {
      title: t('app.kuaizhizao.purchaseInquiry.colSourceCode'),
      dataIndex: 'source_code',
      width: 148,
      minWidth: 148,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: false,
      ellipsis: true,
      render: (_, r) => (
        <SourceDocumentCode
          sourceType={r.source_type}
          sourceId={r.source_id}
          sourceCode={r.source_code}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.common.colLineMaterials'),
      ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
      render: (_, r) => renderDocumentLineMaterialsPreview(r.items, t),
    },
    {
      title: t('app.kuaizhizao.purchaseInquiry.colBuyer'),
      dataIndex: 'buyer_name',
      width: 100,
      minWidth: 100,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
    },
    {
      title: t('app.kuaizhizao.purchaseInquiry.colQuoteDeadline'),
      dataIndex: 'quote_deadline',
      width: 132,
      minWidth: 132,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
      render: (_, r) => (r.quote_deadline ? formatDateTime(r.quote_deadline, 'YYYY-MM-DD') : '-'),
    },
    {
      title: t('app.kuaizhizao.salesManagement.pushProgress.title'),
      dataIndex: 'downstream_push_progress',
      ...DOCUMENT_PROGRESS_COLUMN_DEFAULTS,
      render: (_, r) => <DocumentPushProgressBar percent={resolveInquiryPushPercent(r)} />,
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.totalQuantity'),
      dataIndex: 'total_quantity',
      width: 100,
      minWidth: 100,
      uniTableKeepWidth: true,
      resizable: false,
      align: 'right' as const,
      hideInSearch: true,
      render: (_, r) => (formatQuantity(r.total_quantity)),
    },
    {
      title: t('app.kuaizhizao.salesOrder.totalAmountLabel'),
      dataIndex: 'total_amount',
      width: 120,
      minWidth: 120,
      uniTableKeepWidth: true,
      resizable: false,
      align: 'right' as const,
      hideInSearch: true,
      render: (_, r) => (r.total_amount != null ? formatCurrencyAmount(r.total_amount) : '-'),
    },
    ...buildDocumentAuditColumns<PurchaseInquiry>(t),
    {
      title: t('common.createdAt'),
      dataIndex: 'created_at_range',
      valueType: 'dateRange',
      hideInTable: true,
      fieldProps: {
        placeholder: [t('app.kuaizhizao.quotation.dateRangeStart'), t('app.kuaizhizao.quotation.dateRangeEnd')],
      },
      formItemProps: formDateRangeFormItemProps,
    },
    ...(purchaseInquiryAuditColumn ? [purchaseInquiryAuditColumn] : []),
    {
      title: t('app.kuaizhizao.purchaseInquiry.colLifecycle'),
      key: 'lifecycle',
      dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
      fixed: 'right',
      valueType: 'select',
      valueEnum: purchaseInquiryLifecycleValueEnum,
      render: (_, record) => (
        <ListUniLifecycleCell lifecycle={getPurchaseInquiryLifecycle(record as Record<string, unknown>)} />
      ),
    },
    {
      title: t('common.actions'),
      key: 'option',
      valueType: 'option',
      fixed: 'right',
      render: (_, record) => {
        const isDraft = isInquiryDraft(record);
        const canUpdate = record.capabilities?.update?.allowed === true && purchaseInquiryPerms.canUpdate;
        const canDelete = record.capabilities?.delete?.allowed === true && purchaseInquiryPerms.canDelete;
        const parts: React.ReactNode[] = [
          <Button {...rowActionKind('read')} key="view" onClick={() => openDetail(record)}>
            {t('common.detail')}
          </Button>,
        ];

        if (isDraft) {
          parts.push(
            <Button {...rowActionKind('update')} key="edit" disabled={!canUpdate} onClick={() => canUpdate && openEdit(record)}>
              {t('common.edit')}
            </Button>,
          );
          parts.push(
            <Button
              {...rowActionKind('delete')}
              key="del"
              disabled={!canDelete}
              onClick={() => {
                if (!canDelete) return;
                modal.confirm({
                  title: t('app.kuaizhizao.purchaseInquiry.confirmDelete'),
                  onOk: async () => {
                    await deletePurchaseInquiry(record.id!);
                    message.success(t('app.kuaizhizao.purchaseInquiry.deleted'));
                    actionRef.current?.reload();
                  },
                });
              }}
            >
              {t('common.delete')}
            </Button>,
          );
          parts.push(
            <Button
              {...rowActionKind('release')}
              key="publish"
              disabled={!purchaseInquiryPerms.canUpdate}
              onClick={async () => {
                if (!purchaseInquiryPerms.canUpdate) return;
                await publishPurchaseInquiry(record.id!);
                message.success(t('app.kuaizhizao.purchaseInquiry.publishSuccess'));
    actionRef.current?.reload();
              }}
            >
              {t('app.kuaizhizao.purchaseInquiry.publishInquiry')}
            </Button>,
          );
        }

        if (isInquiryQuoting(record)) {
          parts.push(
            <Button
              {...rowActionKind('update')}
              key="close-quoting"
              disabled={!purchaseInquiryPerms.canUpdate}
              onClick={async () => {
                if (!purchaseInquiryPerms.canUpdate) return;
                await closeInquiryQuoting(record.id!);
                message.success(t('app.kuaizhizao.purchaseInquiry.closeQuotingSuccess'));
    actionRef.current?.reload();
              }}
            >
              {t('app.kuaizhizao.purchaseInquiry.closeQuoting')}
            </Button>,
          );
        }

        if (isInquiryPendingCompare(record) || isInquiryQuoting(record) || isInquiryAwarded(record)) {
          parts.push(
            <Button {...rowActionKind('read')} key="compare" onClick={() => void openCompare(record)}>
              {t('app.kuaizhizao.purchaseInquiry.compareAward')}
            </Button>,
          );
        }

        parts.push(
          <UniWorkflowActions
            {...rowActionKind('skip')}
            key="workflow-actions"
            record={record}
            entityName={t('app.kuaizhizao.purchaseInquiry.entityName')}
            statusField="status"
            reviewStatusField="review_status"
            draftStatuses={['DRAFT', '草稿']}
            pendingStatuses={['PENDING', 'PENDING_REVIEW', '待审核']}
            approvedStatuses={['APPROVED', '已通过', '审核通过']}
            rejectedStatuses={['REJECTED', '已驳回']}
            onSuccess={() => {
              actionRef.current?.reload();
              if (detailOpen && detail?.id === record.id && record.id != null) {
                void getPurchaseInquiry(record.id)
                  .then(setDetail)
                  .catch(() => {});
              }
            }}
          />,
        );

        return parts;
      },
    },
  ], SALES_DOC_LIST_FIELD_RANK),
    [detail, detailOpen, message, modal, openCompare, purchaseInquiryAuditColumn, purchaseInquiryLifecycleValueEnum, purchaseInquiryPerms.canDelete, purchaseInquiryPerms.canUpdate, resolveInquiryPushPercent, t],
  );

  const detailTableColumns: ProColumns<PurchaseInquiryItemRow>[] = useMemo(
    () =>
      alignProColumns<PurchaseInquiryItemRow>(
        [
      {
        title: t('app.kuaizhizao.purchaseInquiry.colNameInquiryCode'),
        key: 'inquiry_code',
        dataIndex: 'inquiry_code',
        ...UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
        fixed: 'left',
        hideInSearch: false,
        fieldProps: { placeholder: t('app.kuaizhizao.purchaseInquiry.colInquiryCode') },
        render: (_, record) => (
          <UniTableStackedPrimaryCell
            primary={String(record.inquiry_name ?? '')}
            secondary={String(record.inquiry_code ?? '')}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.colInquiryCode'),
        dataIndex: 'inquiry_code',
        hideInTable: true,
      },
      {
        title: t('common.name'),
        dataIndex: 'inquiry_name',
        hideInTable: true,
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.colMaterialName'),
        key: 'material_display',
        dataIndex: 'material_name',
        ...UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
        render: (_, record) => (
          <MaterialStackedCell
            material_name={record.material_name}
            material_code={record.material_code}
            material_spec={record.material_spec}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.colMaterialCode'),
        dataIndex: 'material_code',
        hideInTable: true,
      },
      {
        title: t('common.quantity'),
        dataIndex: 'quantity',
        width: 120,
        align: 'right',
        render: (val: unknown, record) => (
          <QuantityWithUnitDisplay quantity={val} unit={record.unit} />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.requiredDate'),
        dataIndex: 'required_date',
        width: 132,
        uniTableKeepWidth: true,
        hideInSearch: true,
        render: (_: unknown, row) =>
          row.required_date ? formatDateTime(row.required_date, 'YYYY-MM-DD') : '-',
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.colQuoteDeadline'),
        dataIndex: 'quote_deadline',
        width: 132,
        uniTableKeepWidth: true,
        hideInSearch: true,
        render: (_: unknown, row) =>
          row.quote_deadline ? formatDateTime(row.quote_deadline, 'YYYY-MM-DD') : '-',
      },
      {
        title: t('app.kuaizhizao.salesManagement.pushProgress.title'),
        key: 'line_push_progress',
        ...DETAIL_TABLE_PROGRESS_COLUMN_DEFAULTS,
        render: (_: unknown, record) => {
          const percent = resolveInquiryPushPercent({
            status: record.status,
          } as PurchaseInquiry);
          return <DocumentPushProgressBar percent={percent} />;
        },
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.colLifecycle'),
        dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
        fixed: 'right',
        hideInSearch: false,
        valueEnum: purchaseInquiryLifecycleValueEnum,
        render: (_, record) => (
          <ListUniLifecycleCell
            lifecycle={getPurchaseInquiryLifecycle({
              status: record.status,
              review_status: record.review_status,
            } as Record<string, unknown>)}
          />
        ),
      },
        ],
        GLOBAL_DOC_DETAIL_TABLE_FIELD_RANK,
      ),
    [purchaseInquiryLifecycleValueEnum, resolveInquiryPushPercent, t],
  );

  const request = useCallback(
    async (
      params: Record<string, unknown>,
      sort?: Record<string, 'ascend' | 'descend' | null>,
      _filter?: Record<string, unknown>,
      searchFormValues?: Record<string, unknown>,
    ) => {
      const apiParams = resolvePurchaseInquiryListApiParams(
        params,
        sort,
        searchFormValues,
      ) as Parameters<typeof listPurchaseInquiries>[0];
      const list = await listPurchaseInquiries(apiParams);
      const inquiries = list.data ?? [];
      // 行缓存唯一真源：onTableDataChange（prefetch 会走本 request，禁止在此覆盖）
      if (dataViewModeRef.current === 'order') {
        return { data: inquiries, success: true, total: list.total ?? inquiries.length };
      }
      const flatRows = flattenDocumentDetailRows<PurchaseInquiry, PurchaseInquiryItem>({
        headers: inquiries,
        getHeaderId: (h) => h.id,
        getItems: (h) => h.items,
        buildRowKey: (h, item, index) =>
          item?.id ? `inq-${h.id}-item-${item.id}` : `inq-${h.id}-idx-${index}`,
        mapItemRow: (h, item) => ({
          ...item,
          inquiry_id: h.id ?? 0,
          inquiry_code: h.inquiry_code,
          inquiry_name: h.inquiry_name,
          source_code: h.source_code,
          buyer_name: h.buyer_name,
          quote_deadline: h.quote_deadline,
          status: h.status,
          review_status: h.review_status,
        }),
        mapEmptyHeaderRow: (h) => ({
          inquiry_id: h.id ?? 0,
          inquiry_code: h.inquiry_code,
          inquiry_name: h.inquiry_name,
          material_id: 0,
          material_code: '-',
          material_name: '-',
          unit: '',
          quantity: 0,
          status: h.status,
          review_status: h.review_status,
          quote_deadline: h.quote_deadline,
        }),
      }) as PurchaseInquiryItemRow[];
      return { data: flatRows, success: true, total: list.total ?? inquiries.length };
    },
    [],
  );

  const addEditItem = () => {
    setEditItems((prev) => {
      const next = [
        ...prev,
        { material_id: undefined, material_code: '', material_name: '', unit: '件', quantity: 1 },
      ];
      editForm.setFieldValue(
        '__inquiry_edit_item',
        next.map((item) => ({ material_id: item.material_id })),
      );
      return next;
    });
  };

  const openAddVendorModal = () => {
    setSelectedSupplierIdsForAdd([]);
    setAddVendorModalOpen(true);
  };

  const handleConfirmAddVendors = () => {
    if (!selectedSupplierIdsForAdd.length) {
      message.warning(t('app.kuaizhizao.purchaseInquiry.selectSuppliersFirst'));
      return;
    }
    const toAdd = supplierOptions.filter(
      (s) => selectedSupplierIdsForAdd.includes(Number(s.id)) && !editVendors.some((v) => v.supplier_id === Number(s.id)),
    );
    if (!toAdd.length) {
      message.warning(t('app.kuaizhizao.purchaseInquiry.suppliersAlreadyAdded'));
      return;
    }
    setEditVendors((prev) => [
      ...prev,
      ...toAdd.map((s) => {
        const full = resolveFullSupplierFromList({ id: s.id }, supplierOptions);
        const firstContact = full ? buildSupplierContactPickOptions(full)[0] : undefined;
        return {
          supplier_id: Number(s.id),
          supplier_name: String(s.name ?? ''),
          contact_name: firstContact?.value,
          contact_phone: firstContact?.phone,
          contact_email: undefined,
          email_notify: false,
        };
      }),
    ]);
    setAddVendorModalOpen(false);
    setSelectedSupplierIdsForAdd([]);
    message.success(t('app.kuaizhizao.purchaseInquiry.vendorsAdded', { count: toAdd.length }));
  };

  const formatSupplierLabel = useCallback(
    (s: SupplierLike) => {
      const code = String(s.code ?? '').trim();
      const name = String(s.name ?? s.supplier_name ?? '').trim();
      return code ? `${code} - ${name}` : name;
    },
    [],
  );

  const patchEditVendor = useCallback((supplierId: number, patch: Partial<PurchaseInquiryVendor>) => {
    setEditVendors((prev) =>
      prev.map((v) => (v.supplier_id === supplierId ? { ...v, ...patch } : v)),
    );
  }, []);

  const editVendorColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.purchaseInquiry.supplier'),
        dataIndex: 'supplier_name',
        width: 180,
        ellipsis: true,
        render: (name: string, record: PurchaseInquiryVendor) => {
          const matched = supplierOptions.find((s) => s.id === record.supplier_id);
          return matched ? formatSupplierLabel(matched) : name;
        },
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.vendorContact'),
        width: 120,
        render: (_: unknown, r: PurchaseInquiryVendor) => (
          <PurchaseSupplierContactPickInput
            supplierId={r.supplier_id}
            supplierList={supplierOptions}
            hostResource={KUAIZHIZAO_DOC_HOST.purchaseInquiry}
            value={r.contact_name}
            placeholder={t('app.kuaizhizao.purchaseInquiry.vendorContact')}
            onChange={(contactName, contactPhone) => {
              const patch: Partial<PurchaseInquiryVendor> = { contact_name: contactName };
              if (contactPhone !== undefined) {
                patch.contact_phone = contactPhone;
              }
              patchEditVendor(r.supplier_id!, patch);
            }}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.vendorPhone'),
        width: 120,
        render: (_: unknown, r: PurchaseInquiryVendor) => (
          <Input
            size="small"
            value={r.contact_phone}
            placeholder={t('app.kuaizhizao.purchaseInquiry.vendorPhone')}
            onChange={(e) => patchEditVendor(r.supplier_id!, { contact_phone: e.target.value })}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.vendorEmail'),
        width: 160,
        render: (_: unknown, r: PurchaseInquiryVendor) => (
          <Input
            size="small"
            value={r.contact_email}
            placeholder={t('app.kuaizhizao.purchaseInquiry.vendorEmail')}
            onChange={(e) => patchEditVendor(r.supplier_id!, { contact_email: e.target.value })}
          />
        ),
      },
      {
        title: (
          <Tooltip title={t('app.kuaizhizao.purchaseInquiry.emailNotifyHint')}>
            <span>{t('app.kuaizhizao.purchaseInquiry.emailNotify')}</span>
          </Tooltip>
        ),
        width: 100,
        align: 'center' as const,
        render: (_: unknown, r: PurchaseInquiryVendor) => (
          <Checkbox
            checked={Boolean(r.email_notify)}
            onChange={(e) => patchEditVendor(r.supplier_id!, { email_notify: e.target.checked })}
          />
        ),
      },
      {
        title: t('common.actions'),
        width: 72,
        render: (_: unknown, r: PurchaseInquiryVendor) => (
          <Button type="link" danger size="small" onClick={() => setEditVendors((prev) => prev.filter((v) => v.supplier_id !== r.supplier_id))}>
            {t('common.remove')}
          </Button>
        ),
      },
    ],
    [supplierOptions, t, formatSupplierLabel, patchEditVendor],
  );

  const editItemColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.purchaseInquiry.material'),
        width: 280,
        render: (_: unknown, r: PurchaseInquiryItem, idx: number) => (
          <UniMaterialSelect
            name={['__inquiry_edit_item', idx, 'material_id']}
            label=""
            size="small"
            formItemProps={{ style: { margin: 0 } }}
            fallbackOption={
              r.material_id
                ? { value: r.material_id, label: `${r.material_code || ''} - ${r.material_name || ''}`.trim() || String(r.material_id) }
                : undefined
            }
            onChange={(_, mat) => {
              if (!mat) return;
              setEditItems((prev) => {
                const next = [...prev];
                next[idx] = {
                  ...next[idx],
                  material_id: mat.id,
                  material_code: mat.code,
                  material_name: mat.name,
                  material_spec: mat.spec,
                  unit: mat.unit ?? '件',
                };
                return next;
              });
            }}
          />
        ),
      },
      {
        title: t('common.quantity'),
        width: 120,
        render: (_: unknown, r: PurchaseInquiryItem, idx: number) => (
          <InputNumber
            min={0}
            size="small"
            style={{ width: '100%' }}
            value={r.quantity}
            onChange={(v) => setEditItems((prev) => {
              const next = [...prev];
              next[idx] = { ...next[idx], quantity: v ?? 0 };
              return next;
            })}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.requiredDate'),
        width: 160,
        render: (_: unknown, r: PurchaseInquiryItem, idx: number) => (
          <FutureDatePicker
            size="small"
            style={{ width: '100%' }}
            value={r.required_date ? dayjs(r.required_date) : undefined}
            getForm={() => editForm}
            baseFieldName="inquiry_date"
            t={t}
            onApply={(d) => setEditItems((prev) => {
              const next = [...prev];
              next[idx] = { ...next[idx], required_date: d.format('YYYY-MM-DD') };
              return next;
            })}
            onChange={(d) => setEditItems((prev) => {
              const next = [...prev];
              next[idx] = { ...next[idx], required_date: d?.format('YYYY-MM-DD') };
              return next;
            })}
          />
        ),
      },
      {
        title: t('common.actions'),
        width: 60,
        fixed: 'right' as const,
        render: (_: unknown, __: PurchaseInquiryItem, idx: number) => (
          <Button type="link" danger size="small" onClick={() => setEditItems((prev) => prev.filter((_, i) => i !== idx))}>{t('app.kuaizhizao.purchaseInquiry.deleteLine')}</Button>
        ),
      },
    ],
    [t],
  );

  const detailVendorColumns = useMemo(
    () => [
      { title: t('app.kuaizhizao.purchaseInquiry.supplier'), dataIndex: 'supplier_name', ellipsis: true },
      { title: t('app.kuaizhizao.purchaseInquiry.vendorContact'), dataIndex: 'contact_name', width: 100, ellipsis: true },
      { title: t('app.kuaizhizao.purchaseInquiry.vendorEmail'), dataIndex: 'contact_email', width: 140, ellipsis: true },
      {
        title: t('app.kuaizhizao.purchaseInquiry.emailNotify'),
        dataIndex: 'email_notify',
        width: 90,
        render: (v: boolean) => (v ? t('common.yes') : t('common.no')),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.quoteStatus'),
        width: 100,
        render: (_: unknown, v: PurchaseInquiryVendor) => (
          <Tag color={v.status === 'QUOTED' ? 'success' : 'default'}>
            {v.status === 'QUOTED' ? t('app.kuaizhizao.purchaseInquiry.quoted') : t('app.kuaizhizao.purchaseInquiry.pendingQuote')}
          </Tag>
        ),
      },
      {
        title: t('common.actions'),
        width: 160,
        render: (_: unknown, v: PurchaseInquiryVendor) => {
          if (!detail) return null;
          const canQuote = isInquiryQuoting(detail) || isInquiryPendingCompare(detail);
          if (!canQuote) {
            return v.status === 'QUOTED' ? (
              <Typography.Text type="secondary">{t('app.kuaizhizao.purchaseInquiry.recorded')}</Typography.Text>
            ) : (
              <Typography.Text type="secondary">—</Typography.Text>
            );
          }
          const quoted = v.status === 'QUOTED';
          return (
            <Button
              type={quoted ? 'link' : 'primary'}
              size="small"
              icon={<FormOutlined />}
              onClick={() => openQuoteEntry(detail, v.supplier_id!)}
            >
              {quoted ? t('app.kuaizhizao.purchaseInquiry.editQuote') : t('app.kuaizhizao.purchaseInquiry.enterQuoteHere')}
            </Button>
          );
        },
      },
    ],
    [detail, t],
  );

  const detailItemColumns = useMemo(
    () => [
      { title: t('app.kuaizhizao.purchaseInquiry.colMaterialCode'), dataIndex: 'material_code', width: 120 },
      { title: t('app.kuaizhizao.purchaseInquiry.colMaterialName'), dataIndex: 'material_name' },
      { title: t('common.quantity'), dataIndex: 'quantity', width: 90, render: formatQuantity },
      { title: t('common.unit'), dataIndex: 'unit', width: 60 },
      { title: t('app.kuaizhizao.purchaseInquiry.requiredDate'), dataIndex: 'required_date', width: 110, render: (v: string) => (v ? formatDateBySiteSetting(v) : '-') },
    ],
    [t],
  );

  const detailBasicColumns = useMemo<ProDescriptionsItemProps<PurchaseInquiry>[]>(
    () =>
      alignDescriptionColumns([
        { title: t('app.kuaizhizao.purchaseInquiry.colInquiryCode'), dataIndex: 'inquiry_code' },
        {
          title: t('app.kuaizhizao.purchaseInquiry.source'),
          dataIndex: 'source_code',
          key: 'linked_source_code',
          render: (_, r) => (
            <SourceDocumentCode
              sourceType={r?.source_type}
              sourceId={r?.source_id}
              sourceCode={r?.source_code}
            />
          ),
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.demandPartyName'),
          dataIndex: 'demand_party_name',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.colBuyer'),
          dataIndex: 'buyer_name',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.buyerPhone'),
          dataIndex: 'buyer_phone',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.inquiryDate'),
          dataIndex: 'inquiry_date',
          valueType: 'date',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.colQuoteDeadline'),
          dataIndex: 'quote_deadline',
          valueType: 'date',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.currency'),
          dataIndex: 'currency',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.exchangeRate'),
          dataIndex: 'exchange_rate',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.invoiceType'),
          dataIndex: 'invoice_type',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.taxRate'),
          dataIndex: 'tax_rate',
          render: (_, r) =>
            r?.tax_rate != null ? `${(Number(r.tax_rate) * 100).toFixed(0)}%` : '—',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.paymentMethod'),
          dataIndex: 'payment_method',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.paymentTerms'),
          dataIndex: 'payment_terms',
        },
        {
          title: t('app.kuaizhizao.purchaseInquiry.tradeMode'),
          dataIndex: 'trade_mode',
        },
        {
          title: t('common.remark'),
          dataIndex: 'notes',
          span: 3,
        },
      ] as ProDescriptionsItemProps<PurchaseInquiry>[]),
    [t],
  );

  const inquiryLifecycle = useMemo(
    () => (detail ? getPurchaseInquiryLifecycle(detail as Record<string, unknown>) : null),
    [detail],
  );
  const inquiryNextSteps = inquiryLifecycle?.nextStepSuggestions;
  const inquiryShowNextInTitle = Boolean(inquiryNextSteps?.length);

  const inquiryTracking = useDocumentTracking(
    detailOpen && detail?.id ? 'purchase_inquiry' : undefined,
    detail?.id,
    inquiryTrackingRefreshKey,
  );

  const detailCollaboration = useMemo(() => {
    if (!detail || !inquiryLifecycle) return undefined;
    const mainStages = inquiryLifecycle.mainStages ?? [];
    if (!mainStages.length) return undefined;
    return (
      <UniLifecycleStepper
        steps={mainStages}
        status={inquiryLifecycle.status}
        showLabels
        nextStepSuggestions={inquiryLifecycle.nextStepSuggestions}
        hideNextStepSuggestions={inquiryShowNextInTitle}
      />
    );
  }, [detail, inquiryLifecycle, inquiryShowNextInTitle]);

  const detailSupplementary = useMemo(() => {
    if (!detail) return undefined;
    return (
      <>
        {isInquiryDraft(detail) ? (
          <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
            {t('app.kuaizhizao.purchaseInquiry.hintAfterPublish')}
          </Typography.Text>
        ) : null}
        {(isInquiryQuoting(detail) || isInquiryPendingCompare(detail)) ? (
          <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
            {t('app.kuaizhizao.purchaseInquiry.hintQuoting')}
          </Typography.Text>
        ) : null}
        {(detail.vendors ?? []).length > 0 ? (
          <Table
            size="small"
            pagination={false}
            rowKey="supplier_id"
            dataSource={detail.vendors ?? []}
            columns={detailVendorColumns}
          />
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.purchaseInquiry.emptyVendorsInDetail')} />
        )}
      </>
    );
  }, [detail, detailVendorColumns, t]);

  const detailLines = useMemo(() => {
    if (!detail) return undefined;
    return (
      <Table
        size="small"
        rowKey="id"
        pagination={false}
        dataSource={detail.items ?? []}
        columns={detailItemColumns}
        locale={{ emptyText: t('app.kuaizhizao.salesReturn.emptyItems') }}
      />
    );
  }, [detail, detailItemColumns, t]);

  const quoteItemColumns = useMemo(
    () => [
      { title: t('app.kuaizhizao.purchaseInquiry.colMaterialCode'), dataIndex: 'material_code', width: 120, ellipsis: true },
      { title: t('app.kuaizhizao.purchaseInquiry.colMaterialName'), dataIndex: 'material_name', width: 180, ellipsis: true },
      {
        title: t('app.kuaizhizao.purchaseInquiry.inquiryQuantity'),
        width: 100,
        align: 'right' as const,
        render: (_: unknown, item: PurchaseInquiryItem) => `${item.quantity ?? '-'} ${item.unit ?? ''}`.trim(),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.quotedQuantity'),
        width: 110,
        render: (_: unknown, item: PurchaseInquiryItem) => (
          <Form.Item
            name={`qty_${item.id}`}
            style={{ margin: 0 }}
            rules={[{ required: true, message: t('common.required') }]}
          >
            <InputNumber min={0} precision={quantityDecimals} style={{ width: '100%' }} size="small" />
          </Form.Item>
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.unitPrice'),
        width: 120,
        render: (_: unknown, item: PurchaseInquiryItem) => (
          <Form.Item
            name={`price_${item.id}`}
            style={{ margin: 0 }}
            rules={[{ required: true, message: t('common.required') }]}
          >
            <InputNumber min={0} precision={priceDecimals} style={{ width: '100%' }} size="small" />
          </Form.Item>
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.promisedDeliveryDate'),
        width: 140,
        render: (_: unknown, item: PurchaseInquiryItem) => (
          <Form.Item name={`date_${item.id}`} style={{ margin: 0 }}>
            <DatePicker style={{ width: '100%' }} size="small" />
          </Form.Item>
        ),
      },
    ],
    [t, quantityDecimals, priceDecimals],
  );

  const compareColumns = useMemo(
    () => [
      { title: t('app.kuaizhizao.purchaseInquiry.material'), width: 220, render: (_: unknown, r: ComparisonRow) => `${r.material_code} ${r.material_name}` },
      { title: t('common.quantity'), dataIndex: 'quantity', width: 80, align: 'right' as const, render: formatQuantity },
      ...(compareRows[0]?.cells ?? []).map((cell, idx) => ({
        title: cell.supplier_name ?? t('app.kuaizhizao.purchaseInquiry.supplierFallback', { index: idx + 1 }),
        width: 148,
        align: 'center' as const,
        render: (_: unknown, row: ComparisonRow) => {
          const c = row.cells[idx];
          if (!c?.quote_item_id) return '-';
          const rowAwardedCell = row.cells.find((cell) => cell.is_awarded && cell.quote_item_id);
          const rowLocked = !!rowAwardedCell;
          const selected = awardSelection[row.inquiry_item_id] === c.quote_item_id;
          const priceText = c.unit_price != null ? formatPrice(c.unit_price) : '-';
          return (
            <Space size={4} align="center" wrap={false} style={{ whiteSpace: 'nowrap' }}>
              <Button
                type={selected ? 'primary' : 'default'}
                size="small"
                disabled={rowLocked && rowAwardedCell?.quote_item_id !== c.quote_item_id}
                icon={selected ? <CheckOutlined /> : undefined}
                onClick={() => {
                  if (rowLocked) return;
                  setAwardSelection((prev) => ({ ...prev, [row.inquiry_item_id]: c.quote_item_id! }));
                }}
                style={c.is_lowest_price && !selected ? { borderColor: '#52c41a', color: '#389e0d' } : undefined}
              >
                {priceText}
              </Button>
              {c.is_lowest_price ? (
                <Tag color="success" style={{ margin: 0, fontSize: 11, lineHeight: '18px', flexShrink: 0 }}>
                  {t('app.kuaizhizao.purchaseInquiry.lowest')}
                </Tag>
              ) : null}
            </Space>
          );
        },
      })),
    ],
    [awardSelection, compareRows, t],
  );

  const pullRequisitionColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.purchaseInquiry.colRequisitionCode'),
        dataIndex: 'requisition_code',
        width: 168,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialName'),
        dataIndex: 'material_name',
        ellipsis: true,
        render: (_: unknown, record: PullPurchaseRequisitionCandidate) => (
          <MaterialStackedCell
            material_name={record.material_name}
            material_code={record.material_code}
            material_spec={record.material_spec}
          />
        ),
      },
      {
        title: t('components.uniPullQuery.documentDateColumn'),
        dataIndex: 'document_date',
        width: 112,
        sorter: (a: PullPurchaseRequisitionCandidate, b: PullPurchaseRequisitionCandidate) =>
          String(a.document_date || a.requisition_date || '').localeCompare(
            String(b.document_date || b.requisition_date || ''),
          ),
        defaultSortOrder: 'descend' as const,
        render: (_: unknown, record: PullPurchaseRequisitionCandidate) => {
          const raw = record.document_date || record.requisition_date;
          return raw ? formatBusinessDateOnly(String(raw)) : '-';
        },
      },
      {
        title: t('common.quantity'),
        dataIndex: 'suggested_quantity',
        width: 100,
        align: 'right' as const,
        render: (v: number) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.salesOrder.colShippedQty'),
        dataIndex: 'pushed_quantity',
        width: 100,
        align: 'right' as const,
        render: (v: number) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.salesOrder.colShippableQty'),
        dataIndex: 'remaining_quantity',
        width: 100,
        align: 'right' as const,
        render: (v: number) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.purchaseInquiry.colRequiredDate'),
        dataIndex: 'required_date',
        width: 112,
        render: (v: string) => (v ? formatBusinessDateOnly(v) : '-'),
      },
      buildDocumentAttachmentsListColumn<PullPurchaseRequisitionCandidate>(t),
      {
        title: t('app.kuaizhizao.purchaseRequisition.pull.convertStatus'),
        key: 'convert_status',
        width: 100,
        align: 'center' as const,
        render: (_: unknown, record: PullPurchaseRequisitionCandidate) =>
          renderPullCapabilityTag(
            isPullRequisitionOpenLineSelectable(record),
            t('app.kuaizhizao.purchaseRequisition.pull.canCreate'),
            t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
          ),
      },
    ],
    [t],
  );

  const timeconfigBasicItems = useDetailDrawerDescriptionItems(
    detailBasicColumns.filter((col) => {
                  if (col.dataIndex !== 'notes') return true;
                  return String(detail?.notes ?? '').trim().length > 0;
                }),
                detail,
    'purchase_inquiry',
  );

  const purchaseInquiryAttachments = documentAttachmentsFromRecord(detail);
  const purchaseInquiryAttLabel = t('app.uniDetail.sectionAttachments');

  const purchaseInquiryCanCommit =
    isCreatePage
    || editingId == null
    || ['', 'DRAFT', '草稿', 'REJECTED', '已驳回', 'rejected'].includes(String(editingReviewStatus ?? '').trim());

  const triggerInquiryCommitAfterSave = useCallback(() => {
    commitAfterSaveRef.current = true;
    void editForm
      .validateFields()
      .then(() => handleSaveEdit())
      .catch(() => {
        commitAfterSaveRef.current = false;
      });
  }, [editForm, handleSaveEdit]);

  const renderPurchaseInquiryFormBody = () => (
    <>
      <div className="document-form-untitled-groups">
        <div className="document-form-untitled-group">
      <Row gutter={FORM_LAYOUT.GRID_GUTTER} wrap={false}>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormText name="inquiry_name" label={t('app.kuaizhizao.purchaseInquiry.inquiryName')} rules={[{ required: true }]} />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormDatePicker
            name="inquiry_date"
            label={t('app.kuaizhizao.purchaseInquiry.inquiryDate')}
            fieldProps={{ style: { width: '100%' } }}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormSelect
            name="demand_party_id"
            label={t('app.kuaizhizao.purchaseInquiry.demandPartyName')}
            rules={[{ required: true, message: t('app.kuaizhizao.purchaseInquiry.demandPartyRequired') }]}
            options={demandPartyOptions.map((p) => ({
              value: p.id,
              label: p.code ? `${p.code} - ${p.name}` : p.name,
            }))}
            fieldProps={{
              showSearch: true,
              optionFilterProp: 'label',
              onChange: (id: number) => {
                const party = demandPartyOptions.find((p) => p.id === id);
                editForm.setFieldsValue({
                  demand_party_id: id,
                  demand_party_name: party?.name,
                });
              },
            }}
          />
          <Form.Item name="demand_party_name" hidden>
            <Input />
          </Form.Item>
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <Form.Item name="buyer_id" label={t('app.kuaizhizao.purchaseInquiry.buyer')}>
            <UniDropdown
              showSearch
              allowClear
              loading={usersLoading}
              style={{ width: '100%' }}
              placeholder={t('app.kuaizhizao.purchaseInquiry.buyerPlaceholder')}
              options={userList.map((u) => ({
                value: Number(u.id),
                label: normalizeUserDisplayName(u.full_name || u.username),
              }))}
              onChange={(val, opt: { label?: string }) => {
                const uid = val != null && Number.isFinite(Number(val)) ? Number(val) : undefined;
                const user = userList.find((u) => Number(u.id) === uid);
                editForm.setFieldsValue({
                  buyer_id: uid,
                  buyer_name: opt?.label,
                  buyer_phone: user?.phone || undefined,
                });
              }}
            />
          </Form.Item>
          <Form.Item name="buyer_name" hidden>
            <Input />
          </Form.Item>
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormDatePicker
            name="quote_deadline"
            label={t('app.kuaizhizao.purchaseInquiry.quoteDeadline')}
            fieldProps={buildFutureDateShortcutFieldProps({
              getForm: () => editForm,
              fieldName: 'quote_deadline',
              baseFieldName: 'inquiry_date',
              t,
            })}
          />
        </Col>
      </Row>
      <Row gutter={FORM_LAYOUT.GRID_GUTTER} wrap={false}>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormText name="buyer_phone" label={t('app.kuaizhizao.purchaseInquiry.buyerPhone')} />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <PurchaseDepartmentFormField
            options={departmentOptions}
            loading={departmentOptionsLoading}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }} aria-hidden />
        <Col flex="1 1 0" style={{ minWidth: 0 }} aria-hidden />
        <Col flex="1 1 0" style={{ minWidth: 0 }} aria-hidden />
      </Row>
        </div>
      </div>

      <div className="uni-table-detail" style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontWeight: 500 }}>{t('app.kuaizhizao.purchaseInquiry.invitedVendors')}</span>
          {editVendors.length > 0 && (
            <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={openAddVendorModal}>
              {t('app.kuaizhizao.purchaseInquiry.addVendor')}
            </Button>
          )}
        </div>
        {editVendors.length > 0 ? (
          <Table
            size="small"
            pagination={false}
            scroll={{ x: 900 }}
            rowKey={(r) => r.supplier_id!}
            dataSource={editVendors}
            columns={editVendorColumns}
          />
        ) : (
          <div
            style={{
              padding: '12px 16px',
              background: '#fafafa',
              borderRadius: 4,
              border: '1px dashed var(--river-border-color)',
              textAlign: 'center',
              color: '#999',
            }}
          >
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={t('app.kuaizhizao.purchaseInquiry.emptyInvitedVendors')}
            />
            <Button type="primary" ghost icon={<PlusOutlined />} onClick={openAddVendorModal} style={{ marginTop: 8 }}>
              {t('app.kuaizhizao.purchaseInquiry.addVendor')}
            </Button>
          </div>
        )}
      </div>

      <div className="document-form-untitled-group">
      <Row gutter={FORM_LAYOUT.GRID_GUTTER} wrap={false}>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormSelect
            name="payment_method"
            label={t('app.kuaizhizao.purchaseInquiry.paymentMethod')}
            options={paymentMethodOptions}
            fieldProps={{ allowClear: true }}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <DictionarySelect
            dictionaryCode="PAYMENT_TERMS"
            name="payment_terms"
            label={t('app.kuaizhizao.purchaseInquiry.paymentTerms')}
            formRef={editFormRef}
            hostResource={PURCHASE_INQUIRY_RESOURCE}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <DictionarySelect
            dictionaryCode="TRADE_MODE"
            name="trade_mode"
            label={t('app.kuaizhizao.purchaseInquiry.tradeMode')}
            formRef={editFormRef}
            hostResource={PURCHASE_INQUIRY_RESOURCE}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <DictionarySelect
            dictionaryCode="CURRENCY"
            name="currency"
            label={t('app.kuaizhizao.purchaseInquiry.currency')}
            formRef={editFormRef}
            valueEqualsLabel={false}
            hostResource={PURCHASE_INQUIRY_RESOURCE}
            rules={[{ required: true }]}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormDigit
            name="exchange_rate"
            label={t('app.kuaizhizao.purchaseInquiry.exchangeRate')}
            min={0}
            fieldProps={{ precision: 6, style: { width: '100%' } }}
          />
        </Col>
      </Row>
      <Row gutter={FORM_LAYOUT.GRID_GUTTER} wrap={false}>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormSelect
            name="invoice_type"
            label={t('app.kuaizhizao.purchaseInquiry.invoiceType')}
            options={invoiceTypeOptions}
            rules={[{ required: true }]}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormSelect
            name="tax_rate_percent"
            label={t('app.kuaizhizao.purchaseInquiry.taxRate')}
            options={taxRatePercentOptions}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }} aria-hidden />
        <Col flex="1 1 0" style={{ minWidth: 0 }} aria-hidden />
        <Col flex="1 1 0" style={{ minWidth: 0 }} aria-hidden />
      </Row>
      </div>

      <div className="uni-table-detail" style={{ marginBottom: 24 }}>
        <Space style={{ marginBottom: 8 }}>
          <span style={{ fontWeight: 500 }}>{t('app.kuaizhizao.purchaseInquiry.inquiryItems')}</span>
          <Button size="small" onClick={addEditItem}>{t('app.kuaizhizao.purchaseInquiry.addLine')}</Button>
        </Space>
        <Table
          size="small"
          pagination={false}
          style={{ width: '100%' }}
          scroll={{ x: 720 }}
          rowKey={(_, idx) => String(idx)}
          dataSource={editItems}
          columns={editItemColumns}
        />
      </div>

      <DetailDrawerSection titleAccent title={t('common.remark')}>
        <ProFormTextArea name="notes" label={false} fieldProps={{ rows: 2 }} />
      </DetailDrawerSection>
      <DetailDrawerSection titleAccent title={t('app.uniDetail.sectionAttachments')} marginBottom={0}>
        <DocumentAttachmentsField category="purchase_inquiry_attachments" label={false} />
      </DetailDrawerSection>
    </>
  );

  useSubmitShortcut(() => void handleSaveEdit(), isFormPage);

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
                  onClick={leavePurchaseInquiryFormPage}
                />
                <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
                  {isCreatePage
                    ? t('app.kuaizhizao.purchaseInquiry.createModalTitle')
                    : t('app.kuaizhizao.purchaseInquiry.editTitle')}
                </Typography.Title>
              </Space>
              <DocumentFormPageHeaderActions
                onCancel={leavePurchaseInquiryFormPage}
                onSaveDraft={() => void handleSaveEdit()}
                onPrimarySubmit={() => void handleSaveEdit()}
                isCreatePage={isCreatePage}
                showSaveDraft={false}
                canSubmitAfterSave={false}
                showCommitSubmit={purchaseInquiryCanCommit}
                saveDraftLoading={inquiryFormBusy}
                commitSubmitLoading={inquiryFormBusy}
                onCommitSubmit={triggerInquiryCommitAfterSave}
              />
            </>
          }
        >
          <Spin spinning={formPageLoading}>
            <ProForm form={editForm} layout="vertical" submitter={false} onFinish={() => void handleSaveEdit()}>
              {renderPurchaseInquiryFormBody()}
            </ProForm>
          </Spin>
        </DocumentFormPageLayout>
        <Modal
          title={t('app.kuaizhizao.purchaseInquiry.selectVendorTitle')}
          open={addVendorModalOpen}
          onOk={handleConfirmAddVendors}
          onCancel={() => {
            setAddVendorModalOpen(false);
            setSelectedSupplierIdsForAdd([]);
          }}
          okText={t('common.confirm')}
          cancelText={t('common.cancel')}
          okButtonProps={{ disabled: selectedSupplierIdsForAdd.length === 0 }}
          destroyOnHidden
        >
          <Select
            mode="multiple"
            placeholder={t('app.kuaizhizao.purchaseInquiry.searchVendorPlaceholder')}
            options={availableSuppliersForAdd.map((s) => ({
              label: formatSupplierLabel(s),
              value: s.id,
            }))}
            value={selectedSupplierIdsForAdd}
            onChange={setSelectedSupplierIdsForAdd}
            style={{ width: '100%' }}
            showSearch
            allowClear
            maxTagCount="responsive"
            filterOption={(input, option) => (option?.label ?? '').toString().toLowerCase().includes(input.toLowerCase())}
            notFoundContent={availableSuppliersForAdd.length === 0 ? t('app.kuaizhizao.purchaseInquiry.noAvailableVendors') : undefined}
          />
          {availableSuppliersForAdd.length === 0 && (
            <Typography.Text type="secondary" style={{ display: 'block', marginTop: 12, fontSize: 12 }}>
              {t('app.kuaizhizao.purchaseInquiry.noSuppliersHint')}
            </Typography.Text>
          )}
        </Modal>
        <Modal
          title={t('app.kuaizhizao.menu.purchase-management.purchase-demand-parties')}
          open={demandPartyOpen}
          onCancel={() => {
            setDemandPartyOpen(false);
            void listPurchaseDemandParties({ is_active: true, limit: 500 })
              .then((res) => setDemandPartyOptions(res.data ?? []))
              .catch(() => setDemandPartyOptions([]));
          }}
          footer={null}
          width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
          destroyOnHidden
        >
          <PurchaseDemandPartiesPanel
            embedded
            onChanged={() => {
              void listPurchaseDemandParties({ is_active: true, limit: 500 })
                .then((res) => setDemandPartyOptions(res.data ?? []))
                .catch(() => setDemandPartyOptions([]));
            }}
          />
        </Modal>
      </>
    );
  }

  return (
    <>
      {purchaseInquiryAuditModal}
    <ListPageTemplate>
      <UniTable<PurchaseInquiry>
        actionRef={actionRef}
        rowKey={dataViewMode === 'detail' ? '_rowKey' : 'id'}
        columns={columns}
        request={request}
        viewTypes={['table', 'detailTable', 'help']}
        defaultViewType={viewTypeState === 'help' ? 'table' : viewTypeState}
        helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.purchaseInquiry)}
        onViewTypeChange={(v) => {
          dataViewModeRef.current = resolveDetailTableViewMode(v as 'table' | 'detailTable' | 'help');
          setViewTypeState(v as 'table' | 'detailTable' | 'help');
          setTimeout(() => actionRef.current?.reload(), 0);
        }}
        detailTableColumns={detailTableColumns}
        onTableDataChange={(rows) => {
          if (dataViewModeRef.current === 'order') {
            tableRowsRef.current = rows as PurchaseInquiry[];
          }
        }}
        columnPersistenceId={PURCHASE_INQUIRY_LIST_PERSISTENCE_ID}
        pinnedTabsField={LIST_LIFECYCLE_STAGE_FIELD}
        pinnedTabsValueEnum={purchaseInquiryLifecycleValueEnum}
        showAdvancedSearch={true}
        skipFuzzyPinyinClientFilter
        enableRowSelection={viewTypeState !== 'detailTable'}
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        showDeleteButton={viewTypeState !== 'detailTable'}
        onDelete={handleBatchDelete}
        deleteButtonText={t('common.delete')}
        deleteConfirmTitle={(count) => t('app.kuaizhizao.purchaseInquiry.confirmBatchDelete', { count })}
        toolBarActionsAfterDelete={
          demandPartyPerms.canRead
            ? [
                <Button key="purchase-demand-parties" onClick={() => setDemandPartyOpen(true)}>
                  {t('app.kuaizhizao.menu.purchase-management.purchase-demand-parties')}
                </Button>,
              ]
            : []
        }
        toolBarRender={() => [
          <UniPullCreateToolbar
            key="create-purchase-inquiry-with-pull"
            compactKey="create-purchase-inquiry-with-pull"
            createIcon={<PlusOutlined />}
            createLabel={t('app.kuaizhizao.purchaseInquiry.createInquiry')}
            onCreate={handleCreate}
            menuItems={[
              ...buildKuaizhizaoPullCreateMenuItems(t, [
                {
                  key: 'pull-from-requisition',
                  actionKey: 'purchase_inquiry.pull_from_requisition',
                  onClick: pullFromRequisitionQuery.openModal,
                },
              ]),
              { type: 'divider', key: 'copy-selected-divider' },
              {
                key: 'copy-selected',
                label: t('app.kuaizhizao.purchaseInquiry.copySelectedCreate'),
                disabled: !selectedInquiryForToolbar,
                onClick: () => void handleCopySelectedPurchaseInquiry(),
              },
            ]}
          />,
          ...(viewTypeState === 'detailTable' ? [] : [
            <UniPushToolbarButton
              key={`purchase-inquiry-push-${selectedInquiryForToolbar?.id ?? 'none'}`}
              menuItems={toolbarPushMenuItems}
              disabled={selectedRowKeys.length !== 1 || !selectedInquiryForToolbar}
              disabledReason={toolbarPushDisabledReason}
              sourceDocument={
                selectedInquiryForToolbar?.id
                  ? { type: 'purchase_inquiry', id: Number(selectedInquiryForToolbar.id) }
                  : null
              }
              pushTargets={{ 'push-purchase-order': 'purchase_order' }}
            />,
            <UniBatchMenuButton
              key="purchase-inquiry-submit"
              selectedRowKeys={selectedRowKeys}
              menuItems={purchaseInquiryToolbarAuditMenus.submit}
              buttonText={t('common.submit')}
            />,
            <UniBatchMenuButton
              key="purchase-inquiry-audit"
              selectedRowKeys={selectedRowKeys}
              menuItems={purchaseInquiryToolbarAuditMenus.audit}
              buttonText={t('components.uniAction.audit')}
            />,
          ]),
        ]}
      />
      <Modal
        title={t('app.kuaizhizao.menu.purchase-management.purchase-demand-parties')}
        open={demandPartyOpen}
        onCancel={() => {
          setDemandPartyOpen(false);
          void listPurchaseDemandParties({ is_active: true, limit: 500 })
            .then((res) => setDemandPartyOptions(res.data ?? []))
            .catch(() => setDemandPartyOptions([]));
        }}
        footer={null}
        width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
        destroyOnHidden
      >
        <PurchaseDemandPartiesPanel embedded onChanged={() => {
          void listPurchaseDemandParties({ is_active: true, limit: 500 })
            .then((res) => setDemandPartyOptions(res.data ?? []))
            .catch(() => setDemandPartyOptions([]));
        }} />
      </Modal>

      <DetailDrawerTemplate
        title={t('app.kuaizhizao.purchaseInquiry.detailTitle', { code: detail?.inquiry_code ?? '' })}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        size={DRAWER_CONFIG.HALF_WIDTH}
        extra={
          detail ? (
            <Space size="small" wrap>
              {isInquiryDraft(detail) && (
                <Button type="primary" onClick={async () => {
                  await publishPurchaseInquiry(detail.id!);
                  message.success(t('app.kuaizhizao.purchaseInquiry.publishSuccess'));
                  setDetail(await getPurchaseInquiry(detail.id!));
    actionRef.current?.reload();
                }}>{t('app.kuaizhizao.purchaseInquiry.publishInquiry')}</Button>
              )}
              {isInquiryQuoting(detail) && (
                <Button onClick={async () => {
                  await closeInquiryQuoting(detail.id!);
                  message.success(t('app.kuaizhizao.purchaseInquiry.closeQuotingSuccess'));
                  setDetail(await getPurchaseInquiry(detail.id!));
    actionRef.current?.reload();
                }}>{t('app.kuaizhizao.purchaseInquiry.closeQuoting')}</Button>
              )}
              {(isInquiryPendingCompare(detail) || isInquiryQuoting(detail) || isInquiryAwarded(detail)) && (
                <Button onClick={() => void openCompare(detail)}>{t('app.kuaizhizao.purchaseInquiry.compareAward')}</Button>
              )}
              {isInquiryDraft(detail) && (
                <Button
                  icon={<EditOutlined />}
                  onClick={() => {
                    setDetailOpen(false);
                    if (detail?.id) navigate(purchaseInquiryEditPath(detail.id));
                  }}
                >
                  {t('common.edit')}
                </Button>
              )}
              <UniWorkflowActions {...rowActionKind('skip')}
                record={detail}
                entityName={t('app.kuaizhizao.purchaseInquiry.entityName')}
                resourcePrefix={PURCHASE_INQUIRY_RESOURCE}
                unifiedAudit
                statusField="status"
                reviewStatusField="review_status"
                draftStatuses={['DRAFT', '草稿']}
                pendingStatuses={['PENDING', 'PENDING_REVIEW', '待审核']}
                approvedStatuses={['APPROVED', '已通过', '审核通过']}
                rejectedStatuses={['REJECTED', '已驳回']}
                theme="default"
                onSuccess={async () => {
    actionRef.current?.reload();
                  setInquiryTrackingRefreshKey((k) => k + 1);
                  if (detail.id) setDetail(await getPurchaseInquiry(detail.id));
                }}
              />
            </Space>
          ) : null
        }
        collaborationTitleSuffix={
          inquiryShowNextInTitle ? (
            <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
              {t('common.next')}：
              {inquiryNextSteps!.join(t('components.uniLifecycle.nextStepSeparator'))}
            </Typography.Text>
          ) : undefined
        }
        basic={
          detail ? (
            <Descriptions
              column={3}
              size="small"
              items={timeconfigBasicItems}
            />
          ) : undefined
        }
        collaboration={detailCollaboration}
        collaborationAuditRecord={detail}
        supplementaryTitle={
          detail
            ? t('app.kuaizhizao.purchaseInquiry.invitedVendors')
            : hasDocumentAttachments(purchaseInquiryAttachments)
              ? purchaseInquiryAttLabel
              : undefined
        }
        supplementary={appendDocumentAttachmentsToSupplementary(
          detailSupplementary,
          purchaseInquiryAttachments,
          purchaseInquiryAttLabel,
        )}
        linesTitle={t('app.kuaizhizao.purchaseInquiry.inquiryItems')}
        lines={detailLines}
        timeline={
          detail ? (
            inquiryTracking.data && !inquiryTracking.loading ? (
              <DocumentTrackingTimelineBody data={inquiryTracking.data} />
            ) : inquiryTracking.error ? (
              <Typography.Text type="danger">{inquiryTracking.error}</Typography.Text>
            ) : null
          ) : null
        }
        historyTab={
          detail?.id != null
            ? {
                documentId: detail.id,
                label: t('app.kuaizhizao.purchaseInquiry.approvalRecords'),
                children: (
                  <DocumentApprovalRecordsPane
                    entityType="purchase_inquiry"
                    entityId={detail.id}
                    refreshKey={inquiryTrackingRefreshKey}
                  />
                ),
              }
            : undefined
        }
        attachmentCenter={
          detail?.id != null
            ? {
                documentType: 'purchase_inquiry',
                documentId: detail.id,
                attachmentCategory: 'purchase_inquiry_attachments',
                canManageSelfAttachments: purchaseInquiryPerms.canUpdate,
                onDeleteSelfAttachment: async (fileUid: string) => {
                  const current = documentAttachmentsFromRecord(detail);
                  const target = current.find((f: DocumentAttachmentFile) => {
                    const uid = resolveDocumentAttachmentFileUuid(f) || String(f.uid || '').trim();
                    return uid === fileUid;
                  });
                  if (isSystemDocumentAttachment(target)) {
                    message.warning(t('app.uniDetail.attachmentCenter.systemDeleteForbidden'));
                    throw new Error('system attachment cannot delete');
                  }
                  const next = current.filter((f: DocumentAttachmentFile) => {
                    const uid = resolveDocumentAttachmentFileUuid(f) || String(f.uid || '').trim();
                    return uid !== fileUid;
                  });
                  await updatePurchaseInquiry(detail.id!, {
                    attachments: normalizeDocumentAttachments(next),
                  });
                  setDetail(await getPurchaseInquiry(detail.id!));
                  setInquiryTrackingRefreshKey((k) => k + 1);
                },
                onAddSelfAttachments: async (files: DocumentAttachmentFile[]) => {
                  const latest = await getPurchaseInquiry(detail.id!);
                  const current = documentAttachmentsFromRecord(latest);
                  const merged = normalizeDocumentAttachments([...current, ...files]);
                  await updatePurchaseInquiry(detail.id!, { attachments: merged });
                  setDetail(await getPurchaseInquiry(detail.id!));
                  setInquiryTrackingRefreshKey((k) => k + 1);
                },
              }
            : undefined
        }
        traceDocument={
          detail?.id != null
            ? {
                documentType: 'purchase_inquiry',
                documentId: detail.id,
                selfDocumentId: detail.id,
              }
            : undefined
        }
      />

      <Modal
        title={`${t('app.kuaizhizao.purchaseInquiry.enterSupplierQuoteTitle')}${quoteSupplierId && detail?.vendors ? ` - ${detail.vendors.find((v) => v.supplier_id === quoteSupplierId)?.supplier_name ?? ''}` : ''}`}
        open={quoteOpen}
        width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
        onCancel={() => {
          setQuoteOpen(false);
          setPendingQuoteFormValues(null);
        }}
        onOk={() => void saveQuote()}
        afterOpenChange={(open) => {
          if (open) {
            if (pendingQuoteFormValues) {
              quoteForm.setFieldsValue(pendingQuoteFormValues);
            }
            return;
          }
          quoteForm.resetFields();
          setPendingQuoteFormValues(null);
        }}
        destroyOnHidden
      >
        <Form form={quoteForm} layout="vertical">
          <Row gutter={FORM_LAYOUT.GRID_GUTTER}>
            <Col span={12}>
              <Form.Item name="quote_date" label={t('app.kuaizhizao.purchaseInquiry.quoteDate')} rules={[{ required: true, message: t('app.kuaizhizao.purchaseInquiry.selectQuoteDateRequired') }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="valid_until" label={t('app.kuaizhizao.purchaseInquiry.validUntil')}>
                <FutureDatePicker
                  style={{ width: '100%' }}
                  placeholder={t('app.kuaizhizao.purchaseInquiry.selectDatePlaceholder')}
                  getForm={() => quoteForm}
                  baseFieldName="quote_date"
                  fieldName="valid_until"
                  t={t}
                />
              </Form.Item>
            </Col>
          </Row>

          <div className="uni-table-detail" style={{ marginBottom: 16 }}>
            <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>{t('app.kuaizhizao.purchaseInquiry.quoteItems')}</Typography.Text>
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
              {t('app.kuaizhizao.purchaseInquiry.quoteItemsHint')}
            </Typography.Text>
            <Table
              size="small"
              pagination={false}
              rowKey="id"
              scroll={{ x: 860 }}
              dataSource={detail?.items ?? []}
              columns={quoteItemColumns}
            />
          </div>

          <Form.Item name="notes" label={t('common.remark')}>
            <Input.TextArea rows={2} placeholder={t('app.kuaizhizao.purchaseInquiry.quoteNotesPlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={t('app.kuaizhizao.purchaseInquiry.compareAwardTitle')}
        open={compareOpen}
        width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
        onCancel={() => {
          setCompareOpen(false);
          setCompareInquiryId(null);
        }}
        onOk={() => void confirmAward()}
      >
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12, fontSize: 12 }}>
          {t('app.kuaizhizao.purchaseInquiry.compareAwardHint')}
        </Typography.Text>
        {!compareRows.some((row) => row.cells.some((cell) => cell.quote_item_id)) ? (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            title={t('app.kuaizhizao.purchaseInquiry.selectAwardQuoteNoQuote')}
          />
        ) : (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            title={t('app.kuaizhizao.purchaseInquiry.compareAwardPartialHint')}
          />
        )}
        <Table
          size="small"
          pagination={false}
          rowKey="inquiry_item_id"
          dataSource={compareRows}
          scroll={{ x: 'max-content' }}
          columns={compareColumns}
        />
      </Modal>

      <UniPullQueryModal<PullPurchaseRequisitionCandidate>
        open={pullFromRequisitionQuery.open}
        title={pullFromRequisitionAction.label}
        onCancel={pullFromRequisitionQuery.closeModal}
        onOk={pullFromRequisitionQuery.handleConfirm}
        rowKey="id"
        columns={pullRequisitionColumns}
        dataSource={pullFromRequisitionQuery.dataSource}
        loading={pullFromRequisitionQuery.loading}
        confirmLoading={pullFromRequisitionQuery.confirmLoading}
        selectionType={pullFromRequisitionQuery.selectionType}
        selectedRowKeys={pullFromRequisitionQuery.selectedRowKeys}
        selectedRows={pullFromRequisitionQuery.selectedRows}
        onSelectedRowKeysChange={pullFromRequisitionQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromRequisitionQuery.isRowDisabled}
        searchDraft={pullFromRequisitionQuery.searchDraft}
        onSearchDraftChange={pullFromRequisitionQuery.setSearchDraft}
        onSearchApply={pullFromRequisitionQuery.handleSearchApply}
        onSearchClear={pullFromRequisitionQuery.handleSearchClear}
        appliedKeyword={pullFromRequisitionQuery.appliedKeyword}
        searchPlaceholder={t('app.kuaizhizao.purchaseInquiry.pull.searchPlaceholder')}
        filterExtra={(
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaizhizao.purchaseInquiry.pull.sourceDocPlaceholder')}
            style={{ width: 220, flexShrink: 0 }}
            value={pullSourceRequisitionId}
            options={pullSourceRequisitionOptions}
            onChange={(value) => {
              const nextId = Number(value);
              const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
              pullSourceRequisitionIdRef.current = next;
              setPullSourceRequisitionId(next);
              pullFromRequisitionQuery.handleSelectedRowKeysChange([], []);
              pullFromRequisitionQuery.handleSearchApply(pullFromRequisitionQuery.appliedKeyword);
            }}
          />
        )}
        getRowLabel={(row) =>
          [row.requisition_code, row.material_code].filter(Boolean).join(' ')
        }
        page={pullFromRequisitionQuery.page}
        pageSize={pullFromRequisitionQuery.pageSize}
        total={pullFromRequisitionQuery.total}
        onPageChange={pullFromRequisitionQuery.handlePageChange}
        scopeOptions={pullFromRequisitionQuery.scopeOptions}
        scope={pullFromRequisitionQuery.scope}
        onScopeChange={pullFromRequisitionQuery.handleScopeChange}
        okText={t('app.kuaizhizao.purchaseInquiry.pull.ok')}
      />

      <Modal
        title={pushToPurchaseOrderAction.label}
        open={pushPoPreviewOpen}
        destroyOnHidden
        width={1100}
        onCancel={resetPushPoPreviewModal}
        okText={pushToPurchaseOrderAction.label}
        cancelText={t('common.cancel')}
        confirmLoading={pushPoPreviewConfirming}
        onOk={() => void handlePushPoPreviewConfirm()}
        okButtonProps={{
          disabled:
            pushPoPreviewLoading ||
            !pushPoPreviewData ||
            !!pushPoPreviewData?.has_blocking_issues,
        }}
      >
        {pushPoPreviewLoading ? (
          <div style={{ minHeight: 120, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
            <Spin />
            <div style={{ color: 'var(--ant-color-primary)' }}>{t('app.kuaizhizao.salesOrder.loadingPreview')}</div>
          </div>
        ) : pushPoPreviewData ? (
          <div>
            <p style={{ marginBottom: 12, fontWeight: 500 }}>{pushPoPreviewData.summary}</p>
            {pushPoPreviewData.has_blocking_issues && pushPoPreviewData.blocking_reason ? (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                title={
                  purchaseInquiryCapabilityReasonMessage(pushPoPreviewData.blocking_reason, t)
                    || t('app.kuaizhizao.purchaseInquiry.push.failed')
                }
              />
            ) : null}
            {pushPoPreviewData.items?.length > 0 ? (
              <Table
                size="small"
                dataSource={pushPoPreviewData.items}
                rowKey={(row) => String(row.item_id)}
                pagination={false}
                scroll={{ x: 960 }}
                columns={[
                  {
                    title: t('common.select'),
                    dataIndex: 'item_id',
                    width: 64,
                    render: (_: unknown, row) => {
                      const itemId = Number(row.item_id);
                      const maxQty = Number(row.max_push_quantity ?? 0);
                      const disabled = !Number.isFinite(maxQty) || maxQty <= 0;
                      return (
                        <Switch
                          size="small"
                          disabled={disabled}
                          checked={pushPoSelectedItemIds.includes(itemId)}
                          onChange={(checked) => {
                            setPushPoSelectedItemIds((prev) =>
                              checked ? Array.from(new Set([...prev, itemId])) : prev.filter((id) => id !== itemId),
                            );
                          }}
                        />
                      );
                    },
                  },
                  { title: t('app.kuaizhizao.salesOrder.materialCode'), dataIndex: 'material_code', width: 130, ellipsis: true },
                  { title: t('app.kuaizhizao.salesOrder.materialName'), dataIndex: 'material_name', width: 160, ellipsis: true },
                  { title: t('common.quantity'), dataIndex: 'quantity', width: 90, align: 'right', render: formatQuantity },
                  { title: t('app.kuaizhizao.salesOrder.colShippedQty'), dataIndex: 'pushed_quantity', width: 90, align: 'right', render: formatQuantity },
                  { title: t('app.kuaizhizao.salesOrder.colShippableQty'), dataIndex: 'max_push_quantity', width: 90, align: 'right', render: formatQuantity },
                ]}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.purchaseInquiry.push.previewNoLines')} />
            )}
            {pushPoPreviewData.tip ? (
              <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                {pushPoPreviewData.tip}
              </Typography.Paragraph>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </ListPageTemplate>
    </>
  );
};

export default PurchaseInquiriesPage;
