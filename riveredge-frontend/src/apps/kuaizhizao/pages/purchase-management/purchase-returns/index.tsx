/**
 * 采购退货单管理页面
 *
 * 提供采购退货单的查看、确认退货与删除；列表与详情遵循 UI_Standard / riveredge-detail-drawer-ui。
 *
 * @author RiverEdge Team
 * @date 2026-01-17
 */

import React, { useRef, useState, useMemo, useEffect, useCallback, lazy, Suspense } from 'react';
import type { TFunction } from 'i18next';
import { rowActionKind, rowActionCreateRefund } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  paymentRefundService,
  PAYMENT_REFUND_RESOURCE,
} from '../../../../kuaicaiwu/services/finance/payment-refund';
import {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
  ProForm,
  ProFormText,
  ProFormDatePicker,
  ProFormTextArea,
  ProFormSelect,
  ProFormInstance,
} from '@ant-design/pro-components';
import {
  App,
  Alert,
  Button,
  Spin,
  Table,
  Typography,
  Descriptions,
  Empty,
  Dropdown,
  Space,
  Row,
  Col,
  Form as AntForm,
  InputNumber,
  Input,
  Select,
  List,
  theme,
} from 'antd';
import { ArrowLeftOutlined, EyeOutlined, CheckCircleOutlined, EditOutlined, PlusOutlined, AppstoreAddOutlined, ImportOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  PurchaseDepartmentFormField,
  resolvePurchaseDepartmentPayload,
  usePurchaseDepartmentOptions,
} from '../shared/PurchaseDepartmentFormField';
import { UniTable, readPersistedUniTableViewType, type UniTableRequestMeta} from '../../../../../components/uni-table';
import {
  UniCapabilityBatchButton,
  UniBatchMenuButton,
  pickCapability,
  runCapabilityBatchLoop,
  withDocumentSubmitCombinedItem,
  type UniBatchMenuItem,
} from '../../../../../components/uni-batch';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import {
  UniPullQueryModal,
  isPullOpenLineSelectable,
  isPullableScope,
  renderPullCapabilityTag,
  renderPullQueryDocStatus,
  toUniPullQueryHttpParams,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
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
  DetailDrawerActions,
  DetailDrawerSection,
  MODAL_CONFIG,
  DRAWER_CONFIG,
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageHeaderActions,
  DocumentFormPageLayout,
  useDetailDrawerDescriptionItems,
  type StatCard,
} from '../../../../../components/layout-templates';
import { useLeaveFormTab } from '../../../../../components/uni-tabs/navigateClosingTab';
import { useSubmitShortcut } from '../../../../../hooks/useSubmitShortcut';
const LazyUniImport = lazy(() =>
  import('../../../../../components/uni-import').then((m) => ({ default: m.UniImport })),
);
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import { buildDocumentLineDualQuantityFormColumns } from '../../../../../components/quantity-with-unit';
import {
  pickDocumentLineDualQuantityFields,
  resolveDocumentLineQuantityField,
} from '../../../../../utils/materialDualQuantity';
import { useNumericPrecision } from '../../../../../hooks/useNumericPrecision';
import {
  DOCUMENT_DETAIL_COL_WIDTH,
  DOCUMENT_DETAIL_CONTROL_SIZE,
  DOCUMENT_DETAIL_NUM_COL,
  DOCUMENT_DETAIL_TABLE_PROPS,
  DOCUMENT_DETAIL_TEXT_COL,
  DocumentDetailTableStyles,
} from '../../../components/document-detail-table/documentDetailTable';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import { UniMaterialBatchPicker } from '../../../../../components/uni-material-batch-picker';
import { UniWarehouseSelect } from '../../../../../components/uni-warehouse-select';
import type { Material } from '../../../../master-data/types/material';
import {
  collectImportMaterialCodes,
  resolveMaterialsByCodesForImport,
} from '../../../../master-data/utils/materialImportResolve';
import {
  applyPurchaseDocumentLineMaterialPricing,
  getMaterialDefaultPurchasePrice,
  repriceUnlockedPurchaseDocumentLineIfNeeded,
} from '../../../../master-data/utils/resolve-partner-material-price';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import { SimpleSparkline } from '../../../../../components';
import { UniLifecycle, UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import { DocumentTrackingTimelineBody, useDocumentTracking } from '../../../../../components/document-tracking-panel';
import { WarehouseTraceBriefPrimaryActions } from '../../warehouse-management/WarehouseTraceBriefFooter';
import OutboundBatchAllocationField from '../../warehouse-management/outbound/OutboundBatchAllocationField';
import {
  coerceBatchAllocationsDraft,
  isValidOutboundBatchAllocations,
  type OutboundBatchAllocation,
} from '../../warehouse-management/outbound/outboundBatchAllocation';
import type { InventoryPickOption } from '../../warehouse-management/outbound/outboundConfirmInventoryOptions';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { buildKuaizhizaoPullCreateMenuItems, resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import { qualityApi, warehouseApi } from '../../../services/production';
import { listPurchaseOrders } from '../../../services/purchase';
import type {
  PurchaseReceiptReturnPullLine,
  PurchaseReturnPullLine,
} from '../../../services/warehouse-execution';
import type { PurchaseReturn, PurchaseReturnDetail, PurchaseReturnItem } from '../../../services/purchase-return';
import {
  approvePurchaseReturn,
  commitPurchaseReturn,
  revokePurchaseReturn,
  submitPurchaseReturnForReview,
  withdrawPurchaseReturn,
} from '../../../services/purchase-return';
import type { PurchaseReturnListParams } from '../../../services/purchase-return';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import {
  purchaseReturnBatchConfirmAllowed,
  purchaseReturnBatchWithdrawAllowed,
  purchaseReturnCapabilityReasonMessage,
} from '../../../../../hooks/useDocumentCapabilities';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { isManualAuditEnabled } from '../../../../../utils/auditMode';
import { useWarehouseLocationOptions } from '../../../hooks/useWarehouseLocationOptions';
import { lineLocationSelectionRequired } from '../../../../../components/uni-wh-dropdown';
import {
  isMaterialBatchEntryEnabled,
  useWarehouseTrackingFlags,
} from '../../warehouse-management/shared/warehouseTrackingFlags';
import { loadConfirmPreviewMaterialMeta } from '../../warehouse-management/inbound/inboundItemTracking';
import {
  runOutboundHubConfirmFromRecord,
  formatOutboundConfirmError,
} from '../../warehouse-management/outbound/outboundHubRunConfirm';
import { getDictionaryOptions } from '../../../../master-data/services/supply-chain';
import { initializeSystemDictionaries } from '../../../../../services/dataDictionary';
import {
  buildPurchaseReturnLifecycleValueEnum,
  getPurchaseReturnLifecycle,
  LIST_LIFECYCLE_STAGE_FIELD,
  resolvePurchaseReturnListApiParams,
} from '../../../utils/purchaseReturnLifecycle';
import { ListUniLifecycleCell } from '../../sales-management/shared/ListUniLifecycleCell';
import { createListAuditPhaseColumn } from '../../sales-management/shared/listAuditPhaseColumn';
import {
  buildDocumentDetailPartnerMaterialFormColumns,
  buildDocumentDetailSpecModelFormColumns,
  withMaterialLineFillMapping,
} from '../../sales-management/shared/materialLineFormDetail';
import { alignProColumns, alignDescriptionColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { LinkedDocumentCode } from '../../../../../components/linked-document-code';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import { flattenDocumentDetailRows, resolveDetailTableViewMode } from '../../shared/detailTableFlatRows';
import {
  KUAIZHIZAO_DOC_HOST,
  loadMaterialFormReferenceList,
  loadSupplierFormReferenceList,
} from '../../../../../utils/documentFormReferenceLoad';
import { extractProTableSort } from '../../../../../utils/tableQueryKey';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { useImportDictionaryOptions } from '../../../../../hooks/useImportDictionaryOptions';
import { pickImportExampleValue } from '../../../../../utils/loadImportDictionaryValues';
import { importInChunksViaPerItemCreate } from '../../../../../utils/chunkedBulkImport';
import { warehouseApi as masterWarehouseApi } from '../../../../master-data/services/warehouse';
import { useImportMaterialUnitOptions } from '../../../../master-data/hooks/useImportMaterialUnitOptions';
import {
  buildDocumentReturnListImportTemplate,
  parseDocumentReturnListImport,
} from '../../shared/documentReturnListImport';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import {
  CustomFieldsFormSection,
  CustomFieldsDetailSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import {
  DocumentAttachmentsReadonly,
  documentAttachmentsFromRecord,
  hasDocumentAttachments,
} from '../../../components/DocumentAttachmentsReadonly';
import { mapAttachmentsToUploadList, normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { formatBusinessDateOnly, formatDateTime, formatNumber, formatQuantity, formatCurrencyAmount, formatCurrencyPrice } from '../../../../../utils/format';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { isPendingReviewStatus } from '../../../constants/documentStatus';
const PURCHASE_RETURN_RESOURCE = 'kuaizhizao:purchase-return';

const PURCHASE_RETURN_LIST_PERSISTENCE_ID =
  'apps.kuaizhizao.pages.purchase-management.purchase-returns-width-v2';
const PURCHASE_RETURN_LIST_PATH = '/apps/kuaizhizao/purchase-management/purchase-returns';
const purchaseReturnEditPath = (id: number) => `${PURCHASE_RETURN_LIST_PATH}/${id}/edit`;
const PURCHASE_RETURN_REFUNDED_STATUSES = new Set(['已退货', 'completed', '已完成', 'RETURNED']);

const isPurchaseReturnRefundEligible = (record: { status?: string; id?: number }) =>
  record.id != null && PURCHASE_RETURN_REFUNDED_STATUSES.has(String(record.status || '').trim());

/** 与后端 review_status 对齐，供 UniWorkflowActions 识别 */
const PR_WORKFLOW_DRAFT_STATUSES = ['草稿', 'draft'];
const PR_WORKFLOW_PENDING_STATUSES = ['待审核', 'pending_review', 'pending_approval', 'PENDING'];
const PR_WORKFLOW_APPROVED_STATUSES = ['审核通过', '已通过', 'approved', 'APPROVED'];
const PR_WORKFLOW_REJECTED_STATUSES = ['审核驳回', '已驳回', 'rejected', 'REJECTED'];

function isPurchaseReturnRowSelectable(record: PurchaseReturn): boolean {
  if (record.capabilities?.delete?.allowed === true) return true;
  if (record.capabilities?.confirm?.allowed === true) return true;
  if (record.capabilities?.withdraw?.allowed === true) return true;
  const st = record.status ?? '';
  const rs = record.review_status ?? '';
  if (PR_WORKFLOW_DRAFT_STATUSES.includes(st)) return true;
  if (PR_WORKFLOW_PENDING_STATUSES.includes(st) || PR_WORKFLOW_PENDING_STATUSES.includes(rs)) {
    return true;
  }
  if (PR_WORKFLOW_REJECTED_STATUSES.includes(rs)) return true;
  if (String(rs).trim() === 'SUBMITTED') return true;
  return false;
}

type PurchaseReturnItemRow = PurchaseReturnItem & {
  _rowKey: string;
  return_id: number;
  return_code?: string;
  supplier_name?: string;
  purchase_receipt_code?: string;
  purchase_order_code?: string;
  warehouse_name?: string;
  return_time?: string;
  status?: string;
  review_status?: string;
  lifecycle?: Record<string, unknown>;
  capabilities?: PurchaseReturn['capabilities'];
  audit?: PurchaseReturn['audit'];
};

const PURCHASE_RETURN_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_purchase_returns';

const PR_DETAIL_ITEMS_MIN_WIDTH = 1000;

const RETURN_REASON_VALUES = [
  'QUALITY_ISSUE',
  'SPEC_MISMATCH',
  'QTY_ERROR',
  'PACKAGE_DAMAGE',
  'CUSTOMER_CANCEL',
  'OTHER',
];
const RETURN_TYPE_VALUES = ['EXCHANGE', 'REFUND', 'REWORK', 'SCRAP_RETURN', 'OTHER'];
const SHIPPING_METHOD_VALUES = ['EXPRESS', 'LOGISTICS', 'SELF_PICKUP', 'DEDICATED', 'AIR', 'SEA'];

const DICT_VALUE_TO_KEY: Record<string, string> = {
  QUALITY_ISSUE: 'qualityIssue',
  SPEC_MISMATCH: 'specMismatch',
  QTY_ERROR: 'qtyError',
  PACKAGE_DAMAGE: 'packageDamage',
  CUSTOMER_CANCEL: 'customerCancel',
  OTHER: 'other',
  EXCHANGE: 'exchange',
  REFUND: 'refund',
  REWORK: 'rework',
  SCRAP_RETURN: 'scrapReturn',
  EXPRESS: 'express',
  LOGISTICS: 'logistics',
  SELF_PICKUP: 'selfPickup',
  DEDICATED: 'dedicated',
  AIR: 'air',
  SEA: 'sea',
};

function buildDictFallbackOptions(t: TFunction, values: string[]) {
  return values.map((value) => {
    const dictKey = DICT_VALUE_TO_KEY[value] ?? value.toLowerCase();
    return {
      label: t(`app.kuaizhizao.purchaseReturn.dict.${dictKey}`),
      value,
    };
  });
}

/** 行/抽屉「确认退货」：capabilities + 业务态 + 审核相位（与后端 assert 同源）。 */
function canShowPurchaseReturnConfirm(
  record: {
    status?: string | null;
    review_status?: string | null;
    capabilities?: PurchaseReturn['capabilities'];
    audit?: PurchaseReturn['audit'];
  },
  canSubmit: boolean,
): boolean {
  if (!canSubmit) return false;
  if (record.capabilities?.confirm?.allowed !== true) return false;
  // 须审核通过：优先看 audit.phase；无 audit 时回退 review_status
  const auditPhase = String(record.audit?.phase ?? '').trim();
  if (auditPhase) {
    if (auditPhase !== 'approved') return false;
  } else {
    const review = String(record.review_status ?? '').trim();
    const approved = review === '审核通过' || review === '已通过' || review.toLowerCase() === 'approved';
    if (!approved) return false;
  }
  const status = String(record.status ?? '').trim();
  if (
    status === '已退货' ||
    status === '已取消' ||
    status === 'completed' ||
    status === 'RETURNED' ||
    status === 'cancelled' ||
    status === 'CANCELLED'
  ) {
    return false;
  }
  return true;
}

function getImportRowValue(row: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = row[key];
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      return value;
    }
  }
  return undefined;
}

type PullIncomingInspectionCandidate = {
  id: number;
  inspection_code?: string;
  purchase_receipt_code?: string;
  supplier_name?: string;
  material_name?: string;
  status?: string;
  quality_status?: string;
  unqualified_quantity?: number;
  updated_at?: string;
  capabilities?: {
    push_purchase_return?: { allowed?: boolean; reason?: string | null };
  };
};

const PurchaseReturnsPage: React.FC = () => {
  const { t, i18n } = useTranslation();
  const {
    options: departmentOptions,
    loading: departmentOptionsLoading,
    resolveName: resolveDepartmentName,
  } = usePurchaseDepartmentOptions();
  const pullFromPurchaseReceiptAction = resolveKuaizhizaoDocumentAction(
    t,
    'purchase_return.pull_from_purchase_receipt',
  );
  const pullFromPurchaseOrderAction = resolveKuaizhizaoDocumentAction(t, 'purchase_return.pull_from_purchase_order');
  const pullFromIncomingInspectionAction = resolveKuaizhizaoDocumentAction(
    t,
    'purchase_return.pull_from_incoming_inspection',
  );
  const { message: messageApi, modal: modalApi } = App.useApp();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const isCreatePage = location.pathname.endsWith('/purchase-returns/new');
  const editRouteMatch = location.pathname.match(/\/purchase-returns\/(\d+)\/edit$/);
  const editRouteId = editRouteMatch ? Number(editRouteMatch[1]) : null;
  const isEditPage = editRouteId != null && Number.isFinite(editRouteId) && editRouteId > 0;
  const isFormPage = isCreatePage || isEditPage;
  const leavePurchaseReturnFormPage = useLeaveFormTab(PURCHASE_RETURN_LIST_PATH);
  const formPageInitKeyRef = useRef<string | null>(null);
  const [formPageLoading, setFormPageLoading] = useState(false);
  const pendingCreateFormValuesRef = useRef<Record<string, unknown> | null>(null);
  const { token } = theme.useToken();
  const purchaseReturnDetailDrawerZIndex = token.zIndexPopupBase;
  const defaultUnit = t('app.kuaizhizao.purchaseReturn.defaultUnit');
  const fallbackReturnReasonOptions = useMemo(
    () => buildDictFallbackOptions(t, RETURN_REASON_VALUES),
    [t, i18n.language],
  );
  const fallbackReturnTypeOptions = useMemo(
    () => buildDictFallbackOptions(t, RETURN_TYPE_VALUES),
    [t, i18n.language],
  );
  const fallbackShippingMethodOptions = useMemo(
    () => buildDictFallbackOptions(t, SHIPPING_METHOD_VALUES),
    [t, i18n.language],
  );

  const getReturnStatusLabel = (status?: string) => {
    if (!status) return '-';
    const statusLabelMap: Record<string, string> = {
      '待退货': t('app.kuaizhizao.purchaseReturn.statusPending'),
      '已退货': t('app.kuaizhizao.purchaseReturn.statusReturned'),
      '已取消': t('app.kuaizhizao.purchaseReturn.statusCancelled'),
      '草稿': t('app.kuaizhizao.purchaseReturn.statusDraft'),
    };
    return statusLabelMap[status] ?? status;
  };

  const getReviewStatusLabel = (status?: string) => {
    if (!status) return '-';
    const reviewLabelMap: Record<string, string> = {
      '草稿': t('app.kuaizhizao.purchaseReturn.statusDraft'),
      '待审核': t('app.kuaizhizao.purchaseReturn.reviewPending'),
      '审核通过': t('app.kuaizhizao.purchaseReturn.reviewApproved'),
      '审核驳回': t('app.kuaizhizao.purchaseReturn.reviewRejected'),
    };
    return reviewLabelMap[status] ?? status;
  };

  const returnStatusMap = useMemo(
    () => ({
      待退货: { text: t('app.kuaizhizao.purchaseReturn.statusPending'), color: 'default' },
      已退货: { text: t('app.kuaizhizao.purchaseReturn.statusReturned'), color: 'success' },
      已取消: { text: t('app.kuaizhizao.purchaseReturn.statusCancelled'), color: 'error' },
      草稿: { text: t('app.kuaizhizao.purchaseReturn.statusDraft'), color: 'default' },
    }),
    [t, i18n.language],
  );
  const actionRef = useRef<ActionType>(null);
  const tableRowsRef = useRef<PurchaseReturn[]>([]);
  const [viewTypeState, setViewTypeState] = useState<'table' | 'detailTable' | 'help'>(() =>
    readPersistedUniTableViewType(PURCHASE_RETURN_LIST_PERSISTENCE_ID, 'table', [
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
  const purchaseReturnLifecycleValueEnum = useMemo(() => buildPurchaseReturnLifecycleValueEnum(t), [t]);
  const purchaseReturnAuditEnabled = useAuditRequired('purchase_return', false);
  const purchaseReturnAuditColumn = useMemo(
    () => createListAuditPhaseColumn<PurchaseReturn>({ t, auditEnabled: purchaseReturnAuditEnabled }),
    [t, purchaseReturnAuditEnabled],
  );
  const [supplierList, setSupplierList] = useState<Array<{ id: number; name?: string; code?: string }>>([]);

  useEffect(() => {
    void loadSupplierFormReferenceList(KUAIZHIZAO_DOC_HOST.purchaseReturn).then(setSupplierList);
  }, []);

  const purchaseReturnSupplierSearchOptions = useMemo(
    () =>
      supplierList.map((s) => ({
        value: Number(s.id),
        label: [s.name, s.code].filter(Boolean).join(' - ') || String(s.id),
      })),
    [supplierList],
  );

  const pullSourceOrderIdRef = useRef<number | undefined>(undefined);
  const [pullSourceOrderId, setPullSourceOrderId] = useState<number | undefined>();
  const [pullSourceOrderOptions, setPullSourceOrderOptions] = useState<Array<{ value: number; label: string }>>([]);
  const pullSourceReceiptIdRef = useRef<number | undefined>(undefined);
  const [pullSourceReceiptId, setPullSourceReceiptId] = useState<number | undefined>();
  const [pullSourceReceiptOptions, setPullSourceReceiptOptions] = useState<
    Array<{ value: number; label: string }>
  >([]);
  const [poPullLineBatch, setPoPullLineBatch] = useState<Record<number, string>>({});
  const [poPullLineBatchAllocs, setPoPullLineBatchAllocs] = useState<
    Record<number, OutboundBatchAllocation[]>
  >({});
  const [prPullLineBatch, setPrPullLineBatch] = useState<Record<number, string>>({});
  const [prPullLineQty, setPrPullLineQty] = useState<Record<number, number>>({});
  const [prPullLineWh, setPrPullLineWh] = useState<Record<number, number>>({});
  const [prPullBatchWarehouseId, setPrPullBatchWarehouseId] = useState<number | undefined>();
  const [poPullWarehouseOptions, setPoPullWarehouseOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [poPullLineWh, setPoPullLineWh] = useState<Record<number, number>>({});
  const [poPullBatchWarehouseId, setPoPullBatchWarehouseId] = useState<number | undefined>();
  const purchaseReturnPerms = useResourcePermissions(PURCHASE_RETURN_RESOURCE);
  const paymentRefundPerms = useResourcePermissions(PAYMENT_REFUND_RESOURCE);
  const payablePerms = useResourcePermissions('kuaicaiwu:payable');
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const queryClient = useQueryClient();
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  const selectedReturnsForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
        .filter((row): row is PurchaseReturn => row != null),
    [selectedRowKeys],
  );

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingDetail, setEditingDetail] = useState<PurchaseReturnDetail | null>(null);
  const [importModalVisible, setImportModalVisible] = useState(false);
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false);
  const formRef = useRef<ProFormInstance>(null);
  const commitAfterSaveRef = useRef(false);
  const { quantity: quantityDecimals } = useNumericPrecision();

  const {
    customFields: purchaseReturnFormCustomFields,
    customFieldValues: purchaseReturnFormCustomFieldValues,
    loadFieldValues: loadPurchaseReturnFormFieldValues,
    extractFormValues: extractPurchaseReturnFormValues,
    saveCustomFieldValues: savePurchaseReturnCustomFieldValues,
    resetFieldValues: resetPurchaseReturnFormFieldValues,
  } = useCustomFields({ tableName: PURCHASE_RETURN_CUSTOM_FIELD_TABLE, loadWhenOpen: true, open: isFormPage });

  const {
    customFields: purchaseReturnListCustomFields,
    generateCustomFieldColumns: generatePurchaseReturnCustomFieldColumns,
    enrichRecordsWithCustomFields: enrichPurchaseReturnRecordsWithCustomFields,
    customFieldValues: purchaseReturnDetailCustomFieldValues,
    loadFieldValuesForDetail: loadPurchaseReturnFieldValuesForDetail,
    resetDetailFieldValues: resetPurchaseReturnDetailFieldValues,
  } = useCustomFieldsForList<PurchaseReturn>({ tableName: PURCHASE_RETURN_CUSTOM_FIELD_TABLE });
  const {
    selectedWarehouseId,
    locationOptions,
    updateSelectedWarehouseId,
    resetSelectedWarehouseId,
  } = useWarehouseLocationOptions();
  const trackingFlags = useWarehouseTrackingFlags();

  const confirmPurchaseReturnWithValidation = useCallback(
    async (id: number): Promise<PurchaseReturnDetail> => {
      await runOutboundHubConfirmFromRecord({
        t,
        record: { id, outbound_type: 'purchase_return' },
        trackingFlags,
      });
      return (await warehouseApi.purchaseReturn.get(String(id))) as PurchaseReturnDetail;
    },
    [t, trackingFlags],
  );

  const [returnReasonOptions, setReturnReasonOptions] = useState(fallbackReturnReasonOptions);
  const [returnTypeOptions, setReturnTypeOptions] = useState(fallbackReturnTypeOptions);
  const [shippingMethodOptions, setShippingMethodOptions] = useState(fallbackShippingMethodOptions);
  const [dictOptionsLoading, setDictOptionsLoading] = useState(false);
  const materialUnitImport = useImportMaterialUnitOptions();
  const purchaseReturnImportDict = useImportDictionaryOptions([
    'RETURN_REASON',
    'RETURN_TYPE',
    'SHIPPING_METHOD',
  ]);
  const purchaseReturnLineUnitOptions = materialUnitImport.options;
  const purchaseReturnImportDictBag = useMemo(
    () => ({
      ...purchaseReturnImportDict,
      MATERIAL_UNIT: materialUnitImport.options,
      parseDict: (code: string, raw?: string | null) =>
        code === 'MATERIAL_UNIT'
          ? materialUnitImport.parse(raw)
          : purchaseReturnImportDict.parseDict(code, raw),
    }),
    [purchaseReturnImportDict, materialUnitImport.options, materialUnitImport.parse],
  );
  const purchaseReturnLineImportColumnOptions = useMemo(
    () => [
      undefined,
      purchaseReturnLineUnitOptions,
      undefined,
      undefined,
      undefined,
      undefined,
      undefined,
    ],
    [purchaseReturnLineUnitOptions],
  );
  const purchaseReturnListImportTemplate = useMemo(
    () =>
      buildDocumentReturnListImportTemplate(t, purchaseReturnImportDictBag, {
        partnerField: 'supplier',
        codeLabelKey: 'app.kuaizhizao.purchaseReturn.colReturnCode',
        partnerLabelKey: 'app.kuaizhizao.purchaseReturn.supplier',
        partnerAliases: ['供应商', '供应商名称'],
        materialLabelKey: 'app.kuaizhizao.purchaseReturn.import.materialCode',
        unitLabelKey: 'common.unit',
        qtyLabelKey: 'app.kuaizhizao.purchaseReturn.import.returnQuantity',
        unitPriceLabelKey: 'app.kuaizhizao.purchaseReturn.import.unitPrice',
        batchLabelKey: 'app.kuaizhizao.purchaseReturn.import.batchNumber',
        locationLabelKey: 'app.kuaizhizao.purchaseReturn.import.location',
        notesLabelKey: 'common.remark',
        defaultUnit: t('app.kuaizhizao.purchaseReturn.defaultUnit'),
        examplePartner: t('app.kuaizhizao.purchaseReturn.listImport.exampleSupplier'),
        exampleMaterial: 'MAT001',
        exampleWarehouse: t('app.kuaizhizao.purchaseReturn.listImport.exampleWarehouse'),
      }),
    [t, i18n.language, purchaseReturnImportDictBag],
  );

  const invalidatePurchaseReturnStatistics = () => {
    queryClient.invalidateQueries({ queryKey: ['purchaseReturnStatistics'] });
  };

  const purchaseReturnToolbarAuditMenus = useMemo(() => {
    const reload = () => {
      setSelectedRowKeys([]);
      queryClient.invalidateQueries({ queryKey: ['purchaseReturnStatistics'] });
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    };
    const reviewOf = (row: PurchaseReturn) => String(row.review_status || '').trim();
    const allowed = (row: PurchaseReturn, key: string) => pickCapability(row, key)?.allowed === true;
    const run = (
      keys: React.Key[],
      records: PurchaseReturn[],
      capabilityKey: string,
      permAllowed: boolean,
      onRun: (id: number) => Promise<unknown>,
      notAllowedMessage?: string,
    ) =>
      runCapabilityBatchLoop({
        keys,
        records,
        capabilityKey,
        permAllowed,
        notAllowedMessage,
        onRun,
        onSuccess: reload,
        message: messageApi,
        t,
      });
    const submitRows = selectedReturnsForBatch.filter((row) => allowed(row, 'submit'));
    const committedRows = selectedReturnsForBatch.filter(
      (row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'withdraw_submit'),
    );
    const pendingRows = selectedReturnsForBatch.filter((row) => {
      const review = reviewOf(row);
      return review !== 'SUBMITTED' && isPendingReviewStatus(review) && allowed(row, 'withdraw_submit');
    });
    const reviewRows = selectedReturnsForBatch.filter((row) => allowed(row, 'submit_review'));
    const approveRows = selectedReturnsForBatch.filter(
      (row) => reviewOf(row) !== 'SUBMITTED' && isPendingReviewStatus(reviewOf(row)) && allowed(row, 'approve'),
    );
    const revokeRows = selectedReturnsForBatch.filter((row) => allowed(row, 'revoke_approval'));
    const canSubmit = purchaseReturnPerms.canAction?.('submit') ?? false;
    const canApprove = purchaseReturnPerms.canAction?.('approve') ?? false;
    const canRevoke = purchaseReturnPerms.canAction?.('revoke') ?? false;
    const none = selectedReturnsForBatch.length > 0;
    const submitDisabled = none && !(canSubmit && submitRows.length > 0);
    const submitItems: UniBatchMenuItem[] = withDocumentSubmitCombinedItem(
      [
        {
          key: 'submit',
          label: t('common.submit'),
          disabled: submitDisabled,
          onClick: (keys) => run(keys, submitRows, 'submit', canSubmit, (id) => commitPurchaseReturn(id)),
        },
        {
          key: 'withdraw-submit',
          label: t('app.kuaizhizao.purchaseReturn.toolbar.withdrawSubmit'),
          disabled: none && committedRows.length === 0,
          onClick: (keys) =>
            run(keys, committedRows, 'withdraw_submit', canSubmit, (id) => withdrawPurchaseReturn(id)),
        },
        {
          key: 'submit-review',
          label: t('app.kuaizhizao.purchaseReturn.toolbar.submitReview'),
          disabled: none && !(canSubmit && reviewRows.length > 0),
          onClick: (keys) =>
            run(
              keys,
              reviewRows,
              'submit_review',
              canSubmit,
              (id) => submitPurchaseReturnForReview(id),
              t('app.kuaizhizao.purchaseReturn.toolbar.submitReviewNotAllowed'),
            ),
        },
      ],
      {
        t,
        message: messageApi,
        disabled: submitDisabled,
        commitRecords: submitRows,
        permAllowed: canSubmit,
        commit: (id) => commitPurchaseReturn(id),
        submitReview: (id) => submitPurchaseReturnForReview(id),
        onSuccess: reload,
      },
    );
    const auditItems: UniBatchMenuItem[] = [
      {
        key: 'approve',
        label: t('common.audit'),
        disabled: none && !(canApprove && approveRows.length > 0),
        onClick: (keys) => run(keys, approveRows, 'approve', canApprove, (id) => approvePurchaseReturn(id)),
      },
      {
        key: 'withdraw-review',
        label: t('app.kuaizhizao.purchaseReturn.toolbar.withdrawReview'),
        disabled: none && pendingRows.length === 0,
        onClick: (keys) =>
          run(keys, pendingRows, 'withdraw_submit', canSubmit, (id) => withdrawPurchaseReturn(id)),
      },
      {
        key: 'revoke',
        label: t('app.kuaizhizao.purchaseReturn.toolbar.revoke'),
        disabled: none && !(canRevoke && revokeRows.length > 0),
        onClick: (keys) =>
          run(keys, revokeRows, 'revoke_approval', canRevoke, (id) => revokePurchaseReturn(id)),
      },
    ];
    return { submitItems, auditItems };
  }, [
    invalidateMenuBadgeCounts,
    messageApi,
    purchaseReturnPerms,
    queryClient,
    selectedReturnsForBatch,
    t,
  ]);

  const { data: prStats } = useQuery({
    queryKey: ['purchaseReturnStatistics'],
    queryFn: () => warehouseApi.purchaseReturn.statistics(),
  });

  useEffect(() => {
    if (!isFormPage) return;
    let cancelled = false;
    (async () => {
      setDictOptionsLoading(true);
      const loadAll = async () => {
        const [reason, rtype, ship] = await Promise.all([
          getDictionaryOptions('RETURN_REASON'),
          getDictionaryOptions('RETURN_TYPE'),
          getDictionaryOptions('SHIPPING_METHOD'),
        ]);
        return { reason, rtype, ship };
      };
      try {
        let { reason, rtype, ship } = await loadAll();
        if (!cancelled && (reason.length === 0 || rtype.length === 0 || ship.length === 0)) {
          try {
            await initializeSystemDictionaries();
            if (!cancelled) ({ reason, rtype, ship } = await loadAll());
          } catch (e) {
            console.warn('initializeSystemDictionaries failed:', e);
          }
        }
        if (!cancelled) {
          setReturnReasonOptions(reason.length ? reason : fallbackReturnReasonOptions);
          setReturnTypeOptions(rtype.length ? rtype : fallbackReturnTypeOptions);
          setShippingMethodOptions(ship.length ? ship : fallbackShippingMethodOptions);
        }
      } finally {
        if (!cancelled) setDictOptionsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isFormPage, fallbackReturnReasonOptions, fallbackReturnTypeOptions, fallbackShippingMethodOptions]);

  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [returnDetail, setReturnDetail] = useState<PurchaseReturnDetail | null>(null);
  const purchaseReturnLifecycle = useMemo(
    () => (returnDetail ? getPurchaseReturnLifecycle(returnDetail, t) : null),
    [returnDetail, t],
  );
  const [prRetTrackingRefreshKey, setPrRetTrackingRefreshKey] = useState(0);
  const purchaseReturnTracking = useDocumentTracking(
    detailDrawerVisible && returnDetail?.id ? 'purchase_return' : undefined,
    returnDetail?.id,
    prRetTrackingRefreshKey,
  );

  const handlePurchaseReturnAuditSuccess = async () => {
    invalidateMenuBadgeCounts();
    actionRef.current?.reload();
    if (returnDetail?.id != null) {
      try {
        const updated = await warehouseApi.purchaseReturn.get(String(returnDetail.id));
        setReturnDetail(updated as PurchaseReturnDetail);
        setPrRetTrackingRefreshKey((k) => k + 1);
      } catch {
        /* 详情刷新失败不影响列表 */
      }
    }
  };

  const handleDetail = async (record: PurchaseReturn) => {
    try {
      const detail = await warehouseApi.purchaseReturn.get(record.id!.toString());
      setReturnDetail(detail as PurchaseReturnDetail);
      setDetailDrawerVisible(true);
      setPrRetTrackingRefreshKey((k) => k + 1);
      if (record.id != null) {
        await loadPurchaseReturnFieldValuesForDetail(record.id);
      }
    } catch {
      messageApi.error(t('app.kuaizhizao.purchaseReturn.detailFailed'));
    }
  };

  const executeConfirm = async (record: PurchaseReturn) => {
    if (record.id == null) return;
    try {
          const confirmed = await confirmPurchaseReturnWithValidation(record.id);
          messageApi.success(t('app.kuaizhizao.purchaseReturn.confirmSuccess'));
          const outcome = confirmed?.finance_outcome;
          if (outcome?.needs_payment_refund && outcome.refund_remainder > 0) {
            messageApi.warning(
              t('app.kuaizhizao.purchaseReturn.financeOutcome.confirmRefundHint', {
                amount: outcome.refund_remainder,
              }),
              8,
            );
          } else if (outcome?.no_blue_payable) {
            messageApi.warning(t('app.kuaizhizao.purchaseReturn.financeOutcome.noBluePayableHint'), 8);
          }
          invalidatePurchaseReturnStatistics();
          if (returnDetail?.id === record.id) {
            const fresh = await warehouseApi.purchaseReturn.get(String(record.id));
            setReturnDetail(fresh as PurchaseReturnDetail);
            setPrRetTrackingRefreshKey((k) => k + 1);
          }
          invalidateMenuBadgeCounts();
    actionRef.current?.reload();
        } catch (error: unknown) {
          messageApi.error(
            formatOutboundConfirmError(error, t) ||
              getApiErrorMessage(error, t('app.kuaizhizao.purchaseReturn.confirmFailed')),
          );
          throw error;
        }
  };

  // 处理新增
  const handleCreate = () => {
    pendingCreateFormValuesRef.current = null;
    navigate(`${PURCHASE_RETURN_LIST_PATH}/new`);
  };
  useNewShortcut(handleCreate);
  const createButtonLabel = t('app.kuaizhizao.purchaseReturn.create');

  const pullDocumentScopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );


  const pullFromPurchaseOrderQuery = useUniPullQuery<PurchaseReturnPullLine>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullDocumentScopeOptions,
    defaultScope: 'pullable',
    onOpen: () => {
      pullSourceOrderIdRef.current = undefined;
      setPullSourceOrderId(undefined);
      setPoPullLineBatch({});
      setPoPullLineWh({});
      setPoPullBatchWarehouseId(undefined);
      void listPurchaseOrders({ skip: 0, limit: 100 })
        .then((res) => {
          setPullSourceOrderOptions(
            (res?.data ?? [])
              .filter((row) => row.id != null && row.order_code)
              .map((row) => ({ value: row.id!, label: String(row.order_code) })),
          );
        })
        .catch((error: unknown) => {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseReturn.pull.loadSourceFailed')));
          setPullSourceOrderOptions([]);
        });
      void masterWarehouseApi
        .list({ is_active: true, limit: 500 })
        .then((whRes) => {
          const whList = Array.isArray(whRes) ? whRes : (whRes as { items?: unknown[] })?.items ?? [];
          setPoPullWarehouseOptions(
            (Array.isArray(whList) ? whList : []).map((w) => {
              const row = w as { id: number; code?: string; name?: string };
              const label = `${row.code || ''} ${row.name || ''}`.trim() || String(row.id);
              return { label, value: row.id };
            }),
          );
        })
        .catch((error: unknown) => {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseReturn.pull.loadWarehouseFailed')));
          setPoPullWarehouseOptions([]);
        });
    },
    loadData: async (params) => {
      const { scope } = params;
      try {
        const listRes = await warehouseApi.purchaseReturn.listPurchaseOrderPullLines({
          ...toUniPullQueryHttpParams(params),
          order_id: pullSourceOrderIdRef.current,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.listFailed')));
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullOpenLineSelectable(record),
    onConfirm: async (_keys, rows) => {
      const selectedRows = rows.filter((row) => isPullOpenLineSelectable(row));
      const selectedIds = selectedRows.map((row) => Number(row.id)).filter((id) => id > 0);
      if (!selectedIds.length) {
        messageApi.warning(t('app.kuaizhizao.purchaseReturn.pull.selectLinesFirst'));
        return;
      }
      const lineBatches: Record<number, string> = {};
      const lineWarehouses: Record<number, number> = {};
      const lineLocationCodes: Record<number, string> = {};
      for (const row of selectedRows) {
        const id = Number(row.id);
        if (!(id > 0)) continue;
        const remQty = Number(row.remaining_quantity ?? row.suggested_quantity ?? 0);
        const pickOptions: InventoryPickOption[] = (row.available_batches || [])
          .map((b) => {
            const bn = String(b.batch_number || '').trim();
            if (!bn) return null;
            return {
              value: bn,
              label: bn,
              quantity: Number(b.receipt_quantity ?? 0) || undefined,
            } as InventoryPickOption;
          })
          .filter((x): x is InventoryPickOption => x != null);
        const allocs =
          poPullLineBatchAllocs[id] ??
          coerceBatchAllocationsDraft(
            poPullLineBatch[id] || row.suggested_batch_number,
            remQty,
          ) ??
          [];
        if (row.requires_batch_number || pickOptions.length > 0) {
          if (!isValidOutboundBatchAllocations(allocs, pickOptions, remQty) || allocs.length !== 1) {
            messageApi.error(
              t('app.kuaizhizao.purchaseReturn.pull.batchRequired', {
                material: row.material_name || row.material_code || '-',
              }),
            );
            return;
          }
        }
        const batch = allocs.length === 1 ? allocs[0].batchNo : undefined;
        if (batch) lineBatches[id] = batch;
        const wh =
          poPullLineWh[id] ??
          (row.warehouse_id != null && Number(row.warehouse_id) > 0
            ? Number(row.warehouse_id)
            : undefined);
        if (wh == null || !(wh > 0)) {
          messageApi.error(
            t('app.kuaizhizao.purchaseReturn.pull.selectWarehouseForMaterial', {
              material: row.material_code || row.material_name || '-',
            }),
          );
          return;
        }
        lineWarehouses[id] = wh;
        const batchRow = row.available_batches?.find((b) => b.batch_number === batch);
        const locCode = String(batchRow?.location_code ?? '').trim() || undefined;
        const locId =
          batchRow?.location_id != null && Number(batchRow.location_id) > 0
            ? Number(batchRow.location_id)
            : undefined;
        const needLoc = await lineLocationSelectionRequired(wh, locId, locCode);
        if (needLoc) {
          messageApi.error(
            t('app.kuaizhizao.warehouseOutbound.msg.selectLocationForMaterial', {
              material: row.material_code || row.material_name || '-',
            }),
          );
          return;
        }
        if (locCode) lineLocationCodes[id] = locCode;
      }
      try {
        const res = await warehouseApi.purchaseReturn.pullFromPurchaseOrderItems(selectedIds, {
          lineBatches,
          lineWarehouses,
          lineLocationCodes:
            Object.keys(lineLocationCodes).length > 0 ? lineLocationCodes : undefined,
        });
        messageApi.success(
          res.message ||
            t('app.kuaizhizao.shipmentNotice.createFromSourceSuccess', {
              source: pullFromPurchaseOrderAction.sourceLabel,
              target: pullFromPurchaseOrderAction.targetLabel,
            }),
        );
        pullFromPurchaseOrderQuery.closeModal();
        setPoPullLineBatch({});
        setPoPullLineBatchAllocs({});
        setPoPullLineWh({});
        setPoPullBatchWarehouseId(undefined);
        invalidatePurchaseReturnStatistics();
        invalidateMenuBadgeCounts();
        actionRef.current?.reload();
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(
            error,
            t('app.kuaizhizao.shipmentNotice.createFromSourceFailed', {
              source: pullFromPurchaseOrderAction.sourceLabel,
              target: pullFromPurchaseOrderAction.targetLabel,
            }),
          ),
        );
      }
    },
  });

  useEffect(() => {
    if (!pullFromPurchaseOrderQuery.open) return;
    const rows = pullFromPurchaseOrderQuery.dataSource;
    if (!rows.length) return;
    setPoPullLineWh((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const row of rows) {
        const id = Number(row.id);
        if (!(id > 0) || next[id] != null) continue;
        const suggested = Number(row.warehouse_id);
        if (Number.isFinite(suggested) && suggested > 0) {
          next[id] = suggested;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [pullFromPurchaseOrderQuery.open, pullFromPurchaseOrderQuery.dataSource]);

  const applyPoPullBatchWarehouse = useCallback(
    (warehouseId: number) => {
      setPoPullBatchWarehouseId(warehouseId);
      const targetIds =
        pullFromPurchaseOrderQuery.selectedRowKeys.length > 0
          ? pullFromPurchaseOrderQuery.selectedRowKeys.map((k) => Number(k)).filter((id) => id > 0)
          : pullFromPurchaseOrderQuery.dataSource.map((row) => Number(row.id)).filter((id) => id > 0);
      if (!targetIds.length) {
        messageApi.warning(t('app.kuaizhizao.purchaseReturn.pull.batchWarehouseNoLines'));
        return;
      }
      setPoPullLineWh((prev) => {
        const next = { ...prev };
        for (const id of targetIds) next[id] = warehouseId;
        return next;
      });
      messageApi.success(
        t('app.kuaizhizao.purchaseReturn.pull.batchWarehouseApplied', { count: targetIds.length }),
      );
    },
    [
      messageApi,
      pullFromPurchaseOrderQuery.dataSource,
      pullFromPurchaseOrderQuery.selectedRowKeys,
      t,
    ],
  );

  useEffect(() => {
    if (!pullFromPurchaseOrderQuery.open) return;
    const rows = pullFromPurchaseOrderQuery.dataSource;
    if (!rows.length) return;
    setPoPullLineBatch((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const row of rows) {
        const id = Number(row.id);
        if (!(id > 0) || next[id]) continue;
        const suggested = String(row.suggested_batch_number || '').trim();
        if (suggested) {
          next[id] = suggested;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
    setPoPullLineBatchAllocs((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const row of rows) {
        const id = Number(row.id);
        if (!(id > 0) || (next[id] && next[id].length)) continue;
        const suggested = String(row.suggested_batch_number || '').trim();
        if (!suggested) continue;
        const remQty = Number(row.remaining_quantity ?? row.suggested_quantity ?? 0);
        next[id] = [{ batchNo: suggested, quantity: remQty > 0 ? remQty : 0 }];
        changed = true;
      }
      return changed ? next : prev;
    });
  }, [pullFromPurchaseOrderQuery.open, pullFromPurchaseOrderQuery.dataSource]);

  const pullFromPurchaseReceiptQuery = useUniPullQuery<PurchaseReceiptReturnPullLine>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullDocumentScopeOptions,
    defaultScope: 'pullable',
    onOpen: () => {
      void warehouseApi.purchaseReceipt
        .list({ skip: 0, limit: 100, status: '已入库' })
        .then((res) => {
          const list = Array.isArray(res) ? res : (res as { data?: unknown[] })?.data ?? [];
          setPullSourceReceiptOptions(
            (Array.isArray(list) ? list : [])
              .filter((row: { id?: number; receipt_code?: string }) => row.id != null && row.receipt_code)
              .map((row: { id: number; receipt_code: string }) => ({
                value: row.id,
                label: String(row.receipt_code),
              })),
          );
        })
        .catch((error: unknown) => {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseReturn.pull.loadSourceFailed')));
          setPullSourceReceiptOptions([]);
        });
      void masterWarehouseApi
        .list({ is_active: true, limit: 500 })
        .then((whRes) => {
          const whList = Array.isArray(whRes) ? whRes : (whRes as { items?: unknown[] })?.items ?? [];
          setPoPullWarehouseOptions(
            (Array.isArray(whList) ? whList : []).map((w) => {
              const row = w as { id: number; code?: string; name?: string };
              const label = `${row.code || ''} ${row.name || ''}`.trim() || String(row.id);
              return { label, value: row.id };
            }),
          );
        })
        .catch((error: unknown) => {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseReturn.pull.loadWarehouseFailed')));
          setPoPullWarehouseOptions([]);
        });
    },
    loadData: async (params) => {
      const { scope } = params;
      try {
        const listRes = await warehouseApi.purchaseReturn.listPurchaseReceiptPullLines({
          ...toUniPullQueryHttpParams(params),
          purchase_receipt_id: pullSourceReceiptIdRef.current,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.listFailed')));
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullOpenLineSelectable(record),
    onConfirm: async (_keys, rows) => {
      const selectedRows = rows.filter((row) => isPullOpenLineSelectable(row));
      const selectedIds = selectedRows.map((row) => Number(row.id)).filter((id) => id > 0);
      if (!selectedIds.length) {
        messageApi.warning(t('app.kuaizhizao.purchaseReturn.pull.selectLinesFirst'));
        return;
      }
      const lineBatches: Record<number, string> = {};
      const lineWarehouses: Record<number, number> = {};
      const lineQuantities: Record<number, number> = {};
      const lineLocationCodes: Record<number, string> = {};
      for (const row of selectedRows) {
        const id = Number(row.id);
        if (!(id > 0)) continue;
        const batch =
          String(prPullLineBatch[id] || row.suggested_batch_number || '').trim() || undefined;
        if (row.requires_batch_number && !batch) {
          messageApi.error(
            t('app.kuaizhizao.purchaseReturn.pull.batchRequired', {
              material: row.material_name || row.material_code || '-',
            }),
          );
          return;
        }
        if (batch) lineBatches[id] = batch;
        const wh =
          prPullLineWh[id] ??
          (row.warehouse_id != null && Number(row.warehouse_id) > 0
            ? Number(row.warehouse_id)
            : undefined);
        if (wh == null || !(wh > 0)) {
          messageApi.error(
            t('app.kuaizhizao.purchaseReturn.pull.selectWarehouseForMaterial', {
              material: row.material_code || row.material_name || '-',
            }),
          );
          return;
        }
        lineWarehouses[id] = wh;
        const locCode = String(row.suggested_location_code ?? '').trim() || undefined;
        const locId =
          row.location_id != null && Number(row.location_id) > 0 ? Number(row.location_id) : undefined;
        const needLoc = await lineLocationSelectionRequired(wh, locId, locCode);
        if (needLoc) {
          messageApi.error(
            t('app.kuaizhizao.warehouseOutbound.msg.selectLocationForMaterial', {
              material: row.material_code || row.material_name || '-',
            }),
          );
          return;
        }
        if (locCode) lineLocationCodes[id] = locCode;
        const maxQty = Number(row.remaining_quantity ?? row.suggested_quantity ?? 0);
        const qty = Number(prPullLineQty[id] ?? maxQty);
        if (!Number.isFinite(qty) || qty <= 0) {
          messageApi.error(
            t('app.kuaizhizao.purchaseReturn.pull.returnQtyInvalid', {
              material: row.material_code || row.material_name || '-',
            }),
          );
          return;
        }
        if (Number.isFinite(maxQty) && maxQty > 0 && qty > maxQty) {
          messageApi.error(
            t('app.kuaizhizao.purchaseReturn.pull.returnQtyExceeds', {
              material: row.material_code || row.material_name || '-',
            }),
          );
          return;
        }
        lineQuantities[id] = qty;
      }
      try {
        const res = await warehouseApi.purchaseReturn.pullFromPurchaseReceiptItems(selectedIds, {
          lineBatches,
          lineWarehouses,
          lineQuantities,
          lineLocationCodes:
            Object.keys(lineLocationCodes).length > 0 ? lineLocationCodes : undefined,
        });
        messageApi.success(
          res.message ||
            t('app.kuaizhizao.shipmentNotice.createFromSourceSuccess', {
              source: pullFromPurchaseReceiptAction.sourceLabel,
              target: pullFromPurchaseReceiptAction.targetLabel,
            }),
        );
        pullFromPurchaseReceiptQuery.closeModal();
        setPrPullLineBatch({});
        setPrPullLineQty({});
        setPrPullLineWh({});
        setPrPullBatchWarehouseId(undefined);
        pullSourceReceiptIdRef.current = undefined;
        setPullSourceReceiptId(undefined);
        invalidatePurchaseReturnStatistics();
        invalidateMenuBadgeCounts();
        actionRef.current?.reload();
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(
            error,
            t('app.kuaizhizao.shipmentNotice.createFromSourceFailed', {
              source: pullFromPurchaseReceiptAction.sourceLabel,
              target: pullFromPurchaseReceiptAction.targetLabel,
            }),
          ),
        );
      }
    },
  });

  const isPullPurchaseReturnSourceSelectable = useCallback(
    (record: { capabilities?: { push_purchase_return?: { allowed?: boolean } } }) =>
      record.capabilities?.push_purchase_return?.allowed === true,
    [],
  );

  const pullFromIncomingInspectionQuery = useUniPullQuery<PullIncomingInspectionCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullDocumentScopeOptions,
    defaultScope: 'pullable',
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const response = await qualityApi.incomingInspection.list({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          keyword: keyword.trim() || undefined,
        });
        const list = Array.isArray(response)
          ? response
          : (response as { data?: unknown[]; items?: unknown[] })?.data
            ?? (response as { items?: unknown[] })?.items
            ?? [];
        const rows = (Array.isArray(list) ? list : []) as PullIncomingInspectionCandidate[];
        const filtered = isPullableScope(scope)
          ? rows.filter((row) => isPullPurchaseReturnSourceSelectable(row))
          : rows;
        return { data: filtered, total: Number((response as { total?: number })?.total ?? filtered.length) };
      } catch (e: any) {
        messageApi.error(e?.message || t('app.kuaizhizao.quality.common.messages.loadListFailed'));
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullPurchaseReturnSourceSelectable(record),
    onConfirm: async (_keys, rows) => {
      const selectedIds = rows
        .filter((row) => isPullPurchaseReturnSourceSelectable(row))
        .map((row) => Number(row.id))
        .filter((id) => id > 0);
      if (!selectedIds.length) {
        messageApi.warning(t('app.kuaizhizao.purchaseReturn.pull.selectLinesFirst'));
        return;
      }
      try {
        for (const inspectionId of selectedIds) {
          await qualityApi.incomingInspection.pushToPurchaseReturn(String(inspectionId));
        }
        messageApi.success(
          t('app.kuaizhizao.shipmentNotice.createFromSourceSuccess', {
            source: pullFromIncomingInspectionAction.sourceLabel,
            target: pullFromIncomingInspectionAction.targetLabel,
          }),
        );
        pullFromIncomingInspectionQuery.closeModal();
        invalidatePurchaseReturnStatistics();
        invalidateMenuBadgeCounts();
        actionRef.current?.reload();
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(
            error,
            t('app.kuaizhizao.shipmentNotice.createFromSourceFailed', {
              source: pullFromIncomingInspectionAction.sourceLabel,
              target: pullFromIncomingInspectionAction.targetLabel,
            }),
          ),
        );
      }
    },
  });

  useEffect(() => {
    const raw = searchParams.get('pullPurchaseReceiptId');
    const id = raw ? Number(raw) : NaN;
    if (!Number.isFinite(id) || id <= 0) return;
    pullSourceReceiptIdRef.current = id;
    setPullSourceReceiptId(id);
    pullFromPurchaseReceiptQuery.openModal();
    const next = new URLSearchParams(searchParams);
    next.delete('pullPurchaseReceiptId');
    setSearchParams(next, { replace: true });
  }, []);

  useEffect(() => {
    const openCreate = searchParams.get('openCreate');
    const openPull = searchParams.get('openPull');
    if (openCreate !== '1' && openPull !== 'purchase_order' && openPull !== 'purchase_receipt') {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete('openCreate');
    next.delete('openPull');
    setSearchParams(next, { replace: true });
    if (openCreate === '1') {
      pendingCreateFormValuesRef.current = null;
      navigate(`${PURCHASE_RETURN_LIST_PATH}/new`);
      return;
    }
    if (openPull === 'purchase_order') {
      pullFromPurchaseOrderQuery.openModal();
      return;
    }
    pullFromPurchaseReceiptQuery.openModal();
    // 采购退货出库页跳转深链，仅首屏消费一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const raw = searchParams.get('openEditId');
    const id = raw ? Number(raw) : NaN;
    if (!Number.isFinite(id) || id <= 0) return;
    const next = new URLSearchParams(searchParams);
    next.delete('openEditId');
    setSearchParams(next, { replace: true });
    navigate(purchaseReturnEditPath(id));
    // 深链仅首屏消费一次（与 pullPurchaseReceiptId 一致）
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!pullFromPurchaseReceiptQuery.open) return;
    const rows = pullFromPurchaseReceiptQuery.dataSource;
    if (!rows.length) return;
    setPrPullLineQty((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const row of rows) {
        const id = Number(row.id);
        if (!(id > 0) || next[id] != null) continue;
        const remaining = Number(row.remaining_quantity ?? 0);
        const suggested = Number(row.suggested_quantity ?? 0);
        const defaultQty =
          Number.isFinite(remaining) && remaining > 0
            ? remaining
            : Number.isFinite(suggested) && suggested > 0
              ? suggested
              : 0;
        if (defaultQty > 0) {
          next[id] = defaultQty;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [pullFromPurchaseReceiptQuery.open, pullFromPurchaseReceiptQuery.dataSource]);

  useEffect(() => {
    if (!pullFromPurchaseReceiptQuery.open) return;
    const rows = pullFromPurchaseReceiptQuery.dataSource;
    if (!rows.length) return;
    setPrPullLineWh((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const row of rows) {
        const id = Number(row.id);
        if (!(id > 0) || next[id] != null) continue;
        const suggested = Number(row.warehouse_id);
        if (Number.isFinite(suggested) && suggested > 0) {
          next[id] = suggested;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [pullFromPurchaseReceiptQuery.open, pullFromPurchaseReceiptQuery.dataSource]);

  useEffect(() => {
    if (!pullFromPurchaseReceiptQuery.open) return;
    const rows = pullFromPurchaseReceiptQuery.dataSource;
    if (!rows.length) return;
    setPrPullLineBatch((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const row of rows) {
        const id = Number(row.id);
        if (!(id > 0) || next[id]) continue;
        const suggested = String(row.suggested_batch_number || '').trim();
        if (suggested) {
          next[id] = suggested;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [pullFromPurchaseReceiptQuery.open, pullFromPurchaseReceiptQuery.dataSource]);

  const applyPrPullBatchWarehouse = useCallback(
    (warehouseId: number) => {
      setPrPullBatchWarehouseId(warehouseId);
      const targetIds =
        pullFromPurchaseReceiptQuery.selectedRowKeys.length > 0
          ? pullFromPurchaseReceiptQuery.selectedRowKeys.map((k) => Number(k)).filter((id) => id > 0)
          : pullFromPurchaseReceiptQuery.dataSource.map((row) => Number(row.id)).filter((id) => id > 0);
      if (!targetIds.length) {
        messageApi.warning(t('app.kuaizhizao.purchaseReturn.pull.batchWarehouseNoLines'));
        return;
      }
      setPrPullLineWh((prev) => {
        const next = { ...prev };
        for (const id of targetIds) next[id] = warehouseId;
        return next;
      });
      messageApi.success(
        t('app.kuaizhizao.purchaseReturn.pull.batchWarehouseApplied', { count: targetIds.length }),
      );
    },
    [
      messageApi,
      pullFromPurchaseReceiptQuery.dataSource,
      pullFromPurchaseReceiptQuery.selectedRowKeys,
      t,
    ],
  );

  const handleEdit = (record: PurchaseReturn) => {
    if (record.id == null) return;
    navigate(purchaseReturnEditPath(record.id));
  };

  const loadPurchaseReturnEditForm = useCallback(
    async (id: number) => {
      setFormPageLoading(true);
      try {
        const detail = (await warehouseApi.purchaseReturn.get(String(id))) as PurchaseReturnDetail;
        if (detail.capabilities?.update?.allowed !== true) {
          messageApi.warning(t('app.kuaizhizao.purchaseReturn.editOnlyPending'));
          leavePurchaseReturnFormPage();
          return;
        }
        setEditingId(id);
        setEditingDetail(detail);
        updateSelectedWarehouseId(detail.warehouse_id ?? null);
        const rt = detail.return_time ? dayjs(detail.return_time) : dayjs();
        formRef.current?.resetFields?.();
        formRef.current?.setFieldsValue({
          supplier_id: detail.supplier_id,
          supplier_name: detail.supplier_name,
          department_id: (detail as { department_id?: number | null }).department_id ?? undefined,
          department_name: (detail as { department_name?: string | null }).department_name ?? undefined,
          warehouse_id: detail.warehouse_id,
          warehouse_name: detail.warehouse_name,
          return_time: rt,
          return_reason: detail.return_reason,
          return_type: detail.return_type,
          replenish: detail.replenish === true,
          shipping_method: detail.shipping_method,
          notes: detail.notes,
          attachments: mapAttachmentsToUploadList(detail.attachments),
          items: (detail.items || []).map((it) => ({
            material_id: (it as { material_id?: number }).material_id,
            material_code: it.material_code,
            material_name: it.material_name,
            return_quantity: it.return_quantity,
            unit_price: it.unit_price,
            batch_number: it.batch_number,
            location_code: it.location_code,
            notes: it.notes,
            purchase_receipt_item_id: (it as { purchase_receipt_item_id?: number }).purchase_receipt_item_id,
            material_spec: (it as { material_spec?: string }).material_spec,
            material_unit: (it as { material_unit?: string }).material_unit ?? t('app.kuaizhizao.purchaseReturn.defaultUnit'),
            aux_quantity: (it as { aux_quantity?: number }).aux_quantity,
            aux_unit: (it as { aux_unit?: string }).aux_unit,
            unit_conversion_rate: (it as { unit_conversion_rate?: number }).unit_conversion_rate,
          })),
        });
        const fieldFormValues = await loadPurchaseReturnFormFieldValues(id);
        formRef.current?.setFieldsValue(fieldFormValues);
      } catch {
        messageApi.error(t('app.kuaizhizao.purchaseReturn.loadDetailFailed'));
        leavePurchaseReturnFormPage();
      } finally {
        setFormPageLoading(false);
      }
    },
    [
      leavePurchaseReturnFormPage,
      loadPurchaseReturnFormFieldValues,
      messageApi,
      t,
      updateSelectedWarehouseId,
    ],
  );

  const initPurchaseReturnCreateForm = useCallback(() => {
    setEditingId(null);
    setEditingDetail(null);
    resetPurchaseReturnFormFieldValues();
    resetSelectedWarehouseId();
    formRef.current?.resetFields?.();
    const pending = pendingCreateFormValuesRef.current;
    if (pending) {
      pendingCreateFormValuesRef.current = null;
      formRef.current?.setFieldsValue(pending);
      const warehouseId = pending.warehouse_id;
      if (warehouseId != null && warehouseId !== '') {
        updateSelectedWarehouseId(Number(warehouseId));
      }
      return;
    }
    formRef.current?.setFieldsValue({
      return_time: dayjs(),
      items: [],
    });
  }, [
    resetPurchaseReturnFormFieldValues,
    resetSelectedWarehouseId,
    updateSelectedWarehouseId,
  ]);

  useEffect(() => {
    if (!isFormPage) {
      formPageInitKeyRef.current = null;
      return;
    }
    const initKey = isCreatePage ? 'create' : `edit:${editRouteId}`;
    if (formPageInitKeyRef.current === initKey) return;
    formPageInitKeyRef.current = initKey;
    if (isCreatePage) {
      initPurchaseReturnCreateForm();
      return;
    }
    if (editRouteId != null) {
      void loadPurchaseReturnEditForm(editRouteId);
    }
  }, [
    editRouteId,
    initPurchaseReturnCreateForm,
    isCreatePage,
    isFormPage,
    loadPurchaseReturnEditForm,
  ]);

  const handleCopySelectedPurchaseReturn = async () => {
    const source = selectedReturnsForBatch.length === 1 ? selectedReturnsForBatch[0] : null;
    if (source?.id == null) {
      messageApi.warning(t('app.kuaizhizao.purchaseReturn.selectToCopy'));
      return;
    }
    try {
      const detail = (await warehouseApi.purchaseReturn.get(String(source.id))) as PurchaseReturnDetail;
      setEditingId(null);
      setEditingDetail(null);
      updateSelectedWarehouseId(detail.warehouse_id ?? null);
      pendingCreateFormValuesRef.current = {
        supplier_id: detail.supplier_id,
        supplier_name: detail.supplier_name,
        department_id: (detail as { department_id?: number | null }).department_id ?? undefined,
        department_name: (detail as { department_name?: string | null }).department_name ?? undefined,
        warehouse_id: detail.warehouse_id,
        warehouse_name: detail.warehouse_name,
        return_time: dayjs(),
        return_reason: detail.return_reason,
        return_type: detail.return_type,
        replenish: detail.replenish === true,
        shipping_method: detail.shipping_method,
        notes: detail.notes,
        items: (detail.items || []).map((it) => ({
          material_id: (it as { material_id?: number }).material_id,
          material_code: it.material_code,
          material_name: it.material_name,
          return_quantity: it.return_quantity,
          unit_price: it.unit_price,
          batch_number: it.batch_number,
          location_code: it.location_code,
          notes: it.notes,
          material_spec: (it as { material_spec?: string }).material_spec,
          material_unit: (it as { material_unit?: string }).material_unit ?? defaultUnit,
          aux_quantity: (it as { aux_quantity?: number }).aux_quantity,
          aux_unit: (it as { aux_unit?: string }).aux_unit,
          unit_conversion_rate: (it as { unit_conversion_rate?: number }).unit_conversion_rate,
        })),
      };
      formPageInitKeyRef.current = null;
      navigate(`${PURCHASE_RETURN_LIST_PATH}/new`);
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t('common.loadFailed')));
    }
  };

  const executeWithdraw = async (record: PurchaseReturn) => {
    try {
          await warehouseApi.purchaseReturn.withdraw(String(record.id));
          messageApi.success(t('app.kuaizhizao.purchaseReturn.withdrawSuccess'));
          invalidatePurchaseReturnStatistics();
          invalidateMenuBadgeCounts();
          if (returnDetail?.id === record.id) {
            const fresh = await warehouseApi.purchaseReturn.get(String(record.id));
            setReturnDetail(fresh as PurchaseReturnDetail);
            setPrRetTrackingRefreshKey((k) => k + 1);
          }
    actionRef.current?.reload();
        } catch (error: unknown) {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseReturn.withdrawFailed')));
          throw error;
        }
  };

  const buildPurchaseReturnItemsPayload = (items: any[]) =>
    (items || []).map((it) => {
      const qty = resolveDocumentLineQuantityField(it as Record<string, unknown>, 'return_quantity');
      const price = Number(it.unit_price ?? 0);
      // 行金额以数量×单价为准，避免表单里残留的 0 总金额覆盖真实金额
      const total = Number((qty * price).toFixed(2));
      return {
        purchase_receipt_item_id: it.purchase_receipt_item_id ?? undefined,
        material_id: it.material_id,
        material_code: it.material_code || '',
        material_name: it.material_name || '',
        material_spec: it.material_spec ?? undefined,
        material_unit: it.material_unit || defaultUnit,
        ...pickDocumentLineDualQuantityFields(it as Record<string, unknown>),
        return_quantity: qty,
        unit_price: price,
        total_amount: total,
        batch_number: it.batch_number ?? undefined,
        location_code: it.location_code ?? undefined,
        notes: it.notes ?? undefined,
      };
    });

  const onFinish = async (values: any) => {
    const shouldCommit = commitAfterSaveRef.current;
    commitAfterSaveRef.current = false;
    try {
      const { customData, standardValues } = extractPurchaseReturnFormValues(values);
      const formItems = formRef.current?.getFieldValue('items');
      const itemsPayload = buildPurchaseReturnItemsPayload(
        Array.isArray(formItems) ? formItems : standardValues.items,
      );
      if (itemsPayload.some((line) => !(line.return_quantity > 0))) {
        messageApi.warning(t('app.kuaizhizao.purchaseReturn.returnQuantityRequired'));
        return;
      }
      const headerWhId = Number(standardValues.warehouse_id ?? editingDetail?.warehouse_id ?? 0);
      const materialMeta = await loadConfirmPreviewMaterialMeta(
        itemsPayload
          .filter((line) => line.material_id != null && Number(line.material_id) > 0)
          .map((line) => ({
            id: Number(line.material_id),
            material_id: Number(line.material_id),
            material_code: line.material_code,
          })),
      );
      for (const line of itemsPayload) {
        const material = line.material_code || line.material_name || '-';
        const needLoc = await lineLocationSelectionRequired(
          headerWhId,
          undefined,
          line.location_code,
        );
        if (needLoc) {
          messageApi.error(
            t('app.kuaizhizao.warehouseOutbound.msg.selectLocationForMaterial', { material }),
          );
          return;
        }
        const mid = Number(line.material_id);
        const meta = materialMeta[mid];
        if (isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) {
          if (!String(line.batch_number ?? '').trim()) {
            messageApi.error(
              t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
                material,
                batches: '—',
              }),
            );
            return;
          }
        }
      }
      const returnTime =
        standardValues.return_time && typeof standardValues.return_time.format === 'function'
          ? standardValues.return_time.format('YYYY-MM-DD')
          : standardValues.return_time;
      const saveId = editingId ?? editRouteId;
      let recordId: number | undefined;
      if (saveId) {
        const detail = editingDetail;
        if (!detail || detail.capabilities?.update?.allowed !== true) {
          messageApi.warning(t('app.kuaizhizao.purchaseReturn.editNotAllowed'));
          return;
        }
        const departmentPayload = resolvePurchaseDepartmentPayload(
          standardValues.department_id,
          resolveDepartmentName,
          standardValues.department_name,
        );
        await warehouseApi.purchaseReturn.update(String(saveId), {
          supplier_id: standardValues.supplier_id,
          supplier_name: standardValues.supplier_name ?? detail.supplier_name,
          ...departmentPayload,
          warehouse_id: standardValues.warehouse_id,
          warehouse_name: standardValues.warehouse_name ?? detail.warehouse_name,
          return_time: returnTime,
          return_reason: standardValues.return_reason ?? null,
          return_type: standardValues.return_type ?? detail.return_type ?? '质量问题',
          replenish: Boolean(standardValues.replenish),
          shipping_method: standardValues.shipping_method ?? null,
          tracking_number: detail.tracking_number ?? null,
          shipping_address: detail.shipping_address ?? null,
          notes: standardValues.notes ?? null,
          attachments: normalizeDocumentAttachments(standardValues.attachments),
          purchase_receipt_id: detail.purchase_receipt_id ?? null,
          purchase_receipt_code: detail.purchase_receipt_code ?? null,
          purchase_order_id: detail.purchase_order_id ?? null,
          purchase_order_code: detail.purchase_order_code ?? null,
          status: detail.status,
          items: itemsPayload,
        });
        recordId = saveId;
        if (!shouldCommit) {
          messageApi.success(t('app.kuaizhizao.purchaseReturn.updateSuccess'));
        }
      } else {
        const created = await warehouseApi.purchaseReturn.create({
          ...standardValues,
          ...resolvePurchaseDepartmentPayload(
            standardValues.department_id,
            resolveDepartmentName,
            standardValues.department_name,
          ),
          return_time: returnTime,
          attachments: normalizeDocumentAttachments(standardValues.attachments),
          items: itemsPayload,
        });
        recordId = (created as any)?.id;
        if (!shouldCommit) {
          messageApi.success(t('app.kuaizhizao.purchaseReturn.createSuccess'));
        }
      }
      if (recordId != null) {
        await savePurchaseReturnCustomFieldValues(recordId, customData);
      }
      if (shouldCommit) {
        if (recordId == null) {
          messageApi.error(t('common.operationFailed'));
          return;
        }
        try {
          await commitPurchaseReturn(recordId);
        } catch (error: unknown) {
          setEditingId(recordId);
          formPageInitKeyRef.current = null;
          navigate(purchaseReturnEditPath(recordId));
          messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
          actionRef.current?.reload();
          return;
        }
        messageApi.success(t('app.kuaizhizao.purchaseReturn.committed'));
      }
      resetPurchaseReturnFormFieldValues();
      setEditingId(null);
      setEditingDetail(null);
      resetSelectedWarehouseId();
      invalidatePurchaseReturnStatistics();
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
      formPageInitKeyRef.current = null;
      leavePurchaseReturnFormPage();
    } catch (error: any) {
      messageApi.error(error.message || t('common.operationFailed'));
    }
  };

  const appendItemsFromMaterials = (materials: Material[]) => {
    const currentItems = formRef.current?.getFieldValue('items') || [];
    const newItems = materials.map((m) => ({
      material_id: m.id,
      material_code: m.mainCode,
      material_name: m.name,
      material_spec: m.specification,
      material_unit: m.baseUnit,
      return_quantity: 1,
      unit_price: getMaterialDefaultPurchasePrice(m),
    }));
    formRef.current?.setFieldsValue({
      items: [...currentItems, ...newItems],
    });
    setMaterialPickerOpen(false);
  };

  const handleListImport = async (data: any[][]) => {
    if (!data || data.length < 2) {
      messageApi.warning(t('app.kuaizhizao.quotation.importDataInvalid'));
      return;
    }
    const rows = (data.slice(2) as any[][]).filter((row) =>
      row?.some((c) => c != null && String(c).trim() !== ''),
    );
    if (rows.length === 0) {
      messageApi.warning(t('app.kuaizhizao.quotation.noImportRows'));
      return;
    }

    try {
      const [materialsRes, warehousesRes] = await Promise.all([
        loadMaterialFormReferenceList(KUAIZHIZAO_DOC_HOST.purchaseReturn),
        masterWarehouseApi.list({ limit: 1000, is_active: true }),
      ]);
      const { resolveFactoryImportHeaderIndexMap } = await import(
        '../../../../../utils/spreadsheetImportTemplate'
      );
      const headers = (data[0] || []).map((h: unknown) => String(h || '').trim());
      const matColIdx =
        resolveFactoryImportHeaderIndexMap(headers, purchaseReturnListImportTemplate.importHeaderMap)
          .material ?? -1;
      const materials = await resolveMaterialsByCodesForImport(
        collectImportMaterialCodes(rows, matColIdx),
        materialsRes ?? [],
      );
      const warehouses = (warehousesRes as any)?.items ?? (Array.isArray(warehousesRes) ? warehousesRes : []);

      const { errors, items: toImport } = parseDocumentReturnListImport(data, {
        t,
        importHeaderMap: purchaseReturnListImportTemplate.importHeaderMap,
        partnerField: 'supplier',
        partners: supplierList,
        warehouses,
        materials,
        defaultUnit: t('app.kuaizhizao.purchaseReturn.defaultUnit'),
        defaultReturnType: 'OTHER',
        parseDict: purchaseReturnImportDictBag.parseDict,
      });

      if (errors.length > 0) {
        modalApi.warning({
          title: t('app.kuaizhizao.quotation.validationFailed'),
          width: 600,
          content: (
            <div>
              <p>{t('app.master-data.validationFailedIntro')}</p>
              <List
                size="small"
                dataSource={errors}
                renderItem={(item) => (
                  <List.Item>
                    <Typography.Text type="danger">
                      {t('app.kuaizhizao.quotation.importRowError', {
                        row: item.row,
                        message: item.message,
                      })}
                    </Typography.Text>
                  </List.Item>
                )}
              />
            </div>
          ),
        });
        return;
      }

      if (toImport.length === 0) {
        messageApi.warning(t('app.kuaizhizao.quotation.noImportData'));
        return;
      }

      const result = await importInChunksViaPerItemCreate({
        items: toImport,
        createOne: async (item, _index) =>
          warehouseApi.purchaseReturn.create({
            return_code: item.return_code,
            supplier_id: item.partner_id,
            supplier_name: item.partner_name,
            warehouse_id: item.warehouse_id,
            warehouse_name: item.warehouse_name,
            return_time: item.return_time,
            return_reason: item.return_reason,
            return_type: item.return_type,
            shipping_method: item.shipping_method,
            notes: item.notes,
            items: item.items,
          }),
        title: t('app.kuaizhizao.purchaseReturn.listImport.importing'),
        chunkSize: 100,
        concurrency: 4,
      });

      if (result.failureCount > 0) {
        modalApi.warning({
          title: t('app.kuaizhizao.quotation.importPartialTitle'),
          width: 600,
          content: (
            <div>
              <p>
                <strong>
                  {t('app.kuaizhizao.quotation.importResult', {
                    success: result.successCount,
                    failed: result.failureCount,
                  })}
                </strong>
              </p>
              {result.errors.length > 0 && (
                <List
                  size="small"
                  dataSource={result.errors}
                  renderItem={(e) => (
                    <List.Item>
                      <Typography.Text type="danger">
                        {t('app.kuaizhizao.quotation.importRowError', {
                          row: e.row,
                          message: e.error,
                        })}
                      </Typography.Text>
                    </List.Item>
                  )}
                />
              )}
            </div>
          ),
        });
      } else {
        messageApi.success(
          t('app.kuaizhizao.quotation.importSuccess', { count: result.successCount }),
        );
      }
      if (result.successCount > 0) {
        invalidateMenuBadgeCounts();
        invalidatePurchaseReturnStatistics();
    actionRef.current?.reload();
      }
    } catch (error: any) {
      messageApi.error(error?.message || t('common.importFailed'));
    }
  };

  const handleImport = (data: any[]) => {
    const currentItems = formRef.current?.getFieldValue('items') || [];
    const materialCodeKeys = [
      t('app.kuaizhizao.purchaseReturn.import.materialCode'),
      t('app.kuaizhizao.purchaseOrder.import.materialCode'),
      '物料编号',
    ];
    const unitKeys = [
      t('common.unit'),
      t('common.unit'),
      '单位',
    ];
    const returnQuantityKeys = [
      t('app.kuaizhizao.purchaseReturn.import.returnQuantity'),
      '退货数量',
    ];
    const unitPriceKeys = [
      t('app.kuaizhizao.purchaseReturn.import.unitPrice'),
      t('app.kuaizhizao.purchaseOrder.import.unitPrice'),
      '单价',
    ];
    const batchNumberKeys = [
      t('app.kuaizhizao.purchaseReturn.import.batchNumber'),
      '批次号',
    ];
    const locationKeys = [
      t('app.kuaizhizao.purchaseReturn.import.location'),
      '库位',
    ];
    const notesKeys = [
      t('common.remark'),
      '备注',
    ];
    const newItems = data.map((row) => ({
      material_code: getImportRowValue(row, materialCodeKeys),
      material_unit: getImportRowValue(row, unitKeys) || defaultUnit,
      return_quantity: Number(getImportRowValue(row, returnQuantityKeys) || 1),
      unit_price: Number(getImportRowValue(row, unitPriceKeys) || 0),
      batch_number: getImportRowValue(row, batchNumberKeys),
      location_code: getImportRowValue(row, locationKeys),
      notes: getImportRowValue(row, notesKeys),
    }));
    formRef.current?.setFieldsValue({
      items: [...currentItems, ...newItems],
    });
    setImportModalVisible(false);
  };

  const detailColumns: ProDescriptionsItemProps<PurchaseReturnDetail>[] = useMemo(
    () =>
      alignDescriptionColumns([
        {
          title: t('app.kuaizhizao.purchaseReturn.colReturnCode'),
          dataIndex: 'return_code',
          render: (_, entity) => (
            <Typography.Text copyable={{ text: String(entity.return_code ?? '') }}>{entity.return_code ?? '-'}</Typography.Text>
          ),
        },
        {
          title: t('app.kuaizhizao.purchaseReturn.colPurchaseReceiptCode'),
          dataIndex: 'purchase_receipt_code',
        },
        {
          title: t('app.kuaizhizao.purchaseReturn.colPurchaseOrderCode'),
          dataIndex: 'purchase_order_code',
        },
        { title: t('app.kuaizhizao.purchaseReturn.supplier'), dataIndex: 'supplier_name' },
        { title: t('app.kuaizhizao.purchaseReturn.colWarehouse'), dataIndex: 'warehouse_name' },
        { title: t('app.kuaizhizao.purchaseReturn.returnReason'), dataIndex: 'return_reason' },
        { title: t('app.kuaizhizao.purchaseReturn.returnType'), dataIndex: 'return_type' },
        {
          title: t('app.kuaizhizao.purchaseReturn.replenish'),
          dataIndex: 'replenish',
          render: (_, r) => (r.replenish ? t('common.yes') : t('common.no')),
        },
        { title: t('app.kuaizhizao.purchaseReturn.totalQuantity'), dataIndex: 'total_quantity', render: formatQuantity },
        {
          title: t('app.kuaizhizao.purchaseReturn.totalAmount'),
          dataIndex: 'total_amount',
          render: (text: unknown) => (text != null && text !== '' ? formatCurrencyAmount(text) : '-'),
        },
        { title: t('app.kuaizhizao.purchaseReturn.returnTime'), dataIndex: 'return_time', valueType: 'dateTime' },
        { title: t('app.kuaizhizao.purchaseReturn.returner'), dataIndex: 'returner_name' },
        { title: t('app.kuaizhizao.purchaseReturn.reviewer'), dataIndex: 'reviewer_name' },
        { title: t('app.kuaizhizao.purchaseReturn.reviewTime'), dataIndex: 'review_time', valueType: 'dateTime' },
      ] as ProDescriptionsItemProps<PurchaseReturnDetail>[]),
    [t, i18n.language],
  );

  const detailNotesColumn: ProDescriptionsItemProps<PurchaseReturnDetail>[] = useMemo(
    () =>
      alignDescriptionColumns([
        { title: t('common.remark'), dataIndex: 'notes', span: 3 },
      ] as ProDescriptionsItemProps<PurchaseReturnDetail>[]),
    [t, i18n.language],
  );

  const purchaseReturnCustomFieldColumns = generatePurchaseReturnCustomFieldColumns();

  const statCards: StatCard[] = useMemo(() => {
    const s = prStats;
    const z = [0, 0, 0, 0, 0, 0, 0];
    return [
      {
        title: t('app.kuaizhizao.purchaseReturn.statTotal'),
        value: s?.total_count ?? 0,
        valueStyle: { color: token.colorPrimary },
        backgroundChart: <SimpleSparkline data={s?.trend_total?.length ? s.trend_total : z} color={token.colorPrimary} />,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.statusPending'),
        value: s?.pending_count ?? 0,
        valueStyle: { color: token.colorWarning },
        backgroundChart: <SimpleSparkline data={s?.trend_pending?.length ? s.trend_pending : z} color={token.colorWarning} />,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.statusReturned'),
        value: s?.done_count ?? 0,
        valueStyle: { color: token.colorSuccess },
        backgroundChart: <SimpleSparkline data={s?.trend_done?.length ? s.trend_done : z} color={token.colorSuccess} />,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.statusCancelled'),
        value: s?.cancelled_count ?? 0,
        valueStyle: { color: token.colorError },
        backgroundChart: <SimpleSparkline data={s?.trend_cancelled?.length ? s.trend_cancelled : z} color={token.colorError} />,
      },
    ];
  }, [prStats, t, token, i18n.language]);

  const handleBatchDelete = async (keys: React.Key[]) => {
    if (!keys || keys.length === 0) return;
    const rows = keys
      .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
      .filter((row): row is PurchaseReturn => row != null);
    const deletable = rows.filter((row) => row.capabilities?.delete?.allowed === true);
    if (deletable.length === 0) {
      const blocked = rows.find((row) => row.capabilities?.delete?.reason);
      messageApi.warning(
        purchaseReturnCapabilityReasonMessage(blocked?.capabilities?.delete?.reason, t)
          || t('common.deleteFailed'),
      );
      return;
    }
    if (deletable.length < rows.length) {
      messageApi.warning(t('app.kuaizhizao.purchaseReturn.batchDeletePartialSkipped'));
    }
    try {
      for (const row of deletable) {
        await warehouseApi.purchaseReturn.delete(String(row.id));
      }
      messageApi.success(t('app.kuaizhizao.purchaseReturn.batchDeleteSuccess', { count: deletable.length }));
      setSelectedRowKeys([]);
      invalidatePurchaseReturnStatistics();
      if (returnDetail?.id != null && deletable.some((row) => row.id === returnDetail.id)) {
        setReturnDetail(null);
        setDetailDrawerVisible(false);
      }
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('common.deleteFailed'));
    }
  };

  const handleCreateRefund = useCallback(
    async (record: PurchaseReturn) => {
      if (!paymentRefundPerms.canCreate) {
        messageApi.warning(t('app.kuaizhizao.purchaseReturn.refundNoPermission'));
        return;
      }
      if (!isPurchaseReturnRefundEligible(record)) {
        messageApi.warning(t('app.kuaizhizao.purchaseReturn.refundNotCompleted'));
        return;
      }
      const returnId = Number(record.id);
      if (!Number.isFinite(returnId) || returnId <= 0) return;
      try {
        const resolved = await paymentRefundService.resolveFromPurchaseReturn(returnId);
        const ids = (resolved.source_ids || [])
          .map((id) => Number(id))
          .filter((id) => Number.isFinite(id) && id > 0);
        if (!ids.length) {
          messageApi.warning(t('app.kuaizhizao.purchaseReturn.refundNoPayment'));
          return;
        }
        navigate('/apps/kuaizhizao/finance-management/payment-refunds', {
          state: { pullSourceIds: ids },
        });
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.purchaseReturn.refundResolveFailed')),
        );
      }
    },
    [messageApi, navigate, paymentRefundPerms.canCreate, t],
  );

  const handleGenerateRedPayable = useCallback(
    async (record: PurchaseReturn) => {
      if (!payablePerms.canCreate) {
        messageApi.warning(t('app.kuaizhizao.purchaseReturn.generateRedPayableNoPermission'));
        return;
      }
      const returnId = Number(record.id);
      if (!Number.isFinite(returnId) || returnId <= 0) return;
      try {
        const updated = (await warehouseApi.purchaseReturn.generateRedPayable(
          String(returnId),
        )) as PurchaseReturnDetail;
        messageApi.success(t('app.kuaizhizao.purchaseReturn.generateRedPayableSuccess'));
        if (returnDetail?.id === returnId) {
          setReturnDetail(updated);
        }
        actionRef.current?.reload();
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.purchaseReturn.generateRedPayableFailed')),
        );
      }
    },
    [messageApi, payablePerms.canCreate, returnDetail?.id, t],
  );

  const columns: ProColumns<PurchaseReturn>[] = useMemo(
    () => alignProColumns<PurchaseReturn>([
      {
        title: t('app.kuaizhizao.purchaseReturn.returnTime'),
        dataIndex: 'return_time_range',
        valueType: 'dateRange',
        hideInTable: true,
        fieldProps: {
          placeholder: [t('app.kuaizhizao.quotation.dateRangeStart'), t('app.kuaizhizao.quotation.dateRangeEnd')],
        },
        formItemProps: formDateRangeFormItemProps,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.colSupplierReturnCode'),
        key: 'return_code',
        dataIndex: 'return_code',
        width: 240,
        minWidth: 240,
        uniTableKeepWidth: true,
        uniTablePrimaryFlex: false,
        resizable: false,
        fixed: 'left',
        sorter: true,
        render: (_, r) => (
          <UniTableStackedPrimaryCell
            primary={String(r.supplier_name ?? '')}
            secondary={String(r.return_code ?? '')}
          />
        ),
      },
      { title: t('app.kuaizhizao.purchaseReturn.colReturnCode'), dataIndex: 'return_code', hideInTable: true, hideInSearch: false },
      {
        title: t('app.kuaizhizao.purchaseReturn.supplier'),
        dataIndex: 'supplier_id',
        hideInTable: true,
        valueType: 'select',
        fieldProps: {
          showSearch: true,
          optionFilterProp: 'label',
          options: purchaseReturnSupplierSearchOptions,
          placeholder: t('app.kuaizhizao.purchaseReturn.supplier'),
        },
      },
      { title: t('app.kuaizhizao.purchaseReturn.supplier'), dataIndex: 'supplier_name', hideInTable: true, hideInSearch: true },
      {
        title: t('app.kuaizhizao.common.colLineMaterials'),
        ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
        // 采退专用段位：主标识后、仓库前
        key: 'purchase_return_line_materials',
        dataIndex: 'purchase_return_line_materials',
        render: (_, r) => renderDocumentLineMaterialsPreview(r.items, t),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.colWarehouse'),
        key: 'purchase_return_warehouse',
        dataIndex: 'warehouse_name',
        width: 140,
        minWidth: 140,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        sorter: true,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.colRelatedDocs'),
        key: 'purchase_return_related_docs',
        dataIndex: 'purchase_order_code',
        width: 180,
        minWidth: 180,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: false,
        hideInSearch: true,
        render: (_, r) => {
          // 与销售退货一致：来源一般为采购订单或采购入库单二选一
          const receipt = String(r.purchase_receipt_code ?? '').trim();
          const order = String(r.purchase_order_code ?? '').trim();
          if (receipt && r.purchase_receipt_id) {
            return (
              <LinkedDocumentCode
                documentType="purchase_receipt"
                documentId={r.purchase_receipt_id}
                code={receipt}
              />
            );
          }
          if (order && r.purchase_order_id) {
            return (
              <LinkedDocumentCode
                documentType="purchase_order"
                documentId={r.purchase_order_id}
                code={order}
              />
            );
          }
          return receipt || order || '-';
        },
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.colPurchaseOrderCode'),
        dataIndex: 'purchase_order_code',
        hideInTable: true,
        fieldProps: { placeholder: t('app.kuaizhizao.purchaseReturn.colPurchaseOrderCode') },
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.colPurchaseReceiptCode'),
        dataIndex: 'purchase_receipt_code',
        hideInTable: true,
        fieldProps: { placeholder: t('app.kuaizhizao.purchaseReturn.colPurchaseReceiptCode') },
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.totalQuantity'),
        dataIndex: 'total_quantity',
        width: 100,
        minWidth: 100,
        uniTableKeepWidth: true,
        resizable: false,
        align: 'right',
        sorter: true,
        hideInSearch: true,
        render: formatQuantity,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.totalAmount'),
        dataIndex: 'total_amount',
        width: 120,
        minWidth: 120,
        uniTableKeepWidth: true,
        resizable: false,
        align: 'right',
        sorter: true,
        hideInSearch: true,
        render: (text: any) => (text != null && text !== '' ? formatCurrencyAmount(text) : '-'),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.returnTime'),
        dataIndex: 'return_time',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        sorter: true,
        hideInSearch: true,
        render: (_, r) => (r.return_time ? formatDateTime(r.return_time, 'YYYY-MM-DD HH:mm') : '-'),
      },
      ...buildDocumentAuditColumns<PurchaseReturn>(t),
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
      ...(purchaseReturnAuditColumn ? [purchaseReturnAuditColumn] : []),
      {
        title: t('app.kuaizhizao.purchaseReturn.colLifecycle'),
        key: 'lifecycle',
        dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
        fixed: 'right',
        valueType: 'select',
        valueEnum: purchaseReturnLifecycleValueEnum,
        render: (_, record) => (
          <ListUniLifecycleCell lifecycle={getPurchaseReturnLifecycle(record, t)} />
        ),
      },
      ...purchaseReturnCustomFieldColumns,
      {
        title: t('common.actions'),
        key: 'option',
        valueType: 'option',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) => {
          const parts: React.ReactNode[] = [
            <Button {...rowActionKind('read')}
              key="d"
              type="link"
              size="small"
              icon={<EyeOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                handleDetail(record);
              }}
            >
              {t('common.detail')}
            </Button>,
          ];
          if (record.capabilities?.update?.allowed === true && purchaseReturnPerms.canUpdate) {
            parts.push(
              <Button {...rowActionKind('update')}
                key="e"
                type="link"
                size="small"
                icon={<EditOutlined />}
                onClick={(e) => {
                  e.stopPropagation();
                  void handleEdit(record);
                }}
              >
                {t('common.edit')}
              </Button>
            );
          }
          if (isPurchaseReturnRefundEligible(record) && paymentRefundPerms.canCreate) {
            parts.push(
              <Button
                {...rowActionCreateRefund('create')}
                key="refund"
                onClick={(e) => {
                  e.stopPropagation();
                  void handleCreateRefund(record);
                }}
              />,
            );
          }
          return parts;
        },
      },
    ], SALES_DOC_LIST_FIELD_RANK),
    [
      handleCreateRefund,
      handleDetail,
      handleEdit,
      paymentRefundPerms.canCreate,
      purchaseReturnAuditColumn,
      purchaseReturnCustomFieldColumns,
      purchaseReturnLifecycleValueEnum,
      purchaseReturnPerms.canUpdate,
      purchaseReturnSupplierSearchOptions,
      t,
      i18n.language,
    ],
  );

  const formItemColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.shipmentNotice.import.materialName'),
        dataIndex: 'material_id',
        width: DOCUMENT_DETAIL_COL_WIDTH.material,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <UniMaterialSelect
            name={[index, 'material_id']}
            label=""
            placeholder={t('common.selectMaterial')}
            required
            size={DOCUMENT_DETAIL_CONTROL_SIZE}
            listFieldKey={index}
            listFieldName="items"
            fillMapping={withMaterialLineFillMapping({ material_unit: 'baseUnit' })}
            showAdvancedSearch
            skipFuzzyPinyinClientFilter
            onChange={(_v, material) => {
              if (!material || !formRef.current) return;
              const supplierId = Number(formRef.current.getFieldValue('supplier_id'));
              void applyPurchaseDocumentLineMaterialPricing(formRef.current, index, material, {
                asOfField: 'return_time',
                unitPriceField: 'unit_price',
                supplierId: Number.isFinite(supplierId) && supplierId > 0 ? supplierId : undefined,
              });
            }}
          />
        ),
      },
      ...buildDocumentDetailSpecModelFormColumns(t),
      ...buildDocumentDetailPartnerMaterialFormColumns(t, 'supplier'),
      ...buildDocumentLineDualQuantityFormColumns({
        t,
        getForm: () => formRef.current,
        quantityField: 'return_quantity',
        unitField: 'material_unit',
        scenario: 'purchase',
        quantityDecimals,
        unitWidth: DOCUMENT_DETAIL_COL_WIDTH.unit,
        quantityWidth: DOCUMENT_DETAIL_COL_WIDTH.quantity + 80,
        controlSize: DOCUMENT_DETAIL_CONTROL_SIZE,
        unitColumnSpread: DOCUMENT_DETAIL_TEXT_COL,
        quantityColumnSpread: DOCUMENT_DETAIL_NUM_COL,
        onAfterQuantityChange: (rowIndex) => {
          const supplierId = Number(formRef.current?.getFieldValue('supplier_id'));
          void repriceUnlockedPurchaseDocumentLineIfNeeded(formRef.current, rowIndex, {
            asOfField: 'return_time',
            unitPriceField: 'unit_price',
            trigger: 'quantity',
            supplierId: Number.isFinite(supplierId) && supplierId > 0 ? supplierId : undefined,
          });
        },
      }),
      {
        title: t('app.kuaizhizao.purchaseReturn.batchNumber'),
        dataIndex: 'batch_number',
        width: 150,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item name={[index, 'batch_number']} noStyle>
            <Input size={DOCUMENT_DETAIL_CONTROL_SIZE} placeholder={t('app.kuaizhizao.purchaseReturn.batchNumberPlaceholder')} />
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.location'),
        dataIndex: 'location_code',
        width: 180,
        ...DOCUMENT_DETAIL_TEXT_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item name={[index, 'location_code']} noStyle>
            <Select
              options={locationOptions}
              placeholder={selectedWarehouseId ? t('app.kuaizhizao.purchaseReturn.selectLocation') : t('app.kuaizhizao.purchaseReturn.selectWarehouseFirst')}
              style={{ width: '100%' }}
              size={DOCUMENT_DETAIL_CONTROL_SIZE}
              showSearch
              optionFilterProp="label"
              allowClear
              disabled={!selectedWarehouseId}
            />
          </AntForm.Item>
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.unitPrice'),
        dataIndex: 'unit_price',
        width: DOCUMENT_DETAIL_COL_WIDTH.unitPrice,
        ...DOCUMENT_DETAIL_NUM_COL,
        render: (_: unknown, __: unknown, index: number) => (
          <AntForm.Item name={[index, 'unit_price']} noStyle>
            <InputNumber size={DOCUMENT_DETAIL_CONTROL_SIZE} style={{ width: '100%' }} min={0} prefix="¥" />
          </AntForm.Item>
        ),
      },
    ],
    [locationOptions, selectedWarehouseId, quantityDecimals, t, i18n.language],
  );

  const detailItemColumns = useMemo(
    () => [
      { title: t('app.kuaizhizao.purchaseReturn.import.materialCode'), dataIndex: 'material_code', width: 120, ellipsis: true },
      { title: t('app.kuaizhizao.shipmentNotice.import.materialName'), dataIndex: 'material_name', width: 150, ellipsis: true },
      { title: t('app.kuaizhizao.purchaseReturn.returnQuantity'), dataIndex: 'return_quantity', width: 100, align: 'right' as const , render: formatQuantity },
      {
        title: t('app.kuaizhizao.purchaseReturn.unitPrice'),
        dataIndex: 'unit_price',
        width: 100,
        align: 'right' as const,
        render: (text: number) => formatCurrencyPrice(text),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.amount'),
        dataIndex: 'total_amount',
        width: 100,
        align: 'right' as const,
        render: (text: number) => formatCurrencyAmount(text),
      },
      { title: t('app.kuaizhizao.purchaseReturn.import.batchNumber'), dataIndex: 'batch_number', width: 120 },
      { title: t('app.kuaizhizao.purchaseReturn.location'), dataIndex: 'location_code', width: 100 },
    ],
    [t, i18n.language],
  );

  const pullPurchaseOrderColumns = useMemo<ProColumns<PurchaseReturnPullLine>[]>(
    () => [
      {
        title: t('app.kuaizhizao.purchaseOrder.col.orderCode'),
        dataIndex: 'order_code',
        width: 136,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialCode'),
        dataIndex: 'material_code',
        width: 120,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialName'),
        dataIndex: 'material_name',
        width: 200,
        ellipsis: true,
        render: (_: unknown, record: PurchaseReturnPullLine) => (
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
        sorter: (a: PurchaseReturnPullLine, b: PurchaseReturnPullLine) =>
          String(a.document_date || a.order_date || '').localeCompare(
            String(b.document_date || b.order_date || ''),
          ),
        defaultSortOrder: 'descend',
        render: (_: unknown, record: PurchaseReturnPullLine) => {
          const raw = record.document_date || record.order_date;
          return raw ? formatBusinessDateOnly(String(raw)) : '-';
        },
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.pull.warehouseColumn'),
        key: 'warehouse',
        width: 136,
        render: (_: unknown, record: PurchaseReturnPullLine) => (
          <Select
            style={{ width: '100%', minWidth: 118 }}
            size="small"
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaizhizao.purchaseReturn.pull.selectWarehouse')}
            value={poPullLineWh[record.id]}
            options={poPullWarehouseOptions}
            status={!poPullLineWh[record.id] && !record.warehouse_id ? 'error' : undefined}
            onClick={(e) => e.stopPropagation()}
            onChange={(value) => {
              const nextId = Number(value);
              if (!(Number.isFinite(nextId) && nextId > 0)) return;
              setPoPullLineWh((prev) => ({ ...prev, [record.id]: nextId }));
            }}
          />
        ),
      },
      {
        title: t('common.quantity'),
        dataIndex: 'suggested_quantity',
        width: 88,
        align: 'right',
        render: (v) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.salesOrder.colShippedQty'),
        dataIndex: 'pushed_quantity',
        width: 88,
        align: 'right',
        render: (v) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.salesOrder.colShippableQty'),
        dataIndex: 'remaining_quantity',
        width: 88,
        align: 'right',
        render: (v) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.import.batchNumber'),
        key: 'batch_number',
        dataIndex: 'suggested_batch_number',
        width: 220,
        render: (_: unknown, record: PurchaseReturnPullLine) => {
          const pickOptions: InventoryPickOption[] = (record.available_batches || [])
            .map((row) => {
              const bn = String(row.batch_number || '').trim();
              if (!bn) return null;
              return {
                value: bn,
                label: bn,
                quantity: Number(row.receipt_quantity ?? 0) || undefined,
              } as InventoryPickOption;
            })
            .filter((x): x is InventoryPickOption => x != null);
          const remQty = Number(record.remaining_quantity ?? record.suggested_quantity ?? 0);
          const current = poPullLineBatch[record.id] ?? record.suggested_batch_number ?? undefined;
          const allocs =
            poPullLineBatchAllocs[record.id] ??
            coerceBatchAllocationsDraft(current, remQty) ??
            [];
          if (!record.requires_batch_number && !pickOptions.length) {
            return current || '-';
          }
          if (!pickOptions.length) {
            return (
              <Input
                size="small"
                allowClear={!record.requires_batch_number}
                placeholder={t('app.kuaizhizao.purchaseReturn.pull.selectBatch')}
                value={current || undefined}
                status={record.requires_batch_number && !current ? 'error' : undefined}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => {
                  const next = String(e.target.value || '').trim();
                  setPoPullLineBatch((prev) => {
                    const copy = { ...prev };
                    if (next) copy[record.id] = next;
                    else delete copy[record.id];
                    return copy;
                  });
                  setPoPullLineBatchAllocs((prev) => {
                    const copy = { ...prev };
                    if (next) copy[record.id] = [{ batchNo: next, quantity: remQty }];
                    else delete copy[record.id];
                    return copy;
                  });
                }}
              />
            );
          }
          const materialLabel = [record.material_code, record.material_name]
            .filter(Boolean)
            .join(' - ');
          return (
            <span onClick={(e) => e.stopPropagation()}>
              <OutboundBatchAllocationField
                value={allocs}
                onChange={(next) => {
                  setPoPullLineBatchAllocs((prev) => ({ ...prev, [record.id]: next }));
                  setPoPullLineBatch((prev) => {
                    const copy = { ...prev };
                    if (next.length === 1) copy[record.id] = next[0].batchNo;
                    else delete copy[record.id];
                    return copy;
                  });
                }}
                options={pickOptions}
                totalQuantity={remQty}
                materialLabel={materialLabel}
              />
            </span>
          );
        },
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.location'),
        key: 'location',
        width: 96,
        ellipsis: true,
        render: (_: unknown, record: PurchaseReturnPullLine) => {
          const batch = String(
            poPullLineBatch[record.id] ?? record.suggested_batch_number ?? '',
          ).trim();
          const batchRow = record.available_batches?.find((b) => b.batch_number === batch);
          const loc = String(batchRow?.location_code ?? '').trim();
          return loc || '—';
        },
      },
      {
        title: t('app.kuaizhizao.receiptNotice.supplier'),
        dataIndex: 'supplier_name',
        width: 120,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.deliveryDate'),
        dataIndex: 'required_date',
        width: 100,
        render: (v) => (v ? formatBusinessDateOnly(String(v)) : '-'),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.pull.gateStatus'),
        key: 'convert_status',
        width: 96,
        align: 'center',
        render: (_: unknown, record: PurchaseReturnPullLine) =>
          renderPullCapabilityTag(
            isPullOpenLineSelectable(record),
            t('app.kuaizhizao.purchaseReturn.pull.canCreate'),
            t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
          ),
      },
    ],
    [t, i18n.language, poPullLineBatch, poPullLineBatchAllocs, poPullLineWh, poPullWarehouseOptions],
  );

  const pullPurchaseReceiptColumns = useMemo<ProColumns<PurchaseReceiptReturnPullLine>[]>(
    () => [
      {
        title: t('app.kuaizhizao.purchaseReturn.colPurchaseReceiptCode'),
        dataIndex: 'receipt_code',
        width: 136,
        ellipsis: true,
      },
      {
        title: t('components.uniPullQuery.documentDateColumn'),
        dataIndex: 'document_date',
        width: 112,
        sorter: (a, b) =>
          String(a.document_date || a.required_date || '').localeCompare(
            String(b.document_date || b.required_date || ''),
          ),
        defaultSortOrder: 'descend',
        render: (_: unknown, record: PurchaseReceiptReturnPullLine) => {
          const raw = record.document_date || record.required_date;
          return raw ? formatBusinessDateOnly(String(raw)) : '-';
        },
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialCode'),
        dataIndex: 'material_code',
        width: 120,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialName'),
        dataIndex: 'material_name',
        width: 200,
        ellipsis: true,
        render: (_: unknown, record: PurchaseReceiptReturnPullLine) => (
          <MaterialStackedCell
            material_name={record.material_name}
            material_code={record.material_code}
            material_spec={record.material_spec}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.pull.warehouseColumn'),
        key: 'warehouse',
        width: 136,
        render: (_: unknown, record: PurchaseReceiptReturnPullLine) => (
          <Select
            style={{ width: '100%', minWidth: 118 }}
            size="small"
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaizhizao.purchaseReturn.pull.selectWarehouse')}
            value={prPullLineWh[record.id]}
            options={poPullWarehouseOptions}
            status={!prPullLineWh[record.id] && !record.warehouse_id ? 'error' : undefined}
            onClick={(e) => e.stopPropagation()}
            onChange={(value) => {
              const nextId = Number(value);
              if (!(Number.isFinite(nextId) && nextId > 0)) return;
              setPrPullLineWh((prev) => ({ ...prev, [record.id]: nextId }));
            }}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.returnQuantity'),
        key: 'return_quantity',
        width: 100,
        align: 'right',
        render: (_: unknown, record: PurchaseReceiptReturnPullLine) => {
          const maxQty = Number(record.remaining_quantity ?? record.suggested_quantity ?? 0);
          const value = prPullLineQty[record.id] ?? (maxQty > 0 ? maxQty : undefined);
          return (
            <InputNumber
              size="small"
              style={{ width: '100%', minWidth: 72 }}
              min={0}
              max={maxQty > 0 ? maxQty : undefined}
              precision={4}
              value={value}
              status={value == null || !(Number(value) > 0) ? 'error' : undefined}
              onClick={(e) => e.stopPropagation()}
              onChange={(next) => {
                if (next == null) {
                  setPrPullLineQty((prev) => {
                    const copy = { ...prev };
                    delete copy[record.id];
                    return copy;
                  });
                  return;
                }
                const parsed = Number(next);
                if (!Number.isFinite(parsed)) return;
                setPrPullLineQty((prev) => ({ ...prev, [record.id]: parsed }));
              }}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.salesOrder.colShippedQty'),
        dataIndex: 'pushed_quantity',
        width: 88,
        align: 'right',
        render: (v) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.salesOrder.colShippableQty'),
        dataIndex: 'remaining_quantity',
        width: 88,
        align: 'right',
        render: (v) => formatQuantity(v),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.import.batchNumber'),
        key: 'batch_number',
        dataIndex: 'suggested_batch_number',
        width: 132,
        render: (_: unknown, record: PurchaseReceiptReturnPullLine) => {
          const current = prPullLineBatch[record.id] ?? record.suggested_batch_number ?? undefined;
          if (!record.requires_batch_number) {
            return current || '-';
          }
          return (
            <Input
              size="small"
              allowClear={!record.requires_batch_number}
              placeholder={t('app.kuaizhizao.purchaseReturn.pull.selectBatch')}
              value={current || undefined}
              status={record.requires_batch_number && !current ? 'error' : undefined}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => {
                const next = String(e.target.value || '').trim();
                setPrPullLineBatch((prev) => {
                  const copy = { ...prev };
                  if (next) copy[record.id] = next;
                  else delete copy[record.id];
                  return copy;
                });
              }}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.location'),
        key: 'location',
        width: 96,
        ellipsis: true,
        render: (_: unknown, record: PurchaseReceiptReturnPullLine) => {
          const loc = String(record.suggested_location_code ?? '').trim();
          return loc || '—';
        },
      },
      {
        title: t('app.kuaizhizao.receiptNotice.supplier'),
        dataIndex: 'supplier_name',
        width: 120,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.pull.gateStatus'),
        key: 'convert_status',
        width: 96,
        align: 'center',
        render: (_: unknown, record: PurchaseReceiptReturnPullLine) =>
          renderPullCapabilityTag(
            isPullOpenLineSelectable(record),
            t('app.kuaizhizao.purchaseReturn.pull.canCreate'),
            t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
          ),
      },
    ],
    [t, i18n.language, prPullLineBatch, prPullLineQty, prPullLineWh, poPullWarehouseOptions],
  );

  const pullIncomingInspectionColumns = useMemo<ProColumns<PullIncomingInspectionCandidate>[]>(
    () => [
      { title: t('app.kuaizhizao.quality.common.columns.inspectionCode'), dataIndex: 'inspection_code', width: 180, ellipsis: true },
      { title: t('app.kuaizhizao.purchaseReturn.colPurchaseReceiptCode'), dataIndex: 'purchase_receipt_code', width: 180, ellipsis: true },
      { title: t('app.kuaizhizao.receiptNotice.supplier'), dataIndex: 'supplier_name', width: 180, ellipsis: true },
      { title: t('app.kuaizhizao.purchaseOrder.col.materialName'), dataIndex: 'material_name', ellipsis: true },
      { title: t('app.kuaizhizao.quality.common.columns.unqualifiedQty'), dataIndex: 'unqualified_quantity', width: 120, align: 'right', render: (v) => formatQuantity(v) },
      {
        title: t('app.kuaizhizao.quality.common.columns.qualityStatus'),
        dataIndex: 'quality_status',
        width: 100,
        align: 'center' as const,
        render: (v) => renderPullQueryDocStatus(t, v),
      },
      {
        title: t('app.kuaizhizao.quality.common.columns.inspectionStatus'),
        dataIndex: 'status',
        width: 100,
        align: 'center' as const,
        render: (v) => renderPullQueryDocStatus(t, v),
      },
      { title: t('common.updatedAt'), dataIndex: 'updated_at', width: 180, render: (v) => (v ? formatDateTime(v, 'YYYY-MM-DD HH:mm:ss') : '-') },
    ],
    [t, i18n.language],
  );

  const detailTableColumns: ProColumns<PurchaseReturnItemRow>[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.purchaseReturn.colSupplierReturnCode'),
        key: 'return_code',
        dataIndex: 'return_code',
        ...UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
        fixed: 'left',
        hideInSearch: false,
        fieldProps: { placeholder: t('app.kuaizhizao.purchaseReturn.colReturnCode') },
        render: (_, record) => (
          <UniTableStackedPrimaryCell
            primary={String(record.supplier_name ?? '')}
            secondary={String(record.return_code ?? '')}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.colReturnCode'),
        dataIndex: 'return_code',
        hideInTable: true,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.supplier'),
        dataIndex: 'supplier_id',
        hideInTable: true,
        valueType: 'select',
        fieldProps: {
          showSearch: true,
          optionFilterProp: 'label',
          options: purchaseReturnSupplierSearchOptions,
          placeholder: t('app.kuaizhizao.purchaseReturn.supplier'),
        },
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.import.materialName'),
        key: 'material_display',
        dataIndex: 'material_name',
        ...UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
        hideInSearch: true,
        render: (_, record) => (
          <MaterialStackedCell
            material_name={record.material_name}
            material_code={record.material_code}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.import.materialCode'),
        dataIndex: 'material_code',
        hideInTable: true,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.returnQuantity'),
        dataIndex: 'return_quantity',
        width: 100,
        align: 'right',
        hideInSearch: true,
        render: formatQuantity,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.unitPrice'),
        dataIndex: 'unit_price',
        width: 100,
        align: 'right',
        hideInSearch: true,
        render: (text: unknown) =>
          text != null && text !== '' ? formatCurrencyAmount(text) : '-',
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.amount'),
        dataIndex: 'total_amount',
        width: 100,
        align: 'right',
        hideInSearch: true,
        render: (text: unknown) =>
          text != null && text !== '' ? formatCurrencyAmount(text) : '-',
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.import.batchNumber'),
        dataIndex: 'batch_number',
        width: 120,
        hideInSearch: true,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.location'),
        dataIndex: 'location_code',
        width: 100,
        hideInSearch: true,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.colWarehouse'),
        dataIndex: 'warehouse_name',
        width: 140,
        ellipsis: true,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.returnTime'),
        dataIndex: 'return_time',
        width: 132,
        uniTableKeepWidth: true,
        hideInSearch: true,
        render: (_, record) =>
          record.return_time ? formatDateTime(record.return_time, 'YYYY-MM-DD HH:mm') : '-',
      },
      {
        title: t('app.kuaizhizao.purchaseReturn.colLifecycle'),
        dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
        fixed: 'right',
        hideInSearch: false,
        valueType: 'select',
        valueEnum: purchaseReturnLifecycleValueEnum,
        render: (_, record) => (
          <ListUniLifecycleCell
            lifecycle={getPurchaseReturnLifecycle(
              {
                status: record.status,
                review_status: record.review_status,
                lifecycle: record.lifecycle,
              } as PurchaseReturn,
              t,
            )}
          />
        ),
      },
    ],
    [purchaseReturnLifecycleValueEnum, purchaseReturnSupplierSearchOptions, t],
  );

  const timeconfigBasicItems0 = useDetailDrawerDescriptionItems(
    detailColumns, returnDetail as unknown as Record<string, unknown>,
    'purchase_return',
  );

  const timeconfigBasicItems1 = useDetailDrawerDescriptionItems(
    detailNotesColumn, returnDetail as unknown as Record<string, unknown>,
    'purchase_return',
  );

  const purchaseReturnAttachments = documentAttachmentsFromRecord(returnDetail);
  const showPurchaseReturnAttachments =
    Boolean(returnDetail) && hasDocumentAttachments(purchaseReturnAttachments);
  const purchaseReturnFormReview = String(editingDetail?.review_status || '').trim();
  const purchaseReturnFormCanCommit =
    !editingId
    || ['', '草稿', 'draft', 'DRAFT', '审核驳回', '已驳回', 'rejected', 'REJECTED'].includes(
      purchaseReturnFormReview,
    );


  const submitPurchaseReturnForm = useCallback(() => {
    void formRef.current?.submit?.();
  }, []);

  const triggerPurchaseReturnCommit = useCallback(() => {
    commitAfterSaveRef.current = true;
    void formRef.current?.submit?.();
  }, []);

  useSubmitShortcut(submitPurchaseReturnForm, isFormPage);

  const renderPurchaseReturnFormFields = () => (
    <>
        <Row gutter={16}>
          <Col span={8}>
            <ProFormSelect
              name="supplier_id"
              label={t('app.kuaizhizao.purchaseReturn.supplier')}
              placeholder={t('app.kuaizhizao.purchaseReturn.selectSupplier')}
              required
              request={async () => {
                const list = await loadSupplierFormReferenceList(KUAIZHIZAO_DOC_HOST.purchaseReturn);
                return list.map((s) => ({
                  label: s.name || s.code || t('app.kuaizhizao.purchaseReturn.supplierFallback', { id: s.id }),
                  value: s.id,
                }));
              }}
              fieldProps={{
                showSearch: true,
                optionFilterProp: 'label',
                onChange: (value, option) => {
                  formRef.current?.setFieldsValue({ supplier_name: (option as any)?.label ?? '' });
                  const supplierId = Number(value);
                  const lineItems = normalizeFormListItems<Record<string, unknown>>(
                    formRef.current?.getFieldValue('items'),
                  );
                  lineItems.forEach((_, idx) => {
                    void repriceUnlockedPurchaseDocumentLineIfNeeded(formRef.current, idx, {
                      asOfField: 'return_time',
                      unitPriceField: 'unit_price',
                      supplierId: Number.isFinite(supplierId) && supplierId > 0 ? supplierId : undefined,
                    });
                  });
                },
              }}
              rules={[{ required: true, message: t('app.kuaizhizao.purchaseReturn.selectSupplier') }]}
            />
            <ProFormText name="supplier_name" hidden />
          </Col>
          <Col span={8}>
            <UniWarehouseSelect
              name="warehouse_id"
              label={t('app.kuaizhizao.purchaseReturn.returnWarehouse')}
              placeholder={t('app.kuaizhizao.purchaseReturn.selectWarehouse')}
              required
              onChange={(value, wh) => {
                formRef.current?.setFieldsValue({ warehouse_name: (wh as any)?.name ?? '' });
                updateSelectedWarehouseId(value);
              }}
              rules={[{ required: true, message: t('app.kuaizhizao.purchaseReturn.selectWarehouse') }]}
            />
            <ProFormText name="warehouse_name" hidden />
          </Col>
          <Col span={8}>
            <ProFormDatePicker
              name="return_time"
              label={t('app.kuaizhizao.purchaseReturn.returnDate')}
              required
              fieldProps={{
                style: { width: '100%' },
                onChange: () => {
                  const supplierId = Number(formRef.current?.getFieldValue('supplier_id'));
                  const lineItems = normalizeFormListItems<Record<string, unknown>>(
                    formRef.current?.getFieldValue('items'),
                  );
                  lineItems.forEach((_, idx) => {
                    void repriceUnlockedPurchaseDocumentLineIfNeeded(formRef.current, idx, {
                      asOfField: 'return_time',
                      unitPriceField: 'unit_price',
                      supplierId: Number.isFinite(supplierId) && supplierId > 0 ? supplierId : undefined,
                    });
                  });
                },
              }}
              initialValue={dayjs()}
            />
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={8}>
            <PurchaseDepartmentFormField
              options={departmentOptions}
              loading={departmentOptionsLoading}
            />
          </Col>
          <Col span={8}>
            <ProFormSelect
              name="return_reason"
              label={t('app.kuaizhizao.purchaseReturn.returnReason')}
              placeholder={t('app.kuaizhizao.purchaseReturn.selectReturnReason')}
              options={returnReasonOptions}
              fieldProps={{ showSearch: true, allowClear: true, loading: dictOptionsLoading }}
            />
          </Col>
          <Col span={8}>
            <ProFormSelect
              name="return_type"
              label={t('app.kuaizhizao.purchaseReturn.returnType')}
              placeholder={t('app.kuaizhizao.purchaseReturn.selectReturnType')}
              options={returnTypeOptions}
              fieldProps={{ showSearch: true, allowClear: true, loading: dictOptionsLoading }}
            />
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={8}>
            <ProFormSelect
              name="shipping_method"
              label={t('app.kuaizhizao.purchaseReturn.shippingMethod')}
              placeholder={t('app.kuaizhizao.purchaseReturn.selectShippingMethod')}
              options={shippingMethodOptions}
              fieldProps={{ showSearch: true, allowClear: true, loading: dictOptionsLoading }}
            />
          </Col>
          <CustomFieldsFormSection
            customFields={purchaseReturnFormCustomFields}
            customFieldValues={purchaseReturnFormCustomFieldValues}
            gridColumns={3}
            embedInParentRow
          />
        </Row>

        <Row gutter={16}>
          <Col span={8}>
            <ProFormSelect
              name="replenish"
              label={t('app.kuaizhizao.purchaseReturn.replenish')}
              tooltip={t('app.kuaizhizao.purchaseReturn.replenishHint')}
              options={[
                { label: t('common.no'), value: false },
                { label: t('common.yes'), value: true },
              ]}
              initialValue={false}
              rules={[{ required: true, message: t('app.kuaizhizao.purchaseReturn.replenishRequired') }]}
            />
          </Col>
        </Row>

        <DocumentDetailTableStyles />
        <UniTableDetail
          name="items"
          title={t('app.kuaizhizao.purchaseReturn.itemsTitle')}
          required
          requiredMessage={t('app.kuaizhizao.purchaseReturn.itemsRequired')}
          headerExtra={(
            <Space size={8}>
              <Button
                type="default"
                icon={<ImportOutlined />}
                onClick={() => setImportModalVisible(true)}
              >
                {t('common.importDetail')}
              </Button>
              <Button
                type="default"
                icon={<PlusOutlined />}
                onClick={() => {
                  const items = [...(formRef.current?.getFieldValue('items') ?? [])];
                  items.push({ return_quantity: 1, unit_price: 0 });
                  formRef.current?.setFieldsValue({ items });
                }}
              >
                {t('common.addDetail')}
              </Button>
              <Button
                type="default"
                icon={<AppstoreAddOutlined />}
                onClick={() => setMaterialPickerOpen(true)}
              >
                {t('app.kuaizhizao.common.materialBatchSelect')}
              </Button>
            </Space>
          )}
          columns={formItemColumns}
          disabledAdd
          initialValue={{ return_quantity: 1, unit_price: 0 }}
          tableProps={DOCUMENT_DETAIL_TABLE_PROPS}
        />

        <ProFormTextArea name="notes" label={t('common.remark')} placeholder={t('app.kuaizhizao.purchaseReturn.notesPlaceholder')} fieldProps={{ rows: 3 }} />
        <DocumentAttachmentsField category="purchase_return_attachments" />
    </>
  );

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
                  onClick={leavePurchaseReturnFormPage}
                />
                <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
                  {isCreatePage
                    ? t('app.kuaizhizao.purchaseReturn.createTitle')
                    : t('app.kuaizhizao.purchaseReturn.editTitle')}
                </Typography.Title>
              </Space>
              <DocumentFormPageHeaderActions
                onCancel={leavePurchaseReturnFormPage}
                onSaveDraft={submitPurchaseReturnForm}
                onPrimarySubmit={submitPurchaseReturnForm}
                isCreatePage={isCreatePage}
                showSaveDraft={false}
                canSubmitAfterSave={false}
                showCommitSubmit={purchaseReturnFormCanCommit}
                onCommitSubmit={triggerPurchaseReturnCommit}
              />
            </>
          }
        >
          <Spin spinning={formPageLoading}>
            <ProForm formRef={formRef} layout="vertical" submitter={false} onFinish={onFinish}>
              {renderPurchaseReturnFormFields()}
            </ProForm>
          </Spin>
        </DocumentFormPageLayout>
        <UniMaterialBatchPicker
          open={materialPickerOpen}
          onCancel={() => setMaterialPickerOpen(false)}
          onConfirm={appendItemsFromMaterials}
        />
        <Suspense fallback={null}>
          <LazyUniImport
            visible={importModalVisible}
            onCancel={() => setImportModalVisible(false)}
            onConfirm={handleImport}
            title={t('app.kuaizhizao.purchaseReturn.importTitle')}
            headers={[
              t('app.kuaizhizao.purchaseReturn.import.materialCode'),
              t('common.unit'),
              t('app.kuaizhizao.purchaseReturn.import.returnQuantity'),
              t('app.kuaizhizao.purchaseReturn.import.unitPrice'),
              t('app.kuaizhizao.purchaseReturn.import.batchNumber'),
              t('app.kuaizhizao.purchaseReturn.import.location'),
              t('common.remark'),
            ]}
            exampleRow={[
              'MAT001',
              pickImportExampleValue(
                purchaseReturnLineUnitOptions,
                t('app.kuaizhizao.purchaseReturn.defaultUnit'),
              ),
              '10',
              '99.5',
              'B001',
              'A-01',
              '',
            ]}
            columnOptions={purchaseReturnLineImportColumnOptions}
          />
        </Suspense>
      </>
    );
  }

  return (
    <>
      <ListPageTemplate statCards={statCards}>
        <UniTable<PurchaseReturn>
          headerTitle={t('app.kuaizhizao.purchaseReturn.title')}
          columnPersistenceId={PURCHASE_RETURN_LIST_PERSISTENCE_ID}
          actionRef={actionRef}
          viewTypes={['table', 'detailTable', 'help']}
          defaultViewType={viewTypeState === 'help' ? 'table' : viewTypeState}
          onViewTypeChange={(v) => {
            dataViewModeRef.current = resolveDetailTableViewMode(v as 'table' | 'detailTable' | 'help');
            setViewTypeState(v as 'table' | 'detailTable' | 'help');
            setSelectedRowKeys([]);
            setTimeout(() => actionRef.current?.reload(), 0);
          }}
          detailTableColumns={detailTableColumns}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.purchaseReturn)}
          rowKey={dataViewMode === 'detail' ? '_rowKey' : 'id'}
          columns={columns}
          showAdvancedSearch={true}
          skipFuzzyPinyinClientFilter
          pinnedTabsField={LIST_LIFECYCLE_STAGE_FIELD}
          pinnedTabsValueEnum={purchaseReturnLifecycleValueEnum}
          showCreateButton={false}
          createButtonText={createButtonLabel}
          onCreate={handleCreate}
          showImportButton={purchaseReturnPerms.canCreate}
          onImport={handleListImport}
          importHeaders={purchaseReturnListImportTemplate.importHeaders}
          importExampleRow={purchaseReturnListImportTemplate.importExampleRow}
          importColumnOptions={purchaseReturnListImportTemplate.importColumnOptions}
          importFieldMap={purchaseReturnListImportTemplate.importHeaderMap}
          toolBarRender={() => [
            <UniPullCreateToolbar
              key="purchase-return-pull-create"
              compactKey="purchase-return-pull-create"
              createIcon={<PlusOutlined />}
              createLabel={createButtonLabel}
              onCreate={handleCreate}
              menuItems={[
                ...buildKuaizhizaoPullCreateMenuItems(t, [
                  {
                    key: 'pull-from-purchase-receipt',
                    actionKey: 'purchase_return.pull_from_purchase_receipt',
                    onClick: pullFromPurchaseReceiptQuery.openModal,
                  },
                  {
                    key: 'pull-from-purchase-order',
                    actionKey: 'purchase_return.pull_from_purchase_order',
                    onClick: pullFromPurchaseOrderQuery.openModal,
                  },
                  {
                    key: 'pull-from-incoming-inspection',
                    actionKey: 'purchase_return.pull_from_incoming_inspection',
                    onClick: pullFromIncomingInspectionQuery.openModal,
                  },
                ]),
                { type: 'divider', key: 'copy-selected-divider' },
                {
                  key: 'copy-selected',
                  label: t('app.kuaizhizao.purchaseReturn.copySelectedCreate'),
                  disabled: selectedReturnsForBatch.length !== 1,
                  onClick: () => void handleCopySelectedPurchaseReturn(),
                },
              ]}
            />,
            ...(viewTypeState === 'detailTable'
              ? []
              : [
                  <UniBatchMenuButton
                    key="purchase-return-submit"
                    selectedRowKeys={selectedRowKeys}
                    menuItems={purchaseReturnToolbarAuditMenus.submitItems}
                    buttonText={t('common.submit')}
                  />,
                  <UniBatchMenuButton
                    key="purchase-return-audit"
                    selectedRowKeys={selectedRowKeys}
                    menuItems={purchaseReturnToolbarAuditMenus.auditItems}
                    buttonText={t('components.uniAction.audit')}
                  />,
                ]),
          ]}
          request={async (params, sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
            try {
              const apiParams = resolvePurchaseReturnListApiParams(
                params,
                sort,
                searchFormValues,
              ) as PurchaseReturnListParams;
              const response = await warehouseApi.purchaseReturn.list(apiParams);
              const list = response?.data ?? [];
              const enriched = meta?.purpose === 'prefetch'
                ? list
                : await enrichPurchaseReturnRecordsWithCustomFields(list);
              // 行缓存唯一真源：onTableDataChange（prefetch 会走本 request，禁止在此覆盖）
              if (dataViewModeRef.current === 'order') {
                return {
                  data: enriched,
                  success: true,
                  total: response?.total ?? enriched.length,
                };
              }
              const flatRows = flattenDocumentDetailRows<PurchaseReturn, PurchaseReturnItem>({
                headers: enriched,
                getHeaderId: (h) => h.id,
                getItems: (h) => h.items,
                buildRowKey: (h, item, index) =>
                  item?.id
                    ? `return-${h.id}-item-${item.id}`
                    : `return-${h.id}-idx-${index}`,
                mapItemRow: (h, item) => ({
                  ...item,
                  return_id: h.id ?? 0,
                  return_code: h.return_code,
                  supplier_name: h.supplier_name,
                  purchase_receipt_code: h.purchase_receipt_code,
                  purchase_order_code: h.purchase_order_code,
                  warehouse_name: h.warehouse_name,
                  return_time: h.return_time,
                  status: h.status,
                  review_status: h.review_status,
                  lifecycle: h.lifecycle,
                  capabilities: h.capabilities,
                  audit: h.audit,
                }),
                mapEmptyHeaderRow: (h) => ({
                  return_id: h.id ?? 0,
                  return_code: h.return_code,
                  supplier_name: h.supplier_name,
                  purchase_receipt_code: h.purchase_receipt_code,
                  purchase_order_code: h.purchase_order_code,
                  warehouse_name: h.warehouse_name,
                  return_time: h.return_time,
                  status: h.status,
                  review_status: h.review_status,
                  lifecycle: h.lifecycle,
                  capabilities: h.capabilities,
                  audit: h.audit,
                  material_code: '-',
                  material_name: '-',
                  return_quantity: 0,
                  unit_price: 0,
                  total_amount: 0,
                }),
              }) as PurchaseReturnItemRow[];
              return {
                data: flatRows,
                success: true,
                total: response?.total ?? enriched.length,
              };
            } catch {
              messageApi.error(t('app.kuaizhizao.purchaseReturn.listFailed'));
              return {
                data: [],
                success: false,
                total: 0,
              };
            }
          }}
          enableRowSelection={viewTypeState !== 'detailTable'}
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          onTableDataChange={(rows) => {
            if (dataViewModeRef.current === 'order') {
              tableRowsRef.current = rows as PurchaseReturn[];
            }
          }}
          rowSelectionGetCheckboxProps={(record) => ({
            disabled: !isPurchaseReturnRowSelectable(record),
          })}
          showDeleteButton={viewTypeState !== 'detailTable'}
          deleteButtonText={t('common.delete')}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) => t('app.kuaizhizao.purchaseReturn.confirmBatchDelete', { count })}
          toolBarActionsAfterDelete={[]}
          toolBarActionsAfterBatch={[
            <UniCapabilityBatchButton
              key="purchase-return-confirm"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedReturnsForBatch}
              capabilityKey="confirm"
              permAllowed={purchaseReturnPerms.canAction?.('execute') ?? false}
              batchAllowed={purchaseReturnBatchConfirmAllowed}
              onRun={(id) => confirmPurchaseReturnWithValidation(Number(id))}
              notAllowedMessage={t('app.kuaizhizao.purchaseReturn.batchConfirmPartial', { count: 1 })}
              onSuccess={() => {
                setSelectedRowKeys([]);
                invalidatePurchaseReturnStatistics();
                invalidateMenuBadgeCounts();
    actionRef.current?.reload();
              }}
              requireConfirm
              labels={{
                single: t('app.kuaizhizao.purchaseReturn.confirmReturn'),
                batch: t('app.kuaizhizao.purchaseReturn.batchConfirm'),
                singleConfirmTitle: t('app.kuaizhizao.purchaseReturn.confirmTitle'),
              }}
              icon={<CheckCircleOutlined />}
              size="medium"
              color="green"
              variant="solid"
            />,
            <UniCapabilityBatchButton
              key="purchase-return-withdraw"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedReturnsForBatch}
              capabilityKey="withdraw"
              permAllowed={purchaseReturnPerms.canAction?.('revoke') ?? false}
              batchAllowed={purchaseReturnBatchWithdrawAllowed}
              onRun={(id) => warehouseApi.purchaseReturn.withdraw(String(id))}
              notAllowedMessage={t('app.kuaizhizao.purchaseReturn.batchWithdrawPartial', { count: 1 })}
              onSuccess={() => {
                setSelectedRowKeys([]);
                invalidatePurchaseReturnStatistics();
                invalidateMenuBadgeCounts();
    actionRef.current?.reload();
              }}
              requireConfirm
              labels={{
                single: t('app.kuaizhizao.purchaseReturn.withdrawConfirm'),
                batch: t('app.kuaizhizao.purchaseReturn.batchWithdraw'),
              }}
              icon={<EditOutlined />}
              size="medium"
              color="orange"
              variant="solid"
            />,
          ]}
        />
      </ListPageTemplate>



      <UniPullQueryModal<PurchaseReturnPullLine>
        pullQuery={pullFromPurchaseOrderQuery.pullQuery}
        open={pullFromPurchaseOrderQuery.open}
        title={pullFromPurchaseOrderAction.label}
        onCancel={pullFromPurchaseOrderQuery.closeModal}
        onOk={pullFromPurchaseOrderQuery.handleConfirm}
        rowKey="id"
        columns={pullPurchaseOrderColumns}
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
        searchPlaceholder={t('app.kuaizhizao.purchaseReturn.pull.searchPlaceholder')}
        filterExtra={(
          <>
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.purchaseReturn.pull.sourceDocPlaceholder')}
              style={{ width: 220, flexShrink: 0 }}
              value={pullSourceOrderId}
              options={pullSourceOrderOptions}
              onChange={(value) => {
                const nextId = Number(value);
                const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
                pullSourceOrderIdRef.current = next;
                setPullSourceOrderId(next);
                pullFromPurchaseOrderQuery.handleSelectedRowKeysChange([], []);
                pullFromPurchaseOrderQuery.handleSearchApply(pullFromPurchaseOrderQuery.appliedKeyword);
              }}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.purchaseReturn.pull.batchWarehousePlaceholder')}
              style={{ width: 180, flexShrink: 0 }}
              value={poPullBatchWarehouseId}
              options={poPullWarehouseOptions}
              onChange={(value) => {
                if (value == null) {
                  setPoPullBatchWarehouseId(undefined);
                  return;
                }
                const nextId = Number(value);
                if (Number.isFinite(nextId) && nextId > 0) {
                  applyPoPullBatchWarehouse(nextId);
                }
              }}
            />
          </>
        )}
        getRowLabel={(row) =>
          [row.order_code, row.material_code].filter(Boolean).join(' ')
        }
        page={pullFromPurchaseOrderQuery.page}
        pageSize={pullFromPurchaseOrderQuery.pageSize}
        total={pullFromPurchaseOrderQuery.total}
        onPageChange={pullFromPurchaseOrderQuery.handlePageChange}
        scopeOptions={pullFromPurchaseOrderQuery.scopeOptions}
        scope={pullFromPurchaseOrderQuery.scope}
        onScopeChange={pullFromPurchaseOrderQuery.handleScopeChange}
        okText={t('app.kuaizhizao.purchaseReturn.pull.ok')}
        footerHint={t('app.kuaizhizao.purchaseReturn.pull.warehouseHint')}
        tableScroll={{ x: 1304, y: 360 }}
      />

      <UniPullQueryModal<PurchaseReceiptReturnPullLine>
        pullQuery={pullFromPurchaseReceiptQuery.pullQuery}
        open={pullFromPurchaseReceiptQuery.open}
        title={pullFromPurchaseReceiptAction.label}
        onCancel={pullFromPurchaseReceiptQuery.closeModal}
        onOk={pullFromPurchaseReceiptQuery.handleConfirm}
        rowKey="id"
        columns={pullPurchaseReceiptColumns}
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
        searchPlaceholder={t('app.kuaizhizao.purchaseReturn.pull.searchPlaceholder')}
        filterExtra={(
          <>
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.purchaseReturn.pull.receiptSourceDocPlaceholder')}
              style={{ width: 220, flexShrink: 0 }}
              value={pullSourceReceiptId}
              options={pullSourceReceiptOptions}
              onChange={(value) => {
                const nextId = Number(value);
                const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
                pullSourceReceiptIdRef.current = next;
                setPullSourceReceiptId(next);
                pullFromPurchaseReceiptQuery.handleSelectedRowKeysChange([], []);
                pullFromPurchaseReceiptQuery.handleSearchApply(pullFromPurchaseReceiptQuery.appliedKeyword);
              }}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.purchaseReturn.pull.batchWarehousePlaceholder')}
              style={{ width: 180, flexShrink: 0 }}
              value={prPullBatchWarehouseId}
              options={poPullWarehouseOptions}
              onChange={(value) => {
                if (value == null) {
                  setPrPullBatchWarehouseId(undefined);
                  return;
                }
                const nextId = Number(value);
                if (Number.isFinite(nextId) && nextId > 0) {
                  applyPrPullBatchWarehouse(nextId);
                }
              }}
            />
          </>
        )}
        getRowLabel={(row) =>
          [row.receipt_code, row.material_code].filter(Boolean).join(' ')
        }
        page={pullFromPurchaseReceiptQuery.page}
        pageSize={pullFromPurchaseReceiptQuery.pageSize}
        total={pullFromPurchaseReceiptQuery.total}
        onPageChange={pullFromPurchaseReceiptQuery.handlePageChange}
        scopeOptions={pullFromPurchaseReceiptQuery.scopeOptions}
        scope={pullFromPurchaseReceiptQuery.scope}
        onScopeChange={pullFromPurchaseReceiptQuery.handleScopeChange}
        okText={t('app.kuaizhizao.purchaseReturn.pull.ok')}
        footerHint={t('app.kuaizhizao.purchaseReturn.pull.warehouseHint')}
        tableScroll={{ x: 1304, y: 360 }}
      />

      <UniPullQueryModal<PullIncomingInspectionCandidate>
        open={pullFromIncomingInspectionQuery.open}
        title={pullFromIncomingInspectionAction.label}
        onCancel={pullFromIncomingInspectionQuery.closeModal}
        onOk={pullFromIncomingInspectionQuery.handleConfirm}
        rowKey="id"
        columns={pullIncomingInspectionColumns}
        dataSource={pullFromIncomingInspectionQuery.dataSource}
        loading={pullFromIncomingInspectionQuery.loading}
        confirmLoading={pullFromIncomingInspectionQuery.confirmLoading}
        selectionType={pullFromIncomingInspectionQuery.selectionType}
        selectedRowKeys={pullFromIncomingInspectionQuery.selectedRowKeys}
        selectedRows={pullFromIncomingInspectionQuery.selectedRows}
        onSelectedRowKeysChange={pullFromIncomingInspectionQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromIncomingInspectionQuery.isRowDisabled}
        searchDraft={pullFromIncomingInspectionQuery.searchDraft}
        onSearchDraftChange={pullFromIncomingInspectionQuery.setSearchDraft}
        onSearchApply={pullFromIncomingInspectionQuery.handleSearchApply}
        onSearchClear={pullFromIncomingInspectionQuery.handleSearchClear}
        appliedKeyword={pullFromIncomingInspectionQuery.appliedKeyword}
        searchPlaceholder={t('app.kuaizhizao.purchaseReturn.pull.searchPlaceholder')}
        getRowLabel={(row) => [row.inspection_code, row.material_name].filter(Boolean).join(' ')}
        page={pullFromIncomingInspectionQuery.page}
        pageSize={pullFromIncomingInspectionQuery.pageSize}
        total={pullFromIncomingInspectionQuery.total}
        onPageChange={pullFromIncomingInspectionQuery.handlePageChange}
        scopeOptions={pullFromIncomingInspectionQuery.scopeOptions}
        scope={pullFromIncomingInspectionQuery.scope}
        onScopeChange={pullFromIncomingInspectionQuery.handleScopeChange}
        okText={t('app.kuaizhizao.purchaseReturn.pull.ok')}
      />

      <UniMaterialBatchPicker
        open={materialPickerOpen}
        onCancel={() => setMaterialPickerOpen(false)}
        onConfirm={appendItemsFromMaterials}
      />
      <DetailDrawerTemplate
        title={t('app.kuaizhizao.purchaseReturn.detailTitle', {
          suffix: returnDetail?.return_code ? ` - ${returnDetail.return_code}` : '',
        })}
        open={detailDrawerVisible}
        zIndex={purchaseReturnDetailDrawerZIndex}
        onClose={() => {
          setDetailDrawerVisible(false);
          setReturnDetail(null);
          resetPurchaseReturnDetailFieldValues();
        }}
        size={DRAWER_CONFIG.HALF_WIDTH}
        extra={
          returnDetail ? (
            <Space size="small">
              <UniWorkflowActions {...rowActionKind('skip')}
                record={returnDetail}
                entityName={t('app.kuaizhizao.purchaseReturn.entityName')}
                entityType="purchase_return"
                auditNodeKey="purchase_return"
                unifiedAudit
                resourcePrefix={PURCHASE_RETURN_RESOURCE}
                statusField="status"
                reviewStatusField="review_status"
                draftStatuses={PR_WORKFLOW_DRAFT_STATUSES}
                pendingStatuses={PR_WORKFLOW_PENDING_STATUSES}
                approvedStatuses={PR_WORKFLOW_APPROVED_STATUSES}
                rejectedStatuses={PR_WORKFLOW_REJECTED_STATUSES}
                onSuccess={() => { void handlePurchaseReturnAuditSuccess(); }}
                confirmMessages={{
                  submit: isManualAuditEnabled(returnDetail.audit)
                    ? t('app.kuaizhizao.purchaseReturn.submitConfirmAudit')
                    : t('app.kuaizhizao.purchaseReturn.submitConfirmAuto'),
                }}
              />
              <DetailDrawerActions
                items={[
                  {
                    key: 'edit',
                    visible: returnDetail.capabilities?.update?.allowed === true && purchaseReturnPerms.canUpdate,
                    render: () => (
                      <Button {...rowActionKind('update')} onClick={() => void handleEdit(returnDetail)}>
                        {t('common.edit')}
                      </Button>
                    ),
                  },
                  {
                    key: 'refund',
                    visible: isPurchaseReturnRefundEligible(returnDetail) && paymentRefundPerms.canCreate,
                    render: () => (
                      <Button
                        {...rowActionCreateRefund('create')}
                        onClick={() => void handleCreateRefund(returnDetail)}
                      />
                    ),
                  },
                ]}
              />
            </Space>
          ) : null
        }
        collaborationTitleSuffix={
          purchaseReturnLifecycle?.nextStepSuggestions?.length ? (
            <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
              {t('common.next')}：
              {purchaseReturnLifecycle.nextStepSuggestions.join(t('components.uniLifecycle.nextStepSeparator'))}
            </Typography.Text>
          ) : undefined
        }
        collaborationAuditRecord={returnDetail}
        basic={
          returnDetail ? (
            <>
              <Descriptions
                column={3}
                size="small"
                items={timeconfigBasicItems0}
              />
              {hasCustomFieldsDetailContent(purchaseReturnListCustomFields, purchaseReturnDetailCustomFieldValues) ? (
                <div style={{ marginTop: 16 }}>
                  <CustomFieldsDetailSection
                    customFields={purchaseReturnListCustomFields}
                    customFieldValues={purchaseReturnDetailCustomFieldValues}
                  />
                </div>
              ) : null}
              <Descriptions
                column={3}
                size="small"
                style={{ marginTop: 16 }}
                items={timeconfigBasicItems1}
              />
              {returnDetail.status === '已退货' && returnDetail.finance_outcome ? (
                <DetailDrawerSection
                  title={t('app.kuaizhizao.purchaseReturn.financeOutcome.sectionTitle')}
                  style={{ marginTop: 16 }}
                >
                  {returnDetail.finance_outcome.no_blue_payable ? (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 12 }}
                      title={t('app.kuaizhizao.purchaseReturn.financeOutcome.noBluePayableHint')}
                    />
                  ) : null}
                  {returnDetail.finance_outcome.auto_payable_skipped &&
                  !returnDetail.finance_outcome.red_payable_id ? (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 12 }}
                      title={
                        returnDetail.finance_outcome.auto_payable_skip_reason ||
                        t('app.kuaizhizao.purchaseReturn.financeOutcome.autoPayableSkippedTitle')
                      }
                      action={
                        payablePerms.canCreate ? (
                          <Button
                            size="small"
                            type="primary"
                            onClick={() => void handleGenerateRedPayable(returnDetail)}
                          >
                            {t('app.kuaizhizao.purchaseReturn.generateRedPayable')}
                          </Button>
                        ) : undefined
                      }
                    />
                  ) : null}
                  {returnDetail.finance_outcome.needs_payment_refund ? (
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginBottom: 12 }}
                      title={t('app.kuaizhizao.purchaseReturn.financeOutcome.refundAlertTitle')}
                      description={t('app.kuaizhizao.purchaseReturn.financeOutcome.refundAlertDesc', {
                        amount: returnDetail.finance_outcome.refund_remainder,
                      })}
                      action={
                        paymentRefundPerms.canCreate ? (
                          <Button
                            {...rowActionCreateRefund('create')}
                            size="small"
                            type="primary"
                            onClick={() => void handleCreateRefund(returnDetail)}
                          />
                        ) : undefined
                      }
                    />
                  ) : null}
                  <Descriptions
                    column={1}
                    size="small"
                    items={[
                      {
                        key: 'return_amount',
                        label: t('app.kuaizhizao.purchaseReturn.financeOutcome.returnAmount'),
                        children: returnDetail.finance_outcome.return_amount,
                      },
                      {
                        key: 'blue_offset',
                        label: t('app.kuaizhizao.purchaseReturn.financeOutcome.blueOffsetTotal'),
                        children: returnDetail.finance_outcome.blue_offset_total,
                      },
                      ...(returnDetail.finance_outcome.red_payable_amount != null
                        ? [
                            {
                              key: 'red_payable_amount',
                              label: t('app.kuaizhizao.purchaseReturn.financeOutcome.redPayableAmount'),
                              children: returnDetail.finance_outcome.red_payable_amount,
                            },
                          ]
                        : []),
                      ...(returnDetail.finance_outcome.red_payable_code
                        ? [
                            {
                              key: 'red_payable',
                              label: t('app.kuaizhizao.purchaseReturn.financeOutcome.redPayable'),
                              children: returnDetail.finance_outcome.red_payable_id ? (
                                <Typography.Link
                                  onClick={() =>
                                    navigate(
                                      `/apps/kuaicaiwu/finance-management/payables/${returnDetail.finance_outcome!.red_payable_id}`,
                                    )
                                  }
                                >
                                  {returnDetail.finance_outcome.red_payable_code}
                                </Typography.Link>
                              ) : (
                                returnDetail.finance_outcome.red_payable_code
                              ),
                            },
                          ]
                        : []),
                      ...(returnDetail.finance_outcome.settlement_codes?.length
                        ? [
                            {
                              key: 'settlements',
                              label: t('app.kuaizhizao.purchaseReturn.financeOutcome.settlements'),
                              children: returnDetail.finance_outcome.settlement_codes.join('、'),
                            },
                          ]
                        : []),
                      ...(returnDetail.finance_outcome.blue_offsets?.length
                        ? [
                            {
                              key: 'blue_lines',
                              label: t('app.kuaizhizao.purchaseReturn.financeOutcome.bluePayables'),
                              children: (
                                <Space orientation="vertical" size={4}>
                                  {returnDetail.finance_outcome.blue_offsets.map((line) => (
                                    <span key={line.payable_id}>
                                      <Typography.Link
                                        onClick={() =>
                                          navigate(
                                            `/apps/kuaicaiwu/finance-management/payables/${line.payable_id}`,
                                          )
                                        }
                                      >
                                        {line.payable_code}
                                      </Typography.Link>
                                      {' '}
                                      {t('app.kuaizhizao.purchaseReturn.financeOutcome.offsetAmountLabel', {
                                        amount: line.offset_amount,
                                      })}
                                    </span>
                                  ))}
                                </Space>
                              ),
                            },
                          ]
                        : []),
                    ]}
                  />
                  <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                    {t('app.kuaizhizao.purchaseReturn.financeOutcome.paymentDocNote')}
                  </Typography.Paragraph>
                </DetailDrawerSection>
              ) : null}
            </>
          ) : null
        }
        collaboration={
          purchaseReturnLifecycle && (purchaseReturnLifecycle.mainStages ?? []).length > 0 ? (
            <UniLifecycleStepper
              steps={purchaseReturnLifecycle.mainStages ?? []}
              status={purchaseReturnLifecycle.status}
              showLabels
              nextStepSuggestions={purchaseReturnLifecycle.nextStepSuggestions}
              hideNextStepSuggestions={Boolean(purchaseReturnLifecycle.nextStepSuggestions?.length)}
            />
          ) : null
        }
        supplementary={
          showPurchaseReturnAttachments ? (
            <DocumentAttachmentsReadonly attachments={purchaseReturnAttachments} />
          ) : undefined
        }
        supplementaryTitle={
          showPurchaseReturnAttachments ? t('app.uniDetail.sectionAttachments') : undefined
        }
        supplementaryVisible={showPurchaseReturnAttachments}
        lines={
          returnDetail ? (
            returnDetail.items && returnDetail.items.length > 0 ? (
              <Table
                size="small"
                tableLayout="fixed"
                style={{ minWidth: PR_DETAIL_ITEMS_MIN_WIDTH }}
                columns={detailItemColumns}
                dataSource={returnDetail.items}
                pagination={false}
                rowKey="id"
                bordered
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.purchaseReturn.emptyItems')} />
            )
          ) : null
        }
        timeline={
          returnDetail ? (
            purchaseReturnTracking.data && !purchaseReturnTracking.loading ? (
              <DocumentTrackingTimelineBody data={purchaseReturnTracking.data} />
            ) : purchaseReturnTracking.error ? (
              <Typography.Text type="danger">{purchaseReturnTracking.error}</Typography.Text>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.shipmentNotice.noOperationRecords')} />
            )
          ) : null
        }
        traceDocument={
          returnDetail?.id != null
            ? {
                documentType: 'purchase_return',
                documentId: returnDetail.id,
                selfDocumentId: returnDetail.id,
                renderBriefActions: (doc) => (
                  <WarehouseTraceBriefPrimaryActions
                    doc={doc}
                    t={t}
                    navigate={navigate}
                    closeDrawer={() => {
                      setDetailDrawerVisible(false);
                      setReturnDetail(null);
                    }}
                  />
                ),
              }
            : undefined
        }
      />
    </>
  );
};

export default PurchaseReturnsPage;
