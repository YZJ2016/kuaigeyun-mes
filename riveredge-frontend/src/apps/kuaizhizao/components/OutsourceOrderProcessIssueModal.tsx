/**
 * 工序委外「工序发料」：按行确认出库仓、库位、批号与序列号后扣库并开工
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { App, Col, DatePicker, Form, Row, Spin, Typography } from 'antd';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import type { TFunction } from 'i18next';
import { FormModalTemplate, MODAL_CONFIG } from '../../../components/layout-templates';
import { PAGE_SPACING } from '../../../components/layout-templates/constants';
import { materialApi } from '../../master-data/services/material';
import type { Material } from '../../master-data/types/material';
import { resolvePrimaryDefaultWarehouseFromMaterial } from '../../master-data/utils/materialDefaultWarehouse';
import { warehouseApi as masterWarehouseApi } from '../../master-data/services/warehouse';
import { lineLocationSelectionRequired } from '../../../components/uni-wh-dropdown';
import { outsourceOrderApi } from '../services/production';
import { getApiErrorMessage } from '../../../utils/errorHandler';
import { toApiBusinessDocumentDateTime } from '../../../utils/formDate';
import { formatDateTimeBySiteSetting, formatQuantity } from '../../../utils/format';
import OutsourceIssueFormContent, {
  formatOutsourceIssueSupplierBrief,
  type OutsourceIssueLine,
  type OutsourceIssueWorkOrderBrief,
} from './OutsourceIssueFormContent';
import {
  OutboundEntryOperatorField,
  OutboundEntryRemarksSection,
  ReadOnlyFormValue,
  mapWarehouseSelectOptions,
  useOutboundOperatorSelect,
} from '../pages/warehouse-management/outbound/outboundEntryShared';
import {
  loadAvailableQtyByMaterialWarehouse,
  loadBatchOptionsByMaterialId,
  loadInStockSerialOptions,
  type InventoryPickOption,
} from '../pages/warehouse-management/outbound/outboundConfirmInventoryOptions';
import { isValidOutboundBatchAllocations } from '../pages/warehouse-management/outbound/outboundBatchAllocation';
import {
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
  type WarehouseTrackingFlags,
} from '../pages/warehouse-management/shared/warehouseTrackingFlags';
import {
  loadConfirmPreviewMaterialMeta,
  type ConfirmPreviewMaterialMeta,
} from '../pages/warehouse-management/inbound/inboundItemTracking';
import type { OutsourceOrderProgressRecord } from './OutsourceOrderProgressKit';

type Props = {
  open: boolean;
  record: OutsourceOrderProgressRecord | null;
  onClose: () => void;
  onSaved: (record: OutsourceOrderProgressRecord) => void;
  t: TFunction;
};

function mapPreviewLines(
  raw: Record<string, unknown>[],
  outsourceQty: number,
  suggestedBatchQty: number,
): OutsourceIssueLine[] {
  return raw.map((line) => {
    const materialId = Number(line.materialId ?? line.material_id);
    const pending = Number(line.pendingQuantity ?? line.pending_quantity ?? 0);
    const required = Number(line.requiredQuantity ?? line.required_quantity ?? 0);
    const perUnit = outsourceQty > 0 ? required / outsourceQty : 0;
    const batchNeed = perUnit * suggestedBatchQty;
    const issueDefault =
      pending > 0 && suggestedBatchQty > 0
        ? Math.min(pending, batchNeed)
        : pending > 0
          ? pending
          : 0;
    return {
      key: materialId,
      materialId,
      materialCode: String(line.materialCode ?? line.material_code ?? ''),
      materialName: String(line.materialName ?? line.material_name ?? ''),
      unit: String(line.unit ?? ''),
      requiredQuantity: required,
      issuedQuantity: Number(line.issuedQuantity ?? line.issued_quantity ?? 0),
      pendingQuantity: pending,
      availableQuantity: 0,
      issueQuantity: issueDefault,
      serialNumbers: [],
    };
  });
}

async function attachDefaultWarehousesToLines(lines: OutsourceIssueLine[]): Promise<{
  lines: OutsourceIssueLine[];
  materialsById: Map<number, Material>;
}> {
  const ids = [...new Set(lines.map((line) => line.materialId).filter((id) => Number.isFinite(id) && id > 0))];
  const materialsById = new Map<number, Material>();
  if (!ids.length) {
    return { lines, materialsById };
  }
  const res = await materialApi.list({ ids, limit: ids.length });
  for (const m of res.items ?? []) {
    if (m.id != null) materialsById.set(Number(m.id), m);
  }
  const withWarehouse = lines.map((line) => {
    const material = materialsById.get(line.materialId);
    const wh = material ? resolvePrimaryDefaultWarehouseFromMaterial(material) : null;
    if (!wh) return line;
    return { ...line, warehouseId: wh.id };
  });
  return { lines: withWarehouse, materialsById };
}

/** 按出库仓分组批量拉批号选项，避免每行一次库存查询 */
async function prefetchBatchOptionsForLines(
  lines: OutsourceIssueLine[],
  meta: Record<number, ConfirmPreviewMaterialMeta>,
  trackingFlags: WarehouseTrackingFlags,
): Promise<Record<number, InventoryPickOption[]>> {
  const byWarehouse = new Map<number, Set<number>>();
  for (const line of lines) {
    const whId = Number(line.warehouseId ?? 0);
    const materialMeta = meta[line.materialId];
    if (
      whId > 0 &&
      materialMeta &&
      isMaterialBatchEntryEnabled(trackingFlags, materialMeta.batchManaged)
    ) {
      let mids = byWarehouse.get(whId);
      if (!mids) {
        mids = new Set();
        byWarehouse.set(whId, mids);
      }
      mids.add(line.materialId);
    }
  }
  if (!byWarehouse.size) return {};
  const maps = await Promise.all(
    [...byWarehouse.entries()].map(async ([warehouseId, materialIds]) =>
      loadBatchOptionsByMaterialId([...materialIds], warehouseId),
    ),
  );
  return Object.assign({}, ...maps) as Record<number, InventoryPickOption[]>;
}

function formatPlannedDateLabel(value: string | null | undefined): string {
  if (!value) return '-';
  return formatDateTimeBySiteSetting(value);
}

export function OutsourceOrderProcessIssueModal({ open, record, onClose, onSaved, t }: Props) {
  const { message: messageApi, modal: modalApi } = App.useApp();
  const trackingFlags = useWarehouseTrackingFlags();
  const operatorHook = useOutboundOperatorSelect();
  const [loading, setLoading] = useState(false);
  const [issueLines, setIssueLines] = useState<OutsourceIssueLine[]>([]);
  const [previewMessage, setPreviewMessage] = useState<string | null>(null);
  const [allowManualLines, setAllowManualLines] = useState(true);
  const [workOrderBrief, setWorkOrderBrief] = useState<OutsourceIssueWorkOrderBrief>({});
  const [notes, setNotes] = useState('');
  const [issueTime, setIssueTime] = useState<Dayjs | null>(null);
  const [lineMaterialMeta, setLineMaterialMeta] = useState<Record<number, ConfirmPreviewMaterialMeta>>({});
  const [batchOptionsByMaterialId, setBatchOptionsByMaterialId] = useState<
    Record<number, InventoryPickOption[]>
  >({});
  const [batchLoadingMaterialId, setBatchLoadingMaterialId] = useState<number | null>(null);
  const [serialOptionsByMaterialId, setSerialOptionsByMaterialId] = useState<
    Record<number, InventoryPickOption[]>
  >({});
  const [serialLoadingMaterialId, setSerialLoadingMaterialId] = useState<number | null>(null);
  const [warehouseOptions, setWarehouseOptions] = useState<
    ReturnType<typeof mapWarehouseSelectOptions>
  >([]);
  const [stockByMaterialWh, setStockByMaterialWh] = useState<Record<number, Record<number, number>>>(
    {},
  );
  const [stockByWhStatus, setStockByWhStatus] = useState<'idle' | 'loading' | 'ready'>('idle');

  const pickMaterialIdsKey = useMemo(
    () =>
      [
        ...new Set(
          issueLines
            .map((line) => line.materialId)
            .filter((id) => Number.isFinite(id) && id > 0),
        ),
      ]
        .sort((a, b) => a - b)
        .join(','),
    [issueLines],
  );

  const resetState = useCallback(() => {
    setIssueLines([]);
    setPreviewMessage(null);
    setNotes('');
    setIssueTime(null);
    setWorkOrderBrief({});
    setLineMaterialMeta({});
    setBatchOptionsByMaterialId({});
    setSerialOptionsByMaterialId({});
    setWarehouseOptions([]);
    setStockByMaterialWh({});
    setStockByWhStatus('idle');
  }, []);

  const ensureBatchOptionsForLine = useCallback(async (materialId: number, warehouseId: number) => {
    setBatchLoadingMaterialId(materialId);
    try {
      const map = await loadBatchOptionsByMaterialId([materialId], warehouseId);
      setBatchOptionsByMaterialId((prev) => ({ ...prev, ...map }));
    } finally {
      setBatchLoadingMaterialId(null);
    }
  }, []);

  const ensureSerialOptionsForLine = useCallback(
    async (materialId: number) => {
      const meta = lineMaterialMeta[materialId];
      if (!meta?.materialUuid) return;
      setSerialLoadingMaterialId(materialId);
      try {
        const opts = await loadInStockSerialOptions(meta.materialUuid);
        setSerialOptionsByMaterialId((prev) => ({ ...prev, [materialId]: opts }));
      } finally {
        setSerialLoadingMaterialId(null);
      }
    },
    [lineMaterialMeta],
  );

  useEffect(() => {
    if (!open || record?.id == null) {
      resetState();
      return;
    }
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const [preview, whRes] = await Promise.all([
          outsourceOrderApi.issuePreview(String(record.id)),
          masterWarehouseApi.list({ is_active: true, limit: 500 }),
        ]);
        if (cancelled) return;
        setWarehouseOptions(mapWarehouseSelectOptions(whRes));
        setPreviewMessage(preview?.message ?? null);
        setAllowManualLines(preview?.allow_manual_lines !== false);
        const previewRec = preview as Record<string, unknown> | null | undefined;
        setWorkOrderBrief({
          code: String(preview?.outsource_order_code ?? record.code ?? ''),
          product_name: String(preview?.product_name ?? ''),
          quantity: Number(preview?.quantity ?? record.outsource_quantity ?? 0),
          supplier_code: String(previewRec?.supplier_code ?? ''),
          supplier_name: String(previewRec?.supplier_name ?? ''),
          planned_start_date: (previewRec?.planned_start_date as string | null | undefined) ?? undefined,
          planned_end_date: (previewRec?.planned_end_date as string | null | undefined) ?? undefined,
        });
        const outQty = Number(preview?.quantity ?? record.outsource_quantity ?? 0);
        const suggestedBatch = Number(
          (preview as Record<string, unknown> | null | undefined)?.suggested_batch_quantity ?? 0,
        );
        const mapped = mapPreviewLines(
          (preview?.lines ?? []) as Record<string, unknown>[],
          outQty,
          suggestedBatch,
        );
        const { lines: withWarehouse, materialsById } = await attachDefaultWarehousesToLines(mapped);
        const materialById = new Map<string, Material>();
        for (const [mid, material] of materialsById) {
          materialById.set(String(mid), material);
        }
        const meta = await loadConfirmPreviewMaterialMeta(
          withWarehouse.map((line) => ({
            id: line.materialId,
            material_id: line.materialId,
            material_code: line.materialCode,
          })),
          materialById,
        );
        const batchMap = await prefetchBatchOptionsForLines(withWarehouse, meta, trackingFlags);
        if (cancelled) return;
        setLineMaterialMeta(meta);
        setBatchOptionsByMaterialId(batchMap);
        setIssueLines(withWarehouse);
        setIssueTime(dayjs().startOf('day'));
      } catch (error: unknown) {
        if (!cancelled) {
          modalApi.error({
            title: t('common.loadFailed'),
            content: getApiErrorMessage(error, t('app.kuaizhizao.outsourceOrder.processIssueFailed')),
          });
          onClose();
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ensureBatchOptionsForLine, modalApi, onClose, open, record?.code, record?.id, record?.outsource_quantity, resetState, t, trackingFlags]);

  useEffect(() => {
    if (!open) return;
    const missing = issueLines
      .map((line) => line.materialId)
      .filter((id) => Number.isFinite(id) && id > 0 && !lineMaterialMeta[id]);
    if (!missing.length) return;
    let cancelled = false;
    void loadConfirmPreviewMaterialMeta(
      missing.map((materialId) => {
        const line = issueLines.find((l) => l.materialId === materialId);
        return {
          id: materialId,
          material_id: materialId,
          material_code: line?.materialCode ?? '',
        };
      }),
    ).then((meta) => {
      if (!cancelled) {
        setLineMaterialMeta((prev) => ({ ...prev, ...meta }));
      }
    });
    return () => {
      cancelled = true;
    };
  }, [issueLines, lineMaterialMeta, open]);

  useEffect(() => {
    if (!open) return;
    const mids = pickMaterialIdsKey
      .split(',')
      .map((s) => Number(s))
      .filter((id) => Number.isFinite(id) && id > 0);
    if (!mids.length) {
      setStockByMaterialWh({});
      setStockByWhStatus('idle');
      return;
    }
    let cancelled = false;
    setStockByWhStatus('loading');
    void loadAvailableQtyByMaterialWarehouse(mids)
      .then((map) => {
        if (!cancelled) {
          setStockByMaterialWh(map);
          setStockByWhStatus('ready');
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStockByMaterialWh({});
          setStockByWhStatus('idle');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open, pickMaterialIdsKey]);

  useEffect(() => {
    if (!open || stockByWhStatus !== 'ready') return;
    setIssueLines((prev) =>
      prev.map((line) => {
        const whId = Number(line.warehouseId ?? 0);
        if (!(whId > 0)) return line;
        const available = Number(stockByMaterialWh[line.materialId]?.[whId] ?? 0);
        if (available === line.availableQuantity) return line;
        return { ...line, availableQuantity: available };
      }),
    );
  }, [open, stockByMaterialWh, stockByWhStatus]);

  const handleBatchSetWarehouse = useCallback(
    (warehouseId: number) => {
      if (!(warehouseId > 0) || !issueLines.length) return;
      setIssueLines((prev) =>
        prev.map((line) => {
          const available =
            stockByWhStatus === 'ready'
              ? Number(stockByMaterialWh[line.materialId]?.[warehouseId] ?? 0)
              : line.availableQuantity;
          return {
            ...line,
            warehouseId,
            availableQuantity: available,
            locationId: undefined,
            locationCode: undefined,
            batchNumber: undefined,
            batchAllocations: [],
          };
        }),
      );
      messageApi.success(
        t('app.kuaizhizao.warehouseOutbound.entry.batchWarehouseApplied', { count: issueLines.length }),
      );
    },
    [issueLines.length, messageApi, stockByMaterialWh, stockByWhStatus, t],
  );

  const handleFinish = useCallback(async () => {
    if (record?.id == null) return;
    const activeLines = issueLines.filter((line) => line.issueQuantity > 0);
    if (!activeLines.length) {
      messageApi.warning(t('app.kuaizhizao.warehouseOutbound.entry.fillIssueQty'));
      return;
    }

    for (const line of activeLines) {
      const materialLabel = line.materialName || line.materialCode || String(line.materialId);
      const whId = Number(line.warehouseId ?? 0);
      const meta = lineMaterialMeta[line.materialId];

      if (!(whId > 0)) {
        messageApi.error(
          t('app.kuaizhizao.warehouseOutbound.msg.selectLineWarehouse', { material: materialLabel }),
        );
        return;
      }
      const whOpt = warehouseOptions.find((o) => o.value === whId);
      if (!whOpt) {
        messageApi.error(
          t('app.kuaizhizao.warehouseOutbound.msg.selectLineWarehouse', { material: materialLabel }),
        );
        return;
      }
      const needLoc = await lineLocationSelectionRequired(whId, line.locationId, line.locationCode);
      if (needLoc) {
        messageApi.error(
          t('app.kuaizhizao.warehouseOutbound.msg.selectLocationForMaterial', { material: materialLabel }),
        );
        return;
      }

      if (isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) {
        const opts = batchOptionsByMaterialId[line.materialId] ?? [];
        const allocs = (line.batchAllocations ?? []).filter(
          (a) => String(a.batchNo).trim() && Number(a.quantity) > 0,
        );
        const fromSingle =
          !allocs.length && String(line.batchNumber ?? '').trim()
            ? [{ batchNo: String(line.batchNumber).trim(), quantity: line.issueQuantity }]
            : allocs;
        if (!isValidOutboundBatchAllocations(fromSingle, opts, line.issueQuantity)) {
          messageApi.error(
            t('app.kuaizhizao.warehouseOutbound.confirm.batchAllocationRequired', {
              material: materialLabel,
              qty: line.issueQuantity,
              batches: opts.map((o) => o.value).join('、') || '—',
            }),
          );
          return;
        }
      }

      if (isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) {
        const sns = (line.serialNumbers ?? []).map((s) => String(s).trim()).filter(Boolean);
        const qty = Number(line.issueQuantity);
        if (qty > 0 && sns.length !== qty) {
          messageApi.error(
            t('app.kuaizhizao.workOrder.msgSerialManualCountMismatch', {
              count: sns.length,
              qty,
            }),
          );
          return;
        }
      }
    }

    try {
      await outsourceOrderApi.issueBatch(record.id, {
        outsource_order_id: record.id,
        outsource_order_code: String(record.code ?? workOrderBrief.code ?? ''),
        ...(issueTime?.isValid() ? { issued_at: toApiBusinessDocumentDateTime(issueTime) } : {}),
        issued_by: operatorHook.receiverId,
        issued_by_name: operatorHook.receiverName.trim() || undefined,
        remarks: notes.trim() || undefined,
        lines: activeLines.flatMap((line) => {
          const whId = Number(line.warehouseId);
          const whOpt = warehouseOptions.find((o) => o.value === whId)!;
          const base = {
            material_id: line.materialId,
            material_code: line.materialCode,
            material_name: line.materialName,
            unit: line.unit,
            warehouse_id: whId,
            warehouse_name: whOpt.name,
            location_id: line.locationId,
            location_name: line.locationCode?.trim() || undefined,
          };
          const serials = (line.serialNumbers ?? []).map((s) => String(s).trim()).filter(Boolean);
          const allocs = (line.batchAllocations ?? []).filter(
            (a) => String(a.batchNo).trim() && Number(a.quantity) > 0,
          );
          if (allocs.length > 1) {
            return allocs.map((a, index) => ({
              ...base,
              quantity: a.quantity,
              batch_number: a.batchNo,
              serial_numbers:
                serials.length > index ? [serials[index]] : serials.length === 1 ? serials : undefined,
            }));
          }
          return [
            {
              ...base,
              quantity: line.issueQuantity,
              batch_number: allocs[0]?.batchNo || line.batchNumber?.trim() || undefined,
              serial_numbers: serials.length ? serials : undefined,
            },
          ];
        }),
      });
      const refreshed = await outsourceOrderApi.get(String(record.id));
      onSaved(refreshed as OutsourceOrderProgressRecord);
      onClose();
    } catch (error: unknown) {
      messageApi.error(getApiErrorMessage(error, t('app.kuaizhizao.outsourceOrder.processIssueFailed')));
      throw error;
    }
  }, [
    batchOptionsByMaterialId,
    issueLines,
    issueTime,
    lineMaterialMeta,
    messageApi,
    notes,
    onClose,
    onSaved,
    operatorHook.receiverId,
    operatorHook.receiverName,
    record,
    t,
    trackingFlags,
    warehouseOptions,
    workOrderBrief.code,
  ]);

  const plannedStart = workOrderBrief.planned_start_date ?? workOrderBrief.plannedStartDate ?? null;
  const plannedEnd = workOrderBrief.planned_end_date ?? workOrderBrief.plannedEndDate ?? null;

  return (
    <FormModalTemplate
      title={t('app.kuaizhizao.outsourceOrder.processIssueModalTitle', {
        code: record?.code ?? '',
      })}
      open={open}
      onClose={onClose}
      onFinish={handleFinish}
      width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
      grid={false}
      loading={loading}
      submitText={t('common.confirm')}
    >
      <Spin spinning={loading}>
        <Row gutter={16}>
          <Col xs={24} sm={12} lg={8}>
            <Form.Item label={t('app.kuaizhizao.warehouseOutbound.entry.outsourceCode')}>
              <ReadOnlyFormValue value={workOrderBrief.code ?? '-'} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Form.Item label={t('app.kuaizhizao.outsourceOrder.fieldSupplier')}>
              <ReadOnlyFormValue value={formatOutsourceIssueSupplierBrief(workOrderBrief)} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Form.Item label={t('app.kuaizhizao.warehouseOutbound.entry.product')}>
              <ReadOnlyFormValue
                value={workOrderBrief.productName || workOrderBrief.product_name || '-'}
              />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Form.Item label={t('app.kuaizhizao.outsourceWorkOrder.outsourceQty')}>
              <ReadOnlyFormValue
                value={workOrderBrief.quantity != null ? formatQuantity(workOrderBrief.quantity) : '-'}
              />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Form.Item label={t('app.kuaizhizao.outsourceOrder.fieldPlannedStart')}>
              <ReadOnlyFormValue value={formatPlannedDateLabel(plannedStart)} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Form.Item label={t('app.kuaizhizao.outsourceOrder.fieldPlannedEnd')}>
              <ReadOnlyFormValue value={formatPlannedDateLabel(plannedEnd)} />
            </Form.Item>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <OutboundEntryOperatorField hook={operatorHook} />
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Form.Item label={t('app.kuaizhizao.warehouseOutbound.field.documentDate')}>
              <DatePicker
                value={issueTime}
                onChange={(v) => setIssueTime(v ? v.startOf('day') : null)}
                style={{ width: '100%' }}
                placeholder={t('app.kuaizhizao.warehouseOutbound.field.documentDate')}
              />
            </Form.Item>
          </Col>
        </Row>
        <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
          {t('app.kuaizhizao.outsourceOrder.processIssueBatchHint')}
        </Typography.Text>
        <OutsourceIssueFormContent
          workOrder={workOrderBrief}
          hideWorkOrderInfo
          lines={issueLines}
          onLinesChange={setIssueLines}
          allowManualLines={allowManualLines}
          previewMessage={previewMessage}
          warehouseOptions={warehouseOptions}
          stockByMaterialWh={stockByMaterialWh}
          stockByWhStatus={stockByWhStatus}
          onBatchSetWarehouse={handleBatchSetWarehouse}
          trackingFlags={trackingFlags}
          lineMaterialMeta={lineMaterialMeta}
          batchOptionsByMaterialId={batchOptionsByMaterialId}
          batchLoadingMaterialId={batchLoadingMaterialId}
          onEnsureBatchOptions={ensureBatchOptionsForLine}
          serialOptionsByMaterialId={serialOptionsByMaterialId}
          serialLoadingMaterialId={serialLoadingMaterialId}
          onEnsureSerialOptions={ensureSerialOptionsForLine}
        />
        <Row gutter={16} style={{ marginTop: PAGE_SPACING.BLOCK_GAP }}>
          <Col span={24}>
            <OutboundEntryRemarksSection value={notes} onChange={setNotes} />
          </Col>
        </Row>
      </Spin>
    </FormModalTemplate>
  );
}