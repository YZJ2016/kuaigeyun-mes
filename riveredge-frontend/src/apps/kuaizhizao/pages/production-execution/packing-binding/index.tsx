import { rowActionKind, rowActionLabelKeep } from '../../../../../components/uni-action';
/**
 * 装箱打包绑定管理页面
 *
 * 提供装箱打包绑定记录的管理功能，包括查看、更新、删除等。
 * 归属生产管理：产线末端打包/装箱时记录每箱内含产品批次，用于出货追溯。
 *
 * Author: Luigi Lu
 * Date: 2026-01-15
 */

import React, { useRef, useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  ActionType,
  ProColumns,
  ProDescriptionsItemProps,
  ProFormText,
  ProFormDigit,
  ProFormSelect,
  ProFormTextArea,
} from '@ant-design/pro-components';
import {
  App,
  Alert,
  Button,
  Popconfirm,
  Row,
  Col,
  Descriptions,
  Typography,
  Empty,
  Spin,
  Modal,
  Table,
  Space,
  theme as AntdTheme,
  Tag,
} from 'antd';
import { EyeOutlined, EditOutlined, DeleteOutlined, QrcodeOutlined } from '@ant-design/icons';
import { UniTable } from '../../../../../components/uni-table';
import { UniBatchButton } from '../../../../../components/uni-batch';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { packingBindingBatchPrintAllowed } from '../../../../../hooks/useDocumentCapabilities';
import {
  ListPageTemplate,
  FormModalTemplate,
  DetailDrawerTemplate,
  MODAL_CONFIG,
  DRAWER_CONFIG,
  useDetailDrawerDescriptionItems,
  type StatCard,
} from '../../../../../components/layout-templates';
import { SimpleSparkline } from '../../../../../components';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import {
  packingBindingApi,
  type PackingAsnResult,
} from '../../../services/packing-binding';
import { warehouseApi } from '../../../services/production';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import { mapAttachmentsToUploadList, normalizeDocumentAttachments } from '../../../utils/documentAttachments';

import { qrcodeApi } from '../../../../../services/qrcode';
import {
  PackingBindingQrcodePreviewModal,
  type PackingBindingQrcodePreviewItem,
} from './PackingBindingQrcodePreviewModal';

const LazyQRCodeGenerator = lazy(() =>
  import('../../../../../components/qrcode/QRCodeGenerator').then((m) => ({ default: m.QRCodeGenerator })),
);
import { UniLifecycle, UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import { DocumentTrackingTimelineBody, useDocumentTracking } from '../../../../../components/document-tracking-panel';
import { WarehouseTraceBriefPrimaryActions } from '../../warehouse-management/WarehouseTraceBriefFooter';
import { getPackingBindingLifecycle, buildPackingBindingMethodValueEnum, buildPackingBindingSourceValueEnum, resolvePackingBindingListApiParams } from '../../../utils/packingBindingLifecycle';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { formatDateTime, formatDateTimeBySiteSetting } from '../../../../../utils/format';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { extractProTableSort } from '../../../../../utils/tableQueryKey';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { alignProColumns, alignDescriptionColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import {
  MaterialStackedCell,
  UniTableStackedPrimaryCell,
} from '../../../../../components/uni-table/stackedPrimaryColumn';
import { getAntdModal } from '../../../../../utils/antdAppApis';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';

/** 与后端 DECIMAL(12,2) 一致 */
const MAX_PACKING_QUANTITY = 9999999999.99;

interface PackingBinding {
  id?: number;
  uuid?: string;
  finished_goods_receipt_id?: number;
  sales_delivery_id?: number;
  product_id?: number;
  product_code?: string;
  product_name?: string;
  product_serial_no?: string;
  serial_numbers?: string[];
  packing_material_id?: number;
  packing_material_code?: string;
  packing_material_name?: string;
  packing_quantity?: number;
  box_no?: string;
  packing_level?: string;
  parent_box_no?: string;
  pallet_no?: string;
  source_line_id?: number;
  seal_status?: string;
  binding_method?: string;
  barcode?: string;
  bound_by?: number;
  bound_by_name?: string;
  bound_at?: string;
  remarks?: string;
  attachments?: Array<{ uid?: string; name?: string; url?: string }>;
  created_at?: string;
  updated_at?: string;
  capabilities?: {
    update?: { allowed?: boolean; reason?: string };
    delete?: { allowed?: boolean; reason?: string };
    print?: { allowed?: boolean; reason?: string };
    seal?: { allowed?: boolean; reason?: string };
  };
}

interface PackingBindingPageResult {
  data: PackingBinding[];
  total: number;
  success: boolean;
}

interface PackingTaskPoolItem {
  id: number;
  source_type?: 'sales_delivery' | 'finished_goods_receipt';
  doc_code?: string;
  party_name?: string;
  delivery_code: string;
  customer_name: string;
  review_status: string;
  status: string;
  required_quantity?: number | string;
  packed_quantity?: number | string;
  remaining_quantity?: number | string;
  box_count?: number;
  updated_at: string;
}

interface PackingTaskPoolResult {
  pending_review: number;
  pending_outbound: number;
  pending_receipt?: number;
  total: number;
  items: PackingTaskPoolItem[];
}

type PackingBindingSourceType = 'sales_delivery' | 'finished_goods_receipt';

interface PackingBindingSourceItemOption {
  key: string;
  sourceLineId: number;
  productId: number;
  productCode?: string;
  productName?: string;
  productSerialNo?: string;
  maxQuantity?: number;
  remainingQuantity?: number;
  packedQuantity?: number;
  requiredQuantity?: number;
}

const PACKING_QTY_KEYS = [
  'pending_quantity',
  'available_quantity',
  'delivery_quantity',
  'receipt_quantity',
  'qualified_quantity',
  'quantity',
];

function resolvePositiveNumber(value: unknown): number | undefined {
  if (value == null || value === '') return undefined;
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return n;
}

function isNotFoundError(error: any): boolean {
  const status = Number(error?.response?.status ?? error?.status);
  return status === 404;
}

function buildPackingSourceItemOptions(
  detail: Record<string, unknown> | undefined,
  remainingByLine?: Map<number, { remaining: number; packed: number; required: number }>,
): PackingBindingSourceItemOption[] {
  const lines = Array.isArray(detail?.items) ? (detail.items as Array<Record<string, unknown>>) : [];
  return lines
    .map((line, index) => {
      const productId = Number(line.product_id ?? line.material_id ?? line.finished_product_id);
      if (!Number.isFinite(productId) || productId <= 0) {
        return null;
      }
      const lineId = Number(line.id);
      if (!Number.isFinite(lineId) || lineId <= 0) {
        return null;
      }
      const productCode = typeof line.product_code === 'string'
        ? line.product_code
        : typeof line.material_code === 'string'
          ? line.material_code
          : undefined;
      const productName = typeof line.product_name === 'string'
        ? line.product_name
        : typeof line.material_name === 'string'
          ? line.material_name
          : undefined;
      const productSerialNo = typeof line.product_serial_no === 'string' ? line.product_serial_no : undefined;
      const maxQuantity = PACKING_QTY_KEYS
        .map((key) => resolvePositiveNumber(line[key]))
        .find((value) => value != null);
      const rem = remainingByLine?.get(lineId);
      const remainingQuantity = rem?.remaining ?? maxQuantity;
      return {
        key: String(lineId),
        sourceLineId: lineId,
        productId,
        productCode,
        productName,
        productSerialNo,
        maxQuantity: remainingQuantity,
        remainingQuantity,
        packedQuantity: rem?.packed,
        requiredQuantity: rem?.required ?? maxQuantity,
      } satisfies PackingBindingSourceItemOption;
    })
    .filter((option): option is PackingBindingSourceItemOption => option != null)
    .filter((option) => (option.remainingQuantity == null ? true : option.remainingQuantity > 0));
}

function renderPbRowActions(nodes: React.ReactNode[], keyPrefix: string): React.ReactNode {
  return nodes;
}


const PB_STAT_SPARK_1 = [3, 4, 5, 4, 6, 5, 7];
const PB_STAT_SPARK_2 = [2, 3, 2, 4, 3, 5, 4];
const PB_STAT_SPARK_3 = [1, 2, 1, 2, 1, 2, 2];

const PB_RESOURCE = 'kuaizhizao:production-execution-packing-binding';

function buildPackingQuantityRules(
  t: (key: string, options?: Record<string, unknown>) => string,
  required = true,
  maxRemaining?: number,
) {
  const rules: Array<{ required?: boolean; message?: string; validator?: (_: unknown, value: number) => Promise<void> }> = [];
  if (required) {
    rules.push({ required: true, message: t('app.kuaizhizao.packingBinding.ruleEnterPackingQty') });
  }
  rules.push({
    validator: (_rule, value) => {
      if (value == null || value === '') {
        return Promise.resolve();
      }
      const n = Number(value);
      if (!Number.isFinite(n) || n <= 0) {
        return Promise.reject(new Error(t('app.kuaizhizao.packingBinding.rulePackingQtyPositive')));
      }
      if (maxRemaining != null && Number.isFinite(maxRemaining) && n > maxRemaining) {
        return Promise.reject(
          new Error(t('app.kuaizhizao.packingBinding.rulePackingQtyMax', { max: maxRemaining })),
        );
      }
      if (n > MAX_PACKING_QUANTITY) {
        return Promise.reject(
          new Error(t('app.kuaizhizao.packingBinding.rulePackingQtyMax', { max: MAX_PACKING_QUANTITY })),
        );
      }
      return Promise.resolve();
    },
  });
  return rules;
}

const PackingBindingPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const { token } = AntdTheme.useToken();
  const packingBindingDetailDrawerZIndex = token.zIndexPopupBase;
  const navigate = useNavigate();
  const actionRef = useRef<ActionType>(null);
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const tableRowsRef = useRef<PackingBinding[]>([]);
  const packingBindingPerms = useResourcePermissions(PB_RESOURCE);
  const selectedBindingsForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => tableRowsRef.current.find((row) => String(row.id) === String(key)))
        .filter((row): row is PackingBinding => row != null),
    [selectedRowKeys],
  );
  const [searchParams, setSearchParams] = useSearchParams();

  const getBindingSourceLabel = useCallback(
    (record: PackingBinding) => {
      if (record.sales_delivery_id) return t('app.kuaizhizao.packingBinding.sourceSalesDelivery');
      if (record.finished_goods_receipt_id) return t('app.kuaizhizao.packingBinding.sourceFinishedGoodsReceipt');
      return t('app.kuaizhizao.packingBinding.sourceOther');
    },
    [t],
  );

  const bindingMethodTag = useCallback(
    (m?: string) => {
      const v = (m || '').trim();
      if (v === 'scan') return <MarkerTag color="success">{t('app.kuaizhizao.packingBinding.bindingMethodScan')}</MarkerTag>;
      if (v === 'manual') return <MarkerTag color="geekblue">{t('app.kuaizhizao.packingBinding.bindingMethodManual')}</MarkerTag>;
      return v ? <MarkerTag color="default">{v}</MarkerTag> : '-';
    },
    [t],
  );

  const packingQuantityRules = useMemo(() => buildPackingQuantityRules(t), [t]);
  const [createLineRemaining, setCreateLineRemaining] = useState<number | undefined>(undefined);
  const createPackingQuantityRules = useMemo(
    () => buildPackingQuantityRules(t, true, createLineRemaining),
    [createLineRemaining, t],
  );

  const bindingSourceTag = useCallback(
    (record: PackingBinding) => {
      const label = getBindingSourceLabel(record);
      const color = record.sales_delivery_id ? 'orange' : record.finished_goods_receipt_id ? 'success' : 'default';
      return <MarkerTag color={color}>{label}</MarkerTag>;
    },
    [getBindingSourceLabel],
  );

  const getErrorMessage = useCallback(
    (error: any, fallbackKey: string) => error?.message || t(fallbackKey),
    [t],
  );

  const [statsVersion, setStatsVersion] = useState(0);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const formRef = useRef<any>(null);
  const createFormRef = useRef<any>(null);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [createSourceType, setCreateSourceType] = useState<PackingBindingSourceType | null>(null);
  const [createSourceId, setCreateSourceId] = useState<number | null>(null);
  const [createSourceLoading, setCreateSourceLoading] = useState(false);
  const [createSourceItems, setCreateSourceItems] = useState<PackingBindingSourceItemOption[]>([]);

  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [currentBinding, setCurrentBinding] = useState<PackingBinding | null>(null);

  const [pbTrackingRefreshKey, setPbTrackingRefreshKey] = useState(0);

  const handleDetail = useCallback(async (record: PackingBinding) => {
    try {
      const detail = await packingBindingApi.get(record.id!.toString());
      setCurrentBinding(detail);
      setDetailDrawerVisible(true);
      setPbTrackingRefreshKey((k) => k + 1);
    } catch (error: any) {
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.fetchDetailFailed'));
    }
  }, [messageApi]);

  const [localStats, setLocalStats] = useState({ total: 0, scan: 0, manual: 0 });
  const [taskPoolVisible, setTaskPoolVisible] = useState(false);
  const [taskPoolLoading, setTaskPoolLoading] = useState(false);
  const [taskPool, setTaskPool] = useState<PackingTaskPoolResult>({
    pending_review: 0,
    pending_outbound: 0,
    pending_receipt: 0,
    total: 0,
    items: [],
  });
  const [asnVisible, setAsnVisible] = useState(false);
  const [asnLoading, setAsnLoading] = useState(false);
  const [asnData, setAsnData] = useState<PackingAsnResult | null>(null);
  const [qrcodePreviewOpen, setQrcodePreviewOpen] = useState(false);
  const [qrcodePreviewLoading, setQrcodePreviewLoading] = useState(false);
  const [qrcodePreviewItems, setQrcodePreviewItems] = useState<PackingBindingQrcodePreviewItem[]>([]);
  const [qrcodePreviewFailed, setQrcodePreviewFailed] = useState<string[]>([]);

  const refreshLocalStats = useCallback(async () => {
    try {
      const stats = await packingBindingApi.statistics();
      setLocalStats({
        total: Number(stats?.total || 0),
        scan: Number(stats?.scan || 0),
        manual: Number(stats?.manual || 0),
      });
    } catch {
      setLocalStats({ total: 0, scan: 0, manual: 0 });
    }
  }, []);

  const openTaskPool = useCallback(async () => {
    setTaskPoolVisible(true);
    setTaskPoolLoading(true);
    try {
      const result = await packingBindingApi.taskPool({ limit: 20 });
      setTaskPool({
        pending_review: Number(result?.pending_review || 0),
        pending_outbound: Number(result?.pending_outbound || 0),
        pending_receipt: Number(result?.pending_receipt || 0),
        total: Number(result?.total || 0),
        items: Array.isArray(result?.items) ? result.items : [],
      });
    } catch (error: any) {
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.taskPoolFetchFailed'));
    } finally {
      setTaskPoolLoading(false);
    }
  }, [getErrorMessage, messageApi]);

  const openAsn = useCallback(async (deliveryId: number) => {
    setAsnVisible(true);
    setAsnLoading(true);
    setAsnData(null);
    try {
      const data = await packingBindingApi.getAsn(deliveryId);
      setAsnData(data);
    } catch (error: any) {
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.asnFetchFailed'));
      setAsnVisible(false);
    } finally {
      setAsnLoading(false);
    }
  }, [getErrorMessage, messageApi]);

  const closeCreateModal = useCallback(() => {
    setCreateModalVisible(false);
    setCreateSourceType(null);
    setCreateSourceId(null);
    setCreateSourceItems([]);
    setCreateSourceLoading(false);
    setCreateLineRemaining(undefined);
    createFormRef.current?.resetFields();
  }, []);

  const handleSourceItemChange = useCallback((lineKey: string | undefined) => {
    if (!lineKey) return;
    const selected = createSourceItems.find((item) => item.key === lineKey);
    if (!selected) return;
    const nextValues: Record<string, unknown> = {
      source_line_id: selected.sourceLineId,
      product_id: selected.productId,
      product_code: selected.productCode,
      product_name: selected.productName,
      product_serial_no: selected.productSerialNo,
    };
    if (selected.remainingQuantity != null) {
      nextValues.packing_quantity = selected.remainingQuantity;
      setCreateLineRemaining(selected.remainingQuantity);
    } else if (selected.maxQuantity != null) {
      nextValues.packing_quantity = selected.maxQuantity;
      setCreateLineRemaining(selected.maxQuantity);
    } else {
      setCreateLineRemaining(undefined);
    }
    createFormRef.current?.setFieldsValue(nextValues);
  }, [createSourceItems]);

  const openCreateFromSource = useCallback(async (sourceType: PackingBindingSourceType, sourceId: number) => {
    if (!packingBindingPerms.canRead && !packingBindingPerms.canCreate) {
      messageApi.error(t('app.kuaizhizao.packingBinding.noCreatePermission'));
      return;
    }
    if (!packingBindingPerms.canCreate) {
      messageApi.error(t('app.kuaizhizao.packingBinding.noCreatePermission'));
      return;
    }
    setCreateModalVisible(true);
    setCreateSourceType(sourceType);
    setCreateSourceId(sourceId);
    setCreateSourceLoading(true);
    try {
      const [detail, remaining] = await Promise.all([
        sourceType === 'sales_delivery'
          ? warehouseApi.salesDelivery.get(String(sourceId))
          : warehouseApi.finishedGoodsReceipt.get(String(sourceId)),
        packingBindingApi.sourceRemaining({ source_type: sourceType, source_id: sourceId }),
      ]);
      const remainingByLine = new Map(
        (remaining?.lines || []).map((line) => [
          line.source_line_id,
          {
            remaining: Number(line.remaining_quantity) || 0,
            packed: Number(line.packed_quantity) || 0,
            required: Number(line.required_quantity) || 0,
          },
        ]),
      );
      const itemOptions = buildPackingSourceItemOptions(
        detail as Record<string, unknown> | undefined,
        remainingByLine,
      );
      if (itemOptions.length === 0) {
        messageApi.warning(t('app.kuaizhizao.packingBinding.noBindableItems'));
        closeCreateModal();
        return;
      }
      setCreateSourceItems(itemOptions);
      const preferred = itemOptions[0];
      createFormRef.current?.setFieldsValue({
        source_item_key: preferred.key,
        source_line_id: preferred.sourceLineId,
        product_id: preferred.productId,
        product_code: preferred.productCode,
        product_name: preferred.productName,
        product_serial_no: preferred.productSerialNo,
        packing_quantity: preferred.remainingQuantity ?? preferred.maxQuantity ?? undefined,
        packing_level: 'carton',
        serial_numbers: undefined,
        barcode: undefined,
        box_no: undefined,
        parent_box_no: undefined,
        pallet_no: undefined,
        packing_material_id: undefined,
        packing_material_code: undefined,
        packing_material_name: undefined,
        remarks: undefined,
      });
      setCreateLineRemaining(
        preferred.remainingQuantity ?? preferred.maxQuantity ?? undefined,
      );
    } catch (error: any) {
      closeCreateModal();
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.loadSourceFailed'));
    } finally {
      setCreateSourceLoading(false);
    }
  }, [closeCreateModal, getErrorMessage, messageApi, packingBindingPerms.canCreate, packingBindingPerms.canRead, t]);

  useEffect(() => {
    void refreshLocalStats();
  }, [statsVersion, refreshLocalStats]);


  const packingTracking = useDocumentTracking(
    detailDrawerVisible && currentBinding?.id ? 'packing_binding' : undefined,
    currentBinding?.id,
    pbTrackingRefreshKey,
  );
  const packingDetailLifecycle = useMemo(
    () => (currentBinding ? getPackingBindingLifecycle(currentBinding as Record<string, unknown>) : null),
    [currentBinding],
  );
  const packingNextSteps = packingDetailLifecycle?.nextStepSuggestions;
  const packingShowNextInTitle = Boolean(packingNextSteps?.length);

  const [currentBindingId, setCurrentBindingId] = useState<number | null>(null);

  useEffect(() => {
    const boxUuid = searchParams.get('uuid');
    const boxNo = searchParams.get('box_no');
    const action = searchParams.get('action');

    if (action === 'detail' && (boxUuid || boxNo)) {
      const load = async () => {
        try {
          // 先按 uuid 精确匹配（新协议），找不到再回退箱号模糊匹配（兼容旧参数）
          if (boxUuid) {
            const byUuid = await packingBindingApi.list({ uuid: boxUuid, skip: 0, limit: 1 });
            if (Array.isArray(byUuid) && byUuid.length > 0) {
              await handleDetail(byUuid[0]);
              setSearchParams({}, { replace: true });
              return;
            }
          }
          const fallbackBoxNo = boxNo || boxUuid;
          const byBoxNo = await packingBindingApi.list({ box_no: fallbackBoxNo, skip: 0, limit: 1 });
          if (Array.isArray(byBoxNo) && byBoxNo.length > 0) {
            await handleDetail(byBoxNo[0]);
            setSearchParams({}, { replace: true });
            return;
          }
          messageApi.warning(t('app.kuaizhizao.packingBinding.recordNotFound'));
        } catch {
          messageApi.error(t('app.kuaizhizao.packingBinding.fetchRecordFailed'));
        }
      };
      void load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    const action = searchParams.get('action');
    if (action !== 'bind') return;
    const sourceTypeRaw = searchParams.get('source_type');
    const sourceId = Number(searchParams.get('source_id'));
    if (
      (sourceTypeRaw === 'sales_delivery' || sourceTypeRaw === 'finished_goods_receipt')
      && Number.isFinite(sourceId)
      && sourceId > 0
    ) {
      void openCreateFromSource(sourceTypeRaw, sourceId);
    } else {
      messageApi.warning(t('app.kuaizhizao.packingBinding.invalidSourceParam'));
    }
    setSearchParams({}, { replace: true });
  }, [messageApi, openCreateFromSource, searchParams, setSearchParams, t]);

  const handleCreateSubmit = useCallback(async (values: Record<string, unknown>) => {
    if (!createSourceType || createSourceId == null) {
      messageApi.error(t('app.kuaizhizao.packingBinding.invalidSourceParam'));
      return false;
    }
    const productId = Number(values.product_id);
    if (!Number.isFinite(productId) || productId <= 0) {
      messageApi.error(t('app.kuaizhizao.packingBinding.ruleSelectSourceItem'));
      return false;
    }
    const sourceLineId = Number(values.source_line_id);
    const serialRaw = values.serial_numbers;
    const serialNumbers = Array.isArray(serialRaw)
      ? serialRaw.map((x) => String(x).trim()).filter(Boolean)
      : typeof serialRaw === 'string'
        ? String(serialRaw).split(/[,，\s]+/).map((x) => x.trim()).filter(Boolean)
        : undefined;
    const scanned =
      (values.barcode && String(values.barcode).trim())
      || (serialNumbers && serialNumbers.length > 0);
    const payload = {
      product_id: productId,
      source_line_id: Number.isFinite(sourceLineId) && sourceLineId > 0 ? sourceLineId : undefined,
      product_code: values.product_code,
      product_name: values.product_name,
      product_serial_no: values.product_serial_no,
      serial_numbers: serialNumbers,
      packing_material_id: values.packing_material_id ? Number(values.packing_material_id) : undefined,
      packing_material_code: values.packing_material_code,
      packing_material_name: values.packing_material_name,
      packing_quantity: values.packing_quantity,
      box_no: values.box_no,
      packing_level: values.packing_level || 'carton',
      parent_box_no: values.parent_box_no,
      pallet_no: values.pallet_no,
      binding_method: scanned ? 'scan' : 'manual',
      barcode: values.barcode,
      remarks: values.remarks,
    };
    try {
      if (createSourceType === 'sales_delivery') {
        await packingBindingApi.createFromDelivery(String(createSourceId), payload);
      } else {
        await packingBindingApi.createFromReceipt(String(createSourceId), payload);
      }
      messageApi.success(t('app.kuaizhizao.packingBinding.createSuccess'));
      setStatsVersion((v) => v + 1);
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
      if (taskPoolVisible) {
        await openTaskPool();
      }
      // 多次分箱：刷新剩余量；仍有可绑行则保留弹窗
      const sourceType = createSourceType;
      const sourceId = createSourceId;
      const remaining = await packingBindingApi.sourceRemaining({
        source_type: sourceType,
        source_id: sourceId,
      });
      const detail =
        sourceType === 'sales_delivery'
          ? await warehouseApi.salesDelivery.get(String(sourceId))
          : await warehouseApi.finishedGoodsReceipt.get(String(sourceId));
      const remainingByLine = new Map(
        (remaining?.lines || []).map((line) => [
          line.source_line_id,
          {
            remaining: Number(line.remaining_quantity) || 0,
            packed: Number(line.packed_quantity) || 0,
            required: Number(line.required_quantity) || 0,
          },
        ]),
      );
      const itemOptions = buildPackingSourceItemOptions(
        detail as Record<string, unknown> | undefined,
        remainingByLine,
      );
      if (itemOptions.length === 0) {
        closeCreateModal();
      } else {
        setCreateSourceItems(itemOptions);
        const preferred = itemOptions[0];
        createFormRef.current?.resetFields();
        createFormRef.current?.setFieldsValue({
          source_item_key: preferred.key,
          source_line_id: preferred.sourceLineId,
          product_id: preferred.productId,
          product_code: preferred.productCode,
          product_name: preferred.productName,
          product_serial_no: preferred.productSerialNo,
          packing_quantity: preferred.remainingQuantity ?? preferred.maxQuantity ?? undefined,
          packing_level: 'carton',
        });
        setCreateLineRemaining(
          preferred.remainingQuantity ?? preferred.maxQuantity ?? undefined,
        );
        messageApi.info(t('app.kuaizhizao.packingBinding.createContinueHint'));
      }
      return true;
    } catch (error: any) {
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.createFailed'));
      return false;
    }
  }, [
    closeCreateModal,
    createSourceId,
    createSourceType,
    getErrorMessage,
    invalidateMenuBadgeCounts,
    messageApi,
    openTaskPool,
    t,
    taskPoolVisible,
  ]);

  const handleBatchGenerateQRCode = async () => {
    if (selectedRowKeys.length === 0) {
      messageApi.warning(t('app.kuaizhizao.packingBinding.selectForQrcode'));
      return;
    }

    setQrcodePreviewOpen(true);
    setQrcodePreviewLoading(true);
    setQrcodePreviewItems([]);
    setQrcodePreviewFailed([]);

    const failed: string[] = [];
    const generated: PackingBindingQrcodePreviewItem[] = [];
    for (const key of selectedRowKeys) {
      try {
        const binding = await packingBindingApi.get(String(key));
        const boxNo = String(binding.box_no || '').trim();
        const boxUuid = String(binding.uuid || boxNo).trim();
        if (!boxNo || !boxUuid) {
          failed.push(`${boxNo || key}: ${t('app.kuaizhizao.packingBinding.qrcodeMissingBoxNo')}`);
          continue;
        }
        const res = await qrcodeApi.generateBox({
          box_uuid: boxUuid,
          box_code: boxNo,
          material_codes: binding.product_code ? [String(binding.product_code)] : [],
        });
        if (!res?.qrcode_image) {
          failed.push(`${boxNo}: ${t('app.kuaizhizao.packingBinding.generateFailed')}`);
          continue;
        }
        generated.push({
          bindingId: Number(binding.id ?? key),
          boxNo,
          productCode: binding.product_code ? String(binding.product_code) : undefined,
          qrcodeImage: res.qrcode_image,
        });
      } catch (error: any) {
        failed.push(`${String(key)}: ${getErrorMessage(error, 'app.kuaizhizao.packingBinding.generateFailed')}`);
      }
    }

    setQrcodePreviewItems(generated);
    setQrcodePreviewFailed(failed);
    setQrcodePreviewLoading(false);

    if (generated.length === 0) {
      setQrcodePreviewOpen(false);
      getAntdModal().error({
        title: t('app.kuaizhizao.packingBinding.qrcodeBatchFailedTitle'),
        content: (
          <div style={{ maxHeight: 280, overflowY: 'auto' }}>
            {failed.map((msg) => (
              <div key={msg}>{msg}</div>
            ))}
          </div>
        ),
        width: 640,
      });
      return;
    }
    if (failed.length === 0) {
      messageApi.success(t('app.kuaizhizao.packingBinding.qrcodeSuccess', { count: generated.length }));
    } else {
      messageApi.warning(
        t('app.kuaizhizao.packingBinding.qrcodePartial', { success: generated.length, failed: failed.length }),
      );
    }
  };

  const packingBindingBoxQrcodeData = useMemo(() => {
    if (!currentBinding?.box_no) return null;
    const boxNo = String(currentBinding.box_no).trim();
    const boxUuid = String(currentBinding.uuid || boxNo).trim();
    if (!boxNo || !boxUuid) return null;
    return {
      box_uuid: boxUuid,
      box_code: boxNo,
      material_codes: currentBinding.product_code ? [String(currentBinding.product_code)] : [],
    };
  }, [currentBinding?.box_no, currentBinding?.product_code, currentBinding?.uuid]);


  const handleEdit = useCallback(async (record: PackingBinding) => {
    try {
      setCurrentBindingId(record.id!);
      setEditModalVisible(true);
      const detail = await packingBindingApi.get(record.id!.toString());
      formRef.current?.resetFields();
      const serialList = Array.isArray(detail.serial_numbers) ? detail.serial_numbers : [];
      formRef.current?.setFieldsValue({
        packing_quantity: detail.packing_quantity,
        box_no: detail.box_no,
        product_serial_no: detail.product_serial_no,
        serial_numbers: serialList.length ? serialList.join(', ') : undefined,
        packing_material_id: detail.packing_material_id,
        packing_material_code: detail.packing_material_code,
        packing_material_name: detail.packing_material_name,
        remarks: detail.remarks,
        attachments: mapAttachmentsToUploadList(detail.attachments),
      });
    } catch (error: any) {
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.fetchDetailFailed'));
    }
  }, [messageApi]);

  const handleEditSubmit = async (values: any) => {
    try {
      if (!currentBindingId) {
        messageApi.error(t('app.kuaizhizao.packingBinding.idNotFound'));
        return;
      }

      const serialRaw = values.serial_numbers;
      const serialNumbers = Array.isArray(serialRaw)
        ? serialRaw.map((x: unknown) => String(x).trim()).filter(Boolean)
        : typeof serialRaw === 'string'
          ? String(serialRaw).split(/[,，\s]+/).map((x) => x.trim()).filter(Boolean)
          : undefined;
      await packingBindingApi.update(currentBindingId.toString(), {
        packing_quantity: values.packing_quantity,
        box_no: values.box_no,
        product_serial_no: values.product_serial_no,
        serial_numbers: serialNumbers,
        packing_material_id: values.packing_material_id ? Number(values.packing_material_id) : undefined,
        packing_material_code: values.packing_material_code,
        packing_material_name: values.packing_material_name,
        remarks: values.remarks,
        attachments: normalizeDocumentAttachments(values.attachments),
      });
      messageApi.success(t('app.kuaizhizao.packingBinding.updateSuccess'));
      const oid = currentBindingId;
      setEditModalVisible(false);
      setCurrentBindingId(null);
      formRef.current?.resetFields();
      setStatsVersion((v) => v + 1);
      invalidateMenuBadgeCounts();

      actionRef.current?.reload();
      if (oid != null && currentBinding?.id === oid) {
        try {
          const fresh = await packingBindingApi.get(String(oid));
          setCurrentBinding(fresh);
          setPbTrackingRefreshKey((k) => k + 1);
        } catch {
          /* ignore */
        }
      }
    } catch (error: any) {
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.updateFailed'));
      throw error;
    }
  };

  const handleDeleteOne = async (record: PackingBinding) => {
    try {
      await packingBindingApi.delete(record.id!.toString());
      messageApi.success(t('app.kuaizhizao.packingBinding.deleteSuccess'));
      if (currentBinding?.id === record.id) {
        setDetailDrawerVisible(false);
        setCurrentBinding(null);
      }
      setSelectedRowKeys([]);
      setStatsVersion((v) => v + 1);
      invalidateMenuBadgeCounts();

      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.deleteFailed'));
    }
  };

  const handleSeal = useCallback(async (record: PackingBinding) => {
    try {
      const fresh = await packingBindingApi.seal(String(record.id));
      messageApi.success(t('app.kuaizhizao.packingBinding.sealSuccess'));
      if (currentBinding?.id === record.id) {
        setCurrentBinding(fresh as PackingBinding);
      }
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.sealFailed'));
    }
  }, [currentBinding?.id, getErrorMessage, messageApi, t]);

  const handleBatchDelete = async (keys: React.Key[]) => {
    if (keys.length === 0) {
      messageApi.warning(t('app.kuaizhizao.packingBinding.selectToDelete'));
      return;
    }
    const failed: string[] = [];
    let successCount = 0;
    for (const key of keys) {
      try {
        await packingBindingApi.delete(String(key));
        successCount += 1;
      } catch (error: any) {
        failed.push(`${String(key)}: ${getErrorMessage(error, 'common.deleteFailed')}`);
      }
    }
    try {
      setSelectedRowKeys([]);
      if (currentBinding?.id != null && keys.map(Number).includes(currentBinding.id)) {
        setDetailDrawerVisible(false);
        setCurrentBinding(null);
      }
      actionRef.current?.reload();
      setStatsVersion((v) => v + 1);
      invalidateMenuBadgeCounts();
      if (failed.length === 0) {
        messageApi.success(t('app.kuaizhizao.packingBinding.batchDeleteSuccess', { count: successCount }));
        return;
      }
      messageApi.warning(t('app.kuaizhizao.packingBinding.batchDeletePartial', { success: successCount, failed: failed.length }));
      getAntdModal().error({
        title: t('app.kuaizhizao.packingBinding.batchDeleteFailedTitle'),
        content: (
          <div style={{ maxHeight: 280, overflowY: 'auto' }}>
            {failed.map((msg) => (
              <div key={msg}>{msg}</div>
            ))}
          </div>
        ),
        width: 640,
      });
    } catch (error: any) {
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.batchDeleteFailed'));
    }
  };

  const detailBaseColumns: ProDescriptionsItemProps<PackingBinding>[] = useMemo(
    () =>
      alignDescriptionColumns([
      {
        title: t('app.kuaizhizao.packingBinding.colBoxNo'),
        dataIndex: 'box_no',
        render: (_, r) => (
          <Typography.Text copyable={{ text: String(r.box_no ?? '') }}>{r.box_no ?? '-'}</Typography.Text>
        ),
      },
      {
        title: t('app.kuaizhizao.packingBinding.colProductCode'),
        dataIndex: 'product_code',
        render: (_, r) => (
          <Typography.Text copyable={{ text: String(r.product_code ?? '') }}>{r.product_code ?? '-'}</Typography.Text>
        ),
      },
      { title: t('app.kuaizhizao.packingBinding.colProductName'), dataIndex: 'product_name' },
      {
        title: t('app.kuaizhizao.packingBinding.colProductSerialNo'),
        dataIndex: 'product_serial_no',
        render: (val) => val || '-',
      },
      {
        title: t('app.kuaizhizao.packingBinding.colSerialNumbers'),
        dataIndex: 'serial_numbers',
        render: (_, r) =>
          Array.isArray(r.serial_numbers) && r.serial_numbers.length
            ? r.serial_numbers.join(', ')
            : '-',
      },
      {
        title: t('app.kuaizhizao.packingBinding.colSealStatus'),
        dataIndex: 'seal_status',
        render: (_, r) =>
          r.seal_status === 'sealed'
            ? t('app.kuaizhizao.packingBinding.statusSealed')
            : t('app.kuaizhizao.packingBinding.statusBound'),
      },
      {
        title: t('app.kuaizhizao.packingBinding.colPackingLevel'),
        dataIndex: 'packing_level',
        render: (v) => {
          if (v === 'inner') return t('app.kuaizhizao.packingBinding.levelInner');
          if (v === 'pallet') return t('app.kuaizhizao.packingBinding.levelPallet');
          return t('app.kuaizhizao.packingBinding.levelCarton');
        },
      },
      {
        title: t('app.kuaizhizao.packingBinding.colParentBoxNo'),
        dataIndex: 'parent_box_no',
        render: (val) => val || '-',
      },
      {
        title: t('app.kuaizhizao.packingBinding.colPalletNo'),
        dataIndex: 'pallet_no',
        render: (val) => val || '-',
      },
      { title: t('app.kuaizhizao.packingBinding.colPackingQty'), dataIndex: 'packing_quantity', valueType: 'digit' },
      {
        title: t('app.kuaizhizao.packingBinding.colPackingMaterialCode'),
        dataIndex: 'packing_material_code',
        render: (val) => val || '-',
      },
      {
        title: t('app.kuaizhizao.packingBinding.colPackingMaterialName'),
        dataIndex: 'packing_material_name',
        render: (val) => val || '-',
      },
      {
        title: t('app.kuaizhizao.packingBinding.colBindingMethod'),
        dataIndex: 'binding_method',
        render: (_, r) => bindingMethodTag(r.binding_method),
      },
      {
        title: t('app.kuaizhizao.packingBinding.colBarcode'),
        dataIndex: 'barcode',
        render: (val) =>
          val ? <Typography.Text copyable={{ text: String(val) }}>{String(val)}</Typography.Text> : '-',
      },
      {
        title: t('app.kuaizhizao.packingBinding.colFinishedGoodsReceiptId'),
        dataIndex: 'finished_goods_receipt_id',
        render: (val) => (val != null ? String(val) : '-'),
      },
      {
        title: t('app.kuaizhizao.packingBinding.colSalesDeliveryId'),
        dataIndex: 'sales_delivery_id',
        render: (val) => (val != null ? String(val) : '-'),
      },
      { title: t('app.kuaizhizao.packingBinding.colBoundBy'), dataIndex: 'bound_by_name' },
      { title: t('app.kuaizhizao.packingBinding.colBoundAt'), dataIndex: 'bound_at', valueType: 'dateTime' },
      {
        title: t('common.remark'),
        dataIndex: 'remarks',
        span: 3,
      },
    ] as ProDescriptionsItemProps<PackingBinding>[]),
    [bindingMethodTag, t],
  );

  const renderPbRowActionNodes = useCallback(
    (record: PackingBinding): React.ReactNode[] => {
      const nodes: React.ReactNode[] = [];
      nodes.push(
        <Button {...rowActionKind('read')}
          key="detail"
          type="link"
          size="small"
          icon={<EyeOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            void handleDetail(record);
          }}
        >
          {t('common.detail')}
        </Button>
      );
      if (record.capabilities?.update?.allowed !== false && record.seal_status !== 'sealed') {
        nodes.push(
          <Button {...rowActionKind('update')}
            key="edit"
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
      if (record.capabilities?.seal?.allowed !== false && record.seal_status !== 'sealed') {
        nodes.push(
          <Popconfirm
            key="seal"
            title={t('app.kuaizhizao.packingBinding.confirmSeal')}
            onConfirm={() => void handleSeal(record)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Button
              {...rowActionKind('update')}
              type="link"
              size="small"
              onClick={(e) => e.stopPropagation()}
            >
              {t('app.kuaizhizao.packingBinding.seal')}
            </Button>
          </Popconfirm>,
        );
      }
      if (record.capabilities?.delete?.allowed !== false) {
        nodes.push(
          <Popconfirm {...rowActionKind('delete')}
            key="del"
            title={t('app.kuaizhizao.packingBinding.confirmDeleteOne')}
            onConfirm={() => void handleDeleteOne(record)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Button
              type="link"
              size="small"
              danger
              icon={<DeleteOutlined />}
              onClick={(e) => e.stopPropagation()}
            >
              {t('common.delete')}
            </Button>
          </Popconfirm>
        );
      }
      return nodes;
    },
    [handleDetail, handleEdit, handleSeal, t],
  );

  const packingBindingMethodValueEnum = useMemo(() => buildPackingBindingMethodValueEnum(t), [t]);
  const packingBindingSourceValueEnum = useMemo(() => buildPackingBindingSourceValueEnum(t), [t]);

  const columns: ProColumns<PackingBinding>[] = useMemo(
    () => alignProColumns<PackingBinding>([
      {
        title: t('app.kuaizhizao.packingBinding.colBoundAt'),
        dataIndex: 'bound_at_range',
        valueType: 'dateRange',
        hideInTable: true,
        hideInSearch: false,
        fieldProps: {
          placeholder: [t('app.kuaizhizao.quotation.dateRangeStart'), t('app.kuaizhizao.quotation.dateRangeEnd')],
        },
        formItemProps: formDateRangeFormItemProps,
      },
      {
        title: t('common.createdAt'),
        dataIndex: 'created_at_range',
        valueType: 'dateRange',
        hideInTable: true,
        hideInSearch: false,
        fieldProps: {
          placeholder: [t('app.kuaizhizao.quotation.dateRangeStart'), t('app.kuaizhizao.quotation.dateRangeEnd')],
        },
        formItemProps: formDateRangeFormItemProps,
      },
      {
        title: t('app.kuaizhizao.packingBinding.colBoxNo'),
        dataIndex: 'box_no',
        width: 168,
        minWidth: 168,
        uniTableKeepWidth: true,
        uniTablePrimaryFlex: false,
        resizable: false,
        ellipsis: true,
        fixed: 'left',
        sorter: true,
        hideInSearch: false,
        render: (_, r) => (
          <Typography.Text copyable={{ text: String(r.box_no ?? '') }} ellipsis>
            {r.box_no ?? '-'}
          </Typography.Text>
        ),
      },
      {
        title: `${t('app.kuaizhizao.packingBinding.colProductName')}/${t('app.kuaizhizao.packingBinding.colProductCode')}`,
        key: 'product_stacked',
        dataIndex: 'product_name',
        // 无行项目明细：产品名码叠列吃掉视口剩余（RemainderFlex）
        minWidth: 200,
        uniTablePrimaryFlex: true,
        uniTableRemainderFlex: true,
        resizable: false,
        ellipsis: false,
        sorter: true,
        hideInSearch: true,
        render: (_, r) => (
          <MaterialStackedCell material_name={r.product_name} material_code={r.product_code} />
        ),
      },
      {
        title: t('app.kuaizhizao.packingBinding.colProductCode'),
        dataIndex: 'product_code',
        hideInTable: true,
        sorter: true,
        hideInSearch: false,
      },
      {
        title: t('app.kuaizhizao.packingBinding.colProductName'),
        dataIndex: 'product_name',
        hideInTable: true,
        sorter: true,
        hideInSearch: false,
      },
      {
        title: t('app.kuaizhizao.packingBinding.colProductSerialNo'),
        dataIndex: 'product_serial_no',
        width: 140,
        minWidth: 140,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        sorter: true,
        hideInSearch: false,
        render: (_, r) => r.product_serial_no || '-',
      },
      {
        title: t('app.kuaizhizao.packingBinding.colPackingQty'),
        dataIndex: 'packing_quantity',
        width: 100,
        minWidth: 100,
        uniTableKeepWidth: true,
        resizable: false,
        align: 'right',
        sorter: true,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.packingBinding.colPackingMaterial'),
        dataIndex: 'packing_material_name',
        width: 140,
        minWidth: 140,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        hideInSearch: false,
        render: (_, r) => r.packing_material_name || '-',
      },
      {
        title: t('app.kuaizhizao.packingBinding.colBindingMethod'),
        dataIndex: 'binding_method',
        width: 100,
        minWidth: 100,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: false,
        valueType: 'select',
        valueEnum: packingBindingMethodValueEnum,
        render: (_, r) => bindingMethodTag(r.binding_method),
      },
      {
        title: t('app.kuaizhizao.packingBinding.colSealStatus'),
        dataIndex: 'seal_status',
        width: 96,
        minWidth: 96,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: false,
        valueType: 'select',
        valueEnum: {
          bound: { text: t('app.kuaizhizao.packingBinding.statusBound') },
          sealed: { text: t('app.kuaizhizao.packingBinding.statusSealed') },
        },
        render: (_, r) =>
          r.seal_status === 'sealed' ? (
            <MarkerTag color="success">{t('app.kuaizhizao.packingBinding.statusSealed')}</MarkerTag>
          ) : (
            <MarkerTag color="processing">{t('app.kuaizhizao.packingBinding.statusBound')}</MarkerTag>
          ),
      },
      {
        title: t('app.kuaizhizao.packingBinding.colPackingLevel'),
        dataIndex: 'packing_level',
        width: 90,
        minWidth: 90,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        render: (v) => {
          if (v === 'inner') return t('app.kuaizhizao.packingBinding.levelInner');
          if (v === 'pallet') return t('app.kuaizhizao.packingBinding.levelPallet');
          return t('app.kuaizhizao.packingBinding.levelCarton');
        },
      },
      {
        title: t('app.kuaizhizao.packingBinding.colSource'),
        dataIndex: 'source_type',
        width: 110,
        minWidth: 110,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: false,
        valueType: 'select',
        valueEnum: packingBindingSourceValueEnum,
        render: (_, r) => bindingSourceTag(r),
      },
      {
        title: `${t('app.kuaizhizao.packingBinding.colBoundBy')}/${t('app.kuaizhizao.packingBinding.colBoundAt')}`,
        key: 'bound_stacked',
        dataIndex: 'bound_at',
        width: 168,
        minWidth: 168,
        uniTableKeepWidth: true,
        resizable: false,
        sorter: true,
        hideInSearch: true,
        render: (_, r) => (
          <UniTableStackedPrimaryCell
            primary={r.bound_by_name?.trim() || '-'}
            secondary={r.bound_at ? formatDateTime(r.bound_at, 'YYYY-MM-DD HH:mm') : '-'}
            secondaryCopyable={false}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.packingBinding.colBoundBy'),
        dataIndex: 'bound_by_name',
        hideInTable: true,
        sorter: true,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.packingBinding.colBoundAt'),
        dataIndex: 'bound_at',
        valueType: 'dateTime',
        hideInTable: true,
        sorter: true,
        hideInSearch: true,
      },
      ...buildDocumentAuditColumns<PackingBinding>(t),
      {
        title: t('app.kuaizhizao.packingBinding.colLifecycle'),
        key: 'lifecycle',
        dataIndex: 'lifecycle_stage',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) => {
          const lifecycle = getPackingBindingLifecycle(record as Record<string, unknown>);
          return (
            <UniLifecycle
              percent={lifecycle.percent}
              stageName={lifecycle.stageName}
              status={lifecycle.status}
              subStages={lifecycle.subStages}
              showLabel
              size="small"
              showCircleTooltip={false}
            />
          );
        },
      },
      {
        title: t('common.actions'),
        key: 'option',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) =>
          renderPbRowActions(renderPbRowActionNodes(record), `pb-${record.id ?? 'row'}`),
      },
    ], SALES_DOC_LIST_FIELD_RANK),
    [bindingMethodTag, bindingSourceTag, packingBindingMethodValueEnum, packingBindingSourceValueEnum, renderPbRowActionNodes, t],
  );

  const handleRequest = async (
    params: any,
    sort: Record<string, 'ascend' | 'descend' | null>,
    _filter: Record<string, React.ReactText[] | null>,
    searchFormValues?: Record<string, unknown>,
  ) => {
    try {
      const apiParams = resolvePackingBindingListApiParams(params, sort, searchFormValues) as Parameters<
        typeof packingBindingApi.listPage
      >[0];

      const result = (await packingBindingApi.listPage(apiParams)) as PackingBindingPageResult;
      const data = Array.isArray(result?.data) ? result.data : [];
      return {
        data,
        success: result.success !== false,
        total: Number(result?.total || 0),
      };
    } catch (error: any) {
      messageApi.error(getErrorMessage(error, 'app.kuaizhizao.packingBinding.fetchListFailed'));
      return {
        data: [],
        success: false,
        total: 0,
      };
    }
  };

  const statCards: StatCard[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.packingBinding.statTotal'),
        value: localStats.total,
        valueStyle: { color: token.colorPrimary },
        backgroundChart: <SimpleSparkline data={PB_STAT_SPARK_1} color={token.colorPrimary} />,
      },
      {
        title: t('app.kuaizhizao.packingBinding.statScan'),
        value: localStats.scan,
        valueStyle: { color: token.colorSuccess },
        backgroundChart: <SimpleSparkline data={PB_STAT_SPARK_2} color={token.colorSuccess} />,
      },
      {
        title: t('app.kuaizhizao.packingBinding.statManual'),
        value: localStats.manual,
        valueStyle: { color: token.colorWarning },
        backgroundChart: <SimpleSparkline data={PB_STAT_SPARK_3} color={token.colorWarning} />,
      },
    ],
    [localStats.manual, localStats.scan, localStats.total, t, token.colorPrimary, token.colorSuccess, token.colorWarning],
  );

  const taskPoolColumns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.packingBinding.taskPoolColSource'),
        dataIndex: 'source_type',
        width: 110,
        render: (v: string) =>
          v === 'finished_goods_receipt'
            ? t('app.kuaizhizao.packingBinding.sourceFinishedGoodsReceipt')
            : t('app.kuaizhizao.packingBinding.sourceSalesDelivery'),
      },
      {
        title: t('app.kuaizhizao.packingBinding.taskPoolColDeliveryCode'),
        dataIndex: 'doc_code',
        width: 180,
        render: (_: unknown, row: PackingTaskPoolItem) => row.doc_code || row.delivery_code,
      },
      {
        title: t('app.kuaizhizao.packingBinding.taskPoolColCustomer'),
        dataIndex: 'party_name',
        width: 160,
        render: (_: unknown, row: PackingTaskPoolItem) => row.party_name || row.customer_name || '-',
      },
      {
        title: t('app.kuaizhizao.packingBinding.remainingQty'),
        dataIndex: 'remaining_quantity',
        width: 100,
        render: (v: unknown, row: PackingTaskPoolItem) =>
          `${row.packed_quantity ?? 0}/${row.required_quantity ?? '-'}（剩 ${v ?? '-'}）`,
      },
      {
        title: t('app.kuaizhizao.packingBinding.boxCount'),
        dataIndex: 'box_count',
        width: 80,
      },
      { title: t('app.kuaizhizao.packingBinding.taskPoolColDocStatus'), dataIndex: 'status', width: 100 },
      {
        title: t('common.updatedAt'),
        dataIndex: 'updated_at',
        render: (v: string) => (v ? formatDateTime(v, 'YYYY-MM-DD HH:mm:ss') : '-'),
      },
      {
        title: t('common.actions'),
        dataIndex: 'actions',
        width: 120,
        fixed: 'right' as const,
        render: (_: unknown, row: PackingTaskPoolItem) => (
          <Button
            {...rowActionKind('execute')}
            {...rowActionLabelKeep()}
            type="link"
            size="small"
            disabled={!packingBindingPerms.canCreate}
            onClick={() =>
              void openCreateFromSource(
                row.source_type === 'finished_goods_receipt' ? 'finished_goods_receipt' : 'sales_delivery',
                row.id,
              )
            }
          >
            {t('app.kuaizhizao.packingBinding.actionGoBind')}
          </Button>
        ),
      },
    ],
    [openCreateFromSource, packingBindingPerms.canCreate, t],
  );

  const timeconfigBasicItems = useDetailDrawerDescriptionItems(
    detailBaseColumns,
    currentBinding,
    'packing_binding',
  );

  return (
    <>
      <ListPageTemplate statCards={statCards}>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('app.kuaizhizao.packingBinding.scopeAlert')}
        />
        <UniTable<PackingBinding>
          headerTitle={t('app.kuaizhizao.packingBinding.title')}
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.packingBinding)}
          columnPersistenceId="apps.kuaizhizao.pages.production-execution.packing-binding-width-v2"
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch={true}
          skipFuzzyPinyinClientFilter
          pinnedTabsField="binding_method"
          pinnedTabsValueEnum={packingBindingMethodValueEnum}
          request={handleRequest}
          onTableDataChange={(rows) => {
            tableRowsRef.current = rows;
          }}
        enableRowSelection={true}
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          showDeleteButton={true}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) => t('app.kuaizhizao.packingBinding.confirmBatchDelete', { count })}
          toolBarActionsAfterCreate={[
            <Button {...rowActionKind('read')} key="task-pool" onClick={() => void openTaskPool()}>
              {t('app.kuaizhizao.packingBinding.taskPoolButton')}
            </Button>,
          ]}
          toolBarActionsAfterDelete={[
            <UniBatchButton
              key="packing-binding-batch-qrcode"
              selectedRowKeys={selectedRowKeys}
              size="medium"
              icon={<QrcodeOutlined />}
              disabled={
                selectedBindingsForBatch.length > 0 &&
                !packingBindingBatchPrintAllowed(
                  selectedBindingsForBatch,
                  packingBindingPerms.canPrint,
                )
              }
              onAction={() => void handleBatchGenerateQRCode()}
            >
              {t('app.kuaizhizao.packingBinding.batchGenerateQrcode')}
            </UniBatchButton>,
          ]}
          onRow={(record) => ({
            onClick: () => void handleDetail(record),
            style: { cursor: 'pointer' },
          })}
        />
      </ListPageTemplate>

      <FormModalTemplate
        title={t('app.kuaizhizao.packingBinding.createTitle')}
        open={createModalVisible}
        onClose={closeCreateModal}
        onFinish={handleCreateSubmit}
        formRef={createFormRef}
        loading={createSourceLoading}
        {...MODAL_CONFIG}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('app.kuaizhizao.packingBinding.sourceHint', {
            source: createSourceType === 'sales_delivery'
              ? t('app.kuaizhizao.packingBinding.sourceSalesDelivery')
              : t('app.kuaizhizao.packingBinding.sourceFinishedGoodsReceipt'),
            id: createSourceId ?? '-',
          })}
        />
        <ProFormSelect
          name="source_item_key"
          label={t('app.kuaizhizao.packingBinding.fieldSourceItem')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderSourceItem')}
          rules={[{ required: true, message: t('app.kuaizhizao.packingBinding.ruleSelectSourceItem') }]}
          options={createSourceItems.map((item) => ({
            label: item.remainingQuantity != null
              ? `${item.productCode || '-'} / ${item.productName || '-'}（${t('app.kuaizhizao.packingBinding.remainingQty')} ${item.remainingQuantity}）`
              : `${item.productCode || '-'} / ${item.productName || '-'}`,
            value: item.key,
          }))}
          fieldProps={{
            showSearch: true,
            onChange: (value) => handleSourceItemChange(value as string),
          }}
        />
        <ProFormText name="source_line_id" hidden />
        <ProFormText
          name="product_code"
          label={t('app.kuaizhizao.packingBinding.colProductCode')}
          fieldProps={{ readOnly: true }}
        />
        <ProFormText
          name="product_name"
          label={t('app.kuaizhizao.packingBinding.colProductName')}
          fieldProps={{ readOnly: true }}
        />
        <ProFormText name="product_serial_no" label={t('app.kuaizhizao.packingBinding.colProductSerialNo')} />
        <ProFormText
          name="serial_numbers"
          label={t('app.kuaizhizao.packingBinding.colSerialNumbers')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderSerialNumbers')}
        />
        <UniMaterialSelect
          name="packing_material_id"
          label={t('app.kuaizhizao.packingBinding.colPackingMaterialName')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderPackingMaterial')}
          fillMapping={{
            packing_material_code: 'mainCode',
            packing_material_name: 'name',
          }}
          showQuickCreate={false}
        />
        <ProFormText name="packing_material_code" hidden />
        <ProFormText name="packing_material_name" hidden />
        <ProFormDigit
          name="packing_quantity"
          label={t('app.kuaizhizao.packingBinding.fieldPackingQty')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderPackingQty')}
          rules={createPackingQuantityRules}
          min={0.01}
          max={createLineRemaining ?? MAX_PACKING_QUANTITY}
          fieldProps={{ precision: 2, step: 0.01 }}
        />
        <ProFormText
          name="box_no"
          label={t('app.kuaizhizao.packingBinding.fieldBoxNo')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderBoxNo')}
        />
        <ProFormSelect
          name="packing_level"
          label={t('app.kuaizhizao.packingBinding.colPackingLevel')}
          initialValue="carton"
          options={[
            { label: t('app.kuaizhizao.packingBinding.levelCarton'), value: 'carton' },
            { label: t('app.kuaizhizao.packingBinding.levelInner'), value: 'inner' },
            { label: t('app.kuaizhizao.packingBinding.levelPallet'), value: 'pallet' },
          ]}
        />
        <ProFormText name="parent_box_no" label={t('app.kuaizhizao.packingBinding.colParentBoxNo')} />
        <ProFormText name="pallet_no" label={t('app.kuaizhizao.packingBinding.colPalletNo')} />
        <ProFormText
          name="barcode"
          label={t('app.kuaizhizao.packingBinding.colBarcode')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderBarcodeScan')}
        />
        <ProFormTextArea
          name="remarks"
          label={t('common.remark')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderRemarks')}
          fieldProps={{ rows: 3 }}
        />
        <ProFormText name="product_id" hidden />
      </FormModalTemplate>

      <FormModalTemplate
        title={t('app.kuaizhizao.packingBinding.editTitle')}
        open={editModalVisible}
        onClose={() => {
          setEditModalVisible(false);
          setCurrentBindingId(null);
          formRef.current?.resetFields();
        }}
        onFinish={handleEditSubmit}
        formRef={formRef}
        {...MODAL_CONFIG}
      >
        <ProFormDigit
          name="packing_quantity"
          label={t('app.kuaizhizao.packingBinding.fieldPackingQty')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderPackingQty')}
          rules={packingQuantityRules}
          min={0.01}
          max={MAX_PACKING_QUANTITY}
          fieldProps={{ precision: 2, step: 0.01 }}
        />
        <ProFormText
          name="product_serial_no"
          label={t('app.kuaizhizao.packingBinding.colProductSerialNo')}
        />
        <ProFormText
          name="serial_numbers"
          label={t('app.kuaizhizao.packingBinding.colSerialNumbers')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderSerialNumbers')}
        />
        <UniMaterialSelect
          name="packing_material_id"
          label={t('app.kuaizhizao.packingBinding.colPackingMaterialName')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderPackingMaterial')}
          fillMapping={{
            packing_material_code: 'mainCode',
            packing_material_name: 'name',
          }}
          showQuickCreate={false}
        />
        <ProFormText name="packing_material_code" hidden />
        <ProFormText name="packing_material_name" hidden />
        <ProFormText
          name="box_no"
          label={t('app.kuaizhizao.packingBinding.fieldBoxNo')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderBoxNo')}
        />
        <ProFormTextArea
          name="remarks"
          label={t('common.remark')}
          placeholder={t('app.kuaizhizao.packingBinding.placeholderRemarks')}
          fieldProps={{ rows: 3 }}
        />
        <DocumentAttachmentsField category="packing_binding_attachments" />
      </FormModalTemplate>

      <DetailDrawerTemplate
        title={`${t('app.kuaizhizao.packingBinding.detailTitle')}${currentBinding?.box_no ? ` - ${currentBinding.box_no}` : ''}`}
        open={detailDrawerVisible}
        zIndex={packingBindingDetailDrawerZIndex}
        size={DRAWER_CONFIG.HALF_WIDTH}
        onClose={() => {
          setDetailDrawerVisible(false);
          setCurrentBinding(null);
        }}
        extra={
          currentBinding ? (
            <Space>
              {currentBinding.sales_delivery_id != null ? (
                <Button onClick={() => void openAsn(Number(currentBinding.sales_delivery_id))}>
                  {t('app.kuaizhizao.packingBinding.viewAsn')}
                </Button>
              ) : null}
              {currentBinding.capabilities?.seal?.allowed !== false
                && currentBinding.seal_status !== 'sealed' ? (
                <Popconfirm
                  title={t('app.kuaizhizao.packingBinding.confirmSeal')}
                  onConfirm={() => void handleSeal(currentBinding)}
                  okText={t('common.confirm')}
                  cancelText={t('common.cancel')}
                >
                  <Button type="primary">{t('app.kuaizhizao.packingBinding.seal')}</Button>
                </Popconfirm>
              ) : null}
              {currentBinding.capabilities?.update?.allowed !== false
                && currentBinding.seal_status !== 'sealed' ? (
                <Button icon={<EditOutlined />} onClick={() => void handleEdit(currentBinding)}>
                  {t('common.edit')}
                </Button>
              ) : null}
              {currentBinding.capabilities?.delete?.allowed !== false ? (
                <Popconfirm
                  title={t('app.kuaizhizao.packingBinding.confirmDeleteOne')}
                  onConfirm={() => void handleDeleteOne(currentBinding)}
                  okText={t('common.confirm')}
                  cancelText={t('common.cancel')}
                >
                  <Button danger icon={<DeleteOutlined />}>
                    {t('common.delete')}
                  </Button>
                </Popconfirm>
              ) : null}
            </Space>
          ) : null
        }
        collaborationTitleSuffix={
          currentBinding && packingShowNextInTitle ? (
            <Typography.Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
              {t('common.next')}：
              {packingNextSteps!.join(t('components.uniLifecycle.nextStepSeparator'))}
            </Typography.Text>
          ) : undefined
        }
        basic={
          currentBinding ? (
            <Descriptions
              column={3}
              size="small"
              items={timeconfigBasicItems}
            />
          ) : undefined
        }
        basicExtra={
          packingBindingBoxQrcodeData && currentBinding?.capabilities?.print?.allowed !== false ? (
            <div style={{ minWidth: 160, textAlign: 'center' }}>
              <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
                {t('app.kuaizhizao.packingBinding.detailBoxQrcode')}
              </Typography.Text>
              <Suspense fallback={<Spin size="small" />}>
                <LazyQRCodeGenerator
                  qrcodeType="BOX"
                  data={packingBindingBoxQrcodeData}
                  autoGenerate
                  size={6}
                  noCard
                  showCardTitle={false}
                />
              </Suspense>
            </div>
          ) : undefined
        }
        collaboration={
          currentBinding && (packingDetailLifecycle?.mainStages ?? []).length > 0 ? (
            <UniLifecycleStepper
              steps={packingDetailLifecycle!.mainStages ?? []}
              status={packingDetailLifecycle!.status}
              showLabels
              nextStepSuggestions={packingDetailLifecycle!.nextStepSuggestions}
              hideNextStepSuggestions={packingShowNextInTitle}
            />
          ) : null
        }
        timeline={
          currentBinding ? (
            packingTracking.data && !packingTracking.loading ? (
              <DocumentTrackingTimelineBody data={packingTracking.data} />
            ) : packingTracking.error ? (
              <Typography.Text type="danger">{packingTracking.error}</Typography.Text>
            ) : !packingTracking.loading ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('components.documentTrackingPanel.noOperations')} />
            ) : null
          ) : undefined
        }
        traceDocument={
          currentBinding?.id != null
            ? {
                documentType: 'packing_binding',
                documentId: currentBinding.id,
                selfDocumentId: currentBinding.id,
                renderBriefActions: (doc) => (
                  <WarehouseTraceBriefPrimaryActions
                    doc={doc}
                    t={t}
                    navigate={navigate}
                    closeDrawer={() => {
                      setDetailDrawerVisible(false);
                      setCurrentBinding(null);
                    }}
                  />
                ),
              }
            : undefined
        }
      />

      <Modal
        title={t('app.kuaizhizao.packingBinding.taskPoolTitle')}
        open={taskPoolVisible}
        onCancel={() => setTaskPoolVisible(false)}
        footer={null}
        width={920}
      >
        <Alert
          showIcon
          type="info"
          title={t('app.kuaizhizao.packingBinding.taskPoolSummary', {
            pendingReview: taskPool.pending_review,
            pendingOutbound: taskPool.pending_outbound,
            pendingReceipt: taskPool.pending_receipt ?? 0,
            total: taskPool.total,
          })}
          style={{ marginBottom: 12 }}
        />
        <Table<PackingTaskPoolItem>
          rowKey="id"
          loading={taskPoolLoading}
          dataSource={taskPool.items}
          pagination={false}
          size="small"
          columns={taskPoolColumns}
          scroll={{ x: 960 }}
        />
      </Modal>

      <Modal
        title={t('app.kuaizhizao.packingBinding.asnTitle')}
        open={asnVisible}
        onCancel={() => {
          setAsnVisible(false);
          setAsnData(null);
        }}
        footer={null}
        width={960}
      >
        <Spin spinning={asnLoading}>
          {asnData ? (
            <>
              <Alert
                showIcon
                type="info"
                style={{ marginBottom: 12 }}
                title={t('app.kuaizhizao.packingBinding.asnSummary', {
                  code: asnData.delivery_code || asnData.sales_delivery_id,
                  customer: asnData.customer_name || '-',
                  boxes: asnData.box_count,
                  qty: asnData.total_quantity,
                })}
              />
              <Table
                rowKey={(r) => String(r.box_no ?? r.id ?? Math.random())}
                size="small"
                pagination={false}
                dataSource={asnData.lines || []}
                columns={[
                  {
                    title: t('app.kuaizhizao.packingBinding.colPalletNo'),
                    dataIndex: 'pallet_no',
                    width: 120,
                    render: (v) => v || '-',
                  },
                  {
                    title: t('app.kuaizhizao.packingBinding.colParentBoxNo'),
                    dataIndex: 'parent_box_no',
                    width: 120,
                    render: (v) => v || '-',
                  },
                  {
                    title: t('app.kuaizhizao.packingBinding.colBoxNo'),
                    dataIndex: 'box_no',
                    width: 140,
                  },
                  {
                    title: t('app.kuaizhizao.packingBinding.colPackingLevel'),
                    dataIndex: 'packing_level',
                    width: 90,
                  },
                  {
                    title: t('app.kuaizhizao.packingBinding.colProductCode'),
                    dataIndex: 'product_code',
                    width: 120,
                  },
                  {
                    title: t('app.kuaizhizao.packingBinding.colPackingQty'),
                    dataIndex: 'packing_quantity',
                    width: 90,
                    align: 'right' as const,
                  },
                  {
                    title: t('app.kuaizhizao.packingBinding.colSealStatus'),
                    dataIndex: 'seal_status',
                    width: 90,
                    render: (v: string) =>
                      v === 'sealed'
                        ? t('app.kuaizhizao.packingBinding.statusSealed')
                        : t('app.kuaizhizao.packingBinding.statusBound'),
                  },
                ]}
                scroll={{ x: 880 }}
              />
            </>
          ) : null}
        </Spin>
      </Modal>

      <PackingBindingQrcodePreviewModal
        open={qrcodePreviewOpen}
        loading={qrcodePreviewLoading}
        items={qrcodePreviewItems}
        failedMessages={qrcodePreviewFailed}
        onClose={() => {
          setQrcodePreviewOpen(false);
          setQrcodePreviewItems([]);
          setQrcodePreviewFailed([]);
        }}
      />
    </>
  );
};

export default PackingBindingPage;
