/**
 * 从销售订单取单开销售出库 — 独立 Tab 页
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
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Typography,
} from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import type { UploadFile } from 'antd/es/upload/interface';
import {
  draftDayjs,
  draftOptionalNumber,
  mergeRecordMaps,
  usePullEntryFormDraft,
} from '../shared/pullEntryFormDraft';
import { navigateLeavingPullEntry, pullEntryTabKey } from '../shared/pullEntryCloseTab';
import {
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageLayout,
  PAGE_SPACING,
  WAREHOUSE_DETAIL_TABLE_STYLES,
} from '../../../../../components/layout-templates';
import { warehouseApi as masterWarehouseApi } from '../../../../master-data/services/warehouse';
import { getSalesOrder, previewPushSalesOrderToDelivery, pushSalesOrderToDelivery, type SalesOrderItem } from '../../../services/sales-order';
import { warehouseApi } from '../../../services/warehouse-execution';
import { normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { setCustomPageTitle, removeCustomPageTitle } from '../../../../../utils/customPageTitle';
import {
  OutboundEntryAttachmentsSection,
  OutboundEntryOperatorField,
  OutboundEntryRemarksSection,
  ReadOnlyFormValue,
  mapWarehouseSelectOptions,
  useOutboundOperatorSelect,
} from './outboundEntryShared';
import { getOutboundIssueTypeLabel } from './outboundHubTypes';
import { OUTBOUND_LIST_PATH, outboundSalesOrderEntryPath } from './outboundPaths';
import { resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import { toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';
import { useQuery } from '@tanstack/react-query';
import { getBusinessConfig } from '../../../../../services/businessConfig';
import { TOOLBAR_SYNC_PUSH_FLAGS_QUERY_KEY } from '../../../../../hooks/useToolbarSyncPushFlags';
import { reportDocumentStatusText } from '../../../utils/reportPresentation';
import { PurchaseInboundLineLocationCell } from '../inbound/PurchaseInboundLineWhCells';
import { lineLocationSelectionRequired } from '../../../../../components/uni-wh-dropdown';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import {
  loadConfirmPreviewMaterialMeta,
  type ConfirmPreviewMaterialMeta,
} from '../inbound/inboundItemTracking';
import {
  loadBatchOptionsByMaterialId,
  type InventoryPickOption,
} from './outboundConfirmInventoryOptions';
import OutboundBatchAllocationField from './OutboundBatchAllocationField';
import {
  allocateBatchQuantitiesFifo,
  isValidOutboundBatchAllocations,
  lineBatchAllocationsFromRow,
  type OutboundBatchAllocation,
} from './outboundBatchAllocation';
import { SerialNumbersImportTrigger } from '../../../../../components/serial-numbers-import';
import {
  materialSerialApi,
  MATERIAL_SERIAL_GENERATE_MAX_COUNT,
} from '../../../../master-data/services/material';

type SoLineTracking = {
  location_id?: number;
  location_code?: string;
  batch_number?: string;
  batch_allocations?: OutboundBatchAllocation[];
  serial_numbers?: string[];
};

const OutboundSalesOrderPullEntryPage: React.FC = () => {
  const { t } = useTranslation();
  const pullFromSalesOrderAction = resolveKuaizhizaoDocumentAction(t, 'sales_delivery.pull_from_sales_order');
  const { soId: soIdParam } = useParams<{ soId: string }>();
  const salesOrderId = Number(soIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const { message: messageApi } = App.useApp();
  const { data: businessConfig } = useQuery({
    queryKey: TOOLBAR_SYNC_PUSH_FLAGS_QUERY_KEY,
    queryFn: getBusinessConfig,
    staleTime: 60_000,
  });
  const requireShipmentNoticeBeforeDelivery = Boolean(
    businessConfig?.parameters?.sales?.require_shipment_notice_before_delivery,
  );
  const allowNegativeInventory = Boolean(
    businessConfig?.parameters?.warehouse?.allow_negative_inventory,
  );
  const operatorHook = useOutboundOperatorSelect();
  const trackingFlags = useWarehouseTrackingFlags();
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const initRef = useRef(false);
  const [lineMaterialMeta, setLineMaterialMeta] = useState<Record<number, ConfirmPreviewMaterialMeta>>({});
  const [lineTracking, setLineTracking] = useState<Record<number, SoLineTracking>>({});
  const [batchOptionsBySoItemId, setBatchOptionsBySoItemId] = useState<
    Record<number, InventoryPickOption[]>
  >({});
  const [batchLoadingSoItemId, setBatchLoadingSoItemId] = useState<number | null>(null);
  const [generatingSerialSoItemId, setGeneratingSerialSoItemId] = useState<number | null>(null);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [order, setOrder] = useState<Record<string, unknown> | null>(null);
  const [items, setItems] = useState<SalesOrderItem[]>([]);
  const [warehouseOptions, setWarehouseOptions] = useState<{ label: string; value: number; name: string }[]>([]);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [maxQuantities, setMaxQuantities] = useState<Record<number, number>>({});
  const [lineWh, setLineWh] = useState<Record<number, number>>({});
  const [deliveryTime, setDeliveryTime] = useState<Dayjs | null>(null);
  const [notes, setNotes] = useState('');
  const [attachments, setAttachments] = useState<UploadFile[]>([]);
  const { bindSnapshot, persistNow, clearDraft, applyDraftOnce } = usePullEntryFormDraft(
    'kuaizhizao:outbound-sales-order-pull',
  );

  const pagePath =
    Number.isFinite(salesOrderId) && salesOrderId > 0 ? outboundSalesOrderEntryPath(salesOrderId) : OUTBOUND_LIST_PATH;
  const orderCode = String(order?.order_code ?? order?.code ?? '');
  const pageTitle = orderCode
    ? `${pullFromSalesOrderAction.label} — ${orderCode}`
    : pullFromSalesOrderAction.label;

  const totalQty = useMemo(
    () => items.reduce((sum, it) => sum + Number(quantities[it.id!] ?? 0), 0),
    [items, quantities],
  );

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

  const ensureBatchOptionsForSoLine = useCallback(
    async (soItemId: number, materialId: number, warehouseId: number) => {
      if (!(materialId > 0 && warehouseId > 0)) return;
      setBatchLoadingSoItemId(soItemId);
      try {
        const map = await loadBatchOptionsByMaterialId([materialId], warehouseId, batchOptionLabel);
        const key = `${materialId}:${warehouseId}`;
        setBatchOptionsBySoItemId((prev) => ({ ...prev, [soItemId]: map[key] ?? [] }));
      } finally {
        setBatchLoadingSoItemId(null);
      }
    },
    [batchOptionLabel],
  );

  const lineColumns = useMemo(
    () =>
      filterWarehouseTrackingColumns(
        [
      { title: t('app.kuaizhizao.warehouseOutbound.col.materialCode'), dataIndex: 'material_code', width: 120 },
      { title: t('app.kuaizhizao.warehouseOutbound.col.materialName'), dataIndex: 'material_name', ellipsis: true },
      {
        title: t('app.kuaizhizao.warehouseOutbound.entry.orderQty'),
        dataIndex: 'required_quantity',
        width: 100,
        align: 'right' as const,
      },
      {
        title: t('app.kuaizhizao.salesOrder.colShippedQty'),
        dataIndex: 'delivered_quantity',
        width: 100,
        align: 'right' as const,
        render: (v: number | undefined) => Number(v ?? 0),
      },
      {
        title: t('app.kuaizhizao.warehouseCommon.colUnitPrice'),
        dataIndex: 'unit_price',
        width: 100,
        align: 'right' as const,
      },
      {
        title: t('app.kuaizhizao.salesOrder.taxRate'),
        dataIndex: 'tax_rate',
        width: 80,
        align: 'right' as const,
      },
      {
        title: t('app.kuaizhizao.salesOrder.colShippableQty'),
        key: 'max_push',
        width: 100,
        align: 'right' as const,
        render: (_: unknown, it: SalesOrderItem) => Number(maxQuantities[it.id!] ?? 0),
      },
      {
        title: (
          <>
            {t('app.kuaizhizao.salesOrder.pushShipmentLineWarehouse')}
            <Typography.Text type="danger"> *</Typography.Text>
          </>
        ),
        key: 'warehouse',
        width: 160,
        render: (_: unknown, it: SalesOrderItem) =>
          it.id != null ? (
            <Select
              style={{ width: '100%', minWidth: 140 }}
              placeholder={t('app.kuaizhizao.shipmentNotice.selectOutboundWarehouse')}
              showSearch
              optionFilterProp="label"
              options={warehouseOptions}
              value={lineWh[it.id]}
              onChange={(nv) => {
                const soId = it.id!;
                const whId = Number(nv);
                setLineWh((prev) => ({ ...prev, [soId]: whId }));
                setLineTracking((prev) => ({
                  ...prev,
                  [soId]: {
                    ...prev[soId],
                    location_id: undefined,
                    location_code: undefined,
                    batch_number: undefined,
                    batch_allocations: [],
                  },
                }));
                void ensureBatchOptionsForSoLine(soId, Number(it.material_id ?? 0), whId);
              }}
            />
          ) : null,
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.location'),
        key: 'location',
        width: 150,
        render: (_: unknown, it: SalesOrderItem) => {
          if (it.id == null) return null;
          const soId = it.id;
          const whId = lineWh[soId];
          if (!whId) return t('app.kuaizhizao.warehouseInbound.field.selectWarehouseFirst');
          const tr = lineTracking[soId] ?? {};
          return (
            <PurchaseInboundLineLocationCell
              materialId={Number(it.material_id ?? 0) || undefined}
              warehouseId={whId}
              locationId={tr.location_id}
              selectWarehouseFirstPlaceholder={t('app.kuaizhizao.warehouseInbound.field.selectWarehouseFirst')}
              selectLocationPlaceholder={t('app.kuaizhizao.warehouseInbound.field.selectLocation')}
              onChange={(v, loc) => {
                setLineTracking((prev) => ({
                  ...prev,
                  [soId]: {
                    ...prev[soId],
                    location_id: v ?? undefined,
                    location_code: loc?.code ?? '',
                  },
                }));
              }}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.batchNo'),
        key: 'batch',
        width: 260,
        render: (_: unknown, it: SalesOrderItem) => {
          if (it.id == null) return null;
          const soId = it.id;
          const meta = lineMaterialMeta[soId];
          if (!isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) return '—';
          const whId = lineWh[soId];
          const opts = batchOptionsBySoItemId[soId] ?? [];
          const tr = lineTracking[soId] ?? {};
          const qty = Number(quantities[soId] ?? 0);
          const allocs = lineBatchAllocationsFromRow(
            {
              batch_allocations: tr.batch_allocations,
              batch_number: tr.batch_number,
            },
            qty,
          );
          const materialLabel = [it.material_code, it.material_name].filter(Boolean).join(' - ');
          return (
            <span
              onClick={() => {
                if (whId > 0 && !(opts.length > 0)) {
                  void ensureBatchOptionsForSoLine(soId, Number(it.material_id ?? 0), whId);
                }
              }}
            >
              <OutboundBatchAllocationField
                value={allocs}
                onChange={(next) => {
                  setLineTracking((prev) => ({
                    ...prev,
                    [soId]: {
                      ...prev[soId],
                      batch_allocations: next,
                      batch_number: next.length === 1 ? next[0].batchNo : undefined,
                    },
                  }));
                }}
                options={opts}
                totalQuantity={qty}
                loading={batchLoadingSoItemId === soId}
                disabled={!(whId > 0)}
                materialLabel={materialLabel}
                allowManualWithoutStock={allowNegativeInventory && !opts.length}
              />
            </span>
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.serialNo'),
        key: 'serial',
        width: 160,
        render: (_: unknown, it: SalesOrderItem) => {
          if (it.id == null) return null;
          const soId = it.id;
          const meta = lineMaterialMeta[soId];
          if (!isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) return '—';
          const qty = Math.floor(Number(quantities[soId] ?? 0));
          const tr = lineTracking[soId] ?? {};
          return (
            <SerialNumbersImportTrigger
              serials={tr.serial_numbers ?? []}
              expectedCount={qty > 0 ? qty : undefined}
              materialLabel={it.material_code || it.material_name}
              generateLoading={generatingSerialSoItemId === soId}
              onSerialsChange={(next) => {
                setLineTracking((prev) => ({
                  ...prev,
                  [soId]: { ...prev[soId], serial_numbers: next },
                }));
              }}
              onGenerate={async () => {
                const uuid = meta?.materialUuid;
                if (!uuid || !(qty > 0)) return [];
                const count = Math.min(qty, MATERIAL_SERIAL_GENERATE_MAX_COUNT);
                setGeneratingSerialSoItemId(soId);
                try {
                  const res = await materialSerialApi.generate(String(uuid), count, {});
                  setLineTracking((prev) => ({
                    ...prev,
                    [soId]: { ...prev[soId], serial_numbers: res.serial_nos },
                  }));
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
                  setGeneratingSerialSoItemId(null);
                }
              }}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.entry.thisOutbound'),
        key: 'qty',
        width: 140,
        render: (_: unknown, it: SalesOrderItem) =>
          it.id != null ? (
            <InputNumber
              min={0}
              max={Number(maxQuantities[it.id] ?? 0)}
              value={quantities[it.id]}
              onChange={(v) => setQuantities((prev) => ({ ...prev, [it.id!]: Number(v ?? 0) }))}
              style={{ width: '100%' }}
            />
          ) : null,
      },
      { title: t('common.unit'), dataIndex: 'material_unit', width: 60 },
    ],
        trackingFlags,
      ),
    [
      lineWh,
      maxQuantities,
      quantities,
      t,
      warehouseOptions,
      lineTracking,
      lineMaterialMeta,
      trackingFlags,
      batchOptionsBySoItemId,
      batchLoadingSoItemId,
      ensureBatchOptionsForSoLine,
      generatingSerialSoItemId,
      messageApi,
    ],
  );

  const leavePage = useCallback(() => {
    clearDraft();
    navigateLeavingPullEntry(
      navigate,
      OUTBOUND_LIST_PATH,
      pullEntryTabKey(location.pathname, location.search),
    );
  }, [clearDraft, navigate, location.pathname, location.search]);

  useEffect(() => {
    if (!requireShipmentNoticeBeforeDelivery) return;
    messageApi.warning(
      t('pages.system.configCenter.param.sales_require_shipment_notice_before_delivery_desc'),
    );
    leavePage();
  }, [requireShipmentNoticeBeforeDelivery]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bindSnapshot(() => ({
      quantities,
      lineWh,
      lineTracking,
      deliveryTime,
      notes,
      receiverUuid: operatorHook.receiverUuid,
      receiverName: operatorHook.receiverName,
    }));
    persistNow();
  }, [
    quantities,
    lineWh,
    lineTracking,
    deliveryTime,
    notes,
    operatorHook.receiverUuid,
    operatorHook.receiverName,
    bindSnapshot,
    persistNow,
  ]);

  useEffect(() => {
    if (!(Number.isFinite(salesOrderId) && salesOrderId > 0)) {
      messageApi.error(t('app.kuaizhizao.warehouseOutbound.entry.invalidSalesOrder'));
      leavePage();
    }
  }, [salesOrderId, leavePage, messageApi, t]);

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
    if (!Number.isFinite(salesOrderId) || salesOrderId <= 0 || initRef.current) return;
    initRef.current = true;
    void (async () => {
      setLoading(true);
      try {
        const [so, whRes, preview] = await Promise.all([
          getSalesOrder(salesOrderId, true),
          masterWarehouseApi.list({ is_active: true, limit: 500 }),
          previewPushSalesOrderToDelivery(salesOrderId),
        ]);
        setOrder(so as Record<string, unknown>);
        const lines = (so.items ?? []) as SalesOrderItem[];
        setItems(lines);
        setWarehouseOptions(mapWarehouseSelectOptions(whRes));
        const initQty: Record<number, number> = {};
        const initMax: Record<number, number> = {};
        const initLineWh: Record<number, number> = {};
        lines.forEach((it) => {
          if (it.id == null) return;
          initQty[it.id] = 0;
        });
        (preview.items || []).forEach((row) => {
          const itemId = Number(row.item_id);
          if (!Number.isFinite(itemId) || itemId <= 0) return;
          initMax[itemId] = Number(row.max_push_quantity ?? 0);
          const whId = Number(row.warehouse_id);
          if (Number.isFinite(whId) && whId > 0) {
            initLineWh[itemId] = whId;
          }
        });
        setQuantities(initQty);
        setMaxQuantities(initMax);
        setLineWh(initLineWh);
        const metaRows = lines.filter((l) => l.id != null).map((l) => ({ ...l, id: l.id }));
        setLineMaterialMeta(await loadConfirmPreviewMaterialMeta(metaRows));
        applyDraftOnce((draft) => {
          if (draft.quantities) {
            setQuantities((prev) => mergeRecordMaps(prev, draft.quantities as Record<number, number>));
          }
          if (draft.maxQuantities) {
            setMaxQuantities(draft.maxQuantities as Record<number, number>);
          }
          if (draft.lineWh) {
            setLineWh((prev) => mergeRecordMaps(prev, draft.lineWh as Record<number, number>));
          }
          if (draft.lineTracking && typeof draft.lineTracking === 'object') {
            setLineTracking((prev) => ({
              ...prev,
              ...(draft.lineTracking as Record<number, SoLineTracking>),
            }));
          }
          if (draft.deliveryTime) {
            const parsed = draftDayjs(draft.deliveryTime);
            setDeliveryTime(parsed?.isValid() ? parsed.startOf('day') : null);
          }
          if (typeof draft.notes === 'string') setNotes(draft.notes);
          operatorHook.restoreReceiver(
            typeof draft.receiverUuid === 'string' ? draft.receiverUuid : undefined,
            typeof draft.receiverName === 'string' ? draft.receiverName : undefined,
          );
        });
      } catch (e: unknown) {
        messageApi.error((e as Error)?.message || t('app.kuaizhizao.warehouseOutbound.entry.loadSalesOrderFailed'));
        leavePage();
      } finally {
        setLoading(false);
      }
    })();
  }, [salesOrderId, leavePage, messageApi, t, applyDraftOnce, operatorHook.restoreReceiver]);

  const submit = async (mode: 'draft' | 'confirm') => {
    if (!warehouseOptions.length) {
      messageApi.error(t('app.kuaizhizao.salesOrder.pushShipmentNoWarehouse'));
      return;
    }

    const deliveryQuantities: Record<number, number> = {};
    const lineWarehouses: Record<number, number> = {};
    let hasPositive = false;
    for (const it of items) {
      if (it.id == null) continue;
      const qty = Number(quantities[it.id] ?? 0);
      if (qty <= 0) continue;
      const max = Number(maxQuantities[it.id] ?? 0);
      if (qty > max) {
        messageApi.error(
          t('app.kuaizhizao.warehouseOutbound.entry.qtyExceedsPending', {
            material: it.material_code || it.material_name,
            max,
          }),
        );
        return;
      }
      const wh = lineWh[it.id];
      if (wh == null || !(wh > 0)) {
        messageApi.error(
          t('app.kuaizhizao.salesOrder.pushShipmentSelectLineWarehouse', {
            material: it.material_code || it.material_name || it.id,
          }),
        );
        return;
      }
      deliveryQuantities[it.id] = qty;
      lineWarehouses[it.id] = wh;
      hasPositive = true;

      const materialLabel = it.material_code || it.material_name || '-';
      const tr = lineTracking[it.id] ?? {};
      const needLoc = await lineLocationSelectionRequired(wh, tr.location_id, tr.location_code);
      if (needLoc) {
        messageApi.error(
          t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', { material: materialLabel }),
        );
        return;
      }
      const meta = lineMaterialMeta[it.id];
      if (isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) {
        const opts = batchOptionsBySoItemId[it.id] ?? [];
        const allocs = lineBatchAllocationsFromRow(
          {
            batch_allocations: tr.batch_allocations,
            batch_number: tr.batch_number,
          },
          qty,
        );
        if (
          !isValidOutboundBatchAllocations(allocs, opts, qty, {
            allowManualWithoutStock: allowNegativeInventory && !opts.length,
          })
        ) {
          messageApi.error(
            t('app.kuaizhizao.warehouseOutbound.confirm.batchAllocationRequired', {
              material: materialLabel,
              qty,
              batches: opts.map((o) => o.value).join('、') || '—',
            }),
          );
          return;
        }
      }
      if (isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) {
        const serials = (tr.serial_numbers ?? []).map((s) => String(s).trim()).filter(Boolean);
        const expected = Math.floor(qty);
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
    }
    if (!hasPositive) {
      messageApi.warning(t('app.kuaizhizao.warehouseOutbound.entry.fillOutboundQty'));
      return;
    }

    setSubmitting(true);
    try {
      const created = await pushSalesOrderToDelivery(salesOrderId, {
        delivery_quantities: deliveryQuantities,
        line_warehouses: lineWarehouses,
        notes: notes.trim() || undefined,
      });
      if (created?.delivery_id == null) {
        messageApi.error(t('app.kuaizhizao.warehouseOutbound.entry.noDeliveryId'));
        return;
      }
      const headerWhId = lineWarehouses[Number(Object.keys(lineWarehouses)[0])];
      const whOpt = warehouseOptions.find((o) => o.value === headerWhId);
      const detail = (await warehouseApi.salesDelivery.get(String(created.delivery_id))) as {
        items?: Array<Record<string, unknown>>;
      };
      const detailItems = Array.isArray(detail.items) ? detail.items : [];
      const updateItems = detailItems
        .map((row) => {
          const soItemId = Number(row.sales_order_item_id ?? 0);
          if (!(soItemId > 0) || !(deliveryQuantities[soItemId] > 0)) return null;
          const wh = lineWarehouses[soItemId];
          const whName = warehouseOptions.find((o) => o.value === wh)?.name ?? '';
          const tr = lineTracking[soItemId] ?? {};
          const serials = (tr.serial_numbers ?? []).map((s) => String(s).trim()).filter(Boolean);
          const lineQty = Number(deliveryQuantities[soItemId] ?? 0);
          const allocs = lineBatchAllocationsFromRow(
            {
              batch_allocations: tr.batch_allocations,
              batch_number: tr.batch_number,
            },
            lineQty,
          );
          const payload: Record<string, unknown> = {
            id: Number(row.id),
            warehouse_id: wh,
            warehouse_name: whName,
            location_id: tr.location_id != null && tr.location_id > 0 ? tr.location_id : undefined,
            location_code: String(tr.location_code ?? '').trim() || undefined,
            serial_numbers: serials.length ? serials : undefined,
          };
          if (allocs.length) {
            payload.batch_allocations = allocs.map((a) => ({
              batch_number: a.batchNo,
              quantity: a.quantity,
            }));
            if (allocs.length === 1) payload.batch_number = allocs[0].batchNo;
          }
          return payload;
        })
        .filter(Boolean);

      await warehouseApi.salesDelivery.update(String(created.delivery_id), {
        customer_id: Number(order?.customer_id ?? 0),
        customer_name: String(order?.customer_name ?? ''),
        warehouse_id: headerWhId,
        warehouse_name: whOpt?.name,
        ...(deliveryTime?.isValid()
          ? { delivery_time: toApiBusinessDocumentDateTime(deliveryTime) }
          : {}),
        deliverer_id: operatorHook.receiverId,
        deliverer_name: operatorHook.receiverName.trim() || undefined,
        attachments: normalizeDocumentAttachments(attachments),
        items: updateItems,
      });
      invalidateMenuBadgeCounts();
      clearDraft();
      if (mode === 'confirm') {
        navigateLeavingPullEntry(
          navigate,
          OUTBOUND_LIST_PATH,
          pullEntryTabKey(location.pathname, location.search),
          {
            outboundDirectConfirm: {
              id: Number(created.delivery_id),
              outbound_type: 'sales_delivery',
            },
          },
        );
      } else {
        messageApi.success(
          created.message ||
            t('app.kuaizhizao.warehouseOutbound.entry.draftDeliveryCreated', {
              code: created.delivery_code ? `：${created.delivery_code}` : '',
            }),
        );
        leavePage();
      }
    } catch (e: unknown) {
      const err = e as { message?: string; response?: { data?: { detail?: string } } };
      messageApi.error(err?.message || err?.response?.data?.detail || t('common.saveFailed'));
    } finally {
      setSubmitting(false);
    }
  };

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
            <Button loading={submitting} disabled={loading} onClick={() => void submit('draft')}>
              {t('app.kuaizhizao.warehouseOutbound.action.generateDraft')}
            </Button>
            <Button type="primary" loading={submitting} disabled={loading} onClick={() => void submit('confirm')}>
              {t('app.kuaizhizao.warehouseOutbound.action.confirmOutbound')}
            </Button>
          </Space>
        </>
      }
    >
      <Spin spinning={loading}>
        <Card styles={{ body: { padding: PAGE_SPACING.PADDING } }}>
          {order && (
            <Form layout="vertical" requiredMark={false}>
              <Row gutter={16}>
                <Col xs={24} sm={12} lg={6}>
                  <Form.Item label={t('app.kuaizhizao.warehouseOutbound.field.outboundType')}>
                    <ReadOnlyFormValue value={getOutboundIssueTypeLabel(t, 'sales_delivery')} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                  <Form.Item label={t('app.kuaizhizao.warehouseOutbound.entry.sourceDocNo')}>
                    <ReadOnlyFormValue value={orderCode} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                  <Form.Item label={t('app.kuaizhizao.warehouseOutbound.col.customer')}>
                    <ReadOnlyFormValue value={String(order.customer_name ?? '')} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                  <Form.Item label={t('app.kuaizhizao.warehouseOutbound.entry.orderStatus')}>
                    <ReadOnlyFormValue value={reportDocumentStatusText(t, order.status)} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                  <Form.Item label={t('app.kuaizhizao.warehouseOutbound.col.outboundDate')}>
                    <DatePicker
                      style={{ width: '100%' }}
                      value={deliveryTime}
                      onChange={(v) => setDeliveryTime(v ? v.startOf('day') : null)}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                  <OutboundEntryOperatorField hook={operatorHook} />
                </Col>
              </Row>
              <Typography.Text strong style={{ display: 'block', marginTop: 16, marginBottom: 8 }}>
                {t('app.kuaizhizao.warehouseOutbound.entry.outboundDetails')}
                <Typography.Text type="secondary" style={{ marginLeft: 12, fontWeight: 'normal' }}>
                  {t('app.kuaizhizao.warehouseOutbound.entry.totalOutboundQty', { qty: totalQty })}
                </Typography.Text>
              </Typography.Text>
              <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
              <Table
                className="warehouse-detail-table"
                size="small"
                rowKey={(r) => String(r.id)}
                pagination={false}
                dataSource={items}
                columns={lineColumns}
              />
              <OutboundEntryRemarksSection value={notes} onChange={setNotes} />
              <OutboundEntryAttachmentsSection
                category="sales_delivery_attachments"
                fileList={attachments}
                onChange={setAttachments}
              />
            </Form>
          )}
        </Card>
      </Spin>
    </DocumentFormPageLayout>
  );
};

export default OutboundSalesOrderPullEntryPage;
