/**
 * 从采购订单取单开入库单 — 独立 Tab 页（基本信息 + 明细录入）
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { App, Button, Card, Col, DatePicker, Form, Input, InputNumber, Modal, Row, Select, Space, Spin, Table, Tooltip, Typography } from 'antd';
import { ArrowLeftOutlined, ThunderboltOutlined } from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import { prefetchMaterialsForUnitSelect } from '../../../../../components/material-unit-select';
import { SerialNumbersImportTrigger } from '../../../../../components/serial-numbers-import';
import {
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageLayout,
  MODAL_CONFIG,
  PAGE_SPACING,
  WAREHOUSE_DETAIL_TABLE_STYLES,
} from '../../../../../components/layout-templates';
import { DOCUMENT_DETAIL_CONTROL_SIZE } from '../../../components/document-detail-table/documentDetailTable';
import { UniTableDetailHeader } from '../../../../../components/uni-table-detail/UniTableDetail';
import {
  materialBatchApi,
  materialSerialApi,
  MATERIAL_SERIAL_GENERATE_MAX_COUNT,
} from '../../../../master-data/services/material';
import {
  getPurchaseOrder,
  pushPurchaseOrderToReceiptPreview,
  type PurchaseOrder,
  type PurchaseOrderItem,
} from '../../../services/purchase';
import { normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { setCustomPageTitle, removeCustomPageTitle } from '../../../../../utils/customPageTitle';
import {formatDateBySiteSetting, formatQuantity} from '../../../../../utils/format';
import { reportDocumentStatusText } from '../../../utils/reportPresentation';
import { loadConfirmPreviewMaterialMeta, type ConfirmPreviewMaterialMeta } from './inboundItemTracking';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import {
  enrichPurchaseOrderItemsMaterial,
  getOutstandingPoItems,
  getPoItemReceivableMax,
  normalizePurchaseOrderDetail,
} from './inboundPoReceiptEntryUtils';
import { lineLocationSelectionRequired } from '../../../../../components/uni-wh-dropdown';
import { loadPullWarehouseReferenceOptions } from '../../../../../components/uni-pull-query';
import {
  PURCHASE_INBOUND_WH_HOST,
  PurchaseInboundLineLocationCell,
  PurchaseInboundLineWarehouseCell,
} from './PurchaseInboundLineWhCells';
import {
  InboundEntryAttachmentsSection,
  InboundEntryReceiverField,
  InboundEntryRemarksSection,
  ReadOnlyFormValue,
  useInboundReceiverSelect,
} from './inboundEntryShared';
import { inboundReceiptTypeLabel } from './inboundHubTypes';
import {
  INBOUND_LIST_PATH,
  PURCHASE_INBOUND_LIST_PATH,
  inboundPoEntryPath,
  purchaseReceiptCreatePath,
} from './inboundPaths';
import type { PurchaseReceiptPoComposePayload } from './inboundPullEntryTypes';
import {
  draftOptionalNumber,
  mergeRecordMaps,
  sanitizePullEntryLineQuantities,
  usePullEntryFormDraft,
} from '../shared/pullEntryFormDraft';
import { navigateLeavingPullEntry, pullEntryTabKey } from '../shared/pullEntryCloseTab';
import { resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import { coerceFormDate, toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';

const MIN_INBOUND_RECEIPT_YEAR = 2000;

function resolveInboundReceiptDate(draftValue: unknown): Dayjs {
  if (draftValue != null && draftValue !== '') {
    const parsed = coerceFormDate(draftValue);
    if (parsed?.isValid() && parsed.year() >= MIN_INBOUND_RECEIPT_YEAR) {
      return parsed.startOf('day');
    }
  }
  return dayjs().startOf('day');
}

const InboundPoPullEntryPage: React.FC = () => {
  const { poId: poIdParam } = useParams<{ poId: string }>();
  const poId = Number(poIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const { message: messageApi } = App.useApp();
  const { t } = useTranslation();
  const trackingFlags = useWarehouseTrackingFlags();
  const pullFromPurchaseOrderAction = resolveKuaizhizaoDocumentAction(t, 'purchase_receipt.pull_from_purchase_order');
  const receiverHook = useInboundReceiverSelect();
  const initRef = useRef(false);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [order, setOrder] = useState<PurchaseOrder | null>(null);
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [batchNumbers, setBatchNumbers] = useState<Record<number, string>>({});
  const [lineWh, setLineWh] = useState<Record<number, number>>({});
  const [lineWhName, setLineWhName] = useState<Record<number, string>>({});
  const [lineLoc, setLineLoc] = useState<Record<number, number | undefined>>({});
  const [lineLocCode, setLineLocCode] = useState<Record<number, string>>({});
  const [warehouseNameByWhId, setWarehouseNameByWhId] = useState<Record<number, string>>({});
  const [materialMeta, setMaterialMeta] = useState<Record<number, ConfirmPreviewMaterialMeta>>({});
  const [serials, setSerials] = useState<Record<number, string[]>>({});
  const [generatingSerialId, setGeneratingSerialId] = useState<number | null>(null);
  const [generatingBatchId, setGeneratingBatchId] = useState<number | null>(null);
  const [batchWhModalOpen, setBatchWhModalOpen] = useState(false);
  const [batchWhSelectedId, setBatchWhSelectedId] = useState<number | undefined>();
  const [batchWhSelectedName, setBatchWhSelectedName] = useState<string | undefined>();
  const [batchWhApplying, setBatchWhApplying] = useState(false);
  const [receiptTime, setReceiptTime] = useState<Dayjs | null>(null);
  const [deliveryNote, setDeliveryNote] = useState('');
  const [defaultWarehouseId, setDefaultWarehouseId] = useState<number | undefined>();
  const [receiptNotes, setReceiptNotes] = useState('');
  const [receiptAttachments, setReceiptAttachments] = useState<any[]>([]);
  const { bindSnapshot, persistNow, clearDraft, applyDraftOnce } = usePullEntryFormDraft(
    'kuaizhizao:inbound-po-pull',
  );

  const outstandingItems = useMemo(() => getOutstandingPoItems(order), [order]);
  const totalReceiptQty = useMemo(
    () =>
      outstandingItems.reduce((sum, it) => {
        if (it.id == null) return sum;
        return sum + Number(quantities[it.id] ?? 0);
      }, 0),
    [outstandingItems, quantities],
  );
  const pagePath = Number.isFinite(poId) && poId > 0 ? inboundPoEntryPath(poId) : INBOUND_LIST_PATH;
  const pageTitle = order?.order_code
    ? `${pullFromPurchaseOrderAction.label} — ${order.order_code}`
    : pullFromPurchaseOrderAction.label;

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
      quantities: sanitizePullEntryLineQuantities(quantities),
      batchNumbers,
      lineWh,
      lineLoc,
      lineLocCode,
      serials,
      defaultWarehouseId,
      receiptTime,
      deliveryNote,
      receiptNotes,
      receiverUuid: receiverHook.receiverUuid,
      receiverName: receiverHook.receiverName,
    }));
    persistNow();
  }, [
    quantities,
    batchNumbers,
    lineWh,
    lineLoc,
    lineLocCode,
    serials,
    defaultWarehouseId,
    receiptTime,
    deliveryNote,
    receiptNotes,
    receiverHook.receiverUuid,
    receiverHook.receiverName,
    bindSnapshot,
    persistNow,
  ]);

  const applyLineWarehouse = useCallback(
    (lineIds: number[], warehouseId: number, warehouseName?: string) => {
      if (!lineIds.length) return;
      setLineWh((prev) => {
        const next = { ...prev };
        lineIds.forEach((id) => {
          next[id] = warehouseId;
        });
        return next;
      });
      if (warehouseName) {
        setWarehouseNameByWhId((prev) => ({ ...prev, [warehouseId]: warehouseName }));
        setLineWhName((prev) => {
          const next = { ...prev };
          lineIds.forEach((id) => {
            next[id] = warehouseName;
          });
          return next;
        });
      }
      setLineLoc((prev) => {
        const next = { ...prev };
        lineIds.forEach((id) => {
          delete next[id];
        });
        return next;
      });
      setLineLocCode((prev) => {
        const next = { ...prev };
        lineIds.forEach((id) => {
          delete next[id];
        });
        return next;
      });
    },
    [],
  );

  const handleBatchApplyWarehouse = useCallback(
    (warehouseId: number, warehouseName?: string) => {
      const lineIds = outstandingItems
        .filter((it) => it.id != null)
        .map((it) => it.id!);
      if (!lineIds.length) {
        messageApi.warning(t('app.kuaizhizao.warehouseInbound.msg.noLinesToSetWarehouse'));
        return;
      }
      applyLineWarehouse(lineIds, warehouseId, warehouseName);
      setDefaultWarehouseId(warehouseId);
      messageApi.success(t('app.kuaizhizao.warehouseInbound.msg.batchWarehouseApplied', { count: lineIds.length }));
    },
    [applyLineWarehouse, messageApi, outstandingItems, t],
  );

  const handleBatchWhModalConfirm = async () => {
    if (batchWhSelectedId == null || !(batchWhSelectedId > 0)) {
      messageApi.warning(t('app.kuaizhizao.warehouseInbound.field.selectWarehouse'));
      return;
    }
    setBatchWhApplying(true);
    try {
      handleBatchApplyWarehouse(batchWhSelectedId, batchWhSelectedName);
      setBatchWhModalOpen(false);
      setBatchWhSelectedId(undefined);
      setBatchWhSelectedName(undefined);
    } finally {
      setBatchWhApplying(false);
    }
  };

  useEffect(() => {
    if (!(Number.isFinite(poId) && poId > 0)) {
      messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.purchase.invalidPo'));
      leavePage();
    }
  }, [poId, leavePage, messageApi]);

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
    if (!Number.isFinite(poId) || poId <= 0 || initRef.current) return;
    initRef.current = true;
    void (async () => {
      setLoading(true);
      try {
        const detailRaw = await getPurchaseOrder(poId);
        let detail = normalizePurchaseOrderDetail(detailRaw);
        const items = getOutstandingPoItems(detail);
        if (!items.length) {
          messageApi.warning(t('app.kuaizhizao.warehouseInbound.entry.purchase.allReceived'));
          leavePage();
          return;
        }
        const materialById = await prefetchMaterialsForUnitSelect(items.map((it) => it.material_id));
        detail = {
          ...detail,
          items: enrichPurchaseOrderItemsMaterial(detail.items || [], materialById),
        };
        const enrichedOutstanding = getOutstandingPoItems(detail);
        const qtyMap: Record<number, number> = {};
        enrichedOutstanding.forEach((it) => {
          if (it.id != null) qtyMap[it.id] = getPoItemReceivableMax(it);
        });
        const headerWh =
          (detail as PurchaseOrder & { warehouse_id?: number }).warehouse_id != null
          && Number((detail as PurchaseOrder & { warehouse_id?: number }).warehouse_id) > 0
            ? Number((detail as PurchaseOrder & { warehouse_id?: number }).warehouse_id)
            : undefined;
        const whMap: Record<number, number> = {};
        enrichedOutstanding.forEach((it) => {
          if (it.id == null) return;
          let rowWh: number | undefined;
          if (it.material_id) {
            const material = materialById.get(String(it.material_id));
            const defWhs = material?.defaults?.defaultWarehouses;
            if (defWhs?.length) {
              const sorted = [...defWhs].sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999));
              if (sorted[0]?.warehouseId > 0) rowWh = sorted[0].warehouseId;
            }
          }
          if (rowWh == null) rowWh = headerWh;
          if (rowWh != null) whMap[it.id] = rowWh;
        });
        setOrder(detail);
        let mergedQuantities = sanitizePullEntryLineQuantities(qtyMap);
        setLineWh(whMap);
        const whValues = [...new Set(Object.values(whMap))];
        if (whValues.length) {
          const refOpts = await loadPullWarehouseReferenceOptions(PURCHASE_INBOUND_WH_HOST);
          const nameByWhId: Record<number, string> = {};
          refOpts.forEach((w) => {
            nameByWhId[w.value] = w.label;
          });
          setWarehouseNameByWhId(nameByWhId);
          const lineNames: Record<number, string> = {};
          enrichedOutstanding.forEach((it) => {
            if (it.id == null || whMap[it.id] == null) return;
            const label = nameByWhId[whMap[it.id]];
            if (label) lineNames[it.id] = label;
          });
          setLineWhName(lineNames);
        }
        if (whValues.length === 1) setDefaultWarehouseId(whValues[0]);
        setPreviewLoading(true);
        void pushPurchaseOrderToReceiptPreview(poId, qtyMap)
          .then((preview) => {
            const batchMap: Record<number, string> = {};
            (preview.items || []).forEach((it: { item_id: number; batch_number?: string }) => {
              if (it.batch_number) batchMap[it.item_id] = it.batch_number;
            });
            setBatchNumbers(batchMap);
          })
          .catch(() => {
            /* 批号预览失败时可手工填写 */
          })
          .finally(() => setPreviewLoading(false));
        try {
          const meta = await loadConfirmPreviewMaterialMeta(enrichedOutstanding);
          setMaterialMeta(meta);
        } catch {
          /* 物料属性加载失败不阻断录入 */
        }
        let receiptFromDraft: Dayjs | undefined;
        applyDraftOnce((draft) => {
          if (draft.quantities) {
            mergedQuantities = mergeRecordMaps(
              mergedQuantities,
              sanitizePullEntryLineQuantities(draft.quantities as Record<string, unknown>),
            );
          }
          if (draft.batchNumbers) {
            setBatchNumbers((prev) => mergeRecordMaps(prev, draft.batchNumbers as Record<number, string>));
          }
          if (draft.lineWh) {
            setLineWh((prev) => mergeRecordMaps(prev, draft.lineWh as Record<number, number>));
          }
          if (draft.lineLoc) {
            setLineLoc((prev) => ({ ...prev, ...(draft.lineLoc as Record<number, number | undefined>) }));
          }
          if (draft.lineLocCode) {
            setLineLocCode((prev) => mergeRecordMaps(prev, draft.lineLocCode as Record<number, string>));
          }
          if (draft.serials) {
            setSerials((prev) => ({ ...prev, ...(draft.serials as Record<number, string[]>) }));
          }
          const whId = draftOptionalNumber(draft.defaultWarehouseId);
          if (whId != null) setDefaultWarehouseId(whId);
          if (draft.receiptTime != null && draft.receiptTime !== '') {
            const parsed = coerceFormDate(draft.receiptTime);
            if (parsed?.isValid() && parsed.year() >= MIN_INBOUND_RECEIPT_YEAR) {
              receiptFromDraft = parsed.startOf('day');
            }
          }
          if (typeof draft.deliveryNote === 'string') setDeliveryNote(draft.deliveryNote);
          if (typeof draft.receiptNotes === 'string') setReceiptNotes(draft.receiptNotes);
          receiverHook.restoreReceiver({
            uuid: typeof draft.receiverUuid === 'string' ? draft.receiverUuid : undefined,
            name: typeof draft.receiverName === 'string' ? draft.receiverName : undefined,
          });
        });
        setQuantities(sanitizePullEntryLineQuantities(mergedQuantities));
        setReceiptTime(receiptFromDraft ?? resolveInboundReceiptDate(undefined));
      } catch (e: unknown) {
        messageApi.error((e as Error)?.message || t('app.kuaizhizao.warehouseInbound.entry.purchase.loadFailed'));
        leavePage();
      } finally {
        setLoading(false);
      }
    })();
  }, [poId, leavePage, messageApi, applyDraftOnce, receiverHook.restoreReceiver]);

  const handleGenerateBatch = useCallback(
    async (poItemId: number) => {
      const meta = materialMeta[poItemId];
      if (!isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged) || !meta?.materialUuid) {
        messageApi.warning(t('app.kuaizhizao.warehouseOtherInbound.msg.selectMaterialFirst'));
        return;
      }
      setGeneratingBatchId(poItemId);
      try {
        const res = await materialBatchApi.generate(meta.materialUuid, {
          ruleId: meta.defaultBatchRuleId ?? undefined,
        });
        setBatchNumbers((prev) => ({ ...prev, [poItemId]: res.batch_no }));
        messageApi.success(t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerated'));
      } catch (e: unknown) {
        messageApi.error(
          (e as Error)?.message || t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerateFailed'),
        );
      } finally {
        setGeneratingBatchId(null);
      }
    },
    [materialMeta, messageApi, t, trackingFlags],
  );

  const handleGenerateSerial = async (poItemId: number, qty: number) => {
    const meta = materialMeta[poItemId];
    if (!isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged) || !meta?.materialUuid) return;
    const count = Math.max(1, Math.floor(Number(qty) || 1));
    if (count > MATERIAL_SERIAL_GENERATE_MAX_COUNT) {
      messageApi.warning(
        t('app.kuaizhizao.warehouseInbound.msg.serialMax100', {
          max: MATERIAL_SERIAL_GENERATE_MAX_COUNT,
        }),
      );
      return;
    }
    setGeneratingSerialId(poItemId);
    try {
      const res = await materialSerialApi.generate(meta.materialUuid, count, {
        ruleId: meta.defaultSerialRuleId ?? undefined,
      });
      setSerials((prev) => ({ ...prev, [poItemId]: res.serial_nos }));
      messageApi.success(t('app.kuaizhizao.warehouseInbound.msg.serialGenerated', { count: res.count }));
    } catch (e: unknown) {
      messageApi.error((e as Error)?.message || t('app.kuaizhizao.warehouseInbound.msg.serialGenerateFailed'));
    } finally {
      setGeneratingSerialId(null);
    }
  };

  const buildPoComposePayload = (): PurchaseReceiptPoComposePayload => {
    const lineSerials: Record<number, string[]> = {};
    outstandingItems.forEach((it) => {
      if (it.id == null || (quantities[it.id] ?? 0) <= 0) return;
      const sn = serials[it.id];
      if (sn?.length) lineSerials[it.id] = sn;
    });
    return {
      purchaseOrderId: Number(order!.id),
      quantities: { ...quantities },
      batchNumbers: { ...batchNumbers },
      lineWh: { ...lineWh },
      lineLoc: { ...lineLoc },
      lineLocCode: { ...lineLocCode },
      lineSerials,
      defaultWarehouseId: defaultWarehouseId ?? undefined,
      receiptTimeIso:
        receiptTime?.isValid() ? toApiBusinessDocumentDateTime(receiptTime) : undefined,
      receiverId: receiverHook.receiverId ?? undefined,
      receiverName: receiverHook.receiverName.trim() || undefined,
      deliveryNote: deliveryNote.trim() || undefined,
      notes: receiptNotes.trim() || undefined,
      attachments: normalizeDocumentAttachments(receiptAttachments),
    };
  };

  const submitToEditModal = async () => {
    if (!order?.id) return;
    let hasPositiveQty = false;
    for (const it of outstandingItems) {
      if (it.id == null) continue;
      const qty = quantities[it.id] ?? 0;
      const max = getPoItemReceivableMax(it);
      if (qty <= 0) continue;
      hasPositiveQty = true;
      if (qty > max) {
        messageApi.error(
          t('app.kuaizhizao.warehouseInbound.entry.purchase.qtyExceedsOutstanding', {
            material: it.material_code || it.material_name,
            max,
          }),
        );
        return;
      }
      const wh = lineWh[it.id];
      if (wh == null || !(wh > 0)) {
        messageApi.error(
          t('app.kuaizhizao.warehouseInbound.msg.selectWarehouseForMaterial', {
            material: it.material_code || it.material_name || '-',
          }),
        );
        return;
      }
      const locId = lineLoc[it.id];
      const locCode = lineLocCode[it.id];
      const needLoc = await lineLocationSelectionRequired(wh, locId, locCode);
      if (needLoc) {
        messageApi.error(
          t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', {
            material: it.material_code || it.material_name || '-',
          }),
        );
        return;
      }
      const rid = it.id;
      const materialLabel = it.material_code || it.material_name || '-';
      const meta = materialMeta[rid];
      if (isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) {
        if (!String(batchNumbers[rid] ?? '').trim()) {
          messageApi.error(
            t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
              material: materialLabel,
              batches: '—',
            }),
          );
          return;
        }
      }
      if (isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) {
        const serialList = (serials[rid] ?? []).map((s) => String(s).trim()).filter(Boolean);
        const expected = Math.floor(qty);
        if (serialList.length !== expected) {
          messageApi.error(
            t('app.kuaizhizao.warehouseOutbound.entry.serialCountMismatch', {
              material: materialLabel,
              required: expected,
              actual: serialList.length,
            }),
          );
          return;
        }
      }
    }
    if (!hasPositiveQty) {
      messageApi.warning(t('app.kuaizhizao.warehouseInbound.entry.purchase.fillReceiptQty'));
      return;
    }
    setSubmitting(true);
    try {
      clearDraft();
      navigateLeavingPullEntry(
        navigate,
        purchaseReceiptCreatePath(PURCHASE_INBOUND_LIST_PATH),
        pullEntryTabKey(location.pathname, location.search),
        { purchaseReceiptPoCompose: buildPoComposePayload() },
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleDefaultWarehouseChange = (warehouseId: number, warehouseName?: string) => {
    setDefaultWarehouseId(warehouseId);
    const lineIds = outstandingItems.filter((it) => it.id != null).map((it) => it.id!);
    applyLineWarehouse(lineIds, warehouseId, warehouseName);
  };

  const entryColumns = useMemo(
    () =>
      filterWarehouseTrackingColumns(
        [
      {
        title: t('app.kuaizhizao.warehouseInbound.col.materialCode'),
        dataIndex: 'material_code',
        width: 120,
        ellipsis: true,
        render: (v: unknown, record: PurchaseOrderItem) => String(v || record.material_code || '—'),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.materialName'),
        dataIndex: 'material_name',
        width: 150,
        ellipsis: true,
        render: (v: unknown, record: PurchaseOrderItem) => String(v || record.material_name || '—'),
      },
      { title: t('app.kuaizhizao.warehouseInbound.col.purchaseQty'), dataIndex: 'ordered_quantity', width: 100, align: 'right' as const , render: formatQuantity },
      { title: t('app.kuaizhizao.warehouseInbound.col.receivedQty'), dataIndex: 'received_quantity', width: 90, align: 'right' as const },
      { title: t('app.kuaizhizao.warehouseInbound.col.outstandingQty'), dataIndex: 'outstanding_quantity', width: 90, align: 'right' as const },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.maxReceivableQty'),
        key: 'max_receivable_quantity',
        width: 100,
        align: 'right' as const,
        render: (_: unknown, record: PurchaseOrderItem) => getPoItemReceivableMax(record),
      },
      {
        title: (
          <span>
            {t('app.kuaizhizao.warehouseInbound.col.warehouse')}
            <Button
              type="link"
              size="small"
              style={{ padding: '0 4px', height: 'auto' }}
              onClick={() => {
                setBatchWhSelectedId(undefined);
                setBatchWhModalOpen(true);
              }}
            >
              {t('app.kuaizhizao.warehouseInbound.action.batch')}
            </Button>
          </span>
        ),
        width: 150,
        render: (_: unknown, record: PurchaseOrderItem) => {
          if (record.id == null) return null;
          const rid = record.id;
          const materialId = Number(record.material_id ?? 0);
          return (
            <PurchaseInboundLineWarehouseCell
              materialId={materialId > 0 ? materialId : undefined}
              warehouseId={lineWh[rid]}
              placeholder={t('app.kuaizhizao.warehouseInbound.field.select')}
              onChange={(nv, wh) => {
                if (nv == null) return;
                applyLineWarehouse([rid], nv, wh?.name);
              }}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.location'),
        width: 150,
        render: (_: unknown, record: PurchaseOrderItem) => {
          if (record.id == null) return null;
          const rid = record.id;
          const wh = lineWh[rid];
          const materialId = Number(record.material_id ?? 0);
          return (
            <PurchaseInboundLineLocationCell
              materialId={materialId > 0 ? materialId : undefined}
              warehouseId={wh}
              locationId={lineLoc[rid]}
              selectWarehouseFirstPlaceholder={t('app.kuaizhizao.warehouseInbound.field.selectWarehouseFirst')}
              selectLocationPlaceholder={t('app.kuaizhizao.warehouseInbound.field.selectLocation')}
              onChange={(v, loc) => {
                setLineLoc((prev) => ({ ...prev, [rid]: v ?? undefined }));
                setLineLocCode((prev) => {
                  const next = { ...prev };
                  if (v == null) delete next[rid];
                  else next[rid] = loc?.code ?? '';
                  return next;
                });
              }}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.batchNo'),
        key: 'batch_number',
        width: 188,
        render: (_: unknown, record: PurchaseOrderItem) => {
          if (record.id == null) return '—';
          const rid = record.id;
          const meta = materialMeta[rid];
          if (!isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) return '—';
          if (previewLoading && !batchNumbers[rid]) return t('app.kuaizhizao.warehouseInbound.field.loading');
          return (
            <Space size={4} align="center">
              <Input
                placeholder={t('app.kuaizhizao.warehouseInbound.field.optional')}
                value={batchNumbers[rid] ?? ''}
                onChange={(e) => setBatchNumbers((prev) => ({ ...prev, [rid]: e.target.value }))}
                size={DOCUMENT_DETAIL_CONTROL_SIZE}
                allowClear
                style={{ width: 128 }}
              />
              <Tooltip title={t('app.kuaizhizao.warehouseInbound.action.generateBatchNo')}>
                <Button
                  type="text"
                  size="small"
                  icon={<ThunderboltOutlined />}
                  loading={generatingBatchId === rid}
                  aria-label={t('app.kuaizhizao.warehouseInbound.action.generateBatchNo')}
                  onClick={() => void handleGenerateBatch(rid)}
                  style={{ padding: 0, height: 'auto', color: 'var(--ant-color-text-tertiary)' }}
                />
              </Tooltip>
            </Space>
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.serialNo'),
        key: 'serial_numbers',
        width: 150,
        render: (_: unknown, record: PurchaseOrderItem) => {
          if (record.id == null) return '—';
          const rid = record.id;
          const meta = materialMeta[rid];
          if (!isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) return '—';
          const qty = Number(quantities[rid] ?? 0);
          return (
            <SerialNumbersImportTrigger
              serials={serials[rid] ?? []}
              expectedCount={qty > 0 ? qty : undefined}
              materialLabel={record.material_code || record.material_name}
              generateLoading={generatingSerialId === rid}
              onSerialsChange={(next) => setSerials((prev) => ({ ...prev, [rid]: next }))}
              onGenerate={
                qty > 0 && !previewLoading ? () => handleGenerateSerial(rid, qty) : undefined
              }
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.thisReceipt'),
        width: 130,
        align: 'right' as const,
        render: (_: unknown, record: PurchaseOrderItem) => {
          if (record.id == null) return null;
          const rid = record.id;
          const lineQty = sanitizePullEntryLineQuantities({ [rid]: quantities[rid] })[rid] ?? 0;
          return (
            <InputNumber
              min={0}
              max={getPoItemReceivableMax(record)}
              precision={4}
              value={lineQty}
              onChange={(v) => setQuantities((prev) => ({ ...prev, [rid]: Number(v) || 0 }))}
              style={{ width: 110 }}
            />
          );
        },
      },
        ],
        trackingFlags,
      ),
    [
      t,
      trackingFlags,
      applyLineWarehouse,
      batchNumbers,
      generatingBatchId,
      generatingSerialId,
      handleGenerateBatch,
      lineLoc,
      lineLocCode,
      lineWh,
      materialMeta,
      previewLoading,
      quantities,
      serials,
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
            <Button type="primary" loading={submitting} disabled={loading} onClick={() => void submitToEditModal()}>
              {t('app.kuaizhizao.warehouseInbound.action.continueToEditPurchaseReceipt')}
            </Button>
          </Space>
        </>
      }
    >
      <Spin spinning={loading}>
        <Card styles={{ body: { padding: PAGE_SPACING.PADDING } }}>
          <div className="form-modal-content-inner">
            {order && (
              <Form layout="vertical" requiredMark={false}>
                <Row gutter={16}>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.inboundType')}>
                      <ReadOnlyFormValue value={inboundReceiptTypeLabel(t, 'purchase')} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.sourceDocNo')}>
                      <ReadOnlyFormValue value={order.order_code} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.supplier')}>
                      <ReadOnlyFormValue value={order.supplier_name} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.buyer')}>
                      <ReadOnlyFormValue value={order.buyer_name} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.orderDate')}>
                      <ReadOnlyFormValue
                        value={order.order_date ? formatDateBySiteSetting(order.order_date) : undefined}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.requiredDeliveryDate')}>
                      <ReadOnlyFormValue
                        value={order.delivery_date ? formatDateBySiteSetting(order.delivery_date) : undefined}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.orderStatus')}>
                      <ReadOnlyFormValue value={reportDocumentStatusText(t, order.status)} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.currency')}>
                      <ReadOnlyFormValue value={order.currency} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.receiptDate')}>
                      <DatePicker
                        style={{ width: '100%' }}
                        value={receiptTime?.isValid() ? receiptTime : null}
                        onChange={(v) =>
                          setReceiptTime(v?.isValid() ? v.startOf('day') : dayjs().startOf('day'))
                        }
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <InboundEntryReceiverField hook={receiverHook} />
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.defaultWarehouse')}>
                      <PurchaseInboundLineWarehouseCell
                        warehouseId={defaultWarehouseId}
                        placeholder={t('app.kuaizhizao.warehouseInbound.field.applyToAllLines')}
                        onChange={(v, wh) => {
                          if (v != null) handleDefaultWarehouseChange(v, wh?.name);
                          else setDefaultWarehouseId(undefined);
                        }}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.deliveryNote')}>
                      <Input
                        placeholder={t('app.kuaizhizao.warehouseInbound.field.deliveryNotePlaceholder')}
                        value={deliveryNote}
                        onChange={(e) => setDeliveryNote(e.target.value)}
                        maxLength={100}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.supplierContact')}>
                      <ReadOnlyFormValue value={order.supplier_contact} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.contactPhone')}>
                      <ReadOnlyFormValue value={order.supplier_phone} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.totalQty')}>
                      <ReadOnlyFormValue value={totalReceiptQty.toLocaleString()} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.orderNotes')}>
                      <ReadOnlyFormValue value={order.notes} />
                    </Form.Item>
                  </Col>
                </Row>
              </Form>
            )}

            <div className="uni-table-detail" style={{ marginTop: PAGE_SPACING.BLOCK_GAP }}>
              <UniTableDetailHeader title={t('app.kuaizhizao.warehouseInbound.section.inboundDetails')} required />
              <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
              <div className="uni-table-detail-body">
                <div className="uni-table-detail-scroll">
                  <Table
                    className="uni-detail-table warehouse-detail-table"
                    size="small"
                    rowKey="id"
                    pagination={false}
                    scroll={{ x: 1280 }}
                    dataSource={outstandingItems}
                    columns={entryColumns}
                  />
                </div>
              </div>
            </div>

            {order && (
              <Form layout="vertical" requiredMark={false} style={{ marginTop: PAGE_SPACING.BLOCK_GAP }}>
                <InboundEntryAttachmentsSection
                  category="purchase_receipt_attachments"
                  fileList={receiptAttachments}
                  onChange={setReceiptAttachments}
                />
                <InboundEntryRemarksSection value={receiptNotes} onChange={setReceiptNotes} />
              </Form>
            )}
          </div>
        </Card>
      </Spin>

      <Modal
        title={t('app.kuaizhizao.warehouseInbound.entry.purchase.batchWarehouseTitle')}
        open={batchWhModalOpen}
        onCancel={() => {
          if (batchWhApplying) return;
          setBatchWhModalOpen(false);
          setBatchWhSelectedId(undefined);
        }}
        onOk={() => {
          void handleBatchWhModalConfirm();
        }}
        confirmLoading={batchWhApplying}
        okText={t('app.kuaizhizao.warehouseInbound.action.applyToAllLines')}
        cancelText={t('common.cancel')}
        width={MODAL_CONFIG.SMALL_WIDTH}
        destroyOnHidden
      >
        <PurchaseInboundLineWarehouseCell
          warehouseId={batchWhSelectedId}
          placeholder={t('app.kuaizhizao.warehouseInbound.field.selectWarehouse')}
          onChange={(v, wh) => {
            setBatchWhSelectedId(v);
            setBatchWhSelectedName(wh?.name);
          }}
        />
      </Modal>
    </DocumentFormPageLayout>
  );
};

export default InboundPoPullEntryPage;
