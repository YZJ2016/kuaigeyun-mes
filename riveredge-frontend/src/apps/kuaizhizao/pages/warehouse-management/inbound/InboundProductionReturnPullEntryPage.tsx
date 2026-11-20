/**
 * 从生产工单取单开生产退料入库 — 独立 Tab 页
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { App, Button, Card, Col, DatePicker, Form, Input, InputNumber, Modal, Row, Select, Space, Spin, Table, Typography } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { type Dayjs } from 'dayjs';
import {
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageLayout,
  PAGE_SPACING,
  WAREHOUSE_DETAIL_TABLE_STYLES,
} from '../../../../../components/layout-templates';
import { UniTableDetailHeader } from '../../../../../components/uni-table-detail/UniTableDetail';
import { workOrderApi } from '../../../services/production';
import { warehouseApi } from '../../../services/warehouse-execution';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { setCustomPageTitle, removeCustomPageTitle } from '../../../../../utils/customPageTitle';
import { translateWorkOrderLifecycleStatus } from '../../../utils/workOrderLifecycle';
import {
  InboundEntryReceiverField,
  InboundEntryRemarksSection,
  ReadOnlyFormValue,
  useInboundReceiverSelect,
} from './inboundEntryShared';
import { inboundReceiptTypeLabel } from './inboundHubTypes';
import { INBOUND_LIST_PATH, inboundProductionReturnEntryPath } from './inboundPaths';
import {
  draftDayjs,
  draftOptionalNumber,
  usePullEntryFormDraft,
} from '../shared/pullEntryFormDraft';
import { navigateLeavingPullEntry, pullEntryTabKey } from '../shared/pullEntryCloseTab';
import { resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import {
  MaterialUnitSelect,
  fetchMaterialForUnitSelectCache,
} from '../../../../../components/material-unit-select';
import { recalculateQuantityOnUnitChange } from '../../../../../components/quantity-with-unit/formHelpers';
import { formatQuantityWithUnit } from '../../../../../utils/materialUnitDisplay';
import { toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';
import {
  PurchaseInboundLineLocationCell,
  PurchaseInboundLineWarehouseCell,
} from './PurchaseInboundLineWhCells';
import { lineLocationSelectionRequired } from '../../../../../components/uni-wh-dropdown';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import {
  enrichInboundFormItemsTracking,
  loadConfirmPreviewMaterialMeta,
  type ConfirmPreviewMaterialMeta,
} from './inboundItemTracking';
import { materialBatchApi } from '../../../../master-data/services/material';

type PreviewPicking = {
  picking_id: number;
  picking_code: string;
  status: string;
  lines: Array<{
    picking_item_id?: number;
    material_id?: number;
    material_code?: string;
    material_name?: string;
    material_spec?: string;
    material_unit?: string;
    source_doc_quantity?: number;
    source_received_quantity?: number;
    source_pending_quantity?: number;
    warehouse_id?: number;
    warehouse_name?: string;
  }>;
};

type ReturnLine = {
  key: number;
  picking_item_id?: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_spec?: string;
  material_unit?: string;
  picked_quantity: number;
  return_quantity: number;
  warehouse_id?: number;
  warehouse_name?: string;
  location_id?: number;
  location_code?: string;
  batch_number?: string;
  batch_managed?: boolean;
  material_uuid?: string;
};

const InboundProductionReturnPullEntryPage: React.FC = () => {
  const { workOrderId: woIdParam } = useParams<{ workOrderId: string }>();
  const workOrderId = Number(woIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const { message: messageApi } = App.useApp();
  const { t } = useTranslation();
  const pullFromProductionReturnAction = resolveKuaizhizaoDocumentAction(t, 'inbound.pull_from_work_order_for_production_return');
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const receiverHook = useInboundReceiverSelect();
  const trackingFlags = useWarehouseTrackingFlags();
  const [lineMaterialMeta, setLineMaterialMeta] = useState<Record<number, ConfirmPreviewMaterialMeta>>({});
  const [generatingBatchKey, setGeneratingBatchKey] = useState<number | null>(null);
  const initRef = useRef(false);

  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [workOrder, setWorkOrder] = useState<Record<string, unknown> | null>(null);
  const [previewPickings, setPreviewPickings] = useState<PreviewPicking[]>([]);
  const [pickingId, setPickingId] = useState<number | null>(null);
  const [pickingCode, setPickingCode] = useState('');
  const [lines, setLines] = useState<ReturnLine[]>([]);
  const [returnTime, setReturnTime] = useState<Dayjs | null>(null);
  const [returnNotes, setReturnNotes] = useState('');
  const [batchWhModalOpen, setBatchWhModalOpen] = useState(false);
  const [batchWhSelectedId, setBatchWhSelectedId] = useState<number | undefined>();
  const [batchWhSelectedName, setBatchWhSelectedName] = useState<string | undefined>();
  const [batchWhApplying, setBatchWhApplying] = useState(false);
  const { bindSnapshot, persistNow, clearDraft, applyDraftOnce } = usePullEntryFormDraft(
    'kuaizhizao:inbound-production-return-pull',
  );

  const pagePath =
    Number.isFinite(workOrderId) && workOrderId > 0
      ? inboundProductionReturnEntryPath(workOrderId)
      : INBOUND_LIST_PATH;
  const woCode = String(workOrder?.code || workOrderId || '');
  const pageTitle = woCode
    ? `${pullFromProductionReturnAction.label} — ${woCode}`
    : pullFromProductionReturnAction.label;

  const pickingOptions = useMemo(
    () =>
      previewPickings.map((picking) => ({
        value: picking.picking_id,
        label: `${picking.picking_code} - ${picking.status}`,
      })),
    [previewPickings],
  );

  const totalReturnQty = useMemo(
    () => lines.reduce((sum, it) => sum + Number(it.return_quantity ?? 0), 0),
    [lines],
  );

  const leavePage = useCallback(() => {
    clearDraft();
    navigateLeavingPullEntry(
      navigate,
      INBOUND_LIST_PATH,
      pullEntryTabKey(location.pathname, location.search),
    );
  }, [clearDraft, navigate, location.pathname, location.search]);

  const applyLineWarehouse = useCallback(
    (lineKeys: number[], warehouseId: number, warehouseName?: string) => {
      if (!lineKeys.length || !(warehouseId > 0)) return;
      const name = String(warehouseName ?? '').trim();
      setLines((prev) =>
        prev.map((row) =>
          lineKeys.includes(row.key)
            ? {
                ...row,
                warehouse_id: warehouseId,
                warehouse_name: name || row.warehouse_name,
                location_id: undefined,
                location_code: undefined,
              }
            : row,
        ),
      );
    },
    [],
  );

  const applyPickingSelection = useCallback(
    (
      nextPickingId: number | null,
      qtyByItemId?: Record<number, number>,
      pickingsSource?: PreviewPicking[],
      draftLineWh?: Record<number, number>,
      draftLineWhName?: Record<number, string>,
    ) => {
      setPickingId(nextPickingId);
      const source = pickingsSource ?? previewPickings;
      const picking = source.find((row) => row.picking_id === nextPickingId);
      setPickingCode(picking?.picking_code || '');
      const nextLines = (picking?.lines || [])
        .filter((line) => Number(line.source_pending_quantity ?? 0) > 0)
        .map((line, idx) => {
          const key = Number(line.picking_item_id ?? idx);
          const draftWh = draftLineWh?.[key];
          const previewWh =
            line.warehouse_id != null && Number(line.warehouse_id) > 0
              ? Number(line.warehouse_id)
              : undefined;
          const warehouseId = draftWh != null && draftWh > 0 ? draftWh : previewWh;
          const warehouseName =
            (draftWh != null && draftWh > 0
              ? String(draftLineWhName?.[key] ?? '').trim()
              : '') ||
            String(line.warehouse_name ?? '').trim() ||
            undefined;
          return {
            key,
            picking_item_id: line.picking_item_id != null ? Number(line.picking_item_id) : undefined,
            material_id: line.material_id != null ? Number(line.material_id) : undefined,
            material_code: String(line.material_code ?? ''),
            material_name: String(line.material_name ?? ''),
            material_spec: line.material_spec ? String(line.material_spec) : undefined,
            material_unit: String(line.material_unit || '个'),
            picked_quantity: Number(line.source_pending_quantity ?? 0),
            return_quantity: 0,
            warehouse_id: warehouseId,
            warehouse_name: warehouseName,
          };
        });
      const qtyApplied = qtyByItemId
        ? nextLines.map((row) =>
            qtyByItemId[row.key] != null
              ? { ...row, return_quantity: Number(qtyByItemId[row.key]) }
              : row,
          )
        : nextLines;
      void (async () => {
        const enriched = (await enrichInboundFormItemsTracking(
          qtyApplied as unknown as Record<string, unknown>[],
        )) as ReturnLine[];
        const withKeys = enriched.map((row, idx) => ({
          ...row,
          key: qtyApplied[idx]?.key ?? row.key,
          picking_item_id: qtyApplied[idx]?.picking_item_id,
          picked_quantity: qtyApplied[idx]?.picked_quantity ?? row.picked_quantity,
          return_quantity: qtyApplied[idx]?.return_quantity ?? row.return_quantity,
          warehouse_id: qtyApplied[idx]?.warehouse_id ?? row.warehouse_id,
          warehouse_name: qtyApplied[idx]?.warehouse_name ?? row.warehouse_name,
          material_uuid: String(row.material_uuid ?? enriched[idx]?.material_uuid ?? ''),
        }));
        setLines(withKeys);
        setLineMaterialMeta(await loadConfirmPreviewMaterialMeta(withKeys, new Map()));
      })();
    },
    [previewPickings],
  );

  useEffect(() => {
    bindSnapshot(() => ({
      pickingId,
      lineReturnQty: Object.fromEntries(lines.map((row) => [row.key, row.return_quantity])),
      lineWh: Object.fromEntries(
        lines
          .filter((row) => row.warehouse_id != null && row.warehouse_id > 0)
          .map((row) => [row.key, Number(row.warehouse_id)]),
      ),
      lineWhName: Object.fromEntries(
        lines
          .filter((row) => row.warehouse_id != null && row.warehouse_id > 0)
          .map((row) => [row.key, String(row.warehouse_name ?? '')]),
      ),
      returnTime,
      returnNotes,
      receiverUuid: receiverHook.receiverUuid,
      receiverName: receiverHook.receiverName,
    }));
    persistNow();
  }, [
    pickingId,
    lines,
    returnTime,
    returnNotes,
    receiverHook.receiverUuid,
    receiverHook.receiverName,
    bindSnapshot,
    persistNow,
  ]);

  useEffect(() => {
    if (!(Number.isFinite(workOrderId) && workOrderId > 0)) {
      messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.workOrder.invalid'));
      leavePage();
    }
  }, [workOrderId, leavePage, messageApi, t]);

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
    if (!Number.isFinite(workOrderId) || workOrderId <= 0 || initRef.current) return;
    initRef.current = true;
    void (async () => {
      setLoading(true);
      try {
        const [woRaw, previewRaw] = await Promise.all([
          workOrderApi.get(String(workOrderId)),
          warehouseApi.productionReturn.previewFromWorkOrder(workOrderId),
        ]);
        const preview = previewRaw as { pickings?: PreviewPicking[]; message?: string };
        const pickings = Array.isArray(preview.pickings) ? preview.pickings : [];
        if (!pickings.length) {
          messageApi.warning(preview.message || t('app.kuaizhizao.warehouseInbound.entry.productionReturn.noReturnLines'));
          leavePage();
          return;
        }
        setWorkOrder(woRaw as Record<string, unknown>);
        setPreviewPickings(pickings);
        applyDraftOnce((draft) => {
          if (draft.returnTime) {
            const parsed = draftDayjs(draft.returnTime);
            setReturnTime(parsed?.isValid() ? parsed.startOf('day') : null);
          }
          if (typeof draft.returnNotes === 'string') setReturnNotes(draft.returnNotes);
          receiverHook.restoreReceiver({
            uuid: typeof draft.receiverUuid === 'string' ? draft.receiverUuid : undefined,
            name: typeof draft.receiverName === 'string' ? draft.receiverName : undefined,
          });
          const draftPickingId = draftOptionalNumber(draft.pickingId);
          const qtyByItemId = draft.lineReturnQty as Record<number, number> | undefined;
          const draftLineWh = draft.lineWh as Record<number, number> | undefined;
          const draftLineWhName = draft.lineWhName as Record<number, string> | undefined;
          // 旧草稿仅有表头 warehouseId：作为各行缺省仓（行级草稿优先）
          const legacyHeaderWh = draftOptionalNumber(draft.warehouseId);
          const resolveLineWh = (key: number, previewWh?: number) => {
            const fromDraft = draftLineWh?.[key];
            if (fromDraft != null && fromDraft > 0) return fromDraft;
            if (previewWh != null && previewWh > 0) return previewWh;
            return legacyHeaderWh ?? undefined;
          };
          const patchedPickings = pickings.map((picking) => ({
            ...picking,
            lines: (picking.lines || []).map((line, idx) => {
              const key = Number(line.picking_item_id ?? idx);
              const previewWh =
                line.warehouse_id != null && Number(line.warehouse_id) > 0
                  ? Number(line.warehouse_id)
                  : undefined;
              const whId = resolveLineWh(key, previewWh);
              const whName =
                (draftLineWh?.[key] != null
                  ? String(draftLineWhName?.[key] ?? '').trim()
                  : '') ||
                String(line.warehouse_name ?? '').trim() ||
                undefined;
              return {
                ...line,
                warehouse_id: whId,
                warehouse_name: whName,
              };
            }),
          }));
          if (draftPickingId != null) {
            applyPickingSelection(draftPickingId, qtyByItemId, patchedPickings);
          } else {
            const firstPicking = patchedPickings.find((picking) =>
              (picking.lines || []).some((line) => Number(line.source_pending_quantity ?? 0) > 0),
            );
            applyPickingSelection(firstPicking?.picking_id ?? null, undefined, patchedPickings);
          }
        });
      } catch (e: unknown) {
        messageApi.error((e as Error)?.message || t('app.kuaizhizao.warehouseInbound.entry.workOrder.loadFailed'));
        leavePage();
      } finally {
        setLoading(false);
      }
    })();
  }, [
    workOrderId,
    leavePage,
    messageApi,
    t,
    applyDraftOnce,
    receiverHook.restoreReceiver,
    applyPickingSelection,
  ]);

  const handleBatchWhModalConfirm = () => {
    if (batchWhSelectedId == null || !(batchWhSelectedId > 0)) {
      messageApi.warning(t('app.kuaizhizao.warehouseInbound.field.selectWarehouse'));
      return;
    }
    const keys = lines.map((row) => row.key);
    if (!keys.length) {
      messageApi.warning(t('app.kuaizhizao.warehouseInbound.msg.noLinesToSetWarehouse'));
      return;
    }
    setBatchWhApplying(true);
    try {
      applyLineWarehouse(keys, batchWhSelectedId, batchWhSelectedName);
      messageApi.success(
        t('app.kuaizhizao.warehouseInbound.msg.batchWarehouseApplied', { count: keys.length }),
      );
      setBatchWhModalOpen(false);
      setBatchWhSelectedId(undefined);
      setBatchWhSelectedName(undefined);
    } finally {
      setBatchWhApplying(false);
    }
  };

  const submit = async (mode: 'draft' | 'confirm') => {
    if (!pickingId) {
      messageApi.warning(t('app.kuaizhizao.warehouseInbound.entry.productionReturn.selectPicking'));
      return;
    }

    const activeLines = lines.filter((it) => it.return_quantity > 0);
    if (!activeLines.length) {
      messageApi.warning(t('app.kuaizhizao.warehouseInbound.entry.productionReturn.fillReturnQty'));
      return;
    }
    for (const it of activeLines) {
      if (it.return_quantity > it.picked_quantity) {
        messageApi.error(
          t('app.kuaizhizao.warehouseInbound.entry.productionReturn.qtyExceedsPicked', {
            material: it.material_code || it.material_name,
            max: it.picked_quantity,
          }),
        );
        return;
      }
      const materialLabel = it.material_code || it.material_name || '-';
      const lineWhId = Number(it.warehouse_id ?? 0);
      if (!(lineWhId > 0)) {
        messageApi.error(
          t('app.kuaizhizao.warehouseInbound.msg.selectWarehouseForMaterial', {
            material: materialLabel,
          }),
        );
        return;
      }
      const needLoc = await lineLocationSelectionRequired(
        lineWhId,
        it.location_id,
        it.location_code,
      );
      if (needLoc) {
        messageApi.error(
          t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', { material: materialLabel }),
        );
        return;
      }
      const meta = lineMaterialMeta[it.key];
      if (isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) {
        if (!String(it.batch_number ?? '').trim()) {
          messageApi.error(
            t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
              material: materialLabel,
              batches: '—',
            }),
          );
          return;
        }
      }
    }

    // 表头仓仍为接口必填：取首行有效仓作单据默认展示仓；过账以明细行为准
    const headerWhId = Number(activeLines[0]?.warehouse_id ?? 0);
    const headerWhName = String(activeLines[0]?.warehouse_name ?? '').trim() || String(headerWhId);

    setSubmitting(true);
    try {
      const created = (await warehouseApi.productionReturn.create({
        work_order_id: workOrderId,
        work_order_code: woCode,
        picking_id: pickingId,
        picking_code: pickingCode || undefined,
        warehouse_id: headerWhId,
        warehouse_name: headerWhName,
        return_time: returnTime?.isValid() ? toApiBusinessDocumentDateTime(returnTime) : undefined,
        returner_id: receiverHook.receiverId,
        returner_name: receiverHook.receiverName.trim() || undefined,
        notes: returnNotes.trim() || undefined,
        items: activeLines.map((it) => ({
          picking_item_id: it.picking_item_id,
          material_id: it.material_id,
          material_code: it.material_code || '',
          material_name: it.material_name || '',
          material_spec: it.material_spec || undefined,
          material_unit: it.material_unit || '个',
          return_quantity: it.return_quantity,
          warehouse_id: Number(it.warehouse_id),
          warehouse_name: String(it.warehouse_name ?? '').trim() || String(it.warehouse_id),
          location_id:
            it.location_id != null && Number(it.location_id) > 0 ? Number(it.location_id) : undefined,
          location_code: String(it.location_code ?? '').trim() || undefined,
          batch_number: String(it.batch_number ?? '').trim() || undefined,
        })),
      })) as { id?: number; return_code?: string };
      if (created?.id == null) {
        messageApi.error(t('app.kuaizhizao.warehouseInbound.entry.productionReturn.noReturnId'));
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
            inboundDirectConfirm: {
              id: Number(created.id),
              receipt_type: 'production_return',
            },
          },
        );
      } else {
        messageApi.success(
          t('app.kuaizhizao.warehouseInbound.entry.productionReturn.draftCreated', {
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
      {
        title: t('common.unit'),
        dataIndex: 'material_unit',
        width: 88,
        align: 'center' as const,
        render: (_: unknown, record: ReturnLine) =>
          record.material_id ? (
            <MaterialUnitSelect
              materialId={record.material_id}
              value={record.material_unit}
              size="small"
              noStyle
              onChange={(newUnit) => {
                void (async () => {
                  const material = await fetchMaterialForUnitSelectCache(record.material_id!);
                  setLines((prev) =>
                    prev.map((row) => {
                      if (row.key !== record.key) return row;
                      const convert = (qty: number) =>
                        recalculateQuantityOnUnitChange({
                          material,
                          currentQuantity: qty,
                          oldUnit: row.material_unit,
                          newUnit,
                        });
                      return {
                        ...row,
                        material_unit: newUnit,
                        picked_quantity: convert(row.picked_quantity),
                        return_quantity: convert(row.return_quantity),
                      };
                    }),
                  );
                })();
              }}
            />
          ) : (
            record.material_unit || '—'
          ),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.returnableQty'),
        dataIndex: 'picked_quantity',
        width: 100,
        align: 'right' as const,
        render: (v: number, record: ReturnLine) => formatQuantityWithUnit(v, record.material_unit),
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.thisReturn'),
        width: 130,
        align: 'right' as const,
        render: (_: unknown, record: ReturnLine) => (
          <InputNumber
            min={0}
            max={record.picked_quantity}
            precision={4}
            value={record.return_quantity}
            onChange={(v) => {
              const qty = Number(v) || 0;
              setLines((prev) =>
                prev.map((row) =>
                  row.key === record.key ? { ...row, return_quantity: qty } : row,
                ),
              );
            }}
            style={{ width: 110 }}
          />
        ),
      },
      {
        title: (
          <span>
            {t('app.kuaizhizao.warehouseInbound.field.returnWarehouse')}
            <Button
              type="link"
              size="small"
              style={{ padding: '0 4px', height: 'auto' }}
              onClick={() => {
                setBatchWhSelectedId(undefined);
                setBatchWhSelectedName(undefined);
                setBatchWhModalOpen(true);
              }}
            >
              {t('app.kuaizhizao.warehouseInbound.action.batch')}
            </Button>
          </span>
        ),
        width: 168,
        render: (_: unknown, record: ReturnLine) => {
          const materialId = Number(record.material_id ?? 0);
          return (
            <PurchaseInboundLineWarehouseCell
              materialId={materialId > 0 ? materialId : undefined}
              warehouseId={record.warehouse_id}
              placeholder={t('app.kuaizhizao.warehouseInbound.field.selectReturnWarehouse')}
              onChange={(nv, wh) => {
                if (nv == null) return;
                applyLineWarehouse([record.key], nv, wh?.name);
              }}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.location'),
        width: 150,
        render: (_: unknown, record: ReturnLine) => {
          const lineWhId = Number(record.warehouse_id ?? 0);
          if (!(lineWhId > 0)) {
            return t('app.kuaizhizao.warehouseInbound.field.selectWarehouseFirst');
          }
          const materialId = Number(record.material_id ?? 0);
          return (
            <PurchaseInboundLineLocationCell
              materialId={materialId > 0 ? materialId : undefined}
              warehouseId={lineWhId}
              locationId={record.location_id}
              selectWarehouseFirstPlaceholder={t('app.kuaizhizao.warehouseInbound.field.selectWarehouseFirst')}
              selectLocationPlaceholder={t('app.kuaizhizao.warehouseInbound.field.selectLocation')}
              onChange={(v, loc) => {
                setLines((prev) =>
                  prev.map((row) =>
                    row.key === record.key
                      ? {
                          ...row,
                          location_id: v ?? undefined,
                          location_code: loc?.code ?? '',
                        }
                      : row,
                  ),
                );
              }}
            />
          );
        },
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.batchNo'),
        width: 130,
        render: (_: unknown, record: ReturnLine) => {
          const meta = lineMaterialMeta[record.key];
          if (!isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) return '—';
          return (
            <Space size={2}>
              <Input
                size="small"
                style={{ width: 96 }}
                value={record.batch_number ?? ''}
                onChange={(e) => {
                  const v = e.target.value;
                  setLines((prev) =>
                    prev.map((row) => (row.key === record.key ? { ...row, batch_number: v } : row)),
                  );
                }}
              />
              <Button
                type="link"
                size="small"
                icon={<ThunderboltOutlined />}
                loading={generatingBatchKey === record.key}
                style={{ padding: 0 }}
                onClick={() => {
                  const uuid = record.material_uuid || meta?.materialUuid;
                  if (!uuid) return;
                  setGeneratingBatchKey(record.key);
                  void materialBatchApi
                    .generate(uuid, {})
                    .then((res) => {
                      setLines((prev) =>
                        prev.map((row) =>
                          row.key === record.key ? { ...row, batch_number: res.batch_no } : row,
                        ),
                      );
                      messageApi.success(t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerated'));
                    })
                    .catch((e: Error) => {
                      messageApi.error(
                        e?.message || t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerateFailed'),
                      );
                    })
                    .finally(() => setGeneratingBatchKey(null));
                }}
              />
            </Space>
          );
        },
      },
    ],
        trackingFlags,
      ),
    [applyLineWarehouse, generatingBatchKey, lineMaterialMeta, messageApi, t, trackingFlags],
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
            <Button
              type="primary"
              loading={submitting}
              disabled={loading}
              onClick={() => void submit('confirm')}
            >
              {t('app.kuaizhizao.warehouseInbound.action.confirmInbound')}
            </Button>
          </Space>
        </>
      }
    >
      <Spin spinning={loading}>
        <Card styles={{ body: { padding: PAGE_SPACING.PADDING } }}>
          <div className="form-modal-content-inner">
            {workOrder && (
              <Form layout="vertical" requiredMark={false}>
                <Row gutter={16}>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.inboundType')}>
                      <ReadOnlyFormValue value={inboundReceiptTypeLabel(t, 'production_return')} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.workOrderCode')}>
                      <ReadOnlyFormValue value={woCode} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.product')}>
                      <ReadOnlyFormValue
                        value={workOrder.product_name ? String(workOrder.product_name) : undefined}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.workOrderStatus')}>
                      <ReadOnlyFormValue value={translateWorkOrderLifecycleStatus(t, workOrder.status)} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.picking')} required>
                      <Select
                        placeholder={t('app.kuaizhizao.warehouseInbound.field.selectPicking')}
                        showSearch
                        style={{ width: '100%' }}
                        value={pickingId ?? undefined}
                        options={pickingOptions}
                        filterOption={(input, opt) =>
                          (opt?.label ?? '').toString().toLowerCase().includes((input ?? '').toLowerCase())
                        }
                        onChange={(v) => {
                          applyPickingSelection(v ? Number(v) : null);
                        }}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <Form.Item label={t('app.kuaizhizao.warehouseInbound.field.returnDate')}>
                      <DatePicker
                        style={{ width: '100%' }}
                        value={returnTime}
                        onChange={(v) => setReturnTime(v ? v.startOf('day') : null)}
                      />
                    </Form.Item>
                  </Col>
                  <Col xs={24} sm={12} lg={6}>
                    <InboundEntryReceiverField label={t('app.kuaizhizao.warehouseInbound.field.returner')} hook={receiverHook} />
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
                <UniTableDetailHeader title={t('app.kuaizhizao.warehouseInbound.section.returnDetails')} required />
                <style>{WAREHOUSE_DETAIL_TABLE_STYLES}</style>
                <div className="uni-table-detail-body">
                  <div className="uni-table-detail-scroll">
                    <Table
                      className="uni-detail-table warehouse-detail-table"
                      size="small"
                      rowKey="key"
                      pagination={false}
                      scroll={{ x: 1180 }}
                      dataSource={lines}
                      columns={entryColumns}
                    />
                  </div>
                </div>
              </div>
            )}

            {workOrder && (
              <Form layout="vertical" requiredMark={false} style={{ marginTop: PAGE_SPACING.BLOCK_GAP }}>
                <InboundEntryRemarksSection
                  value={returnNotes}
                  onChange={setReturnNotes}
                  label={t('app.kuaizhizao.warehouseInbound.field.returnRemarks')}
                  placeholder={t('app.kuaizhizao.warehouseInbound.field.returnRemarksPlaceholder')}
                />
              </Form>
            )}
          </div>
        </Card>
      </Spin>
      <Modal
        title={t('app.kuaizhizao.warehouseInbound.entry.productionReturn.batchWarehouseTitle')}
        open={batchWhModalOpen}
        confirmLoading={batchWhApplying}
        okText={t('app.kuaizhizao.warehouseInbound.action.applyToAllLines')}
        cancelText={t('common.cancel')}
        onCancel={() => {
          if (batchWhApplying) return;
          setBatchWhModalOpen(false);
          setBatchWhSelectedId(undefined);
          setBatchWhSelectedName(undefined);
        }}
        onOk={() => handleBatchWhModalConfirm()}
        destroyOnHidden
      >
        <PurchaseInboundLineWarehouseCell
          warehouseId={batchWhSelectedId}
          placeholder={t('app.kuaizhizao.warehouseInbound.field.selectReturnWarehouse')}
          onChange={(v, wh) => {
            setBatchWhSelectedId(v);
            setBatchWhSelectedName(wh?.name);
          }}
        />
      </Modal>
    </DocumentFormPageLayout>
  );
};

export default InboundProductionReturnPullEntryPage;
