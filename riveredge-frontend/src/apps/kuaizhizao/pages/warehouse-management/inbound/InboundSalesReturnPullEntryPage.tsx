/**
 * 从销售订单取单开销售退货入库 — 独立 Tab 页
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { App, Button, Card, Col, DatePicker, Form, Input, InputNumber, Row, Select, Space, Spin, Table, Typography } from 'antd';
import { ArrowLeftOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { type Dayjs } from 'dayjs';
import {
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageLayout,
  PAGE_SPACING,
  WAREHOUSE_DETAIL_TABLE_STYLES,
} from '../../../../../components/layout-templates';
import { UniTableDetailHeader } from '../../../../../components/uni-table-detail/UniTableDetail';
import type { UploadFile } from 'antd/es/upload/interface';
import { warehouseApi as masterWarehouseApi } from '../../../../master-data/services/warehouse';
import { getSalesOrder } from '../../../services/sales-order';
import { warehouseApi } from '../../../services/warehouse-execution';
import { normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { setCustomPageTitle, removeCustomPageTitle } from '../../../../../utils/customPageTitle';
import { formatDateBySiteSetting } from '../../../../../utils/format';
import {
  InboundEntryAttachmentsSection,
  InboundEntryReceiverField,
  InboundEntryRemarksSection,
  ReadOnlyFormValue,
  mapWarehouseSelectOptions,
  useInboundReceiverSelect,
} from './inboundEntryShared';
import { inboundReceiptTypeLabel } from './inboundHubTypes';
import { INBOUND_LIST_PATH, inboundSalesReturnEntryPath } from './inboundPaths';
import {
  draftDayjs,
  draftOptionalNumber,
  mergeRecordMaps,
  usePullEntryFormDraft,
} from '../shared/pullEntryFormDraft';
import { navigateLeavingPullEntry, pullEntryTabKey } from '../shared/pullEntryCloseTab';
import { resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import { toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';
import { PurchaseInboundLineLocationCell } from './PurchaseInboundLineWhCells';
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
} from './inboundItemTracking';
import {
  materialBatchApi,
  materialSerialApi,
  MATERIAL_SERIAL_GENERATE_MAX_COUNT,
} from '../../../../master-data/services/material';
import { SerialNumbersImportTrigger } from '../../../../../components/serial-numbers-import';

type PreviewLine = {
  sales_order_item_id?: number;
  material_id: number;
  material_code: string;
  material_name: string;
  material_spec?: string;
  material_unit: string;
  source_doc_quantity?: number;
  source_received_quantity?: number;
  source_pending_quantity?: number;
  return_quantity?: number;
  unit_price?: number;
};

type SalesReturnPreview = {
  sales_order_id: number;
  sales_order_code: string;
  lines: PreviewLine[];
  message?: string;
};

type SalesReturnLineTracking = {
  location_id?: number;
  location_code?: string;
  batch_number?: string;
  serial_numbers?: string[];
};

function buildSalesReturnUpdateItems(
  detailItems: Record<string, unknown>[],
  trackingBySoItemId: Record<number, SalesReturnLineTracking>,
): Record<string, unknown>[] {
  return detailItems.map((item) => {
    const soItemId = Number(item.sales_order_item_id ?? 0);
    const tr = soItemId > 0 ? trackingBySoItemId[soItemId] : undefined;
    const serialFromTr = tr?.serial_numbers?.map((s) => String(s).trim()).filter(Boolean);
    const serialFromItem = Array.isArray(item.serial_numbers)
      ? (item.serial_numbers as unknown[]).map((s) => String(s).trim()).filter(Boolean)
      : [];
    const serial_numbers = serialFromTr?.length ? serialFromTr : serialFromItem.length ? serialFromItem : undefined;
    const batchTrim = String(tr?.batch_number ?? item.batch_number ?? '').trim();
    return {
      material_id: item.material_id,
      material_code: item.material_code,
      material_name: item.material_name,
      material_spec: item.material_spec ?? undefined,
      material_unit: item.material_unit,
      return_quantity: item.return_quantity,
      unit_price: item.unit_price,
      total_amount: item.total_amount,
      sales_order_item_id: item.sales_order_item_id ?? undefined,
      sales_delivery_item_id: item.sales_delivery_item_id ?? undefined,
      location_id:
        tr?.location_id != null && Number(tr.location_id) > 0
          ? Number(tr.location_id)
          : item.location_id != null && Number(item.location_id) > 0
            ? Number(item.location_id)
            : undefined,
      location_code:
        String(tr?.location_code ?? item.location_code ?? '').trim() || undefined,
      batch_number: batchTrim || undefined,
      serial_numbers,
      status: item.status ?? '待退货',
    };
  });
}

const InboundSalesReturnPullEntryPage: React.FC = () => {
  const { salesOrderId: salesOrderIdParam } = useParams<{ salesOrderId: string }>();
  const salesOrderId = Number(salesOrderIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const { message: messageApi } = App.useApp();
  const { t } = useTranslation();
  const pullFromSalesOrderAction = resolveKuaizhizaoDocumentAction(t, 'inbound.pull_from_sales_order');
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const receiverHook = useInboundReceiverSelect();
  const trackingFlags = useWarehouseTrackingFlags();
  const initRef = useRef(false);
  const [lineMaterialMeta, setLineMaterialMeta] = useState<Record<number, ConfirmPreviewMaterialMeta>>({});
  const [lineTracking, setLineTracking] = useState<Record<number, SalesReturnLineTracking>>({});
  const [generatingBatchSoItemId, setGeneratingBatchSoItemId] = useState<number | null>(null);
  const [generatingSerialSoItemId, setGeneratingSerialSoItemId] = useState<number | null>(null);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [preview, setPreview] = useState<SalesReturnPreview | null>(null);
  const [order, setOrder] = useState<Record<string, unknown> | null>(null);
  const [warehouseOptions, setWarehouseOptions] = useState<{ label: string; value: number; name: string }[]>([]);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [defaultWarehouseId, setDefaultWarehouseId] = useState<number | undefined>();
  const [lineWh, setLineWh] = useState<Record<number, number>>({});
  const [returnTime, setReturnTime] = useState<Dayjs | null>(null);
  const [returnNotes, setReturnNotes] = useState('');
  const [attachments, setAttachments] = useState<UploadFile[]>([]);
  const { bindSnapshot, persistNow, clearDraft, applyDraftOnce } = usePullEntryFormDraft(
    'kuaizhizao:inbound-sales-return-pull',
  );

  const lines = preview?.lines ?? [];
  const pagePath =
    Number.isFinite(salesOrderId) && salesOrderId > 0 ? inboundSalesReturnEntryPath(salesOrderId) : INBOUND_LIST_PATH;
  const pageTitle = preview?.sales_order_code
    ? `${pullFromSalesOrderAction.label} — ${preview.sales_order_code}`
    : pullFromSalesOrderAction.label;

  const totalReturnQty = useMemo(
    () =>
      lines.reduce((sum, it) => {
        const itemId = it.sales_order_item_id;
        if (itemId == null) return sum;
        return sum + Number(quantities[itemId] ?? 0);
      }, 0),
    [lines, quantities],
  );

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
      quantities,
      defaultWarehouseId,
      lineWh,
      lineTracking,
      returnTime,
      returnNotes,
      receiverUuid: receiverHook.receiverUuid,
      receiverName: receiverHook.receiverName,
    }));
    persistNow();
  }, [
    quantities,
    defaultWarehouseId,
    lineWh,
    lineTracking,
    returnTime,
    returnNotes,
    receiverHook.receiverUuid,
    receiverHook.receiverName,
    bindSnapshot,
    persistNow,
  ]);

  useEffect(() => {
    if (!(Number.isFinite(salesOrderId) && salesOrderId > 0)) {
      messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.salesReturn.invalidOrder'));
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
  }, [pageTitle, pagePath]);

  useEffect(() => {
    if (!Number.isFinite(salesOrderId) || salesOrderId <= 0 || initRef.current) return;
    initRef.current = true;
    void (async () => {
      setLoading(true);
      try {
        const [previewRaw, orderRaw, whRes] = await Promise.all([
          warehouseApi.salesReturn.previewFromSalesOrder(salesOrderId) as Promise<SalesReturnPreview>,
          getSalesOrder(salesOrderId),
          masterWarehouseApi.list({ is_active: true, limit: 500 }),
        ]);
        if (!previewRaw?.lines?.length) {
          messageApi.warning(previewRaw?.message || t('app.kuaizhizao.warehouseInbound.entry.salesReturn.noLines'));
          leavePage();
          return;
        }
        setWarehouseOptions(mapWarehouseSelectOptions(whRes));
        const qtyMap: Record<number, number> = {};
        previewRaw.lines.forEach((it) => {
          if (it.sales_order_item_id != null) {
            qtyMap[it.sales_order_item_id] = 0;
          }
        });
        setPreview(previewRaw);
        setOrder(orderRaw as Record<string, unknown>);
        setQuantities(qtyMap);
        const metaRows = previewRaw.lines
          .filter((l) => l.sales_order_item_id != null)
          .map((l) => ({ ...l, id: l.sales_order_item_id }));
        setLineMaterialMeta(await loadConfirmPreviewMaterialMeta(metaRows));
        applyDraftOnce((draft) => {
          if (draft.quantities) {
            setQuantities((prev) => mergeRecordMaps(prev, draft.quantities as Record<number, number>));
          }
          const whId = draftOptionalNumber(draft.defaultWarehouseId);
          if (whId != null) setDefaultWarehouseId(whId);
          if (draft.lineWh) {
            setLineWh((prev) => mergeRecordMaps(prev, draft.lineWh as Record<number, number>));
          }
          if (draft.lineTracking && typeof draft.lineTracking === 'object') {
            setLineTracking((prev) => ({
              ...prev,
              ...(draft.lineTracking as Record<number, SalesReturnLineTracking>),
            }));
          }
          if (draft.returnTime) {
            const parsed = draftDayjs(draft.returnTime);
            setReturnTime(parsed?.isValid() ? parsed.startOf('day') : null);
          }
          if (typeof draft.returnNotes === 'string') setReturnNotes(draft.returnNotes);
          receiverHook.restoreReceiver({
            uuid: typeof draft.receiverUuid === 'string' ? draft.receiverUuid : undefined,
            name: typeof draft.receiverName === 'string' ? draft.receiverName : undefined,
          });
        });
      } catch (e: unknown) {
        messageApi.error((e as Error)?.message || t('app.kuaizhizao.warehouseInbound.entry.salesReturn.loadFailed'));
        leavePage();
      } finally {
        setLoading(false);
      }
    })();
  }, [salesOrderId, leavePage, messageApi, t, applyDraftOnce, receiverHook.restoreReceiver]);

  const applyDefaultWarehouse = (warehouseId: number) => {
    setDefaultWarehouseId(warehouseId);
    const next: Record<number, number> = { ...lineWh };
    lines.forEach((it) => {
      if (it.sales_order_item_id != null) next[it.sales_order_item_id] = warehouseId;
    });
    setLineWh(next);
    setLineTracking((prev) => {
      const cleared: Record<number, SalesReturnLineTracking> = { ...prev };
      lines.forEach((it) => {
        const id = it.sales_order_item_id;
        if (id == null) return;
        const row = cleared[id];
        if (row) {
          cleared[id] = { ...row, location_id: undefined, location_code: undefined };
        }
      });
      return cleared;
    });
  };

  const submit = async (mode: 'draft' | 'confirm') => {
    if (!preview) return;
    let hasPositiveQty = false;
    const returnQuantities: Record<number, number> = {};
    for (const it of lines) {
      const itemId = it.sales_order_item_id;
      if (itemId == null) continue;
      const qty = quantities[itemId] ?? 0;
      const max = Number(it.source_pending_quantity ?? 0);
      if (qty <= 0) continue;
      hasPositiveQty = true;
      if (qty > max) {
        messageApi.error(
          t('app.kuaizhizao.warehouseInbound.entry.salesReturn.qtyExceedsReturnable', {
            material: it.material_code || it.material_name,
            max,
          }),
        );
        return;
      }
      returnQuantities[itemId] = qty;
    }
    if (!hasPositiveQty) {
      messageApi.warning(t('app.kuaizhizao.warehouseInbound.entry.salesReturn.fillReturnQty'));
      return;
    }
    const whId = defaultWarehouseId ?? Object.values(lineWh)[0];
    if (!whId || !(whId > 0)) {
      messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.salesReturn.selectWarehouse'));
      return;
    }
    const whOpt = warehouseOptions.find((o) => o.value === whId);
    if (!whOpt) return;

    const batch_numbers: Record<number, string> = {};
    for (const it of lines) {
      const itemId = it.sales_order_item_id;
      if (itemId == null) continue;
      const qty = returnQuantities[itemId];
      if (!(qty > 0)) continue;
      const materialLabel = it.material_code || it.material_name || '-';
      const lineWhId = lineWh[itemId] ?? whId;
      const tr = lineTracking[itemId] ?? {};
      const needLoc = await lineLocationSelectionRequired(lineWhId, tr.location_id, tr.location_code);
      if (needLoc) {
        messageApi.error(
          t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', { material: materialLabel }),
        );
        return;
      }
      const meta = lineMaterialMeta[itemId];
      if (isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) {
        const batchStr = String(tr.batch_number ?? '').trim();
        if (!batchStr) {
          messageApi.error(
            t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
              material: materialLabel,
              batches: '—',
            }),
          );
          return;
        }
        batch_numbers[itemId] = batchStr;
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

    setSubmitting(true);
    try {
      const created = (await warehouseApi.salesReturn.pullFromSalesOrder({
        sales_order_id: salesOrderId,
        warehouse_id: whId,
        warehouse_name: whOpt.name,
        return_quantities: returnQuantities,
        batch_numbers: Object.keys(batch_numbers).length ? batch_numbers : undefined,
      })) as { id?: number; return_code?: string };
      if (created?.id == null) {
        messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.salesReturn.noReturnId'));
        return;
      }
      const detail = (await warehouseApi.salesReturn.get(String(created.id))) as {
        items?: Record<string, unknown>[];
      };
      const detailItems = Array.isArray(detail.items) ? detail.items : [];
      await warehouseApi.salesReturn.update(String(created.id), {
        return_time: returnTime?.isValid() ? toApiBusinessDocumentDateTime(returnTime) : undefined,
        returner_id: receiverHook.receiverId,
        returner_name: receiverHook.receiverName.trim() || undefined,
        notes: returnNotes.trim() || undefined,
        attachments: normalizeDocumentAttachments(attachments),
        items: buildSalesReturnUpdateItems(detailItems, lineTracking),
      });
      invalidateMenuBadgeCounts();
      clearDraft();
      if (mode === 'confirm') {
        navigateLeavingPullEntry(
          navigate,
          INBOUND_LIST_PATH,
          pullEntryTabKey(location.pathname, location.search),
          {
            inboundDirectConfirm: {
              id: Number(created.id),
              receipt_type: 'sales_return',
            },
          },
        );
      } else {
        messageApi.success(
          t('app.kuaizhizao.warehouseInbound.entry.salesReturn.draftCreated', {
            code: created.return_code
              ? t('app.kuaizhizao.warehouseInbound.entry.purchase.draftCreatedSuffix', { code: created.return_code })
              : '',
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

  const entryColumns = useMemo(
    () =>
      filterWarehouseTrackingColumns(
        [
      { title: t('app.kuaizhizao.warehouseInbound.col.materialCode'), dataIndex: 'material_code', width: 120, ellipsis: true },
      { title: t('app.kuaizhizao.warehouseInbound.col.materialName'), dataIndex: 'material_name', width: 150, ellipsis: true },
      { title: t('app.kuaizhizao.warehouseInbound.col.spec'), dataIndex: 'material_spec', width: 120, ellipsis: true, render: (v: unknown) => v || '—' },
      { title: t('common.unit'), dataIndex: 'material_unit', width: 70, align: 'center' as const },
      { title: t('app.kuaizhizao.warehouseInbound.col.shippedQty'), dataIndex: 'source_doc_quantity', width: 100, align: 'right' as const },
      { title: t('app.kuaizhizao.warehouseInbound.col.returnedQty'), dataIndex: 'source_received_quantity', width: 90, align: 'right' as const },
      { title: t('app.kuaizhizao.warehouseInbound.col.returnableQty'), dataIndex: 'source_pending_quantity', width: 90, align: 'right' as const },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.returnWarehouse'),
        width: 150,
        render: (_: unknown, record: PreviewLine) =>
          record.sales_order_item_id != null ? (
            <Select
              style={{ width: '100%', minWidth: 118 }}
              placeholder={t('app.kuaizhizao.warehouseInbound.field.select')}
              showSearch
              optionFilterProp="label"
              value={lineWh[record.sales_order_item_id] ?? defaultWarehouseId}
              options={warehouseOptions}
              onChange={(nv) => {
                const soId = record.sales_order_item_id!;
                setLineWh((prev) => ({ ...prev, [soId]: nv }));
                setLineTracking((prev) => ({
                  ...prev,
                  [soId]: { ...prev[soId], location_id: undefined, location_code: undefined },
                }));
              }}
            />
          ) : null,
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.location'),
        width: 150,
        render: (_: unknown, record: PreviewLine) => {
          const soId = record.sales_order_item_id;
          if (soId == null) return null;
          const lineWhId = lineWh[soId] ?? defaultWarehouseId;
          if (!lineWhId) {
            return t('app.kuaizhizao.warehouseInbound.field.selectWarehouseFirst');
          }
          const tr = lineTracking[soId] ?? {};
          return (
            <PurchaseInboundLineLocationCell
              materialId={record.material_id}
              warehouseId={lineWhId}
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
        title: t('app.kuaizhizao.warehouseInbound.col.batchNo'),
        width: 130,
        render: (_: unknown, record: PreviewLine) => {
          const soId = record.sales_order_item_id;
          if (soId == null) return null;
          const meta = lineMaterialMeta[soId];
          if (!isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) return '—';
          const tr = lineTracking[soId] ?? {};
          return (
            <Space size={2}>
              <Input
                size="small"
                style={{ width: 96 }}
                value={tr.batch_number ?? ''}
                onChange={(e) => {
                  const v = e.target.value;
                  setLineTracking((prev) => ({
                    ...prev,
                    [soId]: { ...prev[soId], batch_number: v },
                  }));
                }}
              />
              <Button
                type="link"
                size="small"
                icon={<ThunderboltOutlined />}
                loading={generatingBatchSoItemId === soId}
                style={{ padding: 0 }}
                onClick={() => {
                  const uuid = meta?.materialUuid;
                  if (!uuid) return;
                  setGeneratingBatchSoItemId(soId);
                  void materialBatchApi
                    .generate(uuid, {})
                    .then((res) => {
                      setLineTracking((prev) => ({
                        ...prev,
                        [soId]: { ...prev[soId], batch_number: res.batch_no },
                      }));
                      messageApi.success(t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerated'));
                    })
                    .catch((e: Error) => {
                      messageApi.error(
                        e?.message || t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerateFailed'),
                      );
                    })
                    .finally(() => setGeneratingBatchSoItemId(null));
                }}
              />
            </Space>
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.serialNo'),
        width: 160,
        render: (_: unknown, record: PreviewLine) => {
          const soId = record.sales_order_item_id;
          if (soId == null) return null;
          const meta = lineMaterialMeta[soId];
          if (!isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) return '—';
          const qty = Math.floor(Number(quantities[soId] ?? 0));
          const tr = lineTracking[soId] ?? {};
          const serials = tr.serial_numbers ?? [];
          return (
            <SerialNumbersImportTrigger
              serials={serials}
              expectedCount={qty > 0 ? qty : undefined}
              materialLabel={record.material_code || record.material_name}
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
        title: t('app.kuaizhizao.warehouseInbound.col.thisSalesReturn'),
        width: 130,
        align: 'right' as const,
        render: (_: unknown, record: PreviewLine) =>
          record.sales_order_item_id != null ? (
            <InputNumber
              min={0}
              max={Number(record.source_pending_quantity ?? 0)}
              precision={4}
              value={quantities[record.sales_order_item_id] ?? 0}
              onChange={(v) =>
                setQuantities((prev) => ({
                  ...prev,
                  [record.sales_order_item_id!]: Number(v) || 0,
                }))
              }
              style={{ width: 110 }}
            />
          ) : null,
      },
    ],
        trackingFlags,
      ),
    [
      t,
      lineWh,
      defaultWarehouseId,
      warehouseOptions,
      quantities,
      lineTracking,
      lineMaterialMeta,
      trackingFlags,
      generatingBatchSoItemId,
      generatingSerialSoItemId,
      messageApi,
    ],
  );

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
              {t('app.kuaizhizao.warehouseInbound.action.generateDraft')}
            </Button>
            <Button type="primary" loading={submitting} disabled={loading} onClick={() => void submit('confirm')}>
              {t('app.kuaizhizao.warehouseInbound.action.confirmInbound')}
            </Button>
          </Space>
        </>
      }
    >
      <Spin spinning={loading}>
        <Card styles={{ body: { padding: PAGE_SPACING.PADDING } }}>
          <div className="form-modal-content-inner">
            {preview && (
              <Form layout="vertical" requiredMark={false}>
                <Row gutter={16}>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.inboundType')}>
                      <ReadOnlyFormValue value={inboundReceiptTypeLabel(t, 'sales_return')} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.sourceDocNo')}>
                      <ReadOnlyFormValue value={preview.sales_order_code} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.customer')}>
                      <ReadOnlyFormValue value={order?.customer_name ? String(order.customer_name) : undefined} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.orderStatus')}>
                      <ReadOnlyFormValue value={order?.status ? String(order.status) : undefined} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.orderDate')}>
                      <ReadOnlyFormValue
                        value={order?.order_date ? formatDateBySiteSetting(String(order.order_date)) : undefined}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.requiredDeliveryDate')}>
                      <ReadOnlyFormValue
                        value={order?.delivery_date ? formatDateBySiteSetting(String(order.delivery_date)) : undefined}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.returnTime')}>
                      <DatePicker
                        style={{ width: '100%' }}
                        value={returnTime}
                        onChange={(v) => setReturnTime(v ? v.startOf('day') : null)}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <InboundEntryReceiverField label={t('app.kuaizhizao.warehouseInbound.field.salesReturner')} hook={receiverHook} />
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.defaultReturnWarehouse')} required>
                      <Select
                        style={{ width: '100%' }}
                        placeholder={t('app.kuaizhizao.warehouseInbound.field.applyToAllLines')}
                        showSearch
                        allowClear
                        optionFilterProp="label"
                        value={defaultWarehouseId}
                        options={warehouseOptions}
                        onChange={(v) => {
                          if (v != null) applyDefaultWarehouse(v);
                          else setDefaultWarehouseId(undefined);
                        }}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.totalQty')}>
                      <ReadOnlyFormValue value={totalReturnQty.toLocaleString()} />
                    </Form.Item>
                  </Col>
                </Row>
              </Form>
            )}

            {lines.length > 0 && (
              <div className="uni-table-detail" style={{ marginTop: PAGE_SPACING.BLOCK_GAP }}>
                <UniTableDetailHeader title={t('app.kuaizhizao.warehouseInbound.section.returnDetailsSales')} required />
                <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
                <div className="uni-table-detail-body">
                  <div className="uni-table-detail-scroll">
                    <Table
                      className="uni-detail-table warehouse-detail-table"
                      size="small"
                      rowKey={(r) => r.sales_order_item_id ?? r.material_id}
                      pagination={false}
                      scroll={{ x: 1500 }}
                      dataSource={lines}
                      columns={entryColumns}
                    />
                  </div>
                </div>
              </div>
            )}

            {preview && (
              <Form layout="vertical" requiredMark={false} style={{ marginTop: PAGE_SPACING.BLOCK_GAP }}>
                <InboundEntryAttachmentsSection
                  category="sales_return_attachments"
                  fileList={attachments}
                  onChange={setAttachments}
                />
                <InboundEntryRemarksSection
                  value={returnNotes}
                  onChange={setReturnNotes}
                  label={t('app.kuaizhizao.warehouseInbound.field.salesReturnRemarks')}
                  placeholder={t('app.kuaizhizao.warehouseInbound.field.salesReturnRemarksPlaceholder')}
                />
              </Form>
            )}
          </div>
        </Card>
      </Spin>
    </DocumentFormPageLayout>
  );
};

export default InboundSalesReturnPullEntryPage;
