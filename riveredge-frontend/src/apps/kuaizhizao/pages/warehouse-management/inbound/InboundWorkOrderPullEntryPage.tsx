/**
 * 从生产工单取单开入库单 — 独立 Tab 页（成品/半成品）
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Typography,
} from 'antd';
import { ArrowLeftOutlined, ThunderboltOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import {
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageLayout,
  PAGE_SPACING,
  WAREHOUSE_DETAIL_TABLE_STYLES,
} from '../../../../../components/layout-templates';
import { UniTableDetailHeader } from '../../../../../components/uni-table-detail/UniTableDetail';
import { warehouseApi as masterWarehouseApi } from '../../../../master-data/services/warehouse';
import { workOrderApi } from '../../../services/production';
import { warehouseApi } from '../../../services/warehouse-execution';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { setCustomPageTitle, removeCustomPageTitle } from '../../../../../utils/customPageTitle';
import { formatDateBySiteSetting } from '../../../../../utils/format';
import { translateWorkOrderLifecycleStatus } from '../../../utils/workOrderLifecycle';
import {
  InboundEntryReceiverField,
  InboundEntryRemarksSection,
  ReadOnlyFormValue,
  mapWarehouseSelectOptions,
  useInboundReceiverSelect,
} from './inboundEntryShared';
import {
  PurchaseInboundLineLocationCell,
} from './PurchaseInboundLineWhCells';
import { lineLocationSelectionRequired } from '../../../../../components/uni-wh-dropdown';
import { inboundReceiptTypeLabel } from './inboundHubTypes';
import { INBOUND_LIST_PATH, inboundWorkOrderEntryPath } from './inboundPaths';
import type { InboundReceiptType } from './inboundHubTypes';
import { navigateLeavingPullEntry, pullEntryTabKey } from '../shared/pullEntryCloseTab';
import { draftOptionalNumber, usePullEntryFormDraft } from '../shared/pullEntryFormDraft';
import { resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import {
  MaterialUnitSelect,
  fetchMaterialForUnitSelectCache,
} from '../../../../../components/material-unit-select';
import { recalculateQuantityOnUnitChange } from '../../../../../components/quantity-with-unit/formHelpers';
import { formatQuantityWithUnit } from '../../../../../utils/materialUnitDisplay';
import { coerceFormDate, toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';

const MIN_INBOUND_RECEIPT_YEAR = 2000;

/** 入库日期默认今天；草稿合法日期可覆盖（对齐采购取单录入）。 */
function resolveInboundReceiptDate(draftValue: unknown): Dayjs {
  if (draftValue != null && draftValue !== '') {
    const parsed = coerceFormDate(draftValue);
    if (parsed?.isValid() && parsed.year() >= MIN_INBOUND_RECEIPT_YEAR) {
      return parsed.startOf('day');
    }
  }
  return dayjs().startOf('day');
}
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import {
  loadConfirmPreviewMaterialMeta,
  type ConfirmPreviewMaterialMeta,
} from './inboundItemTracking';
import {
  materialBatchApi,
  materialSerialApi,
  MATERIAL_SERIAL_GENERATE_MAX_COUNT,
} from '../../../../master-data/services/material';
import { SerialNumbersImportTrigger } from '../../../../../components/serial-numbers-import';

type PreviewLine = {
  material_id: number;
  material_code: string;
  material_name: string;
  material_spec?: string;
  material_unit: string;
  source_doc_quantity?: number;
  source_received_quantity?: number;
  source_pending_quantity?: number;
  receipt_quantity?: number;
};

type WorkOrderPreview = {
  work_order_id: number;
  work_order_code: string;
  inbound_doc_kind: 'finished_goods' | 'semi_finished_goods';
  lines: PreviewLine[];
  message?: string;
};

const InboundWorkOrderPullEntryPage: React.FC = () => {
  const { woId: woIdParam } = useParams<{ woId: string }>();
  const woId = Number(woIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const { message: messageApi } = App.useApp();
  const { t } = useTranslation();
  const pullFromWorkOrderAction = resolveKuaizhizaoDocumentAction(t, 'inbound.pull_from_work_order');
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const receiverHook = useInboundReceiverSelect();
  const trackingFlags = useWarehouseTrackingFlags();
  const initRef = useRef(false);
  const [lineMaterialMeta, setLineMaterialMeta] = useState<ConfirmPreviewMaterialMeta | null>(null);
  const [batchNumber, setBatchNumber] = useState('');
  const [serialNumbers, setSerialNumbers] = useState<string[]>([]);
  const [generatingBatch, setGeneratingBatch] = useState(false);
  const [generatingSerial, setGeneratingSerial] = useState(false);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [preview, setPreview] = useState<WorkOrderPreview | null>(null);
  const [workOrder, setWorkOrder] = useState<Record<string, unknown> | null>(null);
  const [warehouseOptions, setWarehouseOptions] = useState<{ label: string; value: number; name: string }[]>([]);
  const [receiptQty, setReceiptQty] = useState(0);
  const [receiptUnit, setReceiptUnit] = useState('');
  const [displayPendingQty, setDisplayPendingQty] = useState(0);
  const [displayDocQty, setDisplayDocQty] = useState(0);
  const [displayReceivedQty, setDisplayReceivedQty] = useState(0);
  const [warehouseId, setWarehouseId] = useState<number | undefined>();
  const [locationId, setLocationId] = useState<number | undefined>();
  const [locationCode, setLocationCode] = useState('');
  const [receiptTime, setReceiptTime] = useState<Dayjs | null>(null);
  const [receiptNotes, setReceiptNotes] = useState('');
  const { bindSnapshot, persistNow, clearDraft, applyDraftOnce } = usePullEntryFormDraft(
    'kuaizhizao:inbound-work-order-pull',
  );

  const line = preview?.lines?.[0];
  const receiptType: InboundReceiptType = preview?.inbound_doc_kind ?? 'finished_goods';
  const inboundTypeLabel = inboundReceiptTypeLabel(t, receiptType);
  const pagePath = Number.isFinite(woId) && woId > 0 ? inboundWorkOrderEntryPath(woId) : INBOUND_LIST_PATH;
  const maxQty = displayPendingQty > 0 ? displayPendingQty : Number(line?.source_pending_quantity ?? 0);
  const pageTitle = preview?.work_order_code
    ? `${pullFromWorkOrderAction.label} — ${preview.work_order_code}`
    : pullFromWorkOrderAction.label;

  const leavePage = useCallback(() => {
    clearDraft();
    navigateLeavingPullEntry(
      navigate,
      INBOUND_LIST_PATH,
      pullEntryTabKey(location.pathname, location.search),
    );
  }, [clearDraft, navigate, location.pathname, location.search]);

  useEffect(() => {
    bindSnapshot(() => ({
      receiptQty,
      warehouseId,
      locationId,
      locationCode,
      batchNumber,
      serialNumbers,
      receiptTime,
      receiptNotes,
      receiverUuid: receiverHook.receiverUuid,
      receiverName: receiverHook.receiverName,
    }));
    persistNow();
  }, [
    receiptQty,
    warehouseId,
    locationId,
    locationCode,
    batchNumber,
    serialNumbers,
    receiptTime,
    receiptNotes,
    receiverHook.receiverUuid,
    receiverHook.receiverName,
    bindSnapshot,
    persistNow,
  ]);

  useEffect(() => {
    if (!(Number.isFinite(woId) && woId > 0)) {
      messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.workOrder.invalid'));
      leavePage();
    }
  }, [woId, leavePage, messageApi, t]);

  useEffect(() => {
    setCustomPageTitle(pagePath, pageTitle);
    window.dispatchEvent(
      new CustomEvent('riveredge:update-tab-title', {
        detail: { key: pagePath, path: pagePath, title: pageTitle },
      }),
    );
    return () => {
      removeCustomPageTitle(pagePath);
    };
  }, [pagePath, pageTitle]);

  useEffect(() => {
    if (!Number.isFinite(woId) || woId <= 0 || initRef.current) return;
    initRef.current = true;
    void (async () => {
      setLoading(true);
      try {
        const [previewRaw, woRaw, whRes] = await Promise.all([
          warehouseApi.finishedGoodsReceipt.previewFromWorkOrder(woId) as Promise<WorkOrderPreview>,
          workOrderApi.get(String(woId)),
          masterWarehouseApi.list({ is_active: true, limit: 500 }),
        ]);
        if (!previewRaw?.lines?.length) {
          messageApi.warning(previewRaw?.message || t('app.kuaizhizao.warehouseInbound.entry.workOrder.noLines'));
          leavePage();
          return;
        }
        setWarehouseOptions(mapWarehouseSelectOptions(whRes));
        setPreview(previewRaw);
        setWorkOrder(woRaw as Record<string, unknown>);
        const firstLine = previewRaw.lines[0];
        if (firstLine?.material_id) {
          const metaMap = await loadConfirmPreviewMaterialMeta([
            { ...firstLine, id: firstLine.material_id },
          ]);
          setLineMaterialMeta(metaMap[firstLine.material_id] ?? null);
        }
        const ln = previewRaw.lines[0];
        const unit = ln.material_unit || '个';
        setReceiptUnit(unit);
        const pendingQty = Number(ln.source_pending_quantity ?? 0);
        setDisplayPendingQty(pendingQty);
        setDisplayDocQty(Number(ln.source_doc_quantity ?? 0));
        setDisplayReceivedQty(Number(ln.source_received_quantity ?? 0));
        // 本次入库默认 = 待入库数量（预览 receipt_quantity 仅作兜底）
        const suggestedQty = Number(ln.receipt_quantity ?? 0);
        setReceiptQty(pendingQty > 0 ? pendingQty : suggestedQty > 0 ? suggestedQty : 0);

        let receiptFromDraft: Dayjs | null = null;
        let restoredReceiverFromDraft = false;
        applyDraftOnce((draft) => {
          const qty = draftOptionalNumber(draft.receiptQty);
          // 仅正数草稿覆盖，避免下推写入 0 冲掉待入库默认
          if (qty != null && qty > 0) setReceiptQty(qty);
          const whId = draftOptionalNumber(draft.warehouseId);
          if (whId != null) setWarehouseId(whId);
          const locId = draftOptionalNumber(draft.locationId);
          if (locId != null) setLocationId(locId);
          if (typeof draft.locationCode === 'string') setLocationCode(draft.locationCode);
          if (typeof draft.batchNumber === 'string') setBatchNumber(draft.batchNumber);
          if (Array.isArray(draft.serialNumbers)) {
            setSerialNumbers(draft.serialNumbers.map((s) => String(s).trim()).filter(Boolean));
          }
          if (draft.receiptTime != null && draft.receiptTime !== '') {
            receiptFromDraft = resolveInboundReceiptDate(draft.receiptTime);
          }
          if (typeof draft.receiptNotes === 'string') setReceiptNotes(draft.receiptNotes);
          const hasReceiverDraft =
            (typeof draft.receiverUuid === 'string' && draft.receiverUuid.trim() !== '') ||
            (typeof draft.receiverName === 'string' && draft.receiverName.trim() !== '');
          if (hasReceiverDraft) {
            restoredReceiverFromDraft = true;
            receiverHook.restoreReceiver({
              uuid: typeof draft.receiverUuid === 'string' ? draft.receiverUuid : undefined,
              name: typeof draft.receiverName === 'string' ? draft.receiverName : undefined,
            });
          }
        });
        setReceiptTime(receiptFromDraft ?? resolveInboundReceiptDate(undefined));
        if (!restoredReceiverFromDraft) {
          receiverHook.restoreReceiver();
        }
      } catch (e: unknown) {
        messageApi.error((e as Error)?.message || t('app.kuaizhizao.warehouseInbound.entry.workOrder.loadFailed'));
        leavePage();
      } finally {
        setLoading(false);
      }
    })();
  }, [woId, leavePage, messageApi, t, applyDraftOnce, receiverHook.restoreReceiver]);

  const submit = async (mode: 'draft' | 'confirm') => {
    if (!preview || !line) return;
    const qty = Number(receiptQty);
    if (!(qty > 0)) {
      messageApi.warning(t('app.kuaizhizao.warehouseInbound.entry.workOrder.fillReceiptQty'));
      return;
    }
    if (maxQty <= 0) {
      messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.workOrder.noPendingQty'));
      return;
    }
    if (qty > maxQty) {
      messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.workOrder.qtyExceedsPending', { max: maxQty }));
      return;
    }
    if (!warehouseId || !(warehouseId > 0)) {
      messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.workOrder.selectWarehouse'));
      return;
    }
    const whOpt = warehouseOptions.find((o) => o.value === warehouseId);
    if (!whOpt) return;

    const materialLabel = line.material_code || line.material_name || '-';
    const needLoc = await lineLocationSelectionRequired(warehouseId, locationId, locationCode);
    if (needLoc) {
      messageApi.error(
        t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', { material: materialLabel }),
      );
      return;
    }
    const lineLocationPayload = {
      location_id: locationId != null && locationId > 0 ? locationId : undefined,
      location_code: locationCode.trim() || undefined,
    };
    const batchTrim = batchNumber.trim();
    if (isMaterialBatchEntryEnabled(trackingFlags, lineMaterialMeta?.batchManaged) && !batchTrim) {
      messageApi.error(
        t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
          material: materialLabel,
          batches: '—',
        }),
      );
      return;
    }
    if (isMaterialSerialEntryEnabled(trackingFlags, lineMaterialMeta?.serialManaged)) {
      const expected = Math.floor(qty);
      const serials = serialNumbers.map((s) => String(s).trim()).filter(Boolean);
      if (serials.length !== expected) {
        messageApi.error(
          t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
            material: materialLabel,
            required: expected,
            actual: serials.length,
          }),
        );
        return;
      }
    }
    const trackingPayload = {
      batch_number: batchTrim || undefined,
      serial_numbers: serialNumbers.length
        ? serialNumbers.map((s) => String(s).trim()).filter(Boolean)
        : undefined,
    };

    setSubmitting(true);
    try {
      let createdId: number | undefined;
      const headerPatch = {
        ...(receiptTime?.isValid()
          ? { receipt_time: toApiBusinessDocumentDateTime(receiptTime) }
          : {}),
        receiver_id: receiverHook.receiverId,
        receiver_name: receiverHook.receiverName.trim() || undefined,
        notes: receiptNotes.trim() || undefined,
      };

      if (receiptType === 'semi_finished_goods') {
        const created = (await warehouseApi.semiFinishedGoodsReceipt.create({
          work_order_id: woId,
          work_order_code: preview.work_order_code,
          sales_order_id: workOrder?.sales_order_id != null ? Number(workOrder.sales_order_id) : undefined,
          sales_order_code: workOrder?.sales_order_code ? String(workOrder.sales_order_code) : undefined,
          warehouse_id: warehouseId,
          warehouse_name: whOpt.name,
          status: '待入库',
          total_quantity: qty,
          ...headerPatch,
          items: [
            {
              material_id: line.material_id,
              material_code: line.material_code,
              material_name: line.material_name,
              material_spec: line.material_spec,
              material_unit: receiptUnit || line.material_unit,
              receipt_quantity: qty,
              qualified_quantity: qty,
              unqualified_quantity: 0,
              quality_status: '合格',
              status: '待入库',
              ...lineLocationPayload,
              ...trackingPayload,
            },
          ],
        })) as { id?: number; receipt_code?: string };
        createdId = created?.id;
        if (mode === 'draft') {
          messageApi.success(
            t('app.kuaizhizao.warehouseInbound.entry.workOrder.semiDraftCreated', {
              code: created.receipt_code
                ? t('app.kuaizhizao.warehouseInbound.entry.purchase.draftCreatedSuffix', { code: created.receipt_code })
                : '',
            }),
          );
        }
      } else {
        const created = (await warehouseApi.finishedGoodsReceipt.create({
          work_order_id: woId,
          work_order_code: preview.work_order_code,
          sales_order_id: workOrder?.sales_order_id != null ? Number(workOrder.sales_order_id) : undefined,
          sales_order_code: workOrder?.sales_order_code ? String(workOrder.sales_order_code) : undefined,
          warehouse_id: warehouseId,
          warehouse_name: whOpt.name,
          status: '待入库',
          total_quantity: qty,
          ...headerPatch,
          items: [
            {
              material_id: line.material_id,
              material_code: line.material_code,
              material_name: line.material_name,
              material_spec: line.material_spec,
              material_unit: receiptUnit || line.material_unit,
              receipt_quantity: qty,
              qualified_quantity: qty,
              unqualified_quantity: 0,
              quality_status: '合格',
              status: '待入库',
              ...lineLocationPayload,
              ...trackingPayload,
            },
          ],
        })) as { id?: number; receipt_code?: string };
        createdId = created?.id;
        if (mode === 'draft') {
          messageApi.success(
            t('app.kuaizhizao.warehouseInbound.entry.workOrder.finishedDraftCreated', {
              code: created.receipt_code
                ? t('app.kuaizhizao.warehouseInbound.entry.purchase.draftCreatedSuffix', { code: created.receipt_code })
                : '',
            }),
          );
        }
      }

      if (createdId == null) {
        messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.purchase.noReceiptId'));
        return;
      }
      invalidateMenuBadgeCounts();
      clearDraft();
      if (mode === 'confirm') {
        navigateLeavingPullEntry(
          navigate,
          INBOUND_LIST_PATH,
          pullEntryTabKey(location.pathname, location.search),
          {
            inboundOpenDetail: {
              id: Number(createdId),
              receipt_type: receiptType,
            },
            inboundHubEntry: {
              receiptTypeFilter: receiptType,
            },
          },
        );
      } else {
        leavePage();
      }
    } catch (e: unknown) {
      const err = e as { message?: string; response?: { data?: { detail?: string } } };
      messageApi.error(err?.message || err?.response?.data?.detail || t('common.saveFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const entryColumns = useMemo(
    () =>
      filterWarehouseTrackingColumns(
        [
      { title: t('app.kuaizhizao.warehouseInbound.col.materialCode'), dataIndex: 'material_code', width: 120, ellipsis: true },
      { title: t('app.kuaizhizao.warehouseInbound.col.materialName'), dataIndex: 'material_name', width: 150, ellipsis: true },
      { title: t('app.kuaizhizao.warehouseInbound.col.spec'), dataIndex: 'material_spec', width: 120, ellipsis: true, render: (v: unknown) => v || '—' },
      {
        title: t('common.unit'),
        width: 88,
        align: 'center' as const,
        render: () =>
          line?.material_id ? (
            <MaterialUnitSelect
              materialId={line.material_id}
              value={receiptUnit || line.material_unit}
              size="small"
              noStyle
              onChange={(newUnit) => {
                void (async () => {
                  const material = await fetchMaterialForUnitSelectCache(line.material_id);
                  const convert = (qty: number) =>
                    recalculateQuantityOnUnitChange({
                      material,
                      currentQuantity: qty,
                      oldUnit: receiptUnit || line.material_unit,
                      newUnit,
                    });
                  setReceiptUnit(newUnit);
                  setDisplayPendingQty(convert(displayPendingQty));
                  setDisplayDocQty(convert(displayDocQty));
                  setDisplayReceivedQty(convert(displayReceivedQty));
                  setReceiptQty((prev) => convert(prev));
                })();
              }}
            />
          ) : (
            receiptUnit || line?.material_unit || '—'
          ),
      },
      { title: t('app.kuaizhizao.warehouseInbound.col.plannedQty'), width: 100, align: 'right' as const, render: () => formatQuantityWithUnit(displayDocQty, receiptUnit || line?.material_unit) },
      { title: t('app.kuaizhizao.warehouseInbound.col.receivedQty'), width: 90, align: 'right' as const, render: () => formatQuantityWithUnit(displayReceivedQty, receiptUnit || line?.material_unit) },
      { title: t('app.kuaizhizao.warehouseInbound.col.pendingQty'), width: 90, align: 'right' as const, render: () => formatQuantityWithUnit(displayPendingQty, receiptUnit || line?.material_unit) },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.warehouse'),
        width: 150,
        render: () => (
          <Select
            style={{ width: '100%', minWidth: 118 }}
            placeholder={t('app.kuaizhizao.warehouseInbound.field.select')}
            showSearch
            optionFilterProp="label"
            value={warehouseId}
            options={warehouseOptions}
            onChange={(v) => {
              setWarehouseId(v ?? undefined);
              setLocationId(undefined);
              setLocationCode('');
              setBatchNumber('');
              setSerialNumbers([]);
            }}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.location'),
        width: 150,
        render: () => (
          <PurchaseInboundLineLocationCell
            materialId={line?.material_id}
            warehouseId={warehouseId}
            locationId={locationId}
            selectWarehouseFirstPlaceholder={t('app.kuaizhizao.warehouseInbound.field.selectWarehouseFirst')}
            selectLocationPlaceholder={t('app.kuaizhizao.warehouseInbound.field.selectLocation')}
            onChange={(v, loc) => {
              setLocationId(v ?? undefined);
              setLocationCode(loc?.code ?? '');
            }}
          />
        ),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.batchNo'),
        width: 130,
        render: () => {
          if (!isMaterialBatchEntryEnabled(trackingFlags, lineMaterialMeta?.batchManaged)) return '—';
          return (
            <Space size={2}>
              <Input
                size="small"
                style={{ width: 96 }}
                value={batchNumber}
                onChange={(e) => setBatchNumber(e.target.value)}
              />
              <Button
                type="link"
                size="small"
                icon={<ThunderboltOutlined />}
                loading={generatingBatch}
                style={{ padding: 0 }}
                onClick={() => {
                  const uuid = lineMaterialMeta?.materialUuid;
                  if (!uuid) return;
                  setGeneratingBatch(true);
                  void materialBatchApi
                    .generate(uuid, {})
                    .then((res) => {
                      setBatchNumber(res.batch_no);
                      messageApi.success(t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerated'));
                    })
                    .catch((e: Error) => {
                      messageApi.error(
                        e?.message || t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerateFailed'),
                      );
                    })
                    .finally(() => setGeneratingBatch(false));
                }}
              />
            </Space>
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.serialNo'),
        width: 160,
        render: () => {
          if (!isMaterialSerialEntryEnabled(trackingFlags, lineMaterialMeta?.serialManaged)) return '—';
          const qty = Math.floor(Number(receiptQty));
          return (
            <SerialNumbersImportTrigger
              serials={serialNumbers}
              expectedCount={qty > 0 ? qty : undefined}
              materialLabel={line?.material_code || line?.material_name}
              generateLoading={generatingSerial}
              onSerialsChange={setSerialNumbers}
              onGenerate={async () => {
                const uuid = lineMaterialMeta?.materialUuid;
                if (!uuid || !(qty > 0)) return [];
                const count = Math.min(qty, MATERIAL_SERIAL_GENERATE_MAX_COUNT);
                setGeneratingSerial(true);
                try {
                  const res = await materialSerialApi.generate(String(uuid), count, {});
                  setSerialNumbers(res.serial_nos);
                  messageApi.success(
                    t('app.kuaizhizao.warehouseInbound.msg.serialGenerated', { count: res.count }),
                  );
                  return res.serial_nos;
                } catch (e: unknown) {
                  messageApi.error(
                    (e as Error)?.message || t('app.kuaizhizao.warehouseInbound.msg.serialGenerateFailed'),
                  );
                  return [];
                } finally {
                  setGeneratingSerial(false);
                }
              }}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.thisReceipt'),
        width: 130,
        align: 'right' as const,
        render: () => (
          <InputNumber
            min={0}
            max={maxQty > 0 ? maxQty : undefined}
            precision={4}
            value={receiptQty}
            onChange={(v) => setReceiptQty(Number(v) || 0)}
            style={{ width: 110 }}
          />
        ),
      },
    ],
        trackingFlags,
      ),
    [
      t,
      warehouseId,
      warehouseOptions,
      locationId,
      locationCode,
      receiptQty,
      maxQty,
      line,
      receiptUnit,
      displayDocQty,
      displayReceivedQty,
      displayPendingQty,
      trackingFlags,
      lineMaterialMeta,
      batchNumber,
      serialNumbers,
      generatingBatch,
      generatingSerial,
      messageApi,
    ],
  );

  const applyDefaultWarehouse = useCallback((v: number | undefined) => {
    setWarehouseId(v);
    setLocationId(undefined);
    setLocationCode('');
    setBatchNumber('');
    setSerialNumbers([]);
  }, []);

  return (
    <DocumentFormPageLayout
      header={
        <>
          <Space align="center" size={8}>
            <Button type="text" icon={<ArrowLeftOutlined />} aria-label={t('common.back')} onClick={leavePage} />
            <Typography.Title level={4} style={DOCUMENT_DETAIL_PAGE_TITLE_STYLE}>
              {pageTitle}
            </Typography.Title>
          </Space>
          <Space wrap>
            <Button disabled={submitting || loading} onClick={leavePage}>
              {t('common.cancel')}
            </Button>
            <Button loading={submitting} disabled={loading || maxQty <= 0} onClick={() => void submit('draft')}>
              {t('app.kuaizhizao.warehouseInbound.action.generateDraft')}
            </Button>
            <Button type="primary" loading={submitting} disabled={loading || maxQty <= 0} onClick={() => void submit('confirm')}>
              {t('app.kuaizhizao.warehouseInbound.action.confirmInbound')}
            </Button>
          </Space>
        </>
      }
    >
      <Spin spinning={loading}>
        <Card styles={{ body: { padding: PAGE_SPACING.PADDING } }}>
          <div className="form-modal-content-inner">
            {preview && line && (
              <Form layout="vertical" requiredMark={false}>
                <Row gutter={16}>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.inboundType')}>
                      <ReadOnlyFormValue value={inboundTypeLabel} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.workOrderCode')}>
                      <ReadOnlyFormValue value={preview.work_order_code} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.product')}>
                      <ReadOnlyFormValue value={line.material_name} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.productCode')}>
                      <ReadOnlyFormValue value={line.material_code} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.plannedQty')}>
                      <ReadOnlyFormValue value={line.source_doc_quantity} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.receivedQty')}>
                      <ReadOnlyFormValue value={line.source_received_quantity} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.pendingQty')}>
                      <ReadOnlyFormValue value={line.source_pending_quantity} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.sourceSalesOrder')}>
                      <ReadOnlyFormValue value={workOrder?.sales_order_code ? String(workOrder.sales_order_code) : undefined} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.workOrderStatus')}>
                      <ReadOnlyFormValue value={translateWorkOrderLifecycleStatus(t, workOrder?.status)} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.receiptDate')}>
                      <DatePicker
                        style={{ width: '100%' }}
                        value={receiptTime}
                        onChange={(v) => setReceiptTime(v ? v.startOf('day') : null)}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <InboundEntryReceiverField hook={receiverHook} />
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.defaultWarehouse')} required>
                      <Select
                        style={{ width: '100%' }}
                        placeholder={t('app.kuaizhizao.warehouseInbound.field.selectInboundWarehouse')}
                        showSearch
                        optionFilterProp="label"
                        value={warehouseId}
                        options={warehouseOptions}
                        onChange={(v) => applyDefaultWarehouse(v ?? undefined)}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.workOrderDeliveryDate')}>
                      <ReadOnlyFormValue
                        value={
                          workOrder?.delivery_date
                            ? formatDateBySiteSetting(String(workOrder.delivery_date))
                            : undefined
                        }
                      />
                    </Form.Item>
                  </Col>
                </Row>
              </Form>
            )}

            {line && (
              <div className="uni-table-detail" style={{ marginTop: PAGE_SPACING.BLOCK_GAP }}>
                <UniTableDetailHeader title={t('app.kuaizhizao.warehouseInbound.section.inboundDetails')} required />
                <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
                <div className="uni-table-detail-body">
                  <div className="uni-table-detail-scroll">
                    <Table
                      className="uni-detail-table warehouse-detail-table"
                      size="small"
                      rowKey="material_id"
                      pagination={false}
                      scroll={{ x: 1050 }}
                      dataSource={[line]}
                      columns={entryColumns}
                    />
                  </div>
                </div>
              </div>
            )}

            {preview && (
              <Form layout="vertical" requiredMark={false} style={{ marginTop: PAGE_SPACING.BLOCK_GAP }}>
                <InboundEntryRemarksSection value={receiptNotes} onChange={setReceiptNotes} />
              </Form>
            )}
          </div>
        </Card>
      </Spin>
    </DocumentFormPageLayout>
  );
};

export default InboundWorkOrderPullEntryPage;
