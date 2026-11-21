/**
 * 委外发料表单：BOM 待发明细 + 可选手动添加物料；行级出库仓库与可用库存
 */
import React, { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Col,
  Divider,
  Form,
  InputNumber,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Typography,
} from 'antd';
import { PurchaseInboundLineLocationCell } from '../pages/warehouse-management/inbound/PurchaseInboundLineWhCells';
import {
  filterWarehouseTrackingColumns,
  isMaterialBatchEntryEnabled,
  isMaterialSerialEntryEnabled,
  type WarehouseTrackingFlags,
} from '../pages/warehouse-management/shared/warehouseTrackingFlags';
import type { ConfirmPreviewMaterialMeta } from '../pages/warehouse-management/inbound/inboundItemTracking';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { PAGE_SPACING } from '../../../components/layout-templates/constants';
import { UniMaterialSelect } from '../../../components/uni-material-select';
import { useNumericPrecisionPlaces } from '../../../hooks/useNumericPrecision';
import { formatQuantity } from '../../../utils/format';
import { formatDateTimeBySiteSetting } from '../../../utils/format';
import { resolveMaterialScenarioUnit } from '../../../utils/materialScenarioUnit';
import type { Material } from '../../master-data/types/material';
import { resolvePrimaryDefaultWarehouseFromMaterial } from '../../master-data/utils/materialDefaultWarehouse';
import OutboundBatchAllocationField from '../pages/warehouse-management/outbound/OutboundBatchAllocationField';
import OutboundSerialPickerField from '../pages/warehouse-management/outbound/OutboundSerialPickerField';
import {
  lineBatchAllocationsFromRow,
  type OutboundBatchAllocation,
} from '../pages/warehouse-management/outbound/outboundBatchAllocation';
import type { InventoryPickOption } from '../pages/warehouse-management/outbound/outboundConfirmInventoryOptions';

export type OutsourceIssueLine = {
  key: number;
  materialId: number;
  materialCode: string;
  materialName: string;
  unit: string;
  requiredQuantity: number;
  issuedQuantity: number;
  pendingQuantity: number;
  availableQuantity: number;
  issueQuantity: number;
  warehouseId?: number;
  locationId?: number;
  locationCode?: string;
  batchNumber?: string;
  batchAllocations?: OutboundBatchAllocation[];
  serialNumbers?: string[];
  isManual?: boolean;
};

export type OutsourceIssueWorkOrderBrief = {
  id?: number;
  code?: string;
  productName?: string;
  product_name?: string;
  quantity?: number;
  supplier_code?: string;
  supplierCode?: string;
  supplier_name?: string;
  supplierName?: string;
  planned_start_date?: string | null;
  planned_end_date?: string | null;
  plannedStartDate?: string | null;
  plannedEndDate?: string | null;
};

function formatSupplierBrief(workOrder: OutsourceIssueWorkOrderBrief): string {
  const code = (workOrder.supplier_code ?? workOrder.supplierCode ?? '').trim();
  const name = (workOrder.supplier_name ?? workOrder.supplierName ?? '').trim();
  if (code && name) return `${code} - ${name}`;
  return name || code || '-';
}

function formatPlannedDate(value: string | null | undefined): string {
  if (!value) return '-';
  return formatDateTimeBySiteSetting(value);
}

type OutsourceIssueInfoCell = { key: string; label: string; value: React.ReactNode };

function chunkInfoCellsTriple(cells: OutsourceIssueInfoCell[]): OutsourceIssueInfoCell[][] {
  const rows: OutsourceIssueInfoCell[][] = [];
  for (let i = 0; i < cells.length; i += 3) {
    rows.push(cells.slice(i, i + 3));
  }
  return rows;
}

function OutsourceIssueInfoGrid({ cells }: { cells: OutsourceIssueInfoCell[] }) {
  const rows = chunkInfoCellsTriple(cells);
  return (
    <>
      {rows.map((row, rowIndex) => (
        <Row key={row.map((c) => c.key).join('|')} gutter={16} style={rowIndex > 0 ? { marginTop: 0 } : undefined}>
          {row.map((cell) => (
            <Col key={cell.key} xs={24} sm={8}>
              <Form.Item
                label={cell.label}
                style={{ marginBottom: rowIndex === rows.length - 1 ? 0 : 8 }}
              >
                <Typography.Text ellipsis={{ tooltip: true }}>{cell.value}</Typography.Text>
              </Form.Item>
            </Col>
          ))}
        </Row>
      ))}
    </>
  );
}

export type OutsourceIssueWorkOrderInfoPanelProps = {
  workOrder: OutsourceIssueWorkOrderBrief;
  /** i18n key for section title */
  titleKey?: string;
  showSupplierAndPlanned?: boolean;
};

export function OutsourceIssueWorkOrderInfoPanel({
  workOrder,
  titleKey = 'app.kuaizhizao.outsourceWorkOrder.issueWorkOrderInfo',
  showSupplierAndPlanned = false,
}: OutsourceIssueWorkOrderInfoPanelProps) {
  const { t } = useTranslation();
  const plannedStart =
    workOrder.planned_start_date ?? workOrder.plannedStartDate ?? null;
  const plannedEnd = workOrder.planned_end_date ?? workOrder.plannedEndDate ?? null;

  const cells: OutsourceIssueInfoCell[] = [
    {
      key: 'code',
      label: t('app.kuaizhizao.warehouseOutbound.entry.outsourceCode'),
      value: workOrder.code ?? '-',
    },
    ...(showSupplierAndPlanned
      ? [
          {
            key: 'supplier',
            label: t('app.kuaizhizao.outsourceOrder.fieldSupplier'),
            value: formatSupplierBrief(workOrder),
          } as OutsourceIssueInfoCell,
        ]
      : []),
    {
      key: 'product',
      label: t('app.kuaizhizao.warehouseOutbound.entry.product'),
      value: workOrder.productName || workOrder.product_name || '-',
    },
    {
      key: 'quantity',
      label: t('app.kuaizhizao.outsourceWorkOrder.outsourceQty'),
      value: workOrder.quantity != null ? formatQuantity(workOrder.quantity) : '-',
    },
    ...(showSupplierAndPlanned
      ? [
          {
            key: 'planned_start',
            label: t('app.kuaizhizao.outsourceOrder.fieldPlannedStart'),
            value: formatPlannedDate(plannedStart),
          },
          {
            key: 'planned_end',
            label: t('app.kuaizhizao.outsourceOrder.fieldPlannedEnd'),
            value: formatPlannedDate(plannedEnd),
          },
        ]
      : []),
  ];

  return (
    <>
      <Divider style={{ margin: `${PAGE_SPACING.BLOCK_GAP}px 0` }}>{t(titleKey)}</Divider>
      <div
        style={{
          marginBottom: PAGE_SPACING.BLOCK_GAP,
          padding: PAGE_SPACING.PADDING,
          background: '#f5f5f5',
          borderRadius: 4,
        }}
      >
        <OutsourceIssueInfoGrid cells={cells} />
      </div>
    </>
  );
}

export type OutsourceIssueWarehouseOption = {
  label: string;
  value: number;
  name: string;
};

interface OutsourceIssueFormContentProps {
  workOrder: OutsourceIssueWorkOrderBrief;
  lines: OutsourceIssueLine[];
  onLinesChange: (lines: OutsourceIssueLine[]) => void;
  loading?: boolean;
  previewMessage?: string | null;
  allowManualLines?: boolean;
  /** 行级出库仓库选项；传入后隐藏头表选仓，改在明细选仓 */
  warehouseOptions?: OutsourceIssueWarehouseOption[];
  /** 物料 → 仓库 → 可用库存 */
  stockByMaterialWh?: Record<number, Record<number, number>>;
  stockByWhStatus?: 'idle' | 'loading' | 'ready';
  onBatchSetWarehouse?: (warehouseId: number) => void;
  trackingFlags?: WarehouseTrackingFlags;
  lineMaterialMeta?: Record<number, ConfirmPreviewMaterialMeta>;
  batchOptionsByMaterialId?: Record<number, InventoryPickOption[]>;
  batchLoadingMaterialId?: number | null;
  onEnsureBatchOptions?: (materialId: number, warehouseId: number) => void;
  serialOptionsByMaterialId?: Record<number, InventoryPickOption[]>;
  serialLoadingMaterialId?: number | null;
  onEnsureSerialOptions?: (materialId: number) => void;
  hideWorkOrderInfo?: boolean;
  /** 工序委外发料：只录本次发料数量，不选仓库/库存/库位/批号 */
  issueLineDetailMode?: 'warehouse' | 'quantity_only';
}

const OutsourceIssueFormContent: React.FC<OutsourceIssueFormContentProps> = ({
  workOrder,
  lines,
  onLinesChange,
  loading,
  previewMessage,
  allowManualLines = true,
  warehouseOptions,
  stockByMaterialWh,
  stockByWhStatus = 'idle',
  onBatchSetWarehouse,
  trackingFlags,
  lineMaterialMeta,
  batchOptionsByMaterialId,
  batchLoadingMaterialId,
  onEnsureBatchOptions,
  serialOptionsByMaterialId,
  serialLoadingMaterialId,
  onEnsureSerialOptions,
  hideWorkOrderInfo = false,
  issueLineDetailMode = 'warehouse',
}) => {
  const { t } = useTranslation();
  const quantityDecimals = useNumericPrecisionPlaces('quantity');
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerForm] = Form.useForm();
  const [batchWhId, setBatchWhId] = useState<number | undefined>();
  const quantityOnlyLines = issueLineDetailMode === 'quantity_only';
  const lineWarehouseEnabled = !quantityOnlyLines && warehouseOptions !== undefined;
  const trackingEnabled = trackingFlags != null;
  const lineTrackingEnabled = trackingEnabled && (lineWarehouseEnabled || quantityOnlyLines);

  const updateLineQty = (materialId: number, issueQuantity: number) => {
    onLinesChange(
      lines.map((l) => (l.materialId === materialId ? { ...l, issueQuantity } : l)),
    );
  };

  const updateLineWarehouse = (materialId: number, warehouseId: number) => {
    onLinesChange(
      lines.map((l) => {
        if (l.materialId !== materialId) return l;
        const available =
          stockByWhStatus === 'ready'
            ? Number(stockByMaterialWh?.[materialId]?.[warehouseId] ?? 0)
            : l.availableQuantity;
        return {
          ...l,
          warehouseId,
          availableQuantity: available,
          locationId: undefined,
          locationCode: undefined,
          batchNumber: undefined,
          batchAllocations: [],
        };
      }),
    );
  };

  const updateLineLocation = (materialId: number, locationId: number | undefined, locationCode: string) => {
    onLinesChange(
      lines.map((l) =>
        l.materialId === materialId ? { ...l, locationId, locationCode } : l,
      ),
    );
  };

  const updateLineBatchAllocs = (materialId: number, allocs: OutboundBatchAllocation[]) => {
    onLinesChange(
      lines.map((l) =>
        l.materialId === materialId
          ? {
              ...l,
              batchAllocations: allocs,
              batchNumber: allocs.length === 1 ? allocs[0].batchNo : undefined,
            }
          : l,
      ),
    );
  };

  const updateLineSerialNumbers = (materialId: number, serialNumbers: string[]) => {
    onLinesChange(
      lines.map((l) => (l.materialId === materialId ? { ...l, serialNumbers } : l)),
    );
  };

  const removeManualLine = (materialId: number) => {
    onLinesChange(lines.filter((l) => l.materialId !== materialId));
  };

  const addManualMaterial = (_val: number | undefined, material: Material | undefined) => {
    if (!material?.id) return;
    const materialId = Number(material.id);
    if (lines.some((l) => l.materialId === materialId)) {
      return;
    }
    const primaryWh = resolvePrimaryDefaultWarehouseFromMaterial(material);
    onLinesChange([
      ...lines,
      {
        key: materialId,
        materialId,
        materialCode: String(material.mainCode ?? material.code ?? ''),
        materialName: String(material.name ?? ''),
        unit: resolveMaterialScenarioUnit(material, 'production') || material.baseUnit || '',
        requiredQuantity: 0,
        issuedQuantity: 0,
        pendingQuantity: 0,
        availableQuantity: 0,
        issueQuantity: 0,
        warehouseId: primaryWh?.id,
        serialNumbers: [],
        isManual: true,
      },
    ]);
    if (primaryWh?.id && onEnsureBatchOptions) {
      void onEnsureBatchOptions(materialId, primaryWh.id);
    }
    pickerForm.resetFields();
    setPickerOpen(false);
  };

  const warehouseOptionsForMaterial = useCallback(
    (materialId: number) => {
      const opts = warehouseOptions ?? [];
      const stockMap = stockByMaterialWh?.[materialId] ?? {};
      const showStock = stockByWhStatus === 'ready';
      const enriched = opts.map((o) => {
        const qty = Number(stockMap[o.value] ?? 0);
        const baseName = String(o.name || o.label || o.value).trim();
        const label = showStock
          ? t('app.kuaizhizao.warehouseOutbound.option.warehouseWithStock', {
              warehouse: baseName,
              qty: formatQuantity(qty),
            })
          : baseName;
        return { ...o, label, stockQty: qty };
      });
      if (!showStock) return enriched;
      return enriched.sort((a, b) => {
        if (a.stockQty !== b.stockQty) return b.stockQty - a.stockQty;
        return String(a.name || a.label).localeCompare(String(b.name || b.label), 'zh');
      });
    },
    [stockByMaterialWh, stockByWhStatus, t, warehouseOptions],
  );

  const resolveAvailableQty = (r: OutsourceIssueLine): number | null => {
    if (!lineWarehouseEnabled) {
      return Number(r.availableQuantity ?? 0);
    }
    const whId = Number(r.warehouseId ?? 0);
    if (!(whId > 0)) return null;
    if (stockByWhStatus === 'ready') {
      return Number(stockByMaterialWh?.[r.materialId]?.[whId] ?? 0);
    }
    return Number(r.availableQuantity ?? 0);
  };

  const columns: ColumnsType<OutsourceIssueLine> = useMemo(
    () =>
      filterWarehouseTrackingColumns(
        [
      {
        title: t('app.kuaizhizao.salesOrder.materialCode'),
        dataIndex: 'materialCode',
        width: 120,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.salesOrder.materialName'),
        dataIndex: 'materialName',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('common.unit'),
        dataIndex: 'unit',
        width: 56,
        align: 'center',
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.entry.requiredQty'),
        dataIndex: 'requiredQuantity',
        width: 96,
        align: 'right',
        render: (_, r) => (r.isManual ? '—' : formatQuantity(r.requiredQuantity)),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.pull.colIssuedQty'),
        dataIndex: 'issuedQuantity',
        width: 80,
        align: 'right',
        render: (_, r) => (r.isManual ? '—' : formatQuantity(r.issuedQuantity)),
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.entry.pendingIssueQty'),
        dataIndex: 'pendingQuantity',
        width: 80,
        align: 'right',
        render: (_, r) =>
          r.isManual ? (
            '—'
          ) : (
            <Typography.Text type={r.pendingQuantity > 0 ? 'warning' : undefined}>
              {formatQuantity(r.pendingQuantity)}
            </Typography.Text>
          ),
      },
      ...(lineWarehouseEnabled
        ? [
            {
              title: (
                <>
                  {t('app.kuaizhizao.warehouseOutbound.col.warehouseName')}
                  <Typography.Text type="danger"> *</Typography.Text>
                </>
              ),
              key: 'warehouse',
              width: 220,
              render: (_: unknown, r: OutsourceIssueLine) => (
                <Select
                  style={{ width: '100%', minWidth: 160 }}
                  placeholder={t('app.kuaizhizao.warehouseOutbound.msg.selectWarehouse')}
                  showSearch
                  optionFilterProp="label"
                  options={warehouseOptionsForMaterial(r.materialId)}
                  value={r.warehouseId}
                  onChange={(nv) => {
                    const wh = Number(nv);
                    if (!(wh > 0)) return;
                    updateLineWarehouse(r.materialId, wh);
                  }}
                />
              ),
            } as ColumnsType<OutsourceIssueLine>[number],
          ]
        : []),
      ...(lineTrackingEnabled
        ? [
            ...(lineWarehouseEnabled
              ? [
                  {
                    title: t('app.kuaizhizao.warehouseOutbound.col.location'),
              key: 'location',
              width: 150,
              render: (_: unknown, r: OutsourceIssueLine) => {
                const whId = Number(r.warehouseId ?? 0);
                if (!(whId > 0)) {
                  return (
                    <Typography.Text type="secondary">
                      {t('app.kuaizhizao.warehouseInbound.field.selectWarehouseFirst')}
                    </Typography.Text>
                  );
                }
                return (
                  <PurchaseInboundLineLocationCell
                    materialId={r.materialId}
                    warehouseId={whId}
                    locationId={r.locationId}
                    selectWarehouseFirstPlaceholder={t('app.kuaizhizao.warehouseInbound.field.selectWarehouseFirst')}
                    selectLocationPlaceholder={t('app.kuaizhizao.warehouseInbound.field.selectLocation')}
                    onChange={(v, loc) => updateLineLocation(r.materialId, v ?? undefined, loc?.code ?? '')}
                  />
                );
              },
            } as ColumnsType<OutsourceIssueLine>[number],
                ]
              : []),
            {
              title: t('app.kuaizhizao.warehouseOutbound.col.batchNo'),
              key: 'batch',
              width: 260,
              render: (_: unknown, r: OutsourceIssueLine) => {
                const meta = lineMaterialMeta?.[r.materialId];
                if (!trackingFlags || !isMaterialBatchEntryEnabled(trackingFlags, meta?.batchManaged)) {
                  return '—';
                }
                const whId = Number(r.warehouseId ?? 0);
                const opts = batchOptionsByMaterialId?.[r.materialId] ?? [];
                const qty = Number(r.issueQuantity || 0);
                const allocs = lineBatchAllocationsFromRow(
                  {
                    batch_allocations: r.batchAllocations,
                    batch_number: r.batchNumber,
                  },
                  qty,
                );
                const materialLabel = [r.materialCode, r.materialName].filter(Boolean).join(' - ');
                return (
                  <span
                    onClick={() => {
                      if (whId > 0 && onEnsureBatchOptions && !(opts.length > 0)) {
                        onEnsureBatchOptions(r.materialId, whId);
                      }
                    }}
                  >
                    <OutboundBatchAllocationField
                      value={allocs}
                      onChange={(next) => updateLineBatchAllocs(r.materialId, next)}
                      options={opts}
                      totalQuantity={qty}
                      loading={batchLoadingMaterialId === r.materialId}
                      disabled={!(whId > 0)}
                      materialLabel={materialLabel}
                    />
                  </span>
                );
              },
            } as ColumnsType<OutsourceIssueLine>[number],
            {
              title: t('app.kuaizhizao.warehouseOutbound.col.serialNo'),
              key: 'serial',
              width: 168,
              render: (_: unknown, r: OutsourceIssueLine) => {
                const meta = lineMaterialMeta?.[r.materialId];
                if (!trackingFlags || !isMaterialSerialEntryEnabled(trackingFlags, meta?.serialManaged)) {
                  return '—';
                }
                const qty = Number(r.issueQuantity || 0);
                const opts = serialOptionsByMaterialId?.[r.materialId] ?? [];
                const materialLabel = [r.materialCode, r.materialName].filter(Boolean).join(' - ');
                return (
                  <OutboundSerialPickerField
                    value={r.serialNumbers ?? []}
                    onChange={(next) => updateLineSerialNumbers(r.materialId, next)}
                    options={opts}
                    maxCount={qty > 0 ? qty : undefined}
                    loading={serialLoadingMaterialId === r.materialId}
                    disabled={!(qty > 0) || !meta?.materialUuid}
                    materialLabel={materialLabel}
                    onOpenPicker={() => {
                      if (meta?.materialUuid && onEnsureSerialOptions) {
                        void onEnsureSerialOptions(r.materialId);
                      }
                    }}
                  />
                );
              },
            } as ColumnsType<OutsourceIssueLine>[number],
          ]
        : []),
      ...(quantityOnlyLines
        ? []
        : [
            {
              title: t('app.kuaizhizao.outsourceWorkOrder.issueAvailableStock'),
              dataIndex: 'availableQuantity',
              width: 96,
              align: 'right',
              render: (_: unknown, r: OutsourceIssueLine) => {
                const qty = resolveAvailableQty(r);
                if (qty == null) {
                  return (
                    <Typography.Text type="secondary">
                      {t('app.kuaizhizao.outsourceWorkOrder.issueAvailableStockNeedWarehouse')}
                    </Typography.Text>
                  );
                }
                return formatQuantity(qty);
              },
            } as ColumnsType<OutsourceIssueLine>[number],
          ]),
      {
        title: t('app.kuaizhizao.warehouseOutbound.entry.thisIssue'),
        dataIndex: 'issueQuantity',
        width: 120,
        align: 'right',
        fixed: 'right',
        render: (_, r) => {
          const manual = r.isManual === true;
          const disabled = !manual && r.pendingQuantity <= 0;
          return (
            <InputNumber
              min={0}
              max={manual ? undefined : r.pendingQuantity > 0 ? r.pendingQuantity : undefined}
              precision={quantityDecimals}
              value={r.issueQuantity}
              disabled={disabled}
              style={{ width: '100%' }}
              onChange={(v) => updateLineQty(r.materialId, Number(v ?? 0))}
            />
          );
        },
      },
      ...(allowManualLines
        ? [
            {
              title: t('common.actions'),
              key: 'actions',
              width: 72,
              fixed: 'right' as const,
              render: (_: unknown, r: OutsourceIssueLine) =>
                r.isManual ? (
                  <Button type="link" danger size="small" onClick={() => removeManualLine(r.materialId)}>
                    {t('common.delete')}
                  </Button>
                ) : null,
            },
          ]
        : []),
        ],
        trackingFlags ?? { batchManagement: true, serialManagement: true },
      ),
    [
      allowManualLines,
      lineWarehouseEnabled,
      lineTrackingEnabled,
      quantityDecimals,
      quantityOnlyLines,
      lines,
      onLinesChange,
      stockByMaterialWh,
      stockByWhStatus,
      t,
      warehouseOptionsForMaterial,
      trackingEnabled,
      trackingFlags,
      lineMaterialMeta,
      batchOptionsByMaterialId,
      batchLoadingMaterialId,
      onEnsureBatchOptions,
      serialOptionsByMaterialId,
      serialLoadingMaterialId,
      onEnsureSerialOptions,
    ],
  );

  const alertType = allowManualLines && previewMessage ? 'info' : 'warning';

  return (
    <>
      {hideWorkOrderInfo ? null : <OutsourceIssueWorkOrderInfoPanel workOrder={workOrder} />}

      <Divider style={{ margin: `${PAGE_SPACING.BLOCK_GAP}px 0` }}>
        {t('app.kuaizhizao.outsourceWorkOrder.issueLineSection')}
      </Divider>
      {previewMessage ? (
        <Alert type={alertType} showIcon title={previewMessage} style={{ marginBottom: 12 }} />
      ) : null}
      <Space style={{ marginBottom: 12 }} wrap>
        {allowManualLines ? (
          pickerOpen ? (
            <>
              <Form form={pickerForm} style={{ minWidth: 320, flex: 1 }}>
                <UniMaterialSelect
                  name="manual_material_id"
                  label=""
                  placeholder={t('app.kuaizhizao.outsourceWorkOrder.issuePickMaterial')}
                  onChange={addManualMaterial}
                  showQuickCreate
                  showAdvancedSearch
                />
              </Form>
              <Button onClick={() => setPickerOpen(false)}>{t('common.cancel')}</Button>
            </>
          ) : (
            <Button icon={<PlusOutlined />} onClick={() => setPickerOpen(true)}>
              {t('app.kuaizhizao.outsourceWorkOrder.issueAddManualLine')}
            </Button>
          )
        ) : null}
        {lineWarehouseEnabled && onBatchSetWarehouse ? (
          <Space.Compact>
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('app.kuaizhizao.warehouseOutbound.entry.batchSetLineWarehouse')}
              style={{ width: 220 }}
              options={warehouseOptions}
              value={batchWhId}
              onChange={(v) => setBatchWhId(v == null ? undefined : Number(v))}
            />
            <Button
              disabled={!(batchWhId != null && batchWhId > 0) || !lines.length}
              onClick={() => {
                if (batchWhId != null && batchWhId > 0) onBatchSetWarehouse(batchWhId);
              }}
            >
              {t('app.kuaizhizao.warehouseOutbound.entry.batchSetLineWarehouse')}
            </Button>
          </Space.Compact>
        ) : null}
      </Space>
      <Spin spinning={!!loading}>
        <Table<OutsourceIssueLine>
          size="small"
          rowKey="materialId"
          columns={columns}
          dataSource={lines}
          pagination={false}
          scroll={{
            x: quantityOnlyLines
              ? lineTrackingEnabled
                ? 980
                : 760
              : lineWarehouseEnabled
                ? 1180
                : 980,
            y: 280,
          }}
          locale={{
            emptyText: loading
              ? t('common.loading')
              : t('app.kuaizhizao.outsourceWorkOrder.issueLineEmpty'),
          }}
        />
      </Spin>
    </>
  );
};

export default OutsourceIssueFormContent;
