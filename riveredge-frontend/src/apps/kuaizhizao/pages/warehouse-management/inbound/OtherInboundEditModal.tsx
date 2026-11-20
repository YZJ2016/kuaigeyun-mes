/**
 * 其他入库编辑弹窗（入库 Hub 列表「编辑」）。
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Input, InputNumber, Select, Space, Table, Typography } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { SerialNumbersImportTrigger } from '../../../../../components/serial-numbers-import';
import { useWarehouseLocationOptions } from '../../../hooks/useWarehouseLocationOptions';
import { materialBatchApi, materialSerialApi, MATERIAL_SERIAL_GENERATE_MAX_COUNT } from '../../../../master-data/services/material';
import {
  FormModalTemplate,
  MODAL_CONFIG,
  WAREHOUSE_FORM_DETAIL_TABLE_FRAME_STYLES,
} from '../../../../../components/layout-templates';
import { warehouseApi } from '../../../services/production';
import { formatQuantity } from '../../../../../utils/format';
import { useNumericPrecisionPlaces } from '../../../../../hooks/useNumericPrecision';
import {
  appendWarehouseLineAmountColumns,
  KUAIZHIZAO_INBOUND_FIELD_RESOURCE,
} from '../shared/warehouseAmountDisplay';
import {
  isInboundEditable,
  inboundUpdateCapabilityReasonMessage,
  type InboundHubOrder,
} from './inboundHubTypes';
import { normalizeInboundHubDetail } from './inboundHubNormalize';
import { normalizeDocumentAttachments } from '../../../utils/documentAttachments';
import { computeSimpleDocumentLineTotal } from '../../../utils/documentLineAmounts';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import {
  enrichInboundFormItemsTracking,
  loadConfirmPreviewMaterialMeta,
  type ConfirmPreviewMaterialMeta,
} from './inboundItemTracking';

type OtherInboundLineItem = {
  id?: number;
  material_id?: number;
  material_code?: string;
  material_name?: string;
  material_unit?: string;
  inbound_quantity?: number;
  unit_price?: number;
  location_code?: string;
  batch_number?: string;
  serial_numbers?: string[];
  status?: string;
};

type OtherInboundDetail = InboundHubOrder & {
  inbound_code?: string;
  reason_type?: string;
  reason_desc?: string;
  warehouse_id?: number;
  warehouse_name?: string;
  review_status?: string;
  notes?: string;
  attachments?: unknown;
  items?: OtherInboundLineItem[];
};

export type OtherInboundEditModalProps = {
  open: boolean;
  record: { id?: number; receipt_type?: string } | null;
  onClose: () => void;
  onSuccess?: () => void;
};

export const OtherInboundEditModal: React.FC<OtherInboundEditModalProps> = ({
  open,
  record,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const quantityDecimals = useNumericPrecisionPlaces('quantity');
  const { message: messageApi } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState<OtherInboundDetail | null>(null);
  const [reasonDesc, setReasonDesc] = useState('');
  const [notes, setNotes] = useState('');
  const [editableQuantities, setEditableQuantities] = useState<Record<number, number>>({});
  const [editableUnitPrices, setEditableUnitPrices] = useState<Record<number, number>>({});
  const [editableLocations, setEditableLocations] = useState<Record<number, string>>({});
  const [editableBatches, setEditableBatches] = useState<Record<number, string>>({});
  const [editableSerials, setEditableSerials] = useState<Record<number, string[]>>({});
  const [lineMaterialMeta, setLineMaterialMeta] = useState<Record<number, ConfirmPreviewMaterialMeta>>({});
  const [generatingBatchRowId, setGeneratingBatchRowId] = useState<number | null>(null);
  const [generatingSerialRowId, setGeneratingSerialRowId] = useState<number | null>(null);
  const trackingFlags = useWarehouseTrackingFlags();
  const {
    locationOptions,
    updateSelectedWarehouseId,
    resetSelectedWarehouseId,
  } = useWarehouseLocationOptions();

  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const loadKey =
    open && record?.id && record.receipt_type === 'other_inbound' ? String(record.id) : null;

  const resetState = useCallback(() => {
    setDetail(null);
    setReasonDesc('');
    setNotes('');
    setEditableQuantities({});
    setEditableUnitPrices({});
    setEditableLocations({});
    setEditableBatches({});
    setEditableSerials({});
    setLineMaterialMeta({});
    resetSelectedWarehouseId();
  }, [resetSelectedWarehouseId]);

  useEffect(() => {
    if (!open) {
      resetState();
      setLoading(false);
    }
  }, [open, resetState]);

  useEffect(() => {
    if (!loadKey) return;

    let cancelled = false;
    setLoading(true);
    setDetail(null);

    void (async () => {
      try {
        const detailData = (await warehouseApi.otherInbound.get(loadKey)) as OtherInboundDetail;
        const merged = normalizeInboundHubDetail(
          'other_inbound',
          detailData as Record<string, unknown>,
          { id: Number(loadKey), receipt_type: 'other_inbound' },
        ) as OtherInboundDetail;
        if (cancelled) return;
        if (!isInboundEditable(merged)) {
          messageApi.warning(
            inboundUpdateCapabilityReasonMessage(merged, t) || t('common.saveFailed'),
          );
          onCloseRef.current();
          return;
        }
        const enrichedItems = await enrichInboundFormItemsTracking(
          (detailData.items ?? merged.items ?? []) as Record<string, unknown>[],
        );
        setDetail({ ...merged, ...detailData, items: enrichedItems as OtherInboundLineItem[] });
        if (detailData.warehouse_id != null) {
          updateSelectedWarehouseId(detailData.warehouse_id);
        }
        setReasonDesc(String(detailData.reason_desc ?? '').trim());
        setNotes(String(detailData.notes ?? '').trim());
        const qtyMap: Record<number, number> = {};
        const priceMap: Record<number, number> = {};
        const locMap: Record<number, string> = {};
        const batchMap: Record<number, string> = {};
        const serialMap: Record<number, string[]> = {};
        enrichedItems.forEach((it) => {
          if (it?.id == null) return;
          const rid = Number(it.id);
          qtyMap[rid] = Number(it.inbound_quantity ?? 0);
          priceMap[rid] = Number(it.unit_price ?? 0);
          locMap[rid] = String(it.location_code ?? '').trim();
          batchMap[rid] = String(it.batch_number ?? '').trim();
          serialMap[rid] = Array.isArray(it.serial_numbers)
            ? it.serial_numbers.map((s) => String(s).trim()).filter(Boolean)
            : [];
        });
        setEditableQuantities(qtyMap);
        setEditableUnitPrices(priceMap);
        setEditableLocations(locMap);
        setEditableBatches(batchMap);
        setEditableSerials(serialMap);
        const meta = await loadConfirmPreviewMaterialMeta(enrichedItems, new Map());
        setLineMaterialMeta(meta);
      } catch (e: unknown) {
        if (cancelled) return;
        const err = e as { message?: string };
        messageApi.error(err?.message || t('app.kuaizhizao.warehouseInbound.msg.loadDetailFailed'));
        onCloseRef.current();
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [loadKey, messageApi, t, updateSelectedWarehouseId]);

  const handleClose = () => {
    resetState();
    onClose();
  };

  const handleSubmit = async () => {
    if (!detail?.id) return;
    const items = detail.items || [];
    if (!items.length) {
      messageApi.warning(t('app.kuaizhizao.warehouseInbound.msg.noEditableLines'));
      return;
    }
    if (!detail.reason_type || !detail.warehouse_id || !detail.warehouse_name) {
      messageApi.error(t('common.saveFailed'));
      return;
    }

    const mappedItems = items
      .filter((it) => it.material_id != null)
      .map((it) => {
        const rowId = Number(it.id);
        const qty = Number(editableQuantities[rowId] ?? it.inbound_quantity ?? 0);
        if (!(qty > 0)) {
          throw new Error(
            t('app.kuaizhizao.warehouseInbound.msg.actualQtyMustBePositive', {
              material: it.material_code || it.material_name || '-',
            }),
          );
        }
        const unitPrice = Number(editableUnitPrices[rowId] ?? it.unit_price ?? 0);
        const locationCode = String(editableLocations[rowId] ?? it.location_code ?? '').trim();
        if (!locationCode) {
          throw new Error(
            t('app.kuaizhizao.warehouseInbound.msg.selectLocationForMaterial', {
              material: it.material_code || it.material_name || '-',
            }),
          );
        }
        const meta = lineMaterialMeta[rowId];
        const batchStr = String(editableBatches[rowId] ?? it.batch_number ?? '').trim();
        if (isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged) && !batchStr) {
          throw new Error(
            t('app.kuaizhizao.warehouseOutbound.confirm.batchRequired', {
              material: it.material_code || it.material_name || '-',
              batches: '—',
            }),
          );
        }
        const serialList = editableSerials[rowId] ?? [];
        if (isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) {
          if (serialList.length !== qty) {
            throw new Error(
              t('app.kuaizhizao.warehouseOutbound.confirm.serialCountMismatch', {
                material: it.material_code || it.material_name || '-',
                expected: qty,
                actual: serialList.length,
              }),
            );
          }
        }
        return {
          material_id: Number(it.material_id),
          material_code: it.material_code || '',
          material_name: it.material_name || '',
          material_unit: it.material_unit || '个',
          inbound_quantity: qty,
          unit_price: unitPrice,
          total_amount: computeSimpleDocumentLineTotal(qty, unitPrice),
          location_code: locationCode,
          batch_number: batchStr || undefined,
          serial_numbers: serialList.length ? serialList : undefined,
          status: it.status || detail.status || '待入库',
        };
      });

    setSaving(true);
    try {
      await warehouseApi.otherInbound.update(String(detail.id), {
        reason_type: detail.reason_type,
        reason_desc: reasonDesc.trim() || undefined,
        warehouse_id: Number(detail.warehouse_id),
        warehouse_name: detail.warehouse_name,
        status: detail.status || '待入库',
        review_status: detail.review_status || '待审核',
        notes: notes.trim() || undefined,
        attachments: normalizeDocumentAttachments(detail.attachments),
        items: mappedItems,
      });
      messageApi.success(t('common.saveSuccess'));
      handleClose();
      onSuccess?.();
    } catch (error: unknown) {
      const err = error as { message?: string; response?: { data?: { detail?: string } } };
      messageApi.error(err?.message || err?.response?.data?.detail || t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const modalTitle = useMemo(() => {
    const code = String(detail?.inbound_code ?? detail?.receipt_code ?? '').trim();
    return `${t('common.edit')} ${t('app.kuaizhizao.warehouseInbound.receiptType.other_inbound')}${code ? ` - ${code}` : ''}`;
  }, [detail?.inbound_code, detail?.receipt_code, t]);

  const handleGenerateBatch = async (rowId: number, materialUuid: string | undefined) => {
    if (!materialUuid) return;
    setGeneratingBatchRowId(rowId);
    try {
      const res = await materialBatchApi.generate(materialUuid, {});
      setEditableBatches((prev) => ({ ...prev, [rowId]: res.batch_no }));
      messageApi.success(t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerated'));
    } catch (e: unknown) {
      const err = e as { message?: string };
      messageApi.error(err?.message || t('app.kuaizhizao.warehouseOtherInbound.msg.batchGenerateFailed'));
    } finally {
      setGeneratingBatchRowId(null);
    }
  };

  const handleGenerateSerials = async (rowId: number, qty: number, materialUuid: string | undefined) => {
    if (!materialUuid || !(qty > 0)) return;
    const count = Math.min(Math.floor(qty), MATERIAL_SERIAL_GENERATE_MAX_COUNT);
    setGeneratingSerialRowId(rowId);
    try {
      const res = await materialSerialApi.generate(materialUuid, count, {});
      setEditableSerials((prev) => ({ ...prev, [rowId]: res.serial_nos }));
      messageApi.success(t('app.kuaizhizao.warehouseInbound.msg.serialGenerated', { count: res.count }));
    } catch (e: unknown) {
      const err = e as { message?: string };
      messageApi.error(err?.message || t('app.kuaizhizao.warehouseInbound.msg.serialGenerateFailed'));
    } finally {
      setGeneratingSerialRowId(null);
    }
  };

  const lineColumns = useMemo(
    () =>
      filterWarehouseTrackingColumns(
        appendWarehouseLineAmountColumns(
          [
          {
            title: t('app.kuaizhizao.warehouseInbound.col.materialCode'),
            dataIndex: 'material_code',
            width: 120,
            ellipsis: true,
          },
          {
            title: t('app.kuaizhizao.warehouseInbound.col.materialName'),
            dataIndex: 'material_name',
            width: 150,
            ellipsis: true,
          },
          {
            title: t('app.kuaizhizao.warehouseOtherInbound.col.inboundQty'),
            dataIndex: 'inbound_quantity',
            width: 140,
            align: 'right' as const,
            render: (_: unknown, row: OtherInboundLineItem) => {
              if (row.id == null) return formatQuantity(row.inbound_quantity);
              const rid = Number(row.id);
              return (
                <InputNumber
                  min={0.01}
                  precision={quantityDecimals}
                  value={editableQuantities[rid] ?? Number(row.inbound_quantity ?? 0)}
                  onChange={(v) =>
                    setEditableQuantities((prev) => ({ ...prev, [rid]: Number(v) || 0 }))
                  }
                  style={{ width: 110 }}
                  size="small"
                />
              );
            },
          },
          {
            title: t('app.kuaizhizao.warehouseOtherInbound.col.unitPrice'),
            dataIndex: 'unit_price',
            width: 120,
            align: 'right' as const,
            render: (_: unknown, row: OtherInboundLineItem) => {
              if (row.id == null) return formatQuantity(row.unit_price);
              const rid = Number(row.id);
              return (
                <InputNumber
                  min={0}
                  precision={2}
                  value={editableUnitPrices[rid] ?? Number(row.unit_price ?? 0)}
                  onChange={(v) =>
                    setEditableUnitPrices((prev) => ({ ...prev, [rid]: Number(v) || 0 }))
                  }
                  style={{ width: 100 }}
                  size="small"
                />
              );
            },
          },
          {
            title: t('common.unit'),
            dataIndex: 'material_unit',
            width: 72,
            render: (_: unknown, row: OtherInboundLineItem) => row.material_unit || '-',
          },
          {
            title: t('app.kuaizhizao.warehouseOtherInbound.col.location'),
            dataIndex: 'location_code',
            width: 150,
            render: (_: unknown, row: OtherInboundLineItem) => {
              if (row.id == null) return row.location_code || '—';
              const rid = Number(row.id);
              return (
                <Select
                  options={locationOptions}
                  value={editableLocations[rid] || undefined}
                  onChange={(v) => setEditableLocations((prev) => ({ ...prev, [rid]: String(v ?? '') }))}
                  placeholder={t('app.kuaizhizao.warehouseOtherInbound.field.selectLocation')}
                  style={{ width: '100%' }}
                  size="small"
                  showSearch
                  optionFilterProp="label"
                  disabled={!detail?.warehouse_id}
                />
              );
            },
          },
          {
            title: t('app.kuaizhizao.warehouseOtherInbound.col.batchNo'),
            dataIndex: 'batch_number',
            width: 130,
            render: (_: unknown, row: OtherInboundLineItem) => {
              if (row.id == null) return row.batch_number || '—';
              const rid = Number(row.id);
              const meta = lineMaterialMeta[rid];
              if (!isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) return '—';
              return (
                <Space size={2}>
                  <Input
                    size="small"
                    style={{ width: 96 }}
                    value={editableBatches[rid] ?? ''}
                    onChange={(e) =>
                      setEditableBatches((prev) => ({ ...prev, [rid]: e.target.value }))
                    }
                  />
                  <Button
                    type="link"
                    size="small"
                    icon={<ThunderboltOutlined />}
                    loading={generatingBatchRowId === rid}
                    onClick={() => void handleGenerateBatch(rid, meta?.materialUuid)}
                    style={{ padding: 0 }}
                  />
                </Space>
              );
            },
          },
          {
            title: t('app.kuaizhizao.warehouseOtherInbound.col.serialNo'),
            dataIndex: 'serial_numbers',
            width: 150,
            render: (_: unknown, row: OtherInboundLineItem) => {
              if (row.id == null) return '—';
              const rid = Number(row.id);
              const meta = lineMaterialMeta[rid];
              if (!isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) return '—';
              const qty = Number(editableQuantities[rid] ?? row.inbound_quantity ?? 0);
              return (
                <SerialNumbersImportTrigger
                  serials={editableSerials[rid] ?? []}
                  expectedCount={qty > 0 ? qty : undefined}
                  materialLabel={row.material_code || row.material_name}
                  generateLoading={generatingSerialRowId === rid}
                  onSerialsChange={(next) => setEditableSerials((prev) => ({ ...prev, [rid]: next }))}
                  onGenerate={() =>
                    void handleGenerateSerials(rid, qty, meta?.materialUuid)
                  }
                />
              );
            },
          },
        ],
        t,
        // 其他入库：保留可编辑单价，不自动展示金额列、不叠只读单价列
        false,
        KUAIZHIZAO_INBOUND_FIELD_RESOURCE,
        -3,
      ),
        trackingFlags,
      ),
    [
      detail?.warehouse_id,
      editableBatches,
      editableLocations,
      editableQuantities,
      editableSerials,
      generatingBatchRowId,
      generatingSerialRowId,
      lineMaterialMeta,
      locationOptions,
      quantityDecimals,
      t,
      trackingFlags,
    ],
  );

  return (
    <FormModalTemplate
      title={modalTitle}
      open={open}
      onClose={handleClose}
      onFinish={handleSubmit}
      isEdit
      loading={saving}
      width={MODAL_CONFIG.LARGE_WIDTH}
      grid={false}
    >
      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        {t('app.kuaizhizao.warehouseOtherInbound.col.reasonType')}：{detail?.reason_type ?? '-'}
        {' '}
        {t('app.kuaizhizao.warehouseOtherInbound.col.warehouse')}：{detail?.warehouse_name ?? '-'}
      </Typography.Text>
      <div style={{ marginBottom: 12 }}>
        <Typography.Text style={{ display: 'block', marginBottom: 4 }}>
          {t('app.kuaizhizao.warehouseOtherInbound.field.reasonDesc')}
        </Typography.Text>
        <Input.TextArea
          value={reasonDesc}
          onChange={(e) => setReasonDesc(e.target.value)}
          rows={2}
          placeholder={t('app.kuaizhizao.warehouseOtherInbound.field.optional')}
        />
      </div>
      <div style={{ marginBottom: 16 }}>
        <Typography.Text style={{ display: 'block', marginBottom: 4 }}>
          {t('common.notes')}
        </Typography.Text>
        <Input.TextArea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          placeholder={t('app.kuaizhizao.warehouseOtherInbound.field.optional')}
        />
      </div>
      <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
        {t('app.kuaizhizao.warehouseInbound.section.detailInfo')}
      </Typography.Text>
      <style>{WAREHOUSE_FORM_DETAIL_TABLE_FRAME_STYLES}</style>
      <div className="warehouse-form-detail-table-frame">
        <Table
          className="warehouse-detail-table"
          size="small"
          pagination={false}
          loading={loading}
          rowKey={(row) => String(row.id ?? row.material_code)}
          dataSource={detail?.items || []}
          columns={lineColumns}
          scroll={{ x: 'max-content' }}
          style={{ width: '100%', margin: 0 }}
        />
      </div>
    </FormModalTemplate>
  );
};

export default OtherInboundEditModal;
