/**
 * 发货通知单管理页面
 *
 * 销售通知仓库发货，不直接动库存。来源为销售订单。
 * 参考销售订单排版布局，支持单据编号自动生成。
 *
 * @author RiverEdge Team
 * @date 2026-02-22
 */

import React, { useRef, useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react';
import { rowActionKind } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { createListAuditPhaseColumn } from '../shared/listAuditPhaseColumn';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { useLocation, useNavigate } from 'react-router-dom';
import { useDocumentHighlightDeepLink } from '../../../../../hooks/useDocumentHighlightDeepLink';
import { LinkedDocumentCode } from '../../../../../components/linked-document-code';
import { ActionType, ProColumns, ProDescriptionsItemProps, ProForm, ProFormText, ProFormDatePicker, ProFormTextArea, ProFormItem } from '@ant-design/pro-components';
import { App, Button, Space, Modal, Table, Form as AntForm, Select, InputNumber, Input, Row, Col, Typography, Dropdown, Spin, Empty, Descriptions, Alert } from 'antd';
import { ArrowLeftOutlined, PlusOutlined, EyeOutlined, EditOutlined, DeleteOutlined, SendOutlined, AppstoreAddOutlined, ImportOutlined, MoreOutlined, DownOutlined, PrinterOutlined } from '@ant-design/icons';
import { theme as AntdTheme } from 'antd';
import dayjs from 'dayjs';
import { UniTable, readPersistedUniTableViewType, type UniTableRequestMeta } from '../../../../../components/uni-table';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import {
  CustomFieldsFormSection,
  CustomFieldsDetailSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import {
  UniTableStackedPrimaryCell,
  MaterialStackedCell,
} from '../../../../../components/uni-table/stackedPrimaryColumn';
import {
  UniBatchMenuButton,
  UniCapabilityBatchButton,
  pickCapability,
  runCapabilityBatchLoop,
  withDocumentSubmitCombinedItem,
  type UniBatchMenuItem,
} from '../../../../../components/uni-batch';
import { isPendingReviewStatus } from '../../../constants/documentStatus';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import {
  buildDocumentDetailPartnerMaterialFormColumns,
  buildDocumentDetailSpecModelFormColumns,
  withMaterialLineFillMapping,
} from '../shared/materialLineFormDetail';
import {
  buildMaterialModelSpecColumns,
  buildPartnerMaterialLineColumns,
} from '../shared/materialLineColumns';
import { UniMaterialBatchPicker } from '../../../../../components/uni-material-batch-picker';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
const LazyUniImport = lazy(() =>
  import('../../../../../components/uni-import').then((m) => ({ default: m.UniImport })),
);
import type { Material } from '../../../../master-data/types/material';
import {
  buildDocumentLineAuxQuantityDetailColumn,
  buildDocumentLineDualQuantityPairColumns,
} from '../../../../../components/quantity-with-unit';
import { pickDocumentLineDualQuantityFields } from '../../../../../utils/materialDualQuantity';
import { DocumentAmountSummaryWatch } from '../../../components/document-amount-summary/DocumentAmountSummary';
import { computeSimpleDocumentLineTotal } from '../../../utils/documentLineAmounts';
import {
  documentCurrencyTitleVars,
  resolveDocumentCurrencyInputPrefix,
} from '../../../utils/documentCurrencyDisplay';
import { UniWarehouseSelect } from '../../../../../components/uni-warehouse-select';
import {
  UniWhDropdown,
  UniWhLocationOrWholeAuto,
  lineLocationSelectionRequired,
} from '../../../../../components/uni-wh-dropdown';
import { getPopupContainerInModal } from '../../../../../utils/modalEventIsolation';
import { DOCUMENT_DETAIL_CONTROL_SIZE } from '../../../components/document-detail-table/documentDetailTable';
import {
  ListPageTemplate,
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  MODAL_CONFIG,
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageHeaderActions,
  DocumentFormPageLayout,
  useDetailDrawerDescriptionItems,
} from '../../../../../components/layout-templates';
import { useLeaveFormTab } from '../../../../../components/uni-tabs/navigateClosingTab';
import { useSubmitShortcut } from '../../../../../hooks/useSubmitShortcut';
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import {
  UniPullQueryModal,
  isPullableScope,
  renderPullCapabilityTag,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import { UniTableDetail } from '../../../../../components/uni-table-detail';
import { shipmentNoticeApi, type ShipmentNotice, type ShipmentNoticeItem, type ShipmentNoticeNotifyPreviewResponse, type ShipmentNoticeNotifyPreviewPayload, type ShipmentNoticeListParams } from '../../../services/shipment-notice';
import {
  listSalesOrders,
  getSalesOrder,
  listSalesOrderShipmentNoticePullLines,
  pullShipmentNoticesFromSalesOrderItems,
  type SalesOrderShipmentPullLine,
} from '../../../services/sales-order';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import {
  shipmentNoticeBatchWithdrawAllowed,
  shipmentNoticeCapabilityReasonMessage,
} from '../../../../../hooks/useDocumentCapabilities';
import { LinkedOqcPanel } from '../../quality-management/components/LinkedInspectionPanel';
import { getShipmentNoticeLifecycle, buildShipmentNoticeLifecycleValueEnum, resolveShipmentNoticeListApiParams } from '../../../utils/shipmentNoticeLifecycle';
import { UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import { LIST_LIFECYCLE_STAGE_FIELD } from '../../../../../utils/listLifecycleStage';
import { ListUniLifecycleCell } from '../shared/ListUniLifecycleCell';
import { DocumentPushProgressBar, DOCUMENT_PROGRESS_COLUMN_DEFAULTS, DETAIL_TABLE_PROGRESS_COLUMN_DEFAULTS } from '../shared/DocumentPushProgressBar';
import {
  collectShipmentOutboundPushDocuments,
  shipmentNoticeOutboundPushPercent,
} from '../shared/pushProgress';
import { alignProColumns, alignDescriptionColumns, SALES_DOC_LIST_FIELD_RANK } from '../shared/documentFieldAlignment';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../shared/documentLineMaterialsPreview';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import { flattenDocumentDetailRows, resolveDetailTableViewMode } from '../../shared/detailTableFlatRows';
import { DocumentTrackingTimelineBody, useDocumentTracking } from '../../../../../components/document-tracking-panel';
import { WarehouseTraceBriefPrimaryActions } from '../../warehouse-management/WarehouseTraceBriefFooter';
import {
  KUAIZHIZAO_DOC_HOST,
  loadCustomerFormReferenceList,
  loadMaterialFormReferenceList,
} from '../../../../../utils/documentFormReferenceLoad';
import {
  collectImportMaterialCodes,
  findMaterialByImportCode,
  normalizeImportMaterialCode,
  resolveMaterialsByCodesForImport,
} from '../../../../master-data/utils/materialImportResolve';
import { generateCode, testGenerateCode, getCodeRulePageConfig } from '../../../../../services/codeRule';
import { isAutoGenerateEnabled, getPageRuleCode } from '../../../../../utils/codeRulePage';
import { useTranslation } from 'react-i18next';
import { useNumericPrecision } from '../../../../../hooks/useNumericPrecision';
import { buildFactoryImportTemplate } from '../../../../../utils/spreadsheetImportTemplate';
import { useImportMaterialUnitOptions } from '../../../../master-data/hooks/useImportMaterialUnitOptions';
import { pickImportExampleValue } from '../../../../../utils/loadImportDictionaryValues';
import { buildFutureDateShortcutFieldProps } from '../../../../../utils/futureDatePickerShortcuts';
import { buildKuaizhizaoPullCreateMenuItems, resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import {
  appendDocumentAttachmentsToSupplementary,
  documentAttachmentsFromRecord,
  hasDocumentAttachments,
} from '../../../components/DocumentAttachmentsReadonly';
import { mapAttachmentsToUploadList, normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { useKuaizhizaoPrintModal } from '../../../hooks/useKuaizhizaoPrintModal';
import { formatBusinessDateOnly, formatDateTime, formatQuantity, formatPrice, formatAmount, todaySiteDateString } from '../../../../../utils/format';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { QuantityWithUnitDisplay } from '../../../../../components/quantity-with-unit';
import { extractProTableSort } from '../../../../../utils/tableQueryKey';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { fetchAllListItems } from '../../../../../utils/fetchAllListPages';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import {
  referenceDisplayToIdOptions,
  searchReferenceDisplay,
} from '../../../../../utils/referenceDisplay';

const SHIPMENT_NOTICE_RESOURCE = 'kuaizhizao:shipment-notice';
const SHIPMENT_NOTICE_LIST_PATH = '/apps/kuaizhizao/sales-management/shipment-notices';
const SHIPMENT_NOTICE_CREATE_PATH = `${SHIPMENT_NOTICE_LIST_PATH}/new`;
const shipmentNoticeEditPath = (id: number) => `${SHIPMENT_NOTICE_LIST_PATH}/${id}/edit`;
const SHIPMENT_NOTICE_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_shipment_notices';

type NotifyLineWhState = {
  warehouse_id?: number;
  warehouse_name?: string;
  location_id?: number;
  location_code?: string;
};

function NotifyPreviewLocationCell({
  materialId,
  warehouseId,
  locationId,
  disabled,
  onChange,
  t,
}: {
  materialId?: number;
  warehouseId?: number;
  locationId?: number;
  disabled?: boolean;
  onChange: (next: { location_id?: number; location_code?: string }) => void;
  t: (key: string, opts?: Record<string, unknown>) => string;
}) {
  return (
    <UniWhLocationOrWholeAuto
      warehouseId={warehouseId}
      materialId={materialId && materialId > 0 ? materialId : undefined}
      value={locationId}
      showStock={!!(materialId && materialId > 0 && warehouseId && warehouseId > 0)}
      sortByStock={!!(materialId && materialId > 0 && warehouseId && warehouseId > 0)}
      allowClear={false}
      size={DOCUMENT_DETAIL_CONTROL_SIZE}
      getPopupContainer={getPopupContainerInModal}
      disabled={disabled}
      selectWarehouseFirstPlaceholder={t('app.kuaizhizao.warehouseOutbound.msg.selectWarehouse')}
      selectLocationPlaceholder={t('app.kuaizhizao.warehouseOutbound.msg.selectLocation')}
      onChange={(val, loc) => {
        const nextId = Number(val);
        onChange({
          location_id: Number.isFinite(nextId) && nextId > 0 ? nextId : undefined,
          location_code: loc?.code ?? '',
        });
      }}
    />
  );
}

interface ShipmentNoticeDetail extends ShipmentNotice {
  items?: { id?: number; material_id?: number; material_code: string; material_name: string; material_unit: string; notice_quantity: number; unit_price?: number; total_amount?: number }[];
}

type ShipmentNoticeItemRow = ShipmentNoticeItem & {
  _rowKey: string;
  notice_id: number;
  notice_code?: string;
  customer_name?: string;
  sales_order_code?: string;
  warehouse_name?: string;
  planned_ship_date?: string;
  notified_at?: string;
  status?: string;
  sales_delivery_id?: number;
  lifecycle?: Record<string, unknown>;
};

const SHIPMENT_NOTICE_LIST_PERSISTENCE_ID =
  'apps.kuaizhizao.pages.sales-management.shipment-notices-width-v2';

type PullSalesOrderCandidate = SalesOrderShipmentPullLine;

const ShipmentNoticesPage: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { quantity: quantityDecimals, price: priceDecimals } = useNumericPrecision();
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const pullFromSalesOrderAction = resolveKuaizhizaoDocumentAction(t, 'shipment_notice.pull_from_sales_order');

  const materialUnitImport = useImportMaterialUnitOptions();
  const materialUnitImportOptions = materialUnitImport.options;

  const noticeItemImportTemplate = useMemo(
    () =>
      buildFactoryImportTemplate(
        t,
        [
          { field: 'material', labelKey: 'app.kuaizhizao.shipmentNotice.import.materialCode', aliases: ['产品编号'] },
          { field: 'quantity', labelKey: 'common.quantity', aliases: ['数量'] },
          { field: 'unitPrice', labelKey: 'app.kuaizhizao.shipmentNotice.import.unitPrice', aliases: ['单价'] },
          { field: 'name', labelKey: 'app.kuaizhizao.shipmentNotice.import.materialName', aliases: ['产品名称'] },
          { field: 'specification', labelKey: 'app.kuaizhizao.shipmentNotice.import.specification', aliases: ['规格'] },
          { field: 'unit', labelKey: 'common.unit', aliases: ['单位'], options: materialUnitImportOptions },
        ],
        [
          t('app.kuaizhizao.shipmentNotice.importExample.materialCode'),
          t('app.kuaizhizao.shipmentNotice.importExample.quantity'),
          t('app.kuaizhizao.shipmentNotice.importExample.unitPrice'),
          t('app.kuaizhizao.shipmentNotice.importExample.materialName'),
          t('app.kuaizhizao.shipmentNotice.importExample.specification'),
          pickImportExampleValue(materialUnitImportOptions, t('app.kuaizhizao.shipmentNotice.importExample.unit')),
        ],
      ),
    [t, i18n.language, materialUnitImportOptions],
  );
  const navigate = useNavigate();
  const location = useLocation();
  const isCreatePage = location.pathname.endsWith('/shipment-notices/new');
  const editRouteMatch = location.pathname.match(/\/shipment-notices\/(\d+)\/edit$/);
  const editRouteId = editRouteMatch ? Number(editRouteMatch[1]) : null;
  const isEditPage = editRouteId != null && Number.isFinite(editRouteId) && editRouteId > 0;
  const isFormPage = isCreatePage || isEditPage;
  const leaveShipmentNoticeFormPage = useLeaveFormTab(SHIPMENT_NOTICE_LIST_PATH);
  const formPageInitKeyRef = useRef<string | null>(null);
  const [formPageLoading, setFormPageLoading] = useState(false);
  const pendingCreateFormValuesRef = useRef<Record<string, unknown> | null>(null);
  const pendingListImportRowsRef = useRef<unknown[][] | null>(null);
  const salesOrderEntityName = t('app.kuaizhizao.salesOrder.entityName');
  const shipmentNoticeEntityName = t('app.kuaizhizao.shipmentNotice.entityName');
  const statusMap = useMemo(
    () => ({
      待发货: { text: t('app.kuaizhizao.shipmentNotice.statusPending'), color: 'default' },
      已通知: { text: t('app.kuaizhizao.shipmentNotice.statusNotified'), color: 'processing' },
      已出库: { text: t('app.kuaizhizao.shipmentNotice.statusShipped'), color: 'success' },
    }),
    [t, i18n.language],
  );
  const shipmentNoticeAuditEnabled = useAuditRequired('shipment_notice', false);
  const shipmentNoticeAuditColumn = useMemo(
    () => createListAuditPhaseColumn<ShipmentNotice>({ t, auditEnabled: shipmentNoticeAuditEnabled }),
    [t, shipmentNoticeAuditEnabled],
  );
  const defaultUnit = t('app.kuaizhizao.shipmentNotice.defaultUnit');
  const defaultNoticeItem = useMemo(
    () => ({
      material_id: undefined,
      material_code: '',
      material_name: '',
      material_spec: '',
      material_model: '',
      partner_material_code: '',
      partner_material_name: '',
      material_unit: defaultUnit,
      notice_quantity: 1,
      unit_price: 0,
    }),
    [defaultUnit],
  );
  const actionRef = useRef<ActionType>(null);
  const [viewTypeState, setViewTypeState] = useState<'table' | 'detailTable' | 'help'>(() =>
    readPersistedUniTableViewType(SHIPMENT_NOTICE_LIST_PERSISTENCE_ID, 'table', [
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
  const { message: messageApi, modal: modalApi } = App.useApp();
  const { token } = AntdTheme.useToken();
  const noticeDetailDrawerZIndex = token.zIndexPopupBase;
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [noticeDetail, setNoticeDetail] = useState<ShipmentNoticeDetail | null>(null);
  const shipmentNoticePerms = useResourcePermissions(SHIPMENT_NOTICE_RESOURCE);
  const [trackingRefreshKey, setTrackingRefreshKey] = useState(0);

  const shipmentTracking = useDocumentTracking(
    detailDrawerVisible && noticeDetail?.id ? 'shipment_notice' : undefined,
    noticeDetail?.id,
    trackingRefreshKey,
  );

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingBusinessStatus, setEditingBusinessStatus] = useState('待发货');
  const [editingReviewStatus, setEditingReviewStatus] = useState('草稿');
  const createFormRef = useRef<any>(null);
  const editFormRef = useRef<any>(null);
  const createCommitAfterSaveRef = useRef(false);
  const editCommitAfterSaveRef = useRef(false);
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false);
  const [productScope, setProductScope] = useState<'make' | 'all'>('make');
  const [customerList, setCustomerList] = useState<any[]>([]);
  const shipmentNoticeLifecycleValueEnum = useMemo(
    () => buildShipmentNoticeLifecycleValueEnum(t),
    [t],
  );
  const materialSourceType = productScope === 'make' ? 'Make' : undefined;
  const productColumnTitle = (
    <Space size={8} align="center">
      <span>{t('app.kuaizhizao.salesOrder.material')}</span>
      <ThemedSegmented
        size="small"
        value={productScope}
        options={[
          { label: t('app.kuaizhizao.sales.common.productScopeMake'), value: 'make' },
          { label: t('app.kuaizhizao.sales.common.productScopeAll'), value: 'all' },
        ]}
        onChange={(val) => setProductScope((val as 'make' | 'all') ?? 'make')}
      />
    </Space>
  );

  const [salesOrderList, setSalesOrderList] = useState<any[]>([]);
  const [previewCode, setPreviewCode] = useState<string | null>(null);
  const [effectiveRuleCode, setEffectiveRuleCode] = useState<string | null>(null);
  const [importVisible, setImportVisible] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const tableRowsRef = useRef<ShipmentNotice[]>([]);

  const pullSourceOrderIdRef = useRef<number | undefined>(undefined);
  const [pullSourceOrderId, setPullSourceOrderId] = useState<number | undefined>();
  const [pullSourceOrderOptions, setPullSourceOrderOptions] = useState<Array<{ value: number; label: string }>>([]);

  const [notifyPreviewOpen, setNotifyPreviewOpen] = useState(false);
  const [notifyPreviewLoading, setNotifyPreviewLoading] = useState(false);
  const [notifyPreviewConfirming, setNotifyPreviewConfirming] = useState(false);
  const [notifyPreviewData, setNotifyPreviewData] = useState<ShipmentNoticeNotifyPreviewResponse | null>(null);
  const [notifyPreviewTarget, setNotifyPreviewTarget] = useState<ShipmentNotice | null>(null);
  const [notifyLineWh, setNotifyLineWh] = useState<Record<number, NotifyLineWhState>>({});
  const [notifyBatchWarehouseId, setNotifyBatchWarehouseId] = useState<number | undefined>();
  const notifyLineWhRef = useRef<Record<number, NotifyLineWhState>>({});

  const selectedNoticesForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
        .filter((row): row is ShipmentNotice => row != null),
    [selectedRowKeys],
  );

  const shipmentNoticeToolbarAuditMenus = useMemo(() => {
    const rows = selectedNoticesForBatch;
    const reload = () => {
      setSelectedRowKeys([]);
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    };
    const reviewOf = (row: ShipmentNotice) => String(row.review_status || '').trim();
    const allowed = (row: ShipmentNotice, key: string) => pickCapability(row, key)?.allowed === true;
    const run = (
      keys: React.Key[],
      records: ShipmentNotice[],
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
    const submitRows = rows.filter((row) => allowed(row, 'submit'));
    const committedRows = rows.filter(
      (row) => reviewOf(row) === 'SUBMITTED' && allowed(row, 'withdraw_submit'),
    );
    const pendingRows = rows.filter((row) => {
      const review = reviewOf(row);
      return review !== 'SUBMITTED' && isPendingReviewStatus(review) && allowed(row, 'withdraw_submit');
    });
    const reviewRows = rows.filter((row) => allowed(row, 'submit_review'));
    const approveRows = rows.filter(
      (row) => reviewOf(row) !== 'SUBMITTED' && isPendingReviewStatus(reviewOf(row)) && allowed(row, 'approve'),
    );
    const revokeRows = rows.filter((row) => allowed(row, 'revoke_approval'));
    const canSubmit = shipmentNoticePerms.canAction?.('submit') ?? false;
    const canApprove = shipmentNoticePerms.canAction?.('approve') ?? false;
    const canRevoke = shipmentNoticePerms.canAction?.('revoke') ?? false;
    const hasSelection = rows.length > 0;
    const submitDisabled = hasSelection && !(canSubmit && submitRows.length > 0);
    const submitItems: UniBatchMenuItem[] = withDocumentSubmitCombinedItem(
      [
        {
          key: 'submit',
          label: t('common.submit'),
          disabled: submitDisabled,
          onClick: (keys) => run(keys, submitRows, 'submit', canSubmit, (id) => shipmentNoticeApi.commit(id)),
        },
        {
          key: 'withdraw-submit',
          label: t('app.kuaizhizao.shipmentNotice.toolbar.withdrawSubmit'),
          disabled: hasSelection && committedRows.length === 0,
          onClick: (keys) =>
            run(keys, committedRows, 'withdraw_submit', canSubmit, (id) => shipmentNoticeApi.withdrawSubmit(id)),
        },
        {
          key: 'submit-review',
          label: t('app.kuaizhizao.shipmentNotice.toolbar.submitReview'),
          disabled: hasSelection && !(canSubmit && reviewRows.length > 0),
          onClick: (keys) =>
            run(
              keys,
              reviewRows,
              'submit_review',
              canSubmit,
              (id) => shipmentNoticeApi.submitForReview(id),
              t('app.kuaizhizao.shipmentNotice.toolbar.submitReviewNotAllowed'),
            ),
        },
      ],
      {
        t,
        message: messageApi,
        disabled: submitDisabled,
        commitRecords: submitRows,
        permAllowed: canSubmit,
        commit: (id) => shipmentNoticeApi.commit(id),
        submitReview: (id) => shipmentNoticeApi.submitForReview(id),
        onSuccess: reload,
      },
    );
    const auditItems: UniBatchMenuItem[] = [
      {
        key: 'approve',
        label: t('common.audit'),
        disabled: hasSelection && !(canApprove && approveRows.length > 0),
        onClick: (keys) => run(keys, approveRows, 'approve', canApprove, (id) => shipmentNoticeApi.approve(id)),
      },
      {
        key: 'withdraw-review',
        label: t('app.kuaizhizao.shipmentNotice.toolbar.withdrawReview'),
        disabled: hasSelection && pendingRows.length === 0,
        onClick: (keys) =>
          run(keys, pendingRows, 'withdraw_submit', canApprove, (id) => shipmentNoticeApi.withdrawSubmit(id)),
      },
      {
        key: 'revoke',
        label: t('app.kuaizhizao.shipmentNotice.toolbar.revoke'),
        disabled: hasSelection && !(canRevoke && revokeRows.length > 0),
        onClick: (keys) =>
          run(keys, revokeRows, 'revoke_approval', canRevoke, (id) => shipmentNoticeApi.revokeApproval(id)),
      },
    ];
    return { submitItems, auditItems };
  }, [invalidateMenuBadgeCounts, messageApi, selectedNoticesForBatch, shipmentNoticePerms, t]);

  const {
    customFields: shipmentNoticeFormCustomFields,
    customFieldValues: shipmentNoticeFormCustomFieldValues,
    loadFieldValues: loadShipmentNoticeFormFieldValues,
    extractFormValues: extractShipmentNoticeFormValues,
    saveCustomFieldValues: saveShipmentNoticeCustomFieldValues,
    resetFieldValues: resetShipmentNoticeFormFieldValues,
  } = useCustomFields({
    tableName: SHIPMENT_NOTICE_CUSTOM_FIELD_TABLE,
    loadWhenOpen: true,
    open: isFormPage,
  });

  const {
    customFields: shipmentNoticeListCustomFields,
    generateCustomFieldColumns: generateShipmentNoticeCustomFieldColumns,
    enrichRecordsWithCustomFields: enrichShipmentNoticeRecordsWithCustomFields,
    customFieldValues: shipmentNoticeDetailCustomFieldValues,
    loadFieldValuesForDetail: loadShipmentNoticeFieldValuesForDetail,
    resetDetailFieldValues: resetShipmentNoticeDetailFieldValues,
  } = useCustomFieldsForList<ShipmentNotice>({ tableName: SHIPMENT_NOTICE_CUSTOM_FIELD_TABLE });

  const shipmentNoticeCustomFieldColumns = generateShipmentNoticeCustomFieldColumns();

  useEffect(() => {
    if (!isFormPage) return;
    let cancelled = false;
    const load = async () => {
      try {
        const [cust, ordersRes] = await Promise.all([
          loadCustomerFormReferenceList(KUAIZHIZAO_DOC_HOST.shipmentNotice),
          listSalesOrders({ limit: 200, view: 'options' }).catch(() => ({
            data: [],
            total: 0,
            success: false,
          })),
        ]);
        if (cancelled) return;
        setCustomerList(Array.isArray(cust) ? cust : []);
        setSalesOrderList(ordersRes?.data || []);
      } catch (e) {
        if (!cancelled) {
          console.error(t('app.kuaizhizao.shipmentNotice.loadCustomersFailed'), e);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [isFormPage, t]);

  const appendShipmentNoticeItemsFromMaterials = useCallback(
    (selected: Material[]) => {
      const current = createFormRef.current?.getFieldValue('items') ?? [];
      const newRows = selected.map((m) => ({
        material_id: m.id,
        material_code: m.mainCode ?? m.code ?? '',
        material_name: m.name ?? '',
        material_spec: m.specification ?? '',
        material_unit: m.baseUnit ?? defaultUnit,
        notice_quantity: 1,
        unit_price: (m as any).defaults?.defaultSalePrice ?? (m as any).defaults?.default_sale_price ?? 0,
      }));
      // 如果当前只有一行且未选择产品，则替换该行
      if (current.length === 1 && !current[0].material_id && !current[0].material_code) {
        createFormRef.current?.setFieldsValue({ items: newRows });
      } else {
        createFormRef.current?.setFieldsValue({ items: [...current, ...newRows] });
      }
      messageApi.success(t('app.kuaizhizao.common.materialBatchAdded', { count: selected.length }));
    },
    [defaultUnit, messageApi, t]
  );

  /**
   * 发货通知单明细汇总组件
   */
  const ShipmentNoticeFormSummary: React.FC = () => (
    <DocumentAmountSummaryWatch variant="basic" quantityField="notice_quantity" />
  );

  const columns: ProColumns<ShipmentNotice>[] = useMemo(
    () => alignProColumns<ShipmentNotice>([
    {
      title: t('app.kuaizhizao.shipmentNotice.colCustomerNotice'),
      key: 'notice_code',
      dataIndex: 'notice_code',
      width: 240,
      minWidth: 240,
      uniTableKeepWidth: true,
      uniTablePrimaryFlex: false,
      resizable: false,
      fixed: 'left',
      sorter: true,
      fieldProps: { placeholder: t('app.kuaizhizao.shipmentNotice.colNoticeCode') },
      render: (_, record) => (
        <UniTableStackedPrimaryCell
          primary={String(record.customer_name ?? '')}
          secondary={String(record.notice_code ?? '')}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.quotation.form.customer'),
      dataIndex: 'customer_id',
      hideInTable: true,
      valueType: 'select',
      fieldProps: {
        showSearch: true,
        filterOption: false,
        placeholder: t('app.kuaizhizao.quotation.form.customer'),
      },
      debounceTime: 300,
      request: async ({ keyWords }) => {
        const res = await searchReferenceDisplay({
          resource: 'master-data:supply-chain:customer',
          hostResource: 'kuaizhizao:shipment-notice',
          keyword: typeof keyWords === 'string' ? keyWords.trim() : undefined,
          pageSize: 20,
        });
        return referenceDisplayToIdOptions(res.items);
      },
    },
      {
        title: t('app.kuaizhizao.common.colLineMaterials'),
        ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
        // 发货通知专用段位：主标识后、出库仓库前（勿改全局 line_materials）
        key: 'shipment_line_materials',
        dataIndex: 'shipment_line_materials',
        render: (_, record) => renderDocumentLineMaterialsPreview(record.items, t),
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.outboundWarehouse'),
        key: 'outbound_warehouse',
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
        title: t('app.kuaizhizao.shipmentNotice.salesOrderCode'),
        key: 'shipment_sales_order_code',
        dataIndex: 'sales_order_code',
        width: 180,
        minWidth: 180,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: false,
        sorter: true,
        fieldProps: { placeholder: t('app.kuaizhizao.shipmentNotice.salesOrderCode') },
        render: (_, record) => (
          <LinkedDocumentCode
            documentType="sales_order"
            documentId={record.sales_order_id}
            code={record.sales_order_code}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.deliveryConversion'),
      key: 'shipment_outbound_conversion',
      dataIndex: 'sales_delivery_code',
      width: 180,
      minWidth: 180,
      uniTableKeepWidth: true,
      resizable: false,
      hideInSearch: true,
      render: (_, record) => {
        if (record.sales_delivery_id) {
          return (
            <UniTableStackedPrimaryCell
                record={record as Record<string, unknown>}
                secondaryKeys={['sales_delivery_code']}
                primary={t('app.kuaizhizao.shipmentNotice.pulledToOutbound')}
                secondary={String(record.sales_delivery_code || `#${record.sales_delivery_id}`)}
              />
          );
        }
        return (
          <UniTableStackedPrimaryCell
            primary={t('app.kuaizhizao.shipmentNotice.notPulledOutbound')}
            secondary="-"
            secondaryCopyable={false}
          />
        );
      },
    },
    {
      title: t('app.kuaizhizao.shipmentNotice.plannedShipDate'),
      dataIndex: 'planned_ship_date',
      width: 132,
      minWidth: 132,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
      render: (_, record) =>
        record.planned_ship_date ? formatDateTime(record.planned_ship_date, 'YYYY-MM-DD') : '-',
    },
    {
      title: t('app.kuaizhizao.shipmentNotice.plannedShipDate'),
      dataIndex: 'planned_ship_date_range',
      valueType: 'dateRange',
      hideInTable: true,
      fieldProps: {
        placeholder: [t('app.kuaizhizao.quotation.dateRangeStart'), t('app.kuaizhizao.quotation.dateRangeEnd')],
      },
      formItemProps: formDateRangeFormItemProps,
    },
    {
      title: t('app.kuaizhizao.shipmentNotice.notifiedAt'),
      dataIndex: 'notified_at',
      width: 132,
      minWidth: 132,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
      render: (_, record) =>
        record.notified_at ? formatDateTime(record.notified_at, 'YYYY-MM-DD HH:mm') : '-',
    },
    {
      title: t('app.kuaizhizao.salesManagement.pushProgress.title'),
      dataIndex: 'outbound_push_progress',
      ...DOCUMENT_PROGRESS_COLUMN_DEFAULTS,
      render: (_, record) => {
        const percent = shipmentNoticeOutboundPushPercent(record);
        return (
          <DocumentPushProgressBar
            percent={percent}
            tooltip={t('app.kuaizhizao.salesManagement.pushProgress.outboundTooltip', {
              percent,
              status: percent >= 100
                ? t('app.kuaizhizao.salesManagement.pushProgress.pushed')
                : t('app.kuaizhizao.salesManagement.pushProgress.notPushed'),
            })}
            documents={collectShipmentOutboundPushDocuments(
              record,
              t('components.documentTrackingPanel.docType.sales_delivery'),
            )}
            formatMoreDocs={(count) =>
              t('app.kuaizhizao.salesManagement.pushProgress.moreDocs', { count })
            }
          />
        );
      },
    },
    ...buildDocumentAuditColumns<ShipmentNotice>(t),
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
    shipmentNoticeAuditColumn,
    {
      title: t('app.kuaizhizao.salesOrder.lifecycle'),
      dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
      key: 'lifecycle',
      fixed: 'right',
      valueType: 'select',
      valueEnum: shipmentNoticeLifecycleValueEnum,
      render: (_, record) => (
        <ListUniLifecycleCell lifecycle={getShipmentNoticeLifecycle(record as any, t)} />
      ),
    },
    ...shipmentNoticeCustomFieldColumns,
    {
      title: t('common.actions'),
      fixed: 'right',
      hideInSearch: true,
      render: (_, record) => [
        <Button {...rowActionKind('read')} key="detail" onClick={() => handleDetail(record)}>{t('common.detail')}</Button>,
        record.capabilities?.update?.allowed && shipmentNoticePerms.canUpdate ? (
          <Button {...rowActionKind('update')} key="edit" onClick={() => handleEdit(record)}>{t('common.edit')}</Button>
        ) : null,
        record.capabilities?.notify?.allowed && shipmentNoticePerms.canUpdate ? (
          <Button {...rowActionKind('dispatch')} key="notify" icon={<SendOutlined />} onClick={() => handleNotify(record as ShipmentNotice)}>
            {t('app.kuaizhizao.shipmentNotice.notifyWarehouse')}
          </Button>
        ) : null,
        record.capabilities?.withdraw?.allowed && shipmentNoticePerms.canAction?.('revoke') ? (
          <ActionConfirmPopconfirm title={t('app.kuaizhizao.shipmentNotice.withdrawNotify')} description={t('app.kuaizhizao.shipmentNotice.withdrawConfirmContent', { code: record.notice_code })} onConfirm={() => executeWithdraw(record as ShipmentNotice)}>
              <Button {...rowActionKind('revoke')} key="withdraw" onClick={(e) => e.stopPropagation()}>{t('app.kuaizhizao.shipmentNotice.withdrawNotify')}</Button>
            </ActionConfirmPopconfirm>
        ) : null,
      ].filter(Boolean),
    },
  ], SALES_DOC_LIST_FIELD_RANK),
    [
      t,
      shipmentNoticeAuditColumn,
      shipmentNoticeCustomFieldColumns,
      shipmentNoticeLifecycleValueEnum,
      shipmentNoticePerms.canDelete,
      shipmentNoticePerms.canUpdate,
      shipmentNoticePerms,
    ],
  );

  const detailTableColumns: ProColumns<ShipmentNoticeItemRow>[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.shipmentNotice.colCustomerNotice'),
        key: 'notice_code',
        dataIndex: 'notice_code',
        width: 240,
        minWidth: 240,
        uniTableKeepWidth: true,
        uniTablePrimaryFlex: false,
        resizable: false,
        fixed: 'left',
        hideInSearch: false,
        fieldProps: { placeholder: t('app.kuaizhizao.shipmentNotice.colNoticeCode') },
        render: (_, record) => (
          <UniTableStackedPrimaryCell
            primary={String(record.customer_name ?? '')}
            secondary={String(record.notice_code ?? '')}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.colNoticeCode'),
        dataIndex: 'notice_code',
        hideInTable: true,
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.import.materialName'),
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
        title: t('app.kuaizhizao.shipmentNotice.import.materialCode'),
        dataIndex: 'material_code',
        hideInTable: true,
      },
      ...buildMaterialModelSpecColumns(t, { readOnly: true, specWidth: 100, modelWidth: 100 }),
      ...buildPartnerMaterialLineColumns(t, 'customer', { readOnly: true, width: 110 }),
      {
        title: t('common.quantity'),
        dataIndex: 'notice_quantity',
        width: 120,
        minWidth: 120,
        uniTableKeepWidth: true,
        resizable: false,
        align: 'right',
        render: (val: unknown, record) => (
          <QuantityWithUnitDisplay quantity={val} unit={record.material_unit} />
        ),
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.import.unitPrice'),
        dataIndex: 'unit_price',
        width: 100,
        minWidth: 100,
        uniTableKeepWidth: true,
        resizable: false,
        align: 'right',
        render: (text: unknown, record: any) =>
          `${resolveDocumentCurrencyInputPrefix(record?.currency_code)}${formatPrice(text)}`,
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.amount'),
        dataIndex: 'total_amount',
        width: 110,
        minWidth: 110,
        uniTableKeepWidth: true,
        resizable: false,
        align: 'right',
        render: (text: unknown, record: any) =>
          `${resolveDocumentCurrencyInputPrefix(record?.currency_code)}${formatAmount(text)}`,
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.plannedShipDate'),
        dataIndex: 'planned_ship_date',
        width: 132,
        minWidth: 132,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        render: (_: unknown, row) =>
          row.planned_ship_date ? formatDateTime(row.planned_ship_date, 'YYYY-MM-DD') : '-',
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.notifiedAt'),
        dataIndex: 'notified_at',
        width: 132,
        minWidth: 132,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        render: (_: unknown, row) =>
          row.notified_at ? formatDateTime(row.notified_at, 'YYYY-MM-DD HH:mm') : '-',
      },
      {
        title: t('app.kuaizhizao.salesManagement.pushProgress.title'),
        key: 'line_outbound_progress',
        ...DETAIL_TABLE_PROGRESS_COLUMN_DEFAULTS,
        render: (_: unknown, record) => {
          const percent = shipmentNoticeOutboundPushPercent(record);
          return (
            <DocumentPushProgressBar
              percent={percent}
              tooltip={t('app.kuaizhizao.salesManagement.pushProgress.outboundTooltip', {
                percent,
                status: percent >= 100
                  ? t('app.kuaizhizao.salesManagement.pushProgress.pushed')
                  : t('app.kuaizhizao.salesManagement.pushProgress.notPushed'),
              })}
              documents={collectShipmentOutboundPushDocuments(
                record,
                t('components.documentTrackingPanel.docType.sales_delivery'),
              )}
              formatMoreDocs={(count) =>
                t('app.kuaizhizao.salesManagement.pushProgress.moreDocs', { count })
              }
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.salesOrder.lifecycle'),
        dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
        key: 'lifecycle',
        fixed: 'right',
        hideInSearch: false,
        valueEnum: shipmentNoticeLifecycleValueEnum,
        render: (_, record) => (
          <ListUniLifecycleCell
            lifecycle={getShipmentNoticeLifecycle(record as Record<string, unknown>, t)}
          />
        ),
      },
    ],
    [shipmentNoticeLifecycleValueEnum, t],
  );

  const handleDetail = async (record: ShipmentNotice) => {
    try {
      const detail = await shipmentNoticeApi.get(record.id!.toString());
      setNoticeDetail(detail as ShipmentNoticeDetail);
      setDetailDrawerVisible(true);
      setTrackingRefreshKey((k) => k + 1);
      if (record.id != null) {
        await loadShipmentNoticeFieldValuesForDetail(record.id);
      }
    } catch {
      messageApi.error(t('app.kuaizhizao.shipmentNotice.detailFailed'));
    }
  };

  useDocumentHighlightDeepLink(
    useCallback((id: number) => handleDetail({ id }), [messageApi, t]),
  );

  const loadShipmentNoticeEditForm = useCallback(
    async (id: number) => {
      setFormPageLoading(true);
      try {
        const detail = (await shipmentNoticeApi.get(String(id))) as ShipmentNoticeDetail;
        const itemsForm = (detail.items || []).map((it: ShipmentNoticeItem) => ({
          material_id: it.material_id,
          material_code: it.material_code || '',
          material_name: it.material_name || '',
          material_spec: it.material_spec || '',
          material_unit: it.material_unit || '',
          notice_quantity: Number(it.notice_quantity) || 0,
          unit_price: Number(it.unit_price) || 0,
        }));
        setEditingId(id);
        setEditingBusinessStatus(String(detail.status || '待发货'));
        setEditingReviewStatus(String(detail.review_status || '草稿'));
        editFormRef.current?.resetFields();
        editFormRef.current?.setFieldsValue({
          sales_order_id: detail.sales_order_id,
          sales_order_code: detail.sales_order_code,
          customer_id: detail.customer_id,
          customer_name: detail.customer_name,
          customer_contact: detail.customer_contact,
          customer_phone: detail.customer_phone,
          warehouse_id: detail.warehouse_id,
          warehouse_name: detail.warehouse_name,
          planned_ship_date: detail.planned_ship_date ? dayjs(detail.planned_ship_date) : undefined,
          shipping_address: detail.shipping_address,
          currency_code: String((detail as { currency_code?: string }).currency_code || 'CNY').trim().toUpperCase() || 'CNY',
          exchange_rate: Number((detail as { exchange_rate?: number }).exchange_rate ?? 1) || 1,
          notes: detail.notes,
          attachments: mapAttachmentsToUploadList(detail.attachments),
          items: itemsForm.length ? itemsForm : [defaultNoticeItem],
        });
        const fieldFormValues = await loadShipmentNoticeFormFieldValues(id);
        editFormRef.current?.setFieldsValue(fieldFormValues);
      } catch {
        messageApi.error(t('app.kuaizhizao.shipmentNotice.loadDetailFailed'));
        leaveShipmentNoticeFormPage();
      } finally {
        setFormPageLoading(false);
      }
    },
    [defaultNoticeItem, leaveShipmentNoticeFormPage, loadShipmentNoticeFormFieldValues, messageApi, t],
  );

  const handleEdit = (record: ShipmentNotice) => {
    if (record.id) navigate(shipmentNoticeEditPath(record.id));
  };

  const handleCopySelectedShipmentNotice = useCallback(async () => {
    if (selectedNoticesForBatch.length !== 1 || !selectedNoticesForBatch[0]?.id) {
      messageApi.warning(t('app.kuaizhizao.shipmentNotice.selectToCopy'));
      return;
    }
    try {
      const detail = (await shipmentNoticeApi.get(String(selectedNoticesForBatch[0].id))) as ShipmentNoticeDetail;
      let noticeCode = '';
      let ruleCode = getPageRuleCode('kuaizhizao-shipment-notice');
      let autoGenerate = isAutoGenerateEnabled('kuaizhizao-shipment-notice');
      try {
        const pageConfig = await getCodeRulePageConfig('kuaizhizao-shipment-notice');
        if (pageConfig?.ruleCode) {
          ruleCode = pageConfig.ruleCode;
          autoGenerate = !!pageConfig.autoGenerate;
        }
      } catch {
        /* 编号规则读取失败时仍打开复制表单 */
      }
      if (autoGenerate && ruleCode) {
        setEffectiveRuleCode(ruleCode);
        const preview = await testGenerateCode({ rule_code: ruleCode });
        noticeCode = preview.code ?? '';
        setPreviewCode(noticeCode || null);
      }
      const items = Array.isArray(detail.items) ? detail.items : [];
      pendingCreateFormValuesRef.current = {
        notice_code: noticeCode,
        sales_order_id: detail.sales_order_id,
        sales_order_code: detail.sales_order_code,
        customer_id: detail.customer_id,
        customer_name: detail.customer_name,
        customer_contact: detail.customer_contact,
        customer_phone: detail.customer_phone,
        warehouse_id: detail.warehouse_id,
        warehouse_name: detail.warehouse_name,
        planned_ship_date: dayjs(),
        shipping_address: detail.shipping_address,
        currency_code: String((detail as { currency_code?: string }).currency_code || 'CNY').trim().toUpperCase() || 'CNY',
        exchange_rate: Number((detail as { exchange_rate?: number }).exchange_rate ?? 1) || 1,
        notes: detail.notes,
        items: items.length
          ? items.map((it) => ({
              material_id: it.material_id,
              material_code: it.material_code || '',
              material_name: it.material_name || '',
              material_spec: it.material_spec || '',
              material_unit: it.material_unit || defaultUnit,
              notice_quantity: Number(it.notice_quantity) || 0,
              unit_price: Number(it.unit_price) || 0,
              sales_order_item_id: it.sales_order_item_id,
            }))
          : [defaultNoticeItem],
      };
      formPageInitKeyRef.current = null;
      navigate(SHIPMENT_NOTICE_CREATE_PATH);
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.shipmentNotice.loadDetailFailed')));
    }
  }, [defaultNoticeItem, defaultUnit, messageApi, selectedNoticesForBatch, t]);

  const executeNotify = useCallback(async (
    record: ShipmentNotice,
    warehouse?: {
      warehouse_id?: number;
      warehouse_name?: string;
      line_warehouses?: Record<string, number>;
      line_warehouse_names?: Record<string, string>;
      line_location_ids?: Record<string, number>;
      line_location_codes?: Record<string, string>;
      push_mode?: 'draft' | 'confirm';
    },
  ) => {
    const res = (await shipmentNoticeApi.notify(record.id!.toString(), warehouse)) as ShipmentNotice;
    messageApi.success(
      res?.sales_delivery_code
        ? t('app.kuaizhizao.shipmentNotice.notifySuccessWithDelivery', { deliveryCode: res.sales_delivery_code })
        : t('app.kuaizhizao.shipmentNotice.notifySuccess'),
    );
    if (noticeDetail?.id === record.id) {
      const fresh = await shipmentNoticeApi.get(record.id!.toString());
      setNoticeDetail(fresh as ShipmentNoticeDetail);
    }
    invalidateMenuBadgeCounts();
    actionRef.current?.reload();
  }, [invalidateMenuBadgeCounts, messageApi, noticeDetail?.id, t]);

  const resetNotifyPreviewModal = useCallback(() => {
    setNotifyPreviewOpen(false);
    setNotifyPreviewData(null);
    setNotifyPreviewTarget(null);
    setNotifyLineWh({});
    notifyLineWhRef.current = {};
    setNotifyBatchWarehouseId(undefined);
  }, []);

  const buildNotifyPreviewPayload = useCallback(
    (lineMap: Record<number, NotifyLineWhState>, headerWarehouseId?: number): ShipmentNoticeNotifyPreviewPayload => {
      const line_warehouses: Record<string, number> = {};
      for (const [id, row] of Object.entries(lineMap)) {
        const wh = Number(row.warehouse_id);
        if (Number.isFinite(wh) && wh > 0) {
          line_warehouses[id] = wh;
        }
      }
      return {
        warehouse_id: headerWarehouseId && headerWarehouseId > 0 ? headerWarehouseId : undefined,
        line_warehouses: Object.keys(line_warehouses).length ? line_warehouses : undefined,
      };
    },
    [],
  );

  const seedNotifyLineWhFromPreview = useCallback(
    (res: ShipmentNoticeNotifyPreviewResponse, headerFallback?: { warehouse_id?: number; warehouse_name?: string }) => {
      const prev = notifyLineWhRef.current;
      const next = { ...prev };
      let changed = false;
      for (const row of res.items || []) {
        const id = Number(row.item_id);
        if (!(id > 0)) continue;
        if (next[id]?.warehouse_id) continue;
        const suggested =
          row.warehouse_id != null && Number(row.warehouse_id) > 0
            ? Number(row.warehouse_id)
            : headerFallback?.warehouse_id && headerFallback.warehouse_id > 0
              ? headerFallback.warehouse_id
              : undefined;
        if (!suggested) continue;
        next[id] = {
          ...next[id],
          warehouse_id: suggested,
          warehouse_name: row.warehouse_name || headerFallback?.warehouse_name || next[id]?.warehouse_name,
        };
        changed = true;
      }
      if (!changed) return;
      notifyLineWhRef.current = next;
      setNotifyLineWh(next);
    },
    [],
  );

  const loadNotifyPreview = useCallback(
    async (record: ShipmentNotice, payload?: ShipmentNoticeNotifyPreviewPayload) => {
      setNotifyPreviewLoading(true);
      try {
        const res = await shipmentNoticeApi.previewNotify(record.id!.toString(), payload);
        setNotifyPreviewData(res);
        seedNotifyLineWhFromPreview(res, {
          warehouse_id: record.warehouse_id ? Number(record.warehouse_id) : undefined,
          warehouse_name: record.warehouse_name || undefined,
        });
      } catch (error: any) {
        messageApi.error(error?.message || error?.detail || t('app.kuaizhizao.shipmentNotice.notifyPreviewFailed'));
        resetNotifyPreviewModal();
      } finally {
        setNotifyPreviewLoading(false);
      }
    },
    [messageApi, resetNotifyPreviewModal, seedNotifyLineWhFromPreview, t],
  );

  const handleNotify = useCallback(
    (record: ShipmentNotice) => {
      setNotifyPreviewOpen(true);
      setNotifyPreviewConfirming(false);
      setNotifyPreviewData(null);
      setNotifyPreviewTarget(record);
      setNotifyLineWh({});
      notifyLineWhRef.current = {};
      setNotifyBatchWarehouseId(undefined);
      const headerWh = record.warehouse_id ? Number(record.warehouse_id) : undefined;
      void loadNotifyPreview(
        record,
        buildNotifyPreviewPayload({}, headerWh),
      );
    },
    [buildNotifyPreviewPayload, loadNotifyPreview],
  );

  const patchNotifyLineWh = useCallback((itemId: number, patch: NotifyLineWhState) => {
    const next = {
      ...notifyLineWhRef.current,
      [itemId]: {
        ...notifyLineWhRef.current[itemId],
        ...patch,
      },
    };
    notifyLineWhRef.current = next;
    setNotifyLineWh(next);
  }, []);

  const applyNotifyBatchWarehouse = useCallback(
    (warehouseId: number, warehouseName?: string) => {
      setNotifyBatchWarehouseId(warehouseId);
      const items = notifyPreviewData?.items || [];
      if (!items.length) {
        messageApi.warning(t('app.kuaizhizao.warehouseOutbound.pull.batchWarehouseNoLines'));
        return;
      }
      const next = { ...notifyLineWhRef.current };
      for (const row of items) {
        const id = Number(row.item_id);
        if (!(id > 0)) continue;
        next[id] = {
          warehouse_id: warehouseId,
          warehouse_name: warehouseName || '',
          location_id: undefined,
          location_code: undefined,
        };
      }
      notifyLineWhRef.current = next;
      setNotifyLineWh(next);
      messageApi.success(
        t('app.kuaizhizao.warehouseOutbound.pull.batchWarehouseApplied', { count: items.length }),
      );
    },
    [messageApi, notifyPreviewData?.items, t],
  );

  const notifyLinesReady = useMemo(() => {
    const items = notifyPreviewData?.items || [];
    if (!items.length) return false;
    return items.every((row) => {
      const id = Number(row.item_id);
      const wh = notifyLineWh[id]?.warehouse_id;
      return Number.isFinite(Number(wh)) && Number(wh) > 0;
    });
  }, [notifyLineWh, notifyPreviewData?.items]);

  const handleNotifyPreviewConfirm = useCallback(async (pushMode: 'draft' | 'confirm') => {
    if (!notifyPreviewTarget?.id || !notifyPreviewData) return;
    if (notifyPreviewData.has_blocking_issues) return;
    const items = notifyPreviewData.items || [];
    const line_warehouses: Record<string, number> = {};
    const line_warehouse_names: Record<string, string> = {};
    const line_location_ids: Record<string, number> = {};
    const line_location_codes: Record<string, string> = {};

    for (const row of items) {
      const id = Number(row.item_id);
      if (!(id > 0)) continue;
      const state = notifyLineWh[id] || {};
      const wh = Number(state.warehouse_id);
      if (!(Number.isFinite(wh) && wh > 0)) {
        messageApi.warning(
          t('app.kuaizhizao.warehouseOutbound.pull.selectWarehouseForMaterial', {
            material: row.material_code || row.material_name || id,
          }),
        );
        return;
      }
      line_warehouses[String(id)] = wh;
      if (state.warehouse_name) {
        line_warehouse_names[String(id)] = state.warehouse_name;
      }
      const locId = Number(state.location_id);
      const locCode = String(state.location_code || '').trim();
      const needLoc = await lineLocationSelectionRequired(
        wh,
        Number.isFinite(locId) && locId > 0 ? locId : undefined,
        locCode || undefined,
      );
      if (needLoc) {
        messageApi.warning(
          t('app.kuaizhizao.warehouseOutbound.msg.selectLocationForMaterial', {
            material: row.material_code || row.material_name || id,
          }),
        );
        return;
      }
      if (Number.isFinite(locId) && locId > 0) {
        line_location_ids[String(id)] = locId;
      }
      if (locCode) {
        line_location_codes[String(id)] = locCode;
      }
    }

    const firstWh = Object.values(line_warehouses)[0];
    setNotifyPreviewConfirming(true);
    try {
      await executeNotify(notifyPreviewTarget, {
        warehouse_id: firstWh,
        warehouse_name: line_warehouse_names[String(Object.keys(line_warehouses)[0])] || undefined,
        line_warehouses,
        line_warehouse_names: Object.keys(line_warehouse_names).length ? line_warehouse_names : undefined,
        line_location_ids: Object.keys(line_location_ids).length ? line_location_ids : undefined,
        line_location_codes: Object.keys(line_location_codes).length ? line_location_codes : undefined,
        push_mode: pushMode,
      });
      resetNotifyPreviewModal();
      setSelectedRowKeys([]);
    } catch (error: any) {
      messageApi.error(error?.message || t('app.kuaizhizao.shipmentNotice.notifyFailed'));
    } finally {
      setNotifyPreviewConfirming(false);
    }
  }, [
    executeNotify,
    messageApi,
    notifyLineWh,
    notifyPreviewData,
    notifyPreviewTarget,
    resetNotifyPreviewModal,
    t,
  ]);

  const executeWithdraw = async (record: ShipmentNotice) => {
    try {
      await shipmentNoticeApi.withdraw(record.id!.toString());
      messageApi.success(t('app.kuaizhizao.shipmentNotice.withdrawSuccess'));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('app.kuaizhizao.shipmentNotice.withdrawFailed'));
    }
  };

  const handleWithdraw = (record: ShipmentNotice) => {
    modalApi.confirm({
      title: t('app.kuaizhizao.shipmentNotice.withdrawNotify'),
      content: t('app.kuaizhizao.shipmentNotice.withdrawConfirmContent', { code: record.notice_code }),
      onOk: () => executeWithdraw(record),
    });
  };

  const executeDelete = async (record: ShipmentNotice) => {
    try {
      await shipmentNoticeApi.delete(record.id!.toString());
      messageApi.success(t('common.deleteSuccess'));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('common.deleteFailed'));
    }
  };

  const handleBatchDelete = async (keys: React.Key[]) => {
    if (keys.length === 0) return;
    try {
      for (const k of keys) {
        await shipmentNoticeApi.delete(String(k));
      }
      messageApi.success(t('app.kuaizhizao.shipmentNotice.batchDeleteSuccess', { count: keys.length }));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error?.message || t('common.batchDeleteFailed'));
    }
  };

  const handleCreate = () => {
    pendingCreateFormValuesRef.current = null;
    navigate(SHIPMENT_NOTICE_CREATE_PATH);
  };

  const isPullLineSelectable = useCallback(
    (record: { remaining_quantity?: number }) => Number(record.remaining_quantity ?? 0) > 0,
    [],
  );

  const pullFromSalesOrderScopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const pullSalesOrderColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.shipmentNotice.salesOrderCode'),
        dataIndex: 'order_code',
        width: 168,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialName'),
        dataIndex: 'material_name',
        ellipsis: true,
        render: (_: unknown, record: PullSalesOrderCandidate) => (
          <MaterialStackedCell
            material_name={record.material_name}
            material_code={record.material_code}
            material_spec={record.material_spec}
          />
        ),
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
        title: t('app.kuaizhizao.quotation.form.customer'),
        dataIndex: 'customer_name',
        width: 140,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.salesOrder.deliveryDate'),
        dataIndex: 'required_date',
        width: 112,
        render: (v: string) => (v ? formatBusinessDateOnly(v) : '-'),
      },
      {
        title: t('app.kuaizhizao.shipmentNotice.convertStatus'),
        key: 'convert_status',
        width: 100,
        align: 'center' as const,
        render: (_: unknown, record: PullSalesOrderCandidate) =>
          renderPullCapabilityTag(
            Number(record.remaining_quantity ?? 0) > 0,
            t('app.kuaizhizao.shipmentNotice.canCreate'),
            t('app.kuaizhizao.purchaseRequisition.pull.cannotCreate'),
          ),
      },
    ],
    [t],
  );

  const pullFromSalesOrderQuery = useUniPullQuery<PullSalesOrderCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullFromSalesOrderScopeOptions,
    defaultScope: 'pullable',
    onOpen: () => {
      pullSourceOrderIdRef.current = undefined;
      setPullSourceOrderId(undefined);
      void listSalesOrders({ skip: 0, limit: 100, view: 'options' })
        .then((res) => {
          setPullSourceOrderOptions(
            (res?.data ?? [])
              .filter((row) => row.id != null && row.order_code)
              .map((row) => ({ value: row.id!, label: String(row.order_code) })),
          );
        })
        .catch((error: unknown) => {
          messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.shipmentNotice.pull.loadSourceFailed')));
          setPullSourceOrderOptions([]);
        });
    },
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const listRes = await listSalesOrderShipmentNoticePullLines({
          skip: (page - 1) * pageSize,
          limit: pageSize,
          keyword: keyword.trim() || undefined,
          sales_order_id: pullSourceOrderIdRef.current,
          pullable_only: isPullableScope(scope),
        });
        return { data: listRes?.data ?? [], total: listRes?.total ?? 0 };
      } catch (error: unknown) {
        messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.salesOrder.listFailed')));
        return { data: [], total: 0 };
      }
    },
    isRowDisabled: (record) => !isPullLineSelectable(record),
    onConfirm: async (_keys, rows) => {
      const selectedIds = rows
        .filter((row) => isPullLineSelectable(row))
        .map((row) => Number(row.id))
        .filter((id) => id > 0);
      if (!selectedIds.length) {
        messageApi.warning(t('app.kuaizhizao.shipmentNotice.pull.selectLinesFirst'));
        return;
      }
      try {
        const res = await pullShipmentNoticesFromSalesOrderItems(selectedIds);
        messageApi.success(
          res.message ||
            t('app.kuaizhizao.shipmentNotice.createFromSourceSuccess', {
              source: pullFromSalesOrderAction.sourceLabel,
              target: pullFromSalesOrderAction.targetLabel,
            }),
        );
        pullFromSalesOrderQuery.closeModal();
        invalidateMenuBadgeCounts();
    actionRef.current?.reload();
      } catch (error: unknown) {
        messageApi.error(
          getApiErrorMessage(
            error,
            t('app.kuaizhizao.shipmentNotice.createFromSourceFailed', {
              source: pullFromSalesOrderAction.sourceLabel,
              target: pullFromSalesOrderAction.targetLabel,
            }),
          ),
        );
      }
    },
  });

  const onSalesOrderSelect = async (orderId: number) => {
    let order = salesOrderList.find((o: any) => (o.id ?? o.sales_order_id) === orderId);
    if (!order) return;
    try {
      const detail = await getSalesOrder(orderId, true, false, { view: 'options' });
      order = detail;
    } catch {
      // use list data
    }
    const code = order.order_code || order.sales_order_code || order.code;
    const custId = order.customer_id ?? order.customerId;
    const cust = customerList.find((c: any) => (c.id ?? c.customer_id) === custId);
    const custName = cust?.name || cust?.customer_name || order.customer_name || order.customerName || '';
    createFormRef.current?.setFieldsValue({
      sales_order_code: code,
      customer_id: custId,
      customer_name: custName,
      customer_contact: order.customer_contact || cust?.contactPerson || (cust as any)?.contact,
      customer_phone: order.customer_phone || cust?.phone,
      shipping_address: order.shipping_address || cust?.address,
      currency_code: String(order.currency_code || order.currency || 'CNY').trim().toUpperCase() || 'CNY',
      exchange_rate: Number(order.exchange_rate ?? 1) || 1,
    });
    if (order.items && order.items.length > 0) {
      const items = order.items
        .map((it: any, index: number) => ({
          material_id: it.material_id ?? it.materialId,
          material_code: it.material_code || it.materialCode || '',
          material_name: it.material_name || it.materialName || '',
          material_spec: it.material_spec || '',
          material_unit: it.material_unit || it.materialUnit || defaultUnit,
          notice_quantity: Number(it.required_quantity ?? it.quantity ?? it.order_quantity) || 0,
          unit_price: Number((it.unit_price ?? it.unitPrice) || (order.items && order.items[index]?.unit_price)) || 0,
          sales_order_item_id: it.id ?? it.sales_order_item_id,
        }))
        .filter((it: any) => Number(it.material_id) > 0 && Number(it.notice_quantity) > 0);
      createFormRef.current?.setFieldsValue({ items: items.length ? items : [defaultNoticeItem] });
      if (!items.length) {
        messageApi.warning(t('app.kuaizhizao.shipmentNotice.noMaterialItemsFromSource', { source: salesOrderEntityName }));
      }
    }
  };

  const handleCreateSubmit = async (values: any) => {
    const validItems = (values.items ?? []).filter((it: any) => it.material_id && (Number(it.notice_quantity) || 0) > 0);
    if (!validItems.length) {
      messageApi.error(t('app.kuaizhizao.shipmentNotice.itemsRequired'));
      throw new Error(t('app.kuaizhizao.shipmentNotice.itemsRequired'));
    }
    if (!values.sales_order_id || !values.sales_order_code) {
      messageApi.error(t('app.kuaizhizao.salesOrderChange.selectSalesOrder'));
      throw new Error(t('app.kuaizhizao.salesOrderChange.selectSalesOrder'));
    }
    const cust =
      customerList.find((c: any) => Number(c.id ?? c.customer_id) === Number(values.customer_id)) ||
      { name: values.customer_name };
    const customerName = String(cust.name || cust.customer_name || values.customer_name || '').trim();
    if (!values.customer_id || !customerName) {
      messageApi.error(t('app.kuaizhizao.quotation.form.selectCustomer'));
      throw new Error(t('app.kuaizhizao.quotation.form.selectCustomer'));
    }
    const payloadItems = validItems.map((it: any) => ({
      material_id: Number(it.material_id),
      material_code: String(it.material_code || '').trim(),
      material_name: String(it.material_name || '').trim(),
      material_spec: it.material_spec != null && String(it.material_spec).trim()
        ? String(it.material_spec).trim()
        : undefined,
      material_unit: String(it.material_unit || defaultUnit).trim() || defaultUnit,
      ...pickDocumentLineDualQuantityFields(it as Record<string, unknown>),
      notice_quantity: Number(it.notice_quantity) || 0,
      unit_price: Number(it.unit_price) || 0,
      total_amount: computeSimpleDocumentLineTotal(
        Number(it.notice_quantity) || 0,
        Number(it.unit_price) || 0,
      ),
      ...(it.sales_order_item_id != null && Number(it.sales_order_item_id) > 0
        ? { sales_order_item_id: Number(it.sales_order_item_id) }
        : {}),
    }));
    const incompleteItem = payloadItems.find(
      (it) => !it.material_id || !it.material_code || !it.material_name || !it.material_unit,
    );
    if (incompleteItem) {
      messageApi.error(t('app.kuaizhizao.shipmentNotice.itemMaterialIncomplete'));
      throw new Error(t('app.kuaizhizao.shipmentNotice.itemMaterialIncomplete'));
    }
    let noticeCode = values.notice_code;
    const ruleCodeToUse = effectiveRuleCode || getPageRuleCode('kuaizhizao-shipment-notice');
    if (
      ruleCodeToUse &&
      (isAutoGenerateEnabled('kuaizhizao-shipment-notice') || effectiveRuleCode) &&
      (noticeCode === previewCode || !noticeCode)
    ) {
      try {
        const res = await generateCode({ rule_code: ruleCodeToUse });
        noticeCode = res.code;
      } catch (e) {
        console.warn(t('app.kuaizhizao.shipmentNotice.codeGenerateFailed'), e);
      }
    }
    const shouldCommit = createCommitAfterSaveRef.current;
    createCommitAfterSaveRef.current = false;
    try {
      const { customData, standardValues } = extractShipmentNoticeFormValues(values, createFormRef.current);
      const created = await shipmentNoticeApi.create({
        notice_code: noticeCode || undefined,
        sales_order_id: Number(standardValues.sales_order_id ?? values.sales_order_id),
        sales_order_code: String(standardValues.sales_order_code ?? values.sales_order_code),
        customer_id: Number(standardValues.customer_id ?? values.customer_id),
        customer_name: customerName,
        customer_contact: standardValues.customer_contact ?? values.customer_contact,
        customer_phone: standardValues.customer_phone ?? values.customer_phone,
        warehouse_id: values.warehouse_id != null && values.warehouse_id !== ''
          ? Number(values.warehouse_id)
          : undefined,
        warehouse_name: values.warehouse_name || undefined,
        planned_ship_date: values.planned_ship_date ? formatDateTime(values.planned_ship_date, 'YYYY-MM-DD') : undefined,
        shipping_address: standardValues.shipping_address ?? values.shipping_address,
        currency_code: String(standardValues.currency_code || values.currency_code || 'CNY').trim().toUpperCase() || 'CNY',
        exchange_rate: Number(standardValues.exchange_rate ?? values.exchange_rate ?? 1) || 1,
        notes: standardValues.notes ?? values.notes,
        attachments: normalizeDocumentAttachments(standardValues.attachments ?? values.attachments),
        items: payloadItems,
      });
      const createdId = Number((created as { id?: number })?.id);
      if (Number.isFinite(createdId) && createdId > 0) {
        try {
          await saveShipmentNoticeCustomFieldValues(createdId, customData);
        } catch {
          messageApi.error(t('app.kuaizhizao.quality.common.messages.inspectCustomFieldsSaveFailed'));
        }
      }
      if (shouldCommit) {
        if (!Number.isFinite(createdId) || createdId <= 0) {
          messageApi.error(t('common.operationFailed'));
          return;
        }
        try {
          await shipmentNoticeApi.commit(createdId);
        } catch (error: unknown) {
          setEditingId(createdId);
          setEditingBusinessStatus('待发货');
          setEditingReviewStatus('草稿');
          editFormRef.current?.setFieldsValue({
            sales_order_id: values.sales_order_id,
            sales_order_code: values.sales_order_code,
            customer_id: values.customer_id,
            customer_name: customerName,
            customer_contact: values.customer_contact,
            customer_phone: values.customer_phone,
            warehouse_id: values.warehouse_id,
            warehouse_name: values.warehouse_name,
            planned_ship_date: values.planned_ship_date,
            shipping_address: values.shipping_address,
            currency_code: values.currency_code,
            exchange_rate: values.exchange_rate,
            notes: values.notes,
            attachments: normalizeDocumentAttachments(values.attachments),
            items: validItems,
          });
          formPageInitKeyRef.current = null;
          navigate(shipmentNoticeEditPath(createdId));
          messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
          actionRef.current?.reload();
          return;
        }
        messageApi.success(t('app.kuaizhizao.shipmentNotice.committed'));
      } else {
        messageApi.success(t('common.createSuccess'));
      }
      setEffectiveRuleCode(null);
      resetShipmentNoticeFormFieldValues();
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
      leaveShipmentNoticeFormPage();
    } catch (error: any) {
      messageApi.error(error.message || t('common.createFailed'));
      throw error;
    }
  };

  const handleEditSubmit = async (values: any) => {
    const saveId = editingId ?? editRouteId;
    if (!saveId) return;
    const shouldCommit = editCommitAfterSaveRef.current;
    editCommitAfterSaveRef.current = false;
    const { customData, standardValues } = extractShipmentNoticeFormValues(values, editFormRef.current);
    const cust = customerList.find((c: any) => (c.id ?? c.customer_id) === (standardValues.customer_id ?? values.customer_id));
    try {
      await shipmentNoticeApi.update(String(saveId), {
        customer_id: standardValues.customer_id ?? values.customer_id,
        customer_name: cust?.name || cust?.customer_name || values.customer_name,
        customer_contact: standardValues.customer_contact ?? values.customer_contact,
        customer_phone: standardValues.customer_phone ?? values.customer_phone,
        warehouse_id: standardValues.warehouse_id ?? values.warehouse_id,
        warehouse_name: standardValues.warehouse_name ?? values.warehouse_name,
        planned_ship_date: values.planned_ship_date ? formatDateTime(values.planned_ship_date, 'YYYY-MM-DD') : undefined,
        shipping_address: standardValues.shipping_address ?? values.shipping_address,
        currency_code: String(standardValues.currency_code || values.currency_code || 'CNY').trim().toUpperCase() || 'CNY',
        exchange_rate: Number(standardValues.exchange_rate ?? values.exchange_rate ?? 1) || 1,
        notes: standardValues.notes ?? values.notes,
        attachments: normalizeDocumentAttachments(standardValues.attachments ?? values.attachments),
      });
      try {
        await saveShipmentNoticeCustomFieldValues(saveId, customData);
      } catch {
        messageApi.error(t('app.kuaizhizao.quality.common.messages.inspectCustomFieldsSaveFailed'));
      }
      if (shouldCommit) {
        try {
          await shipmentNoticeApi.commit(saveId);
        } catch (error: unknown) {
          messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
          actionRef.current?.reload();
          return;
        }
        messageApi.success(t('app.kuaizhizao.shipmentNotice.committed'));
      } else {
        messageApi.success(t('common.updateSuccess'));
      }
      resetShipmentNoticeFormFieldValues();
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
      leaveShipmentNoticeFormPage();
    } catch (error: any) {
      messageApi.error(error.message || t('common.updateFailed'));
      throw error;
    }
  };

  const detailColumns: ProDescriptionsItemProps<ShipmentNoticeDetail>[] = alignDescriptionColumns([
    { title: t('app.kuaizhizao.shipmentNotice.noticeCode'), dataIndex: 'notice_code' },
    { title: t('app.kuaizhizao.shipmentNotice.salesOrderCode'), dataIndex: 'sales_order_code' },
    { title: t('app.kuaizhizao.quotation.form.customer'), dataIndex: 'customer_name' },
    { title: t('field.customer.contactPerson'), dataIndex: 'customer_contact' },
    { title: t('field.customer.phone'), dataIndex: 'customer_phone' },
    { title: t('app.kuaizhizao.shipmentNotice.outboundWarehouse'), dataIndex: 'warehouse_name' },
    { title: t('app.kuaizhizao.shipmentNotice.plannedShipDate'), dataIndex: 'planned_ship_date', valueType: 'date' },
    {
      title: t('app.kuaizhizao.quotation.form.currency'),
      dataIndex: 'currency_code',
      render: (_: unknown, record: ShipmentNoticeDetail) =>
        String((record as any)?.currency_code || 'CNY').trim().toUpperCase() || 'CNY',
    },
    { title: t('app.kuaizhizao.salesOrder.shippingAddress'), dataIndex: 'shipping_address', span: 3 },
    { title: t('app.kuaizhizao.shipmentNotice.notifiedAt'), dataIndex: 'notified_at', valueType: 'dateTime' },
    { title: t('common.remark'), dataIndex: 'notes', span: 3 },
  ]);

  /** 将 Excel 行写入当前表单「通知明细」（新建弹窗内导入或列表工具栏导入共用） */
  const applyExcelRowsToNoticeForm = async (data: any[][]) => {
    if (data.length <= 1) return;
    const rows = data.slice(1).filter((row) => row[0]);
    const loaded = await loadMaterialFormReferenceList(KUAIZHIZAO_DOC_HOST.shipmentNotice);
    const materials = await resolveMaterialsByCodesForImport(
      collectImportMaterialCodes(rows, 0),
      loaded,
    );
    const items = rows.map((row) => {
      const materialCode = normalizeImportMaterialCode(row[0]);
      const mat = findMaterialByImportCode(materials, materialCode);
      const unitRaw = String(row[5] || '').trim();
      const material_unit = mat?.baseUnit
        || (unitRaw ? materialUnitImport.parse(unitRaw) ?? unitRaw : defaultUnit);
      return {
        material_id: mat?.id,
        material_code: mat?.mainCode || mat?.code || materialCode,
        notice_quantity: Number(row[1]) || 1,
        unit_price: Number(row[2]) || 0,
        material_name: mat?.name || String(row[3] || ''),
        material_spec: mat?.specification || String(row[4] || ''),
        material_unit,
      };
    });

    if (items.length === 0) {
      messageApi.warning(t('app.kuaizhizao.shipmentNotice.importNoValidData'));
      return;
    }

    const currentItems = createFormRef.current?.getFieldValue('items') || [];
    const filteredCurrent = currentItems.filter((it: any) => it.material_id || it.material_code);
    createFormRef.current?.setFieldsValue({
      items: [...filteredCurrent, ...items],
    });
    messageApi.success(t('app.kuaizhizao.shipmentNotice.importSuccessCount', { count: items.length }));
  };

  const initShipmentNoticeCreateForm = useCallback(async () => {
    setEditingId(null);
    createFormRef.current?.resetFields();
    resetShipmentNoticeFormFieldValues();
    const pending = pendingCreateFormValuesRef.current;
    if (pending) {
      pendingCreateFormValuesRef.current = null;
      createFormRef.current?.setFieldsValue(pending);
      const importRows = pendingListImportRowsRef.current;
      if (importRows) {
        pendingListImportRowsRef.current = null;
        await applyExcelRowsToNoticeForm(importRows);
      }
      return;
    }
    setPreviewCode(null);
    setEffectiveRuleCode(null);
    let ruleCode = getPageRuleCode('kuaizhizao-shipment-notice');
    let autoGenerate = isAutoGenerateEnabled('kuaizhizao-shipment-notice');
    try {
      const pageConfig = await getCodeRulePageConfig('kuaizhizao-shipment-notice');
      if (pageConfig?.ruleCode) {
        ruleCode = pageConfig.ruleCode;
        autoGenerate = !!pageConfig.autoGenerate;
      }
    } catch {
      /* 编号规则读取失败时仍打开表单 */
    }
    let noticeCode = '';
    if (autoGenerate && ruleCode) {
      setEffectiveRuleCode(ruleCode);
      try {
        const preview = await testGenerateCode({ rule_code: ruleCode });
        noticeCode = preview.code ?? '';
        setPreviewCode(noticeCode || null);
      } catch (e) {
        console.warn(t('app.kuaizhizao.shipmentNotice.codePreviewFailed'), e);
        setPreviewCode(null);
      }
    }
    createFormRef.current?.setFieldsValue({
      notice_code: noticeCode,
      items: [defaultNoticeItem],
    });
    const importRows = pendingListImportRowsRef.current;
    if (importRows) {
      pendingListImportRowsRef.current = null;
      await applyExcelRowsToNoticeForm(importRows);
    }
  }, [applyExcelRowsToNoticeForm, defaultNoticeItem, resetShipmentNoticeFormFieldValues, t]);

  useEffect(() => {
    if (!isFormPage) {
      formPageInitKeyRef.current = null;
      return;
    }
    const initKey = isCreatePage ? 'create' : `edit-${editRouteId}`;
    if (formPageInitKeyRef.current === initKey) return;
    formPageInitKeyRef.current = initKey;
    if (isCreatePage) {
      void initShipmentNoticeCreateForm();
    } else if (editRouteId != null) {
      void loadShipmentNoticeEditForm(editRouteId);
    }
  }, [
    editRouteId,
    initShipmentNoticeCreateForm,
    isCreatePage,
    isFormPage,
    loadShipmentNoticeEditForm,
  ]);

  const handleFormLineImport = (data: any[][]) => {
    void applyExcelRowsToNoticeForm(data);
  };

  /** 列表工具栏导入：打开新建弹窗并写入明细（与 UniTable 内置导入弹窗配合） */
  const handleListToolbarImport = (data: any[][]) => {
    if (isFormPage && isEditPage) {
      messageApi.warning(t('app.kuaizhizao.shipmentNotice.closeEditBeforeImport'));
      return;
    }
    pendingListImportRowsRef.current = data;
    formPageInitKeyRef.current = null;
    navigate(SHIPMENT_NOTICE_CREATE_PATH);
  };

  const renderCreateForm = () => (
    <>
      <Row gutter={16}>
        <Col span={8}>
          <ProFormText
            name="notice_code"
            label={t('app.kuaizhizao.shipmentNotice.noticeCode')}
            placeholder={isAutoGenerateEnabled('kuaizhizao-shipment-notice') ? t('app.kuaizhizao.quotation.form.codeAutoGenerate') : t('app.kuaizhizao.shipmentNotice.codeRequired')}
            rules={[{ required: true, message: t('app.kuaizhizao.shipmentNotice.codeRequired') }]}
          />
        </Col>
        <Col span={8}>
          <ProForm.Item name="sales_order_id" label={t('app.kuaizhizao.salesOrderChange.salesOrderLabel')} rules={[{ required: true, message: t('app.kuaizhizao.salesOrderChange.selectSalesOrder') }]}>
            <Select
              placeholder={t('app.kuaizhizao.salesOrderChange.selectSalesOrder')}
              showSearch
              optionFilterProp="label"
              options={salesOrderList.map((o: any) => ({
                value: o.id ?? o.sales_order_id,
                label: `${o.order_code || o.sales_order_code || o.code || ''} - ${o.customer_name || o.customerName || ''}`.trim(),
              }))}
              onChange={onSalesOrderSelect}
            />
          </ProForm.Item>
        </Col>
        <Col span={8}>
          <ProForm.Item name="customer_id" label={t('app.kuaizhizao.quotation.form.customer')} rules={[{ required: true, message: t('app.kuaizhizao.quotation.form.selectCustomer') }]}>
            <Select
              placeholder={t('app.kuaizhizao.quotation.form.selectCustomer')}
              showSearch
              optionFilterProp="label"
              options={customerList.map((c: any) => ({ value: c.id ?? c.customer_id, label: c.name || c.customer_name || c.code }))}
              onChange={(v) => {
                const cust = customerList.find((x: any) => (x.id ?? x.customer_id) === v);
                if (cust) createFormRef.current?.setFieldsValue({
                  customer_name: cust.name || cust.customer_name,
                  customer_contact: cust.contactPerson ?? (cust as any)?.contact,
                  customer_phone: cust.phone,
                  shipping_address: cust.address,
                });
              }}
            />
          </ProForm.Item>
        </Col>
      </Row>
      <ProFormText name="sales_order_code" hidden />
      <ProFormText name="customer_name" hidden />
      <Row gutter={16}>
        <Col span={8}>
          <ProFormText name="customer_contact" label={t('field.customer.contactPerson')} placeholder={t('field.customer.contactPersonPlaceholder')} />
        </Col>
        <Col span={8}>
          <ProFormText name="customer_phone" label={t('field.customer.phone')} placeholder={t('field.customer.phonePlaceholder')} />
        </Col>
        <Col span={8}>
          <UniWarehouseSelect
            name="warehouse_id"
            label={t('app.kuaizhizao.shipmentNotice.outboundWarehouse')}
            placeholder={t('app.kuaizhizao.shipmentNotice.selectOutboundWarehouse')}
            onChange={(_, wh) => createFormRef.current?.setFieldsValue({ warehouse_name: wh?.name ?? '' })}
          />
        </Col>
      </Row>
      <ProFormText name="warehouse_name" hidden />
      <ProFormText name="currency_code" hidden initialValue="CNY" />
      <ProForm.Item name="exchange_rate" hidden initialValue={1}>
        <InputNumber />
      </ProForm.Item>
      <Row gutter={16}>
        <Col span={8}>
          <ProFormDatePicker name="planned_ship_date" label={t('app.kuaizhizao.shipmentNotice.plannedShipDate')} fieldProps={buildFutureDateShortcutFieldProps({ getForm: () => createFormRef.current, fieldName: 'planned_ship_date', t })} />
        </Col>
      </Row>
      <ProFormTextArea name="shipping_address" label={t('app.kuaizhizao.salesOrder.shippingAddress')} placeholder={t('app.kuaizhizao.quotation.form.shippingAddressPlaceholder')} fieldProps={{ rows: 2 }} />
      <UniTableDetail
        name="items"
        title={t('app.kuaizhizao.shipmentNotice.noticeItems')}
        required
        requiredMessage={t('app.kuaizhizao.shipmentNotice.noticeItemsRequired')}
        headerExtra={(
          <Space size={8}>
            <Button
              type="default"
              icon={<ImportOutlined />}
              onClick={() => setImportVisible(true)}
            >
              {t('common.importDetail')}
            </Button>
            <Button
              type="default"
              icon={<PlusOutlined />}
              onClick={() => {
                const items = [...(createFormRef.current?.getFieldValue('items') ?? [])];
                items.push({ ...defaultNoticeItem });
                createFormRef.current?.setFieldsValue({ items });
              }}
            >
              {t('app.kuaizhizao.salesOrder.addItem')}
            </Button>
            <Button
              type="default"
              icon={<AppstoreAddOutlined />}
              onClick={() => setMaterialPickerOpen(true)}
            >
              {t('app.kuaizhizao.sales.common.productBatchSelect')}
            </Button>
          </Space>
        )}
        columns={[
                {
                  title: productColumnTitle,
                  dataIndex: 'material_id',
                  width: 220,
                  render: (_: any, __: any, index: number) => (
                    <AntForm.Item noStyle shouldUpdate={(prev: any, curr: any) => prev?.items?.[index] !== curr?.items?.[index]}>
                      {({ getFieldValue }: any) => {
                        const row = getFieldValue('items')?.[index];
                        const mid = row?.material_id ? Number(row.material_id) : null;
                        const fallback = mid && (row?.material_code || row?.material_name)
                          ? { value: mid, label: `${row.material_code || ''} - ${row.material_name || ''}`.trim() || String(mid) }
                          : undefined;
                        return (
                          <div className="uni-detail-material-cell">
                            {/* 注册明细必填字段，避免 setFieldsValue 写入后 onFinish 丢失导致后端 422 Field required */}
                            <AntForm.Item name={[index, 'material_code']} hidden>
                              <Input />
                            </AntForm.Item>
                            <AntForm.Item name={[index, 'material_name']} hidden>
                              <Input />
                            </AntForm.Item>
                            <AntForm.Item name={[index, 'sales_order_item_id']} hidden>
                              <Input />
                            </AntForm.Item>
                            <UniMaterialSelect
                              name={[index, 'material_id']}
                              label=""
                              placeholder={t('app.kuaizhizao.quotation.form.selectMaterial')}
                              required
                              size="small"
                              listFieldKey={index}
                              listFieldName="items"
                              fillMapping={withMaterialLineFillMapping({
                                material_unit: 'baseUnit',
                                unit_price: 'defaults.defaultSalePrice' as any,
                              })}
                              fallbackOption={fallback}
                              formItemProps={{ style: { margin: 0 } }}
                              showQuickCreate
                              showAdvancedSearch
                              skipFuzzyPinyinClientFilter
                              sourceType={materialSourceType}
                            />
                          </div>
                        );
                      }}
                    </AntForm.Item>
                  ),
                },
                ...buildDocumentDetailSpecModelFormColumns(t, { width: 120, inputSize: 'small' }),
                ...buildDocumentDetailPartnerMaterialFormColumns(t, 'customer', {
                  width: 120,
                  inputSize: 'small',
                }),
                ...buildDocumentLineDualQuantityPairColumns({
                  t,
                  getForm: () => createFormRef.current,
                  quantityField: 'notice_quantity',
                  unitField: 'material_unit',
                  scenario: 'sale',
                  quantityPrecision: quantityDecimals,
                  width: 168,
                  columnSpread: { align: 'right' as const },
                }),
                {
                  title: (
                    <AntForm.Item
                      noStyle
                      shouldUpdate={(prev: any, curr: any) => prev?.currency_code !== curr?.currency_code}
                    >
                      {({ getFieldValue }: any) =>
                        t(
                          'app.kuaizhizao.salesOrder.unitPrice',
                          documentCurrencyTitleVars(getFieldValue('currency_code'), t),
                        )
                      }
                    </AntForm.Item>
                  ),
                  dataIndex: 'unit_price',
                  width: 100,
                  align: 'right' as const,
                  render: (_: any, __: any, index: number) => (
                    <AntForm.Item
                      noStyle
                      shouldUpdate={(prev: any, curr: any) => prev?.currency_code !== curr?.currency_code}
                    >
                      {({ getFieldValue }: any) => {
                        const moneyPrefix = resolveDocumentCurrencyInputPrefix(getFieldValue('currency_code'));
                        return (
                          <AntForm.Item name={[index, 'unit_price']} style={{ margin: 0 }}>
                            <InputNumber
                              placeholder="0"
                              min={0}
                              precision={priceDecimals}
                              prefix={moneyPrefix}
                              style={{ width: '100%' }}
                              size="small"
                            />
                          </AntForm.Item>
                        );
                      }}
                    </AntForm.Item>
                  ),
                },
              ]}
        disabledAdd
        minRows={1}
        initialValue={{ ...defaultNoticeItem }}
        tableProps={{
          size: 'small',
          style: { width: '100%', margin: 0 },
        }}
      />
      <ShipmentNoticeFormSummary />
      <ProFormTextArea name="notes" label={t('common.remark')} placeholder={t('common.remark')} fieldProps={{ rows: 2 }} colProps={{ span: 24 }} />
      <CustomFieldsFormSection
        customFields={shipmentNoticeFormCustomFields}
        customFieldValues={shipmentNoticeFormCustomFieldValues}
        gridColumns={2}
      />
      <DocumentAttachmentsField category="shipment_notice_attachments" />
    </>
  );

  const renderEditForm = () => (
    <>
      <Row gutter={16}>
        <Col span={8}>
          <ProFormText name="sales_order_code" label={t('app.kuaizhizao.shipmentNotice.salesOrderCode')} disabled />
        </Col>
        <Col span={8}>
          <ProForm.Item name="customer_id" label={t('app.kuaizhizao.quotation.form.customer')} rules={[{ required: true, message: t('app.kuaizhizao.quotation.form.selectCustomer') }]}>
            <Select
              placeholder={t('app.kuaizhizao.quotation.form.selectCustomer')}
              showSearch
              optionFilterProp="label"
              options={customerList.map((c: any) => ({ value: c.id ?? c.customer_id, label: c.name || c.customer_name || c.code }))}
              onChange={(v) => {
                const cust = customerList.find((x: any) => (x.id ?? x.customer_id) === v);
                if (cust) editFormRef.current?.setFieldsValue({
                  customer_name: cust.name || cust.customer_name,
                  customer_contact: cust.contactPerson ?? (cust as any)?.contact,
                  customer_phone: cust.phone,
                });
              }}
            />
          </ProForm.Item>
        </Col>
        <Col span={8}>
          <ProFormText name="customer_contact" label={t('field.customer.contactPerson')} placeholder={t('field.customer.contactPersonPlaceholder')} />
        </Col>
      </Row>
      <Row gutter={16}>
        <Col span={8}>
          <ProFormText name="customer_phone" label={t('field.customer.phone')} placeholder={t('field.customer.phonePlaceholder')} />
        </Col>
        <Col span={8}>
          <UniWarehouseSelect
            name="warehouse_id"
            label={t('app.kuaizhizao.shipmentNotice.outboundWarehouse')}
            placeholder={t('app.kuaizhizao.shipmentNotice.selectOutboundWarehouse')}
            onChange={(_, wh) => editFormRef.current?.setFieldsValue({ warehouse_name: wh?.name ?? '' })}
          />
        </Col>
        <Col span={8}>
          <ProFormDatePicker name="planned_ship_date" label={t('app.kuaizhizao.shipmentNotice.plannedShipDate')} fieldProps={buildFutureDateShortcutFieldProps({ getForm: () => editFormRef.current, fieldName: 'planned_ship_date', t })} />
        </Col>
      </Row>
      <ProFormText name="warehouse_name" hidden />
      <ProFormText name="customer_name" hidden />
      <ProFormText name="currency_code" hidden />
      <ProForm.Item name="exchange_rate" hidden>
        <InputNumber />
      </ProForm.Item>
      <ProFormTextArea name="shipping_address" label={t('app.kuaizhizao.salesOrder.shippingAddress')} placeholder={t('app.kuaizhizao.quotation.form.shippingAddressPlaceholder')} fieldProps={{ rows: 2 }} />
      <ProFormItem label={t('app.kuaizhizao.shipmentNotice.noticeItems')}>
        <AntForm.Item
          noStyle
          shouldUpdate={(prev: any, curr: any) =>
            prev?.items !== curr?.items || prev?.currency_code !== curr?.currency_code
          }
        >
          {({ getFieldValue }: any) => {
            const items = getFieldValue('items') ?? [];
            const currencyVars = documentCurrencyTitleVars(getFieldValue('currency_code'), t);
            return (
              <Table
                size="small"
                dataSource={items.map((it: any, i: number) => ({ ...it, key: i }))}
                rowKey="key"
                pagination={false}
                columns={[
                  { title: t('app.kuaizhizao.salesOrder.materialCode'), dataIndex: 'material_code', width: 120 },
                  { title: t('app.kuaizhizao.salesOrder.materialName'), dataIndex: 'material_name', width: 150 },
                  { title: t('common.unit'), dataIndex: 'material_unit', width: 60 },
                  { title: t('common.quantity'), dataIndex: 'notice_quantity', width: 90, align: 'right', render: formatQuantity },
                  {
                    title: t('app.kuaizhizao.salesOrder.unitPrice', currencyVars),
                    dataIndex: 'unit_price',
                    width: 90,
                    align: 'right' as const,
                    render: (text: unknown) => {
                      const code = getFieldValue('currency_code');
                      return `${resolveDocumentCurrencyInputPrefix(code)}${text ?? 0}`;
                    },
                  },
                ]}
              />
            );
          }}
        </AntForm.Item>
        <ShipmentNoticeFormSummary />
      </ProFormItem>
      <ProFormTextArea name="notes" label={t('common.remark')} placeholder={t('common.remark')} fieldProps={{ rows: 2 }} colProps={{ span: 24 }} />
      <CustomFieldsFormSection
        customFields={shipmentNoticeFormCustomFields}
        customFieldValues={shipmentNoticeFormCustomFieldValues}
        gridColumns={2}
      />
      <DocumentAttachmentsField category="shipment_notice_attachments" />
    </>
  );

  const timeconfigBasicItems = useDetailDrawerDescriptionItems(
    detailColumns, noticeDetail,
    'shipment_notice',
  );

  const shipmentNoticeAttachments = documentAttachmentsFromRecord(noticeDetail);
  const shipmentNoticeAttLabel = t('app.uniDetail.sectionAttachments');
  const shipmentNoticeOqcSupplementary =
    noticeDetail?.id != null ? (
      <LinkedOqcPanel
        shipmentNoticeId={noticeDetail.id}
        active={detailDrawerVisible}
        onNavigate={(path) => {
          setDetailDrawerVisible(false);
          setNoticeDetail(null);
          navigate(path);
        }}
      />
    ) : undefined;

  const shipmentNoticeCanCommitEdit =
    isCreatePage
    || (['待发货'].includes(String(editingBusinessStatus ?? '').trim())
      && ['', '草稿', 'draft', 'DRAFT', '已驳回', '审核驳回', 'rejected'].includes(
        String(editingReviewStatus ?? '').trim(),
      ));

  const triggerShipmentNoticeCommit = useCallback(() => {
    if (isCreatePage) {
      createCommitAfterSaveRef.current = true;
      void createFormRef.current?.submit?.();
      return;
    }
    editCommitAfterSaveRef.current = true;
    void editFormRef.current?.submit?.();
  }, [isCreatePage]);

  const submitShipmentNoticeForm = useCallback(() => {
    if (isCreatePage) {
      void createFormRef.current?.submit?.();
      return;
    }
    void editFormRef.current?.submit?.();
  }, [isCreatePage]);

  useSubmitShortcut(submitShipmentNoticeForm, isFormPage);

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
                  onClick={leaveShipmentNoticeFormPage}
                />
                <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
                  {isCreatePage
                    ? t('app.kuaizhizao.shipmentNotice.create')
                    : t('app.kuaizhizao.shipmentNotice.edit')}
                </Typography.Title>
              </Space>
              <DocumentFormPageHeaderActions
                onCancel={leaveShipmentNoticeFormPage}
                onSaveDraft={submitShipmentNoticeForm}
                onPrimarySubmit={submitShipmentNoticeForm}
                isCreatePage={isCreatePage}
                showSaveDraft={false}
                canSubmitAfterSave={false}
                showCommitSubmit={shipmentNoticeCanCommitEdit}
                onCommitSubmit={triggerShipmentNoticeCommit}
              />
            </>
          }
        >
          <Spin spinning={formPageLoading}>
            <ProForm
              formRef={isCreatePage ? createFormRef : editFormRef}
              layout="vertical"
              submitter={false}
              initialValues={isCreatePage ? { items: [defaultNoticeItem] } : undefined}
              onFinish={isCreatePage ? handleCreateSubmit : handleEditSubmit}
            >
              {isCreatePage ? renderCreateForm() : renderEditForm()}
            </ProForm>
          </Spin>
        </DocumentFormPageLayout>
        {isCreatePage ? (
          <>
            <UniMaterialBatchPicker
              open={materialPickerOpen}
              onCancel={() => setMaterialPickerOpen(false)}
              onConfirm={(selected) => {
                appendShipmentNoticeItemsFromMaterials(selected);
                setMaterialPickerOpen(false);
              }}
            />
            <Suspense fallback={null}>
              <LazyUniImport
                visible={importVisible}
                onCancel={() => setImportVisible(false)}
                onConfirm={handleFormLineImport}
                title={t('app.kuaizhizao.shipmentNotice.importItemsTitle')}
                headers={noticeItemImportTemplate.importHeaders}
                exampleRow={noticeItemImportTemplate.importExampleRow}
                columnOptions={noticeItemImportTemplate.importColumnOptions}
              />
            </Suspense>
          </>
        ) : null}
      </>
    );
  }

  return (
    <>
      <ListPageTemplate>
        <UniTable
          columnPersistenceId={SHIPMENT_NOTICE_LIST_PERSISTENCE_ID}
          headerTitle={t('app.kuaizhizao.shipmentNotice.title')}
          actionRef={actionRef}
          rowKey={dataViewMode === 'detail' ? '_rowKey' : 'id'}
          columns={columns}
          viewTypes={['table', 'detailTable', 'help']}
          defaultViewType={viewTypeState === 'help' ? 'table' : viewTypeState}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.shipmentNotice)}
          onViewTypeChange={(v) => {
            dataViewModeRef.current = resolveDetailTableViewMode(v as 'table' | 'detailTable' | 'help');
            setViewTypeState(v as 'table' | 'detailTable' | 'help');
            setTimeout(() => actionRef.current?.reload(), 0);
          }}
          detailTableColumns={detailTableColumns}
          onTableDataChange={(rows) => {
            if (dataViewModeRef.current === 'order') {
              tableRowsRef.current = rows as ShipmentNotice[];
            }
          }}
          pinnedTabsField={LIST_LIFECYCLE_STAGE_FIELD}
          pinnedTabsValueEnum={shipmentNoticeLifecycleValueEnum}
          showAdvancedSearch
          skipFuzzyPinyinClientFilter
          showCreateButton={false}
          createButtonText={t('app.kuaizhizao.shipmentNotice.create')}
          onCreate={handleCreate}
          toolBarRender={() => [
            <UniPullCreateToolbar
              compactKey="create-shipment-notice-with-pull"
              createIcon={<PlusOutlined />}
              createLabel={t('app.kuaizhizao.shipmentNotice.create')}
              onCreate={() => {
                void handleCreate();
              }}
              menuItems={[
                ...buildKuaizhizaoPullCreateMenuItems(t, [
                  {
                    key: 'pull-from-sales-order',
                    actionKey: 'shipment_notice.pull_from_sales_order',
                    onClick: () => {
                      pullFromSalesOrderQuery.openModal();
                    },
                  },
                ]),
                { type: 'divider' as const, key: 'copy-selected-divider' },
                {
                  key: 'copy-selected',
                  label: t('app.kuaizhizao.shipmentNotice.copySelectedCreate'),
                  disabled: selectedNoticesForBatch.length !== 1,
                  onClick: () => void handleCopySelectedShipmentNotice(),
                },
              ]}
            />,
            <UniBatchMenuButton
              key="shipment-notice-submit"
              selectedRowKeys={selectedRowKeys}
              menuItems={shipmentNoticeToolbarAuditMenus.submitItems}
              buttonText={t('common.submit')}
            />,
            <UniBatchMenuButton
              key="shipment-notice-audit"
              selectedRowKeys={selectedRowKeys}
              menuItems={shipmentNoticeToolbarAuditMenus.auditItems}
              buttonText={t('components.uniAction.audit')}
            />,
          ]}
          enableRowSelection={viewTypeState !== 'detailTable'}
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          showDeleteButton
          deleteButtonText={t('common.delete')}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) => t('app.kuaizhizao.shipmentNotice.confirmBatchDelete', { count })}
          toolBarActionsAfterBatch={[
            <UniCapabilityBatchButton
              key="shipment-notice-withdraw"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedNoticesForBatch}
              capabilityKey="withdraw"
              permAllowed={shipmentNoticePerms.canAction?.('revoke') ?? false}
              batchAllowed={shipmentNoticeBatchWithdrawAllowed}
              onRun={(id) => shipmentNoticeApi.withdraw(String(id))}
              notAllowedMessage={t('app.kuaizhizao.shipmentNotice.batchWithdrawNotAllowed')}
              onSuccess={() => {
                setSelectedRowKeys([]);
                invalidateMenuBadgeCounts();
    actionRef.current?.reload();
              }}
              requireConfirm
              labels={{
                single: t('app.kuaizhizao.shipmentNotice.withdrawNotify'),
                batch: t('app.kuaizhizao.shipmentNotice.batchWithdrawNotify'),
              }}
              icon={<AppstoreAddOutlined />}
              size="medium"
              color="orange"
              variant="solid"
            />,
          ]}
          rightToolBarActionsBeforeExport={[
            <UniCapabilityBatchButton
              key="shipment-notice-print"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedNoticesForBatch}
              capabilityKey="print"
              permAllowed={shipmentNoticePerms.canPrint}
              batchAllowed={(records, perm) =>
                Boolean(perm) && records.some((record) => record.capabilities?.print?.allowed === true)
              }
              singleOnly
              onRun={async (id) => {
                openPrint({ documentType: 'shipment_notice', documentId: id });
              }}
              labels={{
                single: t('components.uniAction.print'),
                batch: t('components.uniAction.print'),
              }}
              icon={<PrinterOutlined />}
              size="medium"
            />,
          ]}
          importHeaders={noticeItemImportTemplate.importHeaders}
          importExampleRow={noticeItemImportTemplate.importExampleRow}
          importColumnOptions={noticeItemImportTemplate.importColumnOptions}
          importFieldMap={noticeItemImportTemplate.importHeaderMap}
          onImport={handleListToolbarImport}
          showExportButton
          onExport={async (type, keys, pageData) => {
            try {
              let items: ShipmentNotice[] =
                type === 'currentPage' && pageData?.length
                  ? (pageData as ShipmentNotice[])
                  : await fetchAllListItems((p) => shipmentNoticeApi.list(p));
              if (type === 'selected' && keys?.length) {
                items = items.filter((d: ShipmentNotice) => d.id != null && keys.includes(d.id));
              }
              if (items.length === 0) {
                messageApi.warning(t('common.exportNoData'));
                return;
              }
              await downloadRecordsAsXlsx(
                items as Array<Record<string, unknown>>,
                `shipment-notices-${todaySiteDateString()}.xlsx`,
              );
              messageApi.success(t('common.exportCountSuccess', { count: items.length }));
            } catch (error: any) {
              messageApi.error(error?.message || t('common.exportFailed'));
            }
          }}
          request={async (params, sort, _filter, searchFormValues) => {
            try {
              const apiParams = resolveShipmentNoticeListApiParams(
                params,
                sort,
                searchFormValues,
              ) as ShipmentNoticeListParams;
              const response = await shipmentNoticeApi.list(apiParams);
              const rawNotices = response?.data ?? [];
              const notices = await enrichShipmentNoticeRecordsWithCustomFields(rawNotices);
              const total = response?.total ?? notices.length;
              // 行缓存唯一真源：onTableDataChange（prefetch 会走本 request，禁止在此覆盖）
              if (dataViewModeRef.current === 'order') {
                return { data: notices, success: true, total };
              }
              const flatRows = flattenDocumentDetailRows<ShipmentNotice, ShipmentNoticeItem>({
                headers: notices,
                getHeaderId: (h) => h.id,
                getItems: (h) => h.items,
                buildRowKey: (h, item, index) =>
                  item?.id ? `sn-${h.id}-item-${item.id}` : `sn-${h.id}-idx-${index}`,
                mapItemRow: (h, item) => ({
                  ...item,
                  notice_id: h.id ?? 0,
                  notice_code: h.notice_code,
                  customer_name: h.customer_name,
                  sales_order_code: h.sales_order_code,
                  warehouse_name: h.warehouse_name,
                  planned_ship_date: h.planned_ship_date,
                  notified_at: h.notified_at,
                  status: h.status,
                  sales_delivery_id: h.sales_delivery_id,
                  sales_delivery_code: h.sales_delivery_code,
                  lifecycle: h.lifecycle,
                }),
                mapEmptyHeaderRow: (h) => ({
                  notice_id: h.id ?? 0,
                  notice_code: h.notice_code,
                  customer_name: h.customer_name,
                  material_code: '-',
                  material_name: '-',
                  material_unit: '',
                  notice_quantity: 0,
                  status: h.status,
                  sales_delivery_id: h.sales_delivery_id,
                  sales_delivery_code: h.sales_delivery_code,
                  lifecycle: h.lifecycle,
                  planned_ship_date: h.planned_ship_date,
                  notified_at: h.notified_at,
                }),
              }) as ShipmentNoticeItemRow[];
              return { data: flatRows, success: true, total };
            } catch {
              messageApi.error(t('app.kuaizhizao.shipmentNotice.listFailed'));
              return { data: [], success: false, total: 0 };
            }
          }}
        />
      </ListPageTemplate>

      <UniPullQueryModal<PullSalesOrderCandidate>
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
        isRowDisabled={pullFromSalesOrderQuery.isRowDisabled}
        searchDraft={pullFromSalesOrderQuery.searchDraft}
        onSearchDraftChange={pullFromSalesOrderQuery.setSearchDraft}
        onSearchApply={pullFromSalesOrderQuery.handleSearchApply}
        onSearchClear={pullFromSalesOrderQuery.handleSearchClear}
        appliedKeyword={pullFromSalesOrderQuery.appliedKeyword}
        searchPlaceholder={t('app.kuaizhizao.shipmentNotice.pull.searchPlaceholder')}
        filterExtra={(
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaizhizao.shipmentNotice.pull.sourceDocPlaceholder')}
            style={{ width: 220, flexShrink: 0 }}
            value={pullSourceOrderId}
            options={pullSourceOrderOptions}
            onChange={(value) => {
              const nextId = Number(value);
              const next = Number.isFinite(nextId) && nextId > 0 ? nextId : undefined;
              pullSourceOrderIdRef.current = next;
              setPullSourceOrderId(next);
              pullFromSalesOrderQuery.handleSelectedRowKeysChange([], []);
              pullFromSalesOrderQuery.handleSearchApply(pullFromSalesOrderQuery.appliedKeyword);
            }}
          />
        )}
        getRowLabel={(row) =>
          [row.order_code, row.material_code].filter(Boolean).join(' ')
        }
        page={pullFromSalesOrderQuery.page}
        pageSize={pullFromSalesOrderQuery.pageSize}
        total={pullFromSalesOrderQuery.total}
        onPageChange={pullFromSalesOrderQuery.handlePageChange}
        scopeOptions={pullFromSalesOrderQuery.scopeOptions}
        scope={pullFromSalesOrderQuery.scope}
        onScopeChange={pullFromSalesOrderQuery.handleScopeChange}
        okText={t('app.kuaizhizao.shipmentNotice.pull.ok')}
      />

      <DetailDrawerTemplate
        title={`${t('app.kuaizhizao.shipmentNotice.detailTitle')}${noticeDetail?.notice_code ? ` - ${noticeDetail.notice_code}` : ''}`}
        open={detailDrawerVisible}
        zIndex={noticeDetailDrawerZIndex}
        onClose={() => {
          setDetailDrawerVisible(false);
          setNoticeDetail(null);
          resetShipmentNoticeDetailFieldValues();
        }}
        size={DRAWER_CONFIG.HALF_WIDTH}
        extra={
          noticeDetail?.id != null ? (
            <Space size="small">
              {noticeDetail.capabilities?.notify?.allowed && shipmentNoticePerms.canUpdate ? (
                <Button
                  {...rowActionKind('dispatch')}
                  icon={<SendOutlined />}
                  onClick={() => handleNotify(noticeDetail)}
                >
                  {t('app.kuaizhizao.shipmentNotice.notifyWarehouse')}
                </Button>
              ) : null}
              {noticeDetail.capabilities?.withdraw?.allowed && shipmentNoticePerms.canAction?.('revoke') ? (
                <Button {...rowActionKind('revoke')} onClick={() => handleWithdraw(noticeDetail)}>
                  {t('app.kuaizhizao.shipmentNotice.withdrawNotify')}
                </Button>
              ) : null}
              <UniWorkflowActions {...rowActionKind('skip')}
                record={noticeDetail}
                entityName={shipmentNoticeEntityName}
                entityType="shipment_notice"
                auditNodeKey="shipment_notice"
                unifiedAudit
                resourcePrefix={SHIPMENT_NOTICE_RESOURCE}
                statusField="status"
                reviewStatusField="review_status"
                draftStatuses={['待发货']}
                pendingStatuses={['待审核']}
                approvedStatuses={['审核通过', '已通过', '已审核']}
                rejectedStatuses={['审核驳回', '已驳回']}
                onSuccess={async () => {
                  actionRef.current?.reload();
                  invalidateMenuBadgeCounts();
                  setTrackingRefreshKey((k) => k + 1);
                  if (noticeDetail?.id) {
                    const updated = await shipmentNoticeApi.get(String(noticeDetail.id));
                    setNoticeDetail(updated as ShipmentNoticeDetail);
                  }
                }}
              />
              {!(
                noticeDetail.capabilities?.print?.allowed === false ||
                !shipmentNoticePerms.canPrint
              ) ? (
                <Button
                  icon={<PrinterOutlined />}
                  onClick={() => openPrint({ documentType: 'shipment_notice', documentId: noticeDetail.id! })}
                >
                  {t('components.uniAction.print')}
                </Button>
              ) : null}
            </Space>
          ) : null
        }
        basic={
          noticeDetail ? (
            <>
              <Descriptions
                column={3}
                size="small"
                items={timeconfigBasicItems}
              />
              {hasCustomFieldsDetailContent(
                shipmentNoticeListCustomFields,
                shipmentNoticeDetailCustomFieldValues,
              ) ? (
                <div style={{ marginTop: 16 }}>
                  <CustomFieldsDetailSection
                    customFields={shipmentNoticeListCustomFields}
                    customFieldValues={shipmentNoticeDetailCustomFieldValues}
                  />
                </div>
              ) : null}
            </>
          ) : undefined
        }
        collaboration={
          noticeDetail
            ? (() => {
                const lc = getShipmentNoticeLifecycle(noticeDetail as Record<string, unknown>, t);
                const mainStages = lc.mainStages ?? [];
                if (mainStages.length === 0) return null;
                return (
                  <UniLifecycleStepper
                    steps={mainStages}
                    showLabels
                    status={lc.status}
                    nextStepSuggestions={lc.nextStepSuggestions}
                    hideNextStepSuggestions
                  />
                );
              })()
            : undefined
        }
        collaborationAuditRecord={noticeDetail}
        supplementaryTitle={
          noticeDetail?.id != null
            ? t('app.kuaizhizao.shipmentNotice.oqcSection')
            : hasDocumentAttachments(shipmentNoticeAttachments)
              ? shipmentNoticeAttLabel
              : undefined
        }
        supplementary={appendDocumentAttachmentsToSupplementary(
          shipmentNoticeOqcSupplementary,
          shipmentNoticeAttachments,
          shipmentNoticeAttLabel,
        )}
        lines={
          noticeDetail ? (
            noticeDetail.items && noticeDetail.items.length > 0 ? (
              <Table
                size="small"
                rowKey={(record: any) => record.id || record.material_code}
                columns={[
                  { title: t('app.kuaizhizao.salesOrder.materialCode'), dataIndex: 'material_code', width: 120 },
                  { title: t('app.kuaizhizao.salesOrder.materialName'), dataIndex: 'material_name', width: 150 },
                  { title: t('common.unit'), dataIndex: 'material_unit', width: 60 },
                  { title: t('common.quantity'), dataIndex: 'notice_quantity', width: 90, align: 'right', render: formatQuantity },
                  buildDocumentLineAuxQuantityDetailColumn({ t, width: 120 }),
                  {
                    title: t(
                      'app.kuaizhizao.salesOrder.unitPrice',
                      documentCurrencyTitleVars((noticeDetail as any)?.currency_code, t),
                    ),
                    dataIndex: 'unit_price',
                    width: 90,
                    align: 'right' as const,
                    render: (text: unknown) =>
                      `${resolveDocumentCurrencyInputPrefix((noticeDetail as any)?.currency_code)}${text ?? 0}`,
                  },
                  {
                    title: t('app.kuaizhizao.shipmentNotice.amount'),
                    dataIndex: 'total_amount',
                    width: 100,
                    align: 'right' as const,
                    render: (text: unknown) =>
                      `${resolveDocumentCurrencyInputPrefix((noticeDetail as any)?.currency_code)}${formatAmount(text ?? 0, '0.00')}`,
                  },
                ]}
                dataSource={noticeDetail.items}
                pagination={false}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.shipmentNotice.noDetailItems')} />
            )
          ) : undefined
        }
        timeline={
          noticeDetail ? (
            <>
              {shipmentTracking.loading && (
                <div style={{ textAlign: 'center', padding: 24 }}>
                  <Spin />
                </div>
              )}
              {shipmentTracking.error && !shipmentTracking.loading && (
                <Typography.Text type="danger">{shipmentTracking.error}</Typography.Text>
              )}
              {shipmentTracking.data && !shipmentTracking.loading && (
                <DocumentTrackingTimelineBody data={shipmentTracking.data} />
              )}
              {!shipmentTracking.loading && !shipmentTracking.data && !shipmentTracking.error && (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.shipmentNotice.noOperationRecords')} />
              )}
            </>
          ) : undefined
        }
        traceDocument={
          noticeDetail?.id != null
            ? {
                documentType: 'shipment_notice',
                documentId: noticeDetail.id,
                selfDocumentId: noticeDetail.id,
                renderBriefActions: (doc) => (
                  <WarehouseTraceBriefPrimaryActions
                    doc={doc}
                    t={t}
                    navigate={navigate}
                    closeDrawer={() => {
                      setDetailDrawerVisible(false);
                      setNoticeDetail(null);
                    }}
                  />
                ),
              }
            : undefined
        }
      />

      <Modal
        title={t('app.kuaizhizao.shipmentNotice.notifyWarehouse')}
        open={notifyPreviewOpen}
        width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
        onCancel={() => {
          if (notifyPreviewConfirming) return;
          resetNotifyPreviewModal();
        }}
        footer={(
          <Space>
            <Button
              onClick={resetNotifyPreviewModal}
              disabled={notifyPreviewConfirming}
            >
              {t('common.cancel')}
            </Button>
            <Button
              loading={notifyPreviewConfirming}
              disabled={
                notifyPreviewLoading || !notifyPreviewData || !notifyLinesReady || !!notifyPreviewData?.has_blocking_issues
              }
              onClick={() => void handleNotifyPreviewConfirm('draft')}
            >
              {t('components.layoutTemplates.documentFormPage.saveDraft')}
            </Button>
            <Button
              type="primary"
              loading={notifyPreviewConfirming}
              disabled={
                notifyPreviewLoading || !notifyPreviewData || !notifyLinesReady || !!notifyPreviewData?.has_blocking_issues
              }
              onClick={() => void handleNotifyPreviewConfirm('confirm')}
            >
              {t('app.kuaizhizao.warehouseOutbound.toolbar.submitReview')}
            </Button>
          </Space>
        )}
      >
        {notifyPreviewLoading ? (
          <div style={{ minHeight: 120, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
            <Spin />
            <div style={{ color: 'var(--ant-color-primary)' }}>{t('app.kuaizhizao.salesOrder.loadingPreview')}</div>
          </div>
        ) : notifyPreviewData ? (
          <div>
            <p style={{ marginBottom: 12, fontWeight: 500 }}>{notifyPreviewData.summary}</p>
            {notifyPreviewData.has_blocking_issues ? (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 12 }}
                title={
                  notifyPreviewData.line_blocking_issues &&
                  notifyPreviewData.line_blocking_issues.length > 0
                    ? t('app.kuaizhizao.shipmentNotice.notifyInventoryBlocked')
                    : shipmentNoticeCapabilityReasonMessage(notifyPreviewData.blocking_reason, t) ||
                      t('app.kuaizhizao.shipmentNotice.notifyPreviewBlocked')
                }
                description={
                  notifyPreviewData.line_blocking_issues &&
                  notifyPreviewData.line_blocking_issues.length > 0 ? (
                    <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                      {notifyPreviewData.line_blocking_issues.map((msg, idx) => (
                        <li key={`notify-block-${idx}`}>{msg}</li>
                      ))}
                    </ul>
                  ) : undefined
                }
              />
            ) : null}
            <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <Typography.Text type="secondary">
                {t('app.kuaizhizao.shipmentNotice.notifyLineWarehouseHint')}
              </Typography.Text>
              <UniWhDropdown
                hostResource={SHIPMENT_NOTICE_RESOURCE}
                value={notifyBatchWarehouseId}
                allowClear
                size={DOCUMENT_DETAIL_CONTROL_SIZE}
                style={{ width: 220 }}
                placeholder={t('app.kuaizhizao.warehouseOutbound.pull.batchWarehousePlaceholder')}
                getPopupContainer={getPopupContainerInModal}
                onChange={(val, wh) => {
                  if (val == null) {
                    setNotifyBatchWarehouseId(undefined);
                    return;
                  }
                  const nextId = Number(val);
                  if (Number.isFinite(nextId) && nextId > 0) {
                    applyNotifyBatchWarehouse(nextId, wh?.name);
                  }
                }}
              />
            </div>
            {notifyPreviewData.items?.length > 0 ? (
              <Table
                size="small"
                dataSource={notifyPreviewData.items}
                rowKey={(row) => String(row.item_id)}
                pagination={false}
                scroll={{ x: 1180 }}
                columns={[
                  { title: t('app.kuaizhizao.salesOrder.materialCode'), dataIndex: 'material_code', width: 120, ellipsis: true },
                  { title: t('app.kuaizhizao.salesOrder.materialName'), dataIndex: 'material_name', width: 140, ellipsis: true },
                  { title: t('common.quantity'), dataIndex: 'quantity', width: 80, align: 'right', render: formatQuantity },
                  { title: t('app.kuaizhizao.salesOrder.colShipQty'), dataIndex: 'notice_quantity', width: 90, align: 'right', render: formatQuantity },
                  { title: t('app.kuaizhizao.salesOrder.colShippedQty'), dataIndex: 'pushed_quantity', width: 80, align: 'right', render: formatQuantity },
                  { title: t('app.kuaizhizao.salesOrder.colShippableQty'), dataIndex: 'max_push_quantity', width: 90, align: 'right', render: formatQuantity },
                  {
                    title: t('app.kuaizhizao.warehouseOutbound.col.warehouse'),
                    key: 'warehouse',
                    width: 200,
                    render: (_: unknown, row) => {
                      const id = Number(row.item_id);
                      const materialId = Number(row.material_id || 0);
                      const state = notifyLineWh[id] || {};
                      return (
                        <UniWhDropdown
                          hostResource={SHIPMENT_NOTICE_RESOURCE}
                          materialId={materialId > 0 ? materialId : undefined}
                          showStock={materialId > 0}
                          sortByStock={materialId > 0}
                          value={state.warehouse_id}
                          size={DOCUMENT_DETAIL_CONTROL_SIZE}
                          placeholder={t('app.kuaizhizao.warehouseOutbound.msg.selectWarehouse')}
                          getPopupContainer={getPopupContainerInModal}
                          onChange={(val, wh) => {
                            const nextId = Number(val);
                            if (!(Number.isFinite(nextId) && nextId > 0)) return;
                            patchNotifyLineWh(id, {
                              warehouse_id: nextId,
                              warehouse_name: wh?.name || '',
                              location_id: undefined,
                              location_code: undefined,
                            });
                          }}
                        />
                      );
                    },
                  },
                  {
                    title: t('app.kuaizhizao.warehouseOutbound.col.location'),
                    key: 'location',
                    width: 180,
                    render: (_: unknown, row) => {
                      const id = Number(row.item_id);
                      const materialId = Number(row.material_id || 0);
                      const state = notifyLineWh[id] || {};
                      return (
                        <NotifyPreviewLocationCell
                          materialId={materialId > 0 ? materialId : undefined}
                          warehouseId={state.warehouse_id}
                          locationId={state.location_id}
                          disabled={notifyPreviewConfirming}
                          t={t}
                          onChange={(next) => {
                            patchNotifyLineWh(id, next);
                          }}
                        />
                      );
                    },
                  },
                ]}
              />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.shipmentNotice.notifyPreviewNoLines')} />
            )}
            {notifyPreviewData.tip ? (
              <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
                {notifyPreviewData.tip}
              </Typography.Paragraph>
            ) : null}
          </div>
        ) : null}
      </Modal>

      {PrintModal}
    </>
  );
};

export default ShipmentNoticesPage;
