/**
 * 还料单管理页面
 *
 * 提供还料单的创建、查看、确认和管理功能（必须关联借料单）
 *
 * @author RiverEdge Team
 * @date 2026-02-19
 */

import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { isInboundEditable, type InboundHubOrder } from '../inbound/inboundHubTypes';
import { ActionType, ProColumns, ProDescriptionsItemProps, ProFormItem, ProFormTextArea } from '@ant-design/pro-components';
import { App, Button, Col, Descriptions, Form, InputNumber, Modal, Row, Select, Table, Tag, Typography } from 'antd';
import { EyeOutlined, CheckCircleOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { UniTable, type UniTableRequestMeta } from '../../../../../components/uni-table';
import { UniDropdown } from '../../../../../components/uni-dropdown';
import { UniUserSelect } from '../../../../../components/uni-user-select';
import { UniTableDetailHeader } from '../../../../../components/uni-table-detail/UniTableDetail';
import CodeField from '../../../../../components/code-field';
import {   useDetailDrawerDescriptionItems, detailDrawerBasicColumn, DetailDrawerTemplate, DRAWER_CONFIG, FormModalTemplate, ListPageTemplate, MODAL_CONFIG, WAREHOUSE_DETAIL_TABLE_STYLES } from '../../../../../components/layout-templates';
import { warehouseApi } from '../../../services/production';
import { UniLifecycle, UniLifecycleStepper } from '../../../../../components/uni-lifecycle';
import { getMaterialReturnLifecycle } from '../../../utils/materialReturnLifecycle';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import { normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { rowActionKind, rowActionLabelKeep } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { useKuaizhizaoPrintModal } from '../../../hooks/useKuaizhizaoPrintModal';
import { formatDateTime, formatQuantity, todaySiteDateString } from '../../../../../utils/format';
import { buildDocumentLineAuxQuantityDetailColumn } from '../../../../../components/quantity-with-unit';
import { buildDocumentDetailSerialReadonlyColumn } from '../../../components/documentDetailSerialNumberColumn';
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
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../../sales-management/shared/documentLineMaterialsPreview';
import {
  WAREHOUSE_DOC_PINNED_STATUS_FIELD,
  buildMaterialReturnStatusValueEnum,
  normalizeWarehouseListResponse,
  resolveWarehouseDocListParams,
} from '../../../utils/warehouseListCore';
import { useNewShortcut } from '../../../../../hooks/useNewShortcut';
import { withSingleNewShortcutHint } from '../../../../../utils/globalNewShortcut';
import { SUBMIT_SHORTCUT_HINT } from '../../../../../utils/globalSubmitShortcut';
import { ROUTES } from '../../../constants/routes';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { fetchMaterialForUnitSelectCache } from '../../../../../components/material-unit-select';
import { getPopupContainerInModal } from '../../../../../utils/modalEventIsolation';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import OutboundSerialPickerField from '../outbound/OutboundSerialPickerField';
import { useWarehouseLocationOptions } from '../../../hooks/useWarehouseLocationOptions';
import { runInboundHubConfirmFromRecord } from '../inbound/inboundHubRunConfirm';
import { formatApiErrorDetail } from '../../../../../services/api';
import { useCustomFields } from '../../../../../hooks/useCustomFields';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import {
  CustomFieldsFormSection,
  CustomFieldsDetailSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';

const MATERIAL_RETURN_CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_material_returns';

interface MaterialReturn {
  id?: number;
  tenant_id?: number;
  return_code?: string;
  borrow_id?: number;
  borrow_code?: string;
  warehouse_id?: number;
  warehouse_name?: string;
  returner_id?: number;
  returner_name?: string;
  return_time?: string;
  status?: string;
  total_quantity?: number;
  total_items?: number;
  /** 列表「明细」列预览（仅 material_name） */
  items?: { material_name?: string }[];
  notes?: string;
  created_at?: string;
  updated_at?: string;
}

interface MaterialReturnDetail extends MaterialReturn {
  items?: MaterialReturnItem[];
}

interface MaterialReturnItem {
  id?: number;
  borrow_item_id?: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_unit?: string;
  return_quantity?: number;
  location_id?: number;
  location_code?: string;
  batch_number?: string;
  status?: string;
}

interface BorrowItemForReturn {
  id: number;
  material_id: number;
  material_code: string;
  material_name: string;
  material_unit: string;
  borrow_quantity: number;
  returned_quantity: number;
  warehouse_id: number;
  warehouse_name: string;
  location_id?: number;
  location_code?: string;
  batch_number?: string;
  batch_managed?: boolean;
  serial_managed?: boolean;
  available_serial_numbers?: string[];
}

type ReturnLineTrackingDraft = {
  location_code?: string;
  location_id?: number;
  batch_number?: string;
  batch_managed?: boolean;
  serial_managed?: boolean;
};

const MaterialReturnsPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { openPrint, PrintModal } = useKuaizhizaoPrintModal();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>(null);

  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const returnPerms = useResourcePermissions('kuaizhizao:material-return');
  const canUpdateReturn = returnPerms.canUpdate ?? false;
  const [editReturnId, setEditReturnId] = useState<number | null>(null);
  const [detailDrawerVisible, setDetailDrawerVisible] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [returnDetail, setReturnDetail] = useState<MaterialReturnDetail | null>(null);

  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const formRef = useRef<any>(null);
  const [borrowList, setBorrowList] = useState<any[]>([]);
  const [borrowLoading, setBorrowLoading] = useState(false);
  const [selectedBorrowDetail, setSelectedBorrowDetail] = useState<{ borrow_id: number; borrow_code: string; warehouse_id: number; warehouse_name: string; items: BorrowItemForReturn[] } | null>(null);
  const [returnQuantities, setReturnQuantities] = useState<Record<number, number>>({});
  const [returnLineSerial, setReturnLineSerial] = useState<Record<number, string[]>>({});
  const [returnLineTracking, setReturnLineTracking] = useState<Record<number, ReturnLineTrackingDraft>>({});
  const trackingFlags = useWarehouseTrackingFlags();
  const {
    locationOptions,
    updateSelectedWarehouseId,
    resetSelectedWarehouseId,
  } = useWarehouseLocationOptions();

  const {
    customFields: materialReturnFormCustomFields,
    customFieldValues: materialReturnFormCustomFieldValues,
    loadFieldValues: loadMaterialReturnFormFieldValues,
    extractFormValues: extractMaterialReturnFormValues,
    saveCustomFieldValues: saveMaterialReturnCustomFieldValues,
    resetFieldValues: resetMaterialReturnFormFieldValues,
  } = useCustomFields({
    tableName: MATERIAL_RETURN_CUSTOM_FIELD_TABLE,
    loadWhenOpen: true,
    open: createModalVisible,
  });

  const {
    customFields: materialReturnListCustomFields,
    generateCustomFieldColumns: generateMaterialReturnCustomFieldColumns,
    enrichRecordsWithCustomFields: enrichMaterialReturnRecordsWithCustomFields,
    customFieldValues: materialReturnDetailCustomFieldValues,
    loadFieldValuesForDetail: loadMaterialReturnFieldValuesForDetail,
    resetDetailFieldValues: resetMaterialReturnDetailFieldValues,
  } = useCustomFieldsForList<MaterialReturn>({ tableName: MATERIAL_RETURN_CUSTOM_FIELD_TABLE });

  const materialReturnCustomFieldColumns = generateMaterialReturnCustomFieldColumns();

  useEffect(() => {
    const load = async () => {
      if (!createModalVisible) return;
      setBorrowLoading(true);
      try {
        const chunkSize = 100;
        const maxRows = 500;
        const rows: any[] = [];
        let skip = 0;
        while (rows.length < maxRows) {
          const res = await warehouseApi.materialBorrow.list({ status: '已借出', skip, limit: chunkSize });
          const chunk = Array.isArray(res) ? res : (res as any)?.items || (res as any)?.data || [];
          if (!Array.isArray(chunk) || chunk.length === 0) break;
          rows.push(...chunk);
          if (chunk.length < chunkSize) break;
          skip += chunkSize;
        }
        setBorrowList(rows.slice(0, maxRows));
      } catch {
        setBorrowList([]);
      } finally {
        setBorrowLoading(false);
      }
    };
    load();
  }, [createModalVisible]);

  const resolveBorrowItemBatchManaged = useCallback(
    async (materialId: number) => {
      const m = await fetchMaterialForUnitSelectCache(materialId);
      return isMaterialBatchEntryEnabled(trackingFlags, m?.batchManaged);
    },
    [trackingFlags],
  );

  const resolveBorrowItemSerialManaged = useCallback(
    async (materialId: number) => {
      const m = await fetchMaterialForUnitSelectCache(materialId);
      return isMaterialSerialEntryEnabled(trackingFlags, m?.serialManaged);
    },
    [trackingFlags],
  );

  const onBorrowSelect = async (borrowId: number) => {
    if (!borrowId) {
      setSelectedBorrowDetail(null);
      setReturnQuantities({});
      setReturnLineSerial({});
      setReturnLineTracking({});
      resetSelectedWarehouseId();
      return;
    }
    try {
      const detail = await warehouseApi.materialBorrow.get(borrowId.toString());
      const items = (detail as any).items || [];
      const whId = (detail as any).warehouse_id;
      updateSelectedWarehouseId(whId);
      const borrowItems: BorrowItemForReturn[] = await Promise.all(
        items.map(async (it: any) => {
          const materialId = Number(it.material_id);
          const batchManaged = await resolveBorrowItemBatchManaged(materialId);
          const serialManaged = await resolveBorrowItemSerialManaged(materialId);
          const available = Array.isArray(it.available_serial_numbers)
            ? it.available_serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
            : Array.isArray(it.serial_numbers)
              ? it.serial_numbers.map((s: unknown) => String(s ?? '').trim()).filter(Boolean)
              : [];
          return {
            id: it.id,
            material_id: it.material_id,
            material_code: it.material_code,
            material_name: it.material_name,
            material_unit: it.material_unit,
            borrow_quantity: it.borrow_quantity ?? 0,
            returned_quantity: it.returned_quantity ?? 0,
            warehouse_id: it.warehouse_id ?? whId,
            warehouse_name: it.warehouse_name ?? (detail as any).warehouse_name,
            location_id: it.location_id ?? undefined,
            location_code: it.location_code ?? undefined,
            batch_number: it.batch_number ?? undefined,
            batch_managed: batchManaged,
            serial_managed: serialManaged,
            available_serial_numbers: available,
          };
        }),
      );
      setSelectedBorrowDetail({
        borrow_id: (detail as any).id,
        borrow_code: (detail as any).borrow_code,
        warehouse_id: whId,
        warehouse_name: (detail as any).warehouse_name,
        items: borrowItems,
      });
      const qtyMap: Record<number, number> = {};
      const serialMap: Record<number, string[]> = {};
      const trackMap: Record<number, ReturnLineTrackingDraft> = {};
      borrowItems.forEach((it) => {
        const maxRet = Math.max(0, it.borrow_quantity - it.returned_quantity);
        const qty = maxRet > 0 ? maxRet : 0;
        qtyMap[it.id] = qty;
        trackMap[it.id] = {
          location_id: it.location_id,
          location_code: it.location_code,
          batch_number: it.batch_number,
          batch_managed: it.batch_managed,
          serial_managed: it.serial_managed,
        };
        const pool = it.available_serial_numbers ?? [];
        if (isMaterialSerialEntryEnabled(trackingFlags, it.serial_managed) && qty > 0 && pool.length) {
          serialMap[it.id] = pool.slice(0, Math.min(Math.round(qty), pool.length));
        }
      });
      setReturnQuantities(qtyMap);
      setReturnLineSerial(serialMap);
      setReturnLineTracking(trackMap);
    } catch {
      messageApi.error(t('app.kuaizhizao.warehouseMaterialReturn.msg.loadBorrowDetailFailed'));
      setSelectedBorrowDetail(null);
      setReturnLineTracking({});
      resetSelectedWarehouseId();
    }
  };

  const handleDetail = async (record: MaterialReturn) => {
    setDetailDrawerVisible(true);
    setDetailLoading(true);
    setReturnDetail(null);
    resetMaterialReturnDetailFieldValues();
    try {
      const detail = await warehouseApi.materialReturn.get(record.id!.toString());
      setReturnDetail(detail as MaterialReturnDetail);
      if (record.id != null) {
        await loadMaterialReturnFieldValuesForDetail(record.id);
      }
    } catch {
      messageApi.error(t('app.kuaizhizao.warehouseMaterialReturn.msg.loadDetailFailed'));
      setDetailDrawerVisible(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const executeConfirm = async (record: MaterialReturn) => {
    if (record.id == null) return;
    try {
      const confirmResult = await runInboundHubConfirmFromRecord({
        t,
        record: { id: record.id, receipt_type: 'material_return' },
        trackingFlags,
      });
      messageApi.success(t('app.kuaizhizao.warehouseMaterialReturn.msg.confirmSuccess'));
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
          t('app.kuaizhizao.warehouseMaterialReturn.msg.confirmFailed'),
      );
    }
  };

  const listRowsRef = useRef<Map<string, MaterialReturn>>(new Map());
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const isMaterialReturnDeletable = (record: MaterialReturn) => record.status === '待归还' && !!record.id;
  const isMaterialReturnPrintable = (record: MaterialReturn) =>
    (record.status === '待归还' || record.status === '已归还') && !!record.id;

  const selectedMaterialReturnForBatch = useMemo(
    () =>
      selectedRowKeys
        .map((key) => listRowsRef.current.get(String(key)))
        .filter((row): row is MaterialReturn => row != null),
    [selectedRowKeys],
  );

  const canToolbarPrint =
    selectedRowKeys.length === 1 &&
    !!selectedMaterialReturnForBatch[0] &&
    isMaterialReturnPrintable(selectedMaterialReturnForBatch[0]);

  const handleBatchDelete = async (keys: React.Key[]) => {
    const rows = keys
      .map((k) => listRowsRef.current.get(String(k)))
      .filter((r): r is MaterialReturn => !!r && isMaterialReturnDeletable(r));
    if (rows.length === 0) {
      messageApi.warning(t('app.kuaizhizao.warehouseCommon.batchDeleteNoneDeletable'));
      return;
    }
    try {
      for (const row of rows) {
        await warehouseApi.materialReturn.delete(String(row.id));
      }
      messageApi.success(t('app.kuaizhizao.warehouseCommon.deleteSuccess', { count: rows.length }));
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(error.message || t('app.kuaizhizao.warehouseCommon.batchDeleteFailed'));
    }
  };

  const handlePrint = (record: MaterialReturn) => {
    if (!record.id) return;
    openPrint({ documentType: 'material_return', documentId: record.id });
  };

  const handleCreate = () => {
    setEditReturnId(null);
    resetMaterialReturnFormFieldValues();
    setCreateModalVisible(true);
    setSelectedBorrowDetail(null);
    setReturnQuantities({});
    setReturnLineTracking({});
    resetSelectedWarehouseId();
  };

  const openEditReturn = async (record: MaterialReturn) => {
    if (record.id == null) return;
    setEditReturnId(record.id);
    setCreateModalVisible(true);
    setSelectedBorrowDetail(null);
    setReturnQuantities({});
    setReturnLineTracking({});
    resetSelectedWarehouseId();
    try {
      const detail = (await warehouseApi.materialReturn.get(String(record.id))) as MaterialReturnDetail;
      if (detail.status !== '待归还') {
        messageApi.warning(t('app.kuaizhizao.warehouseMaterialReturn.msg.editPendingOnly'));
        setCreateModalVisible(false);
        setEditReturnId(null);
        return;
      }
      await onBorrowSelect(Number(detail.borrow_id));
      const qtyMap: Record<number, number> = {};
      const trackMap: Record<number, ReturnLineTrackingDraft> = {};
      for (const line of detail.items ?? []) {
        const borrowItemId = line.borrow_item_id;
        if (borrowItemId == null) continue;
        qtyMap[borrowItemId] = Number(line.return_quantity ?? 0);
        trackMap[borrowItemId] = {
          location_id: line.location_id,
          location_code: line.location_code,
          batch_number: line.batch_number,
        };
      }
      setReturnQuantities(qtyMap);
      setReturnLineTracking(trackMap);
      formRef.current?.setFieldsValue({
        return_code: detail.return_code,
        borrow_id: detail.borrow_id,
        returner_id: detail.returner_id,
        returner_name: detail.returner_name,
        notes: detail.notes,
        attachments: detail.attachments,
      });
      window.setTimeout(() => {
        void loadMaterialReturnFormFieldValues(record.id!).then((fieldFormValues) => {
          formRef.current?.setFieldsValue(fieldFormValues);
        });
      }, 100);
    } catch {
      messageApi.error(t('app.kuaizhizao.warehouseMaterialReturn.msg.loadDetailFailed'));
      setCreateModalVisible(false);
      setEditReturnId(null);
    }
  };

  const handledDeepLinkEditIdRef = useRef<string | null>(null);
  useEffect(() => {
    const rawEditId = searchParams.get('editId');
    if (!rawEditId || handledDeepLinkEditIdRef.current === rawEditId) return;
    const editId = Number(rawEditId);
    if (!Number.isFinite(editId) || editId <= 0) return;
    handledDeepLinkEditIdRef.current = rawEditId;
    void openEditReturn({ id: editId });
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.delete('editId');
      return next;
    }, { replace: true });
  }, [searchParams, setSearchParams]);

  useNewShortcut(handleCreate);
  const createButtonLabel = useMemo(
    () => withSingleNewShortcutHint(t('app.kuaizhizao.warehouseMaterialReturn.create')),
    [t],
  );

  const createMaterialReturn = async (values: any, andConfirm: boolean) => {
    if (!selectedBorrowDetail) {
      messageApi.error(t('app.kuaizhizao.warehouseMaterialReturn.msg.selectBorrow'));
      throw new Error(t('app.kuaizhizao.warehouseMaterialReturn.msg.selectBorrow'));
    }
    const validItems = selectedBorrowDetail.items
      .filter((it) => (returnQuantities[it.id] ?? 0) > 0)
      .map((it) => {
        const track = returnLineTracking[it.id] ?? {};
        const locationCode = String(track.location_code ?? it.location_code ?? '').trim();
        if (!locationCode) {
          const msg = t('app.kuaizhizao.warehouseOutbound.msg.selectLocationForMaterial', {
            material: it.material_code || it.material_name || '-',
          });
          messageApi.error(msg);
          throw new Error(msg);
        }
        const batch = String(track.batch_number ?? it.batch_number ?? '').trim();
        if (track.batch_managed && !batch) {
          const msg = t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
            material: it.material_code || it.material_name || '-',
            batches: '—',
          });
          messageApi.error(msg);
          throw new Error(msg);
        }
        const returnQty = Number(returnQuantities[it.id] ?? 0);
        const materialLabel = it.material_code || it.material_name || '-';
        let serialPayload: string[] | undefined;
        if (isMaterialSerialEntryEnabled(trackingFlags, track.serial_managed ?? it.serial_managed)) {
          const serials = (returnLineSerial[it.id] ?? [])
            .map((s) => String(s ?? '').trim())
            .filter(Boolean);
          const required = Math.round(returnQty);
          if (serials.length !== required) {
            const msg = t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
              material: materialLabel,
              required,
              actual: serials.length,
            });
            messageApi.error(msg);
            throw new Error(msg);
          }
          serialPayload = serials;
        }
        return {
          borrow_item_id: it.id,
          material_id: it.material_id,
          material_code: it.material_code,
          material_name: it.material_name,
          material_unit: it.material_unit,
          return_quantity: returnQty,
          warehouse_id: selectedBorrowDetail.warehouse_id,
          warehouse_name: selectedBorrowDetail.warehouse_name,
          location_id: track.location_id ?? it.location_id,
          location_code: locationCode,
          batch_number: batch || undefined,
          ...(serialPayload?.length ? { serial_numbers: serialPayload } : {}),
        };
      });
    if (!validItems.length) {
      messageApi.error(t('app.kuaizhizao.warehouseMaterialReturn.msg.needValidReturnQty'));
      throw new Error(t('app.kuaizhizao.warehouseMaterialReturn.msg.needValidReturnQty'));
    }
    setCreateSubmitting(true);
    try {
      const { standardValues, customData } = extractMaterialReturnFormValues(values);
      const payload = {
        return_code: standardValues.return_code,
        borrow_id: selectedBorrowDetail.borrow_id,
        borrow_code: selectedBorrowDetail.borrow_code,
        warehouse_id: selectedBorrowDetail.warehouse_id,
        warehouse_name: selectedBorrowDetail.warehouse_name,
        returner_id: standardValues.returner_id != null ? Number(standardValues.returner_id) : undefined,
        returner_name: standardValues.returner_name,
        notes: standardValues.notes,
        attachments: normalizeDocumentAttachments(standardValues.attachments),
        items: validItems,
      };
      let recordId = editReturnId ?? 0;
      if (editReturnId != null) {
        await warehouseApi.materialReturn.update(String(editReturnId), payload);
        messageApi.success(t('common.saveSuccess'));
      } else {
        const created = await warehouseApi.materialReturn.create(payload, { autoConfirm: andConfirm });
        recordId = Number((created as { id?: number })?.id ?? 0);
        messageApi.success(
          andConfirm
            ? t('app.kuaizhizao.warehouseMaterialReturn.msg.createAndConfirmSuccess')
            : t('app.kuaizhizao.warehouseMaterialReturn.msg.createSuccess'),
        );
      }
      if (recordId > 0) {
        await saveMaterialReturnCustomFieldValues(recordId, customData);
      }
      resetMaterialReturnFormFieldValues();
      setCreateModalVisible(false);
      setEditReturnId(null);
      invalidateMenuBadgeCounts();
      actionRef.current?.reload();
    } catch (error: any) {
      messageApi.error(
        error.message
          || (editReturnId != null
            ? t('common.saveFailed')
            : andConfirm
              ? t('app.kuaizhizao.warehouseMaterialReturn.msg.createAndConfirmFailed')
              : t('common.createFailed')),
      );
      throw error;
    } finally {
      setCreateSubmitting(false);
    }
  };

  /** Ctrl+S / 主按钮：仅保存为待归还 */
  const handleCreateSubmit = async (values: any) => {
    await createMaterialReturn(values, false);
  };

  /** 保存并确认归还（正式入库） */
  const handleCreateAndConfirm = async () => {
    const inst = formRef.current;
    if (!inst || typeof inst.validateFields !== 'function') {
      messageApi.warning(t('components.layoutTemplates.formModal.formNotReady'));
      return;
    }
    try {
      const values = await inst.validateFields();
      await createMaterialReturn(values, true);
    } catch (error: any) {
      if (error?.errorFields) {
        const first = error.errorFields?.[0];
        const text = first?.errors?.filter(Boolean)[0];
        messageApi.error(text || t('components.layoutTemplates.formModal.checkFormHint'));
        return;
      }
      // createMaterialReturn 已提示业务错误
    }
  };

  const materialReturnStatusValueEnum = useMemo(() => buildMaterialReturnStatusValueEnum(t), [t]);

  const columns: ProColumns<MaterialReturn>[] = useMemo(
    () => alignProColumns<MaterialReturn>([
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
        valueEnum: materialReturnStatusValueEnum,
        hideInTable: true,
        search: { order: 20 } as ProColumns['search'],
      },
      {
        title: t('app.kuaizhizao.warehouseMaterialReturn.col.returnTime'),
        dataIndex: 'doc_date_range',
        valueType: 'dateRange',
        hideInTable: true,
        formItemProps: formDateRangeFormItemProps,
        search: { order: 30 } as ProColumns['search'],
      },
      {
        title: t('app.kuaizhizao.warehouseMaterialReturn.col.returnCode'),
        dataIndex: 'return_code',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        fixed: 'left',
        sorter: true,
        search: { order: 40 } as ProColumns['search'],
        render: (_, r) => (
          <Typography.Text copyable={{ text: String(r.return_code ?? '') }} ellipsis>
            {r.return_code ?? '-'}
          </Typography.Text>
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseMaterialReturn.col.borrowCode'),
        dataIndex: 'borrow_code',
        width: 160,
        minWidth: 160,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        sorter: true,
        hideInSearch: true,
        render: (_, r) =>
          r.borrow_id ? (
            <Typography.Link
              ellipsis
              onClick={() => navigate(`${ROUTES.WM_MATERIAL_BORROWS}?id=${r.borrow_id}`)}
            >
              {r.borrow_code ?? '-'}
            </Typography.Link>
          ) : (
            <Typography.Text copyable={{ text: String(r.borrow_code ?? '') }} ellipsis>
              {r.borrow_code ?? '-'}
            </Typography.Text>
          ),
      },
      {
        title: t('app.kuaizhizao.warehouseMaterialReturn.col.warehouse'),
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
        title: t('app.kuaizhizao.warehouseMaterialReturn.col.returner'),
        dataIndex: 'returner_name',
        width: 100,
        minWidth: 100,
        uniTableKeepWidth: true,
        resizable: false,
        ellipsis: true,
        sorter: true,
        hideInSearch: true,
        render: (_, r) =>
          r.returner_name != null && r.returner_name !== '' ? String(r.returner_name) : '-',
      },
      {
        title: t('app.kuaizhizao.warehouseMaterialReturn.col.returnTime'),
        dataIndex: 'return_time',
        width: 132,
        minWidth: 132,
        uniTableKeepWidth: true,
        resizable: false,
        sorter: true,
        hideInSearch: true,
        render: (_, r) => (r.return_time ? formatDateTime(r.return_time) : '-'),
      },
      ...buildDocumentAuditColumns<Record<string, unknown>>(t),
      {
        title: t('app.kuaizhizao.warehouseMaterialReturn.col.lifecycle'),
        dataIndex: 'lifecycle_stage',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) => {
          const lifecycle = getMaterialReturnLifecycle(record as Record<string, unknown>, t);
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
      ...materialReturnCustomFieldColumns,
      {
        title: t('common.actions'),
        key: 'option',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) => {
          const actions: React.ReactNode[] = [
            <Button {...rowActionKind('read')} key="detail" onClick={() => handleDetail(record)} />,
          ];
          const hubRecord: InboundHubOrder = { ...record, receipt_type: 'material_return' };
          if (canUpdateReturn && isInboundEditable(hubRecord)) {
            actions.push(
              <Button
                {...rowActionKind('update')}
                key="edit"
                onClick={(e) => {
                  e.stopPropagation();
                  void openEditReturn(record);
                }}
              />,
            );
          }
          if (record.status === '待归还') {
            actions.push(
              <ActionConfirmPopconfirm title={t('app.kuaizhizao.warehouseMaterialReturn.confirm.title')} description={t('app.kuaizhizao.warehouseMaterialReturn.confirm.content', { code: record.return_code })} onConfirm={() => executeConfirm(record)}>
              <Button
                {...rowActionKind('execute')}
                {...rowActionLabelKeep()}
                key="confirm"
                onClick={(e) => e.stopPropagation()}
              >
                {t('app.kuaizhizao.warehouseMaterialReturn.action.confirmInbound')}
              </Button>
            </ActionConfirmPopconfirm>,
            );
          }
          return actions;
        },
      },
    ], WAREHOUSE_DOC_LIST_FIELD_RANK),
    [t, materialReturnCustomFieldColumns, materialReturnStatusValueEnum, navigate, canUpdateReturn],
  );

  const detailColumns = useMemo(
    () => alignDescriptionColumns([
      { title: t('app.kuaizhizao.warehouseMaterialReturn.col.returnCode'), dataIndex: 'return_code' },
      { title: t('app.kuaizhizao.warehouseMaterialReturn.col.borrowCode'), dataIndex: 'borrow_code' },
      { title: t('app.kuaizhizao.warehouseMaterialReturn.col.warehouse'), dataIndex: 'warehouse_name' },
      { title: t('app.kuaizhizao.warehouseMaterialReturn.col.returner'), dataIndex: 'returner_name' },
      {
        title: t('common.status'),
        dataIndex: 'status',
        render: (s) => {
          const map: Record<string, { textKey: string; color: string }> = {
            待归还: { textKey: 'app.kuaizhizao.warehouseMaterialReturn.status.pending', color: 'default' },
            已归还: { textKey: 'app.kuaizhizao.warehouseMaterialReturn.status.returned', color: 'success' },
            已取消: { textKey: 'app.kuaizhizao.warehouseMaterialReturn.status.cancelled', color: 'error' },
          };
          const c = map[(s as string) || ''] || { textKey: '', color: 'default' };
          return <Tag color={c.color}>{c.textKey ? t(c.textKey) : (s as string) || '-'}</Tag>;
        },
      },
      { title: t('app.kuaizhizao.warehouseMaterialReturn.col.returnTime'), dataIndex: 'return_time', valueType: 'dateTime' },
      { title: t('common.remark'), dataIndex: 'notes', span: 3 },
    ]),
    [t],
  );

  const detailItemColumns = useMemo(
    () =>
      filterWarehouseTrackingColumns(
        [
          {
            title: t('app.kuaizhizao.warehouseMaterialReturn.col.materialCode'),
            dataIndex: 'material_code',
            width: 120,
          },
          {
            title: t('app.kuaizhizao.warehouseMaterialReturn.col.materialName'),
            dataIndex: 'material_name',
            width: 150,
          },
          { title: t('common.unit'), dataIndex: 'material_unit', width: 60 },
          {
            title: t('app.kuaizhizao.warehouseOutbound.col.location'),
            dataIndex: 'location_code',
            width: 100,
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
            title: t('app.kuaizhizao.warehouseMaterialReturn.col.returnQty'),
            dataIndex: 'return_quantity',
            width: 100,
            align: 'right' as const,
            render: formatQuantity,
          },
          buildDocumentLineAuxQuantityDetailColumn({ t, width: 120 }),
          { title: t('common.status'), dataIndex: 'status', width: 80 },
        ],
        trackingFlags,
      ),
    [t, trackingFlags],
  );

  const detailCollaboration = useMemo(() => {
    if (!returnDetail) return undefined;
    const lifecycle = getMaterialReturnLifecycle(returnDetail as unknown as Record<string, unknown>, t);
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
  }, [returnDetail, t]);

  const createFormItemColumns = useMemo(
    () =>
      filterWarehouseTrackingColumns(
        [
          {
            title: t('app.kuaizhizao.warehouseMaterialReturn.col.materialCode'),
            dataIndex: 'material_code',
            width: 120,
          },
          {
            title: t('app.kuaizhizao.warehouseMaterialReturn.col.materialName'),
            dataIndex: 'material_name',
            width: 150,
          },
          { title: t('common.unit'), dataIndex: 'material_unit', width: 60 },
          {
            title: t('app.kuaizhizao.warehouseOutbound.col.location'),
            key: 'location',
            width: 130,
            render: (_: unknown, record: BorrowItemForReturn) => (
              <Select
                size="small"
                style={{ width: '100%' }}
                showSearch
                optionFilterProp="label"
                options={locationOptions}
                value={returnLineTracking[record.id]?.location_code ?? record.location_code}
                placeholder={t('app.kuaizhizao.warehouseOutbound.field.selectLocation')}
                getPopupContainer={getPopupContainerInModal}
                onChange={(code) => {
                  setReturnLineTracking((prev) => ({
                    ...prev,
                    [record.id]: {
                      ...prev[record.id],
                      location_code: code,
                      location_id: prev[record.id]?.location_id ?? record.location_id,
                      batch_number: prev[record.id]?.batch_number ?? record.batch_number,
                      batch_managed: prev[record.id]?.batch_managed ?? record.batch_managed,
                    },
                  }));
                }}
              />
            ),
          },
          {
            title: t('app.kuaizhizao.warehouseOutbound.col.batchNo'),
            key: 'batch',
            width: 110,
            render: (_: unknown, record: BorrowItemForReturn) => {
              const batch =
                returnLineTracking[record.id]?.batch_number ?? record.batch_number ?? '';
              if (!record.batch_managed) return '—';
              return batch ? String(batch) : '—';
            },
          },
          {
            title: t('app.kuaizhizao.warehouseOutbound.col.serialNo'),
            key: 'serial_numbers',
            width: 160,
            render: (_: unknown, record: BorrowItemForReturn) => {
              if (!isMaterialSerialEntryEnabled(trackingFlags, record.serial_managed)) {
                return <span>—</span>;
              }
              const qty = Number(returnQuantities[record.id] ?? 0);
              const options = (record.available_serial_numbers ?? []).map((sn) => ({
                label: sn,
                value: sn,
              }));
              const value = returnLineSerial[record.id] ?? [];
              return (
                <OutboundSerialPickerField
                  value={value}
                  onChange={(next) =>
                    setReturnLineSerial((prev) => ({ ...prev, [record.id]: next }))
                  }
                  options={options}
                  maxCount={qty > 0 ? Math.round(qty) : undefined}
                  disabled={qty <= 0}
                  materialLabel={String(record.material_code || record.material_name || '')}
                />
              );
            },
          },
          {
            title: t('app.kuaizhizao.warehouseMaterialReturn.col.borrowQty'),
            dataIndex: 'borrow_quantity',
            width: 90,
            align: 'right' as const,
          },
          {
            title: t('app.kuaizhizao.warehouseMaterialReturn.col.returnedQty'),
            dataIndex: 'returned_quantity',
            width: 90,
            align: 'right' as const,
          },
          {
            title: t('app.kuaizhizao.warehouseMaterialReturn.col.thisReturnQty'),
            width: 120,
            render: (_: unknown, record: BorrowItemForReturn) => {
              const maxRet = Math.max(0, record.borrow_quantity - record.returned_quantity);
              return (
                <InputNumber
                  min={0}
                  max={maxRet}
                  value={returnQuantities[record.id] ?? 0}
                  onChange={(v) => {
                    const nextQty = Number(v ?? 0);
                    setReturnQuantities((prev) => ({ ...prev, [record.id]: nextQty }));
                    setReturnLineSerial((prev) => {
                      const current = prev[record.id] ?? [];
                      const max = nextQty > 0 ? Math.round(nextQty) : 0;
                      if (current.length <= max) return prev;
                      return { ...prev, [record.id]: current.slice(0, max) };
                    });
                  }}
                  style={{ width: '100%' }}
                />
              );
            },
          },
        ],
        trackingFlags,
      ),
    [locationOptions, returnLineSerial, returnLineTracking, returnQuantities, t, trackingFlags],
  );

  const timeconfigBasicItems = useDetailDrawerDescriptionItems(
    detailColumns, returnDetail,
    'material_return',
  );

  const detailSupplementary = useMemo(() => {
    if (!returnDetail) return undefined;
    if (!hasCustomFieldsDetailContent(materialReturnListCustomFields, materialReturnDetailCustomFieldValues)) {
      return undefined;
    }
    return (
      <CustomFieldsDetailSection
        customFields={materialReturnListCustomFields}
        customFieldValues={materialReturnDetailCustomFieldValues}
      />
    );
  }, [materialReturnDetailCustomFieldValues, materialReturnListCustomFields, returnDetail]);

  return (
    <>
      <ListPageTemplate>
        <UniTable
          headerTitle={t('app.kuaizhizao.warehouseMaterialReturn.title')}
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.materialReturn)}
          actionRef={actionRef}
          rowKey="id"
          columns={columns}
          columnPersistenceId="apps.kuaizhizao.pages.warehouse-management.material-returns-width-v5"
          showAdvancedSearch
          pinnedTabsField={WAREHOUSE_DOC_PINNED_STATUS_FIELD}
          skipFuzzyPinyinClientFilter
          showCreateButton
          createButtonText={createButtonLabel}
          onCreate={handleCreate}
          enableRowSelection
          onTableDataChange={(rows) => {
            const next = new Map<string, MaterialReturn>();
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
            disabled: !isMaterialReturnDeletable(record) && !isMaterialReturnPrintable(record),
          })}
          onDelete={handleBatchDelete}
          deleteConfirmTitle={(count) =>
            t('app.kuaizhizao.warehouseCommon.batchDeleteConfirm', {
              count,
              noun: t('app.kuaizhizao.warehouseMaterialReturn.title'),
            })
          }
          showExportButton
          onExport={async (type, keys, pageData) => {
            try {
              const loadAll = async () => {
                const listParams = resolveWarehouseDocListParams({}, undefined, {
                  docDateParamPrefix: 'return',
                });
                const rows = await fetchAllListItems((p) =>
                  warehouseApi.materialReturn.list({ ...listParams, ...p }),
                );
                return enrichMaterialReturnRecordsWithCustomFields(rows);
              };
              const headers = await resolveWarehouseListExportHeaders(
                type,
                keys,
                pageData as MaterialReturn[] | undefined,
                listRowsRef.current,
                loadAll,
              );
              if (headers.length === 0) {
                messageApi.warning(t('common.exportNoData'));
                return;
              }
              const enriched = await enrichStandaloneDocsWithDetail(headers, (id) =>
                warehouseApi.materialReturn.get(String(id)),
              );
              let flatRows = flattenStandaloneWarehouseDocsForExport(enriched, {
                docCodeField: 'return_code',
                docTypeLabel: t('app.kuaizhizao.warehouseInbound.receiptType.material_return'),
                partnerField: 'returner_name',
                dateFields: ['return_time'],
                operatorFields: ['returner_name'],
              });
              if (type === 'selected' && keys?.length) {
                flatRows = filterWarehouseFlatRowsByExportKeys(flatRows, keys);
              }
              await exportWarehouseDocLinesXlsx(
                flatRows,
                `material-return-lines-${todaySiteDateString()}.xlsx`,
                {
                  t,
                  sheetName: t('app.kuaizhizao.warehouseMaterialReturn.title'),
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
                docDateParamPrefix: 'return',
              });
              const response = await warehouseApi.materialReturn.list({
                skip: ((params.current || 1) - 1) * (params.pageSize || 20),
                limit: params.pageSize || 20,
                ...listParams,
              });
              const { data: raw, total } = normalizeWarehouseListResponse(response);
              const data = meta?.purpose === 'prefetch'
                ? raw
                : await enrichMaterialReturnRecordsWithCustomFields(raw);
              return { data, success: true, total };
            } catch {
              messageApi.error(t('app.kuaizhizao.warehouseMaterialReturn.msg.loadListFailed'));
              return { data: [], success: false, total: 0 };
            }
          }}
          showPrintButton
          printButtonDisabled={!canToolbarPrint}
          printButtonText={t('components.uniAction.print')}
          onPrint={() => {
            const row = selectedMaterialReturnForBatch[0];
            if (row) handlePrint(row);
          }}
        />
      </ListPageTemplate>

      <DetailDrawerTemplate
        title={`${t('app.kuaizhizao.warehouseMaterialReturn.detailTitle')}${returnDetail?.return_code ? ` - ${returnDetail.return_code}` : ''}`}
        open={detailDrawerVisible}
        loading={detailLoading}
        onClose={() => {
          setDetailDrawerVisible(false);
          setReturnDetail(null);
          resetMaterialReturnDetailFieldValues();
        }}
        size={DRAWER_CONFIG.HALF_WIDTH}
        basic={
          returnDetail ? (
            <Descriptions column={detailDrawerBasicColumn(false)} size="small" items={timeconfigBasicItems} />
          ) : undefined
        }
        collaboration={detailCollaboration}
        supplementary={detailSupplementary}
        linesTitle={t('app.kuaizhizao.warehouseMaterialReturn.field.returnDetails')}
        lines={
          returnDetail?.items && returnDetail.items.length > 0 ? (
            <>
              <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
              <Table
                className="warehouse-detail-table"
                size="small"
                rowKey="id"
                columns={detailItemColumns}
                dataSource={returnDetail.items}
                pagination={false}
              />
            </>
          ) : undefined
        }
      />

      <FormModalTemplate
        title={
          editReturnId != null
            ? t('app.kuaizhizao.warehouseMaterialReturn.editModal')
            : t('app.kuaizhizao.warehouseMaterialReturn.createModal')
        }
        open={createModalVisible}
        onClose={() => {
          setCreateModalVisible(false);
          setEditReturnId(null);
          resetMaterialReturnFormFieldValues();
        }}
        formRef={formRef}
        onFinish={handleCreateSubmit}
        loading={createSubmitting}
        submitHidden
        extraFooter={
          <Button
            loading={createSubmitting}
            onClick={() => {
              const inst = formRef.current;
              if (!inst || typeof inst.submit !== 'function') {
                messageApi.warning(t('components.layoutTemplates.formModal.formNotReady'));
                return;
              }
              inst.submit();
            }}
          >
            {t('common.save') + SUBMIT_SHORTCUT_HINT}
          </Button>
        }
        extraFooterAfter={
          editReturnId == null ? (
            <Button type="primary" loading={createSubmitting} onClick={() => void handleCreateAndConfirm()}>
              {t('app.kuaizhizao.warehouseMaterialReturn.action.saveAndConfirm')}
            </Button>
          ) : null
        }
        width={MODAL_CONFIG.LARGE_WIDTH}
        grid={false}
      >
        <Row gutter={16}>
          <Col span={12}>
            <CodeField
              pageCode="kuaizhizao-warehouse-material-return"
              name="return_code"
              label={t('app.kuaizhizao.warehouseMaterialReturn.field.returnCode')}
              autoGenerateOnCreate={editReturnId == null}
              showGenerateButton={false}
              context={{}}
            />
          </Col>
          <Col span={12}>
            <ProFormItem
              name="borrow_id"
              label={t('app.kuaizhizao.warehouseMaterialReturn.field.borrow')}
              rules={[{ required: true, message: t('app.kuaizhizao.warehouseMaterialReturn.field.selectBorrowRequired') }]}
            >
              <UniDropdown
                placeholder={t('app.kuaizhizao.warehouseMaterialReturn.field.selectBorrowPlaceholder')}
                showSearch
                allowClear
                disabled={editReturnId != null}
                loading={borrowLoading}
                style={{ width: '100%' }}
                options={borrowList.map((b: any) => ({
                  value: b.id,
                  label: `${b.borrow_code ?? b.borrowCode ?? ''} - ${b.warehouse_name ?? b.warehouseName ?? ''}`.trim() || String(b.id),
                }))}
                onChange={(v) => onBorrowSelect(v as number)}
              />
            </ProFormItem>
          </Col>
        </Row>
        {selectedBorrowDetail && (
          <>
            <div className="uni-table-detail" style={{ width: '100%' }}>
              <UniTableDetailHeader title={t('app.kuaizhizao.warehouseMaterialReturn.field.returnDetails')} />
              <div style={{ width: '100%', minWidth: 0, boxSizing: 'border-box' }}>
                <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
                <Table
                  className="warehouse-detail-table"
                  size="small"
                  rowKey="id"
                  pagination={false}
                  columns={createFormItemColumns}
                  dataSource={selectedBorrowDetail.items}
                />
              </div>
            </div>
          </>
        )}
        <Form.Item name="returner_id" hidden />
        <Row gutter={16}>
          <Col span={12}>
            <UniUserSelect
              name="returner_uuid"
              label={t('app.kuaizhizao.warehouseMaterialReturn.field.returner')}
              placeholder={t('app.kuaizhizao.warehouseMaterialReturn.field.selectReturner')}
              onChange={(_value: any, user: any) => {
                const picked = Array.isArray(user) ? user[0] : user;
                formRef.current?.setFieldsValue({
                  returner_id: picked?.id,
                  returner_name: picked?.full_name || picked?.username || undefined,
                });
              }}
            />
            <Form.Item name="returner_name" hidden />
          </Col>
          <Col span={12} />
        </Row>
        <CustomFieldsFormSection
          customFields={materialReturnFormCustomFields}
          customFieldValues={materialReturnFormCustomFieldValues}
          gridColumns={2}
        />
        <DocumentAttachmentsField category="material_return_attachments" />
        <ProFormTextArea
          name="notes"
          label={t('common.remark')}
          placeholder={t('app.kuaizhizao.warehouseMaterialReturn.field.optional')}
          fieldProps={{ rows: 2 }}
        />
      </FormModalTemplate>
      {PrintModal}
    </>
  );
};

export default MaterialReturnsPage;
