/**
 * 采购申请管理页面
 */

import React, { useRef, useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react';
import { rowActionKind } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom';
import { useLeaveFormTab } from '../../../../../components/uni-tabs/navigateClosingTab';
import { useDocumentCodeEditability } from '../../../../../hooks/useDocumentCodeEditability';
import { ActionType, ProColumns, ProForm, ProFormText, ProFormDatePicker, ProFormTextArea } from '@ant-design/pro-components';
import { App, Button, Tag, Space, Table, Form as AntForm, Input, InputNumber, Select, Row, Col, Checkbox, Empty, Spin, Typography, DatePicker, Modal, theme, Alert, Switch } from 'antd';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import {
  EyeOutlined,
  CheckOutlined,
  EditOutlined,
  SwapOutlined,
  FileSearchOutlined,
  DeleteOutlined,
  PlusOutlined,
  SendOutlined,
  AppstoreAddOutlined,
  ArrowLeftOutlined,
  ImportOutlined,
  PrinterOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { UniTable, readPersistedUniTableViewType } from '../../../../../components/uni-table';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
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
  UniAuditBatchMenuButton,
  UniCapabilityBatchButton,
  defaultAuditBatchAllowed,
  pickCapability,
  runCapabilityBatchLoop,
  useAuditBatchRunner,
  withDocumentSubmitCombinedItem,
  type AuditBatchAction,
  type UniBatchMenuItem,
} from '../../../../../components/uni-batch';
import { buildUniPushMenuItems, buildUniPushToolbarDisabledReason, UniPushToolbarButton } from '../../../../../components/uni-push';
import {
  UniPullQueryModal,
  isPullableScope,
  renderPullCapabilityTag,
  useUniPullQuery,
  buildPullQueryMaterialIdentityColumn,
  isPullOpenLineSelectable,
} from '../../../../../components/uni-pull-query';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import { SourceDocumentCode } from '../../../../../components/linked-document-code/SourceDocumentCode';
import { ListPageTemplate, DetailDrawerSection, DetailDrawerActions, MODAL_CONFIG, DocumentFormPageLayout, DocumentFormPageHeaderActions, DOCUMENT_DETAIL_PAGE_TITLE_STYLE } from '../../../../../components/layout-templates';
import { setCustomPageTitle, removeCustomPageTitle } from '../../../../../utils/customPageTitle';
import { useSubmitShortcut } from '../../../../../hooks/useSubmitShortcut';
import { buildFutureDateShortcutFieldProps, FutureDatePicker } from '../../../../../utils/futureDatePickerShortcuts';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import {
  buildDocumentDetailPartnerMaterialFormColumns,
  buildDocumentDetailSpecModelFormColumns,
  withMaterialLineFillMapping,
} from '../../sales-management/shared/materialLineFormDetail';
import { MaterialUnitSelect, prefetchMaterialsForUnitSelect } from '../../../../../components/material-unit-select';
import {
  DocumentLineDualQuantityFormCell, DocumentLineUnitSelect } from '../../../../../components/quantity-with-unit';
import {
  coerceDocumentLineQuantity,
  pickDocumentLineDualQuantityFields,
} from '../../../../../utils/materialDualQuantity';
import { resolveMaterialScenarioUnit } from '../../../../../utils/materialScenarioUnit';
import { UniMaterialBatchPicker } from '../../../../../components/uni-material-batch-picker';
import {
  EquipmentPersonSelect,
  resolveUserUuidById,
} from '../../../components/EquipmentPersonSelect';
import {
  PurchaseDepartmentFormField,
  resolvePurchaseDepartmentFromApplicant,
  resolvePurchaseDepartmentPayload,
  usePurchaseDepartmentOptions,
} from '../shared/PurchaseDepartmentFormField';
import type { User } from '../../../../../services/user';
import type { Material } from '../../../../master-data/types/material';
import { resolveDefaultSupplierIdFromMaterial } from '../../../../master-data/utils/materialDefaultSupplier';
import {
  applyPurchaseDocumentLineMaterialPricing,
  repriceUnlockedPurchaseDocumentLineIfNeeded,
  resolvePurchaseDocumentMaterialLinesPricing,
} from '../../../../master-data/utils/resolve-partner-material-price';
import { generateCode, testGenerateCode, getCodeRulePageConfig } from '../../../../../services/codeRule';
import { isAutoGenerateEnabled, getPageRuleCode } from '../../../../../utils/codeRulePage';
import { formatApiErrorDetail } from '../../../../../services/api';
import { downloadFile } from '../../../../../utils';
import { pickImportExampleValue } from '../../../../../utils/loadImportDictionaryValues';
import { useImportMaterialUnitOptions } from '../../../../master-data/hooks/useImportMaterialUnitOptions';

const LazyUniImport = lazy(() =>
  import('../../../../../components/uni-import').then((m) => ({ default: m.UniImport })),
);
import { isAuditedStatus, isPendingReviewStatus } from '../../../constants/documentStatus';
import {
  listPurchaseRequisitions,
  getPurchaseRequisition,
  createPurchaseRequisition,
  updatePurchaseRequisition,
  deletePurchaseRequisition,
  uniAuditPurchaseRequisition,
  submitPurchaseRequisition,
  submitPurchaseRequisitionForReview,
  withdrawPurchaseRequisitionSubmit,
  fixPurchaseRequisitionStatus,
  previewPushToPurchaseOrder,
  previewPushToInquiry,
  PurchaseRequisition,
  PurchaseRequisitionItem,
  type DocumentPushPreview,
} from '../../../services/purchase-requisition';
import {
  handoffDemandComputationToPurchaseRequisitionCreate,
  handoffRequisitionToPurchaseInquiryCreate,
  handoffRequisitionToPurchaseOrderCreate,
} from '../../../utils/documentFlowHandoff';
import {
  listDemandComputationPurchasePullLines,
  listDemandComputations,
  type DemandComputationPurchasePullLine,
} from '../../../services/demand-computation';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { useListSubmitReviewWithInitiator } from '../../../../../hooks/useListSubmitReviewWithInitiator';
import { useDocumentFormCommitAndSubmitReview } from '../../../../../hooks/useDocumentFormCommitAndSubmitReview';
import {
  buildPurchaseRequisitionLifecycleValueEnum,
  getPurchaseRequisitionLifecycle,
  resolvePurchaseRequisitionListApiParams,
} from '../../../utils/purchaseRequisitionLifecycle';
import { LIST_LIFECYCLE_STAGE_FIELD } from '../../../../../utils/listLifecycleStage';
import { formatPurchaseRequisitionSourceType } from '../../../utils/purchaseRequisitionSourceType';
import { renderDemandBusinessModeMarkerTag } from '../../../utils/businessMode';
import { getDocumentLifecycleStageTagProps } from '../../../../../utils/documentLifecycleStatusTag';
import { ListUniLifecycleCell } from '../../sales-management/shared/ListUniLifecycleCell';
import { createListAuditPhaseColumn } from '../../sales-management/shared/listAuditPhaseColumn';
import { getDataDictionaryByCode, getDictionaryItemList, type DictionaryItem } from '../../../../../services/dataDictionary';
import { mapSystemDictionaryItemOptions } from '../../../../../utils/systemDictionaryI18n';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import { alignProColumns, GLOBAL_DOC_DETAIL_TABLE_FIELD_RANK, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { DocumentPushProgressBar, DOCUMENT_PROGRESS_COLUMN_DEFAULTS, DETAIL_TABLE_PROGRESS_COLUMN_DEFAULTS, ratioToPushProgressPercent } from '../../sales-management/shared/DocumentPushProgressBar';
import { flattenDocumentDetailRows, resolveDetailTableViewMode } from '../../shared/detailTableFlatRows';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import {
  PurchaseRequisitionDetailDrawer,
  PURCHASE_REQUISITION_WORKFLOW_PROPS,
} from './components/PurchaseRequisitionDetailDrawer';
import {
  PurchaseRequisitionLineStockCell,
  PurchaseRequisitionLineStockProvider,
} from './components/PurchaseRequisitionLineStock';
import { PurchaseRequisitionFormFieldSettings } from './components/PurchaseRequisitionFormFieldSettings';
import { resolvePurchaseRequisitionFormFieldVisibility } from './purchaseRequisitionFormFieldPrefs';
import {
  KUAIZHIZAO_DOC_HOST,
  loadMaterialFormReferenceList,
  loadSupplierFormReferenceList,
} from '../../../../../utils/documentFormReferenceLoad';
import {
  collectImportMaterialCodes,
  findMaterialByImportCode,
  normalizeImportMaterialCode,
  resolveMaterialsByCodesForImport,
} from '../../../../master-data/utils/materialImportResolve';
import { SupplierSelectDropdown } from '../../../../master-data/components/SupplierSelectDropdown';
import type { Supplier } from '../../../../master-data/types/supply-chain';
import { useTranslation } from 'react-i18next';
import { useGlobalStore, useUserPreferenceStore } from '../../../../../stores';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { useNumericPrecision } from '../../../../../hooks/useNumericPrecision';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useKuaizhizaoPrintModal } from '../../../hooks/useKuaizhizaoPrintModal';
import { buildKuaizhizaoPullCreateMenuItems, resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import {
  handoffDemandComputationToPurchaseRequisitionCreate,
  handoffRequisitionToPurchaseInquiryCreate,
  handoffRequisitionToPurchaseOrderCreate,
  handoffSalesOrdersToPurchaseRequisitionCreate,
  hydrateDocumentFlowCreateFormValues,
} from '../../../utils/documentFlowHandoff';
import {
  listPurchaseRequisitionSalesOrderPullLines,
  listPurchaseRequisitionSalesOrderPullOrders,
  type PurchaseRequisitionSalesOrderPullLine,
} from '../../../services/purchase';
import { mapAttachmentsToUploadList, normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import {
  buildDocumentLineAttachmentsFormColumn,
  DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY,
} from '../../../components/documentLineAttachmentsColumns';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import { buildDocumentAttachmentsListColumn } from '../../../components/documentAttachmentsListColumn';
import { countDocumentAttachments } from '../../../utils/documentAttachments';
import { formatBusinessDateOnly, formatDateTime, formatNumber, formatQuantity, todaySiteDateString, formatCurrencyAmount, formatCurrencyPrice } from '../../../../../utils/format';
import { computeSimpleDocumentLineTotal } from '../../../utils/documentLineAmounts';
import { QuantityWithUnitDisplay } from '../../../../../components/quantity-with-unit';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { extractProTableSort } from '../../../../../utils/tableQueryKey';
import { coerceFormDate, formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import {
  purchaseRequisitionCapabilityReasonMessage,
} from '../../../../../hooks/useDocumentCapabilities';
import { fetchAllListItems } from '../../../../../utils/fetchAllListPages';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import {
  buildDocumentCreateDraftKey,
  clearDocumentFormDraft,
  getDocumentFormDraft,
  setDocumentFormDraft,
} from '../../../../../utils/documentFormDraftCache';

const INITIAL_PR_FORM_ITEM_ROW = {
  material_id: undefined,
  material_code: '',
  material_name: '',
  material_spec: '',
  material_model: '',
  partner_material_code: '',
  partner_material_name: '',
  unit: '件',
  quantity: 1,
  suggested_unit_price: 0,
  required_date: undefined,
  demand_computation_item_id: undefined,
  supplier_id: undefined,
  notes: undefined,
};

const INITIAL_CREATE_ITEMS = [{ ...INITIAL_PR_FORM_ITEM_ROW }];

const PR_DRAFT_HEADER_NUMBER_FIELDS = ['applicant_id', 'department_id'] as const;
const PR_DRAFT_LINE_NUMBER_FIELDS = [
  'quantity',
  'aux_quantity',
  'unit_conversion_rate',
  'suggested_unit_price',
  'material_id',
  'supplier_id',
  'demand_computation_item_id',
] as const;

function healDraftNumber(value: unknown): unknown {
  if (typeof value === 'number' || value == null || value === '') return value;
  const recovered = coerceDocumentLineQuantity(value);
  return recovered == null ? value : recovered;
}

/** 草稿曾把 0、1 存成日期对象。恢复时这些字段必须仍是数字。 */
function healPurchaseRequisitionDraft(values: Record<string, unknown>): Record<string, unknown> {
  const next: Record<string, unknown> = { ...values };
  for (const key of PR_DRAFT_HEADER_NUMBER_FIELDS) {
    if (key in next) next[key] = healDraftNumber(next[key]);
  }
  const items = normalizeFormListItems<Record<string, unknown>>(next.items);
  if (items.length > 0) {
    next.items = items.map((row) => {
      const healed: Record<string, unknown> = { ...row };
      for (const key of PR_DRAFT_LINE_NUMBER_FIELDS) {
        if (key in healed) healed[key] = healDraftNumber(healed[key]);
      }
      return healed;
    });
  }
  return next;
}

/** 下推/草稿灌入采购申请新建页。明细必须进 initialValues，禁止灌完再改掉 flow 查询。 */
function buildPurchaseRequisitionHandoffFormValues(flowBody: Record<string, unknown>): {
  formValues: Record<string, unknown>;
  extras: Record<string, unknown> | null;
} {
  const {
    _documentFlowMeta: _meta,
    documentFlowSourceType,
    documentFlowDemandComputationItemIds,
    documentFlowDemandComputationIds,
    documentFlowReplenishmentSuggestionIds,
    documentFlowSalesOrderId,
    ...formValues
  } = flowBody;
  const hydrated = hydrateDocumentFlowCreateFormValues(formValues);
  const healed = healPurchaseRequisitionDraft(hydrated);
  if (healed.requisition_date == null || healed.requisition_date === '') {
    healed.requisition_date = dayjs();
  }
  const normalizedItems = normalizeFormListItems<Record<string, unknown>>(healed.items).map((item) => {
    const midRaw = item.material_id ?? item.materialId;
    const mid = midRaw != null ? Number(midRaw) : NaN;
    const qtyRaw = item.quantity ?? item.ordered_quantity;
    const qty = Number(qtyRaw);
    return {
      ...item,
      material_id: Number.isFinite(mid) && mid > 0 ? mid : undefined,
      material_code: item.material_code ?? item.materialCode ?? '',
      material_name: item.material_name ?? item.materialName ?? '',
      material_spec: item.material_spec ?? item.materialSpec ?? '',
      material_model: item.material_model ?? item.materialModel ?? '',
      unit: item.unit || '件',
      quantity: Number.isFinite(qty) && qty > 0 ? qty : 1,
      suggested_unit_price: Number(item.suggested_unit_price ?? item.suggestedUnitPrice ?? 0),
      required_date: item.required_date != null ? coerceFormDate(item.required_date) : undefined,
      demand_computation_item_id:
        item.demand_computation_item_id ?? item.demandComputationItemId ?? undefined,
    };
  });
  return {
    formValues: {
      ...healed,
      items: normalizedItems.length > 0 ? normalizedItems : [{ ...INITIAL_PR_FORM_ITEM_ROW }],
    },
    extras: documentFlowSourceType
      ? {
          documentFlowSourceType,
          documentFlowDemandComputationItemIds,
          documentFlowDemandComputationIds,
          documentFlowReplenishmentSuggestionIds,
          documentFlowSalesOrderId,
        }
      : null,
  };
}

const SuggestedPriceStoreRepair: React.FC<{
  form: {
    getFieldValue?: (name: any) => any;
    setFieldValue?: (name: any, value: any) => void;
  } | null | undefined;
  rowIndex: number;
  raw: unknown;
}> = ({ form, rowIndex, raw }) => {
  const repairKey = typeof raw === 'number' || raw == null || raw === '' ? '' : 'bad';
  useEffect(() => {
    if (!repairKey || !form?.getFieldValue || !form.setFieldValue) return;
    const current = form.getFieldValue(['items', rowIndex, 'suggested_unit_price']);
    if (typeof current === 'number' && Number.isFinite(current)) return;
    if (current == null || current === '') return;
    const recovered = coerceDocumentLineQuantity(current);
    if (recovered == null) return;
    form.setFieldValue(['items', rowIndex, 'suggested_unit_price'], recovered);
  }, [form, repairKey, rowIndex]);
  return null;
};

type PurchaseRequisitionItemRow = PurchaseRequisitionItem & {
  _rowKey: string;
  _headerId?: number | string;
  requisition_id: number;
  requisition_code?: string;
  requisition_name?: string;
  source_type?: string;
  source_code?: string;
  applicant_id?: number | null;
  applicant_name?: string | null;
  department_id?: number | null;
  department_name?: string | null;
  status?: string;
  review_status?: string;
  downstream_push_progress?: number;
  lifecycle?: Record<string, unknown>;
  capabilities?: PurchaseRequisition['capabilities'];
  audit?: PurchaseRequisition['audit'];
  created_at?: string;
  updated_at?: string;
  created_by_name?: string;
  updated_by_name?: string;
};

const PURCHASE_REQUISITION_LIST_PERSISTENCE_ID =
  'apps.kuaizhizao.pages.purchase-management.purchase-requisitions-rank-v11';

const PURCHASE_REQUISITION_ORDER_TYPE_FALLBACK: Pick<DictionaryItem, 'value' | 'label' | 'is_system_managed' | 'sort_order'>[] = [
  { value: '标准采购', label: '标准采购', is_system_managed: true, sort_order: 0 },
  { value: '资产采购', label: '资产采购', is_system_managed: true, sort_order: 1 },
  { value: '服务采购', label: '服务采购', is_system_managed: true, sort_order: 2 },
];

type PullDemandComputationCandidate = DemandComputationPurchasePullLine;

function renderPurchaseRequisitionRowActions(nodes: React.ReactNode[], keyPrefix: string): React.ReactNode {
  return nodes;
}

const PURCHASE_REQUISITION_RESOURCE = 'kuaizhizao:purchase-requisition';

const PURCHASE_REQUISITION_LIST_PATH = '/apps/kuaizhizao/purchase-management/purchase-requisitions';
const PURCHASE_REQUISITION_CREATE_PATH = `${PURCHASE_REQUISITION_LIST_PATH}/new`;
const purchaseRequisitionEditPath = (id: number | string) => `${PURCHASE_REQUISITION_LIST_PATH}/${id}/edit`;

const PurchaseRequisitionsPage: React.FC = () => {
  const { t } = useTranslation();
  const { quantity: quantityDecimals, price: priceDecimals, amount: amountDecimals } = useNumericPrecision();
  const pushToPurchaseOrderAction = resolveKuaizhizaoDocumentAction(t, 'purchase_order.pull_from_requisition');
  const pushToInquiryAction = resolveKuaizhizaoDocumentAction(t, 'purchase_inquiry.pull_from_requisition');
  const pullFromDemandComputationAction = resolveKuaizhizaoDocumentAction(t, 'purchase_requisition.pull_from_demand_computation');
  const pullFromSalesOrderAction = resolveKuaizhizaoDocumentAction(t, 'purchase_requisition.pull_from_sales_order');
  const currentUser = useCurrentUser();
  const {
    options: departmentOptions,
    loading: departmentOptionsLoading,
    resolveName: resolveDepartmentName,
  } = usePurchaseDepartmentOptions();
  const purchaseRequestAuditEnabled = useAuditRequired('purchase_request', false);
  const userPreferences = useUserPreferenceStore((s) => s.preferences);
  const showRequisitionNameField = useMemo(
    () => resolvePurchaseRequisitionFormFieldVisibility(userPreferences).requisition_name,
    [userPreferences],
  );
  const purchaseRequisitionPerms = useResourcePermissions(PURCHASE_REQUISITION_RESOURCE);
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const isCreatePage = location.pathname.endsWith('/purchase-requisitions/new');
  const editRouteMatch = location.pathname.match(/\/purchase-requisitions\/(\d+)\/edit$/);
  const editRouteId = editRouteMatch ? Number(editRouteMatch[1]) : null;
  const isEditPage = editRouteId != null && Number.isFinite(editRouteId) && editRouteId > 0;
  const isFormPage = isCreatePage || isEditPage;
  const editingId = isEditPage ? editRouteId : null;
  const prCodeEditability = useDocumentCodeEditability(
    'kuaizhizao-purchase-requisition',
    editingId,
  );
  const prFormDraftKey = useMemo(
    () =>
      isFormPage
        ? buildDocumentCreateDraftKey('kuaizhizao:purchase-requisition', location.pathname, location.search)
        : null,
    [isFormPage, location.pathname, location.search],
  );
  const formPageInitKeyRef = useRef<string | null>(null);
  const purchaseRequisitionCreateSeed = useMemo(() => {
    if (!isCreatePage) return null;
    const flowBodyFromState =
      location.state &&
      typeof location.state === 'object' &&
      (location.state as { documentFlowCreate?: unknown }).documentFlowCreate &&
      typeof (location.state as { documentFlowCreate?: unknown }).documentFlowCreate === 'object'
        ? (location.state as { documentFlowCreate: Record<string, unknown> }).documentFlowCreate
        : null;
    const draft = prFormDraftKey ? getDocumentFormDraft<Record<string, unknown>>(prFormDraftKey) : null;
    const flowBody = flowBodyFromState ?? draft;
    if (!flowBody || Object.keys(flowBody).length === 0) return null;
    return buildPurchaseRequisitionHandoffFormValues(flowBody).formValues;
  }, [isCreatePage, location.state, prFormDraftKey]);
  const { token } = theme.useToken();
  const prqDetailDrawerZIndex = token.zIndexPopupBase;
  const { message: messageApi, modal: modalApi } = App.useApp();
  const [orderTypeOptions, setOrderTypeOptions] = useState<Array<{ label: string; value: string }>>(() =>
    mapSystemDictionaryItemOptions('ORDER_TYPE', PURCHASE_REQUISITION_ORDER_TYPE_FALLBACK as DictionaryItem[], t),
  );
  const [orderTypeLoading, setOrderTypeLoading] = useState(false);
  useEffect(() => {
    const loadOrderType = async () => {
      setOrderTypeLoading(true);
      try {
        const dict = await getDataDictionaryByCode('ORDER_TYPE');
        const items = await getDictionaryItemList(dict.uuid, true);
        const sorted = [...items].sort((a, b) => a.sort_order - b.sort_order);
        setOrderTypeOptions(mapSystemDictionaryItemOptions('ORDER_TYPE', sorted, t));
      } catch {
        setOrderTypeOptions(
          mapSystemDictionaryItemOptions('ORDER_TYPE', PURCHASE_REQUISITION_ORDER_TYPE_FALLBACK as DictionaryItem[], t),
        );
        messageApi.info(t('app.kuaizhizao.purchaseOrder.orderTypeFallback'));
      } finally {
        setOrderTypeLoading(false);
      }
    };
    void loadOrderType();
  }, [messageApi, t]);
  const actionRef = useRef<ActionType>(null);
  const tableRowsRef = useRef<PurchaseRequisition[]>([]);
  const [viewTypeState, setViewTypeState] = useState<'table' | 'detailTable' | 'help'>(() =>
    readPersistedUniTableViewType(PURCHASE_REQUISITION_LIST_PERSISTENCE_ID, 'table', [
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
  const deepLinkHandledRef = useRef<string | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [detailFlatRows, setDetailFlatRows] = useState<PurchaseRequisitionItemRow[]>([]);

  const resolveRequisitionIdFromSelectionKey = useCallback(
    (key: React.Key): number | null => {
      if (dataViewMode === 'order') {
        const id = Number(key);
        return Number.isFinite(id) && id > 0 ? id : null;
      }
      const row = detailFlatRows.find((item) => String(item._rowKey) === String(key));
      const id = Number(row?.requisition_id ?? row?._headerId);
      return Number.isFinite(id) && id > 0 ? id : null;
    },
    [dataViewMode, detailFlatRows],
  );

  const selectedRequisitionsForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
        .filter((row): row is PurchaseRequisition => row != null),
    [selectedRowKeys],
  );

  const purchaseRequisitionAuditBatchHandlers = useMemo(
    () => ({
      submit: (id: number) => uniAuditPurchaseRequisition(id, 'submit'),
      withdraw: (id: number) => withdrawPurchaseRequisitionSubmit(id),
      approve: (id: number) => uniAuditPurchaseRequisition(id, 'approve'),
      revoke: (id: number) => uniAuditPurchaseRequisition(id, 'revoke'),
    }),
    [],
  );
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();

  const handlePurchaseRequisitionAuditBatchSuccess = useCallback(() => {
    setSelectedRowKeys([]);
    invalidateMenuBadgeCounts();
    actionRef.current?.reload();
  }, [invalidateMenuBadgeCounts]);
  const leavePurchaseRequisitionFormPage = useLeaveFormTab(PURCHASE_REQUISITION_LIST_PATH);

  const {
    runAction: runPurchaseRequisitionAuditBatch,
    auditModal: purchaseRequisitionAuditModal,
  } = useAuditBatchRunner<PurchaseRequisition>({
    permGates: purchaseRequisitionPerms,
    handlers: purchaseRequisitionAuditBatchHandlers,
    onBatchComplete: handlePurchaseRequisitionAuditBatchSuccess,
    resolveIdFromKey: resolveRequisitionIdFromSelectionKey,
    auditEntity: {
      entityType: 'purchase_request',
      entityName: t('app.kuaizhizao.purchaseRequisition.entityName'),
    },
  });

  const {
    runSubmitReviewWithInitiator: runPurchaseRequisitionSubmitReviewWithInitiator,
    listInitiatorModal: purchaseRequisitionListInitiatorModal,
  } = useListSubmitReviewWithInitiator({
    entityType: 'purchase_request',
    entityLabel: t('app.kuaizhizao.purchaseRequisition.entityName'),
    submitTitle: t('app.kuaizhizao.purchaseRequisition.toolbar.submitReview'),
    submitReview: (id, payload) => submitPurchaseRequisitionForReview(id, payload ?? {}),
  });

  const purchaseRequisitionToolbarAuditMenus = useMemo(() => {
    const canPerm = (action: AuditBatchAction) => {
      const perm = action === 'approve' ? 'audit' : action === 'submit' ? 'submit' : 'revoke';
      return purchaseRequisitionPerms.canAction?.(perm) ?? false;
    };
    const item = (
      key: string,
      action: AuditBatchAction,
      label: string,
      capKey: string,
      rows: PurchaseRequisition[],
    ): UniBatchMenuItem => ({
      key,
      label,
      disabled:
        selectedRequisitionsForBatch.length > 0
        && !defaultAuditBatchAllowed(rows, canPerm(action), capKey, (row) => row),
      onClick: () =>
        runPurchaseRequisitionAuditBatch(
          action,
          rows.map((row) => row.id!).filter((id): id is number => id != null && Number(id) > 0),
          rows,
          purchaseRequestAuditEnabled,
        ),
    });
    const capOn = (row: PurchaseRequisition, capKey: string) => pickCapability(row, capKey)?.allowed === true;
    const submittedRows = selectedRequisitionsForBatch.filter(
      (row) => String(row.status || '').trim() === 'SUBMITTED' && capOn(row, 'withdraw_submit'),
    );
    const pendingRows = selectedRequisitionsForBatch.filter(
      (row) => isPendingReviewStatus(row.status) && capOn(row, 'withdraw_submit'),
    );
    const submitReviewRows = selectedRequisitionsForBatch.filter((row) =>
      (row.audit?.allowed_actions ?? []).includes('submit_review'),
    );
    const canSubmitReview = purchaseRequisitionPerms.canAction?.('submit') ?? false;
    const submitRows = selectedRequisitionsForBatch.filter((row) => capOn(row, 'submit'));
    const submitMenuItem = item('submit', 'submit', t('common.submit'), 'submit', submitRows);
    const submitDisabled = Boolean(submitMenuItem.disabled);
    return {
      submit: withDocumentSubmitCombinedItem(
        [
          submitMenuItem,
          item('withdraw-submit', 'withdraw', t('app.kuaizhizao.purchaseRequisition.toolbar.withdrawSubmit'), 'withdraw_submit', submittedRows),
          {
            key: 'submit-review',
            label: t('app.kuaizhizao.purchaseRequisition.toolbar.submitReview'),
            disabled: selectedRequisitionsForBatch.length > 0 && !(canSubmitReview && submitReviewRows.length > 0),
            onClick: () => runCapabilityBatchLoop({
              keys: submitReviewRows
                .map((row) => row.id)
                .filter((id): id is number => id != null && Number(id) > 0),
              records: submitReviewRows,
              capabilityKey: 'submit_review',
              permAllowed: canSubmitReview,
              notAllowedMessage: t('app.kuaizhizao.purchaseRequisition.toolbar.submitReviewNotAllowed'),
              onRun: (id) => runPurchaseRequisitionSubmitReviewWithInitiator(id),
              message: messageApi,
              t,
              onSuccess: handlePurchaseRequisitionAuditBatchSuccess,
            }),
          },
        ],
        {
          t,
          message: messageApi,
          disabled: submitDisabled,
          commitRecords: submitRows,
          permAllowed: canSubmitReview,
          resolveId: (key) => resolveRequisitionIdFromSelectionKey(key),
          commit: (id) => submitPurchaseRequisition(id),
          submitReview: (id) => runPurchaseRequisitionSubmitReviewWithInitiator(id),
          onSuccess: handlePurchaseRequisitionAuditBatchSuccess,
        },
      ),
      audit: [
        item('approve', 'approve', t('components.uniAction.audit'), 'approve', selectedRequisitionsForBatch.filter((row) => capOn(row, 'approve'))),
        item('withdraw-review', 'withdraw', t('app.kuaizhizao.purchaseRequisition.toolbar.withdrawReview'), 'withdraw_submit', pendingRows),
        item('revoke', 'revoke', t('app.kuaizhizao.purchaseRequisition.toolbar.revoke'), 'revoke_approval', selectedRequisitionsForBatch.filter((row) => capOn(row, 'revoke_approval'))),
      ] satisfies UniBatchMenuItem[],
    };
  }, [
    handlePurchaseRequisitionAuditBatchSuccess,
    messageApi,
    purchaseRequestAuditEnabled,
    purchaseRequisitionPerms,
    resolveRequisitionIdFromSelectionKey,
    runPurchaseRequisitionAuditBatch,
    runPurchaseRequisitionSubmitReviewWithInitiator,
    selectedRequisitionsForBatch,
    t,
  ]);

  const {
    runAfterPersist: runPurchaseRequisitionSaveAndAudit,
    initiatorModal: purchaseRequisitionInitiatorModal,
  } = useDocumentFormCommitAndSubmitReview({
    entityType: 'purchase_request',
    entityLabel: t('app.kuaizhizao.purchaseRequisition.entityName'),
    commit: submitPurchaseRequisition,
    submitReview: (id, payload) => submitPurchaseRequisitionForReview(id, payload ?? {}),
  });
  const [detailVisible, setDetailVisible] = useState(false);
  const [currentReq, setCurrentReq] = useState<PurchaseRequisition | null>(null);
  const [supplierList, setSupplierList] = useState<Array<{ id: number; code?: string; name: string }>>([]);
  const createFormRef = useRef<any>(null);
  const submitAfterSaveRef = useRef(false);
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  /** 上一次表头要求到货日，用于改表头时同步曾跟随表头的明细行（对齐采购订单/销售订单） */
  const lastHeaderDeliveryRef = useRef<ReturnType<typeof dayjs> | null>(null);
  /** 程序化回填（服务端/草稿）期间禁止 onValuesChange 写草稿，避免空价覆盖手填 */
  const prFormHydratingRef = useRef(false);
  /** 申请人部门 uuid：部门树晚于选人加载时，用于回填 department_id */
  const applicantDepartmentUuidRef = useRef<string | undefined>(undefined);

  const applyHeaderDeliveryToItemLines = useCallback((delivery: unknown) => {
    const coerced = coerceFormDate(delivery);
    if (coerced == null) return;
    const prevHeader = lastHeaderDeliveryRef.current;
    const items = normalizeFormListItems<any>(createFormRef.current?.getFieldValue('items'));
    if (!items.length) return;
    let changed = false;
    const next = items.map((it: Record<string, unknown>) => {
      const lineDate = coerceFormDate(it.required_date);
      if (lineDate == null) {
        changed = true;
        return { ...it, required_date: coerced };
      }
      if (prevHeader && lineDate.isSame(prevHeader, 'day')) {
        changed = true;
        return { ...it, required_date: coerced };
      }
      return it;
    });
    lastHeaderDeliveryRef.current = coerced;
    if (changed) {
      createFormRef.current?.setFieldsValue({ items: next });
    }
  }, []);

  const resolveHeaderRequiredDateDefault = useCallback(() => {
    const mainRequired = createFormRef.current?.getFieldValue('required_date');
    const coerced = coerceFormDate(mainRequired);
    if (coerced != null) return coerced;
    return undefined;
  }, []);
  const [previewCode, setPreviewCode] = useState<string | null>(null);
  const [effectiveRuleCode, setEffectiveRuleCode] = useState<string | null>(null);
  const [effectiveAutoGen, setEffectiveAutoGen] = useState<boolean | null>(null);
  const [effectiveAllowManualEdit, setEffectiveAllowManualEdit] = useState<boolean | null>(null);
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false);
  const [materialPickSourceType, setMaterialPickSourceType] = useState<string | undefined>();
  const [importModalVisible, setImportModalVisible] = useState(false);
  const materialUnitImport = useImportMaterialUnitOptions();
  const requisitionLineUnitOptions = materialUnitImport.options;
  const requisitionLineImportColumnOptions = useMemo(
    () => [
      undefined,
      undefined,
      requisitionLineUnitOptions,
      undefined,
      undefined,
      undefined,
      undefined,
    ],
    [requisitionLineUnitOptions],
  );


  const [pushPoPreviewOpen, setPushPoPreviewOpen] = useState(false);
  const [pushPoPreviewLoading, setPushPoPreviewLoading] = useState(false);
  const [pushPoPreviewConfirming, setPushPoPreviewConfirming] = useState(false);
  const [pushPoPreviewData, setPushPoPreviewData] = useState<DocumentPushPreview | null>(null);
  const [pushPoTarget, setPushPoTarget] = useState<PurchaseRequisition | null>(null);
  const [pushPoDetailItems, setPushPoDetailItems] = useState<PurchaseRequisitionItem[]>([]);
  const [pushPoSuppliers, setPushPoSuppliers] = useState<Array<{ id: number; code?: string; name: string }>>([]);

  const [pushInquiryPreviewOpen, setPushInquiryPreviewOpen] = useState(false);
  const [pushInquiryPreviewLoading, setPushInquiryPreviewLoading] = useState(false);
  const [pushInquiryPreviewConfirming, setPushInquiryPreviewConfirming] = useState(false);
  const [pushInquiryPreviewData, setPushInquiryPreviewData] = useState<DocumentPushPreview | null>(null);
  const [pushInquiryTarget, setPushInquiryTarget] = useState<PurchaseRequisition | null>(null);
  const [pushInquirySelectedItemIds, setPushInquirySelectedItemIds] = useState<number[]>([]);
  const [pullSourceComputationId, setPullSourceComputationId] = useState<number | undefined>();
  const pullSourceComputationIdRef = useRef<number | undefined>(undefined);
  const [pullSourceOptions, setPullSourceOptions] = useState<Array<{ value: number; label: string }>>([]);
  const [pullSourceSalesOrderId, setPullSourceSalesOrderId] = useState<number | undefined>();
  const pullSourceSalesOrderIdRef = useRef<number | undefined>(undefined);
  const [pullSourceSalesOrderOptions, setPullSourceSalesOrderOptions] = useState<
    Array<{ value: number; label: string }>
  >([]);
  const [pullDateConfirmOpen, setPullDateConfirmOpen] = useState(false);
  const [pullDateConfirming, setPullDateConfirming] = useState(false);
  const [pullDateConfirmRows, setPullDateConfirmRows] = useState<
    Array<PullDemandComputationCandidate & { required_date?: string | null }>
  >([]);
  const [pullBulkRequiredDate, setPullBulkRequiredDate] = useState<dayjs.Dayjs | null>(null);

  const [prTrackingRefreshKey, setPrTrackingRefreshKey] = useState(0);

  const ensureSupplierList = useCallback(async (): Promise<Array<{ id: number; code?: string; name: string }>> => {
    if (supplierList.length > 0) return supplierList;
    const list = await loadSupplierFormReferenceList(KUAIZHIZAO_DOC_HOST.purchaseRequisition);
    setSupplierList(list);
    return list;
  }, [supplierList]);


  const appendRequisitionItemsFromMaterials = useCallback(
    async (selected: Material[]) => {
      if (!selected?.length) return;
      const isEmptyItemRow = (row: any) => {
        if (row == null) return true;
        if (row.material_id != null && row.material_id !== '') return false;
        const code = row.material_code;
        return code == null || String(code).trim() === '';
      };
      const requisitionDate = createFormRef.current?.getFieldValue('requisition_date');
      const asOf =
        requisitionDate != null
          ? dayjs.isDayjs(requisitionDate)
            ? requisitionDate
            : dayjs(requisitionDate)
          : dayjs();
      const priced = await resolvePurchaseDocumentMaterialLinesPricing(selected, { asOf });
      const defaultDate = resolveHeaderRequiredDateDefault();
      const queue = priced.map(
        ({ material: m, unitPrice, material_spec, material_model, partner_material_code, partner_material_name }) => ({
        material_id: (m as Material).id,
        material_code: (m as Material).mainCode ?? (m as Material).code ?? '',
        material_name: (m as Material).name ?? '',
        material_spec: material_spec ?? (m as Material).specification ?? '',
        material_model: material_model ?? '',
        partner_material_code: partner_material_code ?? '',
        partner_material_name: partner_material_name ?? '',
        unit: resolveMaterialScenarioUnit(m as Material, 'purchase'),
        quantity: 1,
        suggested_unit_price: unitPrice,
        required_date: defaultDate,
        demand_computation_item_id: undefined,
        supplier_id: resolveDefaultSupplierIdFromMaterial(m as Material),
        notes: undefined,
      }),
      );
      const items = [...normalizeFormListItems<any>(createFormRef.current?.getFieldValue('items'))].map(
        (row: any) => ({ ...row }),
      );
      for (let i = 0; i < items.length && queue.length > 0; i++) {
        if (isEmptyItemRow(items[i])) {
          items[i] = queue.shift()!;
        }
      }
      while (queue.length > 0) {
        items.push(queue.shift()!);
      }
      createFormRef.current?.setFieldsValue({ items });
      messageApi.success(t('app.kuaizhizao.common.materialBatchAdded', { count: selected.length }));
    },
    [messageApi, resolveHeaderRequiredDateDefault, t]
  );

  const handleItemImport = useCallback(
    async (data: any[][]) => {
      const rows = data.slice(2);
      const defaultDate = resolveHeaderRequiredDateDefault();
      const loaded = await loadMaterialFormReferenceList(KUAIZHIZAO_DOC_HOST.purchaseRequisition);
      const materials = await resolveMaterialsByCodesForImport(
        collectImportMaterialCodes(rows, 0),
        loaded,
      );
      const newItems = rows
        .map((row) => {
          const materialCode = normalizeImportMaterialCode(row[0]);
          const spec = String(row[1] || '').trim();
          const unitRaw = String(row[2] || '').trim();
          const unit = materialUnitImport.parse(unitRaw) || unitRaw;
          const quantity = parseFloat(row[3]) || 0;
          const suggestedPrice = parseFloat(row[4]) || 0;
          const requiredDate = row[5];
          const notes = String(row[6] || '').trim();

          if (!materialCode) return null;
          const mat = findMaterialByImportCode(materials, materialCode);

          return {
            ...INITIAL_PR_FORM_ITEM_ROW,
            material_id: mat?.id,
            material_code: mat?.mainCode || mat?.code || materialCode,
            material_name: mat?.name || '',
            material_spec: mat?.specification || spec,
            unit: mat?.baseUnit || unit || '件',
            quantity: quantity || 1,
            suggested_unit_price: suggestedPrice,
            required_date:
              requiredDate && dayjs(requiredDate).isValid() ? dayjs(requiredDate) : defaultDate,
            supplier_id: mat ? resolveDefaultSupplierIdFromMaterial(mat as Material) : undefined,
            notes: notes || undefined,
          };
        })
        .filter((it): it is NonNullable<typeof it> => it !== null);

      if (newItems.length === 0) {
        messageApi.warning(t('app.kuaizhizao.purchaseRequisition.importNoValidData'));
        return;
      }

      const currentItems = normalizeFormListItems<any>(createFormRef.current?.getFieldValue('items'));
      createFormRef.current?.setFieldsValue({ items: [...currentItems, ...newItems] });
      messageApi.success(t('app.kuaizhizao.salesOrder.importSuccessItems', { count: newItems.length }));
      setImportModalVisible(false);
    },
    [messageApi, materialUnitImport, resolveHeaderRequiredDateDefault, t],
  );

  const initialCreateItems = INITIAL_CREATE_ITEMS;

  const loadPurchaseRequisitionEditForm = useCallback(
    async (id: number) => {
      void ensureSupplierList();
      setPreviewCode(null);
      setEffectiveRuleCode(null);
      setEffectiveAutoGen(null);
      setEffectiveAllowManualEdit(null);
      // 先取出草稿，避免回填服务端空价时 onValuesChange 把草稿冲掉
      const draftSnapshot =
        prFormDraftKey ? getDocumentFormDraft<Record<string, unknown>>(prFormDraftKey) : null;
      prFormHydratingRef.current = true;
      try {
        createFormRef.current?.resetFields();
        const detail = await getPurchaseRequisition(id);
        const status = (detail.status ?? '').toString().trim();
        if (!['草稿', 'draft', 'DRAFT'].includes(status)) {
          messageApi.error(t('app.kuaizhizao.purchaseRequisition.onlyDraftEditable'));
          leavePurchaseRequisitionFormPage();
          return;
        }
        const applicantUuid = await resolveUserUuidById(detail.applicant_id);
        const baseValues = {
          requisition_code: detail.requisition_code ?? '',
          order_type: detail.order_type || '标准采购',
          requisition_name: detail.requisition_name ?? '',
          requisition_date: detail.requisition_date ? dayjs(detail.requisition_date) : dayjs(),
          applicant_uuid: applicantUuid,
          applicant_id: detail.applicant_id,
          applicant_name: detail.applicant_name ?? '',
          department_id: detail.department_id ?? undefined,
          department_name: detail.department_name ?? undefined,
          required_date: detail.required_date ? dayjs(detail.required_date) : undefined,
          notes: detail.notes,
          attachments: mapAttachmentsToUploadList(detail.attachments),
          items:
            detail.items && detail.items.length > 0
              ? detail.items.map((it) => ({
                  material_id: it.material_id,
                  material_code: it.material_code ?? '',
                  material_name: it.material_name ?? '',
                  material_spec: it.material_spec ?? '',
                  material_model: it.material_model ?? '',
                  partner_material_code: it.partner_material_code ?? '',
                  partner_material_name: it.partner_material_name ?? '',
                  unit: it.unit ?? '件',
                  quantity: Number(it.quantity ?? 1),
                  suggested_unit_price: Number(it.suggested_unit_price ?? 0),
                  required_date: it.required_date ? dayjs(it.required_date) : undefined,
                  demand_computation_item_id: it.demand_computation_item_id,
                  supplier_id: it.supplier_id,
                  notes: it.notes,
                  attachments: mapAttachmentsToUploadList(it.attachments),
                }))
              : [{ ...INITIAL_PR_FORM_ITEM_ROW }],
        };
        createFormRef.current?.setFieldsValue(baseValues);
        if (draftSnapshot && Object.keys(draftSnapshot).length > 0) {
          createFormRef.current?.setFieldsValue(draftSnapshot);
        }
        // 表头有到货日、行为空时补入（与改表头带入同一套逻辑）
        lastHeaderDeliveryRef.current = null;
        applyHeaderDeliveryToItemLines(
          createFormRef.current?.getFieldValue('required_date') ?? baseValues.required_date,
        );
      } catch {
        messageApi.error(t('app.kuaizhizao.purchaseRequisition.loadFailed'));
        leavePurchaseRequisitionFormPage();
      } finally {
        prFormHydratingRef.current = false;
      }
    },
    [
      applyHeaderDeliveryToItemLines,
      ensureSupplierList,
      leavePurchaseRequisitionFormPage,
      messageApi,
      prFormDraftKey,
      t,
    ],
  );

  const handleEdit = useCallback(
    (record: PurchaseRequisition) => {
      const s = (record.status ?? '').toString().trim();
      if (!['草稿', 'draft', 'DRAFT'].includes(s) || record.id == null) return;
      navigate(purchaseRequisitionEditPath(record.id));
    },
    [navigate],
  );

  const lifecycleValueEnum = useMemo(
    () => buildPurchaseRequisitionLifecycleValueEnum(purchaseRequestAuditEnabled),
    [purchaseRequestAuditEnabled],
  );
  const purchaseRequisitionAuditColumn = useMemo(
    () => createListAuditPhaseColumn<PurchaseRequisition>({ t, auditEnabled: purchaseRequestAuditEnabled }),
    [t, purchaseRequestAuditEnabled],
  );
  const resolveRequisitionPushPercent = useCallback((record: PurchaseRequisition): number => {
    const stageName = String(getPurchaseRequisitionLifecycle(record, purchaseRequestAuditEnabled).stageName ?? '').trim();
    const status = String(record.status ?? '').trim();
    if (stageName === '全部转单' || status === '全部转单' || status === 'FULL_CONVERTED') return 100;
    if (stageName === '部分转单' || status === '部分转单' || status === 'PARTIAL_CONVERTED') return 50;
    return 0;
  }, [purchaseRequestAuditEnabled]);

  const applyDepartmentFromApplicantUser = useCallback(
    (user: User | User[] | undefined) => {
      const picked = Array.isArray(user) ? user[0] : user;
      const deptUuid = picked?.department_uuid || picked?.department?.uuid;
      if (!deptUuid) {
        applicantDepartmentUuidRef.current = undefined;
        createFormRef.current?.setFieldsValue({
          department_id: undefined,
          department_name: undefined,
        });
        return;
      }
      applicantDepartmentUuidRef.current = deptUuid;
      const payload = resolvePurchaseDepartmentFromApplicant(deptUuid, departmentOptions);
      if (payload.department_id == null) {
        // 部门树尚未就绪或用户部门不在选项中：清空旧部门，等 options 就绪后再回填
        createFormRef.current?.setFieldsValue({
          department_id: undefined,
          department_name: undefined,
        });
        return;
      }
      createFormRef.current?.setFieldsValue(payload);
    },
    [departmentOptions],
  );

  const defaultApplicantFields = useCallback(() => {
    if (!currentUser) return {};
    const deptUuid = currentUser.department?.uuid;
    applicantDepartmentUuidRef.current = deptUuid;
    const deptPayload = resolvePurchaseDepartmentFromApplicant(deptUuid, departmentOptions);
    return {
      applicant_uuid: currentUser.uuid,
      applicant_id: currentUser.id,
      applicant_name: currentUser.full_name || currentUser.username || '',
      ...deptPayload,
    };
  }, [currentUser, departmentOptions]);

  useEffect(() => {
    if (!departmentOptions.length) return;
    const pendingUuid = String(applicantDepartmentUuidRef.current ?? '').trim();
    if (!pendingUuid) return;
    const form = createFormRef.current;
    if (!form) return;
    const existing = form.getFieldValue('department_id');
    if (existing != null && existing !== '') return;
    const payload = resolvePurchaseDepartmentFromApplicant(pendingUuid, departmentOptions);
    if (payload.department_id == null) return;
    form.setFieldsValue(payload);
  }, [departmentOptions]);

  const applyCreateFormDefaults = useCallback(
    (values: Record<string, unknown>) => {
      prFormHydratingRef.current = true;
      try {
        createFormRef.current?.setFieldsValue({
          ...defaultApplicantFields(),
          ...values,
        });
      } finally {
        prFormHydratingRef.current = false;
      }
    },
    [defaultApplicantFields],
  );

  const fillBlankPurchaseRequisitionCode = useCallback(async () => {
    const existing = String(createFormRef.current?.getFieldValue?.('requisition_code') ?? '').trim();
    if (existing) return;
    try {
      const config = await getCodeRulePageConfig('kuaizhizao-purchase-requisition');
      const autoGen = config?.autoGenerate ?? isAutoGenerateEnabled('kuaizhizao-purchase-requisition');
      const ruleCode = config?.ruleCode ?? getPageRuleCode('kuaizhizao-purchase-requisition');
      const allowManualEdit = config?.allowManualEdit ?? true;
      setEffectiveRuleCode(ruleCode ?? null);
      setEffectiveAutoGen(autoGen);
      setEffectiveAllowManualEdit(allowManualEdit);
      if (!autoGen || !ruleCode) return;
      const again = String(createFormRef.current?.getFieldValue?.('requisition_code') ?? '').trim();
      if (again) return;
      const reqDate = createFormRef.current?.getFieldValue?.('requisition_date');
      const reqDateStr =
        reqDate?.format?.('YYYY-MM-DD') ??
        (typeof reqDate === 'string' && reqDate.trim() ? reqDate.trim() : undefined);
      const res = await testGenerateCode({
        rule_code: ruleCode,
        ...(reqDateStr ? { context: { requisition_date: reqDateStr, doc_date: reqDateStr } } : {}),
      });
      if (!res.code) return;
      const still = String(createFormRef.current?.getFieldValue?.('requisition_code') ?? '').trim();
      if (still) return;
      setPreviewCode(res.code);
      createFormRef.current?.setFieldValue('requisition_code', res.code);
    } catch (error: unknown) {
      console.warn('采购申请编号预生成失败:', error);
    }
  }, []);

  const initPurchaseRequisitionCreateForm = useCallback(async () => {
    void ensureSupplierList();
    const copy = (location.state as { purchaseRequisitionCopy?: Record<string, any> } | null)
      ?.purchaseRequisitionCopy;
    if (copy) {
      lastHeaderDeliveryRef.current = null;
      setPreviewCode(null);
      const copiedItems = Array.isArray(copy.items) ? copy.items : [];
      const copiedValues = {
        requisition_name: copy.requisition_name,
        requisition_date: dayjs(),
        applicant_id: copy.applicant_id,
        applicant_name: copy.applicant_name,
        department_id: copy.department_id,
        department_name: copy.department_name,
        required_date: copy.required_date ? dayjs(copy.required_date) : undefined,
        notes: copy.notes,
        attachments: mapAttachmentsToUploadList(copy.attachments),
        items: copiedItems.length
          ? copiedItems.map((it: Record<string, any>) => ({
              ...it,
              required_date: it.required_date ? dayjs(it.required_date) : undefined,
              attachments: mapAttachmentsToUploadList(it.attachments),
            }))
          : initialCreateItems,
      };
      try {
        const config = await getCodeRulePageConfig('kuaizhizao-purchase-requisition');
        const autoGen = config?.autoGenerate ?? isAutoGenerateEnabled('kuaizhizao-purchase-requisition');
        const ruleCode = config?.ruleCode ?? getPageRuleCode('kuaizhizao-purchase-requisition');
        setEffectiveRuleCode(ruleCode ?? null);
        setEffectiveAutoGen(autoGen);
        setEffectiveAllowManualEdit(config?.allowManualEdit ?? true);
        if (autoGen && ruleCode) {
          const res = await testGenerateCode({ rule_code: ruleCode });
          setPreviewCode(res.code ?? null);
          applyCreateFormDefaults({ ...copiedValues, requisition_code: res.code ?? '' });
          return;
        }
      } catch (error: unknown) {
        console.warn('采购申请复制编号预生成失败:', error);
      }
      applyCreateFormDefaults(copiedValues);
      return;
    }
    const flowBodyFromState =
      location.state &&
      typeof location.state === 'object' &&
      (location.state as { documentFlowCreate?: unknown }).documentFlowCreate &&
      typeof (location.state as { documentFlowCreate?: unknown }).documentFlowCreate === 'object'
        ? (location.state as { documentFlowCreate: Record<string, unknown> }).documentFlowCreate
        : null;
    const draft = prFormDraftKey ? getDocumentFormDraft<Record<string, unknown>>(prFormDraftKey) : null;
    const flowBody = flowBodyFromState ?? draft;
    if (flowBody && Object.keys(flowBody).length > 0) {
      const handoff = buildPurchaseRequisitionHandoffFormValues(flowBody);
      if (handoff.extras) {
        documentFlowSubmitExtrasRef.current = handoff.extras;
      }
      const healed = handoff.formValues;
      applyCreateFormDefaults(healed);
      lastHeaderDeliveryRef.current = null;
      applyHeaderDeliveryToItemLines(healed.required_date);
      if (!String(healed.requisition_code ?? '').trim()) {
        await fillBlankPurchaseRequisitionCode();
      }
      return;
    }
    lastHeaderDeliveryRef.current = null;
    setPreviewCode(null);
    setEffectiveRuleCode(null);
    setEffectiveAutoGen(null);
    setEffectiveAllowManualEdit(null);
    prFormHydratingRef.current = true;
    try {
      createFormRef.current?.resetFields();
    } finally {
      prFormHydratingRef.current = false;
    }
    try {
      const config = await getCodeRulePageConfig('kuaizhizao-purchase-requisition');
      const autoGen = config?.autoGenerate ?? isAutoGenerateEnabled('kuaizhizao-purchase-requisition');
      const ruleCode = config?.ruleCode ?? getPageRuleCode('kuaizhizao-purchase-requisition');
      setEffectiveRuleCode(ruleCode ?? null);
      setEffectiveAutoGen(autoGen);
      setEffectiveAllowManualEdit(config?.allowManualEdit ?? true);
      const initReqDate = dayjs().format('YYYY-MM-DD');
      const codePreviewContext = { context: { requisition_date: initReqDate, doc_date: initReqDate } };
      if (autoGen && ruleCode) {
        try {
          const res = await testGenerateCode({ rule_code: ruleCode, ...codePreviewContext });
          const preview = res.code;
          setPreviewCode(preview ?? null);
          applyCreateFormDefaults({
            requisition_code: preview ?? '',
            requisition_date: dayjs(),
            items: initialCreateItems,
          });
        } catch (e) {
          console.warn('采购申请编号预生成失败:', e);
          setPreviewCode(null);
          applyCreateFormDefaults({
            requisition_date: dayjs(),
            items: initialCreateItems,
          });
        }
      } else {
        setPreviewCode(null);
        applyCreateFormDefaults({
          requisition_date: dayjs(),
          items: initialCreateItems,
        });
      }
    } catch {
      const ruleCode = getPageRuleCode('kuaizhizao-purchase-requisition');
      setEffectiveRuleCode(ruleCode ?? null);
      setEffectiveAutoGen(isAutoGenerateEnabled('kuaizhizao-purchase-requisition'));
      setEffectiveAllowManualEdit(true);
      const initReqDate = dayjs().format('YYYY-MM-DD');
      const codePreviewContext = { context: { requisition_date: initReqDate, doc_date: initReqDate } };
      if (isAutoGenerateEnabled('kuaizhizao-purchase-requisition') && ruleCode) {
        try {
          const res = await testGenerateCode({ rule_code: ruleCode, ...codePreviewContext });
          const preview = res.code;
          setPreviewCode(preview ?? null);
          applyCreateFormDefaults({
            requisition_code: preview ?? '',
            requisition_date: dayjs(),
            items: initialCreateItems,
          });
        } catch (e) {
          console.warn('采购申请编号预生成失败:', e);
          setPreviewCode(null);
          applyCreateFormDefaults({
            requisition_date: dayjs(),
            items: initialCreateItems,
          });
        }
      } else {
        setPreviewCode(null);
        applyCreateFormDefaults({
          requisition_date: dayjs(),
          items: initialCreateItems,
        });
      }
    }
  }, [
    applyCreateFormDefaults,
    applyHeaderDeliveryToItemLines,
    ensureSupplierList,
    fillBlankPurchaseRequisitionCode,
    initialCreateItems,
    location,
    prFormDraftKey,
  ]);

  const handleCreate = () => {
    navigate(PURCHASE_REQUISITION_CREATE_PATH);
  };

  useEffect(() => {
    if (!isFormPage) {
      formPageInitKeyRef.current = null;
      return;
    }
    const title = isCreatePage
      ? t('app.kuaizhizao.menu.purchase-management.purchase-requisitions.new')
      : t('app.kuaizhizao.menu.purchase-management.purchase-requisitions.edit');
    const sp = new URLSearchParams(location.search || '');
    sp.delete('_refresh');
    const cleanSearch = sp.toString();
    const tabKey = location.pathname + (cleanSearch ? `?${cleanSearch}` : '');
    setCustomPageTitle(location.pathname, title);
    setCustomPageTitle(tabKey, title);
    window.dispatchEvent(
      new CustomEvent('riveredge:update-tab-title', {
        detail: { key: tabKey, path: location.pathname, title },
      }),
    );
    return () => {
      removeCustomPageTitle(location.pathname);
      removeCustomPageTitle(tabKey);
    };
  }, [isFormPage, isCreatePage, location.pathname, location.search, t]);

  useEffect(() => {
    if (!isFormPage) return;
    const flow = new URLSearchParams(location.search || '').get('flow');
    const initKey = isCreatePage
      ? flow
        ? `create:flow:${flow}`
        : 'create'
      : `edit-${editRouteId}`;
    if (formPageInitKeyRef.current === initKey) {
      if (isCreatePage) {
        const form = createFormRef.current;
        const values = form?.getFieldsValue?.(true) as Record<string, unknown> | undefined;
        if (form && values) {
          const healed = healPurchaseRequisitionDraft(values);
          const headerDirty = PR_DRAFT_HEADER_NUMBER_FIELDS.some(
            (key) => healed[key] !== values[key],
          );
          const itemsDirty = JSON.stringify(healed.items ?? null) !== JSON.stringify(values.items ?? null);
          if (headerDirty || itemsDirty) {
            form.setFieldsValue?.({
              applicant_id: healed.applicant_id,
              department_id: healed.department_id,
              items: healed.items ?? values.items,
            });
          }
        }
        const existing = String(form?.getFieldValue?.('requisition_code') ?? '').trim();
        if (!existing) void fillBlankPurchaseRequisitionCode();
      }
      return;
    }
    formPageInitKeyRef.current = initKey;
    if (isCreatePage) {
      void initPurchaseRequisitionCreateForm();
    } else if (editRouteId != null) {
      void loadPurchaseRequisitionEditForm(editRouteId);
    }
  }, [
    isFormPage,
    isCreatePage,
    editRouteId,
    location.search,
    initPurchaseRequisitionCreateForm,
    loadPurchaseRequisitionEditForm,
    fillBlankPurchaseRequisitionCode,
  ]);

  useEffect(() => {
    if (!isFormPage || !prFormDraftKey) return;
    return () => {
      const values = createFormRef.current?.getFieldsValue?.(true);
      if (values && Object.keys(values).length > 0) {
        setDocumentFormDraft(prFormDraftKey, {
          ...values,
          ...(documentFlowSubmitExtrasRef.current ?? {}),
        });
      }
    };
  }, [isFormPage, prFormDraftKey]);

  const pullFromComputationColumns: ProColumns<PullDemandComputationCandidate>[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.purchaseRequisition.pull.computationCode'),
        dataIndex: 'computation_code',
        width: 168,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialName'),
        dataIndex: 'material_name',
        ellipsis: true,
        render: (_, record) => (
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
        sorter: (a, b) =>
          String(a.document_date || '').localeCompare(String(b.document_date || '')),
        defaultSortOrder: 'descend',
        render: (_, record) =>
          record.document_date ? formatBusinessDateOnly(String(record.document_date)) : '-',
      },
      {
        title: t('app.kuaizhizao.purchaseRequisition.pull.businessMode'),
        dataIndex: 'business_mode',
        width: 100,
        align: 'center',
        render: (v) => renderDemandBusinessModeMarkerTag(t, v),
      },
      {
        title: t('common.quantity'),
        dataIndex: 'suggested_quantity',
        width: 100,
        align: 'right',
        render: (v) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.salesOrder.colShippedQty'),
        dataIndex: 'pushed_quantity',
        width: 100,
        align: 'right',
        render: (v) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.salesOrder.colShippableQty'),
        dataIndex: 'remaining_quantity',
        width: 100,
        align: 'right',
        render: (v) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.purchaseRequisition.col.requiredDate'),
        dataIndex: 'required_date',
        width: 112,
        render: (v) => (v ? formatBusinessDateOnly(v) : '-'),
      },
      {
        title: t('app.kuaizhizao.purchaseRequisition.pull.convertStatus'),
        key: 'convert_status',
        width: 100,
        align: 'center',
        render: (_, record) =>
          renderPullCapabilityTag(
            Number(record.remaining_quantity ?? 0) > 0,
            t('app.kuaizhizao.purchaseRequisition.pull.canCreate'),
            t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
          ),
      },
    ],
    [t],
  );

  const isPullComputationSelectable = useCallback(
    (record: PullDemandComputationCandidate) => Number(record.remaining_quantity ?? 0) > 0,
    [],
  );

  const pullDocumentScopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const pullFromComputationQuery = useUniPullQuery<PullDemandComputationCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullDocumentScopeOptions,
    defaultScope: 'pullable',
    onOpen: () => {
      pullSourceComputationIdRef.current = undefined;
      setPullSourceComputationId(undefined);
      void listDemandComputations({
        skip: 0,
        limit: 100,
        computation_status: '完成',
        view: 'options',
      })
        .then((res) => {
          setPullSourceOptions(
            (res?.data ?? [])
              .filter((row) => row.id != null && row.computation_code)
              .map((row) => ({ value: row.id!, label: String(row.computation_code) })),
          );
        })
        .catch((error: unknown) => {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseRequisition.pull.loadSourceFailed')));
          setPullSourceOptions([]);
        });
    },
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const listRes = await listDemandComputationPurchasePullLines({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          keyword: keyword.trim() || undefined,
          computation_id: pullSourceComputationIdRef.current,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseRequisition.pull.failed')));
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullComputationSelectable(record),
    onConfirm: async (_keys, rows) => {
      const selectedRows = rows.filter((row) => isPullComputationSelectable(row));
      if (!selectedRows.length) {
        messageApi.warning(t('app.kuaizhizao.purchaseRequisition.pull.selectLinesFirst'));
        return;
      }
      setPullBulkRequiredDate(null);
      setPullDateConfirmRows(
        selectedRows.map((row) => ({
          ...row,
          required_date: row.required_date ? String(row.required_date).slice(0, 10) : null,
        })),
      );
      pullFromComputationQuery.closeModal();
      setPullDateConfirmOpen(true);
    },
  });

  const pullFromSalesOrderColumns: ProColumns<PurchaseRequisitionSalesOrderPullLine>[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.salesOrder.orderCode'),
        dataIndex: 'order_code',
        width: 168,
        ellipsis: true,
      },
      buildPullQueryMaterialIdentityColumn<PurchaseRequisitionSalesOrderPullLine>(t),
      {
        title: t('components.uniPullQuery.documentDateColumn'),
        dataIndex: 'document_date',
        width: 112,
        render: (_: unknown, record) => {
          const raw = record.document_date || record.order_date;
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
        title: t('app.kuaizhizao.workOrder.pull.colPushedWorkOrderQty'),
        dataIndex: 'pushed_work_order_quantity',
        width: 100,
        align: 'right' as const,
        render: (v: number | undefined) => formatQuantity(Number(v ?? 0)),
      },
      {
        title: t('app.kuaizhizao.pullOpenLine.colPushedPurchaseRequisitionQty'),
        dataIndex: 'pushed_purchase_quantity',
        width: 100,
        align: 'right' as const,
        render: (v: number | undefined, record) =>
          formatQuantity(Number(v ?? record.pushed_quantity ?? 0)),
      },
      {
        title: t('app.kuaizhizao.pullOpenLine.colTransferableQty'),
        dataIndex: 'remaining_quantity',
        width: 100,
        align: 'right' as const,
        render: (v: number) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.purchaseRequisition.pull.convertStatus'),
        key: 'convert_status',
        width: 100,
        align: 'center' as const,
        render: (_: unknown, record) =>
          renderPullCapabilityTag(
            isPullOpenLineSelectable(record),
            t('app.kuaizhizao.purchaseRequisition.pull.canCreate'),
            t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
          ),
      },
    ],
    [t],
  );

  const pullFromSalesOrderQuery = useUniPullQuery<PurchaseRequisitionSalesOrderPullLine>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullDocumentScopeOptions,
    defaultScope: 'pullable',
    onOpen: () => {
      pullSourceSalesOrderIdRef.current = undefined;
      setPullSourceSalesOrderId(undefined);
      void listPurchaseRequisitionSalesOrderPullOrders({ skip: 0, limit: 100, pullable_only: true })
        .then((res) => {
          setPullSourceSalesOrderOptions(
            (res?.data ?? [])
              .filter((row) => row.id != null && row.order_code)
              .map((row) => ({ value: row.id, label: String(row.order_code) })),
          );
        })
        .catch((error: unknown) => {
          messageApi.error(
            getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.pull.loadSourceFailed')),
          );
          setPullSourceSalesOrderOptions([]);
        });
    },
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const listRes = await listPurchaseRequisitionSalesOrderPullLines({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          keyword: keyword.trim() || undefined,
          sales_order_id: pullSourceSalesOrderIdRef.current,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.purchaseRequisition.pull.salesOrderLinesFailed')),
        );
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullOpenLineSelectable(record),
    onConfirm: async (_keys, rows) => {
      const selectable = rows.filter((row) => isPullOpenLineSelectable(row));
      const byOrder = new Map<number, number[]>();
      for (const row of selectable) {
        const oid = Number(row.sales_order_id);
        const itemId = Number(row.id);
        if (oid > 0 && itemId > 0) {
          const bucket = byOrder.get(oid) ?? [];
          bucket.push(itemId);
          byOrder.set(oid, bucket);
        }
      }
      if (!byOrder.size) {
        messageApi.warning(t('app.kuaizhizao.purchaseRequisition.pull.selectLinesFirst'));
        return;
      }
      try {
        await handoffSalesOrdersToPurchaseRequisitionCreate(
          navigate,
          [...byOrder.entries()].map(([orderId, itemIds]) => ({
            salesOrderId: orderId,
            payload: { selected_item_ids: itemIds },
          })),
        );
        messageApi.success(
          t('app.kuaizhizao.documentFlow.openedDownstreamCreate', {
            target: pullFromSalesOrderAction.targetLabel,
          }),
        );
        pullFromSalesOrderQuery.closeModal();
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(
            error,
            t('app.kuaizhizao.purchaseRequisition.pull.salesOrderCreateFailed', {
              source: pullFromSalesOrderAction.sourceLabel,
              target: pullFromSalesOrderAction.targetLabel,
            }),
          ),
        );
      }
    },
  });

  const resetPullDateConfirmModal = useCallback(() => {
    setPullDateConfirmOpen(false);
    setPullDateConfirming(false);
    setPullDateConfirmRows([]);
    setPullBulkRequiredDate(null);
  }, []);

  const handlePullBulkDateApply = useCallback(() => {
    if (!pullBulkRequiredDate) {
      messageApi.warning(t('app.kuaizhizao.purchaseRequisition.pull.bulkDateRequired'));
      return;
    }
    const dateStr = pullBulkRequiredDate.format('YYYY-MM-DD');
    setPullDateConfirmRows((prev) => prev.map((row) => ({ ...row, required_date: dateStr })));
  }, [messageApi, pullBulkRequiredDate, t]);

  const handlePullDateConfirmCreate = useCallback(async () => {
    const missing = pullDateConfirmRows.filter((row) => !row.required_date);
    if (missing.length > 0) {
      messageApi.warning(t('app.kuaizhizao.purchaseRequisition.pull.dateRequired'));
      return;
    }
    const selectedIds = pullDateConfirmRows
      .map((row) => Number(row.id))
      .filter((id) => id > 0);
    if (!selectedIds.length) {
      messageApi.warning(t('app.kuaizhizao.purchaseRequisition.pull.selectLinesFirst'));
      return;
    }
    setPullDateConfirming(true);
    try {
      await handoffDemandComputationToPurchaseRequisitionCreate(
        navigate,
        selectedIds,
        pullDateConfirmRows.map((row) => ({
          item_id: Number(row.id),
          required_date: String(row.required_date),
        })),
      );
      messageApi.success(
        t('app.kuaizhizao.documentFlow.openedDownstreamCreate', {
          target: t('app.kuaizhizao.menu.purchase-management.purchase-requisitions'),
        }),
      );
      resetPullDateConfirmModal();
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseRequisition.pull.failed')));
    } finally {
      setPullDateConfirming(false);
    }
  }, [messageApi, navigate, pullDateConfirmRows, resetPullDateConfirmModal, t]);

  const mapItemsForApi = (
    validItems: Array<{
      material_id?: number;
      material_code?: string;
      material_name?: string;
      material_spec?: string;
      material_model?: string;
      partner_material_code?: string;
      partner_material_name?: string;
      unit?: string;
      quantity?: number;
      suggested_unit_price?: number;
      required_date?: any;
      demand_computation_item_id?: number;
      supplier_id?: number;
      notes?: string;
      attachments?: unknown;
    }>,
    headerRequiredDateStr?: string,
  ) =>
    validItems.map((i, index) => {
      const lineDate =
        coerceFormDate(i.required_date)?.format('YYYY-MM-DD') ??
        (typeof i.required_date === 'string' && i.required_date.trim() ? i.required_date.trim() : undefined) ??
        headerRequiredDateStr;
      if (!lineDate) {
        messageApi.error(t('app.kuaizhizao.purchaseRequisition.lineRequiredDateMissing', { row: index + 1 }));
        throw new Error(t('app.kuaizhizao.purchaseRequisition.form.lineDeliveryRequired'));
      }
      const dualQty = pickDocumentLineDualQuantityFields(i as Record<string, unknown>);
      const rate = Number(dualQty.unit_conversion_rate);
      if (!Number.isFinite(rate) || rate <= 0) {
        delete dualQty.unit_conversion_rate;
      }
      const auxQty = Number(dualQty.aux_quantity);
      if (!Number.isFinite(auxQty) || auxQty < 0) {
        delete dualQty.aux_quantity;
      }
      return {
        material_id: i.material_id!,
        material_code: i.material_code || '',
        material_name: i.material_name || '',
        material_spec: i.material_spec,
        material_model:
          typeof i.material_model === 'string' && i.material_model.trim()
            ? i.material_model.trim()
            : undefined,
        partner_material_code:
          typeof i.partner_material_code === 'string' && i.partner_material_code.trim()
            ? i.partner_material_code.trim()
            : undefined,
        partner_material_name:
          typeof i.partner_material_name === 'string' && i.partner_material_name.trim()
            ? i.partner_material_name.trim()
            : undefined,
        unit: i.unit || '件',
        ...dualQty,
        quantity: Number(i.quantity) || 0,
        suggested_unit_price: Number(i.suggested_unit_price) || 0,
        required_date: lineDate,
        demand_computation_item_id: i.demand_computation_item_id,
        supplier_id: i.supplier_id ?? undefined,
        notes: typeof i.notes === 'string' && i.notes.trim() ? i.notes.trim() : undefined,
        attachments: normalizeDocumentAttachments(i.attachments as any),
      };
    });

  const finalizePurchaseRequisitionForm = useCallback(() => {
    if (prFormDraftKey) clearDocumentFormDraft(prFormDraftKey);
    setEffectiveRuleCode(null);
    setEffectiveAutoGen(null);
    setEffectiveAllowManualEdit(null);
    createFormRef.current?.resetFields();
    invalidateMenuBadgeCounts();
    if (isFormPage) {
      leavePurchaseRequisitionFormPage();
    }
    actionRef.current?.reload();
  }, [
    prFormDraftKey,
    invalidateMenuBadgeCounts,
    isFormPage,
    leavePurchaseRequisitionFormPage,
  ]);

  const runPurchaseRequisitionSubmitAfterSave = async (requisitionId: number, wasEdit: boolean) => {
    const { completed } = await runPurchaseRequisitionSaveAndAudit(requisitionId);
    if (!completed) {
      if (!wasEdit) {
        navigate(purchaseRequisitionEditPath(requisitionId), { replace: true });
      }
      return;
    }
    finalizePurchaseRequisitionForm();
  };

  const handleModalSubmit = async (values: {
    requisition_code?: string;
    requisition_name?: string;
    requisition_date?: any;
    required_date?: any;
    applicant_id?: number;
    applicant_name?: string;
    department_id?: number;
    department_name?: string;
    notes?: string;
    attachments?: unknown;
    items?: Array<{
      material_id?: number;
      material_code?: string;
      material_name?: string;
      material_spec?: string;
      unit?: string;
      quantity?: number;
      suggested_unit_price?: number;
      required_date?: any;
      demand_computation_item_id?: number;
      supplier_id?: number;
      notes?: string;
    }>;
  }) => {
    const requisitionDate =
      values.requisition_date?.format?.('YYYY-MM-DD') ?? values.requisition_date ?? undefined;
    const requiredDate =
      coerceFormDate(values.required_date)?.format('YYYY-MM-DD') ??
      (typeof values.required_date === 'string' ? values.required_date : undefined);
    const validItems = normalizeFormListItems<any>(values.items).filter(
      (i) => i.material_id && (Number(i.quantity) || 0) > 0,
    );
    if (validItems.length === 0) {
      messageApi.error(t('app.kuaizhizao.purchaseRequisition.atLeastOneItem'));
      return;
    }
    let itemsPayload;
    try {
      itemsPayload = mapItemsForApi(validItems, requiredDate);
    } catch {
      return;
    }
    const departmentPayload = resolvePurchaseDepartmentPayload(
      values.department_id,
      resolveDepartmentName,
      values.department_name,
    );
    const shouldSubmit = submitAfterSaveRef.current;
    setFormSubmitting(true);
    try {
      let requisitionId: number | undefined;

      if (editingId != null) {
        const editedCode = String(values.requisition_code ?? '').trim();
        await updatePurchaseRequisition(editingId, {
          // 是否允许改号由后端 document_code 门禁判定，勿因前端 editable 竞态静默丢掉
          ...(editedCode ? { requisition_code: editedCode } : {}),
          order_type: String(values.order_type ?? '标准采购').trim() || '标准采购',
          ...(showRequisitionNameField
            ? { requisition_name: String(values.requisition_name ?? '').trim() }
            : {}),
          requisition_date: requisitionDate,
          required_date: requiredDate,
          applicant_id: values.applicant_id,
          applicant_name: values.applicant_name,
          ...departmentPayload,
          notes: values.notes,
          attachments: normalizeDocumentAttachments(values.attachments),
          items: itemsPayload,
        });
        requisitionId = editingId;
        if (!shouldSubmit) {
          messageApi.success(t('common.save'));
        }
      } else {
        let requisitionCode = values.requisition_code;
        const ruleCode = effectiveRuleCode || getPageRuleCode('kuaizhizao-purchase-requisition');
        const autoGen = effectiveAutoGen ?? isAutoGenerateEnabled('kuaizhizao-purchase-requisition');
        const allowManualEdit = effectiveAllowManualEdit ?? true;
        const userCode = String(requisitionCode ?? '').trim();
        const preview = String(previewCode ?? '').trim();
        const manualCodeOverride = allowManualEdit && userCode && preview && userCode !== preview;
        const codeContext = requisitionDate
          ? { requisition_date: requisitionDate, doc_date: requisitionDate }
          : undefined;
        if (autoGen && ruleCode && !manualCodeOverride) {
          try {
            const res = await generateCode({
              rule_code: ruleCode,
              ...(codeContext ? { context: codeContext } : {}),
            });
            requisitionCode = res.code;
            createFormRef.current?.setFieldValue('requisition_code', res.code);
          } catch (e: unknown) {
            const err = e as { message?: string };
            messageApi.error(
              err?.message || t('app.kuaizhizao.purchaseRequisition.generateCodeFailed'),
            );
            return;
          }
        } else if (manualCodeOverride) {
          requisitionCode = userCode;
        }
        const created = await createPurchaseRequisition({
          requisition_code: requisitionCode || undefined,
          order_type: String(values.order_type ?? '标准采购').trim() || '标准采购',
          ...(showRequisitionNameField
            ? { requisition_name: String(values.requisition_name ?? '').trim() || undefined }
            : {}),
          requisition_date: requisitionDate,
          required_date: requiredDate,
          applicant_id: values.applicant_id,
          applicant_name: values.applicant_name,
          ...departmentPayload,
          notes: values.notes,
          attachments: normalizeDocumentAttachments(values.attachments),
          items: itemsPayload,
        });
        requisitionId = created.id;
        if (!shouldSubmit) {
          messageApi.success(t('common.createSuccess'));
        }
      }

      if (shouldSubmit && requisitionId) {
        submitAfterSaveRef.current = false;
        const wasEdit = editingId != null;
        try {
          await runPurchaseRequisitionSubmitAfterSave(requisitionId, wasEdit);
        } catch (submitErr: unknown) {
          const submitMessage =
            submitErr instanceof Error ? submitErr.message : t('common.operationFailed');
          messageApi.error(
            t('app.kuaizhizao.purchaseRequisition.submitFailedWithReason', { message: submitMessage }),
          );
          if (!wasEdit) {
            navigate(purchaseRequisitionEditPath(requisitionId), { replace: true });
          }
          invalidateMenuBadgeCounts();
          actionRef.current?.reload();
        }
        return;
      }

      finalizePurchaseRequisitionForm();
    } catch (e: any) {
      submitAfterSaveRef.current = false;
      const data = e?.response?.data;
      const apiMessage =
        formatApiErrorDetail(data?.detail)
        || (data?.success === false && data?.error ? formatApiErrorDetail(data.error) : '')
        || e?.message;
      messageApi.error(
        apiMessage || (editingId != null ? t('common.saveFailed') : t('common.createFailed')),
      );
      throw e;
    } finally {
      setFormSubmitting(false);
    }
  };

  const triggerPurchaseRequisitionPrimarySubmit = useCallback(async () => {
    try {
      await createFormRef.current?.validateFields();
      submitAfterSaveRef.current = true;
      createFormRef.current?.submit?.();
    } catch (err: any) {
      if (err?.errorFields?.length) {
        messageApi.warning(t('components.layoutTemplates.formModal.checkFormHint'));
      }
    }
  }, [messageApi, t]);

  const handlePurchaseRequisitionSaveDraft = useCallback(async () => {
    try {
      await createFormRef.current?.validateFields();
      submitAfterSaveRef.current = false;
      createFormRef.current?.submit?.();
    } catch (err: any) {
      if (err?.errorFields?.length) {
        messageApi.warning(t('components.layoutTemplates.formModal.checkFormHint'));
      }
    }
  }, [messageApi, t]);

  const handleDetail = async (record: PurchaseRequisition) => {
    try {
      void ensureSupplierList();
      const detail = await getPurchaseRequisition(record.id!);
      void prefetchMaterialsForUnitSelect((detail.items ?? []).map((i) => i.material_id));
      setCurrentReq(detail);
      setDetailVisible(true);
      setPrTrackingRefreshKey((k) => k + 1);
    } catch {
      messageApi.error(t('app.kuaizhizao.purchaseRequisition.detailFailed'));
    }
  };

  // handleSubmit removed as it is redundant with UniWorkflowActions

  const convertFormRef = React.useRef<{
    selectedIds: number[];
    supplierId: number;
    supplierName: string;
    itemQuantities: Record<number, number>;
    itemUnitPrices: Record<number, number>;
    itemSuppliers: Record<number, number>;
    persistDefaultSupplier: boolean;
  }>({
    selectedIds: [],
    supplierId: 0,
    supplierName: '',
    itemQuantities: {},
    itemUnitPrices: {},
    itemSuppliers: {},
    persistDefaultSupplier: false,
  });

  const selectedRequisitionForToolbar = useMemo(() => {
    if (selectedRowKeys.length !== 1) return null;
    const id = Number(selectedRowKeys[0]);
    if (!Number.isFinite(id) || id <= 0) return null;
    return tableRowsRef.current.find((row) => row.id === id) ?? null;
  }, [selectedRowKeys]);

  async function handleCopySelectedPurchaseRequisition() {
    const record = selectedRequisitionForToolbar;
    if (!record?.id) {
      messageApi.warning(t('app.kuaizhizao.purchaseRequisition.selectToCopy'));
      return;
    }
    try {
      const data = await getPurchaseRequisition(record.id);
      const items = (data.items ?? []).map((it) => {
        const {
          id: _id,
          purchase_order_id: _purchaseOrderId,
          purchase_order_item_id: _purchaseOrderItemId,
          converted_quantity_draft: _draftQty,
          converted_quantity_confirmed: _confirmedQty,
          demand_computation_item_id: _demandItemId,
          ...rest
        } = it;
        return rest;
      });
      navigate(PURCHASE_REQUISITION_CREATE_PATH, {
        state: {
          purchaseRequisitionCopy: {
            requisition_name: data.requisition_name,
            applicant_id: data.applicant_id,
            applicant_name: data.applicant_name,
            department_id: data.department_id,
            department_name: data.department_name,
            required_date: data.required_date,
            notes: data.notes,
            attachments: data.attachments,
            items,
          },
        },
      });
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseRequisition.loadFailed')));
    }
  }

  const canPushPurchaseOrder = !!selectedRequisitionForToolbar?.capabilities?.push_purchase_order?.allowed;
  const canPushInquiry = !!selectedRequisitionForToolbar?.capabilities?.push_inquiry?.allowed;
  const toolbarPushDisabledReason = useMemo(() => {
    const base = buildUniPushToolbarDisabledReason(t, {
      selectedCount: selectedRowKeys.length,
      hasSelectedRecord: !!selectedRequisitionForToolbar,
    });
    if (base) return base;
    if (selectedRequisitionForToolbar && !canPushPurchaseOrder && !canPushInquiry) {
      return (
        purchaseRequisitionCapabilityReasonMessage(
          selectedRequisitionForToolbar.capabilities?.push_purchase_order?.reason
            || selectedRequisitionForToolbar.capabilities?.push_inquiry?.reason,
          t,
        ) || t('app.kuaizhizao.purchaseRequisition.push.flowBlocked', { flowClass: '-' })
      );
    }
    return undefined;
  }, [canPushInquiry, canPushPurchaseOrder, selectedRequisitionForToolbar, selectedRowKeys.length, t]);

  const resetPushPoPreviewModal = useCallback(() => {
    setPushPoPreviewOpen(false);
    setPushPoPreviewData(null);
    setPushPoTarget(null);
    setPushPoDetailItems([]);
    setPushPoSuppliers([]);
  }, []);

  const resetPushInquiryPreviewModal = useCallback(() => {
    setPushInquiryPreviewOpen(false);
    setPushInquiryPreviewData(null);
    setPushInquiryTarget(null);
    setPushInquirySelectedItemIds([]);
  }, []);

  const setupConvertFormFromDetail = useCallback(
    (
      allItems: PurchaseRequisitionItem[],
      unconverted: PurchaseRequisitionItem[],
      suppliers: Array<{ id: number; code?: string; name: string }>,
      maxPushByItemId: Map<number, number>,
    ) => {
      const defaultSupplierId = unconverted[0]?.supplier_id || suppliers[0]?.id;
      const quantities: Record<number, number> = {};
      const unitPrices: Record<number, number> = {};
      unconverted.forEach((i) => {
        if (i.id != null) {
          quantities[i.id] = maxPushByItemId.get(i.id)!;
          unitPrices[i.id] = Number(i.suggested_unit_price ?? 0);
        }
      });
      convertFormRef.current = {
        selectedIds: unconverted.map((i) => i.id!).filter(Boolean),
        supplierId: defaultSupplierId || 0,
        supplierName: suppliers.find((s) => s.id === defaultSupplierId)?.name || suppliers[0]?.name || '',
        itemQuantities: quantities,
        itemUnitPrices: unitPrices,
        itemSuppliers: {},
        persistDefaultSupplier: false,
      };
    },
    [],
  );

  const openPushPoPreview = useCallback(
    async (record: PurchaseRequisition) => {
      if (!record.id) return;
      setPushPoPreviewOpen(true);
      setPushPoPreviewLoading(true);
      setPushPoPreviewConfirming(false);
      setPushPoPreviewData(null);
      setPushPoTarget(record);
      setPushPoDetailItems([]);
      setPushPoSuppliers([]);
      try {
        const preview = await previewPushToPurchaseOrder(record.id);
        setPushPoPreviewData(preview);
        if (preview.has_blocking_issues) return;
        const suppliers = await ensureSupplierList();
        if (!suppliers.length) {
          messageApi.warning(t('app.kuaizhizao.purchaseRequisition.maintainSupplierFirst'));
          resetPushPoPreviewModal();
          return;
        }
        const detail = await getPurchaseRequisition(record.id);
        const maxPushByItemId = new Map(
          (preview.items || []).map((row) => [Number(row.item_id), Number(row.max_push_quantity ?? 0)]),
        );
        const allItems = detail.items || [];
        const unconverted = allItems.filter(
          (i) => i.id != null && (maxPushByItemId.get(i.id) ?? 0) > 0,
        );
        if (unconverted.length === 0) {
          messageApi.info(t('app.kuaizhizao.purchaseRequisition.noPushLines'));
          resetPushPoPreviewModal();
          return;
        }
        setupConvertFormFromDetail(allItems, unconverted, suppliers, maxPushByItemId);
        setPushPoDetailItems(allItems);
        setPushPoSuppliers(suppliers);
      } catch (error: any) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseRequisition.loadDetailFailed')));
        resetPushPoPreviewModal();
      } finally {
        setPushPoPreviewLoading(false);
      }
    },
    [ensureSupplierList, messageApi, resetPushPoPreviewModal, setupConvertFormFromDetail, t],
  );

  const handlePushPoPreviewConfirm = useCallback(async () => {
    if (!pushPoTarget?.id || !pushPoPreviewData || pushPoPreviewData.has_blocking_issues) return;
    const {
      selectedIds,
      supplierId,
      supplierName,
      itemQuantities,
      itemUnitPrices,
      itemSuppliers,
      persistDefaultSupplier,
    } = convertFormRef.current;
    if (selectedIds.length === 0) {
      messageApi.error(t('app.kuaizhizao.purchaseRequisition.selectPushLines'));
      return;
    }
    if (selectedIds.some((id) => !itemSuppliers[id])) {
      messageApi.error(t('app.kuaizhizao.purchaseRequisition.selectLineSupplier'));
      return;
    }
    if (
      selectedIds.some((id) => {
        const price = itemUnitPrices[id];
        return price == null || !Number.isFinite(price) || !(Number(price) > 0);
      })
    ) {
      messageApi.error(t('app.kuaizhizao.purchaseRequisition.convert.invalidUnitPrice'));
      return;
    }
    setPushPoPreviewConfirming(true);
    try {
      await handoffRequisitionToPurchaseOrderCreate(navigate, {
        item_ids: selectedIds,
        supplier_id: supplierId || undefined,
        supplier_name: supplierName || undefined,
        item_quantities: itemQuantities,
        item_unit_prices: Object.fromEntries(selectedIds.map((id) => [id, itemUnitPrices[id] ?? 0])),
        item_suppliers: Object.fromEntries(selectedIds.map((id) => [id, itemSuppliers[id]])),
        persist_default_supplier_to_material: persistDefaultSupplier,
      });
      messageApi.success(
        t('app.kuaizhizao.documentFlow.openedDownstreamCreate', {
          target: t('app.kuaizhizao.purchaseOrder.title'),
        }),
      );
      resetPushPoPreviewModal();
      setSelectedRowKeys([]);
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseRequisition.pushFailed')));
    } finally {
      setPushPoPreviewConfirming(false);
    }
  }, [messageApi, navigate, pushPoPreviewData, pushPoTarget, resetPushPoPreviewModal, t]);

  const openPushInquiryPreview = useCallback(
    async (record: PurchaseRequisition) => {
      if (!record.id) return;
      setPushInquiryPreviewOpen(true);
      setPushInquiryPreviewLoading(true);
      setPushInquiryPreviewConfirming(false);
      setPushInquiryPreviewData(null);
      setPushInquiryTarget(record);
      setPushInquirySelectedItemIds([]);
      try {
        const preview = await previewPushToInquiry(record.id);
        setPushInquiryPreviewData(preview);
        const ids = (preview.items || [])
          .filter((row) => Number(row.max_push_quantity ?? 0) > 0)
          .map((row) => Number(row.item_id));
        setPushInquirySelectedItemIds(ids);
      } catch (error: any) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseRequisition.loadDetailFailed')));
        resetPushInquiryPreviewModal();
      } finally {
        setPushInquiryPreviewLoading(false);
      }
    },
    [messageApi, resetPushInquiryPreviewModal, t],
  );

  const handlePushInquiryPreviewConfirm = useCallback(async () => {
    if (!pushInquiryTarget?.id || !pushInquiryPreviewData || pushInquiryPreviewData.has_blocking_issues) return;
    const selectedIds = pushInquirySelectedItemIds.filter((id) =>
      (pushInquiryPreviewData.items || []).some((row) => Number(row.item_id) === id && Number(row.max_push_quantity ?? 0) > 0),
    );
    if (!selectedIds.length) {
      messageApi.warning(t('app.kuaizhizao.purchaseRequisition.selectPushLines'));
      return;
    }
    setPushInquiryPreviewConfirming(true);
    try {
      await handoffRequisitionToPurchaseInquiryCreate(navigate, { item_ids: selectedIds });
      messageApi.success(
        t('app.kuaizhizao.documentFlow.openedDownstreamCreate', {
          target: t('app.kuaizhizao.menu.purchase-management.purchase-inquiries'),
        }),
      );
      resetPushInquiryPreviewModal();
    } catch (error: any) {
      messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseRequisition.inquiryCreateFailed')));
    } finally {
      setPushInquiryPreviewConfirming(false);
    }
  }, [
    messageApi,
    navigate,
    pushInquiryPreviewData,
    pushInquirySelectedItemIds,
    pushInquiryTarget,
    resetPushInquiryPreviewModal,
    t,
  ]);

  const handleBatchDelete = async (keys: React.Key[]) => {
    if (!keys || keys.length === 0) return;
    try {
      for (const id of keys) {
        await deletePurchaseRequisition(Number(id));
      }
      messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (e: any) {
      messageApi.error(e?.response?.data?.detail || t('common.deleteFailed'));
    }
  };

  /** 协调看板深链：requisitionId + action=pushPO */
  useEffect(() => {
    const requisitionIdRaw = searchParams.get('requisitionId');
    if (!requisitionIdRaw) return;

    const action = searchParams.get('action');
    const linkKey = `${requisitionIdRaw}:${action ?? ''}`;
    if (deepLinkHandledRef.current === linkKey) return;

    const requisitionId = Number(requisitionIdRaw);
    if (Number.isNaN(requisitionId) || requisitionId <= 0) return;

    deepLinkHandledRef.current = linkKey;

    const nextParams = new URLSearchParams(searchParams);
    nextParams.delete('requisitionId');
    nextParams.delete('action');
    const nextSearch = nextParams.toString();
    navigate(
      { pathname: location.pathname, search: nextSearch ? `?${nextSearch}` : '' },
      { replace: true },
    );

    if (action === 'pushPO') {
      setSelectedRowKeys([requisitionId]);
      void (async () => {
        try {
          await ensureSupplierList();
          const detail = await getPurchaseRequisition(requisitionId);
          void prefetchMaterialsForUnitSelect((detail.items ?? []).map((i) => i.material_id));
          setCurrentReq(detail);
          await openPushPoPreview({ ...detail, id: requisitionId });
        } catch {
          messageApi.error(t('app.kuaizhizao.purchaseRequisition.openFailed'));
        }
      })();
      return;
    }

    if (action === 'pushInquiry') {
      setSelectedRowKeys([requisitionId]);
      void (async () => {
        try {
          const detail = await getPurchaseRequisition(requisitionId);
          void prefetchMaterialsForUnitSelect((detail.items ?? []).map((i) => i.material_id));
          setCurrentReq(detail);
          await openPushInquiryPreview({ ...detail, id: requisitionId });
        } catch {
          messageApi.error(t('app.kuaizhizao.purchaseRequisition.openFailed'));
        }
      })();
      return;
    }

    void (async () => {
      try {
        const detail = await getPurchaseRequisition(requisitionId);
        void prefetchMaterialsForUnitSelect((detail.items ?? []).map((i) => i.material_id));
        setCurrentReq(detail);
        setDetailVisible(true);
        setPrTrackingRefreshKey((k) => k + 1);
      } catch {
        messageApi.error(t('app.kuaizhizao.purchaseRequisition.openFailed'));
        deepLinkHandledRef.current = null;
      }
    })();
  }, [searchParams, location.pathname, navigate, messageApi, ensureSupplierList, openPushInquiryPreview, openPushPoPreview, t]);

  const toolbarPushMenuItems = useMemo(() => {
    const pushPoBlockedReason = selectedRequisitionForToolbar && !canPushPurchaseOrder
      ? purchaseRequisitionCapabilityReasonMessage(
          selectedRequisitionForToolbar.capabilities?.push_purchase_order?.reason,
          t,
        )
      : undefined;
    const pushInquiryBlockedReason = selectedRequisitionForToolbar && !canPushInquiry
      ? purchaseRequisitionCapabilityReasonMessage(
          selectedRequisitionForToolbar.capabilities?.push_inquiry?.reason,
          t,
        )
      : undefined;
    return buildUniPushMenuItems([
      {
        key: 'push-purchase-order',
        label: pushToPurchaseOrderAction.label,
        disabled: !selectedRequisitionForToolbar || !canPushPurchaseOrder,
        title: pushPoBlockedReason,
        onClick: () => {
          if (selectedRequisitionForToolbar && canPushPurchaseOrder) {
            void openPushPoPreview(selectedRequisitionForToolbar);
          }
        },
      },
      {
        key: 'push-inquiry',
        label: pushToInquiryAction.label,
        disabled: !selectedRequisitionForToolbar || !canPushInquiry,
        title: pushInquiryBlockedReason,
        onClick: () => {
          if (selectedRequisitionForToolbar && canPushInquiry) {
            void openPushInquiryPreview(selectedRequisitionForToolbar);
          }
        },
      },
    ]);
  }, [
    canPushInquiry,
    canPushPurchaseOrder,
    openPushInquiryPreview,
    openPushPoPreview,
    pushToInquiryAction.label,
    pushToPurchaseOrderAction.label,
    selectedRequisitionForToolbar,
    t,
  ]);

  const executeDeleteOne = async (record: PurchaseRequisition) => {
    try {
          await deletePurchaseRequisition(record.id!);
          messageApi.success(t('common.deleteSuccess'));
          if (currentReq?.id === record.id) {
            setDetailVisible(false);
            setCurrentReq(null);
          }
          invalidateMenuBadgeCounts();
    actionRef.current?.reload();
        } catch (e: any) {
          messageApi.error(e?.response?.data?.detail || t('common.deleteFailed'));
        }
  };

  const handleDeleteOne = (record: PurchaseRequisition) => {
    if (record.capabilities?.delete?.allowed !== true) return;
    modalApi.confirm({
      title: t('app.kuaizhizao.purchaseRequisition.confirmDelete'),
      content: t('app.kuaizhizao.purchaseRequisition.confirmDeleteContent', { code: record.requisition_code }),
      onOk: () => executeDeleteOne(record),
    });
  };

  const columns: ProColumns<PurchaseRequisition>[] = useMemo(() => alignProColumns<PurchaseRequisition>([
    // 仅高级搜索、不在表身展示；必须放在最前，避免夹在可滚动列与右侧 fixed 列之间导致固定列顺序异常
    {
      title: t('app.kuaizhizao.purchaseRequisition.col.requiredDateRange'),
      dataIndex: 'required_date_range',
      valueType: 'dateRange',
      hideInTable: true,
      hideInSearch: false,
      fieldProps: {
        placeholder: [t('app.kuaizhizao.quotation.dateRangeStart'), t('app.kuaizhizao.quotation.dateRangeEnd')],
      },
      formItemProps: formDateRangeFormItemProps,
      search: {
        transform: (value: any) => {
          if (!value || !Array.isArray(value)) return {};
          const [a, b] = value;
          return {
            required_date_from: a ? formatDateTime(a, 'YYYY-MM-DD') : undefined,
            required_date_to: b ? formatDateTime(b, 'YYYY-MM-DD') : undefined,
          };
        },
      },
    },
    {
      title: t('app.kuaizhizao.purchaseRequisition.form.orderType'),
      dataIndex: 'order_type',
      width: 96,
      minWidth: 96,
      uniTableKeepWidth: true,
      hideInSearch: true,
      ellipsis: true,
    },
    {
      title: t('app.kuaizhizao.purchaseRequisition.col.nameAndCode'),
      key: 'requisition_code',
      dataIndex: 'requisition_code',
      width: 240,
      minWidth: 240,
      uniTableKeepWidth: true,
      uniTablePrimaryFlex: false,
      resizable: false,
      fixed: 'left',
      sorter: true,
      hideInSearch: false,
      render: (_, record) => (
        <UniTableStackedPrimaryCell
          primary={String(record.requisition_name ?? '')}
          secondary={String(record.requisition_code ?? '')}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.purchaseRequisition.col.code'),
      dataIndex: 'requisition_code',
      hideInTable: true,
      hideInSearch: false,
    },
    { title: t('app.kuaizhizao.purchaseRequisition.col.name'), dataIndex: 'requisition_name', hideInTable: true, hideInSearch: false, ellipsis: true },
    {
      title: t('app.kuaizhizao.purchaseRequisition.col.sourceCode'),
      dataIndex: 'source_code',
      hideInTable: true,
      hideInSearch: false,
      ellipsis: true,
    },
    {
      title: `${t('app.kuaizhizao.purchaseRequisition.col.sourceType')} / ${t('app.kuaizhizao.purchaseRequisition.col.sourceCode')}`,
      dataIndex: 'source_type',
      width: 180,
      minWidth: 180,
      uniTableKeepWidth: true,
      resizable: false,
      hideInSearch: false,
      // 叠列两行；ellipsis 会破坏居中，补货建议等较长单号时易看起来左对齐
      ellipsis: false,
      align: 'center',
      valueEnum: {
        DemandComputation: {
          text: formatPurchaseRequisitionSourceType('DemandComputation', t),
        },
        ReplenishmentSuggestion: {
          text: formatPurchaseRequisitionSourceType('ReplenishmentSuggestion', t),
        },
      },
      render: (_, record) => {
        const sourceCode = String(record.source_code ?? '').trim();
        if (!sourceCode) {
          return t('app.kuaizhizao.purchaseRequisition.col.sourceTypeActiveRequest');
        }
        return (
          <Space
            orientation="vertical"
            size={0}
            align="center"
            style={{ lineHeight: 1.35, width: '100%' }}
          >
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {formatPurchaseRequisitionSourceType(record.source_type, t)}
            </Typography.Text>
            <SourceDocumentCode
              sourceType={record.source_type}
              sourceId={record.source_id}
              sourceCode={sourceCode}
            />
          </Space>
        );
      },
    },
    {
      title: t('app.kuaizhizao.common.colLineMaterials'),
      ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
      render: (_, record) => renderDocumentLineMaterialsPreview(record.items, t),
    },
    {
      title: t('app.kuaizhizao.purchaseRequisition.col.requiredDate'),
      dataIndex: 'required_date',
      valueType: 'date',
      width: 132,
      minWidth: 132,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
    },
    {
      title: t('app.kuaizhizao.salesManagement.pushProgress.title'),
      dataIndex: 'downstream_push_progress',
      ...DOCUMENT_PROGRESS_COLUMN_DEFAULTS,
      render: (_, record) => (
        <DocumentPushProgressBar percent={resolveRequisitionPushPercent(record)} />
      ),
    },
    {
      title: t('common.quantity'),
      dataIndex: 'total_quantity',
      width: 100,
      minWidth: 100,
      uniTableKeepWidth: true,
      resizable: false,
      align: 'right',
      hideInSearch: true,
      render: (_, record) =>
        formatQuantity(record.total_quantity),
    },
    {
      title: t('app.kuaizhizao.salesOrder.totalAmountLabel'),
      dataIndex: 'total_amount',
      width: 120,
      minWidth: 120,
      uniTableKeepWidth: true,
      resizable: false,
      align: 'right',
      hideInSearch: true,
      render: (_, record) =>
        record.total_amount != null ? formatCurrencyAmount(record.total_amount) : '-',
    },
    ...buildDocumentAuditColumns<PurchaseRequisition>(t),
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
    ...(purchaseRequisitionAuditColumn ? [purchaseRequisitionAuditColumn] : []),
    buildDocumentAttachmentsListColumn<PurchaseRequisition>(t, { allowPreview: true }),
    {
      title: t('app.kuaizhizao.purchaseRequisition.col.lifecycle'),
      key: 'lifecycle',
      dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
      fixed: 'right',
      hideInSearch: false,
      valueEnum: lifecycleValueEnum,
      render: (_, record) => (
        <ListUniLifecycleCell
          lifecycle={getPurchaseRequisitionLifecycle(record, purchaseRequestAuditEnabled)}
          withSubStages
        />
      ),
    },
    {
      title: t('common.actions'),
      key: 'option',
      valueType: 'option',
      fixed: 'right',
      hideInSearch: true,
      render: (_, record) => {
        const parts: React.ReactNode[] = [
          <Button {...rowActionKind('read')} key="d" onClick={() => handleDetail(record)}>
            {t('common.detail')}
          </Button>,
        ];
        if (record.capabilities?.update?.allowed === true && purchaseRequisitionPerms.canUpdate) {
          parts.push(
            <Button {...rowActionKind('update')} key="e" onClick={() => handleEdit(record)}>
              {t('common.edit')}
            </Button>
          );
        }
        parts.push(
          <span {...rowActionKind('skip')} key="wf">
            <UniWorkflowActions {...rowActionKind('skip')}
              record={record}
              entityName={t('app.kuaizhizao.purchaseRequisition.entityName')}
              {...PURCHASE_REQUISITION_WORKFLOW_PROPS}
              theme="link"
              size="small"
              confirmMessages={{ revoke: t('app.kuaizhizao.purchaseRequisition.workflowRevokeConfirm') }}
              onSuccess={() => {
                invalidateMenuBadgeCounts();
    actionRef.current?.reload();
                if (detailVisible && currentReq?.id === record.id && record.id != null) {
                  void getPurchaseRequisition(record.id)
                    .then((res) => {
                      setCurrentReq(res);
                      setPrTrackingRefreshKey((k) => k + 1);
                    })
                    .catch(() => {});
                }
              }}
            />
          </span>
        );
        if (record.capabilities?.delete?.allowed === true && purchaseRequisitionPerms.canDelete) {
          parts.push(
            <ActionConfirmPopconfirm title={t('app.kuaizhizao.purchaseRequisition.confirmDelete')} description={t('app.kuaizhizao.purchaseRequisition.confirmDeleteContent', { code: record.requisition_code })} onConfirm={() => executeDeleteOne(record)}>
              <Button {...rowActionKind('delete')} key="del" onClick={(e) => e.stopPropagation()}>
              {t('common.delete')}
            </Button>
            </ActionConfirmPopconfirm>
          );
        }
        return parts;
      },
    },
  ], SALES_DOC_LIST_FIELD_RANK), [t, purchaseRequestAuditEnabled, purchaseRequisitionAuditColumn, lifecycleValueEnum, handleDetail, handleEdit, handleDeleteOne, resolveRequisitionPushPercent, detailVisible, currentReq?.id, invalidateMenuBadgeCounts, purchaseRequisitionPerms.canDelete]);

  const detailTableColumns: ProColumns<PurchaseRequisitionItemRow>[] = useMemo(
    () =>
      alignProColumns<PurchaseRequisitionItemRow>(
        [
          {
            title: t('app.kuaizhizao.purchaseRequisition.col.nameAndCode'),
            key: 'requisition_code',
            dataIndex: 'requisition_code',
            width: 240,
            minWidth: 240,
            uniTableKeepWidth: true,
            uniTablePrimaryFlex: false,
            resizable: false,
            fixed: 'left',
            hideInSearch: false,
            fieldProps: { placeholder: t('app.kuaizhizao.purchaseRequisition.col.code') },
            render: (_, record) => (
              <UniTableStackedPrimaryCell
                primary={String(record.requisition_name ?? '')}
                secondary={String(record.requisition_code ?? '')}
              />
            ),
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.col.code'),
            dataIndex: 'requisition_code',
            hideInTable: true,
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.col.name'),
            dataIndex: 'requisition_name',
            hideInTable: true,
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.col.materialName'),
            key: 'material_display',
            dataIndex: 'material_name',
            // 明细视图：物料叠列为 RemainderFlex（无头表明细预览列）
            minWidth: 160,
            uniTablePrimaryFlex: true,
            uniTableRemainderFlex: true,
            resizable: false,
            ellipsis: false,
            render: (_, record) => (
              <MaterialStackedCell
                material_name={record.material_name}
                material_code={record.material_code}
                material_spec={record.material_spec}
              />
            ),
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.col.materialCode'),
            dataIndex: 'material_code',
            hideInTable: true,
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.col.applicant'),
            dataIndex: 'applicant_name',
            key: 'applicant_name',
            width: 96,
            minWidth: 96,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
            render: (_, record) => String(record.applicant_name ?? '').trim() || '-',
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.col.department'),
            dataIndex: 'department_name',
            key: 'department_name',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
            render: (_, record) => String(record.department_name ?? '').trim() || '-',
          },
          {
            title: t('common.quantity'),
            dataIndex: 'quantity',
            width: 100,
            minWidth: 100,
            uniTableKeepWidth: true,
            resizable: false,
            align: 'right',
            render: (val: unknown, record) => (
              <QuantityWithUnitDisplay quantity={val} unit={record.unit} />
            ),
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.form.suggestedSupplier'),
            dataIndex: 'supplier_name',
            key: 'supplier_name',
            width: 132,
            minWidth: 132,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
            render: (_: unknown, row) => {
              const name = String(row.supplier_name ?? '').trim();
              return name || '—';
            },
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.col.suggestedPrice'),
            dataIndex: 'suggested_unit_price',
            width: 100,
            minWidth: 100,
            uniTableKeepWidth: true,
            resizable: false,
            align: 'right',
            render: (text: unknown) =>
              text != null ? formatCurrencyPrice(text) : '-',
          },
          {
            title: t('app.kuaizhizao.salesOrder.totalAmountLabel'),
            key: 'line_amount',
            dataIndex: 'total_amount',
            width: 110,
            minWidth: 110,
            uniTableKeepWidth: true,
            resizable: false,
            align: 'right',
            render: (_: unknown, record) => {
              const qty = Number(record.quantity ?? 0);
              const price = Number(record.suggested_unit_price ?? 0);
              return formatCurrencyAmount(computeSimpleDocumentLineTotal(qty, price));
            },
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.col.requiredDate'),
            dataIndex: 'required_date',
            width: 132,
            minWidth: 132,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_: unknown, row) =>
              row.required_date ? formatDateTime(row.required_date, 'YYYY-MM-DD') : '-',
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.form.lineNotes'),
            dataIndex: 'notes',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
            hideInSearch: true,
            render: (_: unknown, row) => {
              const text = String(row.notes ?? '').trim();
              return text || '-';
            },
          },
          {
            title: t('app.kuaizhizao.salesManagement.pushProgress.title'),
            key: 'line_push_progress',
            // 与表格视图同一套进度列（勿用 DETAIL 右固定，否则会落到更新时间右侧）
            ...DOCUMENT_PROGRESS_COLUMN_DEFAULTS,
            render: (_: unknown, record) => {
              const ordered = Number(record.quantity ?? 0);
              const pushed =
                Number(record.converted_quantity_confirmed ?? 0) +
                Number(record.converted_quantity_draft ?? 0);
              const percent = ratioToPushProgressPercent(pushed, ordered);
              return (
                <DocumentPushProgressBar
                  percent={percent}
                  tooltip={t('app.kuaizhizao.salesManagement.pushProgress.percentOnly', { percent })}
                />
              );
            },
          },
          ...buildDocumentAuditColumns<PurchaseRequisitionItemRow>(t),
          ...(purchaseRequisitionAuditColumn
            ? [purchaseRequisitionAuditColumn as ProColumns<PurchaseRequisitionItemRow>]
            : []),
          buildDocumentAttachmentsListColumn<PurchaseRequisitionItemRow>(t),
          {
            title: t('app.kuaizhizao.purchaseRequisition.col.lifecycle'),
            key: 'lifecycle',
            dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
            fixed: 'right',
            hideInSearch: false,
            valueEnum: lifecycleValueEnum,
            render: (_: unknown, record) => (
              <ListUniLifecycleCell
                lifecycle={getPurchaseRequisitionLifecycle(
                  record as unknown as PurchaseRequisition,
                  purchaseRequestAuditEnabled,
                )}
                withSubStages
              />
            ),
          },
          {
            title: t('common.actions'),
            key: 'option',
            valueType: 'option',
            fixed: 'right',
            hideInSearch: true,
            render: (_, record) => {
              const headerId = Number(record.requisition_id ?? record._headerId);
              const header =
                (tableRowsRef.current as PurchaseRequisition[]).find((row) => Number(row.id) === headerId) ??
                ({ id: headerId, ...record } as unknown as PurchaseRequisition);
              const parts: React.ReactNode[] = [
                <Button
                  {...rowActionKind('read')}
                  key="d"
                  onClick={() => handleDetail(header)}
                >
                  {t('common.detail')}
                </Button>,
              ];
              if (header.capabilities?.update?.allowed === true && purchaseRequisitionPerms.canUpdate) {
                parts.push(
                  <Button
                    {...rowActionKind('update')}
                    key="e"
                    onClick={() => handleEdit(header)}
                  >
                    {t('common.edit')}
                  </Button>,
                );
              }
              return parts;
            },
          },
        ],
        GLOBAL_DOC_DETAIL_TABLE_FIELD_RANK,
      ),
    [
      t,
      lifecycleValueEnum,
      purchaseRequestAuditEnabled,
      purchaseRequisitionAuditColumn,
      purchaseRequisitionPerms.canUpdate,
      handleDetail,
      handleEdit,
    ],
  );

  const renderPurchaseRequisitionForm = () => (
    <>
      <DetailDrawerSection
        titleAccent
        title={t('app.uniDetail.sectionBasic')}
        titleExtra={<PurchaseRequisitionFormFieldSettings />}
      >
        <div className="document-form-untitled-groups">
          <div className="document-form-untitled-group">
            <Row gutter={16}>
              <Col span={12}>
                <ProFormText
                  name="requisition_code"
                  label={t('app.kuaizhizao.purchaseRequisition.form.code')}
                  disabled={editingId != null && !prCodeEditability.editable}
                  extra={
                    editingId != null && prCodeEditability.lockedReason
                      ? t(prCodeEditability.lockedReason)
                      : undefined
                  }
                  placeholder={
                    editingId != null
                      ? t('app.kuaizhizao.purchaseRequisition.form.codeAuto')
                      : isAutoGenerateEnabled('kuaizhizao-purchase-requisition')
                        ? t('app.kuaizhizao.purchaseRequisition.form.codeAuto')
                        : t('app.kuaizhizao.purchaseRequisition.form.codeManual')
                  }
                  rules={[{ required: true, message: t('app.kuaizhizao.purchaseRequisition.form.codeManual') }]}
                />
              </Col>
              <Col span={12}>
                <ProForm.Item
                  name="order_type"
                  label={t('app.kuaizhizao.purchaseRequisition.form.orderType')}
                  initialValue="标准采购"
                >
                  <UniDropdown
                    options={orderTypeOptions}
                    loading={orderTypeLoading}
                    placeholder={t('app.kuaizhizao.purchaseOrder.form.orderTypePlaceholder')}
                  />
                </ProForm.Item>
              </Col>
              {showRequisitionNameField ? (
                <Col span={12}>
                  <ProFormText
                    name="requisition_name"
                    label={t('app.kuaizhizao.purchaseRequisition.form.name')}
                    placeholder={t('app.kuaizhizao.purchaseRequisition.form.namePlaceholder')}
                  />
                </Col>
              ) : (
                <Col span={12}>
                  <EquipmentPersonSelect
                    uuidFieldName="applicant_uuid"
                    idFieldName="applicant_id"
                    nameFieldName="applicant_name"
                    label={t('app.kuaizhizao.purchaseRequisition.form.applicant')}
                    formRef={createFormRef}
                    required
                    onUserChange={applyDepartmentFromApplicantUser}
                  />
                </Col>
              )}
            </Row>
          </div>
          <div className="document-form-untitled-group">
            <Row gutter={16}>
              {showRequisitionNameField ? (
                <Col span={12}>
                  <EquipmentPersonSelect
                    uuidFieldName="applicant_uuid"
                    idFieldName="applicant_id"
                    nameFieldName="applicant_name"
                    label={t('app.kuaizhizao.purchaseRequisition.form.applicant')}
                    formRef={createFormRef}
                    required
                    onUserChange={applyDepartmentFromApplicantUser}
                  />
                </Col>
              ) : null}
              <Col span={12}>
                <ProFormDatePicker
                  name="requisition_date"
                  label={t('app.kuaizhizao.purchaseRequisition.form.date')}
                  fieldProps={{
                    style: { width: '100%' },
                    onChange: () => {
                      const items = normalizeFormListItems<Record<string, unknown>>(
                        createFormRef.current?.getFieldValue('items'),
                      );
                      items.forEach((_, idx) => {
                        void repriceUnlockedPurchaseDocumentLineIfNeeded(createFormRef.current, idx, {
                          asOfField: 'requisition_date',
                          unitPriceField: 'suggested_unit_price',
                        });
                      });
                    },
                  }}
                />
              </Col>
            </Row>
            <Row gutter={16} wrap={false}>
              <Col flex="1 1 0" style={{ minWidth: 0 }}>
                <ProFormDatePicker
                  name="required_date"
                  label={t('app.kuaizhizao.purchaseRequisition.form.requiredDate')}
                  rules={[
                    {
                      required: true,
                      message: t('app.kuaizhizao.purchaseRequisition.form.requiredDateRequired'),
                    },
                  ]}
                  fieldProps={buildFutureDateShortcutFieldProps({
                    getForm: () => createFormRef.current,
                    fieldName: 'required_date',
                    baseFieldName: 'requisition_date',
                    allowPastDates: true,
                    t,
                    onApply: (date) => {
                      createFormRef.current?.setFieldValue?.('required_date', date);
                      applyHeaderDeliveryToItemLines(date);
                    },
                    fieldProps: {
                      onChange: (value: unknown) => {
                        applyHeaderDeliveryToItemLines(value);
                      },
                    },
                  })}
                />
              </Col>
              <Col flex="1 1 0" style={{ minWidth: 0 }} aria-hidden />
              <Col flex="1 1 0" style={{ minWidth: 0 }} aria-hidden />
              <Col flex="1 1 0" style={{ minWidth: 0 }} aria-hidden />
              <Col flex="1 1 0" style={{ minWidth: 0 }} aria-hidden />
            </Row>
          </div>
          <div className="document-form-untitled-group">
            <Row gutter={16}>
              {showRequisitionNameField ? (
                <Col span={12}>
                  <ProFormDatePicker
                    name="required_date"
                    label={t('app.kuaizhizao.purchaseRequisition.form.requiredDate')}
                    fieldProps={buildFutureDateShortcutFieldProps({
                      getForm: () => createFormRef.current,
                      fieldName: 'required_date',
                      baseFieldName: 'requisition_date',
                      t,
                      onApply: (date) => {
                        createFormRef.current?.setFieldValue?.('required_date', date);
                        applyHeaderDeliveryToItemLines(date);
                      },
                      fieldProps: {
                        onChange: (value: unknown) => {
                          applyHeaderDeliveryToItemLines(value);
                        },
                      },
                    })}
                  />
                </Col>
              ) : null}
              <Col span={12}>
                <PurchaseDepartmentFormField
                  options={departmentOptions}
                  loading={departmentOptionsLoading}
                />
              </Col>
            </Row>
          </div>
        </div>
      </DetailDrawerSection>

      <DetailDrawerSection titleAccent title={t('app.uniDetail.sectionLines')}>
        <AntForm.Item noStyle shouldUpdate={(prev, curr) => prev?.items !== curr?.items}>
          {({ getFieldValue }) => {
            const formItems = (getFieldValue('items') as Array<{ material_id?: number }>) ?? [];
            const lineMaterialIds = formItems
              .map((row) => Number(row?.material_id))
              .filter((id) => Number.isFinite(id) && id > 0);
            return (
              <PurchaseRequisitionLineStockProvider materialIds={lineMaterialIds}>
        <UniTableDetail
          name="items"
          title={t('app.kuaizhizao.purchaseRequisition.form.itemsTitle')}
          required
          requiredMessage={t('app.kuaizhizao.purchaseRequisition.form.itemsRequired')}
          headerExtra={(
            <Space size={8}>
              <Button
                type="default"
                icon={<ImportOutlined />}
                onClick={() => setImportModalVisible(true)}
              >
                {t('app.kuaizhizao.purchaseRequisition.form.importItems')}
              </Button>
              <Button
                type="default"
                icon={<PlusOutlined />}
                onClick={() => {
                  const items = [...normalizeFormListItems<any>(createFormRef.current?.getFieldValue('items'))];
                  items.push({
                    ...INITIAL_PR_FORM_ITEM_ROW,
                    required_date: resolveHeaderRequiredDateDefault(),
                  });
                  createFormRef.current?.setFieldsValue({ items });
                }}
              >
                {t('app.kuaizhizao.purchaseRequisition.form.addLine')}
              </Button>
              <Button
                type="default"
                icon={<AppstoreAddOutlined />}
                onClick={() => {
                  const orderType = String(createFormRef.current?.getFieldValue('order_type') ?? '').trim();
                  setMaterialPickSourceType(orderType === '服务采购' ? 'Service' : undefined);
                  setMaterialPickerOpen(true);
                }}
              >
                {t('app.kuaizhizao.common.materialBatchSelect')}
              </Button>
            </Space>
          )}
          columns={[
                  {
                    title: t('app.kuaizhizao.purchaseRequisition.form.material'),
                    dataIndex: 'material_id',
                    width: 220,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        noStyle
                        shouldUpdate={(prev: any, curr: any) =>
                          prev?.order_type !== curr?.order_type || prev?.items?.[index] !== curr?.items?.[index]
                        }
                      >
                        {({ getFieldValue }: any) => {
                          const row = getFieldValue('items')?.[index];
                          const materialSourceType =
                            String(getFieldValue('order_type') ?? '').trim() === '服务采购'
                              ? 'Service'
                              : undefined;
                          const mid = row?.material_id ? Number(row.material_id) : null;
                          const fallback =
                            mid && (row?.material_code || row?.material_name)
                              ? {
                                  value: mid,
                                  label:
                                    `${row.material_code || ''} - ${row.material_name || ''}`.trim() || String(mid),
                                }
                              : undefined;
                          return (
                            <>
                              <div
                                className="uni-detail-material-cell"
                                style={{ display: 'flex', alignItems: 'center', width: '100%', gap: 8 }}
                              >
                                <div style={{ flex: 1, minWidth: 200 }}>
                                  <UniMaterialSelect
                                    name={[index, 'material_id']}
                                    label=""
                                    placeholder={t('app.kuaizhizao.salesOrder.selectMaterial')}
                                    required
                                    size="small"
                                    listFieldKey={index}
                                    listFieldName="items"
                                    fillMapping={withMaterialLineFillMapping()}
                                    onChange={(_val, material) => {
                                      if (!material) return;
                                      createFormRef.current?.setFieldValue(
                                        ['items', index, 'unit'],
                                        resolveMaterialScenarioUnit(material, 'purchase'),
                                      );
                                      const defaultSupplierId =
                                        resolveDefaultSupplierIdFromMaterial(material as Material);
                                      if (defaultSupplierId) {
                                        createFormRef.current?.setFieldValue(
                                          ['items', index, 'supplier_id'],
                                          defaultSupplierId,
                                        );
                                      }
                                      void applyPurchaseDocumentLineMaterialPricing(
                                        createFormRef.current,
                                        index,
                                        material,
                                        {
                                          asOfField: 'requisition_date',
                                          unitPriceField: 'suggested_unit_price',
                                          includeTaxRate: false,
                                          supplierId: defaultSupplierId,
                                        },
                                      );
                                    }}
                                    fallbackOption={fallback}
                                    formItemProps={{ style: { margin: 0 } }}
                                    showQuickCreate
                                    showAdvancedSearch
                                    sourceType={materialSourceType}
                                  skipFuzzyPinyinClientFilter
                                  />
                                </div>
                              </div>
                              <AntForm.Item name={[index, 'demand_computation_item_id']} hidden preserve>
                                <Input type="hidden" />
                              </AntForm.Item>
                              <AntForm.Item name={[index, 'material_code']} hidden preserve>
                                <Input type="hidden" />
                              </AntForm.Item>
                              <AntForm.Item name={[index, 'material_name']} hidden preserve>
                                <Input type="hidden" />
                              </AntForm.Item>
                            </>
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('app.kuaizhizao.purchaseRequisition.form.totalStock'),
                    dataIndex: '_warehouse_stock',
                    width: 120,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        noStyle
                        shouldUpdate={(prev: any, curr: any) =>
                          prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id
                        }
                      >
                        {({ getFieldValue }) => {
                          const materialId = getFieldValue(['items', index, 'material_id']);
                          return <PurchaseRequisitionLineStockCell materialId={materialId} />;
                        }}
                      </AntForm.Item>
                    ),
                  },
                  ...buildDocumentDetailSpecModelFormColumns(t, { width: 120, inputSize: 'small' }),
                  {
                    title: t('common.quantity'),
                    dataIndex: 'quantity',
                    width: 100,
                    align: 'right' as const,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        name={[index, 'quantity']}
                        rules={[
                          { required: true, message: t('common.required') },
                          { type: 'number', min: 0.01, message: t('app.kuaizhizao.purchaseRequisition.form.quantityMin') },
                        ]}
                        style={{ margin: 0 }}
                      >
                        {({ getFieldValue }) => {
                          const materialId = getFieldValue(['items', index, 'material_id']);
                          if (!createFormRef.current) return null;
                          return (
                            <>
                              <AntForm.Item name={[index, 'unit']} hidden preserve>
                                <Input type="hidden" />
                              </AntForm.Item>
                              <DocumentLineDualQuantityFormCell
                                form={createFormRef.current}
                                listName="items"
                                rowIndex={index}
                                quantityField="quantity"
                                unitField="unit"
                                scenario="purchase"
                                quantityPrecision={quantityDecimals}
                                materialId={materialId}
                                inlineUnitWithQuantity
                                onAfterQuantityChange={() => {
                                  void repriceUnlockedPurchaseDocumentLineIfNeeded(
                                    createFormRef.current,
                                    index,
                                    {
                                      asOfField: 'requisition_date',
                                      unitPriceField: 'suggested_unit_price',
                                    },
                                  );
                                }}
                              />
                            </>
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('app.kuaizhizao.purchaseRequisition.form.suggestedPrice'),
                    dataIndex: 'suggested_unit_price',
                    width: 130,
                    align: 'right' as const,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        noStyle
                        shouldUpdate={(prev: any, curr: any) =>
                          prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id
                        }
                      >
                        {({ getFieldValue }: any) => {
                          const price = getFieldValue(['items', index, 'suggested_unit_price']);
                          return (
                            <>
                              <SuggestedPriceStoreRepair
                                form={createFormRef.current}
                                rowIndex={index}
                                raw={price}
                              />
                              <AntForm.Item name={[index, 'suggested_unit_price']} style={{ margin: 0 }}>
                                <InputNumber placeholder="0" min={0} precision={priceDecimals} style={{ width: 80 }} size="small" />
                              </AntForm.Item>
                            </>
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('app.kuaizhizao.purchaseRequisition.form.suggestedSupplier'),
                    dataIndex: 'supplier_id',
                    width: 200,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item name={[index, 'supplier_id']} style={{ margin: 0 }}>
                        <SupplierSelectDropdown
                          hostResource={KUAIZHIZAO_DOC_HOST.purchaseRequisition}
                          suppliers={supplierList as Supplier[]}
                          onSuppliersChange={(list) => setSupplierList(list)}
                          placeholder={t('app.kuaizhizao.purchaseRequisition.form.optional')}
                          size="small"
                          style={{ width: '100%' }}
                          onSupplierPick={(s) => {
                            if (!s) return;
                            void repriceUnlockedPurchaseDocumentLineIfNeeded(createFormRef.current, index, {
                              asOfField: 'requisition_date',
                              unitPriceField: 'suggested_unit_price',
                              supplierId: Number(s.id),
                            });
                          }}
                        />
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('app.kuaizhizao.purchaseRequisition.form.lineDelivery'),
                    dataIndex: 'required_date',
                    width: 118,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        name={[index, 'required_date']}
                        rules={[{ required: true, message: t('common.required') }]}
                        style={{ margin: 0 }}
                        getValueProps={(value) => ({ value: coerceFormDate(value) ?? undefined })}
                        normalize={(value) => coerceFormDate(value) ?? undefined}
                      >
                        <FutureDatePicker
                          size="small"
                          style={{ width: '100%' }}
                          placeholder={t('app.kuaizhizao.purchaseRequisition.form.lineDelivery')}
                          getForm={() => createFormRef.current}
                          baseFieldName="requisition_date"
                          t={t}
                          onApply={(date) =>
                            createFormRef.current?.setFieldValue?.(['items', index, 'required_date'], date)
                          }
                        />
                      </AntForm.Item>
                    ),
                  },
                  ...buildDocumentDetailPartnerMaterialFormColumns(t, 'supplier', {
                    width: 120,
                    inputSize: 'small',
                  }),
                  buildDocumentLineAttachmentsFormColumn(
                    t,
                    DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY.purchaseRequisition,
                  ),
                  {
                    title: t('app.kuaizhizao.purchaseRequisition.form.lineNotes'),
                    dataIndex: 'notes',
                    width: 120,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item name={[index, 'notes']} style={{ margin: 0 }}>
                        <Input placeholder={t('common.remark')} size="small" />
                      </AntForm.Item>
                    ),
                  },
                ]}
          disabledAdd
          minRows={1}
          initialValue={{ ...INITIAL_PR_FORM_ITEM_ROW }}
          tableProps={{
            className: 'purchase-requisition-detail-table',
            size: 'small',
            style: { width: '100%', margin: 0 },
          }}
        />
              </PurchaseRequisitionLineStockProvider>
            );
          }}
        </AntForm.Item>
        <ProFormTextArea name="notes" label={t('common.remark')} placeholder={t('common.remark')} />
      </DetailDrawerSection>

      <DetailDrawerSection titleAccent title={t('app.uniDetail.sectionAttachments')} marginBottom={0}>
        <DocumentAttachmentsField category="purchase_requisition_attachments" label={false} />
      </DetailDrawerSection>
    </>
  );

  useSubmitShortcut(() => void triggerPurchaseRequisitionPrimarySubmit(), isFormPage);

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
                onClick={leavePurchaseRequisitionFormPage}
              />
              <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
                {isCreatePage
                  ? t('app.kuaizhizao.menu.purchase-management.purchase-requisitions.new')
                  : t('app.kuaizhizao.menu.purchase-management.purchase-requisitions.edit')}
              </Typography.Title>
            </Space>
            <DocumentFormPageHeaderActions
              onCancel={leavePurchaseRequisitionFormPage}
              onSaveDraft={() => void handlePurchaseRequisitionSaveDraft()}
              onPrimarySubmit={() => void triggerPurchaseRequisitionPrimarySubmit()}
              isCreatePage={isCreatePage}
              showSaveDraft
              primaryCreateLabel={t('components.layoutTemplates.documentFormPage.saveAndSubmit')}
              primaryLoading={formSubmitting}
            />
            </>
          }
        >
          <div className="form-modal-content-inner">
              <ProForm
                key={
                  isCreatePage
                    ? `purchase-requisition-create:${location.search}`
                    : `purchase-requisition-edit:${editRouteId ?? ''}`
                }
                formRef={createFormRef}
                layout="vertical"
                submitter={false}
                scrollToFirstError
                onFinish={handleModalSubmit}
                onValuesChange={() => {
                  if (prFormHydratingRef.current || !prFormDraftKey) return;
                  const values = createFormRef.current?.getFieldsValue?.(true);
                  if (values && Object.keys(values).length > 0) {
                    setDocumentFormDraft(prFormDraftKey, {
                      ...values,
                      ...(documentFlowSubmitExtrasRef.current ?? {}),
                    });
                  }
                }}
                onFinishFailed={({ errorFields }) => {
                  const first = errorFields?.[0];
                  const errText = first?.errors?.filter(Boolean)[0];
                  messageApi.error(errText || t('components.layoutTemplates.formModal.checkFormHint'));
                }}
                initialValues={
                  isCreatePage
                    ? {
                        order_type: '标准采购',
                        requisition_date: dayjs(),
                        ...(purchaseRequisitionCreateSeed ?? { items: initialCreateItems }),
                      }
                    : undefined
                }
              >
                {renderPurchaseRequisitionForm()}
              </ProForm>
            </div>
        </DocumentFormPageLayout>
        <UniMaterialBatchPicker
          open={materialPickerOpen}
          sourceType={materialPickSourceType}
          onCancel={() => setMaterialPickerOpen(false)}
          onConfirm={appendRequisitionItemsFromMaterials}
        />
        <Suspense fallback={null}>
          <LazyUniImport
            visible={importModalVisible}
            onCancel={() => setImportModalVisible(false)}
            onConfirm={handleItemImport}
            title={t('app.kuaizhizao.purchaseRequisition.import.title')}
            headers={[t('app.kuaizhizao.purchaseRequisition.import.materialCode'), t('app.kuaizhizao.purchaseRequisition.import.spec'), t('common.unit'), t('common.quantity'), t('app.kuaizhizao.purchaseRequisition.import.suggestedPrice'), t('app.kuaizhizao.purchaseRequisition.import.lineDelivery'), t('app.kuaizhizao.purchaseRequisition.import.lineNotes')]}
            exampleRow={['MAT001', 'Spec X', pickImportExampleValue(requisitionLineUnitOptions, t('app.kuaizhizao.purchaseRequisition.import.exampleUnit')), '10', '100', '2026-03-01', '']}
            columnOptions={requisitionLineImportColumnOptions}
          />
        </Suspense>
      </>
    );
  }

  return (
    <>
      {purchaseRequisitionAuditModal}
      {purchaseRequisitionInitiatorModal}
      {purchaseRequisitionListInitiatorModal}
      <ListPageTemplate>
        <UniTable
          headerTitle={t('app.kuaizhizao.menu.purchase-management.purchase-requisitions')}
          columnPersistenceId={PURCHASE_REQUISITION_LIST_PERSISTENCE_ID}
          actionRef={actionRef}
          viewTypes={['table', 'detailTable', 'help']}
          defaultViewType={viewTypeState === 'help' ? 'table' : viewTypeState}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.purchaseRequisition)}
          onViewTypeChange={(v) => {
            dataViewModeRef.current = resolveDetailTableViewMode(v as 'table' | 'detailTable' | 'help');
            setViewTypeState(v as 'table' | 'detailTable' | 'help');
            setTimeout(() => actionRef.current?.reload(), 0);
          }}
          detailTableColumns={detailTableColumns}
          request={async (params: any, sort: any, _filter: any, searchFormValues?: Record<string, any>) => {
            const apiParams = resolvePurchaseRequisitionListApiParams(
              params,
              sort,
              searchFormValues,
              params,
            ) as Parameters<typeof listPurchaseRequisitions>[0];
            const res = await listPurchaseRequisitions(apiParams);
            const requisitions = res.data || [];
            const total = res.total || 0;
            // 行缓存唯一真源：onTableDataChange（prefetch 会走本 request，禁止在此覆盖）
            if (dataViewModeRef.current === 'order') {
              return { data: requisitions, success: res.success ?? true, total };
            }
            const flatRows = flattenDocumentDetailRows<PurchaseRequisition, PurchaseRequisitionItem>({
              headers: requisitions,
              getHeaderId: (h) => h.id,
              getItems: (h) => h.items,
              buildRowKey: (h, item, index) =>
                item?.id
                  ? `req-${h.id}-item-${item.id}`
                  : `req-${h.id}-idx-${index}`,
              mapItemRow: (h, item) => ({
                ...item,
                header_attachments_count:
                  h.header_attachments_count ?? countDocumentAttachments(h.attachments),
                line_attachments_count: countDocumentAttachments(item.attachments),
                attachments_count:
                  (h.header_attachments_count ?? countDocumentAttachments(h.attachments)) +
                  countDocumentAttachments(item.attachments),
                requisition_id: h.id ?? 0,
                requisition_code: h.requisition_code,
                requisition_name: h.requisition_name,
                source_type: h.source_type,
                source_code: h.source_code,
                applicant_id: h.applicant_id,
                applicant_name: h.applicant_name,
                department_id: h.department_id,
                department_name: h.department_name,
                status: h.status,
                review_status: h.review_status,
                downstream_push_progress: h.downstream_push_progress,
                lifecycle: h.lifecycle,
                capabilities: h.capabilities,
                audit: h.audit,
                created_at: h.created_at,
                updated_at: h.updated_at,
                created_by_name: h.created_by_name,
                updated_by_name: h.updated_by_name,
              }),
              mapEmptyHeaderRow: (h) => ({
                requisition_id: h.id ?? 0,
                requisition_code: h.requisition_code,
                requisition_name: h.requisition_name,
                applicant_id: h.applicant_id,
                applicant_name: h.applicant_name,
                department_id: h.department_id,
                department_name: h.department_name,
                material_id: 0,
                material_code: '-',
                material_name: '-',
                unit: '',
                quantity: 0,
                suggested_unit_price: 0,
                status: h.status,
                review_status: h.review_status,
                lifecycle: h.lifecycle,
              }),
            }) as PurchaseRequisitionItemRow[];
            return { data: flatRows, success: res.success ?? true, total };
          }}
          onTableDataChange={(rows) => {
            if (dataViewModeRef.current === 'order') {
              tableRowsRef.current = rows as PurchaseRequisition[];
              setDetailFlatRows([]);
              return;
            }
            setDetailFlatRows(rows as PurchaseRequisitionItemRow[]);
          }}
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          columns={columns}
          rowKey={dataViewMode === 'detail' ? '_rowKey' : 'id'}
          enableRowSelection={viewTypeState !== 'detailTable'}
          showAdvancedSearch={true}
          skipFuzzyPinyinClientFilter
          pinnedTabsField={LIST_LIFECYCLE_STAGE_FIELD}
          pinnedTabsValueEnum={lifecycleValueEnum}
          showCreateButton={false}
          createButtonText={t('app.kuaizhizao.menu.purchase-management.purchase-requisitions.new')}
          onCreate={handleCreate}
          toolBarRender={() => [
            <UniPullCreateToolbar
              compactKey="create-purchase-requisition-with-pull"
              createIcon={<PlusOutlined />}
              createLabel={t('app.kuaizhizao.menu.purchase-management.purchase-requisitions.new')}
              onCreate={handleCreate}
              menuItems={[
                ...buildKuaizhizaoPullCreateMenuItems(t, [
                  {
                    key: 'pull-from-demand-computation',
                    actionKey: 'purchase_requisition.pull_from_demand_computation',
                    onClick: () => {
                      pullFromComputationQuery.openModal();
                    },
                  },
                  {
                    key: 'pull-from-sales-order',
                    actionKey: 'purchase_requisition.pull_from_sales_order',
                    onClick: () => {
                      if (!purchaseRequisitionPerms.canCreate) {
                        messageApi.warning(t('common.permissionDenied'));
                        return;
                      }
                      pullFromSalesOrderQuery.openModal();
                    },
                  },
                ]),
                { type: 'divider', key: 'copy-selected-divider' },
                {
                  key: 'copy-selected',
                  label: t('app.kuaizhizao.purchaseRequisition.copySelectedCreate'),
                  disabled: !selectedRequisitionForToolbar,
                  onClick: () => void handleCopySelectedPurchaseRequisition(),
                },
              ]}
            />,
            <UniPushToolbarButton
              key={`purchase-requisition-push-${selectedRequisitionForToolbar?.id ?? 'none'}`}
              menuItems={toolbarPushMenuItems}
              disabled={selectedRowKeys.length !== 1 || !selectedRequisitionForToolbar}
              disabledReason={toolbarPushDisabledReason}
              sourceDocument={
                selectedRequisitionForToolbar?.id
                  ? { type: 'purchase_requisition', id: Number(selectedRequisitionForToolbar.id) }
                  : null
              }
              pushTargets={{
                'push-purchase-order': 'purchase_order',
                'push-inquiry': 'purchase_inquiry',
              }}
            />,
          ]}
          showDeleteButton={true}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) => t('app.kuaizhizao.purchaseRequisition.confirmBatchDelete', { count })}
          toolBarActionsAfterDelete={[
            <UniAuditBatchMenuButton
              key="purchase-requisition-batch-menu"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedRequisitionsForBatch}
              auditEnabled={purchaseRequestAuditEnabled}
              permGates={purchaseRequisitionPerms}
              handlers={purchaseRequisitionAuditBatchHandlers}
              onSuccess={handlePurchaseRequisitionAuditBatchSuccess}
              toolBarButtonSize="medium"
            />,
          ]}
          rightToolBarActionsBeforeExport={[
            <UniCapabilityBatchButton
              key="purchase-requisition-print"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedRequisitionsForBatch}
              capabilityKey="print"
              permAllowed={purchaseRequisitionPerms.canPrint}
              batchAllowed={(records, perm) =>
                Boolean(perm) && records.some((record) => record.capabilities?.print?.allowed === true)
              }
              singleOnly
              onRun={async (id) => {
                openPrint({ documentType: 'purchase_requisition', documentId: id });
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
              let items = (type === 'currentPage' ? (pageData ?? []) : await fetchAllListItems((p) => listPurchaseRequisitions(p)));
              if (type === 'currentPage' && pageData?.length) {
                items = pageData;
              } else if (type === 'selected' && keys?.length) {
                items = items.filter((d: PurchaseRequisition) => d.id != null && keys.includes(d.id));
              }
              if (items.length === 0) {
                messageApi.warning(t('common.noDataToExport'));
                return;
              }
              await downloadRecordsAsXlsx(
                items as Array<Record<string, unknown>>,
                `purchase-requisitions-${todaySiteDateString()}.xlsx`,
              );
              messageApi.success(t('common.exportSuccess', { count: items.length }));
            } catch (error: any) {
              messageApi.error(error?.message || t('common.exportFailed'));
            }
          }}
        />
      </ListPageTemplate>

      <UniPullQueryModal<PullDemandComputationCandidate>
        open={pullFromComputationQuery.open}
        title={pullFromDemandComputationAction.label}
        onCancel={pullFromComputationQuery.closeModal}
        onOk={pullFromComputationQuery.handleConfirm}
        rowKey="id"
        columns={pullFromComputationColumns}
        dataSource={pullFromComputationQuery.dataSource}
        loading={pullFromComputationQuery.loading}
        confirmLoading={pullFromComputationQuery.confirmLoading}
        selectionType={pullFromComputationQuery.selectionType}
        selectedRowKeys={pullFromComputationQuery.selectedRowKeys}
        selectedRows={pullFromComputationQuery.selectedRows}
        onSelectedRowKeysChange={pullFromComputationQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromComputationQuery.isRowDisabled}
        searchDraft={pullFromComputationQuery.searchDraft}
        onSearchDraftChange={pullFromComputationQuery.setSearchDraft}
        onSearchApply={pullFromComputationQuery.handleSearchApply}
        onSearchClear={pullFromComputationQuery.handleSearchClear}
        appliedKeyword={pullFromComputationQuery.appliedKeyword}
        searchPlaceholder={t('app.kuaizhizao.purchaseRequisition.pull.searchPlaceholder')}
        filterExtra={(
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaizhizao.purchaseRequisition.pull.sourceDocPlaceholder')}
            style={{ width: 220, flexShrink: 0 }}
            value={pullSourceComputationId}
            options={pullSourceOptions}
            onChange={(value) => {
              const nextId = Number(value);
              const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
              pullSourceComputationIdRef.current = next;
              setPullSourceComputationId(next);
              pullFromComputationQuery.handleSelectedRowKeysChange([], []);
              pullFromComputationQuery.handleSearchApply(pullFromComputationQuery.appliedKeyword);
            }}
          />
        )}
        getRowLabel={(row) =>
          [row.computation_code, row.material_code].filter(Boolean).join(' ')
        }
        page={pullFromComputationQuery.page}
        pageSize={pullFromComputationQuery.pageSize}
        total={pullFromComputationQuery.total}
        onPageChange={pullFromComputationQuery.handlePageChange}
        scopeOptions={pullFromComputationQuery.scopeOptions}
        scope={pullFromComputationQuery.scope}
        onScopeChange={pullFromComputationQuery.handleScopeChange}
        okText={t('common.next')}
      />

      <UniPullQueryModal<PurchaseRequisitionSalesOrderPullLine>
        open={pullFromSalesOrderQuery.open}
        title={pullFromSalesOrderAction.label}
        onCancel={pullFromSalesOrderQuery.closeModal}
        onOk={pullFromSalesOrderQuery.handleConfirm}
        rowKey="id"
        columns={pullFromSalesOrderColumns}
        dataSource={pullFromSalesOrderQuery.dataSource}
        loading={pullFromSalesOrderQuery.loading}
        confirmLoading={pullFromSalesOrderQuery.confirmLoading}
        selectionType={pullFromSalesOrderQuery.selectionType}
        selectedRowKeys={pullFromSalesOrderQuery.selectedRowKeys}
        selectedRows={pullFromSalesOrderQuery.selectedRows}
        onSelectedRowKeysChange={pullFromSalesOrderQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromSalesOrderQuery.isRowDisabled}
        searchDraft={pullFromSalesOrderQuery.searchDraft}
        onSearchDraftChange={pullFromSalesOrderQuery.setSearchDraft}
        onSearchApply={pullFromSalesOrderQuery.handleSearchApply}
        onSearchClear={pullFromSalesOrderQuery.handleSearchClear}
        appliedKeyword={pullFromSalesOrderQuery.appliedKeyword}
        searchPlaceholder={t('app.kuaizhizao.purchaseOrder.pull.searchPlaceholder')}
        filterExtra={(
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaizhizao.purchaseRequisition.pull.salesOrderSourcePlaceholder')}
            style={{ width: 220, flexShrink: 0 }}
            value={pullSourceSalesOrderId}
            options={pullSourceSalesOrderOptions}
            onChange={(value) => {
              const nextId = Number(value);
              const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
              pullSourceSalesOrderIdRef.current = next;
              setPullSourceSalesOrderId(next);
              pullFromSalesOrderQuery.handleSearchApply(pullFromSalesOrderQuery.appliedKeyword);
            }}
          />
        )}
        getRowLabel={(row) => [row.order_code, row.material_code].filter(Boolean).join(' ')}
        page={pullFromSalesOrderQuery.page}
        pageSize={pullFromSalesOrderQuery.pageSize}
        total={pullFromSalesOrderQuery.total}
        onPageChange={pullFromSalesOrderQuery.handlePageChange}
        scopeOptions={pullFromSalesOrderQuery.scopeOptions}
        scope={pullFromSalesOrderQuery.scope}
        onScopeChange={pullFromSalesOrderQuery.handleScopeChange}
        okText={t('app.kuaizhizao.purchaseRequisition.pull.ok')}
      />

      <Modal
        title={t('app.kuaizhizao.purchaseRequisition.pull.confirmDateTitle')}
        open={pullDateConfirmOpen}
        destroyOnHidden
        width={MODAL_CONFIG.LARGE_WIDTH}
        onCancel={resetPullDateConfirmModal}
        okText={t('app.kuaizhizao.purchaseRequisition.pull.ok')}
        cancelText={t('common.cancel')}
        confirmLoading={pullDateConfirming}
        onOk={() => void handlePullDateConfirmCreate()}
        okButtonProps={{ disabled: pullDateConfirmRows.length === 0 }}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('app.kuaizhizao.purchaseRequisition.pull.dateConfirmHint')}
        />
        <Space wrap style={{ marginBottom: 12 }}>
          <span>{t('app.kuaizhizao.purchaseRequisition.pull.bulkRequiredDate')}</span>
          <DatePicker
            value={pullBulkRequiredDate}
            onChange={(value) => setPullBulkRequiredDate(value)}
          />
          <Button type="default" onClick={handlePullBulkDateApply}>
            {t('app.kuaizhizao.purchaseRequisition.pull.applyBulkDate')}
          </Button>
        </Space>
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          scroll={{ y: 360 }}
          dataSource={pullDateConfirmRows}
          columns={[
            {
              title: t('app.kuaizhizao.purchaseRequisition.pull.computationCode'),
              dataIndex: 'computation_code',
              width: 168,
              ellipsis: true,
            },
            {
              title: t('app.kuaizhizao.salesOrder.materialName'),
              dataIndex: 'material_name',
              ellipsis: true,
              render: (_: unknown, record: PullDemandComputationCandidate) => (
                <MaterialStackedCell
                  material_name={record.material_name}
                  material_code={record.material_code}
                  material_spec={record.material_spec}
                />
              ),
            },
            {
              title: t('app.kuaizhizao.salesOrder.colShippableQty'),
              dataIndex: 'remaining_quantity',
              width: 100,
              align: 'right' as const,
              render: (v: unknown) => formatQuantity(v),
            },
            {
              title: t('app.kuaizhizao.purchaseRequisition.col.requiredDate'),
              dataIndex: 'required_date',
              width: 160,
              render: (_: unknown, record: PullDemandComputationCandidate & { required_date?: string | null }) => (
                <DatePicker
                  style={{ width: '100%' }}
                  value={record.required_date ? dayjs(record.required_date) : null}
                  status={record.required_date ? undefined : 'error'}
                  onChange={(value) => {
                    const dateStr = value ? value.format('YYYY-MM-DD') : null;
                    setPullDateConfirmRows((prev) =>
                      prev.map((row) =>
                        Number(row.id) === Number(record.id)
                          ? { ...row, required_date: dateStr }
                          : row,
                      ),
                    );
                  }}
                />
              ),
            },
          ]}
        />
      </Modal>

      <Modal
        title={pushToPurchaseOrderAction.label}
        open={pushPoPreviewOpen}
        destroyOnHidden
        width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
        onCancel={resetPushPoPreviewModal}
        okText={pushToPurchaseOrderAction.label}
        cancelText={t('common.cancel')}
        confirmLoading={pushPoPreviewConfirming}
        onOk={() => void handlePushPoPreviewConfirm()}
        okButtonProps={{
          disabled:
            pushPoPreviewLoading ||
            !pushPoPreviewData ||
            !!pushPoPreviewData?.has_blocking_issues ||
            pushPoDetailItems.length === 0,
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
                  purchaseRequisitionCapabilityReasonMessage(pushPoPreviewData.blocking_reason, t) ||
                  t('app.kuaizhizao.purchaseRequisition.pushFailed')
                }
              />
            ) : null}
            {pushPoDetailItems.length > 0 && pushPoSuppliers.length > 0 ? (
              <ConvertForm
                items={pushPoDetailItems}
                unconvertedIds={(pushPoPreviewData.items || [])
                  .filter((row) => Number(row.max_push_quantity ?? 0) > 0)
                  .map((row) => Number(row.item_id))}
                maxPushByItemId={Object.fromEntries(
                  (pushPoPreviewData.items || [])
                    .filter((row) => Number(row.max_push_quantity ?? 0) > 0)
                    .map((row) => [Number(row.item_id), Number(row.max_push_quantity)]),
                )}
                suppliers={pushPoSuppliers}
                formRef={convertFormRef}
              />
            ) : null}
            {pushPoPreviewData.tip ? (
              <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                {pushPoPreviewData.tip}
              </Typography.Paragraph>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <Modal
        title={pushToInquiryAction.label}
        open={pushInquiryPreviewOpen}
        destroyOnHidden
        width={1100}
        onCancel={resetPushInquiryPreviewModal}
        okText={pushToInquiryAction.label}
        cancelText={t('common.cancel')}
        confirmLoading={pushInquiryPreviewConfirming}
        onOk={() => void handlePushInquiryPreviewConfirm()}
        okButtonProps={{
          disabled:
            pushInquiryPreviewLoading ||
            !pushInquiryPreviewData ||
            !!pushInquiryPreviewData?.has_blocking_issues,
        }}
      >
        {pushInquiryPreviewLoading ? (
          <div style={{ minHeight: 120, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
            <Spin />
            <div style={{ color: 'var(--ant-color-primary)' }}>{t('app.kuaizhizao.salesOrder.loadingPreview')}</div>
          </div>
        ) : pushInquiryPreviewData ? (
          <div>
            <p style={{ marginBottom: 12, fontWeight: 500 }}>{pushInquiryPreviewData.summary}</p>
            {pushInquiryPreviewData.has_blocking_issues && pushInquiryPreviewData.blocking_reason ? (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                title={
                  purchaseRequisitionCapabilityReasonMessage(pushInquiryPreviewData.blocking_reason, t) ||
                  t('app.kuaizhizao.purchaseRequisition.inquiryCreateFailed')
                }
              />
            ) : null}
            {pushInquiryPreviewData.items?.length > 0 ? (
              <Table
                size="small"
                dataSource={pushInquiryPreviewData.items}
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
                          checked={pushInquirySelectedItemIds.includes(itemId)}
                          onChange={(checked) => {
                            setPushInquirySelectedItemIds((prev) =>
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
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.purchaseRequisition.noInquiryLines')} />
            )}
            {pushInquiryPreviewData.tip ? (
              <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                {pushInquiryPreviewData.tip}
              </Typography.Paragraph>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <PurchaseRequisitionDetailDrawer
        open={detailVisible}
        zIndex={prqDetailDrawerZIndex}
        onClose={() => {
          setDetailVisible(false);
          setCurrentReq(null);
        }}
        requisition={currentReq}
        trackingRefreshKey={prTrackingRefreshKey}
        extra={
          currentReq ? (
            <DetailDrawerActions
              items={[
                {
                  key: 'fixStatus',
                  visible: ['全部转单', 'FULL_CONVERTED'].includes(currentReq.status ?? ''),
                  render: () => (
                    <Button
                      onClick={async () => {
                        if (!currentReq?.id) return;
                        try {
                          const res = await fixPurchaseRequisitionStatus(currentReq.id);
                          setCurrentReq(res);
                          setPrTrackingRefreshKey((k) => k + 1);
                          invalidateMenuBadgeCounts();
    actionRef.current?.reload();
                          messageApi.success(t('app.kuaizhizao.purchaseRequisition.statusFixed'));
                        } catch (e: unknown) {
                          const err = e as { response?: { data?: { detail?: string } } };
                          messageApi.error(err?.response?.data?.detail || t('app.kuaizhizao.purchaseRequisition.fixFailed'));
                        }
                      }}
                    >
                      {t('app.kuaizhizao.purchaseRequisition.fixStatus')}
                    </Button>
                  ),
                },
                {
                  key: 'edit',
                  visible:
                    currentReq.capabilities?.update?.allowed === true && purchaseRequisitionPerms.canUpdate,
                  render: () => (
                    <Button
                      {...rowActionKind('update')}
                      icon={<EditOutlined />}
                      onClick={() => {
                        const r = currentReq;
                        setDetailVisible(false);
                        if (r) void handleEdit(r);
                      }}
                    >
                      {t('common.edit')}
                    </Button>
                  ),
                },
                {
                  key: 'delete',
                  visible:
                    currentReq.capabilities?.delete?.allowed === true && purchaseRequisitionPerms.canDelete,
                  render: () => (
                    <Button
                      {...rowActionKind('delete')}
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => handleDeleteOne(currentReq)}
                    >
                      {t('common.delete')}
                    </Button>
                  ),
                },
                {
                  key: 'print',
                  visible: currentReq.id != null && purchaseRequisitionPerms.canPrint,
                  render: () => (
                    <Button
                      icon={<PrinterOutlined />}
                      onClick={() =>
                        openPrint({ documentType: 'purchase_requisition', documentId: currentReq.id! })
                      }
                    >
                      {t('components.uniAction.print')}
                    </Button>
                  ),
                },
                {
                  key: 'workflow',
                  render: () => (
                    <UniWorkflowActions
                      {...rowActionKind('skip')}
                      record={currentReq}
                      entityName={t('app.kuaizhizao.purchaseRequisition.entityName')}
                      {...PURCHASE_REQUISITION_WORKFLOW_PROPS}
                      theme="default"
                      confirmMessages={{ revoke: t('app.kuaizhizao.purchaseRequisition.workflowRevokeConfirm') }}
                      onSuccess={async () => {
                        invalidateMenuBadgeCounts();
    actionRef.current?.reload();
                        setPrTrackingRefreshKey((k) => k + 1);
                        if (currentReq?.id) {
                          try {
                            setCurrentReq(await getPurchaseRequisition(currentReq.id));
                          } catch (e: unknown) {
                            const err = e as { message?: string };
                            messageApi.error(err?.message || t('app.kuaizhizao.purchaseRequisition.detailFailed'));
                          }
                        }
                      }}
                    />
                  ),
                },
              ]}
            />
          ) : null
        }
      />
      <UniMaterialBatchPicker
        open={materialPickerOpen}
        sourceType={materialPickSourceType}
        onCancel={() => setMaterialPickerOpen(false)}
        onConfirm={appendRequisitionItemsFromMaterials}
      />
      {PrintModal}
    </>
  );
};

const ConvertForm: React.FC<{
  items: PurchaseRequisitionItem[];
  unconvertedIds: number[];
  maxPushByItemId: Record<number, number>;
  suppliers: Array<{ id: number; code?: string; name: string }>;
  formRef: React.MutableRefObject<{
    selectedIds: number[];
    supplierId: number;
    supplierName: string;
    itemQuantities: Record<number, number>;
    itemUnitPrices: Record<number, number>;
    itemSuppliers: Record<number, number>;
    persistDefaultSupplier: boolean;
  }>;
}> = ({ items, unconvertedIds, maxPushByItemId, suppliers, formRef }) => {
  const { t } = useTranslation();
  const { quantity: quantityDecimals, price: priceDecimals, amount: amountDecimals } = useNumericPrecision();
  const fallbackSupplierId = suppliers[0]?.id || 0;
  const [selected, setSelected] = useState<number[]>(unconvertedIds);
  const isPushableItem = (item: PurchaseRequisitionItem) =>
    item.id != null && unconvertedIds.includes(item.id);
  const [batchSupplierId, setBatchSupplierId] = useState<number>(() => {
    const first = items.find(isPushableItem);
    return first?.supplier_id || fallbackSupplierId;
  });
  const [rowSuppliers, setRowSuppliers] = useState<Record<number, number>>(() => {
    const m: Record<number, number> = {};
    items.forEach((i) => {
      if (i.id == null || !unconvertedIds.includes(i.id)) return;
      m[i.id] = i.supplier_id || fallbackSupplierId;
    });
    return m;
  });
  const [quantities, setQuantities] = useState<Record<number, number>>(() => {
    const q: Record<number, number> = {};
    items.filter(isPushableItem).forEach((i) => {
      if (i.id != null) q[i.id] = maxPushByItemId[i.id];
    });
    return q;
  });
  const [unitPrices, setUnitPrices] = useState<Record<number, number>>(() => {
    const p: Record<number, number> = {};
    items.filter(isPushableItem).forEach((i) => {
      if (i.id != null) p[i.id] = Number(i.suggested_unit_price ?? 0);
    });
    return p;
  });
  const [persistDefault, setPersistDefault] = useState(false);
  const hasSuppliers = suppliers && suppliers.length > 0;

  const formatLineAmount = (itemId: number) => {
    const qty = quantities[itemId] ?? 0;
    const price = unitPrices[itemId] ?? 0;
    return computeSimpleDocumentLineTotal(qty, price).toLocaleString('zh-CN', {
      minimumFractionDigits: amountDecimals,
      maximumFractionDigits: amountDecimals,
    });
  };

  const applyBatchToSelected = () => {
    const selectedSet = new Set(selected);
    setRowSuppliers((prev) => {
      const next = { ...prev };
      items.forEach((i) => {
        if (i.id == null || !selectedSet.has(i.id) || !unconvertedIds.includes(i.id)) return;
        next[i.id] = batchSupplierId;
      });
      return next;
    });
  };

  const hasBatchTargetRows = selected.some((id) => {
    const i = items.find((x) => x.id === id);
    return i != null && i.id != null && unconvertedIds.includes(i.id);
  });

  useEffect(() => {
    formRef.current.selectedIds = selected;
    formRef.current.itemQuantities = quantities;
    formRef.current.itemUnitPrices = unitPrices;
    formRef.current.itemSuppliers = rowSuppliers;
    formRef.current.persistDefaultSupplier = persistDefault;
    const firstSelectedId = selected[0];
    const head = firstSelectedId ? rowSuppliers[firstSelectedId] : batchSupplierId;
    const currentSupplierId = (head || batchSupplierId || 0) as number;
    formRef.current.supplierId = currentSupplierId;
    formRef.current.supplierName = suppliers.find((x) => x.id === currentSupplierId)?.name || '';
  }, [selected, quantities, unitPrices, rowSuppliers, persistDefault, batchSupplierId, suppliers, formRef]);

  return (
    <div style={{ margin: 0 }}>
      {hasSuppliers && (
        <div style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span style={{ color: '#666', whiteSpace: 'nowrap' }}>{t('app.kuaizhizao.purchaseRequisition.convert.batchSupplier')}</span>
          <SupplierSelectDropdown
            hostResource={KUAIZHIZAO_DOC_HOST.purchaseRequisition}
            suppliers={suppliers as Supplier[]}
            autoLoad={false}
            style={{ minWidth: 220, flex: 1 }}
            placeholder={t('app.kuaizhizao.purchaseRequisition.convert.batchPlaceholder')}
            value={batchSupplierId || undefined}
            onChange={(v) => setBatchSupplierId(Number(v) || 0)}
          />
          <Button type="default" onClick={applyBatchToSelected} disabled={!hasBatchTargetRows}>
            {t('app.kuaizhizao.purchaseRequisition.convert.applyToSelected')}
          </Button>
        </div>
      )}
      {!hasSuppliers && (
        <p style={{ color: 'var(--ant-color-warning)', margin: '0 0 12px 0' }}>{t('app.kuaizhizao.purchaseRequisition.convert.noSuppliers')}</p>
      )}
      <div style={{ marginBottom: 12 }}>
        <Checkbox checked={persistDefault} onChange={(e) => setPersistDefault(e.target.checked)}>
          {t('app.kuaizhizao.purchaseRequisition.convert.persistSupplier')}
        </Checkbox>
      </div>
      <Table
        size="small"
        rowSelection={{
          selectedRowKeys: selected,
          onChange: (keys) => setSelected(keys as number[]),
          getCheckboxProps: (record: PurchaseRequisitionItem) => ({
            disabled: record.id == null || !unconvertedIds.includes(record.id),
          }),
        }}
        columns={[
          {
            title: t('app.kuaizhizao.purchaseRequisition.convert.col.material'),
            key: 'material',
            width: 200,
            render: (_: unknown, record: PurchaseRequisitionItem) => (
              <UniTableStackedPrimaryCell
                primary={record.material_name || '-'}
                secondary={record.material_code || '-'}
                secondaryCopyable={Boolean(record.material_code)}
              />
            ),
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.convert.col.supplier'),
            width: 380,
            render: (_: unknown, record: PurchaseRequisitionItem) =>
              record.id != null && unconvertedIds.includes(record.id) ? (
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 8,
                    flexWrap: 'nowrap',
                    minWidth: 0,
                  }}
                >
                  <SupplierSelectDropdown
                    hostResource={KUAIZHIZAO_DOC_HOST.purchaseRequisition}
                    suppliers={suppliers as Supplier[]}
                    autoLoad={false}
                    style={{ flex: '1 1 auto', minWidth: 0 }}
                    placeholder={t('app.kuaizhizao.purchaseRequisition.convert.selectSupplier')}
                    value={rowSuppliers[record.id] || undefined}
                    onChange={(v) =>
                      setRowSuppliers((prev) => ({ ...prev, [record.id!]: Number(v) || 0 }))
                    }
                  />
                </div>
              ) : (
                '-'
              ),
          },
          { title: t('app.kuaizhizao.purchaseRequisition.convert.col.demandQty'), dataIndex: 'quantity', width: 88, align: 'right', render: (v: any) => formatQuantity(v) },
          {
            title: t('app.kuaizhizao.purchaseRequisition.convert.col.pushedQty'),
            width: 120,
            align: 'right',
            render: (_: unknown, record: PurchaseRequisitionItem) => {
              const draft = Number(record.converted_quantity_draft ?? 0);
              const confirmed = Number(record.converted_quantity_confirmed ?? 0);
              if (draft === 0 && confirmed === 0) return 0;
              const parts: string[] = [];
              if (draft > 0) parts.push(t('app.kuaizhizao.purchaseRequisition.convert.draftQty', { qty: draft }));
              if (confirmed > 0) parts.push(t('app.kuaizhizao.purchaseRequisition.convert.confirmedQty', { qty: confirmed }));
              return parts.join(' / ');
            },
          },
          { title: t('app.kuaizhizao.purchaseRequisition.convert.col.moq'), width: 88, align: 'right', render: () => '-' },
          {
            title: t('app.kuaizhizao.purchaseRequisition.convert.col.thisPushQty'),
            width: 120,
            align: 'right',
            render: (_: unknown, record: PurchaseRequisitionItem) =>
              record.id != null && unconvertedIds.includes(record.id) ? (
                <InputNumber
                  min={0.01}
                  precision={quantityDecimals}
                  value={quantities[record.id] ?? Number(record.quantity ?? 0)}
                  onChange={(v) => setQuantities((prev) => ({ ...prev, [record.id!]: Number(v) || 0 }))}
                  style={{ width: 100 }}
                />
              ) : (
                '-'
              ),
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.convert.col.unitPrice'),
            width: 120,
            align: 'right',
            render: (_: unknown, record: PurchaseRequisitionItem) =>
              record.id != null && unconvertedIds.includes(record.id) ? (
                <InputNumber
                  min={0}
                  precision={priceDecimals}
                  value={unitPrices[record.id] ?? Number(record.suggested_unit_price ?? 0)}
                  onChange={(v) => setUnitPrices((prev) => ({ ...prev, [record.id!]: Number(v) || 0 }))}
                  style={{ width: 100 }}
                />
              ) : (
                '-'
              ),
          },
          {
            title: t('app.kuaizhizao.purchaseRequisition.convert.col.lineAmount'),
            width: 110,
            align: 'right',
            render: (_: unknown, record: PurchaseRequisitionItem) =>
              record.id != null && unconvertedIds.includes(record.id) ? (
                <Typography.Text>{formatLineAmount(record.id)}</Typography.Text>
              ) : (
                '-'
              ),
          },
        ]}
        dataSource={items}
        pagination={false}
        rowKey="id"
        scroll={{ x: 1280 }}
      />
    </div>
  );
};

export default PurchaseRequisitionsPage;
