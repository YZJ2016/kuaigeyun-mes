/**
 * 采购订单管理页面
 *
 * 提供采购订单的创建、编辑、查看和审批功能
 *
 * @author RiverEdge Team
 * @date 2025-12-30
 */

import React, { useRef, useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react';
import { rowActionKind } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { useNavigate, useLocation } from 'react-router-dom';
import { inboundPoEntryPath } from '../../warehouse-management/inbound/inboundPaths';
import {
  PurchaseDepartmentFormField,
  resolvePurchaseDepartmentPayload,
  usePurchaseDepartmentOptions,
} from '../shared/PurchaseDepartmentFormField';
import { completeDeliveryNodeDocumentLinkIfPending } from '../../delivery-project/shared/deliveryNodeDocumentLink';
import { useLeaveFormTab } from '../../../../../components/uni-tabs/navigateClosingTab';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ActionType, ProColumns, ProForm, ProFormText, ProFormDatePicker, ProFormTextArea, ProFormSelect, ProFormDigit } from '@ant-design/pro-components';
import { App, Button, Space, Modal, Row, Col, Table, Empty, Form as AntForm, Input, InputNumber, List, Typography, theme, Spin, Select, Switch, Alert, Radio } from 'antd';
import { useTranslation } from 'react-i18next';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import {
  buildFactoryImportTemplate,
  resolveFactoryImportHeaderIndexMap,
} from '../../../../../utils/spreadsheetImportTemplate';
import {
  pickImportExampleValue,
} from '../../../../../utils/loadImportDictionaryValues';
import { useImportDictionaryOptions } from '../../../../../hooks/useImportDictionaryOptions';
import { useImportMaterialUnitOptions } from '../../../../master-data/hooks/useImportMaterialUnitOptions';
import {
  buildImportPriceTypeOptions,
  parseImportPriceType,
} from '../../sales-management/shared/salesPriceType';
import {
  buildDocumentDetailPartnerMaterialFormColumns,
  buildDocumentDetailSpecModelFormColumns,
  withMaterialLineFillMapping,
} from '../../sales-management/shared/materialLineFormDetail';
import { PlusOutlined, EditOutlined, DeleteOutlined, DownOutlined, FileTextOutlined, AppstoreAddOutlined, ArrowLeftOutlined, ImportOutlined, PrinterOutlined } from '@ant-design/icons';
import { getDataDictionaryByCode, getDictionaryItemList, type DictionaryItem } from '../../../../../services/dataDictionary';
import { mapSystemDictionaryItemOptions, resolveSystemDictionaryItemLabel } from '../../../../../utils/systemDictionaryI18n';
import { getFileDownloadUrl } from '../../../../../services/file';
import {
  mapAttachmentsToUploadList,
  normalizeDocumentAttachments,
} from '../../../utils/documentAttachments';
import {
  buildDocumentLineAttachmentsFormColumn,
  DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY,
} from '../../../components/documentLineAttachmentsColumns';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import { buildDocumentAttachmentsListColumn } from '../../../components/documentAttachmentsListColumn';
import { LineUnitPriceWithTrendTrigger } from '../../../components/partner-material-price-trend';
import { UniTable, readPersistedUniTableViewType, type UniTableRequestMeta} from '../../../../../components/uni-table';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import {
  UniTableStackedPrimaryCell,
  UniTableStackedLineBadge,
  UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
  UNI_TABLE_STACKED_BADGE_DATE_COLUMN_DEFAULTS,
  MaterialStackedCell,
} from '../../../../../components/uni-table/stackedPrimaryColumn';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../../sales-management/shared/documentLineMaterialsPreview';
import {
  UniAuditBatchMenuButton,
  UniCapabilityBatchButton,
  runCapabilityBatchLoop,
  type UniBatchMenuItem,
} from '../../../../../components/uni-batch';
import { SyncFreshnessBadge } from '../../../../../components/sync-from-source-modal/SyncFreshnessBadge';
import { SyncPushHubButton } from '../../../../../components/sync-push-hub';
import { useToolbarSyncPushFlags, TOOLBAR_SYNC_PUSH_FLAGS_QUERY_KEY } from '../../../../../hooks/useToolbarSyncPushFlags';
import { getBusinessConfig } from '../../../../../services/businessConfig';
import { buildPayableLedgerRecognitionOptions } from '../../../../../utils/documentLedgerRecognition';
import {
  applySupplierFormFields,
  resolveOrgPayableDefaultFromBusinessConfig,
} from '../shared/applySupplierFormFields';
import {
  DEFAULT_PURCHASE_PRICE_TYPE,
  DEFAULT_PURCHASE_TAX_RATE_PERCENT,
  purchaseFormPriceType,
  resolveSupplierDefaultTaxRatePercent,
} from '../shared/purchasePriceType';
import {
  PurchaseSupplierContactFormField,
  PurchaseSupplierPartnerDetailBridge,
  PurchaseSupplierPhoneFormField,
} from '../shared/PurchaseSupplierContactFormFields';
import {
  purchaseOrderFormLineToStored,
  purchaseOrderTaxRateToDecimal,
  readPurchaseOrderEnteredUnitPrice,
  purchaseOrderTaxRateToPercent,
  computePurchaseOrderHeaderAmountsForSave,
  resolvePurchaseOrderDisplayAmount,
  resolvePurchaseOrderLineAmounts,
} from '../shared/purchaseOrderAmounts';
import {
  partnerPaymentMethodSelectOptions,
  partnerSettlementTermsSelectOptions,
  parsePartnerDefaultPaymentMethodImport,
  parsePartnerSettlementTermsImport,
  buildPartnerDefaultPaymentMethodImportOptions,
  buildPartnerSettlementTermsImportOptions,
} from '../../../../master-data/utils/partner-static-labels';
import { renderExternalSyncPrimaryExtra } from '../../../../../components/external-sync-source/ExternalSyncSourceIcon';
import PurchaseOrderSyncFromSourceModal from './PurchaseOrderSyncFromSourceModal';
import PurchaseOrderDocumentPushPanel from './PurchaseOrderDocumentPushPanel';
import {
  ListPageTemplate,
  DetailDrawerActions,
  MODAL_CONFIG,
  DocumentFormPageLayout,
  DocumentFormPageHeaderActions,
  DetailDrawerSection,
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  type StatCard,
} from '../../../../../components/layout-templates';
import { setCustomPageTitle, removeCustomPageTitle } from '../../../../../utils/customPageTitle';
import { useSubmitShortcut } from '../../../../../hooks/useSubmitShortcut';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import {
  CustomFieldsFormSection,
} from '../../../../../components/custom-fields';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import {
  UniPullQueryModal,
  isPullOpenLineSelectable,
  isPullableScope,
  loadPullSourceReferenceOptions,
  PULL_SOURCE_REFERENCE,
  renderPullCapabilityTag,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import { buildUniPushMenuItems, buildUniPushToolbarDisabledReason, UniPushToolbarButton } from '../../../../../components/uni-push';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import {
  DOCUMENT_DETAIL_COL_WIDTH,
  DOCUMENT_DETAIL_DATE_PICKER_STYLE,
  DOCUMENT_DETAIL_NUM_COL,
  DOCUMENT_DETAIL_CONTROL_SIZE,
  DOCUMENT_DETAIL_TABLE_PROPS,
  DOCUMENT_DETAIL_TEXT_COL,
  DocumentDetailTableStyles,
  TaxRateBatchColumnTitle,
  TaxRateDetailCell,
} from '../../../components/document-detail-table/documentDetailTable';
import { DocumentAmountSummary } from '../../../components/document-amount-summary/DocumentAmountSummary';
import { SimpleSparkline } from '../../../../../components';
import CodeField from '../../../../../components/code-field';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import { PaymentMethodWithMixFormItems } from '../../../components/PaymentMethodWithMixFormItems';
import { validatePaymentMethodMix, isPartnerEmployeeAdvancePaymentMethod } from '../../../../master-data/utils/paymentMethodMix';
import { resolvePartnerAdvancePayeeName } from '../../../components/PartnerPaymentAdvancePayeeField';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import { UniMaterialBatchPicker } from '../../../../../components/uni-material-batch-picker';
import { UniWarehouseSelect } from '../../../../../components/uni-warehouse-select';
import { MaterialUnitSelect } from '../../../../../components/material-unit-select';
import {
  DocumentLineDualQuantityFormCell,
  DocumentLineUnitSelect,
} from '../../../../../components/quantity-with-unit';
import { pickDocumentLineDualQuantityFields } from '../../../../../utils/materialDualQuantity';
import { resolveMaterialScenarioUnit } from '../../../../../utils/materialScenarioUnit';
import type { Material } from '../../../../master-data/types/material';
import FeeDetailsTable from '../../../../../components/FeeDetailsTable';
import PriceTypeSwitch, { type PriceTypeValue } from '../../../../../components/price-type-switch/PriceTypeSwitch';
import { setFormPriceType } from '../../../../../utils/priceTypeSwitch';
import dayjs from 'dayjs';
import { formatBusinessDateOnly, formatDateTime, formatQuantity, todaySiteDateString, formatCurrencyAmount, formatCurrencyPrice } from '../../../../../utils/format';
import { quantizeNumericByPlaces } from '../../../../../services/businessConfig';
import { QuantityWithUnitDisplay } from '../../../../../components/quantity-with-unit';
import { extractProTableSort } from '../../../../../utils/tableQueryKey';
import { coerceFormDate, toApiDateString, formDateRangeFormItemProps } from '../../../../../utils/formDate';
import {
  listPurchaseOrders, getPurchaseOrder, createPurchaseOrder, updatePurchaseOrder,
  deletePurchaseOrder, approvePurchaseOrder, submitPurchaseOrder,
  withdrawPurchaseOrder,
  revokePurchaseOrder,
  pushPurchaseOrderToReceipt,
  pushPurchaseOrderToReceiptNotice, pushPurchaseOrderToReceiptNoticeFromPreview, pushPurchaseOrderToInvoice, pushPurchaseOrderToPrepayment, pushPurchaseOrderToPurchaseReturn,
  getPurchaseOrderStatistics,
  getPurchaseOrderSyncBinding,
  previewPushToReceiptNotice, previewPushToReceipt, previewPushToInvoice, previewPushToPrepayment,
  previewPushToPaymentApplication, pushPurchaseOrderToPaymentApplication, previewPushToPurchaseReturn,
  type DocumentPushPreview,
  type PurchaseInvoicePushMode,
  PurchaseOrder,
  PurchaseOrderItem,
  listPurchaseOrderSalesOrderPullOrders,
  listPurchaseOrderSalesOrderPullLines,
  type PurchaseOrderSalesOrderPullCandidate,
  type PurchaseOrderSalesOrderPullLine,
} from '../../../services/purchase';
import {
  listPurchaseRequisitionPurchaseOrderPullLines,
  pullPurchaseOrdersFromRequisitionItems,
  type PurchaseRequisitionPullLine,
} from '../../../services/purchase-requisition';
import {
  buildDocumentCreateDraftKey,
  clearDocumentFormDraft,
  getDocumentFormDraft,
} from '../../../../../utils/documentFormDraftCache';
import {
  continuePoHandoffQueueIfAny,
  handoffInquiryToPurchaseOrderCreate,
  handoffRequisitionToPurchaseOrderCreate,
  handoffSalesOrderToPurchaseOrderCreate,
  hydrateDocumentFlowCreateFormValues,
} from '../../../utils/documentFlowHandoff';
import {
  listPurchaseInquiries,
  listPurchaseInquiryPurchaseOrderPullLines,
  pullPurchaseOrdersFromInquiryItems,
  type PurchaseInquiryPurchasePullLine,
} from '../../../services/purchase-inquiry';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import {
  purchaseOrderCapabilityReasonMessage,
} from '../../../../../hooks/useDocumentCapabilities';
import { qualityApi } from '../../../services/quality-execution';
import LandingCostAllocationModal from './LandingCostAllocationModal';
import { formatApiErrorDetail } from '../../../../../services/api';
import {
  applyPurchaseDocumentLineMaterialPricing,
  repriceUnlockedPurchaseDocumentLineIfNeeded,
  resolvePurchaseDocumentMaterialLinesPricing,
} from '../../../../master-data/utils/resolve-partner-material-price';
import { markDocumentLineUnitPriceLocked } from '../../../utils/documentLinePriceLock';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { SupplierSelectDropdown } from '../../../../master-data/components/SupplierSelectDropdown';
import { searchUserDisplay, type User } from '../../../../../services/user';
import {
  referenceDisplayToIdOptions,
  searchReferenceDisplay,
} from '../../../../../utils/referenceDisplay';
import {
  KUAIZHIZAO_DOC_HOST,
  loadBankAccountFormOptions,
  loadMaterialFormReferenceList,
} from '../../../../../utils/documentFormReferenceLoad';

const LazyUniImport = lazy(() =>
  import('../../../../../components/uni-import').then((m) => ({ default: m.UniImport })),
);

import { getSessionCurrentUser } from '../../../../../utils/sessionCurrentUser';
import { displayItemsToUsers, normalizeUserDisplayName } from '../../../../../utils/userDisplay';
import {
  applyDocumentLineExclAmountEdit,
  documentLineExclMatchesDerived,
} from '../../../utils/documentLineAmounts';
import {
  DocumentStatus,
  ReviewStatusEnum,
  isDraftStatus,
  isAuditedStatus,
  isPendingReviewStatus,
  isRejectedStatus,
  isConfirmedStatus,
} from '../../../constants/documentStatus';
import { getPurchaseOrderLifecycle, buildPurchaseOrderLifecycleValueEnum, resolvePurchaseOrderListApiParams, isPurchaseOrderDeliveryOverdue } from '../../../utils/purchaseOrderLifecycle';
import { LIST_LIFECYCLE_STAGE_FIELD } from '../../../../../utils/listLifecycleStage';
import { PurchaseOrderAiCreateTrigger } from './components/PurchaseOrderAiCreateDrawer';
import {
  PurchaseOrderDetailDrawer,
  PURCHASE_ORDER_WORKFLOW_PROPS,
} from './components/PurchaseOrderDetailDrawer';
import { useKuaiaiEntryAvailable } from '../../../../kuaiai/hooks/useKuaiaiEntryAvailable';
import { UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import { ListUniLifecycleCell } from '../../sales-management/shared/ListUniLifecycleCell';
import { createListAuditPhaseColumn } from '../../sales-management/shared/listAuditPhaseColumn';
import { UNI_TABLE_PAYMENT_SETTLEMENT_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';
import {
  buildPurchaseOrderPaymentSettlementEnum,
  resolvePurchaseOrderPaymentSettlementDisplay,
} from './purchaseOrderListStatus';
import {
  alignProColumns,
  GLOBAL_DOC_DETAIL_TABLE_FIELD_RANK,
  SALES_DOC_LIST_FIELD_RANK,
} from '../../sales-management/shared/documentFieldAlignment';
import { OrderPaymentMilestonesFields } from '../../sales-management/shared/orderPaymentMilestonesFields';
import {
  DocumentPushProgressBar,
  DOCUMENT_PROGRESS_COLUMN_DEFAULTS,
  DETAIL_TABLE_PROGRESS_COLUMN_DEFAULTS,
  ratioToPushProgressPercent,
} from '../../sales-management/shared/DocumentPushProgressBar';
import { collectPurchaseOrderPushDocuments } from '../../sales-management/shared/pushProgress';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import type { SubStage } from '../../../../../components/uni-lifecycle/types';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { useDeferAfterPaint } from '../../../../../hooks/useDeferAfterPaint';
import { useRegisterAiContext } from '../../../../../hooks/useRegisterAiContext';
import { useNumericPrecision } from '../../../../../hooks/useNumericPrecision';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import {
  purchaseOrderBatchPushReceiptNoticeAllowed,
} from '../../../../../hooks/useDocumentCapabilities';
import { useKuaizhizaoPrintModal } from '../../../hooks/useKuaizhizaoPrintModal';
import { importInChunksViaPerItemCreate } from '../../../../../utils/chunkedBulkImport';
import { buildKuaizhizaoPullCreateMenuItems, resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import { warehouseApi as masterWarehouseApi } from '../../../../master-data/services/warehouse';
import {
  collectImportMaterialCodes,
  findMaterialByImportCode,
  normalizeImportMaterialCode,
  resolveMaterialsByCodesForImport,
} from '../../../../master-data/utils/materialImportResolve';
import { normalizeFormListItems } from '../../../../../utils/formListItems';
import { buildFutureDateShortcutFieldProps, FutureDatePicker } from '../../../../../utils/futureDatePickerShortcuts';
import { fetchAllListItems } from '../../../../../utils/fetchAllListPages';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import { getAntdModal } from '../../../../../utils/antdAppApis';
/** 与后端 DocumentStatus / ReviewStatus 及中文存量值对齐，供 UniWorkflowActions 识别 */
const PO_WORKFLOW_DRAFT_STATUSES = ['草稿', 'draft', 'DRAFT', DocumentStatus.DRAFT];
/** 仅匹配主状态「待审核」，勿包含 review 的 PENDING：新建草稿默认 review_status=PENDING，否则会误显「审核」按钮 */
const PO_WORKFLOW_PENDING_STATUSES = [
  '待审核',
  'pending_review',
  'PENDING_REVIEW',
  DocumentStatus.PENDING_REVIEW,
];
const PO_WORKFLOW_APPROVED_STATUSES = [
  '已审核',
  'audited',
  '审核通过',
  '已确认',
  DocumentStatus.AUDITED,
  DocumentStatus.CONFIRMED,
  ReviewStatusEnum.APPROVED,
];
const PO_WORKFLOW_REJECTED_STATUSES = [
  '已驳回',
  'rejected',
  'REJECTED',
  DocumentStatus.REJECTED,
  ReviewStatusEnum.REJECTED,
];

/** 归属采购员：与销售订单业务员字段一致，无匹配选项时用 buyer_name 回显 */
const PurchaseOrderBuyerField: React.FC<{ userList: User[]; loading: boolean }> = ({ userList, loading }) => {
  const { t } = useTranslation();
  const form = AntForm.useFormInstance();
  const buyerId = AntForm.useWatch('buyer_id', form);
  const buyerName = AntForm.useWatch('buyer_name', form);

  const options = useMemo(() => {
    const base = userList.map((u) => ({
      value: Number(u.id),
      label: normalizeUserDisplayName(u.full_name || u.username),
    }));
    const bid =
      buyerId != null && buyerId !== '' && Number.isFinite(Number(buyerId)) ? Number(buyerId) : NaN;
    if (Number.isFinite(bid) && !base.some((o) => o.value === bid)) {
      const label =
        normalizeUserDisplayName(buyerName) || t('app.kuaizhizao.quotation.userFallback', { id: bid });
      return [{ value: bid, label }, ...base];
    }
    return base;
  }, [userList, buyerId, buyerName, t]);

  return (
    <>
      <ProForm.Item
        name="buyer_id"
        label={t('app.kuaizhizao.purchaseOrder.form.buyer')}
        normalize={(v) =>
          v != null && v !== '' && Number.isFinite(Number(v)) ? Number(v) : undefined
        }
      >
        <UniDropdown
          placeholder={t('app.kuaizhizao.purchaseOrder.form.buyerPlaceholder')}
          showSearch
          allowClear
          loading={loading}
          style={{ width: '100%' }}
          options={options}
          onChange={(_val, opt: any) => {
            form.setFieldsValue({ buyer_name: opt?.label });
          }}
        />
      </ProForm.Item>
      <AntForm.Item name="buyer_name" hidden>
        <Input />
      </AntForm.Item>
    </>
  );
};

/** 采购明细行（订单 + 明细合并，用于明细表格平铺） */
type PurchaseOrderItemRow = PurchaseOrderItem & {
  _rowKey: string;
  purchase_order_id: number;
  order_code?: string;
  supplier_name?: string;
  buyer_name?: string;
  order_date?: string;
  delivery_date?: string;
  total_quantity?: number;
  total_amount?: number;
  net_amount?: number;
  tax_amount?: number;
  tax_rate?: number;
  status?: string;
  review_status?: string;
  receipt_progress?: number;
  downstream_push_progress?: number;
  downstream_receipt_notice_codes?: string[];
  downstream_purchase_receipt_codes?: string[];
};

/** 指标卡迷你图默认序列：模块级稳定引用，避免每次 render 新数组触发图表无限 update（G2 interval 报错） */
const PO_STAT_SPARKLINE_ARRIVAL = [60, 75, 80, 78, 85, 90, 88];
const PO_STAT_SPARKLINE_ANNUAL = [1000, 2000, 1500, 3000, 2500, 4000, 3500];
const PO_STAT_SPARKLINE_SUPPLIER = [92, 95, 88, 96, 94, 98, 95];
const PO_STAT_SPARKLINE_OVERDUE = [5, 8, 3, 12, 7, 15, 10];

function renderPurchaseOrderRowActions(nodes: React.ReactNode[], keyPrefix: string): React.ReactNode {
  return nodes;
}

// 使用从服务文件导入的接口
type PurchaseOrderDetail = PurchaseOrder;
// PurchaseOrderItem 已在导入中定义

type PullPurchaseRequisitionCandidate = PurchaseRequisitionPullLine;
type PullPurchaseInquiryCandidate = PurchaseInquiryPurchasePullLine;

type PushPreviewKind =
  | 'receipt_notice'
  | 'receipt'
  | 'invoice'
  | 'prepayment'
  | 'payment_application'
  | 'purchase_return'
  | 'incoming_inspection';

const defaultOrderItem = {
  material_id: undefined,
  material_code: '',
  material_name: '',
  material_spec: '',
  unit: '件',
  ordered_quantity: 1,
  unit_price: 0,
  tax_rate: 0,
  required_date: undefined,
};

/** 新建采购订单未填采购员时，默认当前登录用户（对齐销售订单业务员） */
function resolveDefaultPurchaseOrderBuyer(): {
  buyer_id?: number;
  buyer_name?: string;
} {
  const u = getSessionCurrentUser();
  const id = Number(u?.id);
  if (!Number.isFinite(id) || id <= 0) return {};
  const name = normalizeUserDisplayName(
    u?.full_name || u?.fullName || u?.username || u?.name,
  );
  return { buyer_id: id, buyer_name: name };
}

const ORDER_TYPE_FALLBACK_ITEMS: Pick<DictionaryItem, 'value' | 'label' | 'is_system_managed' | 'sort_order'>[] = [
  { value: '标准采购', label: '标准采购', is_system_managed: true, sort_order: 0 },
  { value: '框架协议', label: '框架协议', is_system_managed: true, sort_order: 1 },
];

const PURCHASE_ORDER_RESOURCE = 'kuaizhizao:purchase-order';

const PURCHASE_ORDER_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_purchase_orders';

const PURCHASE_ORDER_LIST_PATH = '/apps/kuaizhizao/purchase-management/purchase-orders';
const PURCHASE_ORDER_CREATE_PATH = `${PURCHASE_ORDER_LIST_PATH}/new`;
const purchaseOrderEditPath = (id: number) => `${PURCHASE_ORDER_LIST_PATH}/${id}/edit`;

const PurchaseOrdersPage: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { quantity: quantityDecimals, price: priceDecimals, amount: amountDecimals } = useNumericPrecision();
  const kuaiaiAvailable = useKuaiaiEntryAvailable();
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const purchaseOrderAuditEnabled = useAuditRequired('purchase_order', false);
  const purchaseOrderPerms = useResourcePermissions(PURCHASE_ORDER_RESOURCE);
  const toolbarSyncPush = useToolbarSyncPushFlags('purchase');
  const { data: businessConfig } = useQuery({
    queryKey: TOOLBAR_SYNC_PUSH_FLAGS_QUERY_KEY,
    queryFn: getBusinessConfig,
    staleTime: 60_000,
  });
  const requirePurchaseRequisition = Boolean(
    businessConfig?.parameters?.procurement?.require_purchase_requisition,
  );
  const payableLedgerRecognitionOptions = useMemo(
    () => buildPayableLedgerRecognitionOptions(t),
    [t],
  );
  const purchaseOrderPaymentMethodOptions = useMemo(() => partnerPaymentMethodSelectOptions(t), [t]);
  const purchaseOrderSettlementTermsOptions = useMemo(
    () => partnerSettlementTermsSelectOptions(t),
    [t],
  );
  const orgPayableRecognitionDefault = useMemo(
    () => resolveOrgPayableDefaultFromBusinessConfig(businessConfig),
    [businessConfig],
  );
  const purchaseOrderChangePerms = useResourcePermissions('kuaizhizao:purchase-order-change');
  const { token } = theme.useToken();
  const purchaseOrderDetailDrawerZIndex = token.zIndexPopupBase;
  const navigate = useNavigate();
  const location = useLocation();
  const isCreatePage = location.pathname.endsWith('/purchase-orders/new');
  const editRouteMatch = location.pathname.match(/\/purchase-orders\/(\d+)\/edit$/);
  const editRouteId = editRouteMatch ? Number(editRouteMatch[1]) : null;
  const isEditPage = editRouteId != null && Number.isFinite(editRouteId) && editRouteId > 0;
  const isFormPage = isCreatePage || isEditPage;
  const formPageInitializedRef = useRef(false);
  const documentFlowSubmitExtrasRef = useRef<Record<string, unknown> | null>(null);
  const purchaseOrderCreateDraftKeyRef = useRef<string | null>(null);
  const { message: messageApi } = App.useApp();
  const pullFromRequisitionAction = resolveKuaizhizaoDocumentAction(t, 'purchase_order.pull_from_requisition');
  const pullFromInquiryAction = resolveKuaizhizaoDocumentAction(t, 'purchase_order.pull_from_inquiry');
  const pullFromSalesOrderAction = resolveKuaizhizaoDocumentAction(t, 'purchase_order.pull_from_sales_order');
  const pushToReceiptNoticeAction = resolveKuaizhizaoDocumentAction(t, 'receipt_notice.pull_from_purchase_order');
  const pushToReceiptAction = resolveKuaizhizaoDocumentAction(t, 'purchase_receipt.pull_from_purchase_order');
  const pushToInvoiceAction = resolveKuaizhizaoDocumentAction(t, 'purchase_invoice.pull_from_purchase_order');
  const pushToPrepaymentAction = resolveKuaizhizaoDocumentAction(t, 'payment.pull_from_purchase_order');
  const pushToPurchaseReturnAction = resolveKuaizhizaoDocumentAction(t, 'purchase_return.pull_from_purchase_order');
  const pushToPurchaseOrderChangeAction = resolveKuaizhizaoDocumentAction(
    t,
    'purchase_order_change.pull_from_purchase_order',
  );
  const pushToIncomingInspectionAction = resolveKuaizhizaoDocumentAction(
    t,
    'incoming_inspection.pull_from_purchase_order',
  );
  const queryClient = useQueryClient();
  const actionRef = useRef<ActionType>(null);
  /** 列表当前页数据（唯一源：UniTable onTableDataChange，与表格展示一致） */
  const [tableOrders, setTableOrders] = useState<PurchaseOrder[]>([]);
  const purchaseOrderListPersistenceId =
    'apps.kuaizhizao.pages.purchase-management.purchase-orders-width-v7';
  const [viewTypeState, setViewTypeState] = useState<'table' | 'detailTable' | 'help'>(() =>
    readPersistedUniTableViewType(purchaseOrderListPersistenceId, 'table', [
      'table',
      'detailTable',
      'help',
    ]) as 'table' | 'detailTable' | 'help',
  );
  const dataViewMode = viewTypeState === 'table' ? 'order' : 'detail';
  const dataViewModeRef = useRef(dataViewMode);
  useEffect(() => {
    dataViewModeRef.current = dataViewMode;
  }, [dataViewMode]);
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();

  const materialUnitImport = useImportMaterialUnitOptions();
  const purchaseOrderImportDict = useImportDictionaryOptions(['CURRENCY', 'ORDER_TYPE']);
  const purchaseOrderLineUnitOptions = materialUnitImport.options;
  const purchaseOrderLineImportColumnOptions = useMemo(
    () => [undefined, undefined, purchaseOrderLineUnitOptions, undefined, undefined, undefined],
    [purchaseOrderLineUnitOptions],
  );
  const purchaseOrderImportTemplate = useMemo(
    () =>
      buildFactoryImportTemplate(
        t,
        [
          { field: 'code', labelKey: 'app.kuaizhizao.purchaseOrder.import.code', aliases: ['订单编号', '编号'] },
          {
            field: 'supplier',
            required: true,
            labelKey: 'app.kuaizhizao.purchaseOrder.import.supplierName',
            aliases: ['供应商', '供应商名称'],
          },
          {
            field: 'date',
            required: true,
            labelKey: 'app.kuaizhizao.purchaseOrder.import.orderDate',
            aliases: ['订单日期', '日期'],
          },
          {
            field: 'material',
            required: true,
            labelKey: 'app.kuaizhizao.purchaseOrder.import.materialCode',
            aliases: ['物料', '物料编号'],
          },
          { field: 'quantity', required: true, labelKey: 'common.quantity', aliases: ['数量'] },
          {
            field: 'unitPrice',
            required: true,
            labelKey: 'app.kuaizhizao.purchaseOrder.import.unitPrice',
            aliases: ['单价'],
          },
          { field: 'delivery', labelKey: 'app.kuaizhizao.purchaseOrder.import.deliveryDate', aliases: ['交货日期'] },
          { field: 'supplierContact', labelKey: 'app.kuaizhizao.purchaseOrder.import.supplierContact', aliases: ['供应商联系人'] },
          { field: 'supplierPhone', labelKey: 'app.kuaizhizao.purchaseOrder.import.supplierPhone', aliases: ['供应商电话'] },
          { field: 'orderType', labelKey: 'app.kuaizhizao.purchaseOrder.import.orderType', aliases: ['订单类型'] , options: purchaseOrderImportDict.ORDER_TYPE },
          { field: 'buyer', labelKey: 'app.kuaizhizao.purchaseOrder.import.buyer', aliases: ['采购员'] },
          { field: 'currency', labelKey: 'app.kuaizhizao.quotation.form.currency', aliases: ['币种'] , options: purchaseOrderImportDict.CURRENCY },
          { field: 'priceType', labelKey: 'app.kuaizhizao.salesOrder.priceType', aliases: ['价格类型'] , options: buildImportPriceTypeOptions(t) },
          { field: 'notes', labelKey: 'common.remark', aliases: ['备注'] },
        ],
        [
          t('app.kuaizhizao.purchaseOrder.importExample.code'),
          t('app.kuaizhizao.purchaseOrder.importExample.supplierName'),
          t('app.kuaizhizao.purchaseOrder.importExample.orderDate'),
          t('app.kuaizhizao.purchaseOrder.importExample.materialCode'),
          t('app.kuaizhizao.purchaseOrder.importExample.quantity'),
          t('app.kuaizhizao.purchaseOrder.importExample.unitPrice'),
          t('app.kuaizhizao.purchaseOrder.importExample.deliveryDate'),
          '',
          '',
          pickImportExampleValue(purchaseOrderImportDict.ORDER_TYPE, ''),
          '',
          pickImportExampleValue(purchaseOrderImportDict.CURRENCY, 'CNY'),
          pickImportExampleValue(buildImportPriceTypeOptions(t), t('app.kuaizhizao.salesContract.priceTypeTaxInclusive')),
          '',
        ],
      ),
    [t, i18n.language, purchaseOrderImportDict],
  );

  const tableSearchFormRef = useRef<any>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [highlightDeliveryOverdue, setHighlightDeliveryOverdue] = useState(false);

  const selectedOrdersForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => tableOrders.find((row) => String(row.id) === String(key)))
        .filter((row): row is PurchaseOrder => row != null),
    [selectedRowKeys, tableOrders],
  );

  const purchaseOrderHighlightOverdueToolbar = useMemo(
    () => (
      <Space key="highlight-overdue-switch" align="center">
        <Switch checked={highlightDeliveryOverdue} onChange={setHighlightDeliveryOverdue} />
        <span className="uni-table-toolbar-plain-label">
          {t('app.kuaizhizao.purchaseOrder.highlightOverdue')}
        </span>
      </Space>
    ),
    [highlightDeliveryOverdue, t],
  );

  const purchaseOrderAuditBatchHandlers = useMemo(
    () => ({
      submit: (id: number) => submitPurchaseOrder(id),
      withdraw: (id: number) => withdrawPurchaseOrder(id),
      approve: (id: number) => approvePurchaseOrder(id, { approved: true, review_remarks: '' }),
      revoke: (id: number) => revokePurchaseOrder(id),
    }),
    [],
  );

  const handlePurchaseOrderAuditBatchSuccess = useCallback(() => {
    setSelectedRowKeys([]);
    invalidateMenuBadgeCounts();
    actionRef.current?.reload();
  }, [invalidateMenuBadgeCounts]);

  const purchaseOrderBatchPushReceiptNoticePermAllowed =
    purchaseOrderPerms.canAction?.('execute') ?? false;

  const purchaseOrderBatchExtraMenuItems = useMemo<UniBatchMenuItem[]>(
    () => [
      {
        key: 'purchase-order-push-receipt-notice',
        label: t('app.kuaizhizao.purchaseOrder.batchPushNotice'),
        icon: <FileTextOutlined />,
        disabled: !purchaseOrderBatchPushReceiptNoticeAllowed(
          selectedOrdersForBatch,
          purchaseOrderBatchPushReceiptNoticePermAllowed,
        ),
        onClick: async (keys) => {
          await runCapabilityBatchLoop({
            keys,
            records: selectedOrdersForBatch,
            capabilityKey: 'push_receipt_notice',
            permAllowed: purchaseOrderBatchPushReceiptNoticePermAllowed,
            notAllowedMessage: t('app.kuaizhizao.purchaseOrder.batchPushNoticePartial', {
              count: 1,
            }),
            onRun: (id) => pushPurchaseOrderToReceiptNoticeFromPreview(id),
            message: messageApi,
            t,
            onSuccess: handlePurchaseOrderAuditBatchSuccess,
          });
        },
      },
    ],
    [
      handlePurchaseOrderAuditBatchSuccess,
      messageApi,
      purchaseOrderBatchPushReceiptNoticePermAllowed,
      selectedOrdersForBatch,
      t,
    ],
  );

  const leavePurchaseOrderFormPage = useLeaveFormTab(PURCHASE_ORDER_LIST_PATH);
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false);
  const [importModalVisible, setImportModalVisible] = useState(false);
  /** 未税金额正在编辑的行：失焦时反算单价（index/value 用 ref，避免 Form.Item shouldUpdate 闭包过期） */
  const [editingExcl, setEditingExcl] = useState<{ index: number; value: number | null } | null>(null);
  const editingExclIndexRef = useRef<number | null>(null);
  const editingExclValueRef = useRef<number | null>(null);

  // Modal 相关状态
  const [modalVisible, setModalVisible] = useState(false);
  const [isEdit, setIsEdit] = useState(false);
  const [currentOrder, setCurrentOrder] = useState<PurchaseOrder | null>(null);
  const formRef = useRef<any>(null);
  /** 上一次订单头要求到货日，用于改表头时同步曾跟随表头的明细行 */
  const lastHeaderDeliveryRef = useRef<ReturnType<typeof dayjs> | null>(null);

  const applyHeaderDeliveryToItemLines = useCallback((delivery: unknown) => {
    const coerced = coerceFormDate(delivery);
    if (coerced == null) return;
    const prevHeader = lastHeaderDeliveryRef.current;
    const items = normalizeFormListItems<any>(formRef.current?.getFieldValue('items'));
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
      formRef.current?.setFieldsValue({ items: next });
    }
  }, []);

  const {
    customFields: purchaseOrderFormCustomFields,
    customFieldValues: purchaseOrderFormCustomFieldValues,
    loadFieldValues: loadPurchaseOrderFormFieldValues,
    extractFormValues: extractPurchaseOrderFormValues,
    saveCustomFieldValues: savePurchaseOrderCustomFieldValues,
    resetFieldValues: resetPurchaseOrderFormFieldValues,
  } = useCustomFields({ tableName: PURCHASE_ORDER_CUSTOM_FIELD_TABLE, loadWhenOpen: true, open: isFormPage });

  const {
    customFields: purchaseOrderListCustomFields,
    generateCustomFieldColumns: generatePurchaseOrderCustomFieldColumns,
    enrichRecordsWithCustomFields: enrichPurchaseOrderRecordsWithCustomFields,
    customFieldValues: purchaseOrderDetailCustomFieldValues,
    loadFieldValuesForDetail: loadPurchaseOrderFieldValuesForDetail,
    resetDetailFieldValues: resetPurchaseOrderDetailFieldValues,
  } = useCustomFieldsForList<PurchaseOrder>({ tableName: PURCHASE_ORDER_CUSTOM_FIELD_TABLE });
  /** 标记是否在保存后自动提交（草稿转正式） */
  const submitAfterSaveRef = useRef(false);
  const purchaseOrderFormSubmitLockRef = useRef(false);
  /**
   * 新建页已 create 成功但尚未离开时，记下 id。
   * 避免「保存并审核」中途失败/待选审批人后再次提交又走 create → 编码已存在。
   */
  const createdOrderIdRef = useRef<number | null>(null);
  const [purchaseOrderFormSubmitting, setPurchaseOrderFormSubmitting] = useState(false);

  // Drawer 相关状态
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [orderDetail, setOrderDetail] = useState<PurchaseOrderDetail | null>(null);
  const [poTrackingRefreshKey, setPoTrackingRefreshKey] = useState(0);
  useRegisterAiContext(
    detailDrawerVisible && orderDetail
      ? {
          screenLabel: t('app.kuaizhizao.menu.purchase-management.purchase-orders'),
          resourceKey: 'kuaizhizao:purchase_order',
          recordId: orderDetail.id,
          recordLabel: orderDetail.order_code,
        }
      : { screenLabel: t('app.kuaizhizao.menu.purchase-management.purchase-orders') },
  );

  const lifecycleValueEnum = useMemo(
    () => buildPurchaseOrderLifecycleValueEnum(t, purchaseOrderAuditEnabled),
    [t, purchaseOrderAuditEnabled],
  );
  const purchaseOrderAuditColumn = useMemo(
    () => createListAuditPhaseColumn<PurchaseOrder>({ t, auditEnabled: purchaseOrderAuditEnabled }),
    [t, purchaseOrderAuditEnabled],
  );
  const purchaseOrderPaymentSettlementEnum = useMemo(
    () => buildPurchaseOrderPaymentSettlementEnum(t),
    [t],
  );

  // 供应商列表、订单类型、币种
  const [supplierList, setSupplierList] = useState<any[]>([]);
  const [orderTypeOptions, setOrderTypeOptions] = useState<Array<{ label: string; value: string }>>(() =>
    mapSystemDictionaryItemOptions('ORDER_TYPE', ORDER_TYPE_FALLBACK_ITEMS as DictionaryItem[], t),
  );
  const [orderTypeLoading, setOrderTypeLoading] = useState(false);
  const [currencyOptions, setCurrencyOptions] = useState<Array<{ label: string; value: string }>>([]);
  const [currencyLoading, setCurrencyLoading] = useState(false);
  const [bankAccountOptions, setBankAccountOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [users, setUsers] = useState<User[]>([]);
  const currentUser = useCurrentUser();
  const {
    options: departmentOptions,
    loading: departmentOptionsLoading,
    resolveName: resolveDepartmentName,
  } = usePurchaseDepartmentOptions();
  const [usersLoading, setUsersLoading] = useState(false);

  const [syncModalVisible, setSyncModalVisible] = useState(false);
  const [syncFreshnessKey, setSyncFreshnessKey] = useState(0);
  const loadPurchaseOrderSyncBinding = useCallback(() => getPurchaseOrderSyncBinding(), []);

  // 下推退货 Modal
  const [pushToReturnVisible, setPushToReturnVisible] = useState(false);
  const [landingCostModalVisible, setLandingCostModalVisible] = useState(false);

  const invalidateStatistics = () => {
    queryClient.invalidateQueries({ queryKey: ['purchaseOrderStatistics'] });
  };

  useEffect(() => {
    if (!isFormPage) return;
    const loadUsers = async () => {
      setUsersLoading(true);
      try {
        const res = await searchUserDisplay({ page_size: 100, is_active: true });
        setUsers(displayItemsToUsers(res.items || []));
      } catch {
        setUsers([]);
      } finally {
        setUsersLoading(false);
      }
    };
    const loadBankAccounts = async () => {
      const options = await loadBankAccountFormOptions(KUAIZHIZAO_DOC_HOST.purchaseOrder);
      setBankAccountOptions(options);
    };
    void loadUsers();
    void loadBankAccounts();
  }, [currentUser, isFormPage]);

  // 新建页：会话用户晚于表单 init 时再补一次采购员默认
  useEffect(() => {
    if (!isFormPage || !isCreatePage) return;
    const raw = formRef.current?.getFieldValue?.('buyer_id');
    if (raw != null && raw !== '' && Number.isFinite(Number(raw)) && Number(raw) > 0) return;
    const def = resolveDefaultPurchaseOrderBuyer();
    if (def.buyer_id == null) return;
    formRef.current?.setFieldsValue?.(def);
  }, [isFormPage, isCreatePage, currentUser]);

  const purchaseOrderSupplierSearchOptions = useMemo(
    () =>
      supplierList.map((s: { id?: number; name?: string; code?: string; supplier_name?: string }) => ({
        value: Number(s.id),
        label: [s.name ?? s.supplier_name, s.code].filter(Boolean).join(' - ') || String(s.id),
      })),
    [supplierList],
  );

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
          mapSystemDictionaryItemOptions('ORDER_TYPE', ORDER_TYPE_FALLBACK_ITEMS as DictionaryItem[], t),
        );
        messageApi.info(t('app.kuaizhizao.purchaseOrder.orderTypeFallback'));
      } finally {
        setOrderTypeLoading(false);
      }
    };
    const loadCurrency = async () => {
      setCurrencyLoading(true);
      try {
        const dict = await getDataDictionaryByCode('CURRENCY');
        const items = await getDictionaryItemList(dict.uuid, true);
        setCurrencyOptions(items.sort((a, b) => a.sort_order - b.sort_order).map((it) => ({ label: it.label, value: it.value })));
      } catch {
        setCurrencyOptions([{ label: t('app.kuaizhizao.purchaseOrder.currencyCny'), value: 'CNY' }, { label: t('app.kuaizhizao.purchaseOrder.currencyUsd'), value: 'USD' }, { label: t('app.kuaizhizao.purchaseOrder.currencyEur'), value: 'EUR' }]);
      } finally {
        setCurrencyLoading(false);
      }
    };
    loadOrderType();
    loadCurrency();
  }, [t, messageApi]);

  const secondaryStatsReady = useDeferAfterPaint();
  const { data: statistics } = useQuery({
    queryKey: ['purchaseOrderStatistics'],
    queryFn: getPurchaseOrderStatistics,
    enabled: secondaryStatsReady,
  });

  // 下推入库 Modal
  const [feeTypeOptions, setFeeTypeOptions] = useState<any[]>([]);

  useEffect(() => {
    getDataDictionaryByCode('FEE_TYPE')
      .then((dict) => getDictionaryItemList(dict.uuid))
      .then((res) => {
        setFeeTypeOptions(res || []);
      })
      .catch(() => {
        setFeeTypeOptions([]);
      });
  }, []);

  const appendPurchaseItemsFromMaterials = useCallback(
    async (selected: Material[]) => {
      if (!selected?.length) return;
      const mainDelivery = formRef.current?.getFieldValue('delivery_date');
      const defaultDate =
        mainDelivery != null ? (dayjs.isDayjs(mainDelivery) ? mainDelivery : dayjs(mainDelivery)) : dayjs();
      const supplierId = formRef.current?.getFieldValue('supplier_id');
      const orderDate = formRef.current?.getFieldValue('order_date');
      const asOf = orderDate != null ? (dayjs.isDayjs(orderDate) ? orderDate : dayjs(orderDate)) : dayjs();
      const priceType = String(formRef.current?.getFieldValue('price_type') ?? 'tax_exclusive');

      const priced = await resolvePurchaseDocumentMaterialLinesPricing(selected, {
        supplierId: supplierId ? Number(supplierId) : undefined,
        asOf,
        priceType,
      });

      const current = normalizeFormListItems<any>(formRef.current?.getFieldValue('items'));
      const newRows = priced.map(({ material: m, unitPrice, taxRate }) => ({
        material_id: (m as Material).id,
        material_code: (m as Material).mainCode ?? (m as Material).code ?? '',
        material_name: (m as Material).name ?? '',
        material_spec: (m as Material).specification ?? '',
        unit: resolveMaterialScenarioUnit(m as Material, 'purchase'),
        ordered_quantity: 1,
        unit_price: unitPrice,
        tax_rate: taxRate,
        required_date: defaultDate,
      }));
      const firstRow = current?.[0];
      const firstRowEmpty =
        current.length === 1 &&
        !firstRow?.material_id &&
        !(firstRow?.material_code && String(firstRow.material_code).trim()) &&
        !(firstRow?.material_name && String(firstRow.material_name).trim());

      if (firstRowEmpty) {
        formRef.current?.setFieldsValue({ items: [newRows[0], ...newRows.slice(1)] });
      } else {
        formRef.current?.setFieldsValue({ items: [...current, ...newRows] });
      }
      messageApi.success(t('app.kuaizhizao.common.materialBatchAdded', { count: selected.length }));
    },
    [messageApi, t]
  );

  const handleItemImport = useCallback(
    async (data: any[][]) => {
      const rows = data.slice(2);
      const mainDelivery = formRef.current?.getFieldValue('delivery_date');
      const defaultDate =
        mainDelivery != null ? (dayjs.isDayjs(mainDelivery) ? mainDelivery : dayjs(mainDelivery)) : dayjs();
      const loaded = await loadMaterialFormReferenceList(KUAIZHIZAO_DOC_HOST.purchaseOrder);
      const materials = await resolveMaterialsByCodesForImport(
        collectImportMaterialCodes(rows, 0),
        loaded,
      );
      const taxRate = resolveSupplierDefaultTaxRatePercent(
        (supplierList.find(
          (x) => Number(x.id) === Number(formRef.current?.getFieldValue('supplier_id')),
        ) as Record<string, unknown> | undefined) ?? null,
      );
      const importRowErrors: Array<{ row: number; message: string }> = [];
      const newItems = rows
        .map((row, rowIndex) => {
          const materialCode = normalizeImportMaterialCode(row[0]);
          const spec = String(row[1] || '').trim();
          const unitRaw = String(row[2] || '').trim();
          const unit = materialUnitImport.parse(unitRaw) || unitRaw;
          const quantity = parseFloat(row[3]) || 0;
          const priceRaw = row[4];
          const price = Number(priceRaw);
          const requiredDate = row[5];
          const rowNum = rowIndex + 3;

          if (!materialCode) return null;
          if (priceRaw == null || String(priceRaw).trim() === '' || !Number.isFinite(price) || price <= 0) {
            importRowErrors.push({
              row: rowNum,
              message: t('app.kuaizhizao.purchaseOrder.importRowUnitPriceRequired'),
            });
            return null;
          }
          const mat = findMaterialByImportCode(materials, materialCode);

          return {
            material_id: mat?.id,
            material_code: mat?.mainCode || mat?.code || materialCode,
            material_name: mat?.name || '',
            material_spec: mat?.specification ?? '',
            unit: mat?.baseUnit || unit || '件',
            ordered_quantity: quantity || 1,
            unit_price: price,
            tax_rate: taxRate,
            required_date: requiredDate
              ? dayjs(requiredDate).isValid()
                ? dayjs(requiredDate)
                : defaultDate
              : defaultDate,
          };
        })
        .filter((it): it is NonNullable<typeof it> => it !== null);

      if (importRowErrors.length > 0) {
        getAntdModal().warning({
          title: t('app.kuaizhizao.purchaseOrder.importValidationTitle'),
          width: 600,
          content: (
            <div>
              <p>{t('app.kuaizhizao.purchaseOrder.importValidationIntro')}</p>
              <List
                size="small"
                dataSource={importRowErrors}
                renderItem={(item) => (
                  <List.Item>
                    <Typography.Text type="danger">
                      {t('app.kuaizhizao.purchaseOrder.importRowError', {
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

      if (newItems.length === 0) {
        messageApi.warning(t('app.kuaizhizao.purchaseOrder.importNoValidData'));
        return;
      }

      const currentItems = normalizeFormListItems<any>(formRef.current?.getFieldValue('items'));
      formRef.current?.setFieldsValue({ items: [...currentItems, ...newItems] });
      messageApi.success(t('app.kuaizhizao.salesOrder.importSuccessItems', { count: newItems.length }));
      setImportModalVisible(false);
    },
    [messageApi, materialUnitImport, t],
  );

  // 下推退货 Modal 相关详情状态
  const [pushToReturnOrder, setPushToReturnOrder] = useState<PurchaseOrderDetail | null>(null);
  const [pushToReturnQuantities, setPushToReturnQuantities] = useState<Record<number, number>>({});
  const [pushToReturnWarehouseId, setPushToReturnWarehouseId] = useState<number | undefined>(undefined);
  const [pushToReturnWarehouseName, setPushToReturnWarehouseName] = useState('');
  const [pushToReturnLoading, setPushToReturnLoading] = useState(false);
  const [pushToReturnLineMeta, setPushToReturnLineMeta] = useState<
    Record<number, { received: number; pushed: number; remaining: number }>
  >({});
  const [landingCostOrder, setLandingCostOrder] = useState<PurchaseOrder | null>(null);

  /** 列表列顺序：金额/数量/时间在前；生命周期固定倒数第二；操作列最后（与 UI_Standard 一致） */
  const purchaseOrderCustomFieldColumns = generatePurchaseOrderCustomFieldColumns();
  const orderColumns: ProColumns<PurchaseOrder>[] = useMemo(() => alignProColumns<PurchaseOrder>([
    {
      title: t('app.kuaizhizao.purchaseOrder.col.orderDate'),
      dataIndex: 'order_date_range',
      valueType: 'dateRange',
      hideInTable: true,
      fieldProps: {
        placeholder: [t('app.kuaizhizao.quotation.dateRangeStart'), t('app.kuaizhizao.quotation.dateRangeEnd')],
      },
      formItemProps: formDateRangeFormItemProps,
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.deliveryDate'),
      dataIndex: 'delivery_date_range',
      valueType: 'dateRange',
      hideInTable: true,
      fieldProps: {
        placeholder: [t('app.kuaizhizao.quotation.dateRangeStart'), t('app.kuaizhizao.quotation.dateRangeEnd')],
      },
      formItemProps: formDateRangeFormItemProps,
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.supplierAndOrder'),
      key: 'order_code',
      dataIndex: 'order_code',
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
          secondary={String(r.order_code ?? '')}
          primaryExtra={renderExternalSyncPrimaryExtra(r as unknown as Record<string, unknown>)}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.orderCode'),
      dataIndex: 'order_code',
      hideInTable: true,
      hideInSearch: false,
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.supplier'),
      dataIndex: 'supplier_id',
      hideInTable: true,
      valueType: 'select',
      fieldProps: {
        showSearch: true,
        filterOption: false,
        placeholder: t('app.kuaizhizao.purchaseOrder.col.supplier'),
      },
      debounceTime: 300,
      request: async ({ keyWords }) => {
        const res = await searchReferenceDisplay({
          resource: 'master-data:supply-chain:supplier',
          hostResource: 'kuaizhizao:purchase-order',
          keyword: typeof keyWords === 'string' ? keyWords.trim() : undefined,
          pageSize: 20,
        });
        return referenceDisplayToIdOptions(res.items);
      },
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.supplier'),
      dataIndex: 'supplier_name',
      hideInTable: true,
      hideInSearch: true,
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.buyer'),
      dataIndex: 'buyer_id',
      hideInTable: true,
      valueType: 'select',
      fieldProps: {
        showSearch: true,
        filterOption: false,
        placeholder: t('app.kuaizhizao.purchaseOrder.col.buyer'),
      },
      debounceTime: 300,
      request: async ({ keyWords }) => {
        const res = await searchUserDisplay({
          page: 1,
          page_size: 20,
          is_active: true,
          keyword: typeof keyWords === 'string' ? keyWords.trim() || undefined : undefined,
        });
        return (res.items || []).map((u) => ({
          label: u.label || u.full_name || u.username || String(u.id),
          value: u.id,
        }));
      },
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.buyer'),
      dataIndex: 'buyer_name',
      width: 120,
      minWidth: 120,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      ellipsis: true,
      hideInSearch: true,
      render: (_: unknown, record: PurchaseOrder) => normalizeUserDisplayName(record.buyer_name) || '-',
    },
    {
      title: t('app.kuaizhizao.common.colLineMaterials'),
      ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
      render: (_: unknown, record: PurchaseOrder) =>
        renderDocumentLineMaterialsPreview(record.items, t),
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.orderDate'),
      key: 'order_date_delivery_date_stacked',
      dataIndex: 'order_date',
      ...UNI_TABLE_STACKED_BADGE_DATE_COLUMN_DEFAULTS,
      sorter: true,
      hideInSearch: true,
      render: (_: any, record: PurchaseOrder) => (
        <UniTableStackedPrimaryCell
          primary={record.order_date ? formatDateTime(record.order_date, 'YYYY-MM-DD') : '-'}
          secondary={record.delivery_date ? formatDateTime(record.delivery_date, 'YYYY-MM-DD') : '-'}
          secondaryCopyable={false}
          uniformText
          primaryBadge={t('common.start')}
          secondaryBadge={t('common.end')}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.salesManagement.pushProgress.title'),
      dataIndex: 'downstream_push_progress',
      ...DOCUMENT_PROGRESS_COLUMN_DEFAULTS,
      render: (_: any, record: PurchaseOrder) => {
        const percent = Number(record.downstream_push_progress ?? 0);
        return (
          <DocumentPushProgressBar
            percent={percent}
            tooltip={t('app.kuaizhizao.salesManagement.pushProgress.percentOnly', {
              percent: Math.round(percent),
            })}
            documents={collectPurchaseOrderPushDocuments(record, {
              receiptNotice: t('components.documentTrackingPanel.docType.receipt_notice'),
              purchaseReceipt: t('components.documentTrackingPanel.docType.purchase_receipt'),
            })}
            formatMoreDocs={(count) =>
              t('app.kuaizhizao.salesManagement.pushProgress.moreDocs', { count })
            }
          />
        );
      },
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.receiptProgress'),
      dataIndex: 'receipt_progress',
      ...DOCUMENT_PROGRESS_COLUMN_DEFAULTS,
      render: (_: any, record: PurchaseOrder) => {
        const percent = Number(record.receipt_progress ?? 0);
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
      title: t('app.kuaizhizao.purchaseOrder.col.orderAmount'),
      dataIndex: 'total_amount',
      width: 120,
      minWidth: 120,
      uniTableKeepWidth: true,
      resizable: false,
      align: 'right',
      sorter: true,
      hideInSearch: true,
      render: (_: unknown, record: PurchaseOrder) =>
        formatCurrencyAmount(resolvePurchaseOrderDisplayAmount(record)),
    },
    {
      title: t('app.kuaizhizao.purchaseOrder.col.totalQuantity'),
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
    ...buildDocumentAuditColumns<PurchaseOrder>(t),
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
    ...(purchaseOrderAuditColumn ? [purchaseOrderAuditColumn] : []),
    {
      title: t('app.kuaizhizao.purchaseOrder.col.lifecycle'),
      key: 'lifecycle',
      dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
      fixed: 'right',
      valueType: 'select',
      valueEnum: lifecycleValueEnum,
      render: (_: any, record: PurchaseOrder) => (
        <ListUniLifecycleCell lifecycle={getPurchaseOrderLifecycle(record, purchaseOrderAuditEnabled, t)} />
      ),
    },
    {
      title: t('app.kuaizhizao.paymentApplication.col.paymentSettlement'),
      key: 'payment_settlement',
      dataIndex: 'paymentSettlement',
      ...UNI_TABLE_PAYMENT_SETTLEMENT_COLUMN_DEFAULTS,
      fixed: 'right',
      hideInSearch: true,
      valueType: 'select',
      valueEnum: purchaseOrderPaymentSettlementEnum,
      render: (_, record) => {
        const settlement = resolvePurchaseOrderPaymentSettlementDisplay(record, t);
        if (!settlement) return '—';
        return renderDocumentStatusTag(settlement.label, settlement.raw);
      },
    },
    ...purchaseOrderCustomFieldColumns,
    {
      title: t('common.actions'),
      fixed: 'right',
      hideInSearch: true,
      valueType: 'option',
      render: (_: any, record: PurchaseOrder) => {
        const canEdit = record.capabilities?.update?.allowed === true && purchaseOrderPerms.canUpdate;
        const canDelete = record.capabilities?.delete?.allowed === true && purchaseOrderPerms.canDelete;
        const parts: React.ReactNode[] = [
          <Button {...rowActionKind('read')} key="d" onClick={() => handleDetail(record)}>
            {t('common.detail')}
          </Button>,
        ];
        if (canEdit) {
          parts.push(
            <Button {...rowActionKind('update')} key="e" onClick={() => handleEdit(record)}>
              {t('common.edit')}
            </Button>,
          );
        }
        if (canDelete) {
          parts.push(
            <ActionConfirmPopconfirm title={t('app.kuaizhizao.purchaseOrder.deleteTitle')} description={t('app.kuaizhizao.purchaseOrder.deleteContent', { code: record.order_code })} okType="danger" onConfirm={() => executeDelete(record)}>
              <Button {...rowActionKind('delete')} key="del" onClick={(e) => e.stopPropagation()}>
              {t('common.delete')}
            </Button>
            </ActionConfirmPopconfirm>,
          );
        }
        parts.push(
          <UniWorkflowActions {...rowActionKind('skip')}
            key="wf"
            record={record}
            entityName={t('app.kuaizhizao.purchaseOrder.entityName')}
            entityType="purchase_order"
            unifiedAudit
            resourcePrefix="kuaizhizao:purchase-order"
            statusField="status"
            reviewStatusField="review_status"
            draftStatuses={PO_WORKFLOW_DRAFT_STATUSES}
            pendingStatuses={PO_WORKFLOW_PENDING_STATUSES}
            approvedStatuses={PO_WORKFLOW_APPROVED_STATUSES}
            rejectedStatuses={PO_WORKFLOW_REJECTED_STATUSES}
            submitActionLabel={t('app.kuaizhizao.purchaseOrder.submitForReview')}
            theme="link"
            size="small"
            onSuccess={() => {
              invalidateStatistics();
              invalidateMenuBadgeCounts();
    actionRef.current?.reload();
              if (detailDrawerVisible && orderDetail?.id === record.id && record.id != null) {
                void getPurchaseOrder(record.id).then((d) => {
                  setOrderDetail(d);
                  setPoTrackingRefreshKey((k) => k + 1);
                });
              }
            }}
          />
        );
        return parts;
      },
    },
  ], SALES_DOC_LIST_FIELD_RANK), [t, purchaseOrderAuditEnabled, lifecycleValueEnum, purchaseOrderAuditColumn, purchaseOrderPaymentSettlementEnum, purchaseOrderCustomFieldColumns, purchaseOrderPerms, purchaseOrderSupplierSearchOptions, detailDrawerVisible, orderDetail?.id]);

  /** 明细表格列序：GLOBAL_DOC_DETAIL_TABLE_FIELD_RANK（禁止套用 LIST rank） */
  const detailTableColumns: ProColumns<PurchaseOrderItemRow>[] = useMemo(
    () =>
      alignProColumns<PurchaseOrderItemRow>(
        [
      {
        title: t('app.kuaizhizao.purchaseOrder.col.supplierAndOrder'),
        key: 'order_code',
        dataIndex: 'order_code',
        ...UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
        fixed: 'left',
        hideInSearch: false,
        fieldProps: { placeholder: t('app.kuaizhizao.purchaseOrder.col.orderCode') },
        render: (_, record) => (
          <UniTableStackedPrimaryCell
            primary={String(record.supplier_name ?? '')}
            secondary={String(record.order_code ?? '')}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.supplier'),
        dataIndex: 'supplier_id',
        hideInTable: true,
        valueType: 'select',
        fieldProps: {
          showSearch: true,
          filterOption: false,
          placeholder: t('app.kuaizhizao.purchaseOrder.col.supplier'),
        },
        debounceTime: 300,
        request: async ({ keyWords }) => {
          const res = await searchReferenceDisplay({
            resource: 'master-data:supply-chain:supplier',
            hostResource: 'kuaizhizao:purchase-order',
            keyword: typeof keyWords === 'string' ? keyWords.trim() : undefined,
            pageSize: 20,
          });
          return referenceDisplayToIdOptions(res.items);
        },
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.materialName'),
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
        title: t('app.kuaizhizao.purchaseOrder.col.materialCode'),
        dataIndex: 'material_code',
        hideInTable: true,
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.spec'),
        dataIndex: 'material_spec',
        hideInTable: true,
      },
      {
        title: t('common.quantity'),
        dataIndex: 'ordered_quantity',
        width: 120,
        align: 'right',
        render: (val: unknown, record: PurchaseOrderItemRow) => (
          <QuantityWithUnitDisplay quantity={val} unit={record.unit} />
        ),
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.unitPrice'),
        dataIndex: 'unit_price',
        width: 100,
        align: 'right',
        render: (text: unknown) => formatCurrencyPrice(text),
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.totalPrice'),
        dataIndex: 'total_price',
        width: 110,
        align: 'right',
        render: (text: unknown) => formatCurrencyAmount(text),
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.receivedQty'),
        dataIndex: 'received_quantity',
        width: 90,
        align: 'right',
        render: (text: unknown) => formatQuantity(text),
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.outstandingQty'),
        dataIndex: 'outstanding_quantity',
        width: 90,
        align: 'right',
        render: (text: unknown) => formatQuantity(text),
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.requiredDelivery'),
        dataIndex: 'required_date',
        width: 132,
        uniTableKeepWidth: true,
        hideInSearch: true,
        render: (_: unknown, row: PurchaseOrderItemRow) => {
          const raw = row.required_date;
          const text = raw ? formatDateTime(raw, 'YYYY-MM-DD') : '-';
          const overdue = isPurchaseOrderDeliveryOverdue(
            {
              delivery_date: row.required_date || row.delivery_date,
              status: row.status,
              review_status: row.review_status,
            } as PurchaseOrder,
            purchaseOrderAuditEnabled,
          );
          return (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
              <span>{text}</span>
              {overdue ? (
                <UniTableStackedLineBadge tone="danger">
                  {t('app.kuaizhizao.purchaseOrder.overdueBadge')}
                </UniTableStackedLineBadge>
              ) : null}
            </span>
          );
        },
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.lineReceiptProgress'),
        key: 'line_receipt_progress',
        dataIndex: 'line_receipt_progress',
        ...DETAIL_TABLE_PROGRESS_COLUMN_DEFAULTS,
        render: (_: unknown, record: PurchaseOrderItemRow) => {
          const ordered = Number(record.ordered_quantity ?? 0);
          const received = Number(record.received_quantity ?? 0);
          const percent = ratioToPushProgressPercent(received, ordered);
          return (
            <DocumentPushProgressBar
              percent={percent}
              tooltip={t('app.kuaizhizao.purchaseOrder.col.receiptProgressTip', {
                received: formatQuantity(received),
                ordered: formatQuantity(ordered),
                percent,
              })}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.lifecycle'),
        dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
        fixed: 'right',
        hideInSearch: false,
        valueType: 'select',
        valueEnum: lifecycleValueEnum,
        render: (_: unknown, record: PurchaseOrderItemRow) => {
          const orderRecord = {
            id: record.purchase_order_id,
            status: record.status,
            review_status: record.review_status,
            receipt_progress: record.receipt_progress,
            downstream_push_progress: record.downstream_push_progress,
          } as PurchaseOrder;
          return (
            <ListUniLifecycleCell
              lifecycle={getPurchaseOrderLifecycle(orderRecord, purchaseOrderAuditEnabled, t)}
            />
          );
        },
      },
        ],
        GLOBAL_DOC_DETAIL_TABLE_FIELD_RANK,
      ),
    [t, purchaseOrderAuditEnabled, lifecycleValueEnum, purchaseOrderSupplierSearchOptions],
  );

  const columns = (dataViewMode === 'detail' ? detailTableColumns : orderColumns) as ProColumns<any>[];

  const [pushToInvoiceLoading, setPushToInvoiceLoading] = useState(false);

  const pullSourceRequisitionIdRef = useRef<number | undefined>(undefined);
  const [pullSourceRequisitionId, setPullSourceRequisitionId] = useState<number | undefined>();
  const pullSourceOrderTypeRef = useRef<string | undefined>(undefined);
  const [pullSourceOrderType, setPullSourceOrderType] = useState<string | undefined>();
  const pullSourceSalesOrderIdRef = useRef<number | undefined>(undefined);
  const [pullSourceSalesOrderId, setPullSourceSalesOrderId] = useState<number | undefined>();
  const [pullSourceSalesOrderOptions, setPullSourceSalesOrderOptions] = useState<
    { value: number; label: string }[]
  >([]);
  const [pullSourceRequisitionOptions, setPullSourceRequisitionOptions] = useState<Array<{ value: number; label: string }>>([]);
  const pullSourceInquiryIdRef = useRef<number | undefined>(undefined);
  const [pullSourceInquiryId, setPullSourceInquiryId] = useState<number | undefined>();
  const [pullSourceInquiryOptions, setPullSourceInquiryOptions] = useState<Array<{ value: number; label: string }>>([]);

  const [pushPreviewOpen, setPushPreviewOpen] = useState(false);
  const [pushPreviewKind, setPushPreviewKind] = useState<PushPreviewKind | null>(null);
  const [pushPreviewLoading, setPushPreviewLoading] = useState(false);
  const [pushPreviewConfirming, setPushPreviewConfirming] = useState(false);
  const [pushPreviewData, setPushPreviewData] = useState<DocumentPushPreview | null>(null);
  const [pushPreviewTarget, setPushPreviewTarget] = useState<PurchaseOrder | null>(null);
  const [pushPreviewSelectedItemIds, setPushPreviewSelectedItemIds] = useState<number[]>([]);
  const [pushPreviewQuantities, setPushPreviewQuantities] = useState<Record<number, number>>({});
  const [pushPreviewNotes, setPushPreviewNotes] = useState('');
  const [pushPreviewLineWh, setPushPreviewLineWh] = useState<Record<number, number>>({});
  const [pushPreviewWarehouseOptions, setPushPreviewWarehouseOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [pushInvoiceMode, setPushInvoiceMode] = useState<PurchaseInvoicePushMode>('remaining');
  const [pushInvoiceAmount, setPushInvoiceAmount] = useState<number>(0);
  const [pushInvoiceNumber, setPushInvoiceNumber] = useState('');

  const pushPreviewModalTitle = useMemo(() => {
    if (pushPreviewKind === 'receipt_notice') return pushToReceiptNoticeAction.label;
    if (pushPreviewKind === 'receipt') return pushToReceiptAction.label;
    if (pushPreviewKind === 'invoice') return pushToInvoiceAction.label;
    if (pushPreviewKind === 'prepayment') return pushToPrepaymentAction.label;
    if (pushPreviewKind === 'payment_application') return t('app.kuaizhizao.paymentApplication.pushFromPurchaseOrder');
    if (pushPreviewKind === 'purchase_return') return pushToPurchaseReturnAction.label;
    if (pushPreviewKind === 'incoming_inspection') return pushToIncomingInspectionAction.label;
    return t('app.kuaizhizao.salesOrder.pushPreviewTitle');
  }, [
    pushPreviewKind,
    pushToIncomingInspectionAction.label,
    pushToInvoiceAction.label,
    pushToPrepaymentAction.label,
    pushToPurchaseReturnAction.label,
    pushToReceiptAction.label,
    pushToReceiptNoticeAction.label,
    t,
  ]);

  const pushPreviewQtyColumnTitles = useMemo(() => {
    if (pushPreviewKind === 'receipt_notice' || pushPreviewKind === 'receipt') {
      return {
        quantity: t('app.kuaizhizao.purchaseOrder.col.orderedQty'),
        pushed: t('app.kuaizhizao.purchaseOrder.col.receivedQty'),
        pushable: t('app.kuaizhizao.purchaseOrder.col.outstandingQty'),
      };
    }
    if (pushPreviewKind === 'purchase_return') {
      return {
        quantity: t('app.kuaizhizao.purchaseOrder.col.receivedQty'),
        pushed: t('app.kuaizhizao.salesOrder.colPushedQty'),
        pushable: t('app.kuaizhizao.salesOrder.colPushableQty'),
      };
    }
    if (pushPreviewKind === 'incoming_inspection') {
      return {
        quantity: t('app.kuaizhizao.purchaseOrder.col.orderedQty'),
        pushed: t('app.kuaizhizao.purchaseOrder.col.iqcPushedQty'),
        pushable: t('app.kuaizhizao.purchaseOrder.col.iqcRemainingQty'),
      };
    }
    return {
      quantity: t('common.quantity'),
      pushed: t('app.kuaizhizao.salesOrder.colPushedQty'),
      pushable: t('app.kuaizhizao.salesOrder.colPushableQty'),
    };
  }, [pushPreviewKind, t]);

  const pushPreviewConfirmLabel =
    pushPreviewKind === 'receipt_notice' ||
    pushPreviewKind === 'receipt' ||
    pushPreviewKind === 'incoming_inspection'
      ? t('app.kuaizhizao.salesOrder.confirmPush')
      : t('common.confirm');

  // 处理详情查看
  const handleDetail = async (record: PurchaseOrder) => {
    try {
      const detail = await getPurchaseOrder(record.id!);
      setOrderDetail(detail as PurchaseOrderDetail);
      setDetailDrawerVisible(true);
      setPoTrackingRefreshKey((k) => k + 1);
      if (record.id != null) {
        await loadPurchaseOrderFieldValuesForDetail(record.id);
      }
    } catch (error) {
      messageApi.error(t('app.kuaizhizao.purchaseOrder.detailFailed'));
    }
  };

  /** 采购中心等入口：navigate(..., { state: { openPurchaseOrderId } }) 打开详情抽屉 */
  useEffect(() => {
    if (isFormPage) return;
    const raw = (location.state as { openPurchaseOrderId?: unknown } | null)?.openPurchaseOrderId;
    const id = typeof raw === 'number' ? raw : raw != null ? Number(raw) : NaN;
    if (!Number.isFinite(id) || id <= 0) return;
    navigate(`${location.pathname}${location.search}`, { replace: true, state: {} });
    void handleDetail({ id } as PurchaseOrder);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅响应路由 state 开单；handleDetail 用最新闭包
  }, [location.state, location.pathname, location.search, navigate, isFormPage]);

  const resetPushPreviewModal = useCallback(() => {
    setPushPreviewOpen(false);
    setPushPreviewKind(null);
    setPushPreviewData(null);
    setPushPreviewTarget(null);
    setPushPreviewSelectedItemIds([]);
    setPushPreviewQuantities({});
    setPushPreviewNotes('');
    setPushPreviewLineWh({});
    setPushPreviewWarehouseOptions([]);
    setPushInvoiceMode('remaining');
    setPushInvoiceAmount(0);
    setPushInvoiceNumber('');
  }, []);

  const openPushReturnWarehouseModal = useCallback(
    async (record: PurchaseOrder, quantities: Record<number, number>) => {
      const [detail, preview] = await Promise.all([
        getPurchaseOrder(record.id!),
        previewPushToPurchaseReturn(record.id!),
      ]);
      const previewByItemId = new Map(
        (preview.items || []).map((row) => [Number(row.item_id), row]),
      );
      const lineMeta: Record<number, { received: number; pushed: number; remaining: number }> = {};
      for (const row of preview.items || []) {
        const itemId = Number(row.item_id);
        if (!Number.isFinite(itemId) || itemId <= 0) continue;
        lineMeta[itemId] = {
          received: Number(row.quantity ?? 0),
          pushed: Number(row.pushed_quantity ?? 0),
          remaining: Number(row.max_push_quantity ?? 0),
        };
      }
      const items = (detail.items || []).filter((it: PurchaseOrderItem) => {
        if (it.id == null || (quantities[it.id] ?? 0) <= 0) return false;
        const meta = lineMeta[it.id];
        return meta ? meta.remaining > 0 : true;
      });
      if (items.length === 0) {
        messageApi.warning(t('app.kuaizhizao.purchaseOrder.noReturnableQty'));
        return;
      }
      const clampedQuantities: Record<number, number> = {};
      for (const it of items) {
        if (it.id == null) continue;
        const meta = previewByItemId.get(it.id);
        const max = Number(meta?.max_push_quantity ?? it.received_quantity ?? 0);
        const requested = Number(quantities[it.id] ?? 0);
        clampedQuantities[it.id] = Math.min(requested, max > 0 ? max : requested);
      }
      setPushToReturnOrder(detail as PurchaseOrderDetail);
      setPushToReturnQuantities(clampedQuantities);
      setPushToReturnLineMeta(lineMeta);
      setPushToReturnWarehouseId(undefined);
      setPushToReturnWarehouseName('');
      setPushToReturnVisible(true);
    },
    [messageApi, t],
  );

  const loadPushPreview = useCallback(
    async (record: PurchaseOrder, kind: PushPreviewKind, invoiceMode?: PurchaseInvoicePushMode) => {
      if (!record.id) return;
      setPushPreviewOpen(true);
      setPushPreviewKind(kind);
      setPushPreviewTarget(record);
      setPushPreviewConfirming(false);
      setPushPreviewSelectedItemIds([]);
      setPushPreviewQuantities({});
      setPushPreviewNotes('');
      setPushPreviewLineWh({});
      setPushPreviewWarehouseOptions([]);
      setPushInvoiceMode(invoiceMode ?? 'remaining');
      setPushInvoiceAmount(0);
      setPushInvoiceNumber('');
      setPushPreviewLoading(true);
      setPushPreviewData(null);
      try {
        let preview: DocumentPushPreview;
        if (kind === 'receipt_notice') {
          preview = await previewPushToReceiptNotice(record.id);
        } else if (kind === 'receipt') {
          preview = await previewPushToReceipt(record.id);
        } else if (kind === 'invoice') {
          preview = await previewPushToInvoice(record.id);
        } else if (kind === 'prepayment') {
          preview = await previewPushToPrepayment(record.id);
        } else if (kind === 'payment_application') {
          preview = await previewPushToPaymentApplication(record.id);
        } else if (kind === 'incoming_inspection') {
          preview = (await qualityApi.incomingInspection.previewFromPurchaseOrder(
            record.id,
          )) as DocumentPushPreview;
        } else {
          preview = await previewPushToPurchaseReturn(record.id);
        }
        setPushPreviewData(preview);
        if (kind === 'invoice') {
          const preferred = invoiceMode ?? 'remaining';
          const modeRow =
            (preview.invoice_modes || []).find((m) => m.key === preferred && m.allowed) ||
            (preview.invoice_modes || []).find((m) => m.allowed);
          const nextMode = (modeRow?.key === 'prepayment' ? 'prepayment' : 'remaining') as PurchaseInvoicePushMode;
          setPushInvoiceMode(nextMode);
          setPushInvoiceAmount(Number(modeRow?.amount ?? preview.remaining_total ?? 0));
        } else if (kind === 'prepayment') {
          setPushInvoiceAmount(Number(preview.prepayment_amount ?? 0));
        } else if (kind === 'payment_application') {
          setPushInvoiceAmount(Number(preview.max_push_quantity ?? 0));
        }
        const rows = preview.items || [];
        const ids: number[] = [];
        const qtyMap: Record<number, number> = {};
        const lineWh: Record<number, number> = {};
        rows.forEach((row) => {
          const itemId = Number(row.item_id);
          if (!Number.isFinite(itemId) || itemId <= 0) return;
          const defaultQty = Number(row.max_push_quantity ?? 0);
          if (Number.isFinite(defaultQty) && defaultQty > 0) {
            ids.push(itemId);
          }
          qtyMap[itemId] = Number.isFinite(defaultQty) && defaultQty > 0 ? defaultQty : 0;
          const whId = Number(row.warehouse_id);
          if (Number.isFinite(whId) && whId > 0) {
            lineWh[itemId] = whId;
          }
        });
        setPushPreviewSelectedItemIds(ids);
        setPushPreviewQuantities(qtyMap);
        setPushPreviewLineWh(lineWh);
        if (kind === 'receipt_notice' || kind === 'receipt') {
          const whRes = await masterWarehouseApi.list({ is_active: true, limit: 500 });
          const whList = Array.isArray(whRes) ? whRes : (whRes as { items?: unknown[] })?.items ?? [];
          const warehouseOptions = (Array.isArray(whList) ? whList : []).map((w) => {
            const row = w as { id: number; code?: string; name?: string };
            const label = `${row.code || ''} ${row.name || ''}`.trim() || String(row.id);
            return { label, value: row.id };
          });
          setPushPreviewWarehouseOptions(warehouseOptions);
        }
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.push.previewFailed')));
        resetPushPreviewModal();
      } finally {
        setPushPreviewLoading(false);
      }
    },
    [messageApi, resetPushPreviewModal, t],
  );

  const handlePushPreviewConfirm = useCallback(async () => {
    if (!pushPreviewTarget?.id || !pushPreviewData || !pushPreviewKind) return;
    if (pushPreviewData.has_blocking_issues) return;
    const rowById = new Map(
      (pushPreviewData.items || []).map((row) => [Number(row.item_id), row]),
    );
    const selectedIds = pushPreviewSelectedItemIds.filter((id) => {
      const row = rowById.get(id);
      return row && Number(row.max_push_quantity ?? 0) > 0;
    });
    if (
      pushPreviewKind !== 'invoice' &&
      pushPreviewKind !== 'prepayment' &&
      pushPreviewKind !== 'payment_application' &&
      !selectedIds.length
    ) {
      messageApi.warning(t('app.kuaizhizao.purchaseOrder.push.selectLinesFirst'));
      return;
    }

    const needsLineWarehouse =
      pushPreviewKind === 'receipt_notice' ||
      pushPreviewKind === 'receipt' ||
      !!pushPreviewData.line_warehouse_required;

    const quantities: Record<number, number> = {};
    const lineWarehouses: Record<number, number> = {};
    if (
      pushPreviewKind !== 'invoice' &&
      pushPreviewKind !== 'prepayment' &&
      pushPreviewKind !== 'payment_application'
    ) {
      for (const id of selectedIds) {
        const row = rowById.get(id);
        const qty = Number(pushPreviewQuantities[id] ?? 0);
        const maxQty = Number(row?.max_push_quantity ?? 0);
        if (!Number.isFinite(qty) || qty <= 0) {
          messageApi.warning(
            t('app.kuaizhizao.salesOrder.pushQtyInvalid', { code: row?.material_code || id }),
          );
          return;
        }
        if (Number.isFinite(maxQty) && maxQty > 0 && qty > maxQty) {
          messageApi.warning(
            t('app.kuaizhizao.salesOrder.pushQtyExceedsRemaining', { code: row?.material_code || id }),
          );
          return;
        }
        if (needsLineWarehouse) {
          const lineWh = pushPreviewLineWh[id];
          if (lineWh == null || !(lineWh > 0)) {
            messageApi.warning(
              t('app.kuaizhizao.purchaseOrder.pushReceiptSelectLineWarehouse', {
                material: row?.material_code || row?.material_name || id,
              }),
            );
            return;
          }
          lineWarehouses[id] = lineWh;
        }
        quantities[id] = qty;
      }
    }

    const target = pushPreviewTarget;
    const kind = pushPreviewKind;

    if (kind === 'receipt_notice') {
      setPushPreviewConfirming(true);
      try {
        const result = await pushPurchaseOrderToReceiptNotice(target.id!, {
          selected_item_ids: selectedIds,
          notice_quantities: quantities,
          line_warehouses: lineWarehouses,
        });
        messageApi.success(
          t('app.kuaizhizao.purchaseOrder.pushNoticeSuccess', {
            code: result.notice_code || t('app.kuaizhizao.purchaseOrder.createdFallback'),
          }),
        );
        resetPushPreviewModal();
        invalidateStatistics();
        invalidateMenuBadgeCounts();
    actionRef.current?.reload();
        if (detailDrawerVisible && orderDetail?.id === target.id) {
          getPurchaseOrder(target.id!).then(setOrderDetail);
        }
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.pushNoticeFailed')));
      } finally {
        setPushPreviewConfirming(false);
      }
      return;
    }

    if (kind === 'receipt') {
      setPushPreviewConfirming(true);
      try {
        let headerWarehouseId: number | undefined;
        for (const id of selectedIds) {
          const wh = lineWarehouses[id];
          if (wh != null && wh > 0 && headerWarehouseId == null) {
            headerWarehouseId = wh;
          }
        }
        const result = await pushPurchaseOrderToReceipt(target.id!, quantities, undefined, {
          warehouseId: headerWarehouseId,
          lineWarehouses,
        });
        const receiptId = Number(result?.id);
        if (!Number.isFinite(receiptId) || receiptId <= 0) {
          messageApi.error(t('app.kuaizhizao.purchaseOrder.pushReceiptFailed'));
          return;
        }
        messageApi.success(
          t('app.kuaizhizao.purchaseOrder.pushReceiptSuccess', {
            code: result.receipt_code || t('app.kuaizhizao.purchaseOrder.createdFallback'),
          }),
        );
        resetPushPreviewModal();
        invalidateStatistics();
        invalidateMenuBadgeCounts();
    actionRef.current?.reload();
        if (detailDrawerVisible && orderDetail?.id === target.id) {
          getPurchaseOrder(target.id!).then(setOrderDetail);
        }
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.pushReceiptFailed')));
      } finally {
        setPushPreviewConfirming(false);
      }
      return;
    }

    if (kind === 'purchase_return') {
      resetPushPreviewModal();
      await openPushReturnWarehouseModal(target, quantities);
      return;
    }

    if (kind === 'incoming_inspection') {
      setPushPreviewConfirming(true);
      try {
        const created = await qualityApi.incomingInspection.createFromPurchaseOrder(target.id!, {
          selectedItemIds: selectedIds,
          inspectionQuantities: quantities,
          notes: pushPreviewNotes,
        });
        const list = Array.isArray(created) ? created : [];
        messageApi.success(
          t('app.kuaizhizao.purchaseOrder.pushIncomingInspectionSuccess', {
            count: list.length,
          }),
        );
        resetPushPreviewModal();
        invalidateStatistics();
        invalidateMenuBadgeCounts();
        actionRef.current?.reload();
        if (detailDrawerVisible && orderDetail?.id === target.id) {
          getPurchaseOrder(target.id!).then(setOrderDetail);
        }
        if (list.length === 1 && list[0]?.id) {
          navigate(
            `/apps/kuaizhizao/quality-management/incoming-inspection?incoming_inspection_id=${list[0].id}`,
          );
        } else if (list.length > 1) {
          navigate('/apps/kuaizhizao/quality-management/incoming-inspection');
        }
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.pushIncomingInspectionFailed')),
        );
      } finally {
        setPushPreviewConfirming(false);
      }
      return;
    }

    if (kind === 'prepayment') {
      if (!(pushInvoiceAmount > 0)) {
        messageApi.warning(t('app.kuaizhizao.purchaseOrder.pushPrepaymentAmountInvalid'));
        return;
      }
      setPushPreviewConfirming(true);
      try {
        const result = await pushPurchaseOrderToPrepayment(target.id!, {
          amount: pushInvoiceAmount,
          notes: pushPreviewNotes.trim() || undefined,
        });
        messageApi.success(
          t('app.kuaizhizao.purchaseOrder.pushPrepaymentSuccess', {
            code: result.payment_code || t('app.kuaizhizao.purchaseOrder.createdFallback'),
          }),
        );
        resetPushPreviewModal();
        invalidateStatistics();
        invalidateMenuBadgeCounts();
        actionRef.current?.reload();
        if (detailDrawerVisible && orderDetail?.id === target.id) {
          getPurchaseOrder(target.id!).then(setOrderDetail);
        }
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.pushPrepaymentFailed')),
        );
      } finally {
        setPushPreviewConfirming(false);
      }
      return;
    }

    if (kind === 'payment_application') {
      if (!(pushInvoiceAmount > 0)) {
        messageApi.warning(t('app.kuaizhizao.paymentApplication.amountInvalid'));
        return;
      }
      setPushPreviewConfirming(true);
      try {
        const result = await pushPurchaseOrderToPaymentApplication(target.id!, {
          amount: pushInvoiceAmount,
        });
        messageApi.success(
          t('app.kuaizhizao.paymentApplication.createFromOrderSuccess', {
            code: result.applicationCode,
          }),
        );
        resetPushPreviewModal();
        invalidateStatistics();
        invalidateMenuBadgeCounts();
        actionRef.current?.reload();
        if (detailDrawerVisible && orderDetail?.id === target.id) {
          getPurchaseOrder(target.id!).then(setOrderDetail);
        }
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.paymentApplication.createFailed')));
      } finally {
        setPushPreviewConfirming(false);
      }
      return;
    }

    if (!(pushInvoiceAmount > 0)) {
      messageApi.warning(t('app.kuaizhizao.purchaseOrder.pushInvoiceAmountInvalid'));
      return;
    }
    resetPushPreviewModal();
    setPushToInvoiceLoading(true);
    try {
      const result = await pushPurchaseOrderToInvoice(target.id!, {
        invoice_mode: pushInvoiceMode,
        total_amount: pushInvoiceAmount > 0 ? pushInvoiceAmount : undefined,
        invoice_number: pushInvoiceNumber.trim() || undefined,
      });
      messageApi.success(t('app.kuaizhizao.purchaseOrder.pushInvoiceSuccess', { code: result.invoice_code || t('app.kuaizhizao.purchaseOrder.createdFallback') }));
      invalidateStatistics();
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
      if (detailDrawerVisible && orderDetail?.id === target.id) {
        getPurchaseOrder(target.id!).then(setOrderDetail);
      }
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.pushInvoiceFailed')));
    } finally {
      setPushToInvoiceLoading(false);
    }
  }, [
    detailDrawerVisible,
    invalidateMenuBadgeCounts,
    invalidateStatistics,
    messageApi,
    openPushReturnWarehouseModal,
    orderDetail?.id,
    pushInvoiceAmount,
    pushInvoiceMode,
    pushInvoiceNumber,
    pushPreviewData,
    pushPreviewKind,
    pushPreviewLineWh,
    pushPreviewNotes,
    pushPreviewQuantities,
    pushPreviewSelectedItemIds,
    pushPreviewTarget,
    resetPushPreviewModal,
    t,
    navigate,
  ]);

  const handlePushToReceipt = useCallback(
    (record: PurchaseOrder) => {
      const orderId = record.id;
      if (orderId == null || !(Number(orderId) > 0)) return;
      navigate(inboundPoEntryPath(Number(orderId)));
    },
    [navigate],
  );

  const handlePushToNotice = useCallback(
    (record: PurchaseOrder) => {
      void loadPushPreview(record, 'receipt_notice');
    },
    [loadPushPreview],
  );

  const handlePushToInvoice = useCallback(
    (record: PurchaseOrder, mode: PurchaseInvoicePushMode = 'remaining') => {
      void loadPushPreview(record, 'invoice', mode);
    },
    [loadPushPreview],
  );

  const handlePushToPrepayment = useCallback(
    (record: PurchaseOrder) => {
      void loadPushPreview(record, 'prepayment');
    },
    [loadPushPreview],
  );

  const handlePushToPaymentApplication = useCallback(
    (record: PurchaseOrder) => {
      void loadPushPreview(record, 'payment_application');
    },
    [loadPushPreview],
  );

  const handlePushToReturn = useCallback(
    (record: PurchaseOrder) => {
      void loadPushPreview(record, 'purchase_return');
    },
    [loadPushPreview],
  );

  const handlePushToIncomingInspection = useCallback(
    (record: PurchaseOrder) => {
      void loadPushPreview(record, 'incoming_inspection');
    },
    [loadPushPreview],
  );

  const handlePushToReturnConfirm = async () => {
    if (!pushToReturnOrder?.id) return;
    if (!pushToReturnWarehouseId || pushToReturnWarehouseId <= 0) {
      messageApi.warning(t('app.kuaizhizao.purchaseOrder.returnWarehouseRequired'));
      return;
    }
    const items = (pushToReturnOrder.items || []).filter((it: PurchaseOrderItem) => {
      if (it.id == null) return false;
      const meta = pushToReturnLineMeta[it.id];
      return meta ? meta.remaining > 0 : Number(it.received_quantity ?? 0) > 0;
    });
    for (const it of items) {
      if (it.id == null) continue;
      const qty = pushToReturnQuantities[it.id] ?? 0;
      const meta = pushToReturnLineMeta[it.id];
      const max = meta?.remaining ?? Number(it.received_quantity ?? 0);
      if (qty <= 0) continue;
      if (qty > max) {
        messageApi.error(t('app.kuaizhizao.purchaseOrder.qtyExceedsReturnable', { material: it.material_code || it.material_name, max }));
        return;
      }
    }
    setPushToReturnLoading(true);
    try {
      const result = await pushPurchaseOrderToPurchaseReturn({
        purchase_order_id: pushToReturnOrder.id,
        warehouse_id: pushToReturnWarehouseId,
        warehouse_name: pushToReturnWarehouseName || undefined,
        return_quantities: pushToReturnQuantities,
      });
      messageApi.success(t('app.kuaizhizao.purchaseOrder.pushReturnSuccess', { code: result.return_code || t('app.kuaizhizao.purchaseOrder.createdFallback') }));
      setPushToReturnVisible(false);
      setPushToReturnOrder(null);
      setPushToReturnQuantities({});
      setPushToReturnLineMeta({});
      setPushToReturnWarehouseId(undefined);
      setPushToReturnWarehouseName('');
      invalidateStatistics();
      invalidateMenuBadgeCounts();

      actionRef.current?.reload();
      if (detailDrawerVisible && orderDetail?.id === pushToReturnOrder.id) {
        getPurchaseOrder(pushToReturnOrder.id).then(setOrderDetail);
      }
    } catch (error: any) {
      messageApi.error(error?.response?.data?.detail || error.message || t('app.kuaizhizao.purchaseOrder.pushReturnFailed'));
    } finally {
      setPushToReturnLoading(false);
    }
  };

  const selectedOrderForToolbar = useMemo(() => {
    if (selectedRowKeys.length !== 1) return null;
    return tableOrders.find((row) => String(row.id) === String(selectedRowKeys[0])) ?? null;
  }, [selectedRowKeys, tableOrders]);

  const handlePushToPurchaseOrderChange = useCallback(
    (orderId: number) => {
      navigate(
        `/apps/kuaizhizao/purchase-management/purchase-order-changes?source_order_id=${orderId}`,
      );
    },
    [navigate],
  );

  const buildToolbarPushMenuItems = useCallback((record: PurchaseOrder) => {
      const capReason = (cap?: { allowed?: boolean; reason?: string | null }) =>
        cap?.allowed === true ? undefined : purchaseOrderCapabilityReasonMessage(cap?.reason, t);
      const canPushChange =
        purchaseOrderChangePerms.canCreate &&
        record.capabilities?.create_change_order?.allowed === true;
      const changeDisabledReason = !purchaseOrderChangePerms.canCreate
        ? t('app.kuaizhizao.purchaseOrder.push.changeNoPermission')
        : capReason(record.capabilities?.create_change_order);
      return buildUniPushMenuItems([
        {
          key: 'receipt-notice',
          label: pushToReceiptNoticeAction.label,
          disabled: record.capabilities?.push_receipt_notice?.allowed !== true,
          title: capReason(record.capabilities?.push_receipt_notice),
          onClick: () => {
            if (record.capabilities?.push_receipt_notice?.allowed !== true) return;
            handlePushToNotice(record);
          },
        },
        {
          key: 'receipt',
          label: pushToReceiptAction.label,
          disabled: record.capabilities?.push_receipt?.allowed !== true,
          title: capReason(record.capabilities?.push_receipt),
          onClick: () => {
            if (record.capabilities?.push_receipt?.allowed !== true) return;
            handlePushToReceipt(record);
          },
        },
        {
          key: 'invoice',
          label: pushToInvoiceAction.label,
          disabled: record.capabilities?.push_invoice?.allowed !== true,
          title: capReason(record.capabilities?.push_invoice),
          children: [
            {
              key: 'invoice-remaining',
              label: t('app.kuaizhizao.purchaseOrder.pushInvoiceByRemaining'),
              disabled: record.capabilities?.push_invoice?.allowed !== true,
              title: capReason(record.capabilities?.push_invoice),
              onClick: () => {
                if (record.capabilities?.push_invoice?.allowed !== true) return;
                handlePushToInvoice(record, 'remaining');
              },
            },
            {
              key: 'invoice-prepayment',
              label: t('app.kuaizhizao.purchaseOrder.pushInvoiceByPrepayment'),
              disabled:
                record.capabilities?.push_invoice?.allowed !== true ||
                !(Number(record.prepayment_amount) > 0),
              title:
                record.capabilities?.push_invoice?.allowed !== true
                  ? capReason(record.capabilities?.push_invoice)
                  : !(Number(record.prepayment_amount) > 0)
                    ? t('app.kuaizhizao.purchaseOrder.pushInvoiceNoPrepayment')
                    : undefined,
              onClick: () => {
                if (record.capabilities?.push_invoice?.allowed !== true) return;
                if (!(Number(record.prepayment_amount) > 0)) return;
                handlePushToInvoice(record, 'prepayment');
              },
            },
          ],
        },
        {
          key: 'prepayment',
          label: pushToPrepaymentAction.label,
          disabled: record.capabilities?.push_prepayment?.allowed !== true,
          title: capReason(record.capabilities?.push_prepayment),
          onClick: () => {
            if (record.capabilities?.push_prepayment?.allowed !== true) return;
            handlePushToPrepayment(record);
          },
        },
        {
          key: 'payment-application',
          label: t('app.kuaizhizao.paymentApplication.pushFromPurchaseOrder'),
          disabled: record.capabilities?.push_payment_application?.allowed !== true,
          title: capReason(record.capabilities?.push_payment_application),
          onClick: () => {
            if (record.capabilities?.push_payment_application?.allowed !== true) return;
            handlePushToPaymentApplication(record);
          },
        },
        {
          key: 'incoming-inspection',
          label: pushToIncomingInspectionAction.label,
          disabled: record.capabilities?.push_incoming_inspection?.allowed !== true,
          title: capReason(record.capabilities?.push_incoming_inspection),
          onClick: () => {
            if (record.capabilities?.push_incoming_inspection?.allowed !== true) return;
            handlePushToIncomingInspection(record);
          },
        },
        {
          key: 'purchase-return',
          label: pushToPurchaseReturnAction.label,
          disabled: record.capabilities?.push_purchase_return?.allowed !== true,
          title: capReason(record.capabilities?.push_purchase_return),
          onClick: () => {
            if (record.capabilities?.push_purchase_return?.allowed !== true) return;
            handlePushToReturn(record);
          },
        },
        {
          key: 'purchase-order-change',
          label: pushToPurchaseOrderChangeAction.label,
          disabled: !canPushChange,
          title: changeDisabledReason,
          onClick: () => {
            if (!canPushChange || record.id == null) return;
            handlePushToPurchaseOrderChange(Number(record.id));
          },
        },
      ]);
    },
    [
      handlePushToIncomingInspection,
      handlePushToInvoice,
      handlePushToNotice,
      handlePushToPrepayment,
      handlePushToPaymentApplication,
      handlePushToPurchaseOrderChange,
      handlePushToReceipt,
      handlePushToReturn,
      purchaseOrderChangePerms.canCreate,
      pushToIncomingInspectionAction.label,
      pushToInvoiceAction.label,
      pushToPrepaymentAction.label,
      pushToPurchaseOrderChangeAction.label,
      pushToPurchaseReturnAction.label,
      pushToReceiptAction.label,
      pushToReceiptNoticeAction.label,
      t,
    ],
  );

  const toolbarPushMenuItems = useMemo(
    () => (selectedOrderForToolbar ? buildToolbarPushMenuItems(selectedOrderForToolbar) : buildUniPushMenuItems([])),
    [buildToolbarPushMenuItems, selectedOrderForToolbar],
  );

  const purchaseOrderToolbarPushDisabledReason = useMemo(() => {
    const base = buildUniPushToolbarDisabledReason(t, {
      selectedCount: selectedRowKeys.length,
      hasSelectedRecord: !!selectedOrderForToolbar,
    });
    if (base) return base;
    const caps = selectedOrderForToolbar?.capabilities;
    const anyAllowed =
      caps?.push_receipt_notice?.allowed === true ||
      caps?.push_receipt?.allowed === true ||
      caps?.push_invoice?.allowed === true ||
      caps?.push_prepayment?.allowed === true ||
      caps?.push_payment_application?.allowed === true ||
      caps?.push_incoming_inspection?.allowed === true ||
      caps?.push_purchase_return?.allowed === true ||
      (purchaseOrderChangePerms.canCreate && caps?.create_change_order?.allowed === true);
    if (!anyAllowed) {
      return (
        purchaseOrderCapabilityReasonMessage(
          caps?.push_receipt_notice?.reason ||
            caps?.push_receipt?.reason ||
            caps?.push_invoice?.reason ||
            caps?.push_prepayment?.reason ||
            caps?.push_payment_application?.reason ||
            caps?.push_incoming_inspection?.reason ||
            caps?.push_purchase_return?.reason ||
            caps?.create_change_order?.reason,
          t,
        ) || t('app.kuaizhizao.purchaseOrder.push.noActions')
      );
    }
    return undefined;
  }, [purchaseOrderChangePerms.canCreate, selectedOrderForToolbar, selectedRowKeys.length, t]);

  // 处理删除
  const executeDelete = async (record: PurchaseOrder) => {
    try {
          await deletePurchaseOrder(record.id!);
          messageApi.success(t('app.kuaizhizao.purchaseOrder.deleteSuccess'));
          if (orderDetail?.id === record.id) {
            setDetailDrawerVisible(false);
            setOrderDetail(null);
            resetPurchaseOrderDetailFieldValues();
          }
          invalidateStatistics();
          invalidateMenuBadgeCounts();
    actionRef.current?.reload();
        } catch (error: any) {
          messageApi.error(error.message || t('app.kuaizhizao.purchaseOrder.deleteFailed'));
        }
  };

  const handleDelete = async (record: PurchaseOrder) => {
    getAntdModal().confirm({
      title: t('app.kuaizhizao.purchaseOrder.deleteTitle'),
      content: t('app.kuaizhizao.purchaseOrder.deleteContent', { code: record.order_code }),
      okType: 'danger',
      onOk: () => executeDelete(record),
    });
  };

  const handleBatchDelete = async (keys: React.Key[]) => {
    if (keys.length === 0) return;
    try {
      for (const k of keys) {
        await deletePurchaseOrder(Number(k));
      }
      messageApi.success(t('app.kuaizhizao.purchaseOrder.batchDeleteSuccess', { count: keys.length }));
      setSelectedRowKeys([]);
      invalidateStatistics();
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error?.message || t('app.kuaizhizao.purchaseOrder.batchDeleteFailed'));
    }
  };

  const handleSyncComplete = useCallback(() => {
    setSyncFreshnessKey((key) => key + 1);
    invalidateStatistics();
    invalidateMenuBadgeCounts();
    actionRef.current?.reload();
  }, [invalidateStatistics, invalidateMenuBadgeCounts]);

  const handleListImport = async (data: any[][]) => {
    if (!data || data.length < 2) {
      messageApi.warning(t('app.kuaizhizao.purchaseOrder.importEmpty'));
      return;
    }
    const headers = (data[0] || []).map((h: any) => String(h || '').trim());
    const rows = data.slice(2).filter((row: any[]) => row?.some((c: any) => c != null && String(c).trim() !== ''));

    if (rows.length === 0) {
      messageApi.warning(t('app.kuaizhizao.purchaseOrder.importNoRows'));
      return;
    }

    const headerIndexMap = resolveFactoryImportHeaderIndexMap(
      headers,
      purchaseOrderImportTemplate.importHeaderMap,
    );
    const idx = {
      code: headerIndexMap['code'] ?? -1,
      supplier: headerIndexMap['supplier'] ?? -1,
      date: headerIndexMap['date'] ?? -1,
      material: headerIndexMap['material'] ?? -1,
      qty: headerIndexMap['quantity'] ?? -1,
      price: headerIndexMap['unitPrice'] ?? -1,
      delivery: headerIndexMap['delivery'] ?? -1,
      supplierContact: headerIndexMap['supplierContact'] ?? -1,
      supplierPhone: headerIndexMap['supplierPhone'] ?? -1,
      orderType: headerIndexMap['orderType'] ?? -1,
      buyer: headerIndexMap['buyer'] ?? -1,
      currency: headerIndexMap['currency'] ?? -1,
      priceType: headerIndexMap['priceType'] ?? -1,
      notes: headerIndexMap['notes'] ?? -1,
    };

    if (idx.supplier < 0 || idx.date < 0 || idx.material < 0 || idx.qty < 0 || idx.price < 0) {
      messageApi.error(t('app.kuaizhizao.purchaseOrder.importMissingColumns'));
      return;
    }

    const matList = await resolveMaterialsByCodesForImport(
      collectImportMaterialCodes(rows, idx.material),
      [],
    );

    const errors: Array<{ row: number; message: string }> = [];
    const groupMap = new Map<string, { code?: string; supplier: string; date: string; items: any[] }>();

    rows.forEach((row: any[], i: number) => {
      const rowNum = i + 3;
      const supplierName = (row[idx.supplier] ?? '').toString().trim();
      const dateVal = (row[idx.date] ?? '').toString().trim();
      const materialCode = normalizeImportMaterialCode(row[idx.material]);
      const qtyVal = row[idx.qty];
      const qty = Number(qtyVal);
      if (!supplierName) {
        errors.push({ row: rowNum, message: t('app.kuaizhizao.purchaseOrder.importRowSupplierRequired') });
        return;
      }
      if (!dateVal) {
        errors.push({ row: rowNum, message: t('app.kuaizhizao.purchaseOrder.importRowOrderDateRequired') });
        return;
      }
      if (!materialCode) {
        errors.push({ row: rowNum, message: t('app.kuaizhizao.purchaseOrder.importRowMaterialRequired') });
        return;
      }
      if (isNaN(qty) || qty <= 0) {
        errors.push({ row: rowNum, message: t('app.kuaizhizao.purchaseOrder.importRowQtyRequired') });
        return;
      }
      const priceVal = row[idx.price];
      const price = Number(priceVal);
      if (priceVal == null || String(priceVal).trim() === '' || !Number.isFinite(price) || price <= 0) {
        errors.push({ row: rowNum, message: t('app.kuaizhizao.purchaseOrder.importRowUnitPriceRequired') });
        return;
      }

      const mat = findMaterialByImportCode(matList, materialCode);
      if (!mat) {
        errors.push({ row: rowNum, message: t('app.kuaizhizao.purchaseOrder.importRowMaterialNotFound', { code: materialCode }) });
        return;
      }

      const code = idx.code >= 0 ? (row[idx.code] ?? '').toString().trim() : '';
      const delivery = idx.delivery >= 0 ? (row[idx.delivery] ?? '').toString().trim() : undefined;
      const notes = idx.notes >= 0 ? (row[idx.notes] ?? '').toString().trim() : undefined;

      const groupKey = code || `${supplierName}|${dateVal}`;
      if (!groupMap.has(groupKey)) {
        groupMap.set(groupKey, {
          code: code || undefined,
          supplier: supplierName,
          date: dateVal,
          supplierContact: idx.supplierContact >= 0 ? String(row[idx.supplierContact] ?? '').trim() || undefined : undefined,
          supplierPhone: idx.supplierPhone >= 0 ? String(row[idx.supplierPhone] ?? '').trim() || undefined : undefined,
          orderType: idx.orderType >= 0 ? purchaseOrderImportDict.parseDict('ORDER_TYPE', String(row[idx.orderType] ?? '').trim()) || undefined : undefined,
          buyer: idx.buyer >= 0 ? String(row[idx.buyer] ?? '').trim() || undefined : undefined,
          currency: idx.currency >= 0 ? purchaseOrderImportDict.parseDict('CURRENCY', String(row[idx.currency] ?? '').trim()) || undefined : undefined,
          priceType: idx.priceType >= 0 ? parseImportPriceType(String(row[idx.priceType] ?? '').trim(), t) : undefined,
          items: [],
        });
      }
      const g = groupMap.get(groupKey)!;
      g.items.push({
        material_id: mat.id,
        material_code: mat.mainCode || mat.code,
        material_name: mat.name,
        material_spec: mat.specification || '',
        unit: mat.baseUnit || '件',
        ordered_quantity: qty,
        unit_price: price,
        required_date: delivery || undefined,
        notes: notes || undefined,
      });
    });

    if (errors.length > 0) {
      getAntdModal().warning({
        title: t('app.kuaizhizao.purchaseOrder.importValidationTitle'),
        width: 600,
        content: (
          <div>
            <p>{t('app.kuaizhizao.purchaseOrder.importValidationIntro')}</p>
            <List size="small" dataSource={errors} renderItem={(item) => (
              <List.Item><Typography.Text type="danger">{t('app.kuaizhizao.purchaseOrder.importRowError', { row: item.row, message: item.message })}</Typography.Text></List.Item>
            )} />
          </div>
        ),
      });
      return;
    }

    const toImport: Partial<PurchaseOrder>[] = [];
    groupMap.forEach((g) => {
      const supp = supplierList.find((s: any) => ((s.name || s.code || '').trim() === g.supplier.trim()) || ((s.supplier_name || '').trim() === g.supplier.trim()));
      toImport.push({
        order_code: g.code,
        order_date: g.date,
        supplier_id: supp?.id,
        supplier_name: g.supplier,
        supplier_contact: g.supplierContact,
        supplier_phone: g.supplierPhone,
        order_type: g.orderType,
        buyer_name: g.buyer,
        currency: g.currency,
        price_type: g.priceType,
        status: '草稿',
        items: g.items,
      });
    });

    if (toImport.length === 0) {
      messageApi.warning(t('app.kuaizhizao.purchaseOrder.importNoData'));
      return;
    }

    try {
      const result = await importInChunksViaPerItemCreate({
        items: toImport,
        createOne: async (item, _index) => createPurchaseOrder(item),
        title: t('app.kuaizhizao.purchaseOrder.importingTitle'),
        chunkSize: 100,
        concurrency: 4,
      });

      if (result.failureCount > 0) {
        getAntdModal().warning({
          title: t('app.kuaizhizao.purchaseOrder.importPartialTitle'),
          width: 600,
          content: (
            <div>
              <p><strong>{t('app.kuaizhizao.purchaseOrder.importPartialSummary', { success: result.successCount, failed: result.failureCount })}</strong></p>
              {result.errors.length > 0 && (
                <List size="small" dataSource={result.errors} renderItem={(e) => (
                  <List.Item><Typography.Text type="danger">{t('app.kuaizhizao.purchaseOrder.importPartialRowError', { row: e.row, error: e.error })}</Typography.Text></List.Item>
                )} />
              )}
            </div>
          ),
        });
      } else {
        messageApi.success(t('app.kuaizhizao.purchaseOrder.importSuccess', { count: result.successCount }));
      }
      if (result.successCount > 0) {
        invalidateStatistics();
        invalidateMenuBadgeCounts();
    actionRef.current?.reload();
      }
    } catch (error: any) {
      messageApi.error(error?.message || t('app.kuaizhizao.purchaseOrder.importFailed'));
    }
  };

  async function initPurchaseOrderEditForm(orderId: number) {
    try {
      const detail = await getPurchaseOrder(orderId);
      setIsEdit(true);
      setCurrentOrder(detail);
      const headerTaxRatePercent = purchaseOrderTaxRateToPercent(detail.tax_rate);
      const storedPriceType = String(
        (detail as { price_type?: string; priceType?: string }).price_type ??
          (detail as { priceType?: string }).priceType ??
          '',
      ).trim();
      const priceType: PriceTypeValue =
        storedPriceType === 'tax_inclusive' || storedPriceType === 'tax_exclusive'
          ? storedPriceType
          : headerTaxRatePercent > 0
            ? 'tax_inclusive'
            : 'tax_exclusive';
      const items = (detail.items || []).map((it: any) => {
        const lineTaxPercent =
          it.tax_rate != null && Number(it.tax_rate) > 0
            ? purchaseOrderTaxRateToPercent(it.tax_rate)
            : headerTaxRatePercent;
        return {
        id: it.id ?? it.itemId,
        material_id: it.material_id ?? it.materialId,
        material_code: it.material_code || it.materialCode || '',
        material_name: it.material_name || it.materialName || '',
        material_spec: it.material_spec || '',
        unit: it.unit || '件',
        ordered_quantity: Number(it.ordered_quantity ?? it.orderedQuantity) || 0,
        aux_quantity:
          it.aux_quantity != null
            ? Number(it.aux_quantity)
            : it.auxQuantity != null
              ? Number(it.auxQuantity)
              : undefined,
        aux_unit: it.aux_unit ?? it.auxUnit ?? undefined,
        unit_conversion_rate:
          it.unit_conversion_rate != null
            ? Number(it.unit_conversion_rate)
            : it.unitConversionRate != null
              ? Number(it.unitConversionRate)
              : undefined,
        unit_price: readPurchaseOrderEnteredUnitPrice(
          {
            display_unit_price: it.display_unit_price ?? it.displayUnitPrice,
            unit_price: it.unit_price ?? it.unitPrice,
          },
          priceType,
        ),
        tax_rate: lineTaxPercent,
        required_date: it.required_date || it.requiredDate ? dayjs(it.required_date || it.requiredDate) : undefined,
        source_type: it.source_type ?? it.sourceType ?? null,
        source_id: it.source_id ?? it.sourceId ?? null,
        demand_computation_item_id:
          it.demand_computation_item_id ?? it.demandComputationItemId ?? null,
        work_order_id: it.work_order_id ?? it.workOrderId ?? null,
        work_order_code: it.work_order_code ?? it.workOrderCode ?? null,
        received_quantity: Number(it.received_quantity ?? it.receivedQuantity) || 0,
        notes: it.notes ?? '',
        attachments: mapAttachmentsToUploadList(it.attachments),
      };
      });
      window.setTimeout(() => {
        const deliveryDate = detail.delivery_date ? dayjs(detail.delivery_date) : undefined;
        formRef.current?.setFieldsValue({
          order_code: detail.order_code,
          supplier_id: detail.supplier_id,
          supplier_name: detail.supplier_name,
          supplier_contact: detail.supplier_contact,
          supplier_phone: detail.supplier_phone,
          order_date: detail.order_date,
          delivery_date: deliveryDate,
          payment_milestones: ((detail as any).payment_milestones ?? []).map((ms: any) => ({
            ...ms,
            id: ms.id && ms.id > 0 ? ms.id : undefined,
            is_prepayment: Boolean(ms.is_prepayment),
            auto_generate_payable: Boolean(ms.auto_generate_payable),
            planned_date: ms.planned_date ? dayjs(ms.planned_date) : undefined,
          })),
          order_type: detail.order_type || '标准采购',
          payable_recognition:
            (detail as { payable_recognition?: string; payableRecognition?: string }).payable_recognition ??
            (detail as { payableRecognition?: string }).payableRecognition ??
            orgPayableRecognitionDefault,
          payment_method_code: (detail as { payment_method_code?: string | null }).payment_method_code ?? undefined,
          payment_wire_percent:
            (detail as { payment_wire_percent?: number | null }).payment_wire_percent ?? undefined,
          payment_acceptance_percent:
            (detail as { payment_acceptance_percent?: number | null }).payment_acceptance_percent ??
            undefined,
          advance_payee_id:
            (detail as { advance_payee_id?: number | null }).advance_payee_id ?? undefined,
          advance_payee_name:
            (detail as { advance_payee_name?: string | null }).advance_payee_name ?? undefined,
          settlement_terms_code:
            (detail as { settlement_terms_code?: string | null }).settlement_terms_code ?? undefined,
          payment_terms_days:
            (detail as { payment_terms_days?: number | null }).payment_terms_days ?? undefined,
          currency: detail.currency || 'CNY',
          exchange_rate: detail.exchange_rate ?? 1,
          price_type: priceType,
          buyer_id: detail.buyer_id,
          buyer_name: detail.buyer_name,
          department_id:
            (detail as { department_id?: number | null }).department_id ?? undefined,
          department_name:
            (detail as { department_name?: string | null }).department_name ?? undefined,
          notes: detail.notes,
          attachments: (detail as any).attachments || [],
          fee_details: (detail as any).fee_details || [],
          items: items.length > 0 ? items : [defaultOrderItem],
        });
        lastHeaderDeliveryRef.current = coerceFormDate(deliveryDate);
        loadPurchaseOrderFormFieldValues(orderId).then((fieldFormValues) => {
          formRef.current?.setFieldsValue(fieldFormValues);
        });
      }, 100);
    } catch {
      messageApi.error(t('app.kuaizhizao.purchaseOrder.detailFailed'));
      leavePurchaseOrderFormPage();
    }
  }

  const createFormSeed = useMemo(() => {
    if (!isCreatePage) return null;
    const flowBodyFromState =
      location.state &&
      typeof location.state === 'object' &&
      (location.state as { documentFlowCreate?: unknown }).documentFlowCreate &&
      typeof (location.state as { documentFlowCreate?: unknown }).documentFlowCreate === 'object'
        ? ((location.state as { documentFlowCreate: Record<string, unknown> }).documentFlowCreate)
        : null;
    const sp = new URLSearchParams(location.search || '');
    sp.delete('_refresh');
    const draftSearch = sp.toString() ? `?${sp.toString()}` : '';
    const draftKey = buildDocumentCreateDraftKey(
      'kuaizhizao:purchase-order',
      location.pathname,
      draftSearch,
    );
    const flowBodyFromDraft =
      !flowBodyFromState ? getDocumentFormDraft<Record<string, unknown>>(draftKey) : null;
    const flowBody = flowBodyFromState ?? flowBodyFromDraft;
    if (flowBody) {
      const {
        _documentFlowMeta: _meta,
        documentFlowSourceType: _documentFlowSourceType,
        documentFlowRequisitionItemIds: _documentFlowRequisitionItemIds,
        documentFlowInquiryItemIds: _documentFlowInquiryItemIds,
        documentFlowDemandComputationItemIds: _documentFlowDemandComputationItemIds,
        documentFlowDemandComputationIds: _documentFlowDemandComputationIds,
        documentFlowReplenishmentSuggestionIds: _documentFlowReplenishmentSuggestionIds,
        documentFlowSalesOrderId: _documentFlowSalesOrderId,
        documentFlowItemQuantities: _documentFlowItemQuantities,
        documentFlowItemUnitPrices: _documentFlowItemUnitPrices,
        documentFlowItemSuppliers: _documentFlowItemSuppliers,
        documentFlowPersistDefaultSupplier: _documentFlowPersistDefaultSupplier,
        ...rawValues
      } = flowBody;
      const hydrated = hydrateDocumentFlowCreateFormValues(rawValues);
      const items = normalizeFormListItems<any>(hydrated.items).map((item) => {
        const midRaw = item.material_id ?? item.materialId;
        const mid = midRaw != null ? Number(midRaw) : NaN;
        return {
          ...item,
          material_id: Number.isFinite(mid) && mid > 0 ? mid : undefined,
          material_code: item.material_code ?? item.materialCode ?? '',
          material_name: item.material_name ?? item.materialName ?? '',
          material_spec: item.material_spec ?? item.materialSpec ?? '',
          material_model: item.material_model ?? item.materialModel ?? '',
          partner_material_code:
            item.partner_material_code ?? item.partnerMaterialCode ?? '',
          partner_material_name:
            item.partner_material_name ?? item.partnerMaterialName ?? '',
          unit: item.unit || '件',
          ordered_quantity: Number(item.ordered_quantity ?? item.orderedQuantity) || 0,
          unit_price: Number(item.unit_price ?? item.unitPrice) || 0,
          tax_rate:
            item.tax_rate != null
              ? Number(item.tax_rate)
              : DEFAULT_PURCHASE_TAX_RATE_PERCENT,
          required_date:
            item.required_date != null
              ? coerceFormDate(item.required_date) ?? undefined
              : undefined,
          source_type: item.source_type ?? item.sourceType ?? null,
          source_id: item.source_id ?? item.sourceId ?? null,
          demand_computation_item_id:
            item.demand_computation_item_id ?? item.demandComputationItemId ?? null,
          work_order_id: item.work_order_id ?? item.workOrderId ?? null,
          work_order_code: item.work_order_code ?? item.workOrderCode ?? null,
          notes: item.notes ?? '',
          attachments: mapAttachmentsToUploadList(item.attachments),
        };
      });
      const supplierIdRaw = hydrated.supplier_id ?? hydrated.supplierId;
      const supplierIdNum =
        supplierIdRaw != null && Number.isFinite(Number(supplierIdRaw))
          ? Number(supplierIdRaw)
          : undefined;
      return {
        ...hydrated,
        price_type:
          (hydrated.price_type as string | undefined) ?? DEFAULT_PURCHASE_PRICE_TYPE,
        payable_recognition:
          (hydrated.payable_recognition as string | undefined) ??
          (hydrated.payableRecognition as string | undefined) ??
          orgPayableRecognitionDefault,
        items:
          items.length > 0
            ? items
            : [{ ...defaultOrderItem, tax_rate: DEFAULT_PURCHASE_TAX_RATE_PERCENT }],
        supplier_id: supplierIdNum != null && supplierIdNum > 0 ? supplierIdNum : undefined,
        order_date: coerceFormDate(hydrated.order_date) ?? dayjs(),
        delivery_date: coerceFormDate(hydrated.delivery_date) ?? undefined,
        ...((hydrated.buyer_id == null || hydrated.buyer_id === '') &&
        (hydrated.buyerId == null || hydrated.buyerId === '')
          ? resolveDefaultPurchaseOrderBuyer()
          : {}),
      };
    }
    if (sp.get('flow')) return null;
    return {
      items: [{ ...defaultOrderItem, tax_rate: DEFAULT_PURCHASE_TAX_RATE_PERCENT }],
      price_type: DEFAULT_PURCHASE_PRICE_TYPE,
      payable_recognition: orgPayableRecognitionDefault,
      order_date: dayjs(),
      ...resolveDefaultPurchaseOrderBuyer(),
    };
  }, [
    isCreatePage,
    location.pathname,
    location.search,
    location.state,
    orgPayableRecognitionDefault,
  ]);

  const { markSupplierHydrated } = useHydrateSupplierOnCreatePrefill({
    enabled: isCreatePage,
    formRef,
    supplierId:
      createFormSeed?.supplier_id != null ? Number(createFormSeed.supplier_id) : undefined,
    supplierList: supplierList as Array<Record<string, unknown>>,
    users,
    orgPayableDefault: orgPayableRecognitionDefault,
    defaultCurrency: defaultPurchaseOrderCurrency,
    hostResource: KUAIZHIZAO_DOC_HOST.purchaseOrder,
  });

  const handoffRepriceOnceRef = useRef(false);
  useEffect(() => {
    if (!isCreatePage || handoffRepriceOnceRef.current) return;
    const flow = new URLSearchParams(location.search || '').get('flow');
    if (flow !== 'purchase_requisition' && flow !== 'purchase_inquiry') return;
    const form = formRef.current;
    if (!form || !createFormSeed) return;
    const supplierId = Number(form.getFieldValue('supplier_id') ?? createFormSeed.supplier_id);
    if (!Number.isFinite(supplierId) || supplierId <= 0) return;
    const items = normalizeFormListItems<Record<string, unknown>>(form.getFieldValue('items'));
    const lineNeedsWork = (line: Record<string, unknown>) => {
      const mid = Number(line.material_id ?? line.materialId);
      if (!Number.isFinite(mid) || mid <= 0) return false;
      const priceRaw = line.unit_price ?? line.unitPrice;
      const needPrice =
        priceRaw == null || priceRaw === '' || !Number.isFinite(Number(priceRaw));
      const code = String(line.partner_material_code ?? line.partnerMaterialCode ?? '').trim();
      const name = String(line.partner_material_name ?? line.partnerMaterialName ?? '').trim();
      const needPartner = !code || !name;
      return needPrice || needPartner;
    };
    if (!items.some(lineNeedsWork)) return;
    handoffRepriceOnceRef.current = true;
    void (async () => {
      const fallbackTaxRate = resolveSupplierDefaultTaxRatePercent(
        (supplierList.find((x) => Number(x.id) === supplierId) as Record<string, unknown> | undefined) ?? null,
      );
      for (let index = 0; index < items.length; index += 1) {
        if (!lineNeedsWork(items[index])) continue;
        await repriceUnlockedPurchaseDocumentLineIfNeeded(form, index, {
          asOfField: 'order_date',
          trigger: 'partner',
          supplierId,
          fallbackTaxRate,
        });
      }
    })();
  }, [isCreatePage, createFormSeed, location.search, supplierList]);

  const handleEdit = (record: PurchaseOrder) => {
    if (!record.id) return;
    navigate(purchaseOrderEditPath(record.id));
  };

  const handleCreate = () => {
    if (requirePurchaseRequisition) {
      messageApi.warning('当前组织要求先采购申请后下单，请从采购申请加载');
      pullFromRequisitionQuery.openModal();
      return;
    }
    navigate(PURCHASE_ORDER_CREATE_PATH);
  };

  useEffect(() => {
    if (!isCreatePage || !requirePurchaseRequisition) return;
    messageApi.warning('当前组织要求先采购申请后下单，请从采购申请加载');
    navigate(PURCHASE_ORDER_LIST_PATH, { replace: true });
    pullFromRequisitionQuery.openModal();
  }, [isCreatePage, requirePurchaseRequisition]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!isFormPage) {
      formPageInitializedRef.current = false;
      return;
    }
    const titleKey = isCreatePage
      ? 'app.kuaizhizao.menu.purchase-management.purchase-orders.new'
      : 'app.kuaizhizao.menu.purchase-management.purchase-orders.edit';
    const title = t(titleKey);
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

  // 新建：对齐销售订单 createFormSeed —— 只挂 documentFlow 回写 extras，不靠 setTimeout 灌表
  useEffect(() => {
    if (!isCreatePage) {
      documentFlowSubmitExtrasRef.current = null;
      purchaseOrderCreateDraftKeyRef.current = null;
      // 进入编辑路由后以 editRouteId 为准；离开新建页清掉 create 钉住
      if (!isEditPage) {
        createdOrderIdRef.current = null;
      }
      return;
    }
    if (!createFormSeed) {
      documentFlowSubmitExtrasRef.current = null;
      purchaseOrderCreateDraftKeyRef.current = null;
      return;
    }
    setIsEdit(false);
    setCurrentOrder(null);
    createdOrderIdRef.current = null;
    resetPurchaseOrderFormFieldValues();
    lastHeaderDeliveryRef.current = coerceFormDate(createFormSeed.delivery_date);

    const flowBodyFromState =
      location.state &&
      typeof location.state === 'object'
        ? (location.state as { documentFlowCreate?: Record<string, unknown> }).documentFlowCreate
        : undefined;
    const sp = new URLSearchParams(location.search || '');
    sp.delete('_refresh');
    const draftSearch = sp.toString() ? `?${sp.toString()}` : '';
    const draftKey = buildDocumentCreateDraftKey(
      'kuaizhizao:purchase-order',
      location.pathname,
      draftSearch,
    );
    purchaseOrderCreateDraftKeyRef.current = draftKey;
    const flowBody =
      flowBodyFromState ?? getDocumentFormDraft<Record<string, unknown>>(draftKey) ?? null;
    if (!flowBody || !sp.get('flow')) {
      documentFlowSubmitExtrasRef.current = null;
      if (!sp.get('flow')) {
        purchaseOrderCreateDraftKeyRef.current = null;
      }
      return;
    }
    documentFlowSubmitExtrasRef.current = {
      documentFlowSourceType: flowBody.documentFlowSourceType,
      documentFlowRequisitionItemIds: flowBody.documentFlowRequisitionItemIds,
      documentFlowInquiryItemIds: flowBody.documentFlowInquiryItemIds,
      documentFlowDemandComputationItemIds: flowBody.documentFlowDemandComputationItemIds,
      documentFlowDemandComputationIds: flowBody.documentFlowDemandComputationIds,
      documentFlowReplenishmentSuggestionIds: flowBody.documentFlowReplenishmentSuggestionIds,
      documentFlowSalesOrderId: flowBody.documentFlowSalesOrderId,
      documentFlowItemQuantities: flowBody.documentFlowItemQuantities,
      documentFlowItemUnitPrices: flowBody.documentFlowItemUnitPrices,
      documentFlowItemSuppliers: flowBody.documentFlowItemSuppliers,
      documentFlowPersistDefaultSupplier: flowBody.documentFlowPersistDefaultSupplier,
    };
  }, [
    createFormSeed,
    isCreatePage,
    location.pathname,
    location.search,
    location.state,
  ]);

  useEffect(() => {
    if (!isFormPage || formPageInitializedRef.current) return;
    if (isCreatePage) return;
    formPageInitializedRef.current = true;
    if (editRouteId) {
      void initPurchaseOrderEditForm(editRouteId);
    }
  }, [isFormPage, isCreatePage, editRouteId]);

  const pullRequisitionColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.purchaseOrder.col.requisitionCode'),
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
        title: t('app.kuaizhizao.purchaseOrder.col.applicant'),
        dataIndex: 'applicant_name',
        width: 100,
        ellipsis: true,
        render: (v: string | null | undefined) => (v && String(v).trim() ? String(v) : '-'),
      },
      {
        title: t('app.kuaizhizao.purchaseOrder.col.orderType'),
        dataIndex: 'order_type',
        width: 96,
        ellipsis: true,
        render: (v: string | null | undefined) =>
          v && String(v).trim() ? String(v) : '—',
      },
      buildPullQueryMaterialIdentityColumn<PullPurchaseRequisitionCandidate>(t),
      {
        title: t('app.kuaizhizao.purchaseRequisition.form.suggestedSupplier'),
        dataIndex: 'supplier_name',
        width: 128,
        ellipsis: true,
        render: (v: string | null | undefined) => (v && String(v).trim() ? String(v).trim() : '—'),
      },
      buildDocumentAttachmentsListColumn<PullPurchaseRequisitionCandidate>(t),
      ...pullRequisitionQtyColumns.slice(0, 2),
      {
        title: t('app.kuaizhizao.purchaseRequisition.col.department'),
        dataIndex: 'department_name',
        width: 120,
        ellipsis: true,
        render: (v: string | null | undefined) => (v && String(v).trim() ? String(v) : '-'),
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
        title: t('app.kuaizhizao.purchaseOrder.col.demandDate'),
        dataIndex: 'required_date',
        width: 112,
        render: (v: string) => (v ? formatBusinessDateOnly(v) : '-'),
      },
      {
        title: t('app.kuaizhizao.purchaseRequisition.pull.convertStatus'),
        key: 'convert_status',
        width: 100,
        align: 'center' as const,
        render: (_: unknown, record: PullPurchaseRequisitionCandidate) =>
          renderPullCapabilityTag(
            isPullOpenLineSelectable(record),
            t('app.kuaizhizao.purchaseRequisition.pull.canCreate'),
            t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
          ),
      },
    ],
    [t],
  );

  const pullInquiryColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.purchaseOrder.col.inquiryCode'),
        dataIndex: 'inquiry_code',
        width: 168,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialName'),
        dataIndex: 'material_name',
        ellipsis: true,
        render: (_: unknown, record: PullPurchaseInquiryCandidate) => (
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
        sorter: (a: PullPurchaseInquiryCandidate, b: PullPurchaseInquiryCandidate) =>
          String(a.document_date || a.inquiry_date || '').localeCompare(
            String(b.document_date || b.inquiry_date || ''),
          ),
        defaultSortOrder: 'descend' as const,
        render: (_: unknown, record: PullPurchaseInquiryCandidate) => {
          const raw = record.document_date || record.inquiry_date;
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
        title: t('app.kuaizhizao.purchaseOrder.col.demandDate'),
        dataIndex: 'required_date',
        width: 112,
        render: (v: string) => (v ? formatBusinessDateOnly(v) : '-'),
      },
      {
        title: t('app.kuaizhizao.purchaseRequisition.pull.convertStatus'),
        key: 'convert_status',
        width: 100,
        align: 'center' as const,
        render: (_: unknown, record: PullPurchaseInquiryCandidate) =>
          renderPullCapabilityTag(
            isPullOpenLineSelectable(record),
            t('app.kuaizhizao.purchaseRequisition.pull.canCreate'),
            t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
          ),
      },
    ],
    [t],
  );

  const pullSalesOrderColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.salesOrder.orderCode'),
        dataIndex: 'order_code',
        width: 168,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.salesOrder.customerName'),
        dataIndex: 'customer_name',
        ellipsis: true,
        render: (v: string | null | undefined) => (v && String(v).trim() ? String(v) : '-'),
      },
      {
        title: t('components.uniPullQuery.documentDateColumn'),
        dataIndex: 'order_date',
        width: 112,
        render: (v: string | null | undefined) => (v ? formatBusinessDateOnly(String(v)) : '-'),
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
        title: t('app.kuaizhizao.pullOpenLine.colPushedPurchaseOrderQty'),
        dataIndex: 'pushed_purchase_quantity',
        width: 100,
        align: 'right' as const,
        render: (v: number | undefined, record: PurchaseOrderSalesOrderPullLine) =>
          formatQuantity(Number(v ?? record.pushed_quantity ?? 0)),
      },
      {
        title: t('app.kuaizhizao.pullOpenLine.colTransferableQty'),
        dataIndex: 'remaining_quantity',
        width: 100,
        align: 'right' as const,
        render: (v: number) => formatQuantity(v),
      },
    ],
    [t],
  );

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
      pullSourceOrderTypeRef.current = undefined;
      setPullSourceOrderType(undefined);
      void loadPullSourceReferenceOptions({
        resource: PULL_SOURCE_REFERENCE.purchaseRequisition,
        hostResource: PURCHASE_ORDER_RESOURCE,
        maxItems: 500,
      })
        .then(setPullSourceRequisitionOptions)
        .catch((error: unknown) => {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.pull.loadSourceFailed')));
          setPullSourceRequisitionOptions([]);
        });
    },
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const listRes = await listPurchaseRequisitionPurchaseOrderPullLines({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          keyword: keyword.trim() || undefined,
          requisition_id: pullSourceRequisitionIdRef.current,
          order_type: pullSourceOrderTypeRef.current,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.loadRequisitionListFailed')));
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullOpenLineSelectable(record),
    onConfirm: async (_keys, rows) => {
      const selectedIds = rows
        .filter((row) => isPullOpenLineSelectable(row))
        .map((row) => Number(row.id))
        .filter((id) => id > 0);
      if (!selectedIds.length) {
        messageApi.warning(t('app.kuaizhizao.purchaseOrder.pull.selectLinesFirst'));
        return;
      }
      try {
        const res = await pullPurchaseOrdersFromRequisitionItems(selectedIds);
        const createdCodes = (res.purchase_orders ?? [])
          .map((po) => po.purchase_order_code)
          .filter(Boolean);
        messageApi.success(
          createdCodes.length
            ? t('app.kuaizhizao.purchaseOrder.createdFromRequisition', {
                target: pullFromRequisitionAction.targetLabel,
                codes: createdCodes.join('、'),
              })
            : res.message || t('app.kuaizhizao.purchaseOrder.pull.ok'),
        );
        pullFromRequisitionQuery.closeModal();
        invalidateMenuBadgeCounts();
        invalidateStatistics();
    actionRef.current?.reload();
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(
            error,
            t('app.kuaizhizao.purchaseOrder.createFromRequisitionFailed', {
              source: pullFromRequisitionAction.sourceLabel,
              target: pullFromRequisitionAction.targetLabel,
            }),
          ),
        );
      }
    },
  });

  const pullFromInquiryQuery = useUniPullQuery<PullPurchaseInquiryCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullDocumentScopeOptions,
    defaultScope: 'pullable',
    onOpen: () => {
      pullSourceInquiryIdRef.current = undefined;
      setPullSourceInquiryId(undefined);
      void listPurchaseInquiries({ skip: 0, limit: 100 })
        .then((res) => {
          setPullSourceInquiryOptions(
            (res?.data ?? [])
              .filter((row) => row.id != null && row.inquiry_code)
              .map((row) => ({ value: row.id!, label: String(row.inquiry_code) })),
          );
        })
        .catch((error: unknown) => {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.pull.loadSourceFailed')));
          setPullSourceInquiryOptions([]);
        });
    },
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const listRes = await listPurchaseInquiryPurchaseOrderPullLines({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          keyword: keyword.trim() || undefined,
          inquiry_id: pullSourceInquiryIdRef.current,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.loadInquiryListFailed')));
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullOpenLineSelectable(record),
    onConfirm: async (_keys, rows) => {
      const selectedIds = rows
        .filter((row) => isPullOpenLineSelectable(row))
        .map((row) => Number(row.id))
        .filter((id) => id > 0);
      if (!selectedIds.length) {
        messageApi.warning(t('app.kuaizhizao.purchaseOrder.pull.selectLinesFirst'));
        return;
      }
      try {
        const res = await pullPurchaseOrdersFromInquiryItems(selectedIds);
        const createdCodes = (res.purchase_orders ?? [])
          .map((po) => po.purchase_order_code)
          .filter(Boolean);
        messageApi.success(
          createdCodes.length
            ? t('app.kuaizhizao.purchaseOrder.createdFromRequisition', {
                target: pullFromInquiryAction.targetLabel,
                codes: createdCodes.join('、'),
              })
            : res.message || t('app.kuaizhizao.purchaseOrder.pull.ok'),
        );
        pullFromInquiryQuery.closeModal();
        invalidateMenuBadgeCounts();
        invalidateStatistics();
    actionRef.current?.reload();
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(
            error,
            t('app.kuaizhizao.purchaseOrder.createFromRequisitionFailed', {
              source: pullFromInquiryAction.sourceLabel,
              target: pullFromInquiryAction.targetLabel,
            }),
          ),
        );
      }
    },
  });

  const pullFromSalesOrderQuery = useUniPullQuery<PurchaseOrderSalesOrderPullCandidate>({
    rowKey: 'id',
    selectionType: 'radio',
    scopeOptions: pullDocumentScopeOptions,
    defaultScope: 'pullable',
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const listRes = await listPurchaseOrderSalesOrderPullOrders({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          keyword: keyword.trim() || undefined,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.purchaseOrder.pull.loadSourceFailed')));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (_keys, rows) => {
      const orderId = Number(rows[0]?.id);
      if (!orderId) {
        messageApi.warning(t('app.kuaizhizao.purchaseOrder.pull.selectLinesFirst'));
        return;
      }
      try {
        await handoffSalesOrderToPurchaseOrderCreate(navigate, orderId, {});
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
            t('app.kuaizhizao.purchaseOrder.createFromRequisitionFailed', {
              source: pullFromSalesOrderAction.sourceLabel,
              target: pullFromSalesOrderAction.targetLabel,
            }),
          ),
        );
      }
    },
  });

  const handleCopySelectedPurchaseOrder = useCallback(async () => {
    if (requirePurchaseRequisition) {
      messageApi.warning('当前组织要求先采购申请后下单，请从采购申请加载');
      pullFromRequisitionQuery.openModal();
      return;
    }
    const orderId = selectedOrderForToolbar?.id;
    if (orderId == null) return;
    try {
      const detail = await getPurchaseOrder(Number(orderId));
      const customValues = await loadPurchaseOrderFormFieldValues(Number(orderId));
      const headerTaxRatePercent = purchaseOrderTaxRateToPercent(detail.tax_rate);
      const storedPriceType = String(
        (detail as { price_type?: string; priceType?: string }).price_type ??
          (detail as { priceType?: string }).priceType ??
          '',
      ).trim();
      const priceType: PriceTypeValue =
        storedPriceType === 'tax_inclusive' || storedPriceType === 'tax_exclusive'
          ? storedPriceType
          : headerTaxRatePercent > 0
            ? 'tax_inclusive'
            : 'tax_exclusive';
      const plainValue = (value: unknown): unknown => {
        if (dayjs.isDayjs(value)) return value.format('YYYY-MM-DD HH:mm:ss');
        if (Array.isArray(value)) return value.map(plainValue);
        if (value && typeof value === 'object') {
          const out: Record<string, unknown> = {};
          for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
            out[key] = plainValue(nested);
          }
          return out;
        }
        return value;
      };
      const items = (detail.items || []).map((raw) => {
        const it = raw as PurchaseOrderItem & {
          partner_material_code?: string | null;
          partner_material_name?: string | null;
          attachments?: Parameters<typeof mapAttachmentsToUploadList>[0];
        };
        const qty = Number(it.ordered_quantity) || 0;
        const dual = it as PurchaseOrderItem & {
          aux_quantity?: number | null;
          aux_unit?: string | null;
          unit_conversion_rate?: number | null;
        };
        return {
          material_id: it.material_id,
          material_code: it.material_code || '',
          material_name: it.material_name || '',
          material_spec: it.material_spec || '',
          partner_material_code: it.partner_material_code ?? '',
          partner_material_name: it.partner_material_name ?? '',
          unit: it.unit || '件',
          ordered_quantity: qty,
          aux_quantity: dual.aux_quantity != null ? Number(dual.aux_quantity) : undefined,
          aux_unit: dual.aux_unit ?? undefined,
          unit_conversion_rate:
            dual.unit_conversion_rate != null ? Number(dual.unit_conversion_rate) : undefined,
          unit_price: readPurchaseOrderEnteredUnitPrice(
            {
              display_unit_price: (it as { display_unit_price?: unknown; displayUnitPrice?: unknown }).display_unit_price
                ?? (it as { displayUnitPrice?: unknown }).displayUnitPrice,
              unit_price: it.unit_price,
            },
            priceType,
          ),
          tax_rate: headerTaxRatePercent,
          required_date: it.required_date || undefined,
          notes: it.notes ?? '',
          attachments: mapAttachmentsToUploadList(it.attachments),
        };
      });
      const milestones = (detail.payment_milestones ?? []).map((ms) => ({
        milestone_name: ms.milestone_name,
        planned_date: ms.planned_date,
        planned_amount: ms.planned_amount,
        planned_ratio: ms.planned_ratio,
        billing_trigger: ms.billing_trigger || 'milestone',
        is_prepayment: Boolean(ms.is_prepayment),
        auto_generate_payable: ms.is_prepayment ? false : Boolean(ms.auto_generate_payable),
        bank_account_id: ms.is_prepayment ? ms.bank_account_id ?? undefined : undefined,
        notes: ms.notes,
      }));
      const feeDetails = (detail.fee_details ?? []).map((fee: Record<string, unknown>) => ({
        type: fee.type,
        amount: fee.amount,
        bearer: fee.bearer,
        notes: fee.notes,
      }));
      navigate(PURCHASE_ORDER_CREATE_PATH, {
        state: {
          documentFlowCreate: {
            ...(plainValue(customValues) as Record<string, unknown>),
            supplier_id: detail.supplier_id,
            supplier_name: detail.supplier_name,
            supplier_contact: detail.supplier_contact,
            supplier_phone: detail.supplier_phone,
            order_date: todaySiteDateString(),
            delivery_date: detail.delivery_date,
            order_type: detail.order_type || '标准采购',
            payable_recognition:
              detail.payable_recognition ?? orgPayableRecognitionDefault,
            payment_method_code: detail.payment_method_code ?? undefined,
            payment_wire_percent: detail.payment_wire_percent ?? undefined,
            payment_acceptance_percent: detail.payment_acceptance_percent ?? undefined,
            settlement_terms_code: detail.settlement_terms_code ?? undefined,
            payment_terms_days: detail.payment_terms_days ?? undefined,
            currency: detail.currency || 'CNY',
            exchange_rate: detail.exchange_rate ?? 1,
            price_type: priceType,
            buyer_id: detail.buyer_id,
            buyer_name: detail.buyer_name,
            department_id:
              (detail as { department_id?: number | null }).department_id ?? undefined,
            department_name:
              (detail as { department_name?: string | null }).department_name ?? undefined,
            notes: detail.notes,
            attachments: mapAttachmentsToUploadList(detail.attachments),
            fee_details: feeDetails,
            payment_milestones: milestones,
            items,
          },
        },
      });
    } catch {
      messageApi.error(t('app.kuaizhizao.purchaseOrder.detailFailed'));
    }
  }, [
    loadPurchaseOrderFormFieldValues,
    messageApi,
    navigate,
    orgPayableRecognitionDefault,
    pullFromRequisitionQuery,
    requirePurchaseRequisition,
    selectedOrderForToolbar,
    t,
  ]);


  // 处理表单提交（创建/更新）
  const purchaseOrderStatusAlreadySubmitted = (status: string | undefined) =>
    isPendingReviewStatus(status) || isAuditedStatus(status) || isConfirmedStatus(status);

  const runPurchaseOrderSubmitAfterSave = async (orderId: number, isEditMode: boolean) => {
    const fresh = await getPurchaseOrder(orderId);
    const canSubmitNow =
      isDraftStatus(fresh.status) || isRejectedStatus(fresh.status);
    if (!canSubmitNow) {
      if (purchaseOrderStatusAlreadySubmitted(fresh.status)) {
        const st = fresh.status;
        if (isAuditedStatus(st) || isConfirmedStatus(st)) {
          messageApi.success(
            isEditMode
              ? t('app.kuaizhizao.purchaseOrder.saveSubmitAutoApproved')
              : t('app.kuaizhizao.purchaseOrder.createSubmitAutoApproved'),
          );
        } else {
          messageApi.success(
            isEditMode
              ? t('app.kuaizhizao.purchaseOrder.saveSubmitPending')
              : t('app.kuaizhizao.purchaseOrder.createSubmitPending'),
          );
        }
        setCurrentOrder(fresh);
        return;
      }
      messageApi.warning(
        t('app.kuaizhizao.purchaseOrder.saveSubmitFailed', {
          message: t('app.kuaizhizao.purchaseOrder.submitNotDraft'),
        }),
      );
      setCurrentOrder(fresh);
      return;
    }
    try {
      const afterSubmit = await submitPurchaseOrder(orderId);
      const st = (afterSubmit as PurchaseOrder | undefined)?.status;
      setCurrentOrder(afterSubmit as PurchaseOrder);
      if (isAuditedStatus(st)) {
        messageApi.success(
          isEditMode
            ? t('app.kuaizhizao.purchaseOrder.saveSubmitAutoApproved')
            : t('app.kuaizhizao.purchaseOrder.createSubmitAutoApproved'),
        );
      } else {
        messageApi.success(
          isEditMode
            ? t('app.kuaizhizao.purchaseOrder.saveSubmitPending')
            : t('app.kuaizhizao.purchaseOrder.createSubmitPending'),
        );
      }
    } catch (submitErr: unknown) {
      const submitMessage =
        submitErr instanceof Error
          ? submitErr.message
          : String((submitErr as { message?: string })?.message || '');
      const retryFresh = await getPurchaseOrder(orderId);
      setCurrentOrder(retryFresh);
      if (
        submitMessage.includes(t('app.kuaizhizao.purchaseOrder.submitNotDraft'))
        && purchaseOrderStatusAlreadySubmitted(retryFresh.status)
      ) {
        const st = retryFresh.status;
        if (isAuditedStatus(st) || isConfirmedStatus(st)) {
          messageApi.success(
            isEditMode
              ? t('app.kuaizhizao.purchaseOrder.saveSubmitAutoApproved')
              : t('app.kuaizhizao.purchaseOrder.createSubmitAutoApproved'),
          );
        } else {
          messageApi.success(
            isEditMode
              ? t('app.kuaizhizao.purchaseOrder.saveSubmitPending')
              : t('app.kuaizhizao.purchaseOrder.createSubmitPending'),
          );
        }
        return;
      }
      messageApi.warning(
        t('app.kuaizhizao.purchaseOrder.saveSubmitFailed', {
          message: submitMessage || t('common.operationFailed'),
        }),
      );
    }
  };

  const handleFormSubmit = async (values: any): Promise<void> => {
    if (purchaseOrderFormSubmitLockRef.current) {
      return;
    }
    purchaseOrderFormSubmitLockRef.current = true;
    setPurchaseOrderFormSubmitting(true);
    try {
      const { customData, standardValues } = extractPurchaseOrderFormValues(values);
      Object.keys(values).forEach((key) => {
        if (key.startsWith('custom_')) delete values[key];
      });
      Object.assign(values, standardValues);

      const normalizedItems = normalizeFormListItems<any>(values.items);
      const validItems = normalizedItems.filter(
        (it: any) => it.material_id && (Number(it.ordered_quantity) || 0) > 0
      );
      if (!validItems.length) {
        messageApi.error(t('app.kuaizhizao.purchaseOrder.atLeastOneItem'));
        throw new Error(t('app.kuaizhizao.purchaseOrder.atLeastOneItem'));
      }
      const paymentMixErr = validatePaymentMethodMix(
        values.payment_method_code as string | undefined,
        values.payment_wire_percent as number | undefined,
        values.payment_acceptance_percent as number | undefined,
      );
      if (paymentMixErr) {
        messageApi.error(paymentMixErr);
        throw new Error(paymentMixErr);
      }

      const employeeAdvance = isPartnerEmployeeAdvancePaymentMethod(
        values.payment_method_code as string | undefined,
      );
      if (employeeAdvance) {
        const payeeId = Number(values.advance_payee_id);
        if (!Number.isFinite(payeeId) || payeeId <= 0) {
          messageApi.error(t('app.kuaicaiwu.payment.advancePayeeRequired'));
          throw new Error(t('app.kuaicaiwu.payment.advancePayeeRequired'));
        }
        const payeeName =
          resolvePartnerAdvancePayeeName(
            payeeId,
            users.map((u) => ({
              label: normalizeUserDisplayName(u.full_name || u.username),
              value: u.id,
            })),
          ) || normalizeUserDisplayName(values.advance_payee_name);
        if (!payeeName) {
          messageApi.error(t('app.kuaicaiwu.payment.advancePayeeRequired'));
          throw new Error(t('app.kuaicaiwu.payment.advancePayeeRequired'));
        }
        values.advance_payee_id = payeeId;
        values.advance_payee_name = payeeName;
      } else {
        values.advance_payee_id = undefined;
        values.advance_payee_name = undefined;
      }

      const data = { ...values };
      const buyerIdRaw = data.buyer_id;
      if (buyerIdRaw != null && buyerIdRaw !== '' && Number.isFinite(Number(buyerIdRaw))) {
        const buyerId = Number(buyerIdRaw);
        if (!normalizeUserDisplayName(data.buyer_name)) {
          const buyer = users.find((u) => Number(u.id) === buyerId);
          if (buyer) {
            data.buyer_name = normalizeUserDisplayName(buyer.full_name || buyer.username);
          }
        }
      } else {
        const defBuyer = resolveDefaultPurchaseOrderBuyer();
        if (defBuyer.buyer_id != null) {
          data.buyer_id = defBuyer.buyer_id;
          data.buyer_name = defBuyer.buyer_name;
        } else {
          data.buyer_id = undefined;
          data.buyer_name = undefined;
        }
      }
      Object.assign(
        data,
        resolvePurchaseDepartmentPayload(
          data.department_id,
          resolveDepartmentName,
          data.department_name,
        ),
      );
      if (!data.department_id || !String(data.department_name ?? '').trim()) {
        messageApi.error(
          t('app.kuaizhizao.purchaseOrder.form.departmentRequired', '请选择部门'),
        );
        return false;
      }
      // 处理附件
      const formAttachments = data.attachments || [];
      data.attachments = formAttachments.map((f: any) => {
        if (f.response) {
          if (Array.isArray(f.response) && f.response.length > 0) {
            return { uid: f.response[0].uuid, name: f.response[0].original_name, status: 'done', url: getFileDownloadUrl(f.response[0].uuid) };
          }
          if (f.response.uuid) {
            return { uid: f.response.uuid, name: f.response.original_name, status: 'done', url: getFileDownloadUrl(f.response.uuid) };
          }
        }
        return { uid: f.uid, name: f.name, status: 'done', url: f.url };
      });

      const priceType = data.price_type ?? 'tax_exclusive';
      data.currency = data.currency || 'CNY';

      const resolveLineDateStr = (raw: unknown): string | undefined => {
        const coerced = coerceFormDate(raw);
        return coerced ? coerced.format('YYYY-MM-DD') : undefined;
      };

      const lineDateStrs = validItems
        .map((it: any) => resolveLineDateStr(it.required_date))
        .filter((value): value is string => Boolean(value));

      const headerDeliveryStr =
        lineDateStrs.length > 0
          ? lineDateStrs.reduce((max, cur) => (cur > max ? cur : max))
          : toApiDateString(data.delivery_date);

      if (!headerDeliveryStr) {
        messageApi.error(t('app.kuaizhizao.purchaseOrder.form.requiredDateRequired'));
        throw new Error(t('app.kuaizhizao.purchaseOrder.form.requiredDateRequired'));
      }

      data.delivery_date = headerDeliveryStr;
      data.order_date = toApiDateString(data.order_date);

      const itemsPayload = validItems.map((it: any) => {
        const qty = quantizeNumericByPlaces(Number(it.ordered_quantity) || 0, quantityDecimals);
        const formUnitPrice = Number(it.unit_price) || 0;
        const taxRate = Number(it.tax_rate) || 0;
        const storedLine = purchaseOrderFormLineToStored(
          formUnitPrice,
          qty,
          taxRate,
          priceType,
          priceDecimals,
        );
        const price = storedLine.unit_price;
        const dateStr = resolveLineDateStr(it.required_date) ?? headerDeliveryStr;
        if (!dateStr) {
          messageApi.error(t('app.kuaizhizao.purchaseOrder.lineRequiredDateMissing', { row: validItems.indexOf(it) + 1 }));
          throw new Error(t('app.kuaizhizao.purchaseOrder.form.requiredDateRequired'));
        }
        const totalPrice = storedLine.total_price;
        const receivedQty = Number(it.received_quantity) || 0;
        return {
          ...(it.id != null && Number(it.id) > 0 ? { id: Number(it.id) } : {}),
          material_id: Number(it.material_id),
          material_code: it.material_code || '',
          material_name: it.material_name || '',
          material_spec: it.material_spec || null,
          material_model: it.material_model || null,
          partner_material_code: it.partner_material_code || null,
          partner_material_name: it.partner_material_name || null,
          ordered_quantity: qty,
          unit: it.unit || '件',
          ...pickDocumentLineDualQuantityFields(it as Record<string, unknown>),
          unit_price: price,
          display_unit_price: storedLine.display_unit_price,
          total_price: totalPrice,
          tax_rate: taxRate,
          received_quantity: receivedQty,
          outstanding_quantity: Math.max(0, qty - receivedQty),
          required_date: dateStr,
          inspection_required: true,
          source_type: it.source_type || null,
          source_id: it.source_id != null && Number(it.source_id) > 0 ? Number(it.source_id) : null,
          demand_computation_item_id:
            it.demand_computation_item_id != null && Number(it.demand_computation_item_id) > 0
              ? Number(it.demand_computation_item_id)
              : null,
          work_order_id:
            it.work_order_id != null && Number(it.work_order_id) > 0
              ? Number(it.work_order_id)
              : null,
          work_order_code: it.work_order_code || null,
          notes: it.notes || null,
          attachments: normalizeDocumentAttachments(it.attachments),
        };
      });

      const headerAmounts = computePurchaseOrderHeaderAmountsForSave(validItems, priceType);
      const firstLineTaxPercent = validItems[0] ? Number(validItems[0].tax_rate) || 0 : 0;
      data.tax_rate = purchaseOrderTaxRateToDecimal(firstLineTaxPercent);
      data.price_type = priceType;
      data.total_amount = headerAmounts.total_amount;
      data.tax_amount = headerAmounts.tax_amount;
      data.net_amount = headerAmounts.net_amount;

      // 计算费用总额
      const feeDetails = normalizeFormListItems<any>(values.fee_details);
      const totalFeeAmount = feeDetails.reduce((sum: number, fee: any) => {
        return sum + (Number(fee.amount) || 0);
      }, 0);
      data.total_fee_amount = totalFeeAmount;
      data.fee_details = feeDetails;

      const milestoneRows = normalizeFormListItems<any>(values.payment_milestones).filter(
        (ms: any) =>
          ms?.milestone_name?.trim() ||
          ms?.planned_date ||
          ms?.planned_amount != null ||
          ms?.planned_ratio != null ||
          ms?.is_prepayment,
      );
      const prepayCount = milestoneRows.filter((ms: any) => Boolean(ms?.is_prepayment)).length;
      if (prepayCount > 1) {
        messageApi.error(t('app.kuaizhizao.purchaseOrder.prepaymentOnlyOne'));
        throw new Error('purchase_order_prepayment_only_one');
      }
      data.payment_milestones = milestoneRows
        .filter((ms: any) => ms?.milestone_name?.trim() && toApiDateString(ms.planned_date))
        .map((ms: any) => ({
          milestone_name: String(ms.milestone_name).trim(),
          planned_date: toApiDateString(ms.planned_date)!,
          planned_amount: ms.planned_amount != null ? Number(ms.planned_amount) : 0,
          planned_ratio: ms.planned_ratio != null ? Number(ms.planned_ratio) : undefined,
          billing_trigger: ms.billing_trigger || 'milestone',
          is_prepayment: Boolean(ms.is_prepayment),
          auto_generate_payable: ms.is_prepayment ? false : Boolean(ms.auto_generate_payable),
          bank_account_id: ms.is_prepayment ? ms.bank_account_id ?? undefined : undefined,
          notes: ms.notes,
        }));
      const prepayMs = data.payment_milestones.find((ms: any) => ms.is_prepayment);
      data.prepayment_amount = prepayMs ? prepayMs.planned_amount : null;
      data.prepayment_bank_account_id = prepayMs?.bank_account_id ?? null;

      let orderId: number | undefined;
      const editingId =
        (isEditPage && editRouteId) ||
        createdOrderIdRef.current ||
        (isEdit && currentOrder?.id ? Number(currentOrder.id) : null);
      if (editingId) {
        await updatePurchaseOrder(editingId, { ...data, items: itemsPayload });
        orderId = editingId;
        if (!submitAfterSaveRef.current) {
          messageApi.success(t('app.kuaizhizao.purchaseOrder.updateSuccess'));
        }
      } else {
        const flowExtrasRaw = documentFlowSubmitExtrasRef.current;
        const hadFlowHandoff = Boolean(flowExtrasRaw);
        // handoff 回写以本单实际明细为准：按 source_id 重建申请行 id / 数量，避免表单删行改量后误占未转出的申请行
        let flowExtras = flowExtrasRaw;
        if (
          flowExtrasRaw &&
          String(flowExtrasRaw.documentFlowSourceType || '') === 'purchase_requisition_items'
        ) {
          const rawIds = (
            Array.isArray(flowExtrasRaw.documentFlowRequisitionItemIds)
              ? flowExtrasRaw.documentFlowRequisitionItemIds
              : []
          )
            .map((v: unknown) => Number(v))
            .filter((n: number) => Number.isFinite(n) && n > 0);
          let unusedRaw = [...rawIds];
          const qtyMap: Record<number, number> = {};
          const sourceIds: number[] = [];
          for (const it of itemsPayload) {
            let sid = Number(it.source_id);
            if (!(sid > 0) && unusedRaw.length > 0) {
              sid = unusedRaw.shift() as number;
              it.source_id = sid;
              it.source_type = it.source_type || 'purchase_requisition';
            } else if (sid > 0) {
              unusedRaw = unusedRaw.filter((id) => id !== sid);
            }
            const qty = Number(it.ordered_quantity) || 0;
            if (!(sid > 0) || qty <= 0) continue;
            sourceIds.push(sid);
            qtyMap[sid] = qty;
          }
          flowExtras = {
            ...flowExtrasRaw,
            // 明细丢 source 时不得清空 handoff 的申请行 id，否则 finalize 直接跳过
            documentFlowRequisitionItemIds: sourceIds.length > 0 ? sourceIds : rawIds,
            documentFlowItemQuantities:
              Object.keys(qtyMap).length > 0
                ? qtyMap
                : flowExtrasRaw.documentFlowItemQuantities,
          };
        }
        const createPayload =
          flowExtras ?
            {
              ...data,
              ...flowExtras,
            }
          : data;
        const created = await createPurchaseOrder({ ...createPayload, items: itemsPayload });
        orderId = (created as any)?.id;
        if (orderId != null) {
          // 对齐工单：create 成功即钉住编辑身份，后续失败/选人也不再二次 create
          createdOrderIdRef.current = orderId;
          setIsEdit(true);
          setCurrentOrder(created as PurchaseOrder);
        }
        if (hadFlowHandoff) {
          documentFlowSubmitExtrasRef.current = null;
        }
        if (purchaseOrderCreateDraftKeyRef.current) {
          clearDocumentFormDraft(purchaseOrderCreateDraftKeyRef.current);
          purchaseOrderCreateDraftKeyRef.current = null;
        }
        if (!submitAfterSaveRef.current) {
          messageApi.success(t('app.kuaizhizao.purchaseOrder.createSuccess'));
        }
        if (orderId != null) {
          const createdOrder = created as PurchaseOrder;
          const linked = await completeDeliveryNodeDocumentLinkIfPending({
            docType: 'purchase_order',
            docId: orderId,
            docCode: createdOrder.order_code,
            title: createdOrder.supplier_name ?? null,
            navigate,
            message: messageApi,
            t,
          });
          if (linked) {
            submitAfterSaveRef.current = false;
            createdOrderIdRef.current = null;
            return;
          }
          if (hadFlowHandoff && continuePoHandoffQueueIfAny(navigate)) {
            submitAfterSaveRef.current = false;
            createdOrderIdRef.current = null;
            return;
          }
        }
      }

      if (orderId != null) {
        await savePurchaseOrderCustomFieldValues(orderId, customData);
      }

      if (submitAfterSaveRef.current && orderId) {
        submitAfterSaveRef.current = false;
        try {
          await runPurchaseOrderSubmitAfterSave(orderId, isEdit);
          createdOrderIdRef.current = null;
        } catch {
          // 钉住后切编辑路由，避免仍停 /new 再 create → 编码已存在
          if (isCreatePage && orderId) {
            navigate(purchaseOrderEditPath(orderId), { replace: true });
          }
          return;
        }
      }

      if (isFormPage) {
        leavePurchaseOrderFormPage();
      } else {
        setModalVisible(false);
      }
      invalidateStatistics();
      invalidateMenuBadgeCounts();

      actionRef.current?.reload();
    } catch (error: any) {
      submitAfterSaveRef.current = false;
      if (error?.message && !error.message.includes(t('app.kuaizhizao.purchaseOrder.atLeastOneItem')) && !error.message.includes(t('app.kuaizhizao.purchaseOrder.form.requiredDateRequired'))) {
        messageApi.error(error.message || t('common.operationFailed'));
      }
      throw error;
    } finally {
      purchaseOrderFormSubmitLockRef.current = false;
      setPurchaseOrderFormSubmitting(false);
    }
  };

  const statCards: StatCard[] = statistics
    ? [
        {
          title: t('app.kuaizhizao.purchase.statArrivalRate'),
          value: statistics.monthly_arrival_rate ?? 0,
          suffix: '%',
          valueStyle: { color: token.colorPrimary },
          description: (
            <div style={{ color: '#52c41a' }}>
              {t('app.kuaizhizao.purchase.statDeltaVsYesterday')}
            </div>
          ),
          backgroundChart: (
            <SimpleSparkline
              data={statistics?.trends?.arrival_rate || [...PO_STAT_SPARKLINE_ARRIVAL]}
              color={token.colorPrimary}
            />
          ),
        },
        {
          title: t('app.kuaizhizao.purchase.statPendingReview'),
          value: statistics.pending_review_count ?? 0,
          valueStyle: (statistics.pending_review_count ?? 0) > 0 ? { color: '#faad14' } : undefined,
          description:
            (statistics.pending_review_count ?? 0) > 0
              ? t('app.kuaizhizao.purchase.statNeedImmediateReview')
              : t('app.kuaizhizao.purchase.statNothingPending'),
          onClick:
            (statistics.pending_review_count ?? 0) > 0
              ? () => {
                  tableSearchFormRef.current?.setFieldsValue?.({ status: 'PENDING_REVIEW' });
                  actionRef.current?.reload?.();
                }
              : undefined,
        },
        {
          title: t('app.kuaizhizao.purchase.statAnnualTotal'),
          value: statistics.annual_total_amount ?? 0,
          prefix: '¥',
          precision: 2,
          valueStyle: { color: '#2f54eb' },
          description: (
            <div style={{ color: (statistics as any).annual_total_yoy >= 0 ? '#52c41a' : '#ff4d4f' }}>
              {t('app.kuaizhizao.purchase.statVsLastYear', {
                value: (statistics as any).annual_total_yoy
                  ? `${(statistics as any).annual_total_yoy > 0 ? '+' : ''}${(statistics as any).annual_total_yoy}%`
                  : '+0%',
              })}
            </div>
          ),
          backgroundChart: (
            <SimpleSparkline
              data={statistics?.trends?.annual_total || [...PO_STAT_SPARKLINE_ANNUAL]}
              color="#2f54eb"
            />
          ),
        },
        {
          title: t('app.kuaizhizao.purchase.statSupplierOnTime'),
          value: statistics.supplier_on_time_rate ?? 0,
          suffix: '%',
          valueStyle: { color: '#52c41a' },
          backgroundChart: (
            <SimpleSparkline data={PO_STAT_SPARKLINE_SUPPLIER} color="#52c41a" />
          ),
        },
        {
          title: t('app.kuaizhizao.purchase.statOverdue'),
          value: statistics.overdue_count ?? 0,
          valueStyle: (statistics.overdue_count ?? 0) > 0 ? { color: token.colorError } : undefined,
          description: (statistics.overdue_count ?? 0) > 0 ? (
            <div style={{ color: token.colorError }}>
              {t('app.kuaizhizao.purchase.statOverdueAmount', {
                amount: ((statistics.overdue_count ?? 0) * 1200).toLocaleString(),
              })}
            </div>
          ) : null,
          backgroundChart: (
            <SimpleSparkline
              data={PO_STAT_SPARKLINE_OVERDUE}
              color={token.colorError}
            />
          ),
        },
      ]
    : [
        {
          title: t('app.kuaizhizao.purchase.statArrivalRate'),
          value: 0,
          suffix: '%',
          valueStyle: { color: token.colorPrimary },
        },
        {
          title: t('app.kuaizhizao.purchase.statPendingReview'),
          value: 0,
        },
        {
          title: t('app.kuaizhizao.purchase.statAnnualTotal'),
          value: 0,
          prefix: '¥',
          precision: 2,
          valueStyle: { color: '#2f54eb' },
        },
        {
          title: t('app.kuaizhizao.purchase.statSupplierOnTime'),
          value: 0,
          suffix: '%',
          valueStyle: { color: '#52c41a' },
        },
        {
          title: t('app.kuaizhizao.purchase.statOverdue'),
          value: 0,
        },
      ];

  const triggerPurchaseOrderPrimarySubmit = useCallback(async () => {
    if (purchaseOrderFormSubmitLockRef.current) {
      return;
    }
    try {
      await formRef.current?.validateFields();
      submitAfterSaveRef.current = !!(
        isCreatePage || (isEditPage && isDraftStatus(currentOrder?.status))
      );
      formRef.current?.submit();
    } catch (err: any) {
      if (err?.errorFields?.length) {
        messageApi.warning(t('app.kuaizhizao.purchaseOrder.fillRequiredBeforeSubmit'));
      }
    }
  }, [currentOrder?.status, isCreatePage, isEditPage, messageApi, t]);

  const handleSaveDraft = useCallback(async () => {
    if (purchaseOrderFormSubmitLockRef.current) {
      return;
    }
    try {
      await formRef.current?.validateFields();
      submitAfterSaveRef.current = false;
      formRef.current?.submit();
    } catch (err: any) {
      if (err?.errorFields?.length) {
        messageApi.warning(t('app.kuaizhizao.purchaseOrder.fillRequiredBeforeSubmit'));
      }
    }
  }, [messageApi, t]);

  useSubmitShortcut(() => void triggerPurchaseOrderPrimarySubmit(), isFormPage);

  const purchaseOrderFormItemContent = (
    <>
      <DetailDrawerSection titleAccent title={t('app.uniDetail.sectionBasic')}>
        <div className="document-form-untitled-groups">
          <div className="document-form-untitled-group">
      {/* 一行 5 格：对齐销售订单；币种/汇率合占 1 格 */}
      <Row gutter={16} wrap={false}>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <CodeField
            pageCode="kuaizhizao-purchase-order"
            name="order_code"
            label={t('app.kuaizhizao.purchaseOrder.form.orderCode')}
            required={true}
            autoGenerateOnCreate={!isEdit}
            showGenerateButton={false}
            documentId={isEdit ? currentOrder?.id : undefined}
            context={{}}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProForm.Item
            name="supplier_id"
            label={t('app.kuaizhizao.purchaseOrder.form.supplier')}
            rules={[{ required: true, message: t('app.kuaizhizao.purchaseOrder.form.supplierRequired') }]}
          >
            <SupplierSelectDropdown
              hostResource={KUAIZHIZAO_DOC_HOST.purchaseOrder}
              placeholder={t('app.kuaizhizao.purchaseOrder.form.supplierRequired')}
              style={{ width: '100%' }}
              onSuppliersChange={setSupplierList}
              onSupplierPick={(s) => {
                applySupplierFormFields(formRef, s as Record<string, unknown> | null, {
                  users,
                  supplierList: supplierList as unknown as Array<Record<string, unknown>>,
                  orgPayableDefault: resolveOrgPayableDefaultFromBusinessConfig(businessConfig),
                });
                const taxRate = resolveSupplierDefaultTaxRatePercent(
                  s as Record<string, unknown> | null,
                );
                const items = normalizeFormListItems<any>(formRef.current?.getFieldValue('items'));
                const nextItems = items.map((it) => {
                  const current = Number(it?.tax_rate);
                  // 未填或仍为 0 时跟供应商默认；已手改的特殊税率保留
                  if (Number.isFinite(current) && current > 0) return it;
                  return { ...it, tax_rate: taxRate };
                });
                formRef.current?.setFieldsValue({
                  price_type: DEFAULT_PURCHASE_PRICE_TYPE,
                  items: nextItems.length > 0 ? nextItems : [{ ...defaultOrderItem, tax_rate: taxRate }],
                });
                const sid = Number((s as { id?: number })?.id);
                const lineItems = normalizeFormListItems<any>(formRef.current?.getFieldValue('items'));
                lineItems.forEach((_, idx) => {
                  void repriceUnlockedPurchaseDocumentLineIfNeeded(formRef.current, idx, {
                    asOfField: 'order_date',
                    trigger: 'partner',
                    supplierId: Number.isFinite(sid) && sid > 0 ? sid : undefined,
                    fallbackTaxRate: taxRate,
                  });
                });
              }}
            />
          </ProForm.Item>
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <PurchaseOrderBuyerField userList={users} loading={usersLoading} />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormDatePicker
            name="order_date"
            label={t('app.kuaizhizao.purchaseOrder.form.orderDate')}
            placeholder={t('app.kuaizhizao.purchaseOrder.form.orderDateRequired')}
            rules={[{ required: true, message: t('app.kuaizhizao.purchaseOrder.form.orderDateRequired') }]}
            fieldProps={{
              style: { width: '100%' },
              onChange: () => {
                const items = normalizeFormListItems<any>(formRef.current?.getFieldValue('items'));
                const taxRate = resolveSupplierDefaultTaxRatePercent(
                  (supplierList.find(
                    (x) => Number(x.id) === Number(formRef.current?.getFieldValue('supplier_id')),
                  ) as Record<string, unknown> | undefined) ?? null,
                );
                items.forEach((_, idx) => {
                  void repriceUnlockedPurchaseDocumentLineIfNeeded(formRef.current, idx, {
                    asOfField: 'order_date',
                    fallbackTaxRate: taxRate,
                  });
                });
              },
            }}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormDatePicker
            name="delivery_date"
            label={t('app.kuaizhizao.purchaseOrder.form.requiredDate')}
            placeholder={t('app.kuaizhizao.purchaseOrder.form.requiredDateRequired')}
            rules={[{ required: true, message: t('app.kuaizhizao.purchaseOrder.form.requiredDateRequired') }]}
            fieldProps={buildFutureDateShortcutFieldProps({
              getForm: () => formRef.current,
              fieldName: 'delivery_date',
              baseFieldName: 'order_date',
              t,
              onApply: (date) => {
                formRef.current?.setFieldValue?.('delivery_date', date);
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
      </Row>
      <Row gutter={16} wrap={false} style={{ marginTop: 0 }}>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProForm.Item
            name="payable_recognition"
            label={t('field.document.ledgerRecognition')}
            initialValue={orgPayableRecognitionDefault}
            rules={[{ required: true, message: t('field.document.ledgerRecognitionRequired') }]}
          >
            <UniDropdown options={payableLedgerRecognitionOptions} style={{ width: '100%' }} />
          </ProForm.Item>
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProForm.Item
            name="settlement_terms_code"
            label={t('app.kuaizhizao.purchaseOrder.settlementTerms')}
          >
            <UniDropdown
              allowClear
              showSearch
              optionFilterProp="label"
              options={purchaseOrderSettlementTermsOptions}
              placeholder={t('app.kuaizhizao.purchaseOrder.selectSettlementTerms')}
              style={{ width: '100%' }}
            />
          </ProForm.Item>
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <ProFormDigit
            name="payment_terms_days"
            label={t('app.kuaizhizao.purchaseOrder.paymentCycle')}
            placeholder={t('app.kuaizhizao.purchaseOrder.paymentCycleDaysPlaceholder')}
            min={0}
            fieldProps={{ precision: 0, style: { width: '100%' } }}
            tooltip={t('app.kuaizhizao.purchaseOrder.paymentCycleDaysHint')}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <PaymentMethodWithMixFormItems
            formRef={formRef}
            options={purchaseOrderPaymentMethodOptions}
            methodLabel={t('app.kuaizhizao.purchaseOrder.paymentMethod')}
            methodPlaceholder={t('app.kuaizhizao.purchaseOrder.selectPaymentMethod')}
          />
        </Col>
        <Col flex="1 1 0" style={{ minWidth: 0 }}>
          <Row gutter={8} wrap={false}>
            <Col flex="1 1 0" style={{ minWidth: 0 }}>
              <ProForm.Item name="currency" label={t('app.kuaizhizao.purchaseOrder.form.currency')} initialValue="CNY">
                <UniDropdown
                  placeholder={t('app.kuaizhizao.purchaseOrder.form.currencyPlaceholder')}
                  options={currencyOptions}
                  loading={currencyLoading}
                  onChange={(value) => {
                    const code = String(value ?? 'CNY').trim().toUpperCase();
                    if (code === 'CNY') {
                      formRef.current?.setFieldValue('exchange_rate', 1);
                    }
                  }}
                />
              </ProForm.Item>
            </Col>
              <Col span={6}>
                <ProForm.Item
                  name="supplier_id"
                  label={t('app.kuaizhizao.purchaseOrder.form.supplier')}
                  rules={[{ required: true, message: t('app.kuaizhizao.purchaseOrder.form.supplierRequired') }]}
                >
                  <SupplierSelectDropdown
                    hostResource={KUAIZHIZAO_DOC_HOST.purchaseOrder}
                    placeholder={t('app.kuaizhizao.purchaseOrder.form.supplierRequired')}
                    style={{ width: '100%' }}
                    onSuppliersChange={setSupplierList}
                    onSupplierPick={(s) => {
                      if (s) {
                        const bIdRaw = (s as any).buyerId ?? (s as any).buyer_id;
                        const bId =
                          bIdRaw != null && bIdRaw !== '' && Number.isFinite(Number(bIdRaw))
                            ? Number(bIdRaw)
                            : undefined;
                        const buyer = bId != null ? users.find((u) => Number(u.id) === bId) : undefined;
                        const bName =
                          (s as any).buyerName ??
                          (s as any).buyer_name ??
                          (buyer ? normalizeUserDisplayName(buyer.full_name || buyer.username) : '');
                        // 供应商无归属采购员时保留表单已选（含新建默认的当前用户）
                        const buyerPatch =
                          bId != null
                            ? {
                                buyer_id: bId,
                                buyer_name: normalizeUserDisplayName(bName),
                              }
                            : {};
                        formRef.current?.setFieldsValue({
                          supplier_name: s.name ?? (s as any).supplier_name,
                          supplier_contact:
                            (s as any).contact_person ??
                            s.contactPerson ??
                            (s as any).supplier_contact ??
                            (Array.isArray((s as any).contacts) && (s as any).contacts[0]
                              ? (s as any).contacts[0].contactPerson ??
                                (s as any).contacts[0].contact_person
                              : undefined),
                          supplier_phone:
                            s.phone ??
                            (s as any).supplier_phone ??
                            (Array.isArray((s as any).contacts) && (s as any).contacts[0]
                              ? (s as any).contacts[0].phone
                              : undefined),
                          ...buyerPatch,
                        });
                      } else {
                        formRef.current?.setFieldsValue({
                          supplier_name: undefined,
                          supplier_contact: undefined,
                          supplier_phone: undefined,
                        });
                      }
                    }}
                  />
                </ProForm.Item>
              </Col>
              <Col span={6}>
                <PurchaseOrderBuyerField userList={users} loading={usersLoading} />
              </Col>
              <Col span={6}>
                <ProFormDatePicker
                  name="order_date"
                  label={t('app.kuaizhizao.purchaseOrder.form.orderDate')}
                  placeholder={t('app.kuaizhizao.purchaseOrder.form.orderDateRequired')}
                  rules={[{ required: true, message: t('app.kuaizhizao.purchaseOrder.form.orderDateRequired') }]}
                  fieldProps={{ style: { width: '100%' } }}
                />
              </Col>
            </Row>
        </Col>
      </Row>
          </div>
          <div className="document-form-untitled-group">
            <PurchaseSupplierPartnerDetailBridge
              supplierList={supplierList as unknown as Array<Record<string, unknown>>}
              hostResource={KUAIZHIZAO_DOC_HOST.purchaseOrder}
            >
            <Row gutter={16}>
              <Col span={6}>
                <ProFormDatePicker
                  name="delivery_date"
                  label={t('app.kuaizhizao.purchaseOrder.form.requiredDate')}
                  placeholder={t('app.kuaizhizao.purchaseOrder.form.requiredDateRequired')}
                  rules={[{ required: true, message: t('app.kuaizhizao.purchaseOrder.form.requiredDateRequired') }]}
                  fieldProps={buildFutureDateShortcutFieldProps({
                    getForm: () => formRef.current,
                    fieldName: 'delivery_date',
                    baseFieldName: 'order_date',
                    t,
                    onApply: (date) => {
                      formRef.current?.setFieldValue?.('delivery_date', date);
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
              <Col span={6}>
                <ProForm.Item name="order_type" label={t('app.kuaizhizao.purchaseOrder.form.orderType')} initialValue="标准采购">
                  <UniDropdown
                    placeholder={t('app.kuaizhizao.purchaseOrder.form.orderTypePlaceholder')}
                    options={orderTypeOptions}
                    loading={orderTypeLoading}
                  />
                </ProForm.Item>
              </Col>
              <Col span={6}>
                <ProForm.Item name="currency" label={t('app.kuaizhizao.purchaseOrder.form.currency')} initialValue="CNY">
                  <UniDropdown
                    placeholder={t('app.kuaizhizao.purchaseOrder.form.currencyPlaceholder')}
                    options={currencyOptions}
                    loading={currencyLoading}
                  />
                </ProForm.Item>
              </Col>
              <Col span={6}>
                <PurchaseSupplierContactFormField
                  formRef={formRef}
                  label={t('app.kuaizhizao.purchaseOrder.form.contact')}
                  placeholder={t('app.kuaizhizao.purchaseOrder.form.contactPlaceholder')}
                />
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={6}>
                <PurchaseSupplierPhoneFormField
                  label={t('app.kuaizhizao.purchaseOrder.form.phone')}
                  placeholder={t('app.kuaizhizao.purchaseOrder.form.phonePlaceholder')}
                />
              </Col>
              <Col span={6}>
                <PurchaseDepartmentFormField
                  options={departmentOptions}
                  loading={departmentOptionsLoading}
                  required
                  requiredMessage={t(
                    'app.kuaizhizao.purchaseOrder.form.departmentRequired',
                    '请选择部门',
                  )}
                />
              </Col>
            </Row>
            </PurchaseSupplierPartnerDetailBridge>
          </div>
          <CustomFieldsFormSection
            customFields={purchaseOrderFormCustomFields}
            customFieldValues={purchaseOrderFormCustomFieldValues}
            gridColumns={4}
          />
        </div>
        <ProFormText name="supplier_name" hidden />
        <ProFormText name="price_type" hidden />
      </DetailDrawerSection>

      <DetailDrawerSection titleAccent title={t('app.uniDetail.sectionLines')}>
        <AntForm.Item noStyle shouldUpdate={(prev: any, curr: any) => prev?.price_type !== curr?.price_type}>
          {({ getFieldValue: getFormValue }: any) => {
            const rawPriceType = getFormValue('price_type');
            const priceType = rawPriceType === 'tax_inclusive' ? 'tax_inclusive' : 'tax_exclusive';
            const showTaxColumns = priceType === 'tax_inclusive';
            return (
              <>
              <DocumentDetailTableStyles />
              <UniTableDetail
                name="items"
                title={t('app.kuaizhizao.purchaseOrder.form.itemsTitle')}
                required
                requiredMessage={t('app.kuaizhizao.purchaseOrder.form.itemsRequired')}
                leftExtra={(
                  <PriceTypeSwitch
                    checked={priceType === 'tax_inclusive'}
                    checkedChildren={t('app.kuaizhizao.purchaseOrder.form.taxIncl')}
                    unCheckedChildren={t('app.kuaizhizao.purchaseOrder.form.taxExcl')}
                    onChange={(nextChecked) => {
                      setFormPriceType(formRef.current, nextChecked ? 'tax_inclusive' : 'tax_exclusive');
                    }}
                  />
                )}
                headerExtra={(
                  <Space size={8}>
                    <Button
                      type="default"
                      icon={<ImportOutlined />}
                      onClick={() => setImportModalVisible(true)}
                    >
                      {t('app.kuaizhizao.purchaseOrder.form.importItems')}
                    </Button>
                    <Button
                      type="default"
                      icon={<PlusOutlined />}
                      onClick={() => {
                        const mainDelivery = formRef.current?.getFieldValue('delivery_date');
                        const defaultDate =
                          mainDelivery != null
                            ? dayjs.isDayjs(mainDelivery)
                              ? mainDelivery
                              : dayjs(mainDelivery)
                            : dayjs();
                        const items = [...normalizeFormListItems<any>(formRef.current?.getFieldValue('items'))];
                        items.push({
                          ...defaultOrderItem,
                          tax_rate: 0,
                          required_date: defaultDate,
                        });
                        formRef.current?.setFieldsValue({ items });
                      }}
                    >
                      {t('app.kuaizhizao.purchaseOrder.form.addLine')}
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
                columns={[
                {
                  title: t('app.kuaizhizao.purchaseOrder.form.material'),
                  dataIndex: 'material_id',
                  width: DOCUMENT_DETAIL_COL_WIDTH.material,
                  ...DOCUMENT_DETAIL_TEXT_COL,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item noStyle shouldUpdate={(prev: any, curr: any) => prev?.items?.[index] !== curr?.items?.[index]}>
                        {({ getFieldValue }: any) => {
                          const row = normalizeFormListItems<any>(getFieldValue('items'))[index];
                          const mid = row?.material_id ? Number(row.material_id) : null;
                          const fallback = mid && (row?.material_code || row?.material_name)
                            ? { value: mid, label: `${row.material_code || ''} - ${row.material_name || ''}`.trim() || String(mid) }
                            : undefined;
                          return (
                            <UniMaterialSelect
                              name={[index, 'material_id']}
                              label=""
                              placeholder={t('app.kuaizhizao.salesOrder.selectMaterial')}
                              required
                              size={DOCUMENT_DETAIL_CONTROL_SIZE}
                              listFieldKey={index}
                              listFieldName="items"
                              fillMapping={withMaterialLineFillMapping()}
                              onChange={(_val, material) => {
                                if (!material) return;
                                formRef.current?.setFieldValue(
                                  ['items', index, 'unit'],
                                  resolveMaterialScenarioUnit(material, 'purchase'),
                                );
                                void applyPurchaseDocumentLineMaterialPricing(
                                  formRef.current,
                                  index,
                                  material,
                                  { asOfField: 'order_date', unitPriceField: 'unit_price' },
                                );
                              }}
                              fallbackOption={fallback}
                              formItemProps={{ style: { margin: 0 } }}
                              showQuickCreate
                              showAdvancedSearch
                            skipFuzzyPinyinClientFilter
                            />
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  ...buildDocumentDetailSpecModelFormColumns(t),
                  ...buildDocumentDetailPartnerMaterialFormColumns(t, 'supplier'),
                  {
                    title: t('common.unit'),
                    dataIndex: 'unit',
                    width: DOCUMENT_DETAIL_COL_WIDTH.unit,
                    ...DOCUMENT_DETAIL_TEXT_COL,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item noStyle shouldUpdate={(prev, curr) => prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id}>
                        {({ getFieldValue }) => {
                          const materialId = getFieldValue(['items', index, 'material_id']);
                          if (!formRef.current) return null;
                          return (
                            <AntForm.Item name={[index, 'unit']} style={{ margin: 0 }}>
                              <DocumentLineUnitSelect
                                form={formRef.current}
                                listName="items"
                                rowIndex={index}
                                fields={{ quantity: 'ordered_quantity', unit: 'unit' }}
                                materialId={materialId}
                                size={DOCUMENT_DETAIL_CONTROL_SIZE}
                                noStyle
                              />
                            </AntForm.Item>
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('common.quantity'),
                    dataIndex: 'ordered_quantity',
                    width: DOCUMENT_DETAIL_COL_WIDTH.quantity,
                    ...DOCUMENT_DETAIL_NUM_COL,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        noStyle
                        shouldUpdate={(prev, curr) =>
                          prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id
                        }
                      >
                        {({ getFieldValue }) => {
                          const materialId = getFieldValue(['items', index, 'material_id']);
                          if (!formRef.current) return null;
                          return (
                            <DocumentLineDualQuantityFormCell
                              form={formRef.current}
                              listName="items"
                              rowIndex={index}
                              quantityField="ordered_quantity"
                              unitField="unit"
                              scenario="purchase"
                              quantityPrecision={quantityDecimals}
                              materialId={materialId}
                              onAfterQuantityChange={() => {
                                void repriceUnlockedPurchaseDocumentLineIfNeeded(formRef.current, index, {
                                  asOfField: 'order_date',
                                  fallbackTaxRate: resolveSupplierDefaultTaxRatePercent(
                                    (supplierList.find(
                                      (x) =>
                                        Number(x.id) ===
                                        Number(formRef.current?.getFieldValue('supplier_id')),
                                    ) as Record<string, unknown> | undefined) ?? null,
                                  ),
                                });
                              }}
                            />
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: showTaxColumns ? t('app.kuaizhizao.purchaseOrder.col.taxUnitPrice') : t('app.kuaizhizao.purchaseOrder.col.unitPrice'),
                    dataIndex: 'unit_price',
                    width: DOCUMENT_DETAIL_COL_WIDTH.unitPrice + 28,
                    ...DOCUMENT_DETAIL_NUM_COL,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        noStyle
                        shouldUpdate={(prev: any, curr: any) =>
                          prev?.items?.[index]?.material_id !== curr?.items?.[index]?.material_id ||
                          prev?.items?.[index]?.unit_price !== curr?.items?.[index]?.unit_price ||
                          prev?.items?.[index]?.is_gift !== curr?.items?.[index]?.is_gift ||
                          prev?.supplier_id !== curr?.supplier_id
                        }
                      >
                        {({ getFieldValue }) => {
                          const row = normalizeFormListItems<any>(getFieldValue('items'))[index] ?? {};
                          const isGift = Boolean(row.is_gift);
                          return (
                            <AntForm.Item
                              name={[index, 'unit_price']}
                              rules={
                                isGift
                                  ? [
                                      {
                                        type: 'number',
                                        min: 0,
                                        message: t('app.kuaizhizao.purchaseOrder.form.gteZero'),
                                      },
                                    ]
                                  : [
                                      {
                                        required: true,
                                        message: t(
                                          'app.kuaizhizao.purchaseOrder.form.nonGiftUnitPriceRequired',
                                        ),
                                      },
                                      {
                                        type: 'number',
                                        min: 0,
                                        message: t('app.kuaizhizao.purchaseOrder.form.gteZero'),
                                      },
                                      {
                                        validator: async (_, value) => {
                                          if (value === null || value === undefined || value === '') {
                                            throw new Error(
                                              t(
                                                'app.kuaizhizao.purchaseOrder.form.nonGiftUnitPriceRequired',
                                              ),
                                            );
                                          }
                                          const n = Number(value);
                                          if (!Number.isFinite(n) || n < 0) {
                                            throw new Error(t('app.kuaizhizao.purchaseOrder.form.gteZero'));
                                          }
                                        },
                                      },
                                    ]
                              }
                              style={{ margin: 0 }}
                            >
                              <LineUnitPriceWithTrendTrigger
                                side="purchase"
                                materialId={row.material_id}
                                partnerId={getFieldValue('supplier_id')}
                                placeholder={
                                  showTaxColumns
                                    ? t('app.kuaizhizao.purchaseOrder.col.taxUnitPrice')
                                    : t('app.kuaizhizao.purchaseOrder.col.unitPrice')
                                }
                                min={0}
                                precision={priceDecimals}
                                prefix="¥"
                                size={DOCUMENT_DETAIL_CONTROL_SIZE}
                                disabled={isGift}
                                onChange={(val) => {
                                  if (isGift) return;
                                  const items = normalizeFormListItems<any>(
                                    formRef.current?.getFieldValue('items'),
                                  );
                                  const cur = items[index] ?? row;
                                  const next = [...items];
                                  next[index] = markDocumentLineUnitPriceLocked({
                                    ...cur,
                                    unit_price: val ?? 0,
                                  });
                                  formRef.current?.setFieldsValue({ items: next });
                                }}
                              />
                            </AntForm.Item>
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  ...(showTaxColumns
                    ? [
                        {
                          title: t('app.kuaizhizao.purchaseOrder.col.exclAmount'),
                          width: DOCUMENT_DETAIL_COL_WIDTH.exclAmount,
                          ...DOCUMENT_DETAIL_NUM_COL,
                          render: (_: any, __: any, index: number) => (
                            <AntForm.Item noStyle shouldUpdate={(prev: any, curr: any) => prev?.items !== curr?.items}>
                              {({ getFieldValue }: any) => {
                                const items = normalizeFormListItems<any>(getFieldValue('items'));
                                const row = items[index];
                                const qty = Number(row?.ordered_quantity) || 0;
                                const line = resolvePurchaseOrderLineAmounts(row, priceType);
                                const isEditing = editingExcl?.index === index;
                                const displayValue = isEditing ? editingExcl.value : line.excl;
                                return (
                                  <InputNumber
                                    placeholder={t('app.kuaizhizao.purchaseOrder.col.exclAmount')}
                                    min={0}
                                    precision={amountDecimals}
                                    prefix="¥"
                                    style={{ width: '100%' }}
                                    size={DOCUMENT_DETAIL_CONTROL_SIZE}
                                    value={displayValue}
                                    onChange={(val) => {
                                      const v = val ?? null;
                                      editingExclIndexRef.current = index;
                                      editingExclValueRef.current = v;
                                      setEditingExcl({ index, value: v });
                                    }}
                                    onFocus={() => {
                                      editingExclIndexRef.current = index;
                                      setEditingExcl((prev) => {
                                        if (prev?.index === index) return prev;
                                        editingExclValueRef.current = line.excl;
                                        return { index, value: line.excl };
                                      });
                                    }}
                                    onBlur={() => {
                                      const excl = editingExclValueRef.current;
                                      if (
                                        editingExclIndexRef.current === index &&
                                        excl != null &&
                                        qty > 0 &&
                                        !documentLineExclMatchesDerived(
                                          excl,
                                          row?.ordered_quantity,
                                          row?.unit_price,
                                          row?.tax_rate,
                                          priceType,
                                        )
                                      ) {
                                        const applied = applyDocumentLineExclAmountEdit({
                                          qty,
                                          taxRate: row?.tax_rate,
                                          priceType,
                                          exclAmount: excl,
                                          priceDecimals,
                                        });
                                        const next = [...items];
                                        next[index] = { ...row, unit_price: applied.unit_price };
                                        formRef.current?.setFieldsValue({ items: next });
                                      }
                                      editingExclIndexRef.current = null;
                                      setEditingExcl(null);
                                    }}
                                  />
                                );
                              }}
                            </AntForm.Item>
                          ),
                        },
                        {
                          title: (
                            <TaxRateBatchColumnTitle
                              onBatch={(num) => {
                                const items = normalizeFormListItems<Record<string, unknown>>(
                                  formRef.current?.getFieldValue('items'),
                                );
                                if (items.length === 0) return;
                                formRef.current?.setFieldsValue({
                                  items: items.map((it) => ({ ...it, tax_rate: num })),
                                });
                              }}
                            />
                          ),
                          dataIndex: 'tax_rate',
                          width: DOCUMENT_DETAIL_COL_WIDTH.taxRate,
                          ...DOCUMENT_DETAIL_NUM_COL,
                          onCell: () => ({ className: 'quotation-tax-rate-col' }),
                          render: (_: any, __: any, index: number) => <TaxRateDetailCell index={index} />,
                        },
                        {
                          title: t('app.kuaizhizao.purchaseOrder.col.taxAmount'),
                          width: DOCUMENT_DETAIL_COL_WIDTH.taxAmount,
                          ...DOCUMENT_DETAIL_NUM_COL,
                          render: (_: any, __: any, index: number) => (
                            <AntForm.Item noStyle shouldUpdate={(prev: any, curr: any) => prev?.items !== curr?.items}>
                              {({ getFieldValue }: any) => {
                                const row = normalizeFormListItems<any>(getFieldValue('items'))[index];
                                const line = resolvePurchaseOrderLineAmounts(row, priceType);
                                return <span>¥{line.tax.toFixed(amountDecimals)}</span>;
                              }}
                            </AntForm.Item>
                          ),
                        },
                      ]
                    : []),
                  {
                    title: showTaxColumns ? t('app.kuaizhizao.purchaseOrder.col.inclTotal') : t('app.kuaizhizao.purchaseOrder.col.totalPrice'),
                    width: DOCUMENT_DETAIL_COL_WIDTH.lineAmount,
                    ...DOCUMENT_DETAIL_NUM_COL,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item noStyle shouldUpdate={(prev: any, curr: any) => prev?.items !== curr?.items}>
                        {({ getFieldValue }: any) => {
                          const items = normalizeFormListItems<any>(getFieldValue('items'));
                          const row = items[index];
                          const qty = Number(row?.ordered_quantity) || 0;
                          const line = resolvePurchaseOrderLineAmounts(row, priceType);
                          if (showTaxColumns) {
                            return <span>¥{line.incl.toFixed(amountDecimals)}</span>;
                          }
                          // 不含税模式：合计即未税金额，可编辑并反算单价
                          const isEditing = editingExcl?.index === index;
                          const displayValue = isEditing ? editingExcl.value : line.excl;
                          return (
                            <InputNumber
                              placeholder={t('app.kuaizhizao.purchaseOrder.col.totalPrice')}
                              min={0}
                              precision={amountDecimals}
                              prefix="¥"
                              style={{ width: '100%' }}
                              size={DOCUMENT_DETAIL_CONTROL_SIZE}
                              value={displayValue}
                              onChange={(val) => {
                                const v = val ?? null;
                                editingExclIndexRef.current = index;
                                editingExclValueRef.current = v;
                                setEditingExcl({ index, value: v });
                              }}
                              onFocus={() => {
                                editingExclIndexRef.current = index;
                                setEditingExcl((prev) => {
                                  if (prev?.index === index) return prev;
                                  editingExclValueRef.current = line.excl;
                                  return { index, value: line.excl };
                                });
                              }}
                              onBlur={() => {
                                const excl = editingExclValueRef.current;
                                if (
                                  editingExclIndexRef.current === index &&
                                  excl != null &&
                                  qty > 0 &&
                                  !documentLineExclMatchesDerived(
                                    excl,
                                    row?.ordered_quantity,
                                    row?.unit_price,
                                    row?.tax_rate,
                                    'tax_exclusive',
                                  )
                                ) {
                                  const applied = applyDocumentLineExclAmountEdit({
                                    qty,
                                    taxRate: row?.tax_rate,
                                    priceType: 'tax_exclusive',
                                    exclAmount: excl,
                                    priceDecimals,
                                  });
                                  const next = [...items];
                                  next[index] = { ...row, unit_price: applied.unit_price };
                                  formRef.current?.setFieldsValue({ items: next });
                                }
                                editingExclIndexRef.current = null;
                                setEditingExcl(null);
                              }}
                            />
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('app.kuaizhizao.purchaseOrder.col.requiredDelivery'),
                    dataIndex: 'required_date',
                    width: DOCUMENT_DETAIL_COL_WIDTH.deliveryDate,
                    ...DOCUMENT_DETAIL_TEXT_COL,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item name={[index, 'required_date']} rules={[{ required: true, message: t('common.required') }]} style={{ margin: 0 }}>
                        <FutureDatePicker
                          size={DOCUMENT_DETAIL_CONTROL_SIZE}
                          style={DOCUMENT_DETAIL_DATE_PICKER_STYLE}
                          format="YYYY-MM-DD"
                          getForm={() => formRef.current}
                          baseFieldName="order_date"
                          t={t}
                          onApply={(date) =>
                            formRef.current?.setFieldValue?.(['items', index, 'required_date'], date)
                          }
                        />
                      </AntForm.Item>
                    ),
                  },
                  ...buildDocumentDetailPartnerMaterialFormColumns(t, 'supplier'),
                  buildDocumentLineAttachmentsFormColumn(
                    t,
                    DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY.purchaseOrder,
                  ),
                  {
                    title: t('app.kuaizhizao.purchaseOrder.form.lineNotes'),
                    dataIndex: 'notes',
                    width: DOCUMENT_DETAIL_COL_WIDTH.notes,
                    ...DOCUMENT_DETAIL_TEXT_COL,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item name={[index, 'notes']} style={{ margin: 0 }}>
                        <Input
                          placeholder={t('app.kuaizhizao.purchaseOrder.form.lineNotes')}
                          size={DOCUMENT_DETAIL_CONTROL_SIZE}
                        />
                      </AntForm.Item>
                    ),
                  },
                ]}
                disabledAdd
                minRows={1}
                initialValue={{ ...defaultOrderItem, tax_rate: 0, required_date: dayjs() }}
                tableProps={DOCUMENT_DETAIL_TABLE_PROPS}
              />
              </>
            );
          }}
        </AntForm.Item>

        <FeeDetailsTable name="fee_details" label={t('app.kuaizhizao.salesOrder.feeDetailsFormLabel')} />

        <AntForm.Item
          noStyle
          shouldUpdate={(prev: any, curr: any) =>
            prev?.items !== curr?.items ||
            prev?.fee_details !== curr?.fee_details ||
            prev?.price_type !== curr?.price_type
          }
        >
          {({ getFieldValue }: { getFieldValue: (n: string) => any }) => (
            <DocumentAmountSummary variant="purchase" getFieldValue={getFieldValue} quantityField="ordered_quantity" />
          )}
        </AntForm.Item>

        <ProFormTextArea
          name="notes"
          label={t('common.remark')}
          placeholder={t('app.kuaizhizao.purchaseOrder.form.notesPlaceholder')}
          fieldProps={{ rows: 3 }}
        />
      </DetailDrawerSection>

      <DetailDrawerSection titleAccent title={t('app.kuaizhizao.purchaseOrder.paymentPlan')}>
        <OrderPaymentMilestonesFields
          variant="purchase"
          formRef={formRef}
          t={t}
          amountDecimals={amountDecimals}
          bankAccountOptions={bankAccountOptions}
        />
      </DetailDrawerSection>

      <DetailDrawerSection titleAccent title={t('app.uniDetail.sectionAttachments')} marginBottom={0}>
        <DocumentAttachmentsField
          category="purchase_order_attachments"
          label={false}
        />
      </DetailDrawerSection>
    </>
  );

  const purchaseOrderFormAuxModals = (
    <>
        <UniMaterialBatchPicker
          open={materialPickerOpen}
          onCancel={() => setMaterialPickerOpen(false)}
          onConfirm={appendPurchaseItemsFromMaterials}
        />
      <Suspense fallback={null}>
        <LazyUniImport
          visible={importModalVisible}
          onCancel={() => setImportModalVisible(false)}
          onConfirm={handleItemImport}
          title={t('app.kuaizhizao.purchaseOrder.importItemsTitle')}
          headers={[t('app.kuaizhizao.purchaseOrder.importItems.materialCode'), t('app.kuaizhizao.purchaseOrder.importItems.spec'), t('common.unit'), t('common.quantity'), t('app.kuaizhizao.purchaseOrder.importItems.unitPrice'), t('app.kuaizhizao.purchaseOrder.importItems.requiredDate')]}
          exampleRow={['MAT001', 'Spec X', pickImportExampleValue(purchaseOrderLineUnitOptions, t('app.kuaizhizao.purchaseOrder.importItems.exampleUnit')), '10', '100', '2026-03-01']}
          columnOptions={purchaseOrderLineImportColumnOptions}
        />
      </Suspense>
    </>
  );

  if (isFormPage) {
    const canSubmitAfterSave =
      isCreatePage || (isEditPage && isDraftStatus(currentOrder?.status));
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
                onClick={leavePurchaseOrderFormPage}
              />
              <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
                {isCreatePage
                  ? t('app.kuaizhizao.menu.purchase-management.purchase-orders.new')
                  : t('app.kuaizhizao.menu.purchase-management.purchase-orders.edit')}
              </Typography.Title>
            </Space>
            <Space wrap align="center">
              <DocumentFormPageHeaderActions
                onCancel={leavePurchaseOrderFormPage}
                onSaveDraft={() => void handleSaveDraft()}
                onPrimarySubmit={() => void triggerPurchaseOrderPrimarySubmit()}
                isCreatePage={isCreatePage}
                canSubmitAfterSave={canSubmitAfterSave}
                showSaveDraft={canSubmitAfterSave}
                primaryLoading={purchaseOrderFormSubmitting}
                saveDraftLoading={purchaseOrderFormSubmitting}
              />
              {isCreatePage && kuaiaiAvailable ? (
                <PurchaseOrderAiCreateTrigger formRef={formRef} />
              ) : null}
            </Space>
            </>
          }
        >
          <div className="form-modal-content-inner">
              {isCreatePage && !createFormSeed ? (
                <Alert
                  type="error"
                  showIcon
                  title={t('app.kuaizhizao.documentFlow.draftMissing')}
                />
              ) : (
              <ProForm
                key={
                  isCreatePage
                    ? `purchase-order-create:${location.search}`
                    : `purchase-order-edit:${editRouteId ?? ''}`
                }
                formRef={formRef}
                layout="vertical"
                submitter={false}
                scrollToFirstError
                onFinish={handleFormSubmit}
                onFinishFailed={({ errorFields }) => {
                  const first = errorFields?.[0];
                  const errText = first?.errors?.filter(Boolean)[0];
                  messageApi.error(errText || t('components.layoutTemplates.formModal.checkFormHint'));
                }}
                initialValues={isCreatePage ? createFormSeed ?? undefined : undefined}
              >
                {purchaseOrderFormItemContent}
              </ProForm>
              )}
            </div>
        </DocumentFormPageLayout>
        {purchaseOrderFormAuxModals}
      </>
    );
  }

  return (
    <>
      <style>{`
        .purchase-order-row-overdue td.ant-table-cell {
          background: var(--ant-color-warning-bg) !important;
        }
      `}</style>
      <ListPageTemplate statCards={statCards}>
        <UniTable<PurchaseOrder>
          columnPersistenceId={purchaseOrderListPersistenceId}
          headerTitle={t('app.kuaizhizao.menu.purchase-management.purchase-orders')}
          formRef={tableSearchFormRef}
          actionRef={actionRef}
          viewTypes={['table', 'detailTable', 'help']}
          defaultViewType={viewTypeState === 'help' ? 'table' : viewTypeState}
          onViewTypeChange={(v) => {
            const nextMode = v === 'table' ? 'order' : 'detail';
            dataViewModeRef.current = nextMode;
            setViewTypeState(v as 'table' | 'detailTable' | 'help');
            setSelectedRowKeys([]);
            setTimeout(() => actionRef.current?.reload(), 0);
          }}
          detailTableColumns={detailTableColumns}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.purchaseOrder)}
          rowKey={dataViewMode === 'detail' ? '_rowKey' : 'id'}
          rowClassName={(record) => {
            if (!highlightDeliveryOverdue) return '';
            if (dataViewMode === 'order') {
              return isPurchaseOrderDeliveryOverdue(record as PurchaseOrder, purchaseOrderAuditEnabled)
                ? 'purchase-order-row-overdue'
                : '';
            }
            const row = record as PurchaseOrderItemRow;
            return isPurchaseOrderDeliveryOverdue(
              {
                delivery_date: row.required_date || row.delivery_date,
                status: row.status,
                review_status: row.review_status,
              } as PurchaseOrder,
              purchaseOrderAuditEnabled,
            )
              ? 'purchase-order-row-overdue'
              : '';
          }}
          columns={columns}
          showAdvancedSearch={true}
          skipFuzzyPinyinClientFilter
          pinnedTabsField={LIST_LIFECYCLE_STAGE_FIELD}
          pinnedTabsValueEnum={lifecycleValueEnum}
          showCreateButton={false}
          createButtonText={t('app.kuaizhizao.menu.purchase-management.purchase-orders.new')}
          onCreate={handleCreate}
          toolBarRender={() => [
            <UniPullCreateToolbar
              compactKey="create-purchase-order-with-pull"
              createIcon={<PlusOutlined />}
              createLabel={
                requirePurchaseRequisition
                  ? pullFromRequisitionAction.label
                  : t('app.kuaizhizao.menu.purchase-management.purchase-orders.new')
              }
              onCreate={handleCreate}
              menuItems={[
                ...buildKuaizhizaoPullCreateMenuItems(
                  t,
                  requirePurchaseRequisition
                    ? [
                        {
                          key: 'pull-from-requisition',
                          actionKey: 'purchase_order.pull_from_requisition',
                          onClick: pullFromRequisitionQuery.openModal,
                        },
                      ]
                    : [
                        {
                          key: 'pull-from-requisition',
                          actionKey: 'purchase_order.pull_from_requisition',
                          onClick: pullFromRequisitionQuery.openModal,
                        },
                        {
                          key: 'pull-from-inquiry',
                          actionKey: 'purchase_order.pull_from_inquiry',
                          onClick: pullFromInquiryQuery.openModal,
                        },
                        {
                          key: 'pull-from-sales-order',
                          actionKey: 'purchase_order.pull_from_sales_order',
                          onClick: pullFromSalesOrderQuery.openModal,
                        },
                      ],
                ),
                { key: 'copy-selected-divider', type: 'divider' },
                {
                  key: 'copy-selected-create',
                  label: t('app.kuaizhizao.purchaseOrder.copySelectedCreate'),
                  disabled: !selectedOrderForToolbar,
                  onClick: () => {
                    void handleCopySelectedPurchaseOrder();
                  },
                },
              ]}
            />,
            <UniPushToolbarButton
              key={`purchase-order-push-${selectedOrderForToolbar?.id ?? 'none'}`}
              menuItems={toolbarPushMenuItems}
              disabled={selectedRowKeys.length !== 1 || !selectedOrderForToolbar}
              disabledReason={purchaseOrderToolbarPushDisabledReason}
              sourceDocument={
                selectedOrderForToolbar?.id
                  ? { type: 'purchase_order', id: Number(selectedOrderForToolbar.id) }
                  : null
              }
              pushTargets={{
                'receipt-notice': 'receipt_notice',
                receipt: 'purchase_receipt',
                invoice: 'purchase_invoice',
                prepayment: 'payment',
                'incoming-inspection': 'incoming_inspection',
                'purchase-return': 'purchase_return',
                'purchase-order-change': 'purchase_order_change',
              }}
            />,
          ]}
          enableRowSelection={viewTypeState !== 'detailTable'}
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          onTableDataChange={setTableOrders}
          showDeleteButton={viewTypeState !== 'detailTable'}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) => t('app.kuaizhizao.purchaseOrder.confirmBatchDelete', { count })}
          toolBarActionsAfterDelete={[
            <UniAuditBatchMenuButton
              key="purchase-order-batch-menu"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedOrdersForBatch}
              auditEnabled={purchaseOrderAuditEnabled}
              permGates={purchaseOrderPerms}
              handlers={purchaseOrderAuditBatchHandlers}
              extraMenuItems={purchaseOrderBatchExtraMenuItems}
              onSuccess={handlePurchaseOrderAuditBatchSuccess}
              toolBarButtonSize="medium"
            />,
          ]}
          rightToolBarActionsBeforeExport={[
            <UniCapabilityBatchButton
              key="purchase-order-print"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedOrdersForBatch}
              capabilityKey="print"
              permAllowed={purchaseOrderPerms.canPrint}
              batchAllowed={(records, perm) =>
                Boolean(perm) && records.some((record) => record.capabilities?.print?.allowed === true)
              }
              singleOnly
              onRun={async (id) => {
                openPrint({ documentType: 'purchase_order', documentId: id });
              }}
              labels={{
                single: t('components.uniAction.print'),
                batch: t('components.uniAction.print'),
              }}
              icon={<PrinterOutlined />}
              size="medium"
            />,
          ]}
          showImportButton={viewTypeState !== 'detailTable'}
          onImport={handleListImport}
          importHeaders={purchaseOrderImportTemplate.importHeaders}
          importExampleRow={purchaseOrderImportTemplate.importExampleRow}
          importColumnOptions={purchaseOrderImportTemplate.importColumnOptions}
          importFieldMap={purchaseOrderImportTemplate.importHeaderMap}
          showExportButton
          onExport={async (type, keys, pageData) => {
            try {
              const flattenOrders = (orders: PurchaseOrder[]): Array<Record<string, unknown>> => {
                if (dataViewModeRef.current !== 'detail') {
                  return orders as Array<Record<string, unknown>>;
                }
                const flatRows: Array<Record<string, unknown>> = [];
                for (const order of orders) {
                  const items = order.items ?? [];
                  if (items.length === 0) {
                    flatRows.push({
                      _rowKey: `order-${order.id}-empty`,
                      purchase_order_id: order.id,
                      order_code: order.order_code,
                      supplier_name: order.supplier_name,
                      material_code: '-',
                      material_name: '-',
                      ordered_quantity: 0,
                    });
                  } else {
                    items.forEach((item, idx) => {
                      flatRows.push({
                        ...item,
                        _rowKey: item.id
                          ? `order-${order.id}-item-${item.id}`
                          : `order-${order.id}-idx-${idx}`,
                        purchase_order_id: order.id,
                        order_code: order.order_code,
                        supplier_name: order.supplier_name,
                        buyer_name: order.buyer_name,
                        order_date: order.order_date,
                        delivery_date: order.delivery_date,
                        status: order.status,
                        review_status: order.review_status,
                      });
                    });
                  }
                }
                return flatRows;
              };

              let orders = (type === 'currentPage' ? (pageData ?? []) : await fetchAllListItems((p) =>
                listPurchaseOrders({
                  ...p,
                  include_items: true,
                }),
              ));
              let toExport: Array<Record<string, unknown>>;
              if (type === 'currentPage' && pageData?.length) {
                toExport = pageData as Array<Record<string, unknown>>;
              } else if (type === 'selected' && keys?.length) {
                if (dataViewModeRef.current === 'detail') {
                  toExport = flattenOrders(orders).filter((r) => keys.includes(String(r._rowKey)));
                } else {
                  toExport = (orders as PurchaseOrder[]).filter(
                    (d) => d.id != null && keys.includes(d.id),
                  ) as Array<Record<string, unknown>>;
                }
              } else {
                toExport = flattenOrders(orders);
              }
              if (toExport.length === 0) {
                messageApi.warning(t('common.noDataToExport'));
                return;
              }
              await downloadRecordsAsXlsx(
                toExport,
                `purchase-orders-${todaySiteDateString()}.xlsx`,
              );
              messageApi.success(t('common.exportSuccess', { count: toExport.length }));
            } catch (error: any) {
              messageApi.error(error?.message || t('common.exportFailed'));
            }
          }}
          showSyncButton={
            viewTypeState !== 'detailTable' &&
            toolbarSyncPush.hubVisible
          }
          onSync={() => undefined}
          syncToolbarExtra={
            viewTypeState !== 'detailTable' &&
            toolbarSyncPush.hubVisible
              ? () => (
                  <SyncPushHubButton
                    syncEnabled={toolbarSyncPush.syncEnabled}
                    pushEnabled={toolbarSyncPush.pushEnabled}
                    historySourceType="purchase_order"
                    historyTargetProfiles={['kingdee_pur_purchaseorder']}
                    size="medium"
                    wrapButton={(hubButton) => (
                      <SyncFreshnessBadge
                        getBinding={loadPurchaseOrderSyncBinding}
                        refreshKey={syncFreshnessKey}
                      >
                        {hubButton}
                      </SyncFreshnessBadge>
                    )}
                    renderSyncPanel={({ active, close }) => (
                      <PurchaseOrderSyncFromSourceModal
                        contentOnly
                        open={active}
                        onClose={close}
                        onComplete={() => {
                          handleSyncComplete();
                          close();
                        }}
                      />
                    )}
                    renderPushPanel={({ active, close }) => (
                      <PurchaseOrderDocumentPushPanel
                        embedded
                        open={active}
                        onClose={close}
                        orderIds={selectedOrdersForBatch
                          .map((o) => Number(o.id))
                          .filter((id) => Number.isFinite(id) && id > 0)}
                        onComplete={() => {
                          handleSyncComplete();
                          close();
                        }}
                      />
                    )}
                  />
                )
              : undefined
          }
          toolBarActionsEnd={[purchaseOrderHighlightOverdueToolbar]}
          request={async (params, sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
            try {
              const apiParams = resolvePurchaseOrderListApiParams(params, sort, searchFormValues);

              const toFlatRows = (orders: PurchaseOrder[]): PurchaseOrderItemRow[] => {
                const flatRows: PurchaseOrderItemRow[] = [];
                for (const order of orders) {
                  const items = order.items ?? [];
                  if (items.length === 0) {
                    flatRows.push({
                      _rowKey: `order-${order.id}-empty`,
                      purchase_order_id: order.id ?? 0,
                      order_code: order.order_code,
                      supplier_name: order.supplier_name,
                      buyer_name: order.buyer_name,
                      order_date: order.order_date,
                      delivery_date: order.delivery_date,
                      total_quantity: order.total_quantity,
                      total_amount: order.total_amount,
                      net_amount: order.net_amount,
                      tax_amount: order.tax_amount,
                      tax_rate: order.tax_rate,
                      status: order.status,
                      review_status: order.review_status,
                      receipt_progress: order.receipt_progress,
                      downstream_push_progress: order.downstream_push_progress,
                      material_id: 0,
                      material_code: '-',
                      material_name: '-',
                      ordered_quantity: 0,
                      unit: '',
                      unit_price: 0,
                      total_price: 0,
                    } as PurchaseOrderItemRow);
                  } else {
                    items.forEach((item, idx) => {
                      flatRows.push({
                        ...item,
                        _rowKey: item.id
                          ? `order-${order.id}-item-${item.id}`
                          : `order-${order.id}-idx-${idx}`,
                        purchase_order_id: order.id ?? 0,
                        order_code: order.order_code,
                        supplier_name: order.supplier_name,
                        buyer_name: order.buyer_name,
                        order_date: order.order_date,
                        delivery_date: order.delivery_date,
                        total_quantity: order.total_quantity,
                        total_amount: order.total_amount,
                        net_amount: order.net_amount,
                        tax_amount: order.tax_amount,
                        tax_rate: order.tax_rate,
                        status: order.status,
                        review_status: order.review_status,
                        receipt_progress: order.receipt_progress,
                        downstream_push_progress: order.downstream_push_progress,
                      } as PurchaseOrderItemRow);
                    });
                  }
                }
                return flatRows;
              };

              const formatListResponse = async (orders: PurchaseOrder[], total: number) => {
                if (dataViewModeRef.current === 'order') {
                  const enriched = meta?.purpose === 'prefetch'
                    ? orders
                    : await enrichPurchaseOrderRecordsWithCustomFields(orders);
                  return { data: enriched, success: true, total };
                }
                return { data: toFlatRows(orders), success: true, total };
              };

              const response = await listPurchaseOrders(
                apiParams as Parameters<typeof listPurchaseOrders>[0],
              );
              const orders = response.data || [];
              const total = response.total || 0;
              return formatListResponse(orders, total);
            } catch (error) {
              messageApi.error(t('app.kuaizhizao.purchaseOrder.listFailed'));
              return {
                data: [],
                success: false,
                total: 0,
              };
            }
          }}
        />
      </ListPageTemplate>

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
        searchPlaceholder={t('app.kuaizhizao.purchaseOrder.pull.searchPlaceholder')}
        filterExtra={(
          <Space wrap size={8}>
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.purchaseOrder.pull.orderTypePlaceholder')}
              style={{ width: 160, flexShrink: 0 }}
              value={pullSourceOrderType}
              options={orderTypeOptions}
              loading={orderTypeLoading}
              onChange={(value) => {
                const next =
                  value != null && String(value).trim() ? String(value).trim() : undefined;
                pullSourceOrderTypeRef.current = next;
                setPullSourceOrderType(next);
                pullFromRequisitionQuery.handleSearchApply(
                  pullFromRequisitionQuery.appliedKeyword,
                );
              }}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.purchaseOrder.pull.sourceDocPlaceholder')}
              style={{ width: 220, flexShrink: 0 }}
              value={pullSourceRequisitionId}
              options={pullSourceRequisitionOptions}
              onChange={(value) => {
                const nextId = Number(value);
                const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
                pullSourceRequisitionIdRef.current = next;
                setPullSourceRequisitionId(next);
                pullFromRequisitionQuery.handleSearchApply(
                  pullFromRequisitionQuery.appliedKeyword,
                );
              }}
            />
          </Space>
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
        okText={t('app.kuaizhizao.purchaseOrder.pull.ok')}
      />

      <UniPullQueryModal<PullPurchaseInquiryCandidate>
        open={pullFromInquiryQuery.open}
        title={pullFromInquiryAction.label}
        onCancel={pullFromInquiryQuery.closeModal}
        onOk={pullFromInquiryQuery.handleConfirm}
        rowKey="id"
        columns={pullInquiryColumns}
        dataSource={pullFromInquiryQuery.dataSource}
        loading={pullFromInquiryQuery.loading}
        confirmLoading={pullFromInquiryQuery.confirmLoading}
        selectionType={pullFromInquiryQuery.selectionType}
        selectedRowKeys={pullFromInquiryQuery.selectedRowKeys}
        selectedRows={pullFromInquiryQuery.selectedRows}
        onSelectedRowKeysChange={pullFromInquiryQuery.handleSelectedRowKeysChange}
        isRowDisabled={pullFromInquiryQuery.isRowDisabled}
        searchDraft={pullFromInquiryQuery.searchDraft}
        onSearchDraftChange={pullFromInquiryQuery.setSearchDraft}
        onSearchApply={pullFromInquiryQuery.handleSearchApply}
        onSearchClear={pullFromInquiryQuery.handleSearchClear}
        appliedKeyword={pullFromInquiryQuery.appliedKeyword}
        searchPlaceholder={t('app.kuaizhizao.purchaseOrder.pull.searchPlaceholder')}
        filterExtra={(
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaizhizao.purchaseOrder.pull.sourceDocPlaceholder')}
            style={{ width: 220, flexShrink: 0 }}
            value={pullSourceInquiryId}
            options={pullSourceInquiryOptions}
            onChange={(value) => {
              const nextId = Number(value);
              const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
              pullSourceInquiryIdRef.current = next;
              setPullSourceInquiryId(next);
              pullFromInquiryQuery.handleSelectedRowKeysChange([], []);
              pullFromInquiryQuery.handleSearchApply(pullFromInquiryQuery.appliedKeyword);
            }}
          />
        )}
        getRowLabel={(row) =>
          [row.inquiry_code, row.material_code].filter(Boolean).join(' ')
        }
        page={pullFromInquiryQuery.page}
        pageSize={pullFromInquiryQuery.pageSize}
        total={pullFromInquiryQuery.total}
        onPageChange={pullFromInquiryQuery.handlePageChange}
        scopeOptions={pullFromInquiryQuery.scopeOptions}
        scope={pullFromInquiryQuery.scope}
        onScopeChange={pullFromInquiryQuery.handleScopeChange}
        okText={t('app.kuaizhizao.purchaseOrder.pull.ok')}
      />

      <UniPullQueryModal<PurchaseOrderSalesOrderPullCandidate>
        open={pullFromSalesOrderQuery.open}
        title={pullFromSalesOrderAction.label}
        onCancel={pullFromSalesOrderQuery.closeModal}
        onOk={pullFromSalesOrderQuery.handleConfirm}
        rowKey="id"
        columns={pullSalesOrderColumns}
        dataSource={pullFromSalesOrderQuery.dataSource}
        loading={pullFromSalesOrderQuery.loading}
        confirmLoading={pullFromSalesOrderQuery.confirmLoading}
        selectionType={pullFromSalesOrderQuery.selectionType}
        selectedRowKeys={pullFromSalesOrderQuery.selectedRowKeys}
        selectedRows={pullFromSalesOrderQuery.selectedRows}
        onSelectedRowKeysChange={pullFromSalesOrderQuery.handleSelectedRowKeysChange}
        searchDraft={pullFromSalesOrderQuery.searchDraft}
        onSearchDraftChange={pullFromSalesOrderQuery.setSearchDraft}
        onSearchApply={pullFromSalesOrderQuery.handleSearchApply}
        onSearchClear={pullFromSalesOrderQuery.handleSearchClear}
        appliedKeyword={pullFromSalesOrderQuery.appliedKeyword}
        searchPlaceholder={t('app.kuaizhizao.purchaseOrder.pull.searchPlaceholder')}
        getRowLabel={(row) => String(row.order_code || row.id)}
        page={pullFromSalesOrderQuery.page}
        pageSize={pullFromSalesOrderQuery.pageSize}
        total={pullFromSalesOrderQuery.total}
        onPageChange={pullFromSalesOrderQuery.handlePageChange}
        scopeOptions={pullFromSalesOrderQuery.scopeOptions}
        scope={pullFromSalesOrderQuery.scope}
        onScopeChange={pullFromSalesOrderQuery.handleScopeChange}
        okText={t('app.kuaizhizao.purchaseOrder.pull.ok')}
      />

      <Modal
        title={pushPreviewModalTitle}
        open={pushPreviewOpen}
        destroyOnHidden
        width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
        styles={{ body: { maxHeight: MODAL_CONFIG.BODY_MAX_HEIGHT, overflow: 'auto' } }}
        onCancel={resetPushPreviewModal}
        okText={pushPreviewConfirmLabel}
        cancelText={t('common.cancel')}
        confirmLoading={pushPreviewConfirming}
        onOk={() => void handlePushPreviewConfirm()}
        okButtonProps={{
          disabled:
            pushPreviewLoading ||
            !pushPreviewData ||
            !!pushPreviewData?.has_blocking_issues ||
            (pushPreviewKind === 'invoice' ||
            pushPreviewKind === 'prepayment' ||
            pushPreviewKind === 'payment_application'
              ? !(pushInvoiceAmount > 0)
              : pushPreviewSelectedItemIds.length === 0),
        }}
      >
        {pushPreviewLoading ? (
          <div style={{ minHeight: 120, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
            <Spin />
            <div style={{ color: 'var(--ant-color-primary)' }}>{t('app.kuaizhizao.salesOrder.loadingPreview')}</div>
          </div>
        ) : pushPreviewData ? (
          <div>
            {pushPreviewKind !== 'invoice' ? (
              <p style={{ marginBottom: 12, fontWeight: 500 }}>{pushPreviewData.summary}</p>
            ) : null}
            {pushPreviewData.has_blocking_issues && pushPreviewData.blocking_reason ? (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                title={purchaseOrderCapabilityReasonMessage(pushPreviewData.blocking_reason, t) || t('app.kuaizhizao.purchaseOrder.push.previewFailed')}
              />
            ) : null}
            {(pushPreviewKind === 'prepayment' || pushPreviewKind === 'payment_application') &&
            !pushPreviewData.has_blocking_issues ? (
              <div style={{ marginBottom: 12 }}>
                <div style={{ marginBottom: 8 }}>
                  {pushPreviewKind === 'payment_application'
                    ? t('app.kuaizhizao.paymentApplication.requestAmount')
                    : t('app.kuaizhizao.purchaseOrder.pushPrepaymentAmount')}
                </div>
                <InputNumber
                  style={{ width: 280 }}
                  min={0.01}
                  precision={2}
                  value={pushInvoiceAmount > 0 ? pushInvoiceAmount : undefined}
                  onChange={(v) => setPushInvoiceAmount(Number(v) || 0)}
                />
              </div>
            ) : null}
            {pushPreviewKind !== 'invoice' &&
            pushPreviewKind !== 'prepayment' &&
            pushPreviewKind !== 'payment_application' &&
            pushPreviewData.items?.length > 0 ? (
              <Table
                size="small"
                dataSource={pushPreviewData.items}
                rowKey={(row) => String(row.item_id)}
                pagination={false}
                tableLayout="fixed"
                columns={[
                  {
                    title: t('common.select'),
                    dataIndex: 'item_id',
                    key: 'select',
                    width: 64,
                    render: (_: unknown, row: DocumentPushPreview['items'][number]) => {
                      const itemId = Number(row?.item_id);
                      if (!Number.isFinite(itemId) || itemId <= 0) return null;
                      const maxQty = Number(row?.max_push_quantity ?? 0);
                      const disabled = !Number.isFinite(maxQty) || maxQty <= 0;
                      return (
                        <Switch
                          size="small"
                          disabled={disabled}
                          checked={pushPreviewSelectedItemIds.includes(itemId)}
                          onChange={(checked) => {
                            setPushPreviewSelectedItemIds((prev) =>
                              checked ? Array.from(new Set([...prev, itemId])) : prev.filter((id) => id !== itemId),
                            );
                          }}
                        />
                      );
                    },
                  },
                  { title: t('app.kuaizhizao.salesOrder.materialCode'), dataIndex: 'material_code', width: 140, ellipsis: true },
                  { title: t('app.kuaizhizao.salesOrder.materialName'), dataIndex: 'material_name', width: 200, ellipsis: true },
                  { title: pushPreviewQtyColumnTitles.quantity, dataIndex: 'quantity', width: 90, align: 'right', render: formatQuantity },
                  { title: pushPreviewQtyColumnTitles.pushed, dataIndex: 'pushed_quantity', width: 90, align: 'right', render: formatQuantity },
                  { title: pushPreviewQtyColumnTitles.pushable, dataIndex: 'max_push_quantity', width: 90, align: 'right', render: formatQuantity },
                  ...(pushPreviewKind === 'receipt_notice' || pushPreviewKind === 'receipt'
                    ? [
                        {
                          title: (
                            <>
                              {t('app.kuaizhizao.purchaseOrder.pushReceiptWarehouse')}
                              <Typography.Text type="danger"> *</Typography.Text>
                            </>
                          ),
                          key: 'warehouse_id',
                          width: 200,
                          render: (_: unknown, row: DocumentPushPreview['items'][number]) => {
                            const itemId = Number(row?.item_id);
                            if (!Number.isFinite(itemId) || itemId <= 0) return null;
                            const selected = pushPreviewSelectedItemIds.includes(itemId);
                            return (
                              <Select
                                style={{ width: '100%', minWidth: 140 }}
                                placeholder={t('app.kuaizhizao.purchaseOrder.pushReceiptSelectWarehouse')}
                                showSearch
                                optionFilterProp="label"
                                disabled={!selected}
                                value={pushPreviewLineWh[itemId]}
                                options={pushPreviewWarehouseOptions}
                                onChange={(nv) => {
                                  setPushPreviewLineWh((prev) => ({ ...prev, [itemId]: Number(nv) }));
                                }}
                              />
                            );
                          },
                        },
                        {
                          title: t('app.kuaizhizao.salesOrder.colPushQty'),
                          key: 'push_qty',
                          width: 120,
                          align: 'right' as const,
                          render: (_: unknown, row: DocumentPushPreview['items'][number]) => {
                            const itemId = Number(row?.item_id);
                            if (!Number.isFinite(itemId) || itemId <= 0) return null;
                            const maxQty = Number(row?.max_push_quantity ?? 0);
                            const selected = pushPreviewSelectedItemIds.includes(itemId);
                            return (
                              <InputNumber
                                min={0}
                                max={maxQty > 0 ? maxQty : undefined}
                                disabled={!selected || maxQty <= 0}
                                value={pushPreviewQuantities[itemId] ?? 0}
                                onChange={(v) => {
                                  setPushPreviewQuantities((prev) => ({
                                    ...prev,
                                    [itemId]: Number(v) || 0,
                                  }));
                                }}
                                style={{ width: 100 }}
                              />
                            );
                          },
                        },
                      ]
                    : pushPreviewKind === 'purchase_return' || pushPreviewKind === 'incoming_inspection'
                      ? [
                          {
                            title: t('app.kuaizhizao.salesOrder.colPushQty'),
                            key: 'push_qty',
                            width: 120,
                            align: 'right' as const,
                            render: (_: unknown, row: DocumentPushPreview['items'][number]) => {
                              const itemId = Number(row?.item_id);
                              if (!Number.isFinite(itemId) || itemId <= 0) return null;
                              const maxQty = Number(row?.max_push_quantity ?? 0);
                              const selected = pushPreviewSelectedItemIds.includes(itemId);
                              return (
                                <InputNumber
                                  min={0}
                                  max={maxQty > 0 ? maxQty : undefined}
                                  disabled={!selected || maxQty <= 0}
                                  value={pushPreviewQuantities[itemId] ?? 0}
                                  onChange={(v) => {
                                    setPushPreviewQuantities((prev) => ({
                                      ...prev,
                                      [itemId]: Number(v) || 0,
                                    }));
                                  }}
                                  style={{ width: 100 }}
                                />
                              );
                            },
                          },
                        ]
                      : []),
                ]}
              />
            ) : pushPreviewKind === 'invoice' ? (
              <div>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 12 }}
                  title={pushPreviewData.summary}
                  description={
                    <Space orientation="vertical" size={4} style={{ width: '100%' }}>
                      <Typography.Text>
                        {t('app.kuaizhizao.purchaseOrder.pushInvoiceOrderTotal')}:{' '}
                        {formatCurrencyAmount(pushPreviewData.order_total)}
                      </Typography.Text>
                      <Typography.Text>
                        {t('app.kuaizhizao.purchaseOrder.pushInvoiceInvoiced')}:{' '}
                        {formatCurrencyAmount(pushPreviewData.invoiced_total)}
                      </Typography.Text>
                      <Typography.Text>
                        {t('app.kuaizhizao.purchaseOrder.pushInvoiceRemaining')}:{' '}
                        {formatCurrencyAmount(pushPreviewData.remaining_total)}
                      </Typography.Text>
                      <Typography.Text>
                        {t('app.kuaizhizao.purchaseOrder.pushInvoicePrepayment')}:{' '}
                        {formatCurrencyAmount(pushPreviewData.prepayment_amount)}
                      </Typography.Text>
                    </Space>
                  }
                />
                <div style={{ marginBottom: 12 }}>
                  <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                    {t('app.kuaizhizao.purchaseOrder.pushInvoiceMode')}
                  </Typography.Text>
                  <Radio.Group
                    value={pushInvoiceMode}
                    onChange={(e) => {
                      const next = e.target.value as PurchaseInvoicePushMode;
                      setPushInvoiceMode(next);
                      const modeRow = (pushPreviewData.invoice_modes || []).find((m) => m.key === next);
                      setPushInvoiceAmount(Number(modeRow?.amount ?? 0));
                    }}
                    options={(pushPreviewData.invoice_modes || []).map((m) => ({
                      value: m.key,
                      disabled: !m.allowed,
                      label:
                        m.key === 'prepayment'
                          ? t('app.kuaizhizao.purchaseOrder.pushInvoiceByPrepayment')
                          : t('app.kuaizhizao.purchaseOrder.pushInvoiceByRemaining'),
                    }))}
                  />
                </div>
                <div style={{ marginBottom: 12, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                  <div>
                    <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                      {t('app.kuaizhizao.purchaseOrder.pushInvoiceAmount')}
                    </Typography.Text>
                    <InputNumber
                      min={0.01}
                      max={
                        pushInvoiceMode === 'prepayment'
                          ? Number(pushPreviewData.prepayment_pushable ?? 0) || undefined
                          : Number(pushPreviewData.remaining_total ?? 0) || undefined
                      }
                      precision={2}
                      style={{ width: 220 }}
                      value={pushInvoiceAmount}
                      onChange={(v) => setPushInvoiceAmount(Number(v) || 0)}
                    />
                  </div>
                  <div>
                    <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                      {t('app.kuaizhizao.purchaseOrder.pushInvoiceNumber')}
                    </Typography.Text>
                    <Input
                      allowClear
                      maxLength={100}
                      style={{ width: 220 }}
                      value={pushInvoiceNumber}
                      onChange={(e) => setPushInvoiceNumber(e.target.value)}
                      placeholder={t('app.kuaizhizao.purchaseOrder.pushInvoiceNumberPlaceholder')}
                    />
                  </div>
                </div>
                {pushPreviewData.items?.length > 0 ? (
                  <Table
                    size="small"
                    dataSource={pushPreviewData.items}
                    rowKey={(row) => String(row.item_id)}
                    pagination={false}
                    scroll={{ x: 860 }}
                    columns={[
                      { title: t('app.kuaizhizao.salesOrder.materialCode'), dataIndex: 'material_code', width: 130, ellipsis: true },
                      { title: t('app.kuaizhizao.salesOrder.materialName'), dataIndex: 'material_name', width: 160, ellipsis: true },
                      { title: t('common.quantity'), dataIndex: 'quantity', width: 90, align: 'right', render: formatQuantity },
                    ]}
                  />
                ) : null}
              </div>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.purchaseOrder.pull.previewNoLines')} />
            )}
            {pushPreviewKind === 'incoming_inspection' && !pushPreviewData.has_blocking_issues ? (
              <div style={{ marginTop: 12 }}>
                <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                  {t('app.kuaizhizao.purchaseOrder.pushIncomingInspectionNotes')}
                </Typography.Text>
                <Input.TextArea
                  rows={3}
                  maxLength={500}
                  showCount
                  value={pushPreviewNotes}
                  onChange={(e) => setPushPreviewNotes(e.target.value)}
                  placeholder={t('app.kuaizhizao.purchaseOrder.pushIncomingInspectionNotesPlaceholder')}
                />
              </div>
            ) : null}
            {pushPreviewData.tip ? (
              <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                {pushPreviewData.tip}
              </Typography.Paragraph>
            ) : null}
          </div>
        ) : null}
      </Modal>

      <LandingCostAllocationModal
        visible={landingCostModalVisible}
        onCancel={() => {
          setLandingCostModalVisible(false);
          setLandingCostOrder(null);
        }}
        onSuccess={() => {
          setLandingCostModalVisible(false);
          setLandingCostOrder(null);
          invalidateMenuBadgeCounts();
    actionRef.current?.reload();
        }}
        orderId={landingCostOrder?.id || 0}
        orderCode={landingCostOrder?.order_code || ''}
      />

      <PurchaseOrderDetailDrawer
        open={detailDrawerVisible}
        zIndex={purchaseOrderDetailDrawerZIndex}
        onClose={() => {
          setDetailDrawerVisible(false);
          setOrderDetail(null);
          resetPurchaseOrderDetailFieldValues();
        }}
        order={orderDetail}
        trackingRefreshKey={poTrackingRefreshKey}
        customFields={purchaseOrderListCustomFields}
        customFieldValues={purchaseOrderDetailCustomFieldValues}
        feeTypeOptions={feeTypeOptions}
        extra={
          orderDetail ? (
            <DetailDrawerActions
              items={[
                {
                  key: 'create-change',
                  visible:
                    orderDetail.capabilities?.create_change_order?.allowed === true &&
                    purchaseOrderChangePerms.canCreate,
                  render: () => (
                    <Button
                      icon={<EditOutlined />}
                      onClick={() =>
                        navigate(
                          `/apps/kuaizhizao/purchase-management/purchase-order-changes?source_order_id=${orderDetail.id}`,
                        )
                      }
                    >
                      {t('app.kuaizhizao.purchaseOrder.createChange')}
                    </Button>
                  ),
                },
                {
                  key: 'edit',
                  visible: orderDetail.capabilities?.update?.allowed === true && purchaseOrderPerms.canUpdate,
                  render: () => (
                    <Button
                      {...rowActionKind('update')}
                      icon={<EditOutlined />}
                      onClick={() => {
                        setDetailDrawerVisible(false);
                        handleEdit(orderDetail);
                      }}
                    >
                      {t('common.edit')}
                    </Button>
                  ),
                },
                {
                  key: 'delete',
                  visible: orderDetail.capabilities?.delete?.allowed === true && purchaseOrderPerms.canDelete,
                  render: () => (
                    <Button
                      {...rowActionKind('delete')}
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => handleDelete(orderDetail)}
                    >
                      {t('common.delete')}
                    </Button>
                  ),
                },
                {
                  key: 'workflow',
                  render: () => (
                    <UniWorkflowActions
                      {...rowActionKind('skip')}
                      record={orderDetail}
                      entityName={t('app.kuaizhizao.purchaseOrder.entityName')}
                      {...PURCHASE_ORDER_WORKFLOW_PROPS}
                      submitActionLabel={t('app.kuaizhizao.purchaseOrder.submitForReview')}
                      theme="default"
                      onSuccess={() => {
                        invalidateStatistics();
    actionRef.current?.reload();
                        setPoTrackingRefreshKey((k) => k + 1);
                        void getPurchaseOrder(orderDetail.id!)
                          .then(setOrderDetail)
                          .catch((e: unknown) => {
                            const err = e as { message?: string };
                            messageApi.error(err?.message || t('app.kuaizhizao.purchaseOrder.detailFailed'));
                          });
                      }}
                    />
                  ),
                },
                {
                  key: 'print',
                  visible: orderDetail.id != null && purchaseOrderPerms.canPrint,
                  render: () => (
                    <Button
                      icon={<PrinterOutlined />}
                      onClick={() => openPrint({ documentType: 'purchase_order', documentId: orderDetail.id! })}
                    >
                      {t('components.uniAction.print')}
                    </Button>
                  ),
                },
              ]}
            />
          ) : null
        }
      />

      <PurchaseOrderSyncFromSourceModal
        open={syncModalVisible}
        onClose={() => setSyncModalVisible(false)}
        onComplete={handleSyncComplete}
      />

      <Modal
        title={pushToPurchaseReturnAction.label}
        open={pushToReturnVisible}
        onCancel={() => {
          setPushToReturnVisible(false);
          setPushToReturnOrder(null);
          setPushToReturnQuantities({});
          setPushToReturnLineMeta({});
          setPushToReturnWarehouseId(undefined);
          setPushToReturnWarehouseName('');
        }}
        onOk={handlePushToReturnConfirm}
        confirmLoading={pushToReturnLoading}
        okText={t('app.kuaizhizao.purchaseOrder.confirmPush')}
        width={MODAL_CONFIG.STANDARD_WIDTH}
        destroyOnHidden
      >
        {pushToReturnOrder && (
          <div>
            <p style={{ marginBottom: 12 }}>
              {t('app.kuaizhizao.purchaseOrder.pushReturnIntro', { code: pushToReturnOrder.order_code })}
            </p>
            <ProForm
              key={pushToReturnOrder.id}
              submitter={false}
              layout="vertical"
              style={{ marginBottom: 12 }}
            >
              <UniWarehouseSelect
                name="warehouse_id"
                label={t('app.kuaizhizao.purchaseOrder.returnWarehouse')}
                placeholder={t('app.kuaizhizao.purchaseOrder.selectReturnWarehouse')}
                required
                onChange={(value, warehouse) => {
                  setPushToReturnWarehouseId(value);
                  setPushToReturnWarehouseName(warehouse?.name ?? '');
                }}
                rules={[
                  {
                    required: true,
                    message: t('app.kuaizhizao.purchaseOrder.returnWarehouseRequired'),
                  },
                ]}
              />
            </ProForm>
            <Table
              size="small"
              dataSource={(pushToReturnOrder.items || []).filter((it: PurchaseOrderItem) => {
                if (it.id == null) return false;
                const meta = pushToReturnLineMeta[it.id];
                return meta ? meta.remaining > 0 : (it.received_quantity ?? 0) > 0;
              })}
              rowKey="id"
              pagination={false}
              scroll={{ x: 860 }}
              columns={[
                { title: t('app.kuaizhizao.purchaseOrder.col.materialCode'), dataIndex: 'material_code', width: 120 },
                { title: t('app.kuaizhizao.purchaseOrder.col.materialName'), dataIndex: 'material_name', width: 150 },
                {
                  title: t('app.kuaizhizao.purchaseOrder.col.receivedQty'),
                  width: 90,
                  align: 'right',
                  render: (_: unknown, record: PurchaseOrderItem) =>
                    formatQuantity(
                      record.id != null
                        ? pushToReturnLineMeta[record.id]?.received ?? record.received_quantity
                        : record.received_quantity,
                    ),
                },
                {
                  title: t('app.kuaizhizao.salesOrder.colPushedQty'),
                  width: 90,
                  align: 'right',
                  render: (_: unknown, record: PurchaseOrderItem) =>
                    formatQuantity(record.id != null ? pushToReturnLineMeta[record.id]?.pushed ?? 0 : 0),
                },
                {
                  title: t('app.kuaizhizao.salesOrder.colPushableQty'),
                  width: 90,
                  align: 'right',
                  render: (_: unknown, record: PurchaseOrderItem) =>
                    formatQuantity(
                      record.id != null
                        ? pushToReturnLineMeta[record.id]?.remaining ?? record.received_quantity
                        : record.received_quantity,
                    ),
                },
                {
                  title: t('app.kuaizhizao.purchaseOrder.col.returnQty'),
                  width: 140,
                  align: 'right',
                  render: (_: any, record: PurchaseOrderItem) => (record.id != null ? (
                    <InputNumber
                      min={0}
                      max={
                        pushToReturnLineMeta[record.id]?.remaining ??
                        Number(record.received_quantity ?? 0)
                      }
                      value={pushToReturnQuantities[record.id] ?? 0}
                      onChange={(v) =>
                        setPushToReturnQuantities((prev) => ({
                          ...prev,
                          [record.id!]: Number(v) || 0,
                        }))
                      }
                      style={{ width: 100 }}
                    />
                  ) : null),
                },
              ]}
            />
          </div>
        )}
      </Modal>
      {PrintModal}
    </>
  );
};

export default PurchaseOrdersPage;

