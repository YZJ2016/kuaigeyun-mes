/**
 * 从委外工单取单开委外发料 — 独立 Tab 页
 * 出库仓库在明细行选择（多物料可存不同仓）；可用库存按行仓显示
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
  Row,
  Space,
  Spin,
  Typography,
} from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { type Dayjs } from 'dayjs';
import {
  DOCUMENT_DETAIL_PAGE_TITLE_STYLE,
  DocumentFormPageLayout,
  PAGE_SPACING,
} from '../../../../../components/layout-templates';
import { warehouseApi as masterWarehouseApi } from '../../../../master-data/services/warehouse';
import { outsourceMaterialIssueApi, outsourceWorkOrderApi } from '../../../services/production';
import { useInvalidateMenuBadgeCounts } from '../../../../../hooks/useInvalidateMenuBadgeCounts';
import { setCustomPageTitle, removeCustomPageTitle } from '../../../../../utils/customPageTitle';
import { toApiBusinessDocumentDateTime } from '../../../../../utils/formDate';
import OutsourceIssueFormContent, {
  type OutsourceIssueLine,
} from '../../../components/OutsourceIssueFormContent';
import {
  OutboundEntryOperatorField,
  OutboundEntryRemarksSection,
  ReadOnlyFormValue,
  mapWarehouseSelectOptions,
  useOutboundOperatorSelect,
} from './outboundEntryShared';
import { getOutboundIssueTypeLabel } from './outboundHubTypes';
import { OUTBOUND_LIST_PATH, outboundOutsourceEntryPath } from './outboundPaths';
import { resolveKuaizhizaoDocumentAction } from '../../../constants/documentActionRegistry';
import {
  draftDayjs,
  draftOptionalNumber,
  mergeMaterialIssueQuantities,
  usePullEntryFormDraft,
} from '../shared/pullEntryFormDraft';
import { navigateLeavingPullEntry, pullEntryTabKey } from '../shared/pullEntryCloseTab';
import {
  loadAvailableQtyByMaterialWarehouse,
  loadBatchOptionsByMaterialId,
  type InventoryPickOption,
} from './outboundConfirmInventoryOptions';
import { isValidOutboundBatchAllocations } from './outboundBatchAllocation';
import { lineLocationSelectionRequired } from '../../../../../components/uni-wh-dropdown';
import {
  isMaterialBatchEntryEnabled,
  useWarehouseTrackingFlags,
} from '../shared/warehouseTrackingFlags';
import {
  loadConfirmPreviewMaterialMeta,
  type ConfirmPreviewMaterialMeta,
} from '../inbound/inboundItemTracking';

const OutboundOutsourcePullEntryPage: React.FC = () => {
  const { t } = useTranslation();
  const pullFromOutsourceWorkOrderAction = resolveKuaizhizaoDocumentAction(t, 'outbound.pull_from_outsource_work_order');
  const { woId: woIdParam } = useParams<{ woId: string }>();
  const woId = Number(woIdParam);
  const navigate = useNavigate();
  const location = useLocation();
  const { message: messageApi } = App.useApp();
  const operatorHook = useOutboundOperatorSelect();
  const trackingFlags = useWarehouseTrackingFlags();
  const invalidateMenuBadgeCounts = useInvalidateMenuBadgeCounts();
  const initRef = useRef(false);
  const [lineMaterialMeta, setLineMaterialMeta] = useState<Record<number, ConfirmPreviewMaterialMeta>>({});
  const [batchOptionsByMaterialId, setBatchOptionsByMaterialId] = useState<
    Record<number, InventoryPickOption[]>
  >({});
  const [batchLoadingMaterialId, setBatchLoadingMaterialId] = useState<number | null>(null);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [workOrder, setWorkOrder] = useState<Record<string, unknown> | null>(null);
  const [warehouseOptions, setWarehouseOptions] = useState<{ label: string; value: number; name: string }[]>([]);
  const [stockByMaterialWh, setStockByMaterialWh] = useState<Record<number, Record<number, number>>>({});
  const [stockByWhStatus, setStockByWhStatus] = useState<'idle' | 'loading' | 'ready'>('idle');
  const [notes, setNotes] = useState('');
  const [issueTime, setIssueTime] = useState<Dayjs | null>(null);
  const [issueLines, setIssueLines] = useState<OutsourceIssueLine[]>([]);
  const [previewMessage, setPreviewMessage] = useState<string | null>(null);
  const [allowManualLines, setAllowManualLines] = useState(true);
  const { bindSnapshot, persistNow, clearDraft, applyDraftOnce } = usePullEntryFormDraft(
    'kuaizhizao:outbound-outsource-pull',
  );

  const pagePath = Number.isFinite(woId) && woId > 0 ? outboundOutsourceEntryPath(woId) : OUTBOUND_LIST_PATH;
  const woCode = String(workOrder?.code ?? '');
  const pageTitle = woCode
    ? `${pullFromOutsourceWorkOrderAction.label} — ${woCode}`
    : pullFromOutsourceWorkOrderAction.label;

  const totalIssueQty = useMemo(
    () => issueLines.reduce((sum, line) => sum + Number(line.issueQuantity || 0), 0),
    [issueLines],
  );

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

  const leavePage = useCallback(() => {
    clearDraft();
    navigateLeavingPullEntry(
      navigate,
      OUTBOUND_LIST_PATH,
      pullEntryTabKey(location.pathname, location.search),
    );
  }, [clearDraft, navigate, location.pathname, location.search]);

  useEffect(() => {
    bindSnapshot(() => ({
      notes,
      issueTime: issueTime?.isValid() ? toApiBusinessDocumentDateTime(issueTime) : undefined,
      receiverUuid: operatorHook.receiverUuid,
      receiverName: operatorHook.receiverName,
      issueQuantities: Object.fromEntries(issueLines.map((line) => [line.materialId, line.issueQuantity])),
      lineWarehouses: Object.fromEntries(
        issueLines
          .filter((line) => line.warehouseId != null && line.warehouseId > 0)
          .map((line) => [line.materialId, line.warehouseId]),
      ),
    }));
    persistNow();
  }, [notes, issueTime, issueLines, operatorHook.receiverUuid, operatorHook.receiverName, bindSnapshot, persistNow]);

  useEffect(() => {
    if (!(Number.isFinite(woId) && woId > 0)) {
      messageApi.error(t('app.kuaizhizao.warehouseOutbound.entry.invalidOutsource'));
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
  }, [pickMaterialIdsKey]);

  /** 库存就绪后回写已选仓行的可用数量 */
  useEffect(() => {
    if (stockByWhStatus !== 'ready') return;
    setIssueLines((prev) =>
      prev.map((line) => {
        const whId = Number(line.warehouseId ?? 0);
        if (!(whId > 0)) return line;
        const available = Number(stockByMaterialWh[line.materialId]?.[whId] ?? 0);
        if (available === line.availableQuantity) return line;
        return { ...line, availableQuantity: available };
      }),
    );
  }, [stockByMaterialWh, stockByWhStatus]);

  useEffect(() => {
    if (!Number.isFinite(woId) || woId <= 0 || initRef.current) return;
    initRef.current = true;
    void (async () => {
      setLoading(true);
      try {
        const [owo, whRes, preview] = await Promise.all([
          outsourceWorkOrderApi.get(String(woId)),
          masterWarehouseApi.list({ is_active: true, limit: 500 }),
          outsourceMaterialIssueApi.issuePreview(woId),
        ]);
        setWorkOrder(owo as Record<string, unknown>);
        setWarehouseOptions(mapWarehouseSelectOptions(whRes));
        setPreviewMessage(preview?.message ?? preview?.data?.message ?? null);
        setAllowManualLines(
          (preview?.allow_manual_lines ?? preview?.data?.allow_manual_lines) !== false,
        );
        const rawLines = preview?.lines ?? preview?.data?.lines ?? [];
        const mappedLines = rawLines.map((line: Record<string, unknown>) => {
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
            issueQuantity: 0,
          };
        });
        setIssueLines(mappedLines);
        setLineMaterialMeta(
          await loadConfirmPreviewMaterialMeta(
            mappedLines.map((line) => ({
              id: line.materialId,
              material_id: line.materialId,
              material_code: line.materialCode,
            })),
          ),
        );
        applyDraftOnce((draft) => {
          if (typeof draft.notes === 'string') setNotes(draft.notes);
          if (draft.issueTime) {
            const parsed = draftDayjs(draft.issueTime);
            setIssueTime(parsed?.isValid() ? parsed.startOf('day') : null);
          }
          operatorHook.restoreReceiver(
            typeof draft.receiverUuid === 'string' ? draft.receiverUuid : undefined,
            typeof draft.receiverName === 'string' ? draft.receiverName : undefined,
          );
          if (draft.issueQuantities) {
            setIssueLines((prev) =>
              mergeMaterialIssueQuantities(prev, draft.issueQuantities as Record<number, number>),
            );
          }
          const whByMaterial = draft.lineWarehouses as Record<number, number> | undefined;
          if (whByMaterial && typeof whByMaterial === 'object') {
            setIssueLines((prev) =>
              prev.map((row) => {
                const whId = draftOptionalNumber(whByMaterial[row.materialId]);
                return whId != null && whId > 0 ? { ...row, warehouseId: whId } : row;
              }),
            );
          }
        });
      } catch (e: unknown) {
        messageApi.error((e as Error)?.message || t('app.kuaizhizao.warehouseOutbound.entry.loadOutsourceFailed'));
        leavePage();
      } finally {
        setLoading(false);
      }
    })();
  }, [woId, leavePage, messageApi, t, applyDraftOnce, operatorHook.restoreReceiver]);

  const ensureBatchOptionsForLine = useCallback(async (materialId: number, warehouseId: number) => {
    setBatchLoadingMaterialId(materialId);
    try {
      const map = await loadBatchOptionsByMaterialId([materialId], warehouseId);
      setBatchOptionsByMaterialId((prev) => ({ ...prev, ...map }));
    } finally {
      setBatchLoadingMaterialId(null);
    }
  }, []);

  const handleBatchSetWarehouse = useCallback(
    (warehouseId: number) => {
      if (!(warehouseId > 0) || !issueLines.length) return;
      setIssueLines((prev) =>
        prev.map((line) => {
          const available =
            stockByWhStatus === 'ready'
              ? Number(stockByMaterialWh[line.materialId]?.[warehouseId] ?? 0)
              : line.availableQuantity;
          return { ...line, warehouseId, availableQuantity: available };
        }),
      );
      messageApi.success(
        t('app.kuaizhizao.warehouseOutbound.entry.batchWarehouseApplied', { count: issueLines.length }),
      );
    },
    [issueLines.length, messageApi, stockByMaterialWh, stockByWhStatus, t],
  );

  const submit = async () => {
    const activeLines = issueLines.filter((line) => line.issueQuantity > 0);
    if (!activeLines.length) {
      messageApi.warning(t('app.kuaizhizao.warehouseOutbound.entry.fillIssueQty'));
      return;
    }

    for (const line of activeLines) {
      const whId = Number(line.warehouseId ?? 0);
      const materialLabel = line.materialName || line.materialCode || String(line.materialId);
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
      const meta = lineMaterialMeta[line.materialId];
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
    }

    setSubmitting(true);
    try {
      await outsourceMaterialIssueApi.createBatch({
        outsource_work_order_id: woId,
        outsource_work_order_code: woCode,
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
          const allocs = (line.batchAllocations ?? []).filter(
            (a) => String(a.batchNo).trim() && Number(a.quantity) > 0,
          );
          if (allocs.length > 1) {
            return allocs.map((a) => ({
              ...base,
              quantity: a.quantity,
              batch_number: a.batchNo,
            }));
          }
          return [
            {
              ...base,
              quantity: line.issueQuantity,
              batch_number: allocs[0]?.batchNo || line.batchNumber?.trim() || undefined,
            },
          ];
        }),
      });
      invalidateMenuBadgeCounts();
      clearDraft();
      messageApi.success(t('app.kuaizhizao.warehouseOutbound.entry.outsourceIssueCreated'));
      leavePage();
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
            <Button type="primary" loading={submitting} disabled={loading} onClick={() => void submit()}>
              {t('app.kuaizhizao.warehouseOutbound.action.confirmIssue')}
            </Button>
          </Space>
        </>
      }
    >
      <Spin spinning={loading}>
        <Card styles={{ body: { padding: PAGE_SPACING.PADDING } }}>
          {workOrder && (
            <Form layout="vertical" requiredMark={false}>
              <Row gutter={16}>
                <Col xs={24} sm={12} lg={6}>
                  <Form.Item label={t('app.kuaizhizao.warehouseOutbound.field.outboundType')}>
                    <ReadOnlyFormValue value={getOutboundIssueTypeLabel(t, 'outsource_issue')} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                  <Form.Item label={t('app.kuaizhizao.warehouseOutbound.entry.outsourceCode')}>
                    <ReadOnlyFormValue value={woCode} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                  <Form.Item label={t('app.kuaizhizao.warehouseOutbound.entry.product')}>
                    <ReadOnlyFormValue value={String(workOrder.product_name ?? workOrder.productName ?? '')} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                  <Form.Item label={t('app.kuaizhizao.warehouseOutbound.entry.outsourceSupplier')}>
                    <ReadOnlyFormValue value={String(workOrder.supplier_name ?? workOrder.supplierName ?? '')} />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                  <Form.Item label={t('app.kuaizhizao.warehouseOutbound.field.documentDate')}>
                    <DatePicker
                      style={{ width: '100%' }}
                      value={issueTime}
                      onChange={(v) => setIssueTime(v ? v.startOf('day') : null)}
                    />
                  </Form.Item>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                  <OutboundEntryOperatorField hook={operatorHook} />
                </Col>
              </Row>
              <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                {t('app.kuaizhizao.warehouseOutbound.entry.totalIssueQty', { qty: totalIssueQty })}
              </Typography.Text>
              <OutsourceIssueFormContent
                workOrder={workOrder}
                lines={issueLines}
                onLinesChange={setIssueLines}
                previewMessage={previewMessage}
                allowManualLines={allowManualLines}
                warehouseOptions={warehouseOptions}
                stockByMaterialWh={stockByMaterialWh}
                stockByWhStatus={stockByWhStatus}
                onBatchSetWarehouse={handleBatchSetWarehouse}
                trackingFlags={trackingFlags}
                lineMaterialMeta={lineMaterialMeta}
                batchOptionsByMaterialId={batchOptionsByMaterialId}
                batchLoadingMaterialId={batchLoadingMaterialId}
                onEnsureBatchOptions={ensureBatchOptionsForLine}
              />
              <Row gutter={16} style={{ marginTop: 16 }}>
                <Col xs={24}>
                  <OutboundEntryRemarksSection value={notes} onChange={setNotes} />
                </Col>
              </Row>
            </Form>
          )}
        </Card>
      </Spin>
    </DocumentFormPageLayout>
  );
};

export default OutboundOutsourcePullEntryPage;
