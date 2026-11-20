/**
 * 销售变更单
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { rowActionKind } from '../../../../../components/uni-action';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { ActionType, ProColumns, ProDescriptionsItemProps, ProForm, ProFormTextArea } from '@ant-design/pro-components';
import { App, Button, Descriptions, Form, Space, Spin, Typography } from 'antd';
import { ArrowLeftOutlined, CheckOutlined, DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined, PrinterOutlined, RollbackOutlined, SendOutlined, ThunderboltOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { UniTable } from '../../../../../components/uni-table';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { LinkedDocumentCode } from '../../../../../components/linked-document-code';
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
import { UniPullCreateToolbar } from '../../../../../components/uni-pull';
import { isPendingReviewStatus } from '../../../constants/documentStatus';
import {
  UniPullQueryModal,
  UNI_PULL_QUERY_MAX_FETCH_LIMIT,
  pagePullCandidates,
  renderPullQueryDocStatus,
  useUniPullQuery,
} from '../../../../../components/uni-pull-query';
import {
  UniTableStackedPrimaryCell,
} from '../../../../../components/uni-table/stackedPrimaryColumn';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import { MarkerTag } from '../../../../../constants/statusBadges';
import {
  ListPageTemplate,
  DetailDrawerTemplate,
  DRAWER_CONFIG,
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageHeaderActions,
  DocumentFormPageLayout,
  useDetailDrawerDescriptionItems,
} from '../../../../../components/layout-templates';
import { useLeaveFormTab } from '../../../../../components/uni-tabs/navigateClosingTab';
import { useSubmitShortcut } from '../../../../../hooks/useSubmitShortcut';
import { useDocumentFormCommitAndSubmitReview } from '../../../../../hooks/useDocumentFormCommitAndSubmitReview';
import { UniWorkflowActions } from '../../../../../components/uni-workflow-actions';
import { UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import { LIST_LIFECYCLE_STAGE_FIELD } from '../../../../../utils/listLifecycleStage';
import { useAuditRequired } from '../../../../../hooks/useAuditRequired';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import {
  useSalesOrderChangeCapabilities,
} from '../../../../../hooks/useDocumentCapabilities';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import {
  approveSalesOrderChange,
  createSalesOrderChangeFromOrder,
  deleteSalesOrderChange,
  getSalesOrderChange,
  listSalesOrderChanges,
  previewSalesOrderChangeImpact,
  revokeSalesOrderChange,
  submitSalesOrderChange,
  submitSalesOrderChangeForReview,
  updateSalesOrderChange,
  withdrawSalesOrderChange,
  type SalesOrderChange,
  type SalesOrderChangeListParams,
} from '../../../services/sales-order-change';
import { getSalesOrder, listSalesOrders, type SalesOrder } from '../../../services/sales-order';
import {
  KUAIZHIZAO_DOC_HOST,
  loadCustomerFormReferenceList,
} from '../../../../../utils/documentFormReferenceLoad';
import type { Customer } from '../../../../master-data/types/supply-chain';
import {
  buildOrderChangeLifecycleValueEnum,
  getOrderChangeLifecycle,
  resolveOrderChangeListApiParams,
} from '../../../utils/orderChangeLifecycle';
import { formatOrderChangeCategory, ORDER_CHANGE_CATEGORY_LABELS } from '../../../utils/orderChangeCategory';
import {
  OrderChangeItemsTable,
  type OrderChangeItemsTablePricing,
} from '../../../components/order-change/OrderChangeItemsTable';
import { OrderChangeImpactModal } from '../../../components/order-change/OrderChangeImpactModal';
import { isSourceOrderEligibleForChange } from '../../../utils/orderChangeSourceOrder';
import { ListUniLifecycleCell } from '../shared/ListUniLifecycleCell';
import { alignProColumns, alignDescriptionColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../shared/documentFieldAlignment';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../shared/documentLineMaterialsPreview';
import { createListAuditPhaseColumn } from '../shared/listAuditPhaseColumn';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import {
  DocumentAttachmentsReadonly,
  documentAttachmentsFromRecord,
  hasDocumentAttachments,
} from '../../../components/DocumentAttachmentsReadonly';
import { mapAttachmentsToUploadList, normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { useKuaizhizaoPrintModal } from '../../../hooks/useKuaizhizaoPrintModal';
import {
  resolveKuaizhizaoDocumentAction,
} from '../../../constants/documentActionRegistry';
import { formatAmount, formatDateTime, formatNumber } from '../../../../../utils/format';
import { extractProTableSort } from '../../../../../utils/tableQueryKey';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import {
  CustomFieldsFormSection,
  CustomFieldsDetailSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';

const SALES_ORDER_CHANGE_RESOURCE = 'kuaizhizao:sales-order-change';
const SALES_ORDER_CHANGE_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_sales_order_change_orders';
const SALES_ORDER_CHANGE_LIST_PATH = '/apps/kuaizhizao/sales-management/sales-order-changes';
const SALES_ORDER_CHANGE_CREATE_PATH = `${SALES_ORDER_CHANGE_LIST_PATH}/new`;
const salesOrderChangeEditPath = (id: number) => `${SALES_ORDER_CHANGE_LIST_PATH}/${id}/edit`;
type PullSalesOrderCandidate = {
  id: number;
  order_code: string;
  customer_name?: string;
  order_date?: string;
  delivery_date?: string;
  total_amount?: number;
  status?: string;
  review_status?: string;
  salesman_name?: string;
};

const isPullSalesOrderSelectable = (record: PullSalesOrderCandidate): boolean =>
  isSourceOrderEligibleForChange(record.status, record.review_status);

const SalesOrderChangesPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const location = useLocation();
  const isCreatePage = location.pathname.endsWith('/sales-order-changes/new');
  const editRouteMatch = location.pathname.match(/\/sales-order-changes\/(\d+)\/edit$/);
  const editRouteId = editRouteMatch ? Number(editRouteMatch[1]) : null;
  const isEditPage = editRouteId != null && Number.isFinite(editRouteId) && editRouteId > 0;
  const isFormPage = isCreatePage || isEditPage;
  const leaveSalesOrderChangeFormPage = useLeaveFormTab(SALES_ORDER_CHANGE_LIST_PATH);

  const {
    runAfterPersist: runSalesOrderChangeSaveAndAudit,
    initiatorModal: salesOrderChangeInitiatorModal,
  } = useDocumentFormCommitAndSubmitReview({
    entityType: 'sales_order_change',
    entityLabel: t('app.kuaizhizao.salesOrderChange.entityName'),
    commit: submitSalesOrderChange,
  });
  const formPageInitKeyRef = useRef<string | null>(null);
  const [formPageLoading, setFormPageLoading] = useState(false);
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const pullFromSalesOrderAction = resolveKuaizhizaoDocumentAction(
    t,
    'sales_order_change.pull_from_sales_order',
  );
  const [searchParams, setSearchParams] = useSearchParams();
  const actionRef = useRef<ActionType>();
  const invalidateMenuBadge = useInvalidateMenuBadgeCounts();
  const reloadTable = useCallback(() => {
    invalidateMenuBadge();
    actionRef.current?.reload();
  }, [invalidateMenuBadge]);
  const auditEnabled = useAuditRequired('kuaizhizao', 'sales-order-change');
  const changePerms = useResourcePermissions(SALES_ORDER_CHANGE_RESOURCE);
  const permDeniedTitle = t('common.noPermission');

  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<SalesOrderChange | null>(null);
  const detailCapabilityGates = useSalesOrderChangeCapabilities(detail, changePerms, t, permDeniedTitle);
  const [editForm] = Form.useForm();
  const [formSaving, setFormSaving] = useState(false);
  const [editItems, setEditItems] = useState<SalesOrderChange['items']>([]);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [creatingSourceOrderId, setCreatingSourceOrderId] = useState<number | null>(null);
  const commitAfterSaveRef = useRef(false);
  const [changePricing, setChangePricing] = useState<OrderChangeItemsTablePricing | undefined>();
  const [impactOpen, setImpactOpen] = useState(false);
  const [impactLoading, setImpactLoading] = useState(false);
  const [impactData, setImpactData] = useState<Awaited<ReturnType<typeof previewSalesOrderChangeImpact>> | null>(null);
  const [pendingSubmitId, setPendingSubmitId] = useState<number | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const tableRowsRef = useRef<SalesOrderChange[]>([]);
  const [customers, setCustomers] = useState<Customer[]>([]);

  const {
    customFields: changeFormCustomFields,
    customFieldValues: changeFormCustomFieldValues,
    loadFieldValues: loadChangeFormFieldValues,
    extractFormValues: extractChangeFormValues,
    saveCustomFieldValues: saveChangeCustomFieldValues,
    resetFieldValues: resetChangeFormFieldValues,
  } = useCustomFields({
    tableName: SALES_ORDER_CHANGE_CUSTOM_FIELD_TABLE,
    loadWhenOpen: true,
    open: isFormPage,
  });
  const {
    customFields: changeListCustomFields,
    generateCustomFieldColumns: generateChangeCustomFieldColumns,
    enrichRecordsWithCustomFields: enrichChangeRecordsWithCustomFields,
    customFieldValues: changeDetailCustomFieldValues,
    loadFieldValuesForDetail: loadChangeFieldValuesForDetail,
    resetDetailFieldValues: resetChangeDetailFieldValues,
  } = useCustomFieldsForList<SalesOrderChange>({
    tableName: SALES_ORDER_CHANGE_CUSTOM_FIELD_TABLE,
  });

  useEffect(() => {
    void loadCustomerFormReferenceList(KUAIZHIZAO_DOC_HOST.salesOrderChange).then(setCustomers);
  }, []);

  const changeCustomerSearchOptions = useMemo(
    () =>
      customers.map((c) => ({
        value: Number(c.id),
        label: String(c.name ?? c.code ?? ''),
      })),
    [customers],
  );

  const changeCategoryValueEnum = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(ORDER_CHANGE_CATEGORY_LABELS).map(([key, label]) => [key, { text: label }]),
      ),
    [],
  );

  const selectedChangesForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
        .filter((row): row is SalesOrderChange => row != null),
    [selectedRowKeys],
  );

  const openDetail = async (record: SalesOrderChange) => {
    const full = await getSalesOrderChange(record.id!);
    setDetail(full);
    setDetailOpen(true);
    if (full.id != null) {
      await loadChangeFieldValuesForDetail(full.id);
    }
  };

  const hydrateSalesOrderChangeEditForm = useCallback(
    async (full: SalesOrderChange) => {
      setEditingId(full.id!);
      setEditingStatus(full.status ?? null);
      setCreatingSourceOrderId(null);
      let pricingAsOf = full.created_at ? dayjs(full.created_at) : dayjs();
      if (full.source_order_id != null && Number(full.source_order_id) > 0) {
        try {
          const sourceOrder = await getSalesOrder(full.source_order_id, true, false, { view: 'options' });
          if (sourceOrder.order_date) {
            pricingAsOf = dayjs(sourceOrder.order_date);
          }
        } catch {
          /* 保留变更单创建时间 */
        }
      }
      setChangePricing({
        side: 'sales',
        partnerId:
          full.customer_id != null && Number.isFinite(Number(full.customer_id))
            ? Number(full.customer_id)
            : undefined,
        asOf: pricingAsOf,
      });
      setEditItems(full.items ?? []);
      editForm.setFieldsValue({
        change_reason: full.change_reason,
        notes: full.notes,
        attachments: mapAttachmentsToUploadList(full.attachments),
      });
      const fieldFormValues = await loadChangeFormFieldValues(full.id!);
      editForm.setFieldsValue(fieldFormValues);
    },
    [editForm, loadChangeFormFieldValues],
  );

  const openEdit = (record: SalesOrderChange) => {
    if (record.id) navigate(salesOrderChangeEditPath(record.id));
  };

  const handleSaveEdit = async () => {
    setFormSaving(true);
    let values: Record<string, unknown>;
    try {
      values = await editForm.validateFields();
    } catch {
      setFormSaving(false);
      return;
    }
    const { customData, standardValues } = extractChangeFormValues(values, editForm);
    const payload = {
      change_reason: standardValues.change_reason,
      notes: standardValues.notes,
      attachments: normalizeDocumentAttachments(standardValues.attachments),
      items: (editItems ?? []).map((item, idx) => ({
        id: item.id,
        line_no: item.line_no ?? idx + 1,
        source_item_id: item.source_item_id,
        change_type: item.change_type ?? 'QUANTITY',
        material_id: item.material_id,
        material_code: item.material_code,
        material_name: item.material_name,
        material_spec: item.material_spec,
        material_unit: item.material_unit,
        before_quantity: item.before_quantity,
        after_quantity: item.after_quantity,
        before_unit_price: item.before_unit_price,
        after_unit_price: item.after_unit_price,
        before_delivery_date: item.before_delivery_date,
        after_delivery_date: item.after_delivery_date,
        notes: item.notes,
      })),
    };
    const shouldCommit = commitAfterSaveRef.current;
    commitAfterSaveRef.current = false;
    let changeId: number;
    let updateRes: SalesOrderChange;
    if (editingId) {
      updateRes = await updateSalesOrderChange(editingId, payload);
      changeId = editingId;
    } else {
      if (!creatingSourceOrderId) {
        message.error(t('app.kuaizhizao.salesOrderChange.selectSalesOrder'));
        setFormSaving(false);
        return;
      }
      const created = await createSalesOrderChangeFromOrder(
        creatingSourceOrderId,
        standardValues.change_reason || t('app.kuaizhizao.salesOrderChange.defaultReason'),
      );
      updateRes = await updateSalesOrderChange(created.id!, payload);
      changeId = created.id!;
      setEditingId(changeId);
      setEditingStatus(updateRes.status ?? 'DRAFT');
    }

    try {
      await saveChangeCustomFieldValues(changeId, customData);
    } catch {
      message.error(t('app.kuaizhizao.quality.common.messages.inspectCustomFieldsSaveFailed'));
    }

    reloadTable();
    if (shouldCommit) {
      setCreatingSourceOrderId(null);
      resetChangeFormFieldValues();
      setFormSaving(false);
      await runSubmitWithPreview(changeId);
      return;
    }
    if (editingId) {
      message.success(t('common.updateSuccess'));
    } else {
      message.success(t('app.kuaizhizao.salesOrderChange.created', { code: updateRes.change_code }));
    }
    setCreatingSourceOrderId(null);
    resetChangeFormFieldValues();
    setFormSaving(false);
    leaveSalesOrderChangeFormPage();
  };

  const initCreateFromSourceOrder = useCallback(async (orderId: number, reason: string) => {
    const order = await getSalesOrder(orderId, true, false, { view: 'options' });
    setEditingId(null);
    setEditingStatus('DRAFT');
    setCreatingSourceOrderId(orderId);
    setChangePricing({
      side: 'sales',
      partnerId:
        order.customer_id != null && Number.isFinite(Number(order.customer_id))
          ? Number(order.customer_id)
          : undefined,
      asOf: order.order_date ? dayjs(order.order_date) : dayjs(),
    });
    setEditItems(
      (order.items ?? []).map((item, idx) => ({
        line_no: idx + 1,
        source_item_id: item.id,
        change_type: 'QUANTITY',
        material_id: item.material_id,
        material_code: item.material_code,
        material_name: item.material_name,
        material_spec: item.material_spec,
        material_unit: item.material_unit,
        before_quantity: item.required_quantity,
        after_quantity: item.required_quantity,
        before_unit_price: item.unit_price,
        after_unit_price: item.unit_price,
        before_delivery_date: item.delivery_date,
        after_delivery_date: item.delivery_date,
        notes: item.notes,
      })),
    );
    editForm.setFieldsValue({
      change_reason: reason || t('app.kuaizhizao.salesOrderChange.defaultReason'),
      notes: '',
      attachments: [],
    });
    resetChangeFormFieldValues();
  }, [editForm, resetChangeFormFieldValues, t]);

  const mapPullSalesOrderRows = useCallback((rows: SalesOrder[]): PullSalesOrderCandidate[] => {
    return rows
      .filter((order) => order.id && order.order_code)
      .map((order) => ({
        id: Number(order.id),
        order_code: String(order.order_code),
        customer_name: order.customer_name || '',
        order_date: order.order_date || '',
        delivery_date: order.delivery_date || '',
        total_amount: order.total_amount != null ? Number(order.total_amount) : undefined,
        status: order.status || '',
        review_status: order.review_status || '',
        salesman_name: order.salesman_name || '',
      }));
  }, []);

  const pullFromSalesOrderScopeOptions = useMemo(
    () => [
      { label: t('components.uniPullQuery.scopePullable'), value: 'pullable' },
      { label: t('components.uniPullQuery.scopeAll'), value: 'all' },
    ],
    [t],
  );

  const pullFromSalesOrderQuery = useUniPullQuery<PullSalesOrderCandidate>({
    rowKey: 'id',
    selectionType: 'checkbox',
    scopeOptions: pullFromSalesOrderScopeOptions,
    defaultScope: 'pullable',
    isRowDisabled: (record) => !isPullSalesOrderSelectable(record),
    loadData: async ({ keyword, page, pageSize, scope }) => {
      try {
        const result = await listSalesOrders({
          skip: 0,
          limit: UNI_PULL_QUERY_MAX_FETCH_LIMIT,
          keyword: keyword.trim() || undefined,
          include_items: false,
          view: 'options',
        });
        const rows = mapPullSalesOrderRows(result.data || []);
        return pagePullCandidates(rows, scope, page, pageSize, isPullSalesOrderSelectable);
      } catch (error: any) {
        message.error(error?.message ?? t('app.kuaizhizao.orderChange.loadSalesOrdersFailed'));
        return { data: [], total: 0 };
      }
    },
    onConfirm: async (keys, rows) => {
      const selectedIds = rows
        .filter((row) => isPullSalesOrderSelectable(row))
        .map((row) => Number(row.id))
        .filter((id) => id > 0);
      if (!selectedIds.length) {
        message.warning(t('app.kuaizhizao.salesOrderChange.selectSalesOrder'));
        return;
      }
      pullFromSalesOrderQuery.closeModal();
      // 变更单按源销售订单整单创建；多选时逐张打开第一张，其余可再取
      navigate(`${SALES_ORDER_CHANGE_CREATE_PATH}?source_order_id=${selectedIds[0]}`);
      if (selectedIds.length > 1) {
        message.info(t('app.kuaizhizao.salesOrderChange.pull.multiSelectedFirstOnly'));
      }
    },
  });

  const pullSalesOrderColumns: ProColumns<PullSalesOrderCandidate>[] = useMemo(
    () => [
      { title: t('app.kuaizhizao.orderChange.colOrderCode'), dataIndex: 'order_code', width: 160 },
      {
        title: t('path.customers'),
        dataIndex: 'customer_name',
        ellipsis: true,
        render: (value: string) => value || '-',
      },
      {
        title: t('app.kuaizhizao.salesOrder.orderDate'),
        dataIndex: 'order_date',
        width: 120,
        render: (value: string) => (value ? formatDateTime(value, 'YYYY-MM-DD') : '-'),
      },
      {
        title: t('app.kuaizhizao.salesOrder.deliveryDate'),
        dataIndex: 'delivery_date',
        width: 120,
        render: (value: string) => (value ? formatDateTime(value, 'YYYY-MM-DD') : '-'),
      },
      {
        title: t('app.kuaizhizao.orderChange.colAmount'),
        dataIndex: 'total_amount',
        width: 120,
        align: 'right',
        render: (value: number | undefined) =>
          value != null
            ? formatAmount(value)
            : '-',
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 100,
        align: 'center' as const,
        render: (v) => renderPullQueryDocStatus(t, v),
      },
    ],
    [t],
  );

  const openCreate = useCallback(() => {
    pullFromSalesOrderQuery.openModal();
  }, [pullFromSalesOrderQuery]);
  useNewShortcut(openCreate);

  useEffect(() => {
    if (!isFormPage) {
      formPageInitKeyRef.current = null;
      return;
    }
    const initKey = isCreatePage
      ? `create:${location.search}`
      : `edit:${editRouteId}`;
    if (formPageInitKeyRef.current === initKey) return;
    formPageInitKeyRef.current = initKey;

    if (isCreatePage) {
      const sourceId = searchParams.get('source_order_id');
      if (!sourceId) {
        leaveSalesOrderChangeFormPage();
        return;
      }
      setFormPageLoading(true);
      void initCreateFromSourceOrder(
        Number(sourceId),
        t('app.kuaizhizao.salesOrderChange.defaultReason'),
      )
        .catch((error: unknown) => {
          message.error(error instanceof Error ? error.message : t('common.loadFailed'));
          leaveSalesOrderChangeFormPage();
        })
        .finally(() => {
          searchParams.delete('source_order_id');
          setSearchParams(searchParams, { replace: true });
          setFormPageLoading(false);
        });
      return;
    }

    if (!editRouteId) return;
    setFormPageLoading(true);
    void getSalesOrderChange(editRouteId)
      .then((full) => hydrateSalesOrderChangeEditForm(full))
      .catch((error: unknown) => {
        message.error(error instanceof Error ? error.message : t('common.loadFailed'));
        leaveSalesOrderChangeFormPage();
      })
      .finally(() => setFormPageLoading(false));
  }, [
    editRouteId,
    hydrateSalesOrderChangeEditForm,
    initCreateFromSourceOrder,
    isCreatePage,
    isFormPage,
    leaveSalesOrderChangeFormPage,
    location.search,
    message,
    searchParams,
    setSearchParams,
    t,
  ]);

  const runSubmitWithPreview = async (id: number) => {
    setPendingSubmitId(id);
    setImpactLoading(true);
    setImpactOpen(true);
    try {
      const impact = await previewSalesOrderChangeImpact(id);
      setImpactData(impact);
    } catch (e: any) {
      message.error(e?.message ?? t('app.kuaizhizao.salesOrderChange.impactPreviewFailed'));
      setImpactOpen(false);
    } finally {
      setImpactLoading(false);
    }
  };

  const confirmSubmit = async () => {
    const id = pendingSubmitId;
    if (!id) return;
    try {
      const { completed } = await runSalesOrderChangeSaveAndAudit(id);
      if (!completed) {
        return;
      }
    } catch (error: unknown) {
      message.error(getApiErrorMessage(error, t('common.operationFailed')));
      return;
    }
    setImpactOpen(false);
    setPendingSubmitId(null);
    reloadTable();
    leaveSalesOrderChangeFormPage();
    if (detail?.id === id) {
      setDetail(await getSalesOrderChange(id));
    }
  };

  const changeAuditBatchHandlers = useMemo(
    () => ({
      submit: submitSalesOrderChange,
      withdraw: withdrawSalesOrderChange,
      approve: (id: number) => approveSalesOrderChange(id, true),
      revoke: (id: number) => revokeSalesOrderChange(id),
    }),
    [],
  );

  const handleChangeAuditBatchSuccess = useCallback(() => {
    setSelectedRowKeys([]);
    reloadTable();
  }, [reloadTable]);

  const {
    runAction: runSalesOrderChangeAuditBatch,
    auditModal: salesOrderChangeAuditModal,
  } = useAuditBatchRunner<SalesOrderChange>({
    permGates: changePerms,
    handlers: changeAuditBatchHandlers,
    onBatchComplete: handleChangeAuditBatchSuccess,
    auditEntity: {
      entityType: 'sales_order_change',
      entityName: t('app.kuaizhizao.salesOrderChange.entityName'),
    },
  });

  const selectedChangeForToolbar = useMemo(() => {
    if (selectedRowKeys.length !== 1) return null;
    return selectedChangesForBatch[0] ?? null;
  }, [selectedChangesForBatch, selectedRowKeys.length]);

  const salesOrderChangeToolbarAuditMenus = useMemo(() => {
    const canPerm = (action: AuditBatchAction) => {
      const perm = action === 'approve' ? 'audit' : action === 'submit' ? 'submit' : 'revoke';
      return changePerms.canAction?.(perm) ?? false;
    };
    const item = (
      key: string,
      action: AuditBatchAction,
      label: string,
      capKey: string,
      rows: SalesOrderChange[],
    ): UniBatchMenuItem => ({
      key,
      label,
      disabled:
        selectedChangesForBatch.length > 0
        && !defaultAuditBatchAllowed(rows, canPerm(action), capKey, (row) => row),
      onClick: (keys) => {
        const idSet = new Set(rows.map((row) => String(row.id)));
        return runSalesOrderChangeAuditBatch(
          action,
          keys.filter((rowKey) => idSet.has(String(rowKey))),
          rows,
          auditEnabled,
        );
      },
    });
    const capOn = (row: SalesOrderChange, capKey: string) => pickCapability(row, capKey)?.allowed === true;
    const submittedRows = selectedChangesForBatch.filter(
      (row) => String(row.status || '').trim() === 'SUBMITTED' && capOn(row, 'withdraw_submit'),
    );
    const pendingRows = selectedChangesForBatch.filter((row) => {
      const status = String(row.status || '').trim();
      return status !== 'SUBMITTED' && isPendingReviewStatus(status) && capOn(row, 'withdraw_submit');
    });
    const submitReviewRows = selectedChangesForBatch.filter((row) =>
      (row.audit?.allowed_actions ?? []).includes('submit_review'),
    );
    const canSubmitReview = changePerms.canAction?.('submit') ?? false;
    const submitRows = selectedChangesForBatch.filter((row) => capOn(row, 'submit'));
    const submitDisabled =
      selectedChangesForBatch.length > 0 && (!canPerm('submit') || submitRows.length === 0);
    return {
      submit: withDocumentSubmitCombinedItem(
        [
          {
            key: 'submit',
            label: t('common.submit'),
            disabled: submitDisabled,
            onClick: (keys: React.Key[]) => {
              if (keys.length === 1) {
                void runSubmitWithPreview(Number(keys[0]));
                return Promise.resolve();
              }
              return runSalesOrderChangeAuditBatch('submit', keys, submitRows, auditEnabled);
            },
          },
          item('withdraw-submit', 'withdraw', t('app.kuaizhizao.salesOrderChange.toolbar.withdrawSubmit'), 'withdraw_submit', submittedRows),
          {
            key: 'submit-review',
            label: t('app.kuaizhizao.salesOrderChange.toolbar.submitReview'),
            disabled: selectedChangesForBatch.length > 0 && !(canSubmitReview && submitReviewRows.length > 0),
            onClick: (keys: React.Key[]) => runCapabilityBatchLoop({
              keys,
              records: submitReviewRows,
              capabilityKey: 'submit_review',
              permAllowed: canSubmitReview,
              notAllowedMessage: t('app.kuaizhizao.salesOrderChange.toolbar.submitReviewNotAllowed'),
              onRun: (id) => submitSalesOrderChangeForReview(id),
              message,
              t,
              onSuccess: handleChangeAuditBatchSuccess,
            }),
          },
        ],
        {
          t,
          message,
          disabled: submitDisabled,
          commitRecords: submitRows,
          permAllowed: canSubmitReview,
          commit: (id) => submitSalesOrderChange(id),
          submitReview: (id) => submitSalesOrderChangeForReview(id),
          onSuccess: handleChangeAuditBatchSuccess,
        },
      ),
      audit: [
        item('approve', 'approve', t('components.uniAction.audit'), 'approve', selectedChangesForBatch.filter((row) => capOn(row, 'approve'))),
        item('withdraw-review', 'withdraw', t('app.kuaizhizao.salesOrderChange.toolbar.withdrawReview'), 'withdraw_submit', pendingRows),
        item('revoke', 'revoke', t('app.kuaizhizao.salesOrderChange.toolbar.revoke'), 'revoke_approval', selectedChangesForBatch.filter((row) => capOn(row, 'revoke_approval'))),
      ] satisfies UniBatchMenuItem[],
    };
  }, [
    auditEnabled,
    changePerms,
    handleChangeAuditBatchSuccess,
    message,
    runSalesOrderChangeAuditBatch,
    selectedChangesForBatch,
    t,
  ]);

  async function handleCopySelectedSalesOrderChange() {
    const row = selectedChangeForToolbar;
    if (!row?.id) {
      message.warning(t('app.kuaizhizao.salesOrderChange.selectToCopy'));
      return;
    }
    try {
      const full = await getSalesOrderChange(row.id);
      if (!full.source_order_id) {
        message.warning(t('app.kuaizhizao.salesOrderChange.selectToCopy'));
        return;
      }
      const created = await createSalesOrderChangeFromOrder(
        full.source_order_id,
        full.change_reason || t('app.kuaizhizao.salesOrderChange.defaultReason'),
      );
      await updateSalesOrderChange(created.id!, {
        change_reason: full.change_reason,
        notes: full.notes,
        attachments: full.attachments,
        items: (full.items ?? []).map((item, idx) => ({
          line_no: item.line_no ?? idx + 1,
          source_item_id: item.source_item_id,
          change_type: item.change_type ?? 'QUANTITY',
          material_id: item.material_id,
          material_code: item.material_code,
          material_name: item.material_name,
          material_spec: item.material_spec,
          material_unit: item.material_unit,
          before_quantity: item.before_quantity,
          after_quantity: item.after_quantity,
          before_unit_price: item.before_unit_price,
          after_unit_price: item.after_unit_price,
          before_delivery_date: item.before_delivery_date,
          after_delivery_date: item.after_delivery_date,
          notes: item.notes,
        })),
      });
      navigate(salesOrderChangeEditPath(created.id!));
      reloadTable();
    } catch (error: unknown) {
      message.error(
        error instanceof Error
          ? error.message
          : t('app.kuaizhizao.salesOrderChange.copyFailed'),
      );
    }
  }

  const salesOrderChangeCanCommit = ['', 'DRAFT', '草稿', 'draft', 'REJECTED', '已驳回', 'rejected'].includes(
    String(editingStatus ?? '').trim(),
  );

  const orderChangeLifecycleValueEnum = useMemo(
    () => buildOrderChangeLifecycleValueEnum(t),
    [t],
  );
  const orderChangeAuditColumn = useMemo(
    () => createListAuditPhaseColumn<SalesOrderChange>({ t, auditEnabled }),
    [t, auditEnabled],
  );
  const renderDeltaAmount = useCallback((value: unknown) => {
    if (value == null) return '-';
    const amount = Number(value);
    if (!Number.isFinite(amount)) return '-';
    const text = `${amount > 0 ? '+' : ''}${formatNumber(amount, 2)}`;
    const color = amount > 0 ? '#52c41a' : amount < 0 ? '#ff4d4f' : undefined;
    return <span style={{ color }}>{text}</span>;
  }, []);

  const detailBasicColumns = useMemo<ProDescriptionsItemProps<SalesOrderChange>[]>(
    () =>
      alignDescriptionColumns([
      {
        title: t('app.kuaizhizao.salesOrderChange.colChangeCode'),
        dataIndex: 'change_code',
      },
      {
        title: t('app.kuaizhizao.salesOrderChange.colSourceOrderCode'),
        dataIndex: 'source_order_code',
        key: 'sales_order_code',
      },
      {
        title: t('app.kuaizhizao.customerFollowUp.colCustomer'),
        dataIndex: 'customer_name',
      },
      {
        title: t('app.kuaizhizao.salesOrderChange.colCategory'),
        dataIndex: 'change_category',
        render: (_, record) => formatOrderChangeCategory(record.change_category),
      },
      {
        title: t('app.kuaizhizao.salesOrderChange.colVersion'),
        dataIndex: 'change_version',
        render: (_, record) => (record.change_version != null ? `V${record.change_version}` : '-'),
      },
      {
        title: t('app.kuaizhizao.salesOrderChange.colBeforeAmount'),
        dataIndex: 'before_total_amount',
        render: (_, record) => formatNumber(record.before_total_amount, 2),
      },
      {
        title: t('app.kuaizhizao.salesOrderChange.colAfterAmount'),
        dataIndex: 'after_total_amount',
        render: (_, record) => formatNumber(record.after_total_amount, 2),
      },
      {
        title: t('app.kuaizhizao.salesOrderChange.colDeltaAmount'),
        dataIndex: 'delta_amount',
        render: (_, record) => renderDeltaAmount(record.delta_amount),
      },
      {
        title: t('app.kuaizhizao.salesOrderChange.colAppliedAt'),
        dataIndex: 'applied_at',
        valueType: 'dateTime',
      },
      {
        title: t('app.kuaizhizao.salesOrderChange.colChangeReason'),
        dataIndex: 'change_reason',
        span: 3,
      },
      {
        title: t('common.remark'),
        dataIndex: 'notes',
        span: 3,
      },
    ] as ProDescriptionsItemProps<SalesOrderChange>[]),
    [renderDeltaAmount, t],
  );

  const detailCollaboration = useMemo(() => {
    if (!detail) return undefined;
    const lc = getOrderChangeLifecycle(detail as Record<string, unknown>, t);
    const mainStages = lc.mainStages ?? [];
    if (!mainStages.length) return undefined;
    return (
      <UniLifecycleStepper
        steps={mainStages}
        status={lc.status}
        showLabels
        nextStepSuggestions={lc.nextStepSuggestions}
        hideNextStepSuggestions
      />
    );
  }, [detail, t]);

  const columns: ProColumns<SalesOrderChange>[] = useMemo(
    () => alignProColumns<SalesOrderChange>([
    {
      title: t('app.kuaizhizao.salesOrderChange.colCustomerChangeCode'),
      key: 'change_code',
      dataIndex: 'change_code',
      width: 240,
      minWidth: 240,
      uniTableKeepWidth: true,
      uniTablePrimaryFlex: false,
      resizable: false,
      fixed: 'left',
      sorter: true,
      fieldProps: { placeholder: t('app.kuaizhizao.salesOrderChange.colChangeCode') },
      render: (_, record) => (
        <UniTableStackedPrimaryCell
          primary={String(record.customer_name ?? '')}
          secondary={String(record.change_code ?? '')}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.customerFollowUp.colCustomer'),
      dataIndex: 'customer_id',
      hideInTable: true,
      valueType: 'select',
      fieldProps: {
        showSearch: true,
        optionFilterProp: 'label',
        options: changeCustomerSearchOptions,
        placeholder: t('app.kuaizhizao.customerFollowUp.colCustomer'),
      },
    },
    {
      title: t('app.kuaizhizao.salesOrderChange.colSourceOrder'),
      dataIndex: 'source_order_code',
      width: 180,
      minWidth: 180,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: false,
      sorter: true,
      fieldProps: { placeholder: t('app.kuaizhizao.salesOrderChange.colSourceOrder') },
      render: (_, record) => (
        <LinkedDocumentCode
          documentType="sales_order"
          documentId={record.source_order_id}
          code={record.source_order_code}
        />
      ),
    },
    {
      title: t('app.kuaizhizao.salesOrderChange.colCategory'),
      dataIndex: 'change_category',
      ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
      sorter: true,
      valueType: 'select',
      valueEnum: changeCategoryValueEnum,
      render: (_, r) => (
        <MarkerTag color="processing">
          {formatOrderChangeCategory(r.change_category)}
        </MarkerTag>
      ),
    },
    {
      title: t('app.kuaizhizao.common.colLineMaterials'),
      ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
      render: (_, record) => renderDocumentLineMaterialsPreview(record.items, t),
    },
    {
      title: t('app.kuaizhizao.salesOrderChange.colChangeReason'),
      dataIndex: 'change_reason',
      width: 180,
      minWidth: 180,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
      hideInSearch: true,
    },
    {
      title: t('app.kuaizhizao.salesOrderChange.colDeltaAmount'),
      dataIndex: 'delta_amount',
      width: 128,
      minWidth: 128,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
      align: 'right',
      render: (_, r) => renderDeltaAmount(r.delta_amount),
    },
    ...buildDocumentAuditColumns<SalesOrderChange>(t),
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
    {
      title: t('app.kuaizhizao.salesOrderChange.colAppliedAt'),
      dataIndex: 'applied_at',
      width: 132,
      minWidth: 132,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
      render: (_, r) => (r.applied_at ? formatDateTime(r.applied_at, 'YYYY-MM-DD HH:mm') : '-'),
    },
    ...(orderChangeAuditColumn ? [orderChangeAuditColumn] : []),
    ...generateChangeCustomFieldColumns(),
    {
      title: t('app.kuaizhizao.salesOrderChange.colLifecycle'),
      dataIndex: LIST_LIFECYCLE_STAGE_FIELD,
      key: 'lifecycle',
      fixed: 'right',
      valueType: 'select',
      valueEnum: orderChangeLifecycleValueEnum,
      render: (_, record) => (
        <ListUniLifecycleCell
          lifecycle={getOrderChangeLifecycle(record as Record<string, unknown>, t)}
        />
      ),
    },
    {
      title: t('common.actions'),
      valueType: 'option',
      fixed: 'right',
      hideInSearch: true,
      render: (_, record) => {
        const canEdit = record.capabilities?.update?.allowed === true && changePerms.canUpdate;
        return [
          <Button {...rowActionKind('read')} key="view" onClick={() => openDetail(record)}>
            {t('common.detail')}
          </Button>,
          canEdit ? (
            <Button {...rowActionKind('update')} key="edit" onClick={() => openEdit(record)}>
              {t('common.edit')}
            </Button>
          ) : null,
        ];
      },
    },
  ], GLOBAL_DOC_LIST_FIELD_RANK),
    [
      t,
      changeCategoryValueEnum,
      changeCustomerSearchOptions,
      changePerms.canUpdate,
      orderChangeAuditColumn,
      orderChangeLifecycleValueEnum,
      renderDeltaAmount,
    ],
  );

  const request = useCallback(
    async (
      params: Record<string, unknown>,
      sort: Record<string, unknown> | undefined,
      _filter: unknown,
      searchFormValues?: Record<string, unknown>,
    ) => {
      const apiParams = resolveOrderChangeListApiParams(params, sort, searchFormValues, {
        partyIdField: 'customer_id',
      }) as SalesOrderChangeListParams;
      const res = await listSalesOrderChanges(apiParams);
      const items = await enrichChangeRecordsWithCustomFields(res.items ?? []);
      return { data: items, success: true, total: res.total ?? 0 };
    },
    [enrichChangeRecordsWithCustomFields],
  );

  const handleBatchDelete = useCallback(async (keys: React.Key[]) => {
    if (!keys || keys.length === 0) {
      message.warning(t('app.kuaizhizao.salesOrderChange.selectToDelete'));
      return;
    }
    let success = 0;
    let failed = 0;
    for (const key of keys) {
      const id = Number(key);
      if (!Number.isFinite(id) || id <= 0) {
        failed += 1;
        continue;
      }
      try {
        await deleteSalesOrderChange(id);
        success += 1;
      } catch {
        failed += 1;
      }
    }
    if (success > 0) message.success(t('app.kuaizhizao.salesOrderChange.batchDeleteSuccess', { count: success }));
    if (failed > 0) message.warning(t('app.kuaizhizao.salesOrderChange.batchDeletePartial', { count: failed }));
    setSelectedRowKeys([]);
    reloadTable();
  }, [message, t]);

  const timeconfigBasicItems = useDetailDrawerDescriptionItems(
    detailBasicColumns.filter((col) => {
                  if (col.dataIndex !== 'notes') return true;
                  return String(detail?.notes ?? '').trim().length > 0;
                }),
                detail,
    'sales_order_change',
  );

  const salesOrderChangeAttachments = documentAttachmentsFromRecord(detail);
  const showSalesOrderChangeAttachments =
    Boolean(detail) && hasDocumentAttachments(salesOrderChangeAttachments);

  const triggerCommitAfterSave = useCallback(() => {
    commitAfterSaveRef.current = true;
    void editForm
      .validateFields()
      .then(() => handleSaveEdit())
      .catch(() => {
        commitAfterSaveRef.current = false;
        setFormSaving(false);
      });
  }, [editForm, handleSaveEdit]);

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
                  onClick={leaveSalesOrderChangeFormPage}
                />
                <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
                  {isCreatePage
                    ? t('app.kuaizhizao.salesOrderChange.createTitle', {
                        defaultValue: t('app.kuaizhizao.salesOrderChange.editTitle'),
                      })
                    : t('app.kuaizhizao.salesOrderChange.editTitle')}
                </Typography.Title>
              </Space>
              <DocumentFormPageHeaderActions
                onCancel={leaveSalesOrderChangeFormPage}
                onSaveDraft={() => void handleSaveEdit()}
                onPrimarySubmit={() => void handleSaveEdit()}
                isCreatePage={isCreatePage}
                showSaveDraft={false}
                canSubmitAfterSave={false}
                showCommitSubmit={salesOrderChangeCanCommit}
                saveDraftLoading={formSaving}
                commitSubmitLoading={formSaving}
                onCommitSubmit={triggerCommitAfterSave}
              />
            </>
          }
        >
          <Spin spinning={formPageLoading}>
            <ProForm form={editForm} layout="vertical" submitter={false} onFinish={() => void handleSaveEdit()}>
              <OrderChangeItemsTable
                items={editItems ?? []}
                editable
                onChange={setEditItems}
                pricing={changePricing}
              />
              <ProFormTextArea
                name="change_reason"
                label={t('app.kuaizhizao.salesOrderChange.colChangeReason')}
                rules={[{ required: true }]}
              />
              <ProFormTextArea name="notes" label={t('common.remark')} />
              <CustomFieldsFormSection
                customFields={changeFormCustomFields}
                customFieldValues={changeFormCustomFieldValues}
                gridColumns={2}
              />
              <DocumentAttachmentsField category="sales_order_change_attachments" />
            </ProForm>
          </Spin>
        </DocumentFormPageLayout>
        {salesOrderChangeInitiatorModal}
        <OrderChangeImpactModal
          open={impactOpen}
          loading={impactLoading}
          impact={impactData}
          onClose={() => {
            setImpactOpen(false);
            setPendingSubmitId(null);
          }}
          onConfirm={confirmSubmit}
        />
      </>
    );
  }

  return (
    <>
      {salesOrderChangeAuditModal}
    <ListPageTemplate>
      <UniTable<SalesOrderChange>
        actionRef={actionRef}
        rowKey="id"
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.salesOrderChange)}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        columns={columns}
        showAdvancedSearch
        skipFuzzyPinyinClientFilter
        request={request}
        onTableDataChange={(rows) => {
          tableRowsRef.current = rows;
        }}
        columnPersistenceId="apps.kuaizhizao.pages.sales-management.sales-order-changes-width-v2"
        pinnedTabsField={LIST_LIFECYCLE_STAGE_FIELD}
        pinnedTabsValueEnum={orderChangeLifecycleValueEnum}
        toolBarRender={() => [
          <UniPullCreateToolbar
            key="create-sales-order-change-with-pull"
            compactKey="create-sales-order-change-with-pull"
            createIcon={<PlusOutlined />}
            createLabel={t('app.kuaizhizao.salesOrderChange.create')}
            onCreate={openCreate}
            menuItems={[
              {
                key: 'pull-from-sales-order',
                label: pullFromSalesOrderAction.label,
                onClick: openCreate,
              },
              { type: 'divider', key: 'copy-selected-divider' },
              {
                key: 'copy-selected',
                label: t('app.kuaizhizao.salesOrderChange.copySelectedCreate'),
                disabled: !selectedChangeForToolbar,
                onClick: () => void handleCopySelectedSalesOrderChange(),
              },
            ]}
          />,
          <UniBatchMenuButton
            key="sales-order-change-submit"
            selectedRowKeys={selectedRowKeys}
            menuItems={salesOrderChangeToolbarAuditMenus.submit}
            buttonText={t('common.submit')}
          />,
          <UniBatchMenuButton
            key="sales-order-change-audit"
            selectedRowKeys={selectedRowKeys}
            menuItems={salesOrderChangeToolbarAuditMenus.audit}
            buttonText={t('components.uniAction.audit')}
          />,
        ]}
        showDeleteButton
        deleteButtonText={t('common.delete')}
        onDelete={handleBatchDelete}
        deleteConfirmTitle={(count) => t('app.kuaizhizao.salesOrderChange.confirmBatchDelete', { count })}
        toolBarActionsAfterDelete={[]}
        rightToolBarActionsBeforeExport={[
          <UniCapabilityBatchButton
            key="sales-order-change-print"
            selectedRowKeys={selectedRowKeys}
            selectedRecords={selectedChangesForBatch}
            capabilityKey="print"
            permAllowed={changePerms.canPrint}
            batchAllowed={(records, perm) =>
              Boolean(perm) && records.some((record) => record.capabilities?.print?.allowed === true)
            }
            singleOnly
            onRun={async (id) => {
              openPrint({ documentType: 'sales_order_change', documentId: id });
            }}
            labels={{
              single: t('components.uniAction.print'),
              batch: t('components.uniAction.print'),
            }}
            icon={<PrinterOutlined />}
            size="medium"
          />,
        ]}
      />

      <UniPullQueryModal<PullSalesOrderCandidate>
        title={pullFromSalesOrderAction.label}
        open={pullFromSalesOrderQuery.open}
        onCancel={pullFromSalesOrderQuery.closeModal}
        onOk={pullFromSalesOrderQuery.handleConfirm}
        okText={t('common.create')}
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
        page={pullFromSalesOrderQuery.page}
        pageSize={pullFromSalesOrderQuery.pageSize}
        total={pullFromSalesOrderQuery.total}
        onPageChange={pullFromSalesOrderQuery.handlePageChange}
        scopeOptions={pullFromSalesOrderQuery.scopeOptions}
        scope={pullFromSalesOrderQuery.scope}
        onScopeChange={pullFromSalesOrderQuery.handleScopeChange}
        searchPlaceholder={t('app.kuaizhizao.orderChange.searchOrderPlaceholder', {
          orderLabel: t('app.kuaizhizao.salesOrderChange.salesOrderLabel'),
          partnerLabel: t('path.customers'),
        })}
        emptyText={t('app.kuaizhizao.orderChange.emptyNoEligibleOrders', {
          orderLabel: t('app.kuaizhizao.salesOrderChange.salesOrderLabel'),
        })}
        emptySearchText={t('app.kuaizhizao.orderChange.emptyNoSearchResults', {
          orderLabel: t('app.kuaizhizao.salesOrderChange.salesOrderLabel'),
        })}
        okButtonProps={{
          disabled:
            pullFromSalesOrderQuery.selectedRowKeys.length === 0 ||
            pullFromSalesOrderQuery.hasDisabledSelection ||
            pullFromSalesOrderQuery.loading,
        }}
      />

      <DetailDrawerTemplate
        title={t('app.kuaizhizao.salesOrderChange.detailTitle', { code: detail?.change_code ?? '' })}
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          resetChangeDetailFieldValues();
        }}
        size={DRAWER_CONFIG.HALF_WIDTH}
        extra={
          detail ? (
            <Space size="small">
              {!detailCapabilityGates.submit.disabled && (
                <Button icon={<ThunderboltOutlined />} onClick={() => runSubmitWithPreview(detail.id!)}>{t('common.submit')}</Button>
              )}
              {!detailCapabilityGates.update.disabled && (
                <Button icon={<EditOutlined />} onClick={() => { setDetailOpen(false); openEdit(detail); }}>{t('common.edit')}</Button>
              )}
              <UniWorkflowActions {...rowActionKind('skip')}
                record={detail}
                entityName={t('app.kuaizhizao.salesOrderChange.entityName')}
                statusField="status"
                reviewStatusField="review_status"
                draftStatuses={['DRAFT', '草稿', 'SUBMITTED']}
                pendingStatuses={['PENDING_REVIEW', '待审核']}
                approvedStatuses={['AUDITED', '已审核', 'APPLIED', '已生效']}
                rejectedStatuses={['REJECTED', '已驳回']}
                onSuccess={async () => {
                  reloadTable();
                  if (detail.id) setDetail(await getSalesOrderChange(detail.id));
                }}
              />
              {!detailCapabilityGates.print.disabled && detail.id != null && (
                <Button
                  icon={<PrinterOutlined />}
                  onClick={() => openPrint({ documentType: 'sales_order_change', documentId: detail.id! })}
                >
                  {t('components.uniAction.print')}
                </Button>
              )}
            </Space>
          ) : null
        }
        basic={
          detail ? (
            <>
              <Descriptions
                column={3}
                size="small"
                items={timeconfigBasicItems}
              />
              {hasCustomFieldsDetailContent(
                changeListCustomFields,
                changeDetailCustomFieldValues,
              ) ? (
                <div style={{ marginTop: 16 }}>
                  <CustomFieldsDetailSection
                    customFields={changeListCustomFields}
                    customFieldValues={changeDetailCustomFieldValues}
                  />
                </div>
              ) : null}
            </>
          ) : undefined
        }
        collaboration={detailCollaboration}
        collaborationAuditRecord={detail}
        supplementary={
          showSalesOrderChangeAttachments ? (
            <DocumentAttachmentsReadonly attachments={salesOrderChangeAttachments} />
          ) : undefined
        }
        supplementaryTitle={
          showSalesOrderChangeAttachments ? t('app.uniDetail.sectionAttachments') : undefined
        }
        supplementaryVisible={showSalesOrderChangeAttachments}
        lines={detail ? <OrderChangeItemsTable items={detail.items ?? []} /> : undefined}
      />

      <OrderChangeImpactModal
        open={impactOpen}
        loading={impactLoading}
        impact={impactData}
        onClose={() => { setImpactOpen(false); setPendingSubmitId(null); }}
        onConfirm={confirmSubmit}
      />
      {PrintModal}
    </ListPageTemplate>
    </>
  );
};

export default SalesOrderChangesPage;
