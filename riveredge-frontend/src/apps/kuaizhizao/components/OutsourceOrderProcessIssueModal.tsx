/**
 * 工序委外「工序发料」：确认发料数量后按物料默认仓库扣库并开工
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Col, DatePicker, Form, Modal, Row, Spin, Typography } from 'antd';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import type { TFunction } from 'i18next';
import { MODAL_CONFIG } from '../../../components/layout-templates';
import { PAGE_SPACING } from '../../../components/layout-templates/constants';
import { materialApi } from '../../master-data/services/material';
import type { Material } from '../../master-data/types/material';
import { resolvePrimaryDefaultWarehouseFromMaterial } from '../../master-data/utils/materialDefaultWarehouse';
import { outsourceOrderApi } from '../services/production';
import { getApiErrorMessage } from '../../../utils/errorHandler';
import { toApiBusinessDocumentDateTime } from '../../../utils/formDate';
import OutsourceIssueFormContent, {
  OutsourceIssueWorkOrderInfoPanel,
  type OutsourceIssueLine,
  type OutsourceIssueWorkOrderBrief,
} from './OutsourceIssueFormContent';
import {
  OutboundEntryOperatorField,
  OutboundEntryRemarksSection,
  useOutboundOperatorSelect,
} from '../pages/warehouse-management/outbound/outboundEntryShared';
import {
  loadBatchOptionsByMaterialId,
  loadInStockSerialOptions,
  type InventoryPickOption,
} from '../pages/warehouse-management/outbound/outboundConfirmInventoryOptions';
import { isValidOutboundBatchAllocations } from '../pages/warehouse-management/outbound/outboundBatchAllocation';
import {
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
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

function mapPreviewLines(raw: Record<string, unknown>[]): OutsourceIssueLine[] {
  return raw.map((line) => {
    const materialId = Number(line.materialId ?? line.material_id);
    const pending = Number(line.pendingQuantity ?? line.pending_quantity ?? 0);
    return {
      key: materialId,
      materialId,
      materialCode: String(line.materialCode ?? line.material_code ?? ''),
      materialName: String(line.materialName ?? line.material_name ?? ''),
      unit: String(line.unit ?? ''),
      requiredQuantity: Number(line.requiredQuantity ?? line.required_quantity ?? 0),
      issuedQuantity: Number(line.issuedQuantity ?? line.issued_quantity ?? 0),
      pendingQuantity: pending,
      availableQuantity: 0,
      issueQuantity: pending > 0 ? pending : 0,
      serialNumbers: [],
    };
  });
}

async function attachDefaultWarehousesToLines(lines: OutsourceIssueLine[]): Promise<OutsourceIssueLine[]> {
  const ids = [...new Set(lines.map((line) => line.materialId).filter((id) => Number.isFinite(id) && id > 0))];
  if (!ids.length) return lines;
  const res = await materialApi.list({ ids, limit: ids.length });
  const byId = new Map<number, Material>();
  for (const m of res.items ?? []) {
    if (m.id != null) byId.set(Number(m.id), m);
  }
  return lines.map((line) => {
    const material = byId.get(line.materialId);
    const wh = material ? resolvePrimaryDefaultWarehouseFromMaterial(material) : null;
    if (!wh) return line;
    return { ...line, warehouseId: wh.id };
  });
}

export function OutsourceOrderProcessIssueModal({ open, record, onClose, onSaved, t }: Props) {
  const trackingFlags = useWarehouseTrackingFlags();
  const operatorHook = useOutboundOperatorSelect();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
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

  const resetState = useCallback(() => {
    setIssueLines([]);
    setPreviewMessage(null);
    setNotes('');
    setIssueTime(null);
    setWorkOrderBrief({});
    setLineMaterialMeta({});
    setBatchOptionsByMaterialId({});
    setSerialOptionsByMaterialId({});
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
        const preview = await outsourceOrderApi.issuePreview(String(record.id));
        if (cancelled) return;
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
        const mapped = mapPreviewLines((preview?.lines ?? []) as Record<string, unknown>[]);
        const withWarehouse = await attachDefaultWarehousesToLines(mapped);
        const meta = await loadConfirmPreviewMaterialMeta(
          withWarehouse.map((line) => ({
            id: line.materialId,
            material_id: line.materialId,
            material_code: line.materialCode,
          })),
        );
        if (cancelled) return;
        setLineMaterialMeta(meta);
        setIssueLines(withWarehouse);
        setIssueTime(dayjs().startOf('day'));
        for (const line of withWarehouse) {
          const whId = Number(line.warehouseId ?? 0);
          const materialMeta = meta[line.materialId];
          if (whId > 0 && materialMeta && isMaterialBatchEntryEnabled(trackingFlags, materialMeta.batchManaged)) {
            void ensureBatchOptionsForLine(line.materialId, whId);
          }
        }
      } catch (error: unknown) {
        if (!cancelled) {
          Modal.error({
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
  }, [ensureBatchOptionsForLine, onClose, open, record?.code, record?.id, record?.outsource_quantity, resetState, t, trackingFlags]);

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

  const handleOk = async () => {
    if (record?.id == null) return;
    const activeLines = issueLines.filter((line) => line.issueQuantity > 0);
    if (!activeLines.length) {
      Modal.warning({ title: t('app.kuaizhizao.warehouseOutbound.entry.fillIssueQty') });
      return;
    }

    for (const line of activeLines) {
      const materialLabel = line.materialName || line.materialCode || String(line.materialId);
      const whId = Number(line.warehouseId ?? 0);
      const meta = lineMaterialMeta[line.materialId];

      if (isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) {
        if (!(whId > 0)) {
          Modal.error({
            content: t('app.kuaizhizao.warehouseOutbound.msg.selectLineWarehouse', { material: materialLabel }),
          });
          return;
        }
        const opts = batchOptionsByMaterialId[line.materialId] ?? [];
        const allocs = (line.batchAllocations ?? []).filter(
          (a) => String(a.batchNo).trim() && Number(a.quantity) > 0,
        );
        const fromSingle =
          !allocs.length && String(line.batchNumber ?? '').trim()
            ? [{ batchNo: String(line.batchNumber).trim(), quantity: line.issueQuantity }]
            : allocs;
        if (!isValidOutboundBatchAllocations(fromSingle, opts, line.issueQuantity)) {
          Modal.error({
            content: t('app.kuaizhizao.warehouseOutbound.confirm.batchAllocationRequired', {
              material: materialLabel,
              qty: line.issueQuantity,
              batches: opts.map((o) => o.value).join('、') || '—',
            }),
          });
          return;
        }
      }

      if (isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) {
        const sns = (line.serialNumbers ?? []).map((s) => String(s).trim()).filter(Boolean);
        const qty = Number(line.issueQuantity);
        if (qty > 0 && sns.length !== qty) {
          Modal.error({
            content: t('app.kuaizhizao.workOrder.msgSerialManualCountMismatch', {
              count: sns.length,
              qty,
            }),
          });
          return;
        }
      }
    }

    setSubmitting(true);
    try {
      await outsourceOrderApi.issueBatch(record.id, {
        outsource_order_id: record.id,
        outsource_order_code: String(record.code ?? workOrderBrief.code ?? ''),
        ...(issueTime?.isValid() ? { issued_at: toApiBusinessDocumentDateTime(issueTime) } : {}),
        issued_by: operatorHook.receiverId,
        issued_by_name: operatorHook.receiverName.trim() || undefined,
        remarks: notes.trim() || undefined,
        lines: activeLines.flatMap((line) => {
          const base = {
            material_id: line.materialId,
            material_code: line.materialCode,
            material_name: line.materialName,
            unit: line.unit,
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
      Modal.error({
        content: getApiErrorMessage(error, t('app.kuaizhizao.outsourceOrder.processIssueFailed')),
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      {...MODAL_CONFIG}
      width={MODAL_CONFIG.EXTRA_LARGE_WIDTH}
      title={t('app.kuaizhizao.outsourceOrder.processIssueModalTitle', {
        code: record?.code ?? '',
      })}
      open={open}
      onCancel={onClose}
      onOk={() => void handleOk()}
      confirmLoading={submitting}
      destroyOnHidden
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin />
        </div>
      ) : (
        <Form layout="vertical" requiredMark={false}>
          <OutsourceIssueWorkOrderInfoPanel
            workOrder={workOrderBrief}
            titleKey="app.kuaizhizao.outsourceOrder.processIssueOrderInfo"
            showSupplierAndPlanned
          />
          <Row gutter={16}>
            <Col span={24}>
              <Typography.Text type="secondary" style={{ display: 'block', marginBottom: PAGE_SPACING.BLOCK_GAP }}>
                {t('app.kuaizhizao.outsourceOrder.processIssueBatchHint')}
              </Typography.Text>
            </Col>
            <Col xs={24} sm={12}>
              <OutboundEntryOperatorField hook={operatorHook} />
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item label={t('app.kuaizhizao.warehouseOutbound.field.documentDate')}>
                <DatePicker
                  value={issueTime}
                  onChange={(v) => setIssueTime(v)}
                  style={{ width: '100%' }}
                  placeholder={t('app.kuaizhizao.warehouseOutbound.field.documentDate')}
                />
              </Form.Item>
            </Col>
          </Row>
          <OutsourceIssueFormContent
            workOrder={workOrderBrief}
            hideWorkOrderInfo
            issueLineDetailMode="quantity_only"
            lines={issueLines}
            onLinesChange={setIssueLines}
            allowManualLines={allowManualLines}
            previewMessage={previewMessage}
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
        </Form>
      )}
    </Modal>
  );
}