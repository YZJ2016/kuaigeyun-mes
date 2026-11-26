/**
 * 借料单管理页面
 *
 * 提供借料单的创建、查看、确认和管理功能（无工单借料：工具间、研发等）
 *
 * @author RiverEdge Team
 * @date 2026-02-19
 */

import React, { useRef, useState, useEffect, useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { ActionType, ProColumns, ProDescriptionsItemProps, ProFormItem, ProFormTextArea } from '@ant-design/pro-components';
import { App, Button, Col, DatePicker, Descriptions, Form as AntForm, Input, InputNumber, Modal, Row, Select, Space, Table, Tag, Typography } from 'antd';
import { PlusOutlined, EyeOutlined, CheckCircleOutlined, DeleteOutlined, ShoppingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { UniTable, type UniTableRequestMeta } from '../../../../../components/uni-table';
import { UniMaterialSelect } from '../../../../../components/uni-material-select';
import { UniMaterialBatchPicker } from '../../../../../components/uni-material-batch-picker';
import { UniUserSelect } from '../../../../../components/uni-user-select';
import type { Material } from '../../../../master-data/types/material';
import { UniWarehouseSelect } from '../../../../../components/uni-warehouse-select';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import CodeField from '../../../../../components/code-field';
import SyncFromDatasetModal from '../../../../../components/sync-from-dataset-modal';
import { UniTableDetailHeader } from '../../../../../components/uni-table-detail/UniTableDetail';
import {   useDetailDrawerDescriptionItems, detailDrawerBasicColumn, DetailDrawerTemplate, DRAWER_CONFIG, FormModalTemplate, ListPageTemplate, MODAL_CONFIG, WAREHOUSE_DETAIL_TABLE_STYLES } from '../../../../../components/layout-templates';
import { buildDocumentDetailTotalStockFormColumn } from '../../sales-management/shared/materialLineFormDetail';
import { warehouseApi } from '../../../services/production';
import { getMaterialBorrowLifecycle } from '../../../utils/materialBorrowLifecycle';
import { UniLifecycle, UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import { warehouseApi as masterDataWarehouseApi } from '../../../../master-data/services/warehouse';
import { materialApi } from '../../../../master-data/services/material';
import { getPopupContainerInModal } from '../../../../../utils/modalEventIsolation';
import { resolveMaterialScenarioUnit } from '../../../../../utils/materialScenarioUnit';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import { buildDocumentDetailSerialReadonlyColumn } from '../../../components/documentDetailSerialNumberColumn';
import {
  loadBatchOptionsByMaterialId,
  loadInStockSerialOptions,
  type InventoryPickOption,
} from '../outbound/outboundConfirmInventoryOptions';
import OutboundSerialPickerField from '../outbound/OutboundSerialPickerField';
import OutboundBatchAllocationField from '../outbound/OutboundBatchAllocationField';
import {
  isValidOutboundBatchAllocations,
  lineBatchAllocationsFromRow,
  syncFormLineBatchFields,
} from '../outbound/outboundBatchAllocation';
import {
  runOutboundHubConfirmFromRecord,
  formatOutboundConfirmError,
} from '../outbound/outboundHubRunConfirm';
import OutboundHubEditModal from '../outbound/OutboundHubEditModal';
import { isOutboundEditable, type OutboundHubOrder } from '../outbound/outboundHubTypes';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import {
  buildDocumentLineAuxQuantityDetailColumn,
  buildDocumentLineDualQuantityPairColumns,
} from '../../../../../components/quantity-with-unit';
import { pickDocumentLineDualQuantityFields } from '../../../../../utils/materialDualQuantity';
import { normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { rowActionKind, rowActionLabelKeep } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { useKuaizhizaoPrintModal } from '../../../hooks/useKuaizhizaoPrintModal';
import { useTranslation } from 'react-i18next';
import { useNumericPrecisionPlaces } from '../../../../../hooks/useNumericPrecision';
import { useWarehouseLocationOptions } from '../../../hooks/useWarehouseLocationOptions';
import { getDepartmentTree } from '../../../../../services/department';
import { FutureDatePicker } from '../../../../../utils/futureDatePickerShortcuts';
import { formatDateTime, formatQuantity, todaySiteDateString } from '../../../../../utils/format';
import { formDateRangeFormItemProps } from '../../../../../utils/formDate';
import { alignDescriptionColumns, alignProColumns } from '../../sales-management/shared/documentFieldAlignment';
import { WAREHOUSE_DOC_LIST_FIELD_RANK } from '../shared/warehouseDocListFieldRank';
import { buildDocumentAuditColumns } from '../../shared/documentAuditColumns';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../../sales-management/shared/documentLineMaterialsPreview';
import {
  WAREHOUSE_DOC_PINNED_STATUS_FIELD,
  buildMaterialBorrowStatusValueEnum,
  normalizeWarehouseListResponse,
  resolveWarehouseDocListParams,
} from '../../../utils/warehouseListCore';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { fetchAllListItems } from '../../../../../utils/fetchAllListPages';
import {
  enrichStandaloneDocsWithDetail,
  exportWarehouseDocLinesXlsx,
  filterWarehouseFlatRowsByExportKeys,
  flattenStandaloneWarehouseDocsForExport,
  resolveWarehouseListExportHeaders,
} from '../shared/warehouseDocListExport';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import {
  CustomFieldsFormSection,
  CustomFieldsDetailSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';

const MATERIAL_BORROW_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_material_borrows';

interface MaterialBorrow {
  id?: number;
  uuid?: string;
  tenant_id?: number;
  borrow_code?: string;
  warehouse_id?: number;
  warehouse_name?: string;
  borrower_id?: number;
  borrower_name?: string;
  department?: string;
  expected_return_date?: string;
  borrow_time?: string;
  status?: string;
  total_quantity?: number;
  total_items?: number;
  /** 列表「明细」列预览（仅 material_name） */
  items?: { material_name?: string }[];
  notes?: string;
  created_at?: string;
  updated_at?: string;
}

interface MaterialBorrowDetail extends MaterialBorrow {
  items?: MaterialBorrowItem[];
}

interface MaterialBorrowItem {
  id?: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_spec?: string;
  material_unit?: string;
  borrow_quantity?: number;
  returned_quantity?: number;
  status?: string;
}

const MATERIAL_BORROW_STATUS_I18N: Record<string, string> = {
  '待借出': 'app.kuaizhizao.materialBorrow.status.pending',
  '已借出': 'app.kuaizhizao.materialBorrow.status.borrowed',
  '已取消': 'app.kuaizhizao.materialBorrow.status.cancelled',
};

function borrowMaterialIdsKey(items: unknown): string {
  if (!Array.isArray(items)) return '';
  const ids = [
    ...new Set(
      items
        .map((it) => Number((it as { material_id?: unknown })?.material_id))
        .filter((id) => Number.isFinite(id) && id > 0),
    ),
  ].sort((a, b) => a - b);
  return ids.join(',');
}

function translateMaterialBorrowStatus(t: (key: string) => string, status?: string): string {
  if (!status) return '-';
  const key = MATERIAL_BORROW_STATUS_I18N[status];
  return key ? t(key) : status;
}

const MaterialBorrowsPage: React.FC = () => {
  const { t } = useTranslation();
  const quantityDecimals = useNumericPrecisionPlaces('quantity');
  const [searchParams] = useSearchParams();
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const deepLinkOpenedRef = useRef(false);
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const borrowPerms = useResourcePermissions('kuaizhizao:material-borrow');
  const canConfirmBorrow = borrowPerms.canAction?.('execute') ?? false;
  const canRevokeBorrow = borrowPerms.canAction?.('revoke') ?? false;
  const canUpdateBorrow = borrowPerms.canUpdate ?? false;
  const canDeleteBorrow = borrowPerms.canDelete ?? false;
  const [editModalRecord, setEditModalRecord] = useState<OutboundHubOrder | null>(null);

  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [borrowDetail, setBorrowDetail] = useState<MaterialBorrowDetail | null>(null);

  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [syncModalVisible, setSyncModalVisible] = useState(false);
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false);
  const formRef = useRef<any>(null);

  const {
    customFields: materialBorrowFormCustomFields,
    customFieldValues: materialBorrowFormCustomFieldValues,
    extractFormValues: extractMaterialBorrowFormValues,
    saveCustomFieldValues: saveMaterialBorrowCustomFieldValues,
    resetFieldValues: resetMaterialBorrowFormFieldValues,
  } = useCustomFields({
    tableName: MATERIAL_BORROW_CUSTOM_FIELD_TABLE,
    loadWhenOpen: true,
    open: createModalVisible,
  });

  const {
    customFields: materialBorrowListCustomFields,
    generateCustomFieldColumns: generateMaterialBorrowCustomFieldColumns,
    enrichRecordsWithCustomFields: enrichMaterialBorrowRecordsWithCustomFields,
    customFieldValues: materialBorrowDetailCustomFieldValues,
    loadFieldValuesForDetail: loadMaterialBorrowFieldValuesForDetail,
    resetDetailFieldValues: resetMaterialBorrowDetailFieldValues,
  } = useCustomFieldsForList<MaterialBorrow>({ tableName: MATERIAL_BORROW_CUSTOM_FIELD_TABLE });

  const materialBorrowCustomFieldColumns = generateMaterialBorrowCustomFieldColumns();
  const [warehouseList, setWarehouseList] = useState<any[]>([]);
  const [departmentOptions, setDepartmentOptions] = useState<Array<{ label: string; value: string }>>([]);
  const {
    selectedWarehouseId,
    locationOptions,
    updateSelectedWarehouseId,
    resetSelectedWarehouseId,
  } = useWarehouseLocationOptions();
  const trackingFlags = useWarehouseTrackingFlags();
  const [batchOptionsByKey, setBatchOptionsByKey] = useState<Record<string, InventoryPickOption[]>>({});
  const [batchOptionsLoadingKey, setBatchOptionsLoadingKey] = useState<string | null>(null);
  const [serialOptionsByUuid, setSerialOptionsByUuid] = useState<Record<string, InventoryPickOption[]>>({});
  const [serialOptionsLoadingUuid, setSerialOptionsLoadingUuid] = useState<string | null>(null);
  const serialOptionsLoadingRef = useRef<Record<string, boolean>>({});
  const [lineMaterialKey, setLineMaterialKey] = useState('');
  const defaultBorrowItem = {
    material_id: undefined,
    material_uuid: undefined as string | undefined,
    material_code: '',
    material_name: '',
    material_unit: '',
    location_code: undefined,
    batch_number: undefined as string | undefined,
    batch_allocations: [] as { batchNo: string; quantity: number }[],
    batch_managed: false,
    serial_managed: false,
    serial_numbers: undefined as string[] | undefined,
    borrow_quantity: 1,
  };

  const syncLineMaterialKeyFromForm = useCallback(() => {
    setLineMaterialKey(borrowMaterialIdsKey(formRef.current?.getFieldValue('items')));
  }, []);

  const batchOptionLabel = useCallback(
    (batch: string, qty: number, warehouseName?: string) =>
      warehouseName
        ? t('app.kuaizhizao.warehouseOutbound.confirm.batchAvailableWithWh', {
            batch,
            qty,
            warehouse: warehouseName,
          })
        : t('app.kuaizhizao.warehouseOutbound.confirm.batchAvailable', { batch, qty }),
    [t],
  );

  const ensureBatchOptions = useCallback(
    async (materialId: number, warehouseId: number) => {
      const mid = Number(materialId);
      const whId = Number(warehouseId);
      if (!(mid > 0) || !(whId > 0)) return;
      const key = `${mid}:${whId}`;
      setBatchOptionsLoadingKey(key);
      try {
        const map = await loadBatchOptionsByMaterialId([mid], whId, batchOptionLabel);
        setBatchOptionsByKey((prev) => ({ ...prev, [key]: map[mid] ?? [] }));
      } finally {
        setBatchOptionsLoadingKey((cur) => (cur === key ? null : cur));
      }
    },
    [batchOptionLabel],
  );

  const ensureSerialOptions = useCallback(async (materialUuid: string, selected?: string[]) => {
    const uuid = String(materialUuid || '').trim();
    if (!uuid || serialOptionsLoadingRef.current[uuid]) return;
    if (serialOptionsByUuid[uuid]?.length) return;
    serialOptionsLoadingRef.current[uuid] = true;
    setSerialOptionsLoadingUuid(uuid);
    try {
      const opts = await loadInStockSerialOptions(uuid);
      setSerialOptionsByUuid((prev) => ({ ...prev, [uuid]: opts }));
    } catch {
      setSerialOptionsByUuid((prev) => ({ ...prev, [uuid]: [] }));
    } finally {
      serialOptionsLoadingRef.current[uuid] = false;
      setSerialOptionsLoadingUuid((cur) => (cur === uuid ? null : cur));
    }
  }, [serialOptionsByUuid]);

  const applyMaterialBatchFlags = useCallback(
    async (idx: number, material: Material | undefined) => {
      if (!material) return;
      const uuid = material.uuid;
      let batchManaged = material.batchManaged ?? false;
      let serialManaged = material.serialManaged ?? false;
      if (uuid) {
        try {
          const full = await materialApi.get(uuid);
          batchManaged = full.batchManaged ?? false;
          serialManaged = full.serialManaged ?? false;
        } catch {
          /* 使用列表字段 */
        }
      }
      formRef.current?.setFieldValue(
        ['items', idx, 'batch_managed'],
        isMaterialBatchEntryEnabled(trackingFlags, batchManaged),
      );
      formRef.current?.setFieldValue(['items', idx, 'material_uuid'], uuid);
      formRef.current?.setFieldValue(
        ['items', idx, 'serial_managed'],
        isMaterialSerialEntryEnabled(trackingFlags, serialManaged),
      );
    },
    [trackingFlags],
  );

  useEffect(() => {
    if (!createModalVisible) {
      setLineMaterialKey('');
      setBatchOptionsByKey({});
      setBatchOptionsLoadingKey(null);
      return;
    }
    syncLineMaterialKeyFromForm();
  }, [createModalVisible, syncLineMaterialKeyFromForm]);

  useEffect(() => {
    if (!createModalVisible) return;
    const mids = lineMaterialKey
      .split(',')
      .map((s) => Number(s))
      .filter((id) => Number.isFinite(id) && id > 0);
    const whId = Number(selectedWarehouseId) || 0;
    if (!mids.length || !whId) return;
    for (const mid of mids) {
      void ensureBatchOptions(mid, whId);
    }
  }, [createModalVisible, selectedWarehouseId, lineMaterialKey, ensureBatchOptions]);

  useEffect(() => {
    const load = async () => {
      try {
        const wh = await masterDataWarehouseApi.list({ limit: 1000, is_active: true });
        setWarehouseList(Array.isArray(wh) ? wh : (wh as any)?.items || []);
      } catch (e) {
        console.error('加载仓库失败', e);
      }
    };
    load();
  }, []);

  useEffect(() => {
    const flatten = (items: any[] | undefined): Array<{ label: string; value: string }> => {
      if (!Array.isArray(items)) return [];
      const out: Array<{ label: string; value: string }> = [];
      const walk = (nodes: any[], prefix = '') => {
        nodes.forEach((node) => {
          const name = String(node?.name ?? '').trim();
          const uuid = String(node?.uuid ?? '').trim();
          if (name && uuid) {
            out.push({ label: prefix ? `${prefix} / ${name}` : name, value: uuid });
          }
          if (Array.isArray(node?.children) && node.children.length > 0) {
            walk(node.children, prefix ? `${prefix} / ${name}` : name);
          }
        });
      };
      walk(items);
      return out;
    };
    const loadDepartments = async () => {
      try {
        const res = await getDepartmentTree({ is_active: true });
        setDepartmentOptions(flatten(res?.items));
      } catch (e) {
        console.error('加载部门失败', e);
        setDepartmentOptions([]);
      }
    };
    void loadDepartments();
  }, []);

  const materialBorrowStatusValueEnum = useMemo(() => buildMaterialBorrowStatusValueEnum(t), [t]);

  const columns: ProColumns<MaterialBorrow>[] = useMemo(() => alignProColumns<MaterialBorrow>([
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
      valueEnum: materialBorrowStatusValueEnum,
      hideInTable: true,
      search: { order: 20 } as ProColumns['search'],
    },
    {
      title: t('app.kuaizhizao.materialBorrow.col.borrowTime'),
      dataIndex: 'doc_date_range',
      valueType: 'dateRange',
      hideInTable: true,
      formItemProps: formDateRangeFormItemProps,
      search: { order: 30 } as ProColumns['search'],
    },
    {
      title: t('app.kuaizhizao.materialBorrow.col.borrowCode'),
      dataIndex: 'borrow_code',
      width: 160,
      minWidth: 160,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
      fixed: 'left',
      sorter: true,
      search: { order: 40 } as ProColumns['search'],
      render: (_, r) => (
        <Typography.Text copyable={{ text: String(r.borrow_code ?? '') }} ellipsis>
          {r.borrow_code ?? '-'}
        </Typography.Text>
      ),
    },
    {
      title: t('app.kuaizhizao.warehouseReports.colWarehouse'),
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
      title: t('app.kuaizhizao.materialBorrow.col.borrower'),
      dataIndex: 'borrower_name',
      width: 100,
      minWidth: 100,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
      sorter: true,
      hideInSearch: true,
      render: (_, r) =>
        r.borrower_name != null && r.borrower_name !== '' ? String(r.borrower_name) : '-',
    },
    {
      title: t('app.kuaizhizao.materialBorrow.col.department'),
      dataIndex: 'department',
      width: 100,
      minWidth: 100,
      uniTableKeepWidth: true,
      resizable: false,
      ellipsis: true,
      sorter: true,
      hideInSearch: true,
      render: (_, r) =>
        r.department != null && r.department !== '' ? String(r.department) : '-',
    },
    {
      title: t('app.kuaizhizao.materialBorrow.col.expectedReturnDate'),
      dataIndex: 'expected_return_date',
      valueType: 'date',
      width: 132,
      minWidth: 132,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
    },
    {
      title: t('app.kuaizhizao.materialBorrow.col.borrowTime'),
      dataIndex: 'borrow_time',
      width: 132,
      minWidth: 132,
      uniTableKeepWidth: true,
      resizable: false,
      sorter: true,
      hideInSearch: true,
      render: (_, r) => (r.borrow_time ? formatDateTime(r.borrow_time) : '-'),
    },
    ...buildDocumentAuditColumns<Record<string, unknown>>(t),
    ...materialBorrowCustomFieldColumns,
    {
      title: t('app.kuaizhizao.warehouseOutbound.col.lifecycle'),
      dataIndex: 'lifecycle_stage',
      fixed: 'right',
      hideInSearch: true,
      render: (_, record) => {
        const lifecycle = getMaterialBorrowLifecycle(record as Record<string, unknown>, t);
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
      render: (_, record) => {
        const hubRecord: OutboundHubOrder = { ...record, outbound_type: 'material_borrow' };
        return (
          <Space size="small" wrap>
            <Button {...rowActionKind('read')} onClick={() => handleDetail(record)} />
            {canUpdateBorrow && isOutboundEditable(hubRecord) ? (
              <Button
                {...rowActionKind('update')}
                onClick={(e) => {
                  e.stopPropagation();
                  setEditModalRecord(hubRecord);
                }}
              />
            ) : null}
            {record.status === '待借出' && canConfirmBorrow ? (
              <ActionConfirmPopconfirm title={t('app.kuaizhizao.materialBorrow.msg.confirmTitle')} description={t('app.kuaizhizao.materialBorrow.msg.confirmContent', { code: record.borrow_code })} onConfirm={() => executeConfirm(record)}>
              <Button
                  {...rowActionKind('execute')}
                  {...rowActionLabelKeep()}
                  onClick={(e) => e.stopPropagation()}
                >
                  {t('app.kuaizhizao.materialBorrow.action.confirmBorrow')}
                </Button>
            </ActionConfirmPopconfirm>
            ) : null}
            {record.status === '待借出' && canDeleteBorrow ? (
                <ActionConfirmPopconfirm title={t('app.kuaizhizao.materialBorrow.msg.deleteTitle')} description={t('app.kuaizhizao.materialBorrow.msg.deleteContent', { code: record.borrow_code })} onConfirm={() => executeDelete(record)}>
              <Button {...rowActionKind('delete')} onClick={(e) => e.stopPropagation()} />
            </ActionConfirmPopconfirm>
            ) : null}
            {record.status === '已借出' && canRevokeBorrow && (
              <ActionConfirmPopconfirm title={t('app.kuaizhizao.materialBorrow.msg.withdrawTitle')} description={t('app.kuaizhizao.materialBorrow.msg.withdrawContent', { code: record.borrow_code })} onConfirm={() => executeWithdraw(record)}>
              <Button {...rowActionKind('revoke')} {...rowActionLabelKeep()} onClick={(e) => e.stopPropagation()}>
                {t('app.kuaizhizao.materialBorrow.action.withdrawBorrow')}
              </Button>
            </ActionConfirmPopconfirm>
            )}
          </Space>
        );
      },
    },
  ], WAREHOUSE_DOC_LIST_FIELD_RANK), [t, materialBorrowStatusValueEnum, canUpdateBorrow, canConfirmBorrow, canRevokeBorrow, canDeleteBorrow, materialBorrowCustomFieldColumns]);

  const handleDetail = useCallback(async (record: MaterialBorrow) => {
    if (record.id == null) return;
    setDetailDrawerVisible(true);
    setDetailLoading(true);
    setBorrowDetail(null);
    resetMaterialBorrowDetailFieldValues();
    try {
      const detail = await warehouseApi.materialBorrow.get(record.id.toString());
      setBorrowDetail(detail as MaterialBorrowDetail);
      await loadMaterialBorrowFieldValuesForDetail(record.id);
    } catch {
      messageApi.error(t('app.kuaizhizao.materialBorrow.msg.loadDetailFailed'));
      setDetailDrawerVisible(false);
    } finally {
      setDetailLoading(false);
    }
  }, [loadMaterialBorrowFieldValuesForDetail, messageApi, resetMaterialBorrowDetailFieldValues, t]);

  useEffect(() => {
    const idRaw = searchParams.get('id')?.trim();
    const uuidRaw = searchParams.get('uuid')?.trim();
    if (!idRaw && !uuidRaw) {
      deepLinkOpenedRef.current = false;
      actionRef.current?.reload();
      return;
    }
    if (deepLinkOpenedRef.current) {
      actionRef.current?.reload();
      return;
    }
    deepLinkOpenedRef.current = true;
    void (async () => {
      try {
        if (idRaw) {
          const id = Number(idRaw);
          if (Number.isFinite(id) && id > 0) {
            await handleDetail({ id });
            return;
          }
        }
        if (uuidRaw) {
          const res = await warehouseApi.materialBorrow.list({ keyword: uuidRaw, limit: 100 });
          const items = (res as { items?: MaterialBorrow[] }).items ?? [];
          const hit = items.find((row) => String(row.uuid) === uuidRaw);
          if (hit) {
            await handleDetail(hit);
          }
        }
      } catch {
        messageApi.error(t('app.kuaizhizao.materialBorrow.msg.loadDetailFailed'));
      } finally {
        actionRef.current?.reload();
      }
    })();
  }, [searchParams, handleDetail, messageApi, t]);

  const executeConfirm = async (record: MaterialBorrow) => {
    if (record.id == null) return;
    try {
      const confirmed = await runOutboundHubConfirmFromRecord({
        t,
        record: { id: record.id, outbound_type: 'material_borrow' },
        trackingFlags,
      });
      messageApi.success(t('app.kuaizhizao.materialBorrow.msg.confirmSuccess'));
      if (confirmed.externalPushMessage) {
        messageApi.warning(confirmed.externalPushMessage);
      }
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: unknown) {
      messageApi.error(formatOutboundConfirmError(error, t));
    }
  };

  const executeWithdraw = async (record: MaterialBorrow) => {
    try {
      await warehouseApi.materialBorrow.withdraw(record.id!.toString());
      messageApi.success(t('app.kuaizhizao.materialBorrow.msg.withdrawSuccess'));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('app.kuaizhizao.materialBorrow.msg.withdrawFailed'));
    }
  };

  const executeDelete = async (record: MaterialBorrow) => {
    try {
      await warehouseApi.materialBorrow.delete(record.id!.toString());
      messageApi.success(t('common.deleteSuccess'));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('common.deleteFailed'));
    }
  };

  const listRowsRef = useRef<Map<string, MaterialBorrow>>(new Map());
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const isMaterialBorrowDeletable = (record: MaterialBorrow) => record.status === '待借出' && !!record.id;
  const isMaterialBorrowPrintable = (record: MaterialBorrow) =>
    (record.status === '待借出' || record.status === '已借出') && !!record.id;

  const selectedMaterialBorrowForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => listRowsRef.current.get(String(key)))
        .filter((row): row is MaterialBorrow => row != null),
    [selectedRowKeys],
  );

  const canToolbarPrint =
    selectedRowKeys.length === 1 &&
    !!selectedMaterialBorrowForBatch[0] &&
    isMaterialBorrowPrintable(selectedMaterialBorrowForBatch[0]);

  const handleBatchDelete = async (keys: React.Key[]) => {
    const rows = keys
      .map((k) => listRowsRef.current.get(String(k)))
      .filter((r): r is MaterialBorrow => !!r && isMaterialBorrowDeletable(r));
    if (rows.length === 0) {
      messageApi.warning(t('app.kuaizhizao.warehouseCommon.batchDeleteNoneDeletable'));
      return;
    }
    try {
      for (const row of rows) {
        await warehouseApi.materialBorrow.delete(String(row.id));
      }
      messageApi.success(t('app.kuaizhizao.warehouseCommon.deleteSuccess', { count: rows.length }));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('app.kuaizhizao.warehouseCommon.batchDeleteFailed'));
    }
  };

  const handleSyncConfirm = async (rows: Record<string, any>[]) => {
    try {
      let successCount = 0;
      for (const row of rows) {
        const payload = {
          warehouse_id: row.warehouse_id ?? row.warehouseId,
          warehouse_name: row.warehouse_name || row.warehouseName,
          borrower_name: row.borrower_name || row.borrowerName,
          status: row.status || '待借出',
          items: Array.isArray(row.items) ? row.items : [],
        };
        await warehouseApi.materialBorrow.create(payload);
        successCount += 1;
      }
      messageApi.success(t('app.kuaizhizao.materialBorrow.msg.syncSuccess', { count: successCount }));
      invalidateMenuBadgeCounts();

      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error?.message || t('app.kuaizhizao.materialBorrow.msg.syncFailed'));
    }
  };

  const handlePrint = (record: MaterialBorrow) => {
    if (!record.id) return;
    openPrint({ documentType: 'material_borrow', documentId: record.id });
  };

  const appendBorrowItemsFromMaterials = useCallback(
    (selected: Material[]) => {
      const current = formRef.current?.getFieldValue('items') ?? [];
      const startIdx = (Array.isArray(current) ? current.length : 0);
      const newRows = selected.map((m) => ({
        ...defaultBorrowItem,
        material_id: m.id,
        material_code: m.mainCode ?? m.code ?? '',
        material_name: m.name ?? '',
        material_unit: resolveMaterialScenarioUnit(m, 'purchase') || m.baseUnit || '',
        batch_managed: isMaterialBatchEntryEnabled(trackingFlags, m.batchManaged),
      }));
      formRef.current?.setFieldsValue({ items: [...current, ...newRows] });
      void (async () => {
        for (let i = 0; i < selected.length; i += 1) {
          await applyMaterialBatchFlags(startIdx + i, selected[i]);
          const mid = Number(selected[i]?.id ?? 0);
          const whId = Number(selectedWarehouseId ?? 0);
          if (mid > 0 && whId > 0) void ensureBatchOptions(mid, whId);
        }
        syncLineMaterialKeyFromForm();
      })();
      messageApi.success(t('app.kuaizhizao.common.materialBatchAdded', { count: selected.length }));
    },
    [
      applyMaterialBatchFlags,
      ensureBatchOptions,
      messageApi,
      selectedWarehouseId,
      syncLineMaterialKeyFromForm,
      t,
      trackingFlags,
    ],
  );

  /** 参考销售订单：先打开弹窗，再让 CodeField 自动生成编号 */
  const handleCreate = () => {
    resetSelectedWarehouseId();
    resetMaterialBorrowFormFieldValues();
    setCreateModalVisible(true);
    // FormModalTemplate 设置了 destroyOnHidden，ProForm 每次打开都是全新挂载，无需 setTimeout + resetFields
  };
  useNewShortcut(handleCreate);
  const createButtonLabel = useMemo(
    () => withSingleNewShortcutHint(t('app.kuaizhizao.materialBorrow.create')),
    [t],
  );

  const handleCreateSubmit = async (values: any) => {
    try {
      const { standardValues, customData } = extractMaterialBorrowFormValues(values);
      const validItems = (standardValues.items ?? []).filter((it: any) => it.material_id && (Number(it.borrow_quantity) || 0) > 0);
      if (!validItems.length) {
        messageApi.error(t('app.kuaizhizao.materialBorrow.msg.needValidLines'));
        throw new Error(t('app.kuaizhizao.materialBorrow.msg.needValidLinesRule'));
      }
      for (const it of validItems) {
        const material = it.material_code || it.material_name || '-';
        if (!String(it.location_code || '').trim()) {
          const msg = t('app.kuaizhizao.warehouseOutbound.msg.selectLocationForMaterial', {
            material,
          });
          messageApi.error(msg);
          throw new Error(msg);
        }
        const qty = Number(it.borrow_quantity) || 0;
        const allocs = lineBatchAllocationsFromRow(it as Record<string, unknown>, qty);
        if (it.batch_managed) {
          const materialId = Number(it.material_id) || 0;
          const whId = Number(standardValues.warehouse_id) || 0;
          const key = materialId > 0 && whId > 0 ? `${materialId}:${whId}` : '';
          const opts = key ? batchOptionsByKey[key] ?? [] : [];
          if (!isValidOutboundBatchAllocations(allocs, opts, qty)) {
            const msg = t('app.kuaizhizao.warehouseOutbound.confirm.batchAllocationRequired', {
              material,
              qty,
              batches: opts.map((o) => o.value).join('、') || '—',
            });
            messageApi.error(msg);
            throw new Error(msg);
          }
        }
        if (isMaterialSerialEntryEnabled(trackingFlags, !!it.serial_managed)) {
          const serials = Array.isArray(it.serial_numbers)
            ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
            : [];
          const required = Math.round(qty);
          if (serials.length !== required) {
            const msg = t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
              material,
              required,
              actual: serials.length,
            });
            messageApi.error(msg);
            throw new Error(msg);
          }
          if (allocs.length > 1) {
            const msg = t('app.kuaizhizao.warehouseOutbound.confirm.batchSerialMultiNotSupported', {
              material,
            });
            messageApi.error(msg);
            throw new Error(msg);
          }
        }
      }
      const wh = warehouseList.find((w: any) => (w.id ?? w.warehouse_id) === standardValues.warehouse_id);
      const warehouseName = standardValues.warehouse_name ?? wh?.name ?? wh?.warehouse_name ?? '';
      const created = await warehouseApi.materialBorrow.create({
        borrow_code: standardValues.borrow_code,
        warehouse_id: standardValues.warehouse_id,
        warehouse_name: warehouseName,
        borrower_id: standardValues.borrower_id != null ? Number(standardValues.borrower_id) : undefined,
        borrower_name: standardValues.borrower_name,
        department: standardValues.department,
        expected_return_date: standardValues.expected_return_date ? formatDateTime(standardValues.expected_return_date, 'YYYY-MM-DD') : undefined,
        notes: standardValues.notes,
        attachments: normalizeDocumentAttachments(standardValues.attachments),
        items: validItems.flatMap((it: any) => {
          const qty = Number(it.borrow_quantity) || 0;
          const allocs = lineBatchAllocationsFromRow(it as Record<string, unknown>, qty);
          const serials =
            isMaterialSerialEntryEnabled(trackingFlags, !!it.serial_managed) &&
            Array.isArray(it.serial_numbers)
              ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
              : undefined;
          const base = {
            material_id: it.material_id,
            material_code: it.material_code || '',
            material_name: it.material_name || '',
            material_unit: it.material_unit || '',
            ...pickDocumentLineDualQuantityFields(it as Record<string, unknown>),
            location_code: it.location_code || undefined,
            warehouse_id: standardValues.warehouse_id,
            warehouse_name: warehouseName,
            ...(serials?.length ? { serial_numbers: serials } : {}),
          };
          if (allocs.length > 1) {
            return allocs.map((a) => ({
              ...base,
              borrow_quantity: a.quantity,
              batch_number: a.batchNo,
            }));
          }
          return [
            {
              ...base,
              borrow_quantity: qty,
              batch_number: allocs[0]?.batchNo || it.batch_number?.trim() || undefined,
            },
          ];
        }),
      });
      const recordId = Number((created as { id?: number })?.id ?? 0);
      if (recordId > 0) {
        await saveMaterialBorrowCustomFieldValues(recordId, customData);
      }
      messageApi.success(t('common.createSuccess'));
      resetSelectedWarehouseId();
      resetMaterialBorrowFormFieldValues();
      setCreateModalVisible(false);
      invalidateMenuBadgeCounts();

      actionRef.current?.reload();
    } catch (error: any) {
      if (error.message !== t('app.kuaizhizao.materialBorrow.msg.needValidLinesRule')) messageApi.error(error.message || t('common.createFailed'));
      throw error;
    }
  };

  const detailColumns = useMemo(() => alignDescriptionColumns([
    { title: t('app.kuaizhizao.materialBorrow.col.borrowCode'), dataIndex: 'borrow_code' },
    { title: t('app.kuaizhizao.warehouseReports.colWarehouse'), dataIndex: 'warehouse_name' },
    { title: t('app.kuaizhizao.materialBorrow.col.borrower'), dataIndex: 'borrower_name' },
    { title: t('app.kuaizhizao.materialBorrow.col.department'), dataIndex: 'department' },
    {
      title: t('common.status'),
      dataIndex: 'status',
      render: (s) => {
        const status = (s as string) || '';
        const colorMap: Record<string, string> = {
          '待借出': 'default',
          '已借出': 'success',
          '已取消': 'error',
        };
        return <Tag color={colorMap[status] || 'default'}>{translateMaterialBorrowStatus(t, status)}</Tag>;
      },
    },
    { title: t('app.kuaizhizao.materialBorrow.col.expectedReturnDate'), dataIndex: 'expected_return_date', valueType: 'date' },
    { title: t('app.kuaizhizao.materialBorrow.col.borrowTime'), dataIndex: 'borrow_time', valueType: 'dateTime' },
    { title: t('common.remark'), dataIndex: 'notes', span: 3 },
  ]), [t]);

  const detailCollaboration = useMemo(() => {
    if (!borrowDetail) return undefined;
    const lifecycle = getMaterialBorrowLifecycle(borrowDetail as unknown as Record<string, unknown>, t);
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
  }, [borrowDetail, t]);

  const timeconfigBasicItems = useDetailDrawerDescriptionItems(
    detailColumns, borrowDetail,
    'material_borrow',
  );

  return (
    <>
      <ListPageTemplate>
        <UniTable
          headerTitle={t('app.kuaizhizao.materialBorrow.title')}
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.materialBorrow)}
          columnPersistenceId="apps.kuaizhizao.pages.warehouse-management.material-borrows-width-v4"
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          showAdvancedSearch={true}
          pinnedTabsField={WAREHOUSE_DOC_PINNED_STATUS_FIELD}
          skipFuzzyPinyinClientFilter
          showCreateButton
          createButtonText={createButtonLabel}
          onCreate={handleCreate}
          enableRowSelection
          onTableDataChange={(rows) => {
            const next = new Map<string, MaterialBorrow>();
            for (const row of rows) {
              if (row.id != null) next.set(String(row.id), row);
            }
            listRowsRef.current = next;
          }}
          selectedRowKeys={selectedRowKeys}
          onRowSelectionChange={setSelectedRowKeys}
          showDeleteButton
          deleteButtonText={t('common.delete')}
          rowSelectionGetCheckboxProps={(record) => ({
            disabled: !isMaterialBorrowDeletable(record) && !isMaterialBorrowPrintable(record),
          })}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) =>
            t('app.kuaizhizao.warehouseCommon.batchDeleteConfirm', {
              count,
              noun: t('app.kuaizhizao.materialBorrow.title'),
            })
          }
          showImportButton={false}
          showExportButton
          onExport={async (type, keys, pageData) => {
            try {
              const loadAll = async () => {
                const listParams = resolveWarehouseDocListParams({}, undefined, {
                  docDateParamPrefix: 'borrow',
                });
                const rows = await fetchAllListItems((p) =>
                  warehouseApi.materialBorrow.list({ ...listParams, ...p }),
                );
                return enrichMaterialBorrowRecordsWithCustomFields(rows);
              };
              const headers = await resolveWarehouseListExportHeaders(
                type,
                keys,
                pageData as MaterialBorrow[] | undefined,
                listRowsRef.current,
                loadAll,
              );
              if (headers.length === 0) {
                messageApi.warning(t('common.exportNoData'));
                return;
              }
              const enriched = await enrichStandaloneDocsWithDetail(headers, (id) =>
                warehouseApi.materialBorrow.get(String(id)),
              );
              let flatRows = flattenStandaloneWarehouseDocsForExport(enriched, {
                docCodeField: 'borrow_code',
                docTypeLabel: t('app.kuaizhizao.warehouseOutbound.type.materialBorrow'),
                partnerField: 'borrower_name',
                dateFields: ['borrow_time'],
                operatorFields: ['borrower_name'],
              });
              if (type === 'selected' && keys?.length) {
                flatRows = filterWarehouseFlatRowsByExportKeys(flatRows, keys);
              }
              await exportWarehouseDocLinesXlsx(
                flatRows,
                `material-borrow-lines-${todaySiteDateString()}.xlsx`,
                {
                  t,
                  sheetName: t('app.kuaizhizao.materialBorrow.title'),
                  includeDocTypeColumn: false,
                  direction: 'standalone',
                },
              );
              messageApi.success(t('common.exportSuccess', { count: flatRows.length }));
            } catch (error: unknown) {
              messageApi.error((error as { message?: string })?.message || t('common.exportFailed'));
            }
          }}
          showSyncButton
          onSync={() => setSyncModalVisible(true)}
          request={async (params, sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
            try {
              const listParams = resolveWarehouseDocListParams(searchFormValues, sort, {
                docDateParamPrefix: 'borrow',
              });
              const response = await warehouseApi.materialBorrow.list({
                skip: ((params.current || 1) - 1) * (params.pageSize || 20),
                limit: params.pageSize || 20,
                ...listParams,
              });
              const { data: raw, total } = normalizeWarehouseListResponse(response);
              const data = meta?.purpose === 'prefetch'
                ? raw
                : await enrichMaterialBorrowRecordsWithCustomFields(raw);
              return { data, success: true, total };
            } catch {
              messageApi.error(t('app.kuaizhizao.materialBorrow.msg.loadListFailed'));
              return { data: [], success: false, total: 0 };
            }
          }}
          showPrintButton
          printButtonDisabled={!canToolbarPrint}
          printButtonText={t('components.uniAction.print')}
          onPrint={() => {
            const row = selectedMaterialBorrowForBatch[0];
            if (row) handlePrint(row);
          }}
        />
      </ListPageTemplate>

      <DetailDrawerTemplate
        title={`${t('app.kuaizhizao.materialBorrow.detailTitle')}${borrowDetail?.borrow_code ? ` - ${borrowDetail.borrow_code}` : ''}`}
        open={detailDrawerVisible}
        loading={detailLoading}
        onClose={() => {
          setDetailDrawerVisible(false);
          setBorrowDetail(null);
          resetMaterialBorrowDetailFieldValues();
        }}
        size={DRAWER_CONFIG.HALF_WIDTH}
        basic={
          borrowDetail ? (
            <Descriptions column={detailDrawerBasicColumn(false)} size="small" items={timeconfigBasicItems} />
          ) : undefined
        }
        collaboration={detailCollaboration}
        supplementary={
          borrowDetail &&
          hasCustomFieldsDetailContent(materialBorrowListCustomFields, materialBorrowDetailCustomFieldValues) ? (
            <CustomFieldsDetailSection
              customFields={materialBorrowListCustomFields}
              customFieldValues={materialBorrowDetailCustomFieldValues}
            />
          ) : undefined
        }
        linesTitle={t('app.kuaizhizao.warehouseOutbound.section.lines')}
        lines={
          borrowDetail?.items && borrowDetail.items.length > 0 ? (
            <>
              <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
              <Table
                className="warehouse-detail-table"
                size="small"
                rowKey="id"
                columns={filterWarehouseTrackingColumns(
                  [
                    {
                      title: t('app.kuaizhizao.warehouseOutbound.col.materialCode'),
                      dataIndex: 'material_code',
                      width: 120,
                    },
                    {
                      title: t('app.kuaizhizao.warehouseOutbound.col.materialName'),
                      dataIndex: 'material_name',
                      width: 150,
                    },
                    { title: t('common.unit'), dataIndex: 'material_unit', width: 60 },
                    {
                      title: t('app.kuaizhizao.warehouseOutbound.col.location'),
                      dataIndex: 'location_code',
                      width: 120,
                      render: (v) => v || '-',
                    },
                    {
                      title: t('app.kuaizhizao.warehouseOutbound.col.batchNo'),
                      key: 'batch',
                      dataIndex: 'batch_number',
                      width: 100,
                      render: (v) => (v ? String(v) : '-'),
                    },
                    buildDocumentDetailSerialReadonlyColumn(t),
                    {
                      title: t('app.kuaizhizao.materialBorrow.col.borrowQty'),
                      dataIndex: 'borrow_quantity',
                      width: 100,
                      align: 'right',
                    },
                    buildDocumentLineAuxQuantityDetailColumn({ t, width: 120 }),
                    {
                      title: t('app.kuaizhizao.materialBorrow.col.returnedQty'),
                      dataIndex: 'returned_quantity',
                      width: 100,
                      align: 'right',
                    },
                    { title: t('common.status'), dataIndex: 'status', width: 80 },
                  ],
                  trackingFlags,
                )}
                dataSource={borrowDetail.items}
                pagination={false}
              />
            </>
          ) : undefined
        }
      />

      <FormModalTemplate
        title={t('app.kuaizhizao.materialBorrow.createModal')}
        open={createModalVisible}
        onClose={() => {
          resetSelectedWarehouseId();
          resetMaterialBorrowFormFieldValues();
          setCreateModalVisible(false);
        }}
        formRef={formRef}
        onFinish={handleCreateSubmit}
        width={MODAL_CONFIG.LARGE_WIDTH}
        grid={false}
      >
        <Row gutter={16}>
          <Col span={12}>
            <CodeField
              pageCode="kuaizhizao-warehouse-material-borrow"
              name="borrow_code"
              label={t('app.kuaizhizao.materialBorrow.field.borrowCode')}
              autoGenerateOnCreate={true}
              showGenerateButton={false}
              context={{}}
            />
          </Col>
          <Col span={12}>
            <UniWarehouseSelect
              name="warehouse_id"
              label={t('app.kuaizhizao.warehouseReports.colWarehouse')}
              placeholder={t('app.kuaizhizao.warehouseOutbound.field.selectWarehouse')}
              required
              onChange={(val, wh) => {
                updateSelectedWarehouseId(val);
                const items = formRef.current?.getFieldValue('items') || [];
                formRef.current?.setFieldsValue({
                  warehouse_name: wh?.name ?? '',
                  // 换仓后明细必须重选本仓物料/库位，禁止保留他仓选中项
                  items: (Array.isArray(items) ? items : []).map((row: Record<string, unknown>) => ({
                    ...row,
                    material_id: undefined,
                    material_code: '',
                    material_name: '',
                    material_unit: '',
                    location_code: undefined,
                    batch_number: undefined,
                    batch_managed: false,
                  })),
                });
                syncLineMaterialKeyFromForm();
              }}
            />
          </Col>
        </Row>
        <AntForm.Item name="warehouse_name" hidden />
        <AntForm.Item name="borrower_id" hidden />
        <AntForm.Item name="department_uuid" hidden />
        <Row gutter={16}>
          <Col span={12}>
            <UniUserSelect
              name="borrower_uuid"
              label={t('app.kuaizhizao.materialBorrow.field.borrower')}
              placeholder={t('app.kuaizhizao.materialBorrow.field.selectBorrower')}
              onChange={(_value: any, user: any) => {
                const picked = Array.isArray(user) ? user[0] : user;
                formRef.current?.setFieldsValue({
                  borrower_id: picked?.id,
                  borrower_name: picked?.full_name || picked?.username || undefined,
                });
              }}
            />
            <AntForm.Item name="borrower_name" hidden>
              <Input />
            </AntForm.Item>
          </Col>
          <Col span={12}>
            <ProFormItem name="department_uuid" label={t('app.kuaizhizao.materialBorrow.col.department')}>
              <UniDropdown
                placeholder={t('app.kuaizhizao.materialBorrow.field.selectDepartment')}
                options={departmentOptions}
                showSearch
                optionFilterProp="label"
                onChange={(value) => {
                  const selected = departmentOptions.find((d) => d.value === value);
                  const label = selected?.label;
                  const deptName = label ? String(label).split(' / ').pop() || label : undefined;
                  formRef.current?.setFieldsValue({ department: deptName });
                }}
              />
            </ProFormItem>
            <AntForm.Item name="department" hidden>
              <Input />
            </AntForm.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <ProFormItem name="expected_return_date" label={t('app.kuaizhizao.materialBorrow.field.expectedReturnDate')}>
              <FutureDatePicker getForm={() => formRef.current} t={t} style={{ width: '100%' }} />
            </ProFormItem>
          </Col>
          <Col span={12} />
        </Row>
        <div className="uni-table-detail" style={{ width: '100%' }}>
          <UniTableDetailHeader title={t('app.kuaizhizao.warehouseOutbound.section.lines')} required />
          <AntForm.Item name="items" noStyle rules={[{ type: 'array', min: 1, message: t('app.kuaizhizao.materialBorrow.msg.needValidLinesRule') }]}>
            <AntForm.List name="items">
              {(fields, { add, remove }) => {
                const cols = [
                  {
                    title: t('app.kuaizhizao.warehouseOutbound.field.material'),
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
                                placeholder={
                                  selectedWarehouseId
                                    ? t('app.kuaizhizao.warehouseOutbound.field.selectMaterial')
                                    : t('app.kuaizhizao.warehouseOutbound.field.selectWarehouseFirst')
                                }
                                required
                                size="small"
                                disabled={!selectedWarehouseId}
                                warehouseId={selectedWarehouseId}
                                listFieldKey={index}
                                listFieldName="items"
                                fillMapping={{
                                  material_code: 'mainCode',
                                  material_name: 'name',
                                  material_unit: 'baseUnit',
                                }}
                                onChange={async (_val, material) => {
                                  formRef.current?.setFieldValue(['items', index, 'batch_number'], undefined);
                                  formRef.current?.setFieldValue(['items', index, 'batch_allocations'], []);
                                  if (material) {
                                    formRef.current?.setFieldValue(
                                      ['items', index, 'material_unit'],
                                      resolveMaterialScenarioUnit(material, 'purchase') || material.baseUnit || '',
                                    );
                                    await applyMaterialBatchFlags(index, material);
                                    const mid = Number(_val ?? material.id ?? 0);
                                    const whId = Number(selectedWarehouseId ?? 0);
                                    if (mid > 0 && whId > 0) {
                                      void ensureBatchOptions(mid, whId);
                                    }
                                  }
                                  syncLineMaterialKeyFromForm();
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
                  buildDocumentDetailTotalStockFormColumn(t),
                  {
                    title: t('app.kuaizhizao.warehouseOutbound.col.location'),
                    dataIndex: 'location_code',
                    width: 180,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        name={[index, 'location_code']}
                        style={{ margin: 0 }}
                        rules={[
                          {
                            required: true,
                            message: t('app.kuaizhizao.warehouseOutbound.field.selectLocation'),
                          },
                        ]}
                      >
                        <Select
                          options={locationOptions}
                          placeholder={selectedWarehouseId ? t('app.kuaizhizao.warehouseOutbound.field.selectLocation') : t('app.kuaizhizao.warehouseOutbound.field.selectWarehouseFirst')}
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
                    title: t('app.kuaizhizao.warehouseOutbound.col.batchNo'),
                    key: 'batch',
                    dataIndex: 'batch_allocations',
                    width: 260,
                    render: (_: any, __: any, index: number) => (
                      <AntForm.Item
                        noStyle
                        shouldUpdate={(prev, curr) =>
                          prev?.items?.[index] !== curr?.items?.[index] ||
                          prev?.warehouse_id !== curr?.warehouse_id
                        }
                      >
                        {({ getFieldValue }) => {
                          const row = getFieldValue('items')?.[index] as
                            | Record<string, unknown>
                            | undefined;
                          if (!row?.batch_managed) return '—';
                          const materialId = Number(row?.material_id ?? 0);
                          const whId = Number(selectedWarehouseId ?? 0);
                          const key = materialId > 0 && whId > 0 ? `${materialId}:${whId}` : '';
                          const opts = key ? batchOptionsByKey[key] ?? [] : [];
                          const loading = !!key && batchOptionsLoadingKey === key;
                          const qty = Number(row?.borrow_quantity ?? 0);
                          const allocs = lineBatchAllocationsFromRow(row, qty);
                          const materialLabel = [row?.material_code, row?.material_name]
                            .filter(Boolean)
                            .join(' - ');
                          const disabled = !(whId > 0) || !(materialId > 0);
                          return (
                            <span
                              onClick={() => {
                                if (
                                  !disabled &&
                                  materialId > 0 &&
                                  whId > 0 &&
                                  !batchOptionsByKey[key]?.length
                                ) {
                                  void ensureBatchOptions(materialId, whId);
                                }
                              }}
                            >
                              <AntForm.Item name={[index, 'batch_allocations']} hidden>
                                <Input />
                              </AntForm.Item>
                              <AntForm.Item name={[index, 'batch_number']} hidden>
                                <Input />
                              </AntForm.Item>
                              <OutboundBatchAllocationField
                                value={allocs}
                                onChange={(next) =>
                                  syncFormLineBatchFields(
                                    (name, value) => formRef.current?.setFieldValue(name, value),
                                    index,
                                    next,
                                  )
                                }
                                options={opts}
                                totalQuantity={qty}
                                loading={loading}
                                disabled={disabled}
                                materialLabel={String(materialLabel)}
                              />
                            </span>
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  {
                    title: t('app.kuaizhizao.warehouseOutbound.col.serialNo'),
                    key: 'serial_numbers',
                    dataIndex: 'serial_numbers',
                    width: 160,
                    render: (_: unknown, __: unknown, index: number) => (
                      <AntForm.Item
                        noStyle
                        shouldUpdate={(prev, curr) => prev?.items?.[index] !== curr?.items?.[index]}
                      >
                        {({ getFieldValue }) => {
                          const row = getFieldValue('items')?.[index];
                          if (!isMaterialSerialEntryEnabled(trackingFlags, row?.serial_managed)) {
                            return <span>—</span>;
                          }
                          const qty = Number(row?.borrow_quantity ?? 0);
                          const sn = getFieldValue(['items', index, 'serial_numbers']);
                          const uuid = String(row?.material_uuid ?? '').trim();
                          const serials = Array.isArray(sn)
                            ? sn.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
                            : [];
                          return (
                            <>
                              <AntForm.Item name={[index, 'serial_numbers']} hidden>
                                <Input />
                              </AntForm.Item>
                              <OutboundSerialPickerField
                                value={serials}
                                onChange={(next) =>
                                  formRef.current?.setFieldValue(['items', index, 'serial_numbers'], next)
                                }
                                options={uuid ? serialOptionsByUuid[uuid] ?? [] : []}
                                maxCount={qty > 0 ? Math.round(qty) : undefined}
                                loading={!!uuid && serialOptionsLoadingUuid === uuid}
                                onOpenPicker={() => {
                                  if (uuid) void ensureSerialOptions(uuid, serials);
                                }}
                                materialLabel={String(row?.material_code || row?.material_name || '')}
                              />
                            </>
                          );
                        }}
                      </AntForm.Item>
                    ),
                  },
                  ...buildDocumentLineDualQuantityPairColumns({
                    t,
                    getForm: () => formRef.current,
                    quantityField: 'borrow_quantity',
                    unitField: 'material_unit',
                    scenario: 'purchase',
                    quantityPrecision: quantityDecimals,
                    width: 168,
                    columnSpread: { align: 'right' as const },
                  }),
                  {
                    title: t('common.actions'),
                    width: 60,
                    render: (_: any, __: any, index: number) => (
                      <Button type="link" danger size="small" icon={<DeleteOutlined />} onClick={() => remove(index)} disabled={fields.length <= 1} />
                    ),
                  },
                ];
                const visibleCols = filterWarehouseTrackingColumns(cols, trackingFlags);
                const totalWidth = visibleCols.reduce((s, c) => s + (c.width as number || 0), 0);
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
                        columns={visibleCols}
                        scroll={fields.length > 0 ? { x: totalWidth } : undefined}
                        style={{ width: '100%', margin: 0 }}
                        footer={() => (
                          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', width: '100%' }}>
                            <Button type="dashed" icon={<PlusOutlined />} style={{ flex: 1, minWidth: 120 }} onClick={() => add(defaultBorrowItem)}>
                              {t('app.kuaizhizao.warehouseOutbound.action.addLine')}
                            </Button>
                            <Button
                              type="default"
                              icon={<ShoppingOutlined />}
                              style={{ flex: 1, minWidth: 120 }}
                              disabled={!selectedWarehouseId}
                              onClick={() => {
                                if (!selectedWarehouseId) {
                                  messageApi.warning(t('app.kuaizhizao.warehouseOutbound.field.selectWarehouseFirst'));
                                  return;
                                }
                                setMaterialPickerOpen(true);
                              }}
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
          </AntForm.Item>
        </div>
        <CustomFieldsFormSection
          customFields={materialBorrowFormCustomFields}
          customFieldValues={materialBorrowFormCustomFieldValues}
          gridColumns={2}
        />
        <DocumentAttachmentsField category="material_borrow_attachments" />
        <ProFormTextArea name="notes" label={t('common.remark')} placeholder={t('app.kuaizhizao.warehouseOutbound.field.optional')} fieldProps={{ rows: 2 }} />
      </FormModalTemplate>

      <SyncFromDatasetModal
        open={syncModalVisible}
        onClose={() => setSyncModalVisible(false)}
        onConfirm={handleSyncConfirm}
        title={t('app.kuaizhizao.materialBorrow.syncTitle')}
      />

      <UniMaterialBatchPicker
        open={materialPickerOpen}
        onCancel={() => setMaterialPickerOpen(false)}
        onConfirm={appendBorrowItemsFromMaterials}
        warehouseId={selectedWarehouseId}
      />
      <OutboundHubEditModal
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

export default MaterialBorrowsPage;
