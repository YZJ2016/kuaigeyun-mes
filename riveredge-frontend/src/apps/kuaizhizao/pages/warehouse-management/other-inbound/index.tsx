/**
 * 其他入库单管理页面
 *
 * 提供其他入库单的创建、查看、确认和管理功能（原因类型见数据字典 INBOUND_REASON_TYPE）
 * 支持批号规则选择与自动生成批号
 *
 * @author RiverEdge Team
 * @date 2026-02-19
 */

import React, { useRef, useState, useEffect, useCallback, useMemo } from 'react';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import OtherInboundEditModal from '../inbound/OtherInboundEditModal';
import { isInboundEditable, type InboundHubOrder } from '../inbound/inboundHubTypes';
import { readExternalWithdrawMessage } from '../shared/externalWithdrawMessage';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import {
  CustomFieldsFormSection,
  CustomFieldsDetailSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';
import { useNavigate } from 'react-router-dom';
import { ActionType, ProColumns, ProDescriptionsItemProps, ProFormItem, ProFormTextArea } from '@ant-design/pro-components';
import { App, Button, Tag, Space, Modal, Table, Form as AntForm, InputNumber, Input, Row, Col, Select, Typography, Descriptions } from 'antd';
import { PlusOutlined, EyeOutlined, CheckCircleOutlined, DeleteOutlined, ThunderboltOutlined, ShoppingOutlined, RollbackOutlined } from '@ant-design/icons';
import { UniCapabilityBatchButton } from '../../../../../components/uni-batch';
import { UniTable, type UniTableRequestMeta} from '../../../../../components/uni-table';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import { UniMaterialBatchPicker } from '../../../../../components/uni-material-batch-picker';
import { MaterialUnitSelect } from '../../../../../components/material-unit-select';
import { buildDocumentLineDualQuantityPairColumns } from '../../../../../components/quantity-with-unit';
import { pickDocumentLineDualQuantityFields } from '../../../../../utils/materialDualQuantity';
import { resolveMaterialScenarioUnit } from '../../../../../utils/materialScenarioUnit';
import { MaterialUnitLabel } from '../../../../../components/material-unit-label';
import type { Material } from '../../../../master-data/types/material';
import { UniWarehouseSelect } from '../../../../../components/uni-warehouse-select';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import { UniTableDetailHeader } from '../../../../../components/uni-table-detail/UniTableDetail';
import CodeField from '../../../../../components/code-field';
import { getDataDictionaryByCode, getDictionaryItemList } from '../../../../../services/dataDictionary';
import {   useDetailDrawerDescriptionItems, detailDrawerBasicColumn, DetailDrawerTemplate, DRAWER_CONFIG, FormModalTemplate, ListPageTemplate, MODAL_CONFIG, WAREHOUSE_DETAIL_TABLE_STYLES } from '../../../../../components/layout-templates';
import { warehouseApi } from '../../../services/production';
import { getOtherInboundLifecycle } from '../../../utils/otherInboundLifecycle';
import { UniLifecycle, UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { useNumericPrecision } from '../../../../../hooks/useNumericPrecision';
import { warehouseApi as masterDataWarehouseApi } from '../../../../master-data/services/warehouse';
import { materialApi, materialBatchApi, materialSerialApi, MATERIAL_SERIAL_GENERATE_MAX_COUNT } from '../../../../master-data/services/material';
import { SerialNumbersImportTrigger } from '../../../../../components/serial-numbers-import';
import { useWarehouseLocationOptions } from '../../../hooks/useWarehouseLocationOptions';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import { normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { rowActionKind, rowActionLabelKeep } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import { renderWarehouseReasonTypeMarkerTag } from '../shared/warehouseMarkerTags';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { useKuaizhizaoPrintModal } from '../../../hooks/useKuaizhizaoPrintModal';
import { formatDateTime, formatQuantity, todaySiteDateString } from '../../../../../utils/format';
import { fetchAllListItems } from '../../../../../utils/fetchAllListPages';
import {
  enrichStandaloneDocsWithDetail,
  exportWarehouseDocLinesXlsx,
  filterWarehouseFlatRowsByExportKeys,
  flattenStandaloneWarehouseDocsForExport,
  resolveWarehouseListExportHeaders,
} from '../shared/warehouseDocListExport';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { alignDescriptionColumns, alignProColumns } from '../../sales-management/shared/documentFieldAlignment';
import { WAREHOUSE_DOC_LIST_FIELD_RANK } from '../shared/warehouseDocListFieldRank';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import { createListAuditPhaseColumn } from '../../sales-management/shared/listAuditPhaseColumn';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../../sales-management/shared/documentLineMaterialsPreview';
import {
  WAREHOUSE_DOC_PINNED_STATUS_FIELD,
  buildOtherInboundStatusValueEnum,
  normalizeWarehouseListResponse,
  resolveWarehouseDocListParams,
} from '../../../utils/warehouseListCore';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { SyncPushHubButton } from '../../../../../components/sync-push-hub';
import { useToolbarSyncPushFlags } from '../../../../../hooks/useToolbarSyncPushFlags';
import OtherInboundDocumentPushPanel from './OtherInboundDocumentPushPanel';
import { runInboundHubConfirmFromRecord } from '../inbound/inboundHubRunConfirm';
import { formatApiErrorDetail } from '../../../../../services/api';

const REASON_TYPES_FALLBACK = [
  { value: '盘盈', label: '盘盈' },
  { value: '调拨', label: '调拨' },
  { value: '样品', label: '样品' },
  { value: '报废', label: '报废' },
  { value: '生产完工入库', label: '生产完工入库' },
  { value: '降级回用', label: '降级回用' },
  { value: '其他', label: '其他' },
];

const REASON_TYPE_I18N: Record<string, string> = {
  '盘盈': 'app.kuaizhizao.warehouseOtherInbound.reason.surplus',
  '调拨': 'app.kuaizhizao.warehouseOtherInbound.reason.transfer',
  '调拨入库': 'app.kuaizhizao.warehouseOtherInbound.reason.transfer',
  '样品': 'app.kuaizhizao.warehouseOtherInbound.reason.sample',
  '报废': 'app.kuaizhizao.warehouseOtherInbound.reason.scrap',
  '生产完工入库': 'app.kuaizhizao.warehouseOtherInbound.reason.productionFinished',
  '降级回用': 'app.kuaizhizao.warehouseOtherInbound.reason.downgrade',
  '其他': 'app.kuaizhizao.warehouseOtherInbound.reason.other',
};

function normalizeReasonTypeValue(value: string | undefined): string | undefined {
  if (!value) return value;
  const trimmed = value.trim();
  if (trimmed === '调拨入库') return '调拨';
  return trimmed;
}

function translateReasonTypeLabel(t: (key: string) => string, value: string | undefined): string {
  if (!value) return '-';
  const key = REASON_TYPE_I18N[value];
  return key ? t(key) : value;
}

interface OtherInbound {
  id?: number;
  tenant_id?: number;
  inbound_code?: string;
  reason_type?: string;
  reason_desc?: string;
  warehouse_id?: number;
  warehouse_name?: string;
  status?: string;
  receiver_id?: number;
  receiver_name?: string;
  receipt_time?: string;
  total_quantity?: number;
  total_items?: number;
  total_amount?: number;
  /** 列表「明细」列预览（仅 material_name） */
  items?: { material_name?: string }[];
  notes?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: any;
}

interface OtherInboundDetail extends OtherInbound {
  items?: OtherInboundItem[];
}

interface OtherInboundItem {
  id?: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_spec?: string;
  material_unit?: string;
  location_code?: string;
  inbound_quantity?: number;
  unit_price?: number;
  total_amount?: number;
  batch_number?: string;
  notes?: string;
}

const defaultInboundItem = {
  material_id: undefined,
  material_code: '',
  material_name: '',
  material_unit: '',
  inbound_quantity: 1,
  // 单价选填，不自动带物料采购价/成本
  unit_price: undefined as number | undefined,
  material_uuid: undefined,
  batch_managed: false,
  serial_managed: false,
  batch_rule_id: undefined,
  default_batch_rule_id: undefined,
  serial_rule_id: undefined,
  default_serial_rule_id: undefined,
  location_code: undefined,
  batch_number: undefined,
  serial_numbers: undefined,
};

const OTHER_INBOUND_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_other_inbounds';

const OtherInboundPage: React.FC = () => {
  const { t } = useTranslation();
  const otherInboundAuditColumn = useMemo(
    () => createListAuditPhaseColumn<Record<string, unknown>>({ t }),
    [t],
  );
  const trackingFlags = useWarehouseTrackingFlags();
  const { quantity: quantityDecimals, price: priceDecimals } = useNumericPrecision();
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const navigate = useNavigate();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>(null);

  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const toolbarSyncPush = useToolbarSyncPushFlags('kuaizhizao:other-inbound');
  const inboundPerms = useResourcePermissions('kuaizhizao:other-inbound');
  const canUpdateInbound = inboundPerms.canUpdate ?? false;
  const [editModalRecord, setEditModalRecord] = useState<InboundHubOrder | null>(null);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [inboundDetail, setInboundDetail] = useState<OtherInboundDetail | null>(null);

  const [createModalVisible, setCreateModalVisible] = useState(false);
  const formRef = useRef<any>(null);

  const {
    customFields: otherInboundFormCustomFields,
    customFieldValues: otherInboundFormCustomFieldValues,
    extractFormValues: extractOtherInboundFormValues,
    saveCustomFieldValues: saveOtherInboundCustomFieldValues,
    resetFieldValues: resetOtherInboundFormFieldValues,
  } = useCustomFields({
    tableName: OTHER_INBOUND_CUSTOM_FIELD_TABLE,
    loadWhenOpen: true,
    open: createModalVisible,
  });

  const {
    customFields: otherInboundListCustomFields,
    generateCustomFieldColumns: generateOtherInboundCustomFieldColumns,
    enrichRecordsWithCustomFields: enrichOtherInboundRecordsWithCustomFields,
    customFieldValues: otherInboundDetailCustomFieldValues,
    loadFieldValuesForDetail: loadOtherInboundFieldValuesForDetail,
    resetDetailFieldValues: resetOtherInboundDetailFieldValues,
  } = useCustomFieldsForList<OtherInbound>({ tableName: OTHER_INBOUND_CUSTOM_FIELD_TABLE });
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false);
  const [warehouseList, setWarehouseList] = useState<any[]>([]);
  const [reasonTypeOptions, setReasonTypeOptions] = useState<Array<{ label: string; value: string }>>([]);
  const [reasonTypeLoading, setReasonTypeLoading] = useState(false);
  const [generatingBatchIdx, setGeneratingBatchIdx] = useState<number | null>(null);
  const [generatingSerialIdx, setGeneratingSerialIdx] = useState<number | null>(null);
  const {
    selectedWarehouseId,
    locationOptions,
    updateSelectedWarehouseId,
    resetSelectedWarehouseId,
  } = useWarehouseLocationOptions();

  useEffect(() => {
    const load = async () => {
      try {
        const wh = await masterDataWarehouseApi.list({ limit: 1000, is_active: true });
        setWarehouseList(Array.isArray(wh) ? wh : (wh as any)?.items || []);
      } catch (e) {
        console.error('加载仓库/规则失败', e);
      }
    };
    load();
  }, []);

  const fallbackReasonTypeOptions = useMemo(
    () => REASON_TYPES_FALLBACK.map(({ value }) => ({ value, label: t(REASON_TYPE_I18N[value]) })),
    [t],
  );

  useEffect(() => {
    setReasonTypeOptions(fallbackReasonTypeOptions);
  }, [fallbackReasonTypeOptions]);

  useEffect(() => {
    const loadReasonType = async () => {
      setReasonTypeLoading(true);
      try {
        const dict = await getDataDictionaryByCode('INBOUND_REASON_TYPE');
        if (!dict?.uuid) {
          setReasonTypeOptions(fallbackReasonTypeOptions);
          return;
        }
        const items = await getDictionaryItemList(dict.uuid, true);
        const seen = new Set<string>();
        const options = items
          .sort((a, b) => a.sort_order - b.sort_order)
          .map((it) => {
            const value = normalizeReasonTypeValue(it.value) || String(it.value || '').trim();
            const label = String(it.label || value).trim() || value;
            return { label, value };
          })
          .filter((opt) => {
            if (!opt.value) return false;
            if (seen.has(opt.value)) return false;
            seen.add(opt.value);
            return true;
          });
        setReasonTypeOptions(options.length ? options : fallbackReasonTypeOptions);
      } catch {
        setReasonTypeOptions(fallbackReasonTypeOptions);
      } finally {
        setReasonTypeLoading(false);
      }
    };
    loadReasonType();
  }, [fallbackReasonTypeOptions]);

  const otherInboundCustomFieldColumns = generateOtherInboundCustomFieldColumns();
  const otherInboundStatusValueEnum = useMemo(() => buildOtherInboundStatusValueEnum(t), [t]);

  const executeConfirmInbound = useCallback(
    async (record: OtherInbound) => {
      if (record.id == null) return;
      try {
        const confirmResult = await runInboundHubConfirmFromRecord({
          t,
          record: { id: record.id, receipt_type: 'other_inbound' },
          trackingFlags,
        });
        messageApi.success(t('app.kuaizhizao.warehouseInbound.msg.otherInboundConfirmed'));
        if (confirmResult.externalPushMessage) {
          messageApi.warning(confirmResult.externalPushMessage);
        }
        invalidateMenuBadgeCounts();
        actionRef.current?.reload();
      } catch (error: unknown) {
        const err = error as { message?: string; response?: { data?: { detail?: unknown } } };
        messageApi.error(
          formatApiErrorDetail(err?.response?.data?.detail) ||
            err?.message ||
            t('app.kuaizhizao.warehouseInbound.msg.confirmFailed'),
        );
        throw error;
      }
    },
    [invalidateMenuBadgeCounts, messageApi, t, trackingFlags],
  );

  const columns: ProColumns<OtherInbound>[] = useMemo(
    () => alignProColumns<OtherInbound>([
      {
        title: t('common.updatedAt'),
        dataIndex: 'updated_at_range',
        valueType: 'dateRange',
        hideInTable: true,
        formItemProps: formDateRangeFormItemProps,
        search: { order: 10 } as ProColumns['search'],
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        valueType: 'select',
        valueEnum: otherInboundStatusValueEnum,
        hideInTable: true,
        search: { order: 20 } as ProColumns['search'],
      },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.reasonType'),
        dataIndex: 'reason_type',
        valueType: 'select',
        fieldProps: { options: reasonTypeOptions, loading: reasonTypeLoading },
        hideInTable: true,
        search: { order: 30 } as ProColumns['search'],
      },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.receiptTime'),
        dataIndex: 'doc_date_range',
        valueType: 'dateRange',
        hideInTable: true,
        formItemProps: formDateRangeFormItemProps,
        search: { order: 40 } as ProColumns['search'],
      },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.inboundCode'),
        dataIndex: 'inbound_code',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        fixed: 'left',
        sorter: true,
        search: { order: 50 } as ProColumns['search'],
        render: (_, r) => (
          <Typography.Text copyable={{ text: String(r.inbound_code ?? '') }} ellipsis>
            {r.inbound_code ?? '-'}
          </Typography.Text>
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.warehouse'),
        dataIndex: 'warehouse_name',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        sorter: true,
        hideInSearch: true,
        render: (_, r) =>
          r.warehouse_name != null && r.warehouse_name !== '' ? String(r.warehouse_name) : '-',
      },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.reasonType'),
        dataIndex: 'reason_type',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        sorter: true,
        hideInSearch: true,
        render: (v) =>
          renderWarehouseReasonTypeMarkerTag(translateReasonTypeLabel(t, String(v || '')), String(v || '')),
      },
      {
        title: t('app.kuaizhizao.common.colLineMaterials'),
        ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
        render: (_, r) => renderDocumentLineMaterialsPreview(r.items, t),
      },
      {
        title: t('app.kuaizhizao.warehouseCommon.colTotalQuantity'),
        dataIndex: 'total_quantity',
        width: 100,
      minWidth: 100,
      uniTableKeepWidth: true,
      resizable: false,
        sorter: true,
        hideInSearch: true,
        render: (_, r) => formatQuantity(r.total_quantity),
      },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.receiver'),
        dataIndex: 'receiver_name',
        width: 100,
        minWidth: 100,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        sorter: true,
        hideInSearch: true,
        render: (_, r) =>
          r.receiver_name != null && r.receiver_name !== '' ? String(r.receiver_name) : '-',
      },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.receiptTime'),
        dataIndex: 'receipt_time',
        width: 132,
        minWidth: 132,
        uniTableKeepWidth: true,
        resizable: false,
        sorter: true,
        hideInSearch: true,
        render: (_, r) => (r.receipt_time ? formatDateTime(r.receipt_time) : '-'),
      },
      ...buildDocumentAuditColumns<Record<string, unknown>>(t),
      otherInboundAuditColumn,
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.lifecycle'),
        dataIndex: 'lifecycle_stage',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) => {
          const lifecycle = getOtherInboundLifecycle(record as Record<string, unknown>, t);
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
      ...otherInboundCustomFieldColumns,
      {
        title: t('common.actions'),
        key: 'option',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) => {
          const hubRecord: InboundHubOrder = { ...record, receipt_type: 'other_inbound' };
          const actions: React.ReactNode[] = [
            <Button key="detail" {...rowActionKind('read')} onClick={() => handleDetail(record)} />,
          ];
          if (canUpdateInbound && isInboundEditable(hubRecord)) {
            actions.push(
              <Button
                key="edit"
                {...rowActionKind('update')}
                onClick={(e) => {
                  e.stopPropagation();
                  setEditModalRecord(hubRecord);
                }}
              />,
            );
          }
          return <Space>{actions}</Space>;
        },
      },
    ], WAREHOUSE_DOC_LIST_FIELD_RANK),
    [
      t,
      otherInboundAuditColumn,
      otherInboundCustomFieldColumns,
      otherInboundStatusValueEnum,
      reasonTypeOptions,
      reasonTypeLoading,
      canUpdateInbound,
    ],
  );

  const handleDetail = async (record: OtherInbound) => {
    setDetailDrawerVisible(true);
    setDetailLoading(true);
    setInboundDetail(null);
    resetOtherInboundDetailFieldValues();
    try {
      const detail = await warehouseApi.otherInbound.get(record.id!.toString());
      setInboundDetail(detail as OtherInboundDetail);
      if (record.id != null) {
        await loadOtherInboundFieldValuesForDetail(record.id);
      }
    } catch {
      messageApi.error(t('app.kuaizhizao.warehouseOtherInbound.msg.loadDetailFailed'));
      setDetailDrawerVisible(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const executeDelete = async (record: OtherInbound) => {
    try {
      await warehouseApi.otherInbound.delete(record.id!.toString());
      messageApi.success(t('common.deleteSuccess'));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('common.deleteFailed'));
    }
  };

  const listRowsRef = useRef<Map<string, OtherInbound>>(new Map());
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const isOtherInboundDeletable = (record: OtherInbound) => record.status === '待入库' && !!record.id;
  const isOtherInboundPrintable = (record: OtherInbound) => !!record.id;

  const handlePrint = (record: OtherInbound) => {
    if (!record.id) return;
    openPrint({ documentType: 'other_inbound', documentId: record.id });
  };

  const selectedOtherInboundForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => listRowsRef.current.get(String(key)))
        .filter((row): row is OtherInbound => row != null),
    [selectedRowKeys],
  );

  const selectedOtherInboundCapabilityRows = useMemo(
    () =>
      selectedOtherInboundForBatch.map((row) => ({
        ...row,
        capabilities: {
          confirm: { allowed: row.status === '待入库' },
          withdraw: { allowed: row.status === '已入库' },
        },
      })),
    [selectedOtherInboundForBatch],
  );

  const reloadOtherInboundAfterCapability = useCallback(() => {
    setSelectedRowKeys([]);
    invalidateMenuBadgeCounts();
    actionRef.current?.reload();
  }, [invalidateMenuBadgeCounts]);

  const selectedOtherInboundIdsForDocumentPush = useMemo(
    () =>
      selectedOtherInboundForBatch
        .filter((row) => Number(row.id) > 0)
        .map((row) => Number(row.id)),
    [selectedOtherInboundForBatch],
  );

  const canToolbarPrint =
    selectedRowKeys.length === 1 &&
    !!selectedOtherInboundForBatch[0] &&
    isOtherInboundPrintable(selectedOtherInboundForBatch[0]);

  const handleBatchDelete = async (keys: React.Key[]) => {
    const rows = keys
      .map((k) => listRowsRef.current.get(String(k)))
      .filter((r): r is OtherInbound => !!r && isOtherInboundDeletable(r));
    if (rows.length === 0) {
      messageApi.warning(t('app.kuaizhizao.warehouseCommon.batchDeleteNoneDeletable'));
      return;
    }
    try {
      for (const row of rows) {
        await warehouseApi.otherInbound.delete(String(row.id));
      }
      messageApi.success(t('app.kuaizhizao.warehouseCommon.deleteSuccess', { count: rows.length }));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('app.kuaizhizao.warehouseCommon.batchDeleteFailed'));
    }
  };

  const executeWithdraw = async (record: OtherInbound) => {
    try {
      const kingdeeWarn = readExternalWithdrawMessage(
        await warehouseApi.otherInbound.withdraw(record.id!.toString()),
      );
      if (kingdeeWarn) {
        messageApi.warning(kingdeeWarn);
      }
      messageApi.success(t('app.kuaizhizao.warehouseOtherInbound.msg.withdrawSuccess'));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('app.kuaizhizao.warehouseOtherInbound.msg.withdrawFailed'));
    }
  };

  const appendOtherInboundItemsFromMaterials = useCallback(
    async (selected: Material[]) => {
      const current = formRef.current?.getFieldValue('items') ?? [];
      const newRows = await Promise.all(
        selected.map(async (m) => {
          const row = {
            ...defaultInboundItem,
            material_id: m.id,
            material_code: m.mainCode ?? m.code ?? '',
            material_name: m.name ?? '',
            material_unit: m.inventoryUnit ?? m.baseUnit ?? '',
            material_uuid: m.uuid,
            batch_managed: isMaterialBatchEntryEnabled(trackingFlags, m.batchManaged ?? false),
            serial_managed: isMaterialSerialEntryEnabled(trackingFlags, m.serialManaged ?? false),
            default_batch_rule_id: m.defaultBatchRuleId,
            default_serial_rule_id: m.defaultSerialRuleId,
          };
          if (m.uuid) {
            try {
              const full = await materialApi.get(m.uuid);
              return {
                ...row,
                batch_managed: isMaterialBatchEntryEnabled(trackingFlags, full.batchManaged ?? false),
                serial_managed: isMaterialSerialEntryEnabled(trackingFlags, full.serialManaged ?? false),
                default_batch_rule_id: full.defaultBatchRuleId,
                default_serial_rule_id: full.defaultSerialRuleId,
              };
            } catch {
              return row;
            }
          }
          return row;
        }),
      );
      formRef.current?.setFieldsValue({ items: [...current, ...newRows] });
      messageApi.success(t('app.kuaizhizao.common.materialBatchAdded', { count: selected.length }));
    },
    [messageApi, t, trackingFlags],
  );

  /** 参考销售订单：先打开弹窗，再让 CodeField 自动生成编号 */
  const handleCreate = () => {
    resetSelectedWarehouseId();
    setCreateModalVisible(true);
    setTimeout(() => {
      formRef.current?.resetFields();
      formRef.current?.setFieldsValue({ items: [defaultInboundItem] });
    }, 0);
  };
  useNewShortcut(handleCreate);
  const createButtonLabel = useMemo(
    () => withSingleNewShortcutHint(t('app.kuaizhizao.warehouseOtherInbound.create')),
    [t],
  );

  const handleCreateSubmit = async (values: any) => {
    try {
      const validItems = (values.items ?? []).filter((it: any) => it.material_id && (Number(it.inbound_quantity) || 0) > 0);
      if (!validItems.length) {
        messageApi.error(t('app.kuaizhizao.warehouseOtherInbound.msg.needValidLine'));
        throw new Error(t('app.kuaizhizao.warehouseOtherInbound.msg.needValidLine'));
      }
      for (const it of validItems) {
        const material = it.material_code || it.material_name || '-';
        if (!String(it.location_code || '').trim()) {
          messageApi.error(
            t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', { material }),
          );
          throw new Error(
            t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', { material }),
          );
        }
        if (it.batch_managed && !String(it.batch_number ?? '').trim()) {
          const msg = t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
            material,
            batches: '—',
          });
          messageApi.error(msg);
          throw new Error(msg);
        }
        if (it.serial_managed) {
          const qty = Math.floor(Number(it.inbound_quantity) || 0);
          const serials = (Array.isArray(it.serial_numbers) ? it.serial_numbers : [])
            .map((s: unknown) => String(s ?? '').trim())
            .filter(Boolean);
          if (serials.length !== qty) {
            const msg = t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
              material,
              required: qty,
              actual: serials.length,
            });
            messageApi.error(msg);
            throw new Error(msg);
          }
        }
      }
      const wh = warehouseList.find((w: any) => (w.id ?? w.warehouse_id) === values.warehouse_id);
      const warehouseName = values.warehouse_name ?? wh?.name ?? wh?.warehouse_name ?? '';
      const { standardValues, customData } = extractOtherInboundFormValues(values);
      const created = await warehouseApi.otherInbound.create({
        inbound_code: standardValues.inbound_code,
        // 字典可能存「调拨入库」，提交前归一为 schema 枚举「调拨」
        reason_type: normalizeReasonTypeValue(standardValues.reason_type) || standardValues.reason_type,
        reason_desc: standardValues.reason_desc,
        warehouse_id: standardValues.warehouse_id,
        warehouse_name: warehouseName,
        notes: standardValues.notes,
        attachments: normalizeDocumentAttachments(standardValues.attachments),
        items: validItems.map((it: any) => ({
          material_id: it.material_id,
          material_code: it.material_code || '',
          material_name: it.material_name || '',
          material_unit: it.material_unit || '',
          location_code: it.location_code || undefined,
          ...pickDocumentLineDualQuantityFields(it as Record<string, unknown>),
          inbound_quantity: Number(it.inbound_quantity) || 0,
          unit_price: Number(it.unit_price) || 0,
          batch_number: it.batch_number || undefined,
          serial_numbers: it.serial_numbers || undefined,
        })),
      });
      const recordId = Number((created as { id?: number })?.id ?? 0);
      if (recordId > 0 && Object.keys(customData).length > 0) {
        await saveOtherInboundCustomFieldValues(recordId, customData);
      }
      messageApi.success(t('common.createSuccess'));
      resetOtherInboundFormFieldValues();
      resetSelectedWarehouseId();
      setCreateModalVisible(false);
      invalidateMenuBadgeCounts();

      actionRef.current?.reload();
    } catch (error: any) {
      if (error.message !== t('app.kuaizhizao.warehouseOtherInbound.msg.needValidLine')) {
        messageApi.error(error.message || t('common.createFailed'));
      }
      throw error;
    }
  };

  const handleGenerateBatch = async (idx: number) => {
    if (!trackingFlags.batchManagement) return;
    const items = formRef.current?.getFieldValue('items') ?? [];
    const row = items[idx];
    if (!row?.material_uuid || !row?.batch_managed) {
      messageApi.warning(t('app.kuaizhizao.warehouseOtherInbound.msg.selectMaterialFirst'));
      return;
    }
    setGeneratingBatchIdx(idx);
    try {
      const res = await materialBatchApi.generate(row.material_uuid, {
        ruleId: row.batch_rule_id ?? row.default_batch_rule_id,
      });
      formRef.current?.setFieldValue(['items', idx, 'batch_number'], res.batch_no);
      messageApi.success(t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerated'));
    } catch (e: any) {
      messageApi.error(e?.message || t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerateFailed'));
    } finally {
      setGeneratingBatchIdx(null);
    }
  };

  const handleGenerateSerials = async (idx: number): Promise<string[]> => {
    if (!trackingFlags.serialManagement) return [];
    const items = formRef.current?.getFieldValue('items') ?? [];
    const row = items[idx];
    if (!row?.material_uuid || !row?.serial_managed) {
      messageApi.warning(t('app.kuaizhizao.warehouseOtherInbound.msg.selectMaterialFirst'));
      return [];
    }
    const count = Math.max(1, Math.floor(Number(row.inbound_quantity) || 1));
    if (count > MATERIAL_SERIAL_GENERATE_MAX_COUNT) {
      messageApi.warning(
        t('app.kuaizhizao.warehouseOtherInbound.msg.serialMax100', {
          max: MATERIAL_SERIAL_GENERATE_MAX_COUNT,
        }),
      );
      return [];
    }
    setGeneratingSerialIdx(idx);
    try {
      const res = await materialSerialApi.generate(row.material_uuid, count, {
        ruleId: row.serial_rule_id ?? row.default_serial_rule_id,
      });
      const serialNos = res.serial_nos ?? [];
      formRef.current?.setFieldValue(['items', idx, 'serial_numbers'], serialNos);
      messageApi.success(t('app.kuaizhizao.warehouseOtherInbound.msg.serialGenerated', { count: res.count }));
      return serialNos;
    } catch (e: any) {
      messageApi.error(e?.message || t('app.kuaizhizao.warehouseOtherInbound.msg.serialGenerateFailed'));
      return [];
    } finally {
      setGeneratingSerialIdx(null);
    }
  };

  const onMaterialSelectForBatchSerial = async (idx: number, _val: number | undefined, material: any | undefined) => {
    if (!material) return;
    const uuid = material.uuid || material.UUID;
    let batchManaged = material.batchManaged ?? material.batch_managed ?? false;
    let serialManaged = material.serialManaged ?? material.serial_managed ?? false;
    let defaultBatchRuleId = material.defaultBatchRuleId ?? material.default_batch_rule_id;
    let defaultSerialRuleId = material.defaultSerialRuleId ?? material.default_serial_rule_id;
    if (uuid) {
      try {
        const full = await materialApi.get(uuid);
        batchManaged = full.batchManaged ?? false;
        serialManaged = full.serialManaged ?? false;
        defaultBatchRuleId = full.defaultBatchRuleId;
        defaultSerialRuleId = full.defaultSerialRuleId;
      } catch {
        // 使用列表返回的字段
      }
    }
    formRef.current?.setFieldValue(['items', idx, 'material_uuid'], uuid);
    formRef.current?.setFieldValue(
      ['items', idx, 'batch_managed'],
      isMaterialBatchEntryEnabled(trackingFlags, batchManaged),
    );
    formRef.current?.setFieldValue(
      ['items', idx, 'serial_managed'],
      isMaterialSerialEntryEnabled(trackingFlags, serialManaged),
    );
    formRef.current?.setFieldValue(['items', idx, 'default_batch_rule_id'], defaultBatchRuleId);
    formRef.current?.setFieldValue(['items', idx, 'default_serial_rule_id'], defaultSerialRuleId);
  };

  const detailColumns = useMemo(
    () => alignDescriptionColumns([
      { title: t('app.kuaizhizao.warehouseOtherInbound.col.inboundCode'), dataIndex: 'inbound_code' },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.reasonType'),
        dataIndex: 'reason_type',
        render: (_, record) =>
          renderWarehouseReasonTypeMarkerTag(translateReasonTypeLabel(t, record.reason_type), record.reason_type),
      },
      { title: t('app.kuaizhizao.warehouseOtherInbound.field.reasonDesc'), dataIndex: 'reason_desc', span: 3 },
      { title: t('app.kuaizhizao.warehouseOtherInbound.col.warehouse'), dataIndex: 'warehouse_name' },
      {
        title: t('common.status'),
        dataIndex: 'status',
        render: (s) => {
          const map: Record<string, { textKey: string; color: string }> = {
            '待入库': { textKey: 'app.kuaizhizao.warehouseOtherInbound.status.pending', color: 'default' },
            '已入库': { textKey: 'app.kuaizhizao.warehouseOtherInbound.status.posted', color: 'success' },
            '已取消': { textKey: 'app.kuaizhizao.warehouseOtherInbound.status.cancelled', color: 'error' },
          };
          const c = map[(s as string) || ''] || { textKey: '', color: 'default' };
          return <Tag color={c.color}>{c.textKey ? t(c.textKey) : (s as string) || '-'}</Tag>;
        },
      },
      { title: t('app.kuaizhizao.warehouseOtherInbound.col.receiver'), dataIndex: 'receiver_name' },
      { title: t('app.kuaizhizao.warehouseOtherInbound.col.receiptTime'), dataIndex: 'receipt_time', valueType: 'dateTime' },
    ]),
    [t],
  );

  const detailNotesColumn: ProDescriptionsItemProps<OtherInboundDetail> = useMemo(
    () => ({
      title: t('common.remark'),
      dataIndex: 'notes',
      span: 3,
    }),
    [t],
  );

  const detailItemColumns = useMemo(
    () => [
      { title: t('app.kuaizhizao.warehouseOtherInbound.col.materialCode'), dataIndex: 'material_code', width: 120 },
      { title: t('app.kuaizhizao.warehouseOtherInbound.col.materialName'), dataIndex: 'material_name', width: 150 },
      {
        title: t('common.unit'),
        dataIndex: 'material_unit',
        width: 60,
        render: (val: unknown) => <MaterialUnitLabel value={val as string | null} />,
      },
      { title: t('app.kuaizhizao.warehouseOtherInbound.col.location'), dataIndex: 'location_code', width: 100, ellipsis: true },
      { title: t('app.kuaizhizao.warehouseOtherInbound.col.inboundQty'), dataIndex: 'inbound_quantity', width: 100, align: 'right' as const },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.unitPrice'),
        dataIndex: 'unit_price',
        width: 100,
        align: 'right' as const,
        render: (v: unknown) => {
          const n = Number(v);
          return Number.isFinite(n) && n > 0 ? String(v) : '—';
        },
      },
      { title: t('app.kuaizhizao.warehouseOtherInbound.col.batchNo'), dataIndex: 'batch_number', width: 120, ellipsis: true },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.serialNo'),
        dataIndex: 'serial_numbers',
        width: 140,
        ellipsis: true,
        render: (val: unknown) => {
          const list = Array.isArray(val) ? val : [];
          return list.length > 0 ? list.join('、') : '—';
        },
      },
      { title: t('common.remark'), dataIndex: 'notes' },
    ],
    [t],
  );

  const detailCollaboration = useMemo(() => {
    if (!inboundDetail) return undefined;
    const lifecycle = getOtherInboundLifecycle(inboundDetail as unknown as Record<string, unknown>, t);
    const mainStages = lifecycle.mainStages ?? [];
    if (!mainStages.length) return undefined;
    return (
      <UniLifecycleStepper
        steps={mainStages}
        status={lifecycle.status}
        showLabels
        nextStepSuggestions={lifecycle.nextStepSuggestions}
      />
    );
  }, [inboundDetail, t]);

  const timeconfigBasicItems0 = useDetailDrawerDescriptionItems(
    [detailNotesColumn],
    inboundDetail,
    'other_inbound',
  );
  const timeconfigBasicItems1 = useDetailDrawerDescriptionItems(
    detailColumns,
    inboundDetail,
    'other_inbound',
  );

  const detailSupplementary = useMemo(() => {
    if (!inboundDetail) return undefined;
    const nodes: React.ReactNode[] = [];
    if (hasCustomFieldsDetailContent(otherInboundListCustomFields, otherInboundDetailCustomFieldValues)) {
      nodes.push(
        <CustomFieldsDetailSection
          key="custom-fields"
          customFields={otherInboundListCustomFields}
          customFieldValues={otherInboundDetailCustomFieldValues}
        />,
      );
    }
    if (inboundDetail.notes) {
      nodes.push(
        <Descriptions
          key="notes"
          column={detailDrawerBasicColumn(false)}
          size="small"
          style={nodes.length > 0 ? { marginTop: 16 } : undefined}
          items={timeconfigBasicItems0}
        />,
      );
    }
    if (nodes.length === 0) return undefined;
    return <>{nodes}</>;
  }, [detailNotesColumn, inboundDetail, otherInboundDetailCustomFieldValues, otherInboundListCustomFields, timeconfigBasicItems0]);

  return (
    <>
      <ListPageTemplate>
        <UniTable
          headerTitle={t('app.kuaizhizao.warehouseOtherInbound.title')}
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.otherInbound)}
          columnPersistenceId="apps.kuaizhizao.pages.warehouse-management.other-inbound-width-v4"
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch
          pinnedTabsField={WAREHOUSE_DOC_PINNED_STATUS_FIELD}
          skipFuzzyPinyinClientFilter
          showCreateButton
          createButtonText={createButtonLabel}
          onCreate={handleCreate}
          enableRowSelection
          onTableDataChange={(rows) => {
            const next = new Map<string, OtherInbound>();
            for (const row of rows) {
              if (row.id != null) next.set(String(row.id), row);
            }
            listRowsRef.current = next;
          }}
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          showSyncButton={toolbarSyncPush.hubVisible && toolbarSyncPush.pushEnabled}
          onSync={() => undefined}
          syncToolbarExtra={
            toolbarSyncPush.hubVisible && toolbarSyncPush.pushEnabled
              ? () => (
                  <SyncPushHubButton
                    syncEnabled={false}
                    pushEnabled={toolbarSyncPush.pushEnabled}
                    historySourceType="other_inbound"
                    historyTargetProfiles={['kingdee_im_otherinbill']}
                    size="medium"
                    renderPushPanel={({ active, close }) => (
                      <OtherInboundDocumentPushPanel
                        embedded
                        open={active}
                        onClose={close}
                        inboundIds={selectedOtherInboundIdsForDocumentPush}
                        onComplete={() => {
                          actionRef.current?.reload?.();
                          close();
                        }}
                      />
                    )}
                  />
                )
              : undefined
          }
          showDeleteButton
          deleteButtonText={t('common.delete')}
          toolBarActionsAfterBatch={[
            <UniCapabilityBatchButton
              key="other-inbound-confirm"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedOtherInboundCapabilityRows}
              capabilityKey="confirm"
              permAllowed={inboundPerms.canAction?.('execute') ?? false}
              onRun={async (id) => {
                const row = selectedOtherInboundForBatch.find((r) => Number(r.id) === id);
                if (!row) {
                  throw new Error(t('app.kuaizhizao.warehouseInbound.msg.notConfirmable'));
                }
                await runInboundHubConfirmFromRecord({
                  t,
                  record: { id: row.id, receipt_type: 'other_inbound' },
                  trackingFlags,
                });
              }}
              onSuccess={reloadOtherInboundAfterCapability}
              requireConfirm
              labels={{
                single: t('app.kuaizhizao.warehouseInbound.action.confirmInbound'),
                batch: t('app.kuaizhizao.warehouseInbound.action.confirmInbound'),
                singleConfirmTitle: t('app.kuaizhizao.warehouseInbound.action.confirmInbound'),
              }}
              icon={<CheckCircleOutlined />}
              size="medium"
              color="green"
              variant="solid"
            />,
            <UniCapabilityBatchButton
              key="other-inbound-withdraw"
              selectedRowKeys={selectedRowKeys}
              selectedRecords={selectedOtherInboundCapabilityRows}
              capabilityKey="withdraw"
              permAllowed={inboundPerms.canAction?.('revoke') ?? false}
              onRun={async (id) => {
                await warehouseApi.otherInbound.withdraw(String(id));
              }}
              onSuccess={reloadOtherInboundAfterCapability}
              requireConfirm
              labels={{
                single: t('app.kuaizhizao.warehouseOtherInbound.action.withdrawInbound'),
                batch: t('app.kuaizhizao.warehouseOtherInbound.action.withdrawInbound'),
                singleConfirmTitle: t('app.kuaizhizao.warehouseOtherInbound.confirm.withdrawTitle'),
              }}
              icon={<RollbackOutlined />}
              size="medium"
              color="orange"
              variant="solid"
            />,
          ]}
          rowSelectionGetCheckboxProps={(record) => ({
            disabled: !isOtherInboundDeletable(record) && !isOtherInboundPrintable(record),
          })}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) =>
            t('app.kuaizhizao.warehouseCommon.batchDeleteConfirm', {
              count,
              noun: t('app.kuaizhizao.warehouseOtherInbound.title'),
            })
          }
          showExportButton
          onExport={async (type, keys, pageData) => {
            try {
              const loadAll = async () => {
                const searchFormValues: Record<string, unknown> = {};
                const listParams = resolveWarehouseDocListParams(searchFormValues, undefined, {
                  docDateParamPrefix: 'receipt',
                });
                const rows = await fetchAllListItems((p) =>
                  warehouseApi.otherInbound.list({ ...listParams, ...p }),
                );
                return enrichOtherInboundRecordsWithCustomFields(rows);
              };
              const headers = await resolveWarehouseListExportHeaders(
                type,
                keys,
                pageData as OtherInbound[] | undefined,
                listRowsRef.current,
                loadAll,
              );
              if (headers.length === 0) {
                messageApi.warning(t('common.exportNoData'));
                return;
              }
              const enriched = await enrichStandaloneDocsWithDetail(headers, (id) =>
                warehouseApi.otherInbound.get(String(id)),
              );
              let flatRows = flattenStandaloneWarehouseDocsForExport(enriched, {
                docCodeField: 'inbound_code',
                docTypeLabel: t('app.kuaizhizao.warehouseInbound.receiptType.other_inbound'),
                dateFields: ['receipt_time'],
                operatorFields: ['receiver_name'],
              });
              if (type === 'selected' && keys?.length) {
                flatRows = filterWarehouseFlatRowsByExportKeys(flatRows, keys);
              }
              await exportWarehouseDocLinesXlsx(
                flatRows,
                `other-inbound-lines-${todaySiteDateString()}.xlsx`,
                {
                  t,
                  sheetName: t('app.kuaizhizao.warehouseOtherInbound.title'),
                  includeDocTypeColumn: false,
                  direction: 'standalone',
                },
              );
              messageApi.success(t('common.exportSuccess', { count: flatRows.length }));
            } catch (error: unknown) {
              messageApi.error((error as { message?: string })?.message || t('common.exportFailed'));
            }
          }}
          request={async (params, sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
            try {
              const listParams = resolveWarehouseDocListParams(searchFormValues, sort, {
                docDateParamPrefix: 'receipt',
              });
              const response = await warehouseApi.otherInbound.list({
                skip: ((params.current || 1) - 1) * (params.pageSize || 20),
                limit: params.pageSize || 20,
                ...listParams,
              });
              const { data: raw, total } = normalizeWarehouseListResponse(response);
              const data = meta?.purpose === 'prefetch'
                ? raw
                : await enrichOtherInboundRecordsWithCustomFields(raw);
              return { data, success: true, total };
            } catch {
              messageApi.error(t('app.kuaizhizao.warehouseOtherInbound.msg.loadListFailed'));
              return { data: [], success: false, total: 0 };
            }
          }}
          showPrintButton
          printButtonDisabled={!canToolbarPrint}
          printButtonText={t('components.uniAction.print')}
          onPrint={() => {
            const row = selectedOtherInboundForBatch[0];
            if (row) handlePrint(row);
          }}
        />
      </ListPageTemplate>

      <DetailDrawerTemplate
        title={`${t('app.kuaizhizao.warehouseOtherInbound.detailTitle')}${inboundDetail?.inbound_code ? ` - ${inboundDetail.inbound_code}` : ''}`}
        open={detailDrawerVisible}
        loading={detailLoading}
        onClose={() => {
          setDetailDrawerVisible(false);
          setInboundDetail(null);
          resetOtherInboundDetailFieldValues();
        }}
        size={DRAWER_CONFIG.HALF_WIDTH}
        basic={
          inboundDetail ? (
            <Descriptions column={detailDrawerBasicColumn(false)} size="small" items={timeconfigBasicItems1} />
          ) : undefined
        }
        collaboration={detailCollaboration}
        supplementary={detailSupplementary}
        linesTitle={t('app.kuaizhizao.warehouseOtherInbound.field.lines')}
        lines={
          inboundDetail?.items && inboundDetail.items.length > 0 ? (
            <>
              <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
              <Table
                className="warehouse-detail-table"
                size="small"
                rowKey="id"
                columns={detailItemColumns}
                dataSource={inboundDetail.items}
                pagination={false}
              />
            </>
          ) : undefined
        }
      />

      <FormModalTemplate
        title={t('app.kuaizhizao.warehouseOtherInbound.createModal')}
        open={createModalVisible}
        onClose={() => {
          resetSelectedWarehouseId();
          setCreateModalVisible(false);
          resetOtherInboundFormFieldValues();
        }}
        formRef={formRef}
        onFinish={handleCreateSubmit}
        submitText={t('app.kuaizhizao.warehouseOtherInbound.action.saveDraft')}
        width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
        initialValues={{ reason_type: '其他' }}
        grid={false}
      >
        <Row gutter={16}>
          <Col span={12}>
            <CodeField
              pageCode="kuaizhizao-warehouse-other-inbound"
              name="inbound_code"
              label={t('app.kuaizhizao.warehouseOtherInbound.field.inboundCode')}
              autoGenerateOnCreate={true}
              showGenerateButton={false}
              context={{}}
            />
          </Col>
          <Col span={12}>
            <UniWarehouseSelect
              name="warehouse_id"
              label={t('app.kuaizhizao.warehouseOtherInbound.field.warehouse')}
              placeholder={t('app.kuaizhizao.warehouseOtherInbound.field.selectWarehouse')}
              required
              hostResource="kuaizhizao:other-inbound"
              onChange={(val, wh) => {
                updateSelectedWarehouseId(val);
                formRef.current?.setFieldsValue({ warehouse_name: wh?.name ?? '' });
              }}
            />
          </Col>
        </Row>
        <AntForm.Item name="warehouse_name" hidden />
        <Row gutter={16}>
          <Col span={12}>
            <ProFormItem name="reason_type" label={t('app.kuaizhizao.warehouseOtherInbound.field.reasonType')} rules={[{ required: true }]}>
              <UniDropdown
                placeholder={t('app.kuaizhizao.warehouseOtherInbound.field.selectReasonType')}
                showSearch
                allowClear
                loading={reasonTypeLoading}
                style={{ width: '100%' }}
                options={reasonTypeOptions}
                quickCreate={{
                  label: t('app.kuaizhizao.warehouseOtherInbound.field.dictManage'),
                  onClick: () => navigate('/system/data-dictionaries?keyword=INBOUND_REASON_TYPE'),
                }}
              />
            </ProFormItem>
          </Col>
          <Col span={12}>
            <ProFormItem name="reason_desc" label={t('app.kuaizhizao.warehouseOtherInbound.field.reasonDesc')}>
              <Input placeholder={t('app.kuaizhizao.warehouseOtherInbound.field.optional')} />
            </ProFormItem>
          </Col>
          <CustomFieldsFormSection
            customFields={otherInboundFormCustomFields}
            customFieldValues={otherInboundFormCustomFieldValues}
            gridColumns={2}
            embedInParentRow
          />
        </Row>
        <div className="uni-table-detail" style={{ width: '100%' }}>
          <UniTableDetailHeader title={t('app.kuaizhizao.warehouseOtherInbound.field.lines')} required />
          <AntForm.List name="items">
              {(fields, { add, remove }) => {
                const cols = filterWarehouseTrackingColumns(
                  [
                  {
                    title: t('app.kuaizhizao.warehouseOtherInbound.col.material'),
                    dataIndex: 'material_id',
                    width: 260,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item noStyle shouldUpdate={(prev: any, curr: any) => prev?.items?.[index] !== curr?.items?.[index]}>
                        {({ getFieldValue }: any) => {
                          const row = getFieldValue('items')?.[index];
                          const mid = row?.material_id ? Number(row.material_id) : null;
                          const fallback = mid && (row?.material_code || row?.material_name)
                            ? { value: mid, label: `${row.material_code || ''} - ${row.material_name || ''}`.trim() || String(mid) }
                            : undefined;
                          return (
                            <div className="warehouse-detail-material-cell">
                              <UniMaterialSelect
                                name={[index, 'material_id']}
                                label=""
                                placeholder={t('app.kuaizhizao.warehouseOtherInbound.field.selectMaterial')}
                                required
                                size="small"
                                listFieldKey={index}
                                listFieldName="items"
                                fillMapping={{
                                  material_code: 'mainCode',
                                  material_name: 'name',
                                }}
                                onChange={(v, material) => {
                                  if (material) {
                                    formRef.current?.setFieldValue(
                                      ['items', index, 'material_unit'],
                                      resolveMaterialScenarioUnit(material, 'purchase'),
                                    );
                                  }
                                  void onMaterialSelectForBatchSerial(index, v, material);
                                }}
                                fallbackOption={fallback}
                                formItemProps={{ style: { margin: 0 } }}
                                showQuickCreate
                                showAdvancedSearch
                              />
                            </div>
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  ...buildDocumentLineDualQuantityPairColumns({
                    t,
                    getForm: () => formRef.current,
                    quantityField: 'inbound_quantity',
                    unitField: 'material_unit',
                    scenario: 'inventory',
                    quantityPrecision: quantityDecimals,
                    width: 168,
                    columnSpread: { align: 'right' as const },
                  }),
                  {
                    title: t('app.kuaizhizao.warehouseOtherInbound.col.location'),
                    dataIndex: 'location_code',
                    width: 150,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        name={[index, 'location_code']}
                        style={{ margin: 0 }}
                        rules={[
                          {
                            required: true,
                            message: t('app.kuaizhizao.warehouseOtherInbound.field.selectLocation'),
                          },
                        ]}
                      >
                        <Select
                          options={locationOptions}
                          placeholder={selectedWarehouseId ? t('app.kuaizhizao.warehouseOtherInbound.field.selectLocation') : t('app.kuaizhizao.warehouseOtherInbound.field.selectWarehouseFirst')}
                          style={{ width: '100%' }}
                          size="small"
                          showSearch
                          optionFilterProp="label"
                          disabled={!selectedWarehouseId}
                        />
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('app.kuaizhizao.warehouseOtherInbound.col.batchNo'),
                    dataIndex: 'batch_number',
                    width: 130,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        noStyle
                        shouldUpdate={(prev, curr) => prev?.items?.[index] !== curr?.items?.[index]}
                      >
                        {({ getFieldValue }) => {
                          const row = getFieldValue('items')?.[index];
                          if (!row?.batch_managed) return '—';
                          return (
                            <Space size={2}>
                              <AntForm.Item name={[index, 'batch_number']} style={{ margin: 0 }}>
                                <Input placeholder={t('app.kuaizhizao.warehouseOtherInbound.field.optional')} size="small" style={{ width: 96 }} />
                              </AntForm.Item>
                              <Button
                                type="link"
                                size="small"
                                icon={<ThunderboltOutlined />}
                                loading={generatingBatchIdx === index}
                                onClick={() => handleGenerateBatch(index)}
                                style={{ padding: 0 }}
                              />
                            </Space>
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('app.kuaizhizao.warehouseOtherInbound.col.serialNo'),
                    dataIndex: 'serial_numbers',
                    width: 150,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        noStyle
                        shouldUpdate={(prev, curr) => prev?.items?.[index] !== curr?.items?.[index]}
                      >
                        {({ getFieldValue }) => {
                          const row = getFieldValue('items')?.[index];
                          if (!row?.serial_managed) return '—';
                          const qty = Number(row?.inbound_quantity ?? 0);
                          const sn = getFieldValue(['items', index, 'serial_numbers']);
                          return (
                            <SerialNumbersImportTrigger
                              serials={Array.isArray(sn) ? sn : []}
                              expectedCount={qty > 0 ? qty : undefined}
                              materialLabel={row?.material_code || row?.material_name}
                              generateLoading={generatingSerialIdx === index}
                              onSerialsChange={(next) =>
                                formRef.current?.setFieldValue(['items', index, 'serial_numbers'], next)
                              }
                              onGenerate={() => handleGenerateSerials(index)}
                            />
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('app.kuaizhizao.warehouseOtherInbound.col.unitPrice'),
                    dataIndex: 'unit_price',
                    width: 100,
                    align: 'right' as const,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item name={[index, 'unit_price']} style={{ margin: 0 }}>
                        <InputNumber placeholder="0" min={0} precision={priceDecimals} style={{ width: '100%' }} size="small" />
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('common.actions'),
                    width: 60,
                    render: (_: any, __: any, index: number) => (
                      <Button type="link" danger size="small" icon={<DeleteOutlined />} onClick={() => remove(index)} disabled={fields.length <= 1} />
                    ),
                  },
                ],
                  trackingFlags,
                );
                const totalWidth = cols.reduce((s, c) => s + (c.width as number || 0), 0);
                return (
                  <div style={{ width: '100%', minWidth: 0, boxSizing: 'border-box' }}>
                    <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
                    <div style={{ width: '100%', overflowX: 'auto' }}>
                      <Table
                        className="warehouse-detail-table"
                        size="small"
                        dataSource={fields.map((f, i) => ({ ...f, key: f.key ?? i }))}
                        rowKey="key"
                        pagination={false}
                        columns={cols}
                        scroll={fields.length > 0 ? { x: totalWidth } : undefined}
                        style={{ width: '100%', margin: 0 }}
                        footer={() => (
                          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', width: '100%' }}>
                            <Button type="dashed" icon={<PlusOutlined />} style={{ flex: 1, minWidth: 120 }} onClick={() => add(defaultInboundItem)}>
                              {t('app.kuaizhizao.warehouseOtherInbound.action.addLine')}
                            </Button>
                            <Button
                              type="default"
                              icon={<ShoppingOutlined />}
                              style={{ flex: 1, minWidth: 120 }}
                              onClick={() => setMaterialPickerOpen(true)}
                            >
                              {t('app.kuaizhizao.common.materialBatchSelect')}
                            </Button>
                          </div>
                        )}
                      />
                    </div>
                  </div>
                );
              }}
            </AntForm.List>
        </div>
        <DocumentAttachmentsField category="other_inbound_attachments" />
        <ProFormTextArea name="notes" label={t('common.remark')} placeholder={t('app.kuaizhizao.warehouseOtherInbound.field.optional')} fieldProps={{ rows: 2 }} />
      </FormModalTemplate>

      <UniMaterialBatchPicker
        open={materialPickerOpen}
        onCancel={() => setMaterialPickerOpen(false)}
        onConfirm={appendOtherInboundItemsFromMaterials}
      />
      <OtherInboundEditModal
        open={editModalRecord != null}
        record={editModalRecord}
        onClose={() => setEditModalRecord(null)}
        onSuccess={() => {
          invalidateMenuBadgeCounts();
          actionRef.current?.reload();
          setEditModalRecord(null);
        }}
      />

      {PrintModal}
    </>
  );
};

export default OtherInboundPage;
