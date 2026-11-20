/**
 * 工序序列编辑器
 * 支持手柄拖拽排序（原生 HTML5，仅手柄）、添加工序、替换工序、删除工序
 */

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import {
  Button,
  Tag,
  Space,
  Modal,
  message,
  Select,
  Table,
  Empty,
  Typography,
  Switch,
  InputNumber,
  Input,
  theme,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useSubmitShortcut } from '../../../hooks/useSubmitShortcut';
import { SUBMIT_SHORTCUT_HINT } from '../../../utils/globalSubmitShortcut';
import { MODAL_ISOLATE_POINTER_PROPS } from '../../../utils/modalEventIsolation';
import { PlusOutlined } from '@ant-design/icons';
import { UniDropdown } from '../../../components/uni-dropdown';
import { renderOperationReportingTypeMarker } from '../utils/operationMeta';
import { operationApi } from '../services/process';
import type { Operation } from '../types/process';
import { OperationFormModal } from './OperationFormModal';
import { supplierApi, unwrapSupplyPagedList } from '../services/supply-chain';
import {
  MODAL_ABOVE_DETAIL_SIDECHAIN_OFFSET,
  MODAL_NESTED_ABOVE_PARENT_OFFSET,
  FILE_PREVIEW_OVERLAY_Z_INDEX,
} from '../../../components/layout-templates/constants';
import { SequenceIndexCell } from '../../../components/sequence-index-cell';
import { inspectionPlanApi, unwrapInspectionPlanList } from '../../kuaizhizao/services/quality-execution';
import {
  InspectionPlanFormModal,
  type InspectionPlanRecord,
} from '../../kuaizhizao/components/InspectionPlanFormModal';
import { ipqcFromOperation } from '../utils/processRouteSequenceUtils';
import {
  fetchActiveOperationCatalog,
  mergeOperationIntoActiveCatalog,
} from '../utils/activeOperationCatalog';
import {
  fromSeconds,
  normalizeTimeUnit,
  toSeconds,
} from '../utils/manufacturingTimeUnits';
import type { ManufacturingTimeUnit } from '../types/productProcess';

const TIME_UNIT_OPTIONS: { value: ManufacturingTimeUnit; labelKey: string }[] = [
  { value: 'h', labelKey: 'app.master-data.manufacturing.timeUnitHour' },
  { value: 'm', labelKey: 'app.master-data.manufacturing.timeUnitMinute' },
  { value: 's', labelKey: 'app.master-data.manufacturing.timeUnitSecond' },
];

const OPERATION_PICK_MODAL_WIDTH = 840;
/** 顶对齐距视口顶（与 antd 默认 100px 接近，略收一点以免遮挡站顶栏） */
const OPERATION_PICK_MODAL_TOP = 88;
const OPERATION_PICK_TABLE_SCROLL_Y = 400;
/** 表头 + 滚动区，避免无数据时弹窗变矮、垂直位置跳动 */
const OPERATION_PICK_TABLE_MIN_HEIGHT = OPERATION_PICK_TABLE_SCROLL_Y + 40;

const operationPickModalStyles = {
  body: { paddingTop: 8, paddingBottom: 12 },
};

const OPERATION_ROW_DRAG_MIME = 'application/x-riveredge-operation-uuid';

function moveOperationList(items: OperationItem[], sourceUuid: string, targetUuid: string): OperationItem[] {
  const oldIndex = items.findIndex((op) => op.uuid === sourceUuid);
  const newIndex = items.findIndex((op) => op.uuid === targetUuid);
  if (oldIndex < 0 || newIndex < 0 || oldIndex === newIndex) return items;
  const next = [...items];
  const [moved] = next.splice(oldIndex, 1);
  next.splice(newIndex, 0, moved);
  return next;
}

function filterOperationList(ops: Operation[], keyword: string): Operation[] {
  const q = keyword.trim().toLowerCase();
  if (!q) return ops;
  return ops.filter((op) =>
    `${op.code ?? ''} ${op.name ?? ''} ${op.description ?? ''}`.toLowerCase().includes(q),
  );
}

type OperationPickPanelProps = {
  operations: Operation[];
  loading: boolean;
  mode: 'multiple' | 'single';
  multipleValue?: string[];
  onMultipleChange?: (uuids: string[]) => void;
  singleValue?: string;
  onSingleChange?: (uuid: string | undefined) => void;
  searchPlaceholder: string;
  onQuickAdd?: () => void;
  quickAddLabel?: string;
};

export const OperationPickPanel: React.FC<OperationPickPanelProps> = ({
  operations,
  loading,
  mode,
  multipleValue = [],
  onMultipleChange,
  singleValue,
  onSingleChange,
  searchPlaceholder,
  onQuickAdd,
  quickAddLabel,
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const [keyword, setKeyword] = useState('');
  const filtered = useMemo(() => filterOperationList(operations, keyword), [operations, keyword]);
  const selectedOperations = useMemo(
    () =>
      multipleValue
        .map((id) => operations.find((o) => o.uuid === id))
        .filter((op): op is Operation => !!op),
    [multipleValue, operations],
  );

  const handleSelectAllFiltered = () => {
    if (mode !== 'multiple' || !onMultipleChange) return;
    const ids = filtered.map((o) => o.uuid);
    const allOn = ids.length > 0 && ids.every((id) => multipleValue.includes(id));
    if (allOn) {
      onMultipleChange(multipleValue.filter((id) => !ids.includes(id)));
    } else {
      onMultipleChange([...new Set([...multipleValue, ...ids])]);
    }
  };

  const pickColumns = useMemo<ColumnsType<Operation>>(
    () => [
      {
        title: t('field.operation.code'),
        dataIndex: 'code',
        key: 'code',
        width: 112,
        ellipsis: true,
      },
      {
        title: t('field.operation.name'),
        dataIndex: 'name',
        key: 'name',
        width: 140,
        ellipsis: true,
      },
      {
        title: t('app.master-data.operationSequence.reportingType'),
        key: 'reportingType',
        width: 108,
        render: (_: unknown, record) =>
          renderOperationReportingTypeMarker(
            t,
            record.reportingType ?? (record as { reporting_type?: string }).reporting_type,
          ),
      },
      {
        title: t('app.master-data.operationSequence.pickColDescription'),
        key: 'description',
        ellipsis: true,
        render: (_: unknown, record) => (
          <Typography.Text type="secondary" ellipsis style={{ fontSize: 12 }}>
            {record.description?.trim() || t('common.empty')}
          </Typography.Text>
        ),
      },
    ],
    [t],
  );

  const handlePickRowSelectionChange = (keys: React.Key[]) => {
    if (mode === 'single') {
      onSingleChange?.(keys[0] != null ? String(keys[0]) : undefined);
      return;
    }
    if (!onMultipleChange) return;
    const inViewIds = new Set(filtered.map((o) => o.uuid));
    const keptOutsideView = multipleValue.filter((id) => !inViewIds.has(id));
    onMultipleChange([...keptOutsideView, ...keys.map(String)]);
  };

  return (
    <div>
      <Input.Search
        allowClear
        placeholder={searchPlaceholder}
        value={keyword}
        onChange={(e) => setKeyword(e.target.value)}
        style={{ marginBottom: 8 }}
      />
      {mode === 'multiple' ? (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('app.master-data.operationSequence.pickSelected', { count: multipleValue.length })}
          </Typography.Text>
          <Space size={0}>
            {onQuickAdd ? (
              <Button type="link" size="small" icon={<PlusOutlined />} onClick={onQuickAdd}>
                {quickAddLabel ?? t('app.master-data.operationSequence.quickAddOperation')}
              </Button>
            ) : null}
            <Button type="link" size="small" disabled={!filtered.length} onClick={handleSelectAllFiltered}>
              {t('app.master-data.operationSequence.pickSelectAll')}
            </Button>
            <Button
              type="link"
              size="small"
              disabled={!multipleValue.length}
              onClick={() => onMultipleChange?.([])}
            >
              {t('app.master-data.operationSequence.pickClear')}
            </Button>
          </Space>
        </div>
      ) : onQuickAdd ? (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
          <Button type="link" size="small" icon={<PlusOutlined />} onClick={onQuickAdd}>
            {quickAddLabel ?? t('app.master-data.operationSequence.quickAddOperation')}
          </Button>
        </div>
      ) : null}
      {mode === 'multiple' && selectedOperations.length > 0 ? (
        <div style={{ marginBottom: 8 }}>
          <Space wrap size={[4, 4]}>
            {selectedOperations.map((op) => (
              <Tag
                key={op.uuid}
                closable
                onClose={() => onMultipleChange?.(multipleValue.filter((id) => id !== op.uuid))}
              >
                {op.code} - {op.name}
              </Tag>
            ))}
          </Space>
        </div>
      ) : null}
      <div style={{ minHeight: OPERATION_PICK_TABLE_MIN_HEIGHT }}>
        <Table<Operation>
          size="small"
          rowKey="uuid"
          loading={loading}
          pagination={false}
          scroll={{ x: 520, y: OPERATION_PICK_TABLE_SCROLL_Y }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={t('app.master-data.operationSequence.noAvailableOperations')}
              />
            ),
          }}
          dataSource={filtered}
          columns={pickColumns}
          rowSelection={{
            type: mode === 'multiple' ? 'checkbox' : 'radio',
            columnWidth: mode === 'multiple' ? 48 : 40,
            preserveSelectedRowKeys: true,
            selectedRowKeys:
              mode === 'multiple'
                ? multipleValue
                : singleValue
                  ? [singleValue]
                  : [],
            onChange: handlePickRowSelectionChange,
          }}
          onRow={(record) => ({
            onClick: () => {
              if (mode === 'single') {
                onSingleChange?.(record.uuid);
                return;
              }
              const checked = multipleValue.includes(record.uuid);
              if (checked) {
                onMultipleChange?.(multipleValue.filter((id) => id !== record.uuid));
              } else {
                onMultipleChange?.([...multipleValue, record.uuid]);
              }
            },
            style: { cursor: 'pointer' },
          })}
          style={{ background: token.colorFillAlter, borderRadius: 6 }}
        />
      </div>
    </div>
  );
};

export interface OperationItem {
  uuid: string;
  code: string;
  name: string;
  description?: string;
  reportingType?: 'quantity' | 'status';
  /** 节点工序：仅在路线允许工序跳转时生效 */
  isNodeOperation?: boolean;
  /** 工序级超报（写入路线 JSON；none+0 可不提交键以继承路线默认） */
  overReportMode?: 'none' | 'fixed' | 'percent';
  overReportValue?: number;
  /** 标准工时（界面值 + 单位 + 件数基准；写入路线 operation_sequence） */
  standardTime?: number;
  standardTimeQty?: number;
  standardTimeUnit?: 'h' | 'm' | 's';
  /** 准备时间（界面分钟；落库为小时） */
  setupTime?: number;
  /** 工价/计件单价（元），写入路线 operation_sequence */
  pieceRate?: number;
  /** 计划工序委外（写入路线 operation_sequence） */
  isOutsourced?: boolean;
  outsourceLeadTimeDays?: number;
  outsourceSupplierId?: number;
  outsourceSupplierName?: string;
  /** 过程检验（路线步骤覆盖工序主数据，写入 operation_sequence） */
  inspectionMode?: 'none' | 'simple' | 'plan';
  /** @deprecated 兼容首方案；优先用 inspectionPlanIds */
  inspectionPlanId?: number;
  inspectionPlanName?: string;
  /** 有序多方案（先外观后尺寸） */
  inspectionPlanIds?: number[];
  inspectionPlanNames?: string[];
}

export interface OperationSequenceEditorProps {
  value?: OperationItem[];
  onChange?: (operations: OperationItem[]) => void;
  /** 为 true 时显示「节点工序」列（与路线「允许工序跳转」联动） */
  showNodeOperationColumn?: boolean;
  /** 工艺路线 / 产品工艺：显示工时、工价列 */
  showTimeColumns?: boolean;
  /** 嵌套在 FormModal 内时传入，保证工序选择弹窗叠在父弹窗之上 */
  nestedModalZIndex?: number;
  /** 工序选择弹窗打开/关闭时通知父级（用于 Escape 等快捷键不关闭父弹窗） */
  onPickModalOpenChange?: (open: boolean) => void;
}

export const OperationSequenceEditor: React.FC<OperationSequenceEditorProps> = ({
  value = [],
  onChange,
  showNodeOperationColumn = false,
  showTimeColumns = false,
  nestedModalZIndex,
  onPickModalOpenChange,
}) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const pickModalZIndex =
    nestedModalZIndex ??
    token.zIndexPopupBase + MODAL_ABOVE_DETAIL_SIDECHAIN_OFFSET + MODAL_NESTED_ABOVE_PARENT_OFFSET;
  const effectivePickModalZIndex = Math.max(pickModalZIndex, FILE_PREVIEW_OVERLAY_Z_INDEX);
  const operationFormModalZIndex = effectivePickModalZIndex + MODAL_NESTED_ABOVE_PARENT_OFFSET;
  const selectPopupZIndex = effectivePickModalZIndex;
  const operations = value ?? [];
  const operationsRef = useRef(operations);
  operationsRef.current = operations;
  const commitOperations = useCallback(
    (next: OperationItem[]) => {
      onChange?.(next);
    },
    [onChange],
  );
  const [allOperations, setAllOperations] = useState<Operation[]>([]);
  const [supplierOptions, setSupplierOptions] = useState<Array<{ value: number; label: string }>>([]);
  const [processPlanOptions, setProcessPlanOptions] = useState<
    Array<{ value: number; label: string; name: string }>
  >([]);
  const [operationsCatalogLoading, setOperationsCatalogLoading] = useState(false);
  const [addModalVisible, setAddModalVisible] = useState(false);
  const [selectedOperationUuids, setSelectedOperationUuids] = useState<string[]>([]);
  const [replaceModalVisible, setReplaceModalVisible] = useState(false);
  const [operationFormModalOpen, setOperationFormModalOpen] = useState(false);
  const [inspectionPlanQuickAddOpen, setInspectionPlanQuickAddOpen] = useState(false);
  const [inspectionPlanQuickAddTargetUuid, setInspectionPlanQuickAddTargetUuid] = useState<string | null>(
    null,
  );
  const [replacingOperationUuid, setReplacingOperationUuid] = useState<string | null>(null);
  const [replacementOperationUuid, setReplacementOperationUuid] = useState<string | undefined>(undefined);
  const [draggingUuid, setDraggingUuid] = useState<string | null>(null);

  useEffect(() => {
    onPickModalOpenChange?.(
      addModalVisible || replaceModalVisible || operationFormModalOpen || inspectionPlanQuickAddOpen,
    );
  }, [
    addModalVisible,
    replaceModalVisible,
    operationFormModalOpen,
    inspectionPlanQuickAddOpen,
    onPickModalOpenChange,
  ]);

  const suppliersLoadedRef = useRef(false);

  const loadAllOperations = useCallback(async () => {
    try {
      setOperationsCatalogLoading(true);
      const list = await fetchActiveOperationCatalog();
      setAllOperations(list);
    } catch (error: any) {
      message.error(error.message || t('app.master-data.operationSequence.loadListFailed'));
    } finally {
      setOperationsCatalogLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void loadAllOperations();
  }, [loadAllOperations]);

  const loadSupplierOptions = useCallback(async () => {
    if (suppliersLoadedRef.current) return;
    try {
      const result = await supplierApi.list({ limit: 1000, isActive: true });
      const items = unwrapSupplyPagedList(result);
      setSupplierOptions(
        items
          .map((s: { id?: number; code?: string; name?: string }) => ({
            value: Number(s.id),
            label: s.code ? `${s.code} ${s.name ?? ''}` : String(s.name ?? s.id),
          }))
          .filter((o) => Number.isFinite(o.value) && o.value > 0),
      );
      suppliersLoadedRef.current = true;
    } catch {
      setSupplierOptions([]);
    }
  }, []);

  const loadProcessPlanOptions = useCallback(async () => {
    try {
      const plans = unwrapInspectionPlanList(await inspectionPlanApi.list({ limit: 500 }));
      setProcessPlanOptions(
        (plans as Array<Record<string, unknown>>)
          .filter((p) => String(p.plan_type || p.planType || '') === 'process')
          .map((p) => {
            const id = Number(p.id);
            const code = String(p.plan_code || p.planCode || '');
            const name = String(p.plan_name || p.planName || '');
            const active = p.is_active ?? p.isActive;
            const inactiveHint =
              active === false ? ` (${t('common.disabled', { defaultValue: '停用' })})` : '';
            return {
              value: id,
              name: name || code || String(id),
              label: `${code ? `${code} ` : ''}${name}${inactiveHint}`.trim(),
            };
          })
          .filter((o) => Number.isFinite(o.value) && o.value > 0),
      );
    } catch {
      setProcessPlanOptions([]);
    }
  }, [t]);

  useEffect(() => {
    void loadProcessPlanOptions();
  }, [loadProcessPlanOptions]);

  const patchOutsource = useCallback(
    (uuid: string, patch: Partial<OperationItem>) => {
      commitOperations(
        operationsRef.current.map((op) => (op.uuid === uuid ? { ...op, ...patch } : op)),
      );
    },
    [commitOperations],
  );

  const patchInspection = useCallback(
    (uuid: string, patch: Partial<OperationItem>) => {
      commitOperations(
        operationsRef.current.map((op) => (op.uuid === uuid ? { ...op, ...patch } : op)),
      );
    },
    [commitOperations],
  );

  const handleInspectionPlanQuickCreated = useCallback(
    async (created: InspectionPlanRecord) => {
      const targetUuid = inspectionPlanQuickAddTargetUuid;
      const id = created?.id != null ? Number(created.id) : NaN;
      const name = String(created.plan_name ?? '').trim();
      const code = String(created.plan_code ?? '').trim();
      const label = `${code ? `${code} ` : ''}${name}`.trim() || String(id);
      const row = targetUuid
        ? operationsRef.current.find((op) => op.uuid === targetUuid)
        : undefined;
      const prevIds = row?.inspectionPlanIds?.length
        ? row.inspectionPlanIds
        : row?.inspectionPlanId != null
          ? [row.inspectionPlanId]
          : [];
      const prevNames = row?.inspectionPlanNames ?? [];
      const nameById = new Map(processPlanOptions.map((p) => [p.value, p.name] as const));
      await loadProcessPlanOptions();
      if (Number.isFinite(id) && id > 0) {
        setProcessPlanOptions((prev) =>
          prev.some((o) => o.value === id)
            ? prev
            : [...prev, { value: id, name: name || code || String(id), label }],
        );
        if (targetUuid) {
          const nextIds = [
            ...new Set([...prevIds.map(Number).filter((n) => Number.isFinite(n) && n > 0), id]),
          ];
          const names = nextIds.map((planId, idx) => {
            if (planId === id) return name || code || label;
            return prevNames[idx] || nameById.get(planId) || '';
          });
          patchInspection(targetUuid, {
            inspectionMode: 'plan',
            inspectionPlanIds: nextIds,
            inspectionPlanNames: names,
            inspectionPlanId: nextIds[0],
            inspectionPlanName: names[0] || undefined,
          });
        }
      }
      setInspectionPlanQuickAddTargetUuid(null);
    },
    [inspectionPlanQuickAddTargetUuid, loadProcessPlanOptions, patchInspection, processPlanOptions],
  );

  const handleOperationQuickCreateSuccess = useCallback(
    (created: Operation) => {
      mergeOperationIntoActiveCatalog(created);
      setAllOperations((prev) => {
        if (prev.some((op) => op.uuid === created.uuid)) return prev;
        return [...prev, created];
      });
      if (addModalVisible && !operations.some((op) => op.uuid === created.uuid)) {
        setSelectedOperationUuids((prev) => [...new Set([...prev, created.uuid])]);
      }
      if (replaceModalVisible) {
        setReplacementOperationUuid(created.uuid);
      }
    },
    [addModalVisible, replaceModalVisible, operations],
  );

  const handleNativeDragStart = useCallback((uuid: string, e: React.DragEvent<HTMLSpanElement>) => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData(OPERATION_ROW_DRAG_MIME, uuid);
    setDraggingUuid(uuid);
  }, []);

  const handleNativeDragEnd = useCallback(() => {
    setDraggingUuid(null);
  }, []);

  const handleNativeRowDragOver = useCallback((e: React.DragEvent<HTMLTableRowElement>) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  }, []);

  const handleNativeRowDrop = useCallback(
    (targetUuid: string, e: React.DragEvent<HTMLTableRowElement>) => {
      e.preventDefault();
      const sourceUuid = e.dataTransfer.getData(OPERATION_ROW_DRAG_MIME);
      if (!sourceUuid) {
        setDraggingUuid(null);
        return;
      }
      commitOperations(moveOperationList(operations, sourceUuid, targetUuid));
      setDraggingUuid(null);
    },
    [commitOperations, operations],
  );

  const handleAddOperation = () => {
    if (!selectedOperationUuids?.length) {
      message.warning(t('app.master-data.operationSequence.selectToAdd'));
      return;
    }
    const newOperations = selectedOperationUuids
      .map((uuid) => allOperations.find((op) => op.uuid === uuid))
      .filter((op): op is Operation => !!op && !operations.some((e) => e.uuid === op.uuid));
    if (newOperations.length === 0) {
      message.warning(t('app.master-data.operationSequence.allAddedOrNotFound'));
      return;
    }
    const newItems: OperationItem[] = newOperations.map((op) => {
      const ipqc = ipqcFromOperation(op);
      return {
        uuid: op.uuid,
        code: op.code,
        name: op.name,
        description: op.description,
        reportingType: (op.reportingType ?? (op as any).reporting_type ?? 'quantity') as 'quantity' | 'status',
        isNodeOperation: false,
        overReportMode: (op as any).overReportMode ?? (op as any).over_report_mode ?? 'none',
        overReportValue: Number((op as any).overReportValue ?? (op as any).over_report_value ?? 0) || 0,
        inspectionMode: ipqc.inspectionMode,
        inspectionPlanId: ipqc.inspectionPlanId,
        inspectionPlanName: ipqc.inspectionPlanName,
        inspectionPlanIds: ipqc.inspectionPlanIds ?? [],
        inspectionPlanNames: ipqc.inspectionPlanNames ?? [],
      };
    });
    commitOperations([...operations, ...newItems]);
    setAddModalVisible(false);
    setSelectedOperationUuids([]);
    message.success(t('app.master-data.operationSequence.addSuccess', { count: newItems.length }));
  };

  const handleDeleteOperation = (uuid: string) => {
    const next = operations.filter((op) => op.uuid !== uuid);
    if (next.length === operations.length) {
      message.warning(t('app.master-data.operationSequence.replaceNotFound'));
      return;
    }
    commitOperations(next);
  };

  const toggleNodeOperation = (uuid: string, checked: boolean) => {
    commitOperations(operations.map((op) => (op.uuid === uuid ? { ...op, isNodeOperation: checked } : op)));
  };

  const patchOverReport = (uuid: string, patch: Partial<Pick<OperationItem, 'overReportMode' | 'overReportValue'>>) => {
    commitOperations(operations.map((op) => (op.uuid === uuid ? { ...op, ...patch } : op)));
  };

  const patchTime = (
    uuid: string,
    patch: Partial<
      Pick<
        OperationItem,
        'standardTime' | 'standardTimeQty' | 'standardTimeUnit' | 'setupTime' | 'pieceRate'
      >
    >,
  ) => {
    commitOperations(operations.map((op) => (op.uuid === uuid ? { ...op, ...patch } : op)));
  };

  const changeStandardTimeUnit = (uuid: string, nextUnit: ManufacturingTimeUnit) => {
    const row = operations.find((op) => op.uuid === uuid);
    if (!row) return;
    const prevUnit = normalizeTimeUnit(row.standardTimeUnit);
    const seconds = toSeconds(row.standardTime, prevUnit);
    patchTime(uuid, {
      standardTimeUnit: nextUnit,
      standardTime: fromSeconds(seconds, nextUnit),
    });
  };

  const handleOpenReplaceModal = (uuid: string) => {
    setReplacingOperationUuid(uuid);
    setReplacementOperationUuid(undefined);
    setReplaceModalVisible(true);
  };

  const handleReplaceOperation = () => {
    if (!replacingOperationUuid || !replacementOperationUuid) {
      message.warning(t('app.master-data.operationSequence.selectToReplace'));
      return;
    }
    if (replacingOperationUuid === replacementOperationUuid) {
      message.warning(t('app.master-data.operationSequence.cannotReplaceSame'));
      return;
    }
    if (operations.some((op) => op.uuid === replacementOperationUuid && op.uuid !== replacingOperationUuid)) {
      message.warning(t('app.master-data.operationSequence.alreadyInList'));
      return;
    }
    const replacingIndex = operations.findIndex((op) => op.uuid === replacingOperationUuid);
    const replacement = allOperations.find((op) => op.uuid === replacementOperationUuid);
    if (replacingIndex === -1 || !replacement) {
      message.error(t('app.master-data.operationSequence.replaceNotFound'));
      return;
    }
    const ipqc = ipqcFromOperation(replacement);
    const newOperations = [...operations];
    newOperations[replacingIndex] = {
      uuid: replacement.uuid,
      code: replacement.code,
      name: replacement.name,
      description: replacement.description,
      reportingType: (replacement.reportingType ?? (replacement as any).reporting_type ?? 'quantity') as 'quantity' | 'status',
      isNodeOperation: false,
      overReportMode: (replacement as any).overReportMode ?? (replacement as any).over_report_mode ?? 'none',
      overReportValue: Number((replacement as any).overReportValue ?? (replacement as any).over_report_value ?? 0) || 0,
      inspectionMode: ipqc.inspectionMode,
      inspectionPlanId: ipqc.inspectionPlanId,
      inspectionPlanName: ipqc.inspectionPlanName,
      inspectionPlanIds: ipqc.inspectionPlanIds ?? [],
      inspectionPlanNames: ipqc.inspectionPlanNames ?? [],
    };
    commitOperations(newOperations);
    setReplaceModalVisible(false);
    setReplacingOperationUuid(null);
    setReplacementOperationUuid(undefined);
    message.success(t('app.master-data.operationSequence.replaceSuccess'));
  };

  useSubmitShortcut(
    addModalVisible ? handleAddOperation : replaceModalVisible ? handleReplaceOperation : undefined,
    addModalVisible || replaceModalVisible,
  );

  const availableOperations = allOperations.filter((op) => !operations.some((a) => a.uuid === op.uuid));
  const getAvailableForReplace = (excludeUuid: string | null) => {
    if (!excludeUuid) return availableOperations;
    return allOperations.filter((op) => op.uuid === excludeUuid || !operations.some((a) => a.uuid === op.uuid));
  };

  /** 任一行开启计划委外时才展示提前期 / 委外供应商列 */
  const showOutsourceDetailColumns = operations.some((op) => !!op.isOutsourced);

  useEffect(() => {
    if (!showOutsourceDetailColumns) return;
    void loadSupplierOptions();
  }, [showOutsourceDetailColumns, loadSupplierOptions]);

  const pickListLoading = operationsCatalogLoading && allOperations.length === 0;

  /** 与昨日布局一致：scroll.x ≥ 列宽之和，避免挤列；弹窗加宽后仍按列宽总和滚动 */
  const tableScrollX = useMemo(() => {
    // 序号(左固定) + 工序 + 报工 + 质检模式 + 检验方案 + 计划委外 + 超报 + 操作(右固定)
    let w = 100 + 220 + 120 + 148 + 280 + 88 + 200 + 100;
    if (showOutsourceDetailColumns) w += 100 + 180;
    if (showNodeOperationColumn) w += 88;
    if (showTimeColumns) w += 312 + 120;
    return w;
  }, [showNodeOperationColumn, showTimeColumns, showOutsourceDetailColumns]);

  const selectPopupProps = useMemo(
    () => ({
      getPopupContainer: () => document.body,
      styles: { popup: { root: { zIndex: selectPopupZIndex } } },
    }),
    [selectPopupZIndex],
  );

  const columns: ColumnsType<OperationItem> = [
      {
        title: t('app.master-data.operationSequence.index'),
        key: 'index',
        width: 100,
        fixed: 'left',
        render: (_: unknown, record: OperationItem, index: number) => (
          <SequenceIndexCell
            index={index}
            token={token}
            dragSortTitle={t('app.master-data.operationSequence.dragSort')}
            nativeDragHandle={{
              isDragging: draggingUuid === record.uuid,
              onDragStart: (e) => handleNativeDragStart(record.uuid, e),
              onDragEnd: handleNativeDragEnd,
            }}
          />
        ),
      },
      {
        title: t('app.master-data.operationSequence.operationCodeName'),
        key: 'operation',
        width: 220,
        ellipsis: true,
        render: (_: unknown, record: OperationItem) => (
          <div style={{ whiteSpace: 'nowrap' }}>
            <div style={{ fontWeight: 500 }}>
              {record.code} - {record.name}
            </div>
            {record.description ? (
              <div
                style={{
                  fontSize: 12,
                  color: token.colorTextSecondary,
                  marginTop: 4,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
              >
                {record.description}
              </div>
            ) : null}
          </div>
        ),
      },
      {
        title: t('app.master-data.operationSequence.reportingType'),
        key: 'reportingType',
        width: 120,
        render: (_: unknown, record: OperationItem) =>
          renderOperationReportingTypeMarker(t, record.reportingType),
      },
      ...(showNodeOperationColumn
        ? [
            {
              title: t('app.master-data.operationSequence.nodeOperation'),
              key: 'isNodeOperation',
              width: 88,
              render: (_: unknown, record: OperationItem) => (
                <Switch
                  size="small"
                  checked={!!record.isNodeOperation}
                  onChange={(c) => toggleNodeOperation(record.uuid, c)}
                />
              ),
            },
          ]
        : []),
      ...(showTimeColumns
        ? [
            {
              title: t('app.master-data.manufacturing.standardTime'),
              key: 'standardTime',
              width: 312,
              render: (_: unknown, record: OperationItem) => (
                <Space.Compact style={{ display: 'inline-flex', flexWrap: 'nowrap', maxWidth: '100%' }}>
                  <InputNumber
                    size="small"
                    min={0}
                    step={0.01}
                    precision={2}
                    style={{ width: 76 }}
                    placeholder="0"
                    value={record.standardTime}
                    onChange={(v) => patchTime(record.uuid, { standardTime: v ?? undefined })}
                  />
                  <Select
                    size="small"
                    style={{ width: 68 }}
                    value={normalizeTimeUnit(record.standardTimeUnit)}
                    options={TIME_UNIT_OPTIONS.map((o) => ({
                      value: o.value,
                      label: t(o.labelKey),
                    }))}
                    {...selectPopupProps}
                    onChange={(u) => changeStandardTimeUnit(record.uuid, u as ManufacturingTimeUnit)}
                  />
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '0 6px',
                      color: token.colorTextSecondary,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    /
                  </span>
                  <InputNumber
                    size="small"
                    min={1}
                    step={1}
                    precision={0}
                    style={{ width: 76 }}
                    value={record.standardTimeQty ?? 1}
                    onChange={(v) =>
                      patchTime(record.uuid, {
                        standardTimeQty: v != null && Number(v) >= 1 ? Number(v) : 1,
                      })
                    }
                  />
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '0 8px',
                      background: token.colorFillAlter,
                      border: `1px solid ${token.colorBorder}`,
                      borderLeft: 0,
                      borderRadius: '0 6px 6px 0',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {t('app.master-data.manufacturing.pieceUnit')}
                  </span>
                </Space.Compact>
              ),
            },
            {
              title: t('app.master-data.manufacturing.laborPrice'),
              key: 'pieceRate',
              width: 120,
              render: (_: unknown, record: OperationItem) => (
                <InputNumber
                  size="small"
                  min={0}
                  precision={2}
                  step={0.01}
                  style={{ width: '100%' }}
                  suffix={t('app.master-data.manufacturing.yuanPerPieceUnit')}
                  placeholder="0"
                  value={record.pieceRate}
                  onChange={(v) =>
                    patchTime(record.uuid, {
                      pieceRate: v != null && Number.isFinite(Number(v)) ? Number(v) : undefined,
                    })
                  }
                />
              ),
            },
          ]
        : []),
      {
        title: t('app.master-data.operationSequence.inspectionMode'),
        key: 'inspectionMode',
        width: 148,
        render: (_: unknown, record: OperationItem) => {
          const mode = record.inspectionMode ?? 'none';
          return (
            <Select
              size="small"
              style={{ width: '100%' }}
              value={mode}
              options={[
                { value: 'none', label: t('field.operation.inspectionModeNone') },
                { value: 'simple', label: t('field.operation.inspectionModeSimple') },
                { value: 'plan', label: t('field.operation.inspectionModePlan') },
              ]}
              {...selectPopupProps}
              onChange={(v) => {
                const nextMode = (v || 'none') as OperationItem['inspectionMode'];
                if (nextMode !== 'plan') {
                  patchInspection(record.uuid, {
                    inspectionMode: nextMode,
                    inspectionPlanId: undefined,
                    inspectionPlanName: undefined,
                    inspectionPlanIds: [],
                    inspectionPlanNames: [],
                  });
                  return;
                }
                patchInspection(record.uuid, {
                  inspectionMode: 'plan',
                  inspectionPlanIds: record.inspectionPlanIds?.length
                    ? record.inspectionPlanIds
                    : record.inspectionPlanId
                      ? [record.inspectionPlanId]
                      : [],
                  inspectionPlanId: record.inspectionPlanId,
                  inspectionPlanName: record.inspectionPlanName,
                  inspectionPlanNames: record.inspectionPlanNames,
                });
              }}
            />
          );
        },
      },
      {
        title: t('app.master-data.operationSequence.inspectionPlan'),
        key: 'inspectionPlanIds',
        width: 280,
        render: (_: unknown, record: OperationItem) => {
          const mode = record.inspectionMode ?? 'none';
          const value =
            mode === 'plan'
              ? (record.inspectionPlanIds?.length
                  ? record.inspectionPlanIds
                  : record.inspectionPlanId != null
                    ? [record.inspectionPlanId]
                    : [])
              : [];
          return (
            <UniDropdown
              size="small"
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              style={{ width: '100%' }}
              disabled={mode !== 'plan'}
              options={processPlanOptions}
              value={value}
              placeholder={t('app.master-data.operationSequence.selectInspectionPlanOrdered')}
              // 表体内勿用 responsive（易整列收成 +N）；优先展示方案名，超出 2 个再 +N
              maxTagCount={2}
              maxTagPlaceholder={(omitted) => `+${omitted.length}`}
              tagRender={(props) => {
                const { value: tagValue, closable, onClose } = props;
                const opt = processPlanOptions.find((p) => p.value === Number(tagValue));
                const text = opt?.name || String(props.label ?? tagValue);
                return (
                  <Tag
                    closable={closable}
                    onClose={onClose}
                    style={{ marginInlineEnd: 4, maxWidth: 120 }}
                    title={opt?.label || text}
                  >
                    <span
                      style={{
                        display: 'inline-block',
                        maxWidth: 96,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        verticalAlign: 'bottom',
                      }}
                    >
                      {text}
                    </span>
                  </Tag>
                );
              }}
              quickCreate={
                mode === 'plan'
                  ? {
                      label: t('field.operation.quickAddInspectionPlan'),
                      onClick: () => {
                        setInspectionPlanQuickAddTargetUuid(record.uuid);
                        setInspectionPlanQuickAddOpen(true);
                      },
                    }
                  : undefined
              }
              {...selectPopupProps}
              onChange={(ids, opts) => {
                const nextIds = (Array.isArray(ids) ? ids : [])
                  .map((v) => Number(v))
                  .filter((n) => Number.isFinite(n) && n > 0);
                const optList = Array.isArray(opts) ? opts : opts ? [opts] : [];
                const labelById = new Map<number, string>();
                for (const opt of optList) {
                  const o = opt as { value?: number; label?: string };
                  if (o?.value != null) labelById.set(Number(o.value), String(o.label || ''));
                }
                const names = nextIds.map(
                  (id) =>
                    processPlanOptions.find((p) => p.value === id)?.name
                    || labelById.get(id)
                    || processPlanOptions.find((p) => p.value === id)?.label
                    || '',
                );
                patchInspection(record.uuid, {
                  inspectionMode: 'plan',
                  inspectionPlanIds: nextIds,
                  inspectionPlanNames: names,
                  inspectionPlanId: nextIds[0],
                  inspectionPlanName: names[0] || undefined,
                });
              }}
            />
          );
        },
      },      {
        title: t('app.master-data.operationSequence.plannedOutsource'),
        key: 'isOutsourced',
        width: 88,
        render: (_: unknown, record: OperationItem) => (
          <Switch
            size="small"
            checked={!!record.isOutsourced}
            onChange={(c) =>
              patchOutsource(record.uuid, {
                isOutsourced: c,
                outsourceLeadTimeDays: c ? record.outsourceLeadTimeDays ?? 1 : undefined,
                outsourceSupplierId: c ? record.outsourceSupplierId : undefined,
                outsourceSupplierName: c ? record.outsourceSupplierName : undefined,
              })
            }
          />
        ),
      },
      ...(showOutsourceDetailColumns
        ? [
            {
              title: t('app.master-data.operationSequence.outsourceLeadDays'),
              key: 'outsourceLeadTimeDays',
              width: 100,
              render: (_: unknown, record: OperationItem) => (
                <InputNumber
                  size="small"
                  min={0}
                  precision={0}
                  style={{ width: '100%' }}
                  disabled={!record.isOutsourced}
                  value={record.isOutsourced ? record.outsourceLeadTimeDays ?? 1 : undefined}
                  onChange={(v) =>
                    patchOutsource(record.uuid, {
                      outsourceLeadTimeDays: v == null ? 1 : Number(v),
                    })
                  }
                />
              ),
            },
            {
              title: t('app.master-data.operationSequence.outsourceSupplier'),
              key: 'outsourceSupplierId',
              width: 180,
              render: (_: unknown, record: OperationItem) => (
                <Select
                  size="small"
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  style={{ width: '100%' }}
                  disabled={!record.isOutsourced}
                  options={supplierOptions}
                  value={record.outsourceSupplierId}
                  placeholder={t('app.master-data.operationSequence.selectOutsourceSupplier')}
                  {...selectPopupProps}
                  onChange={(v, opt) => {
                    const label = Array.isArray(opt)
                      ? undefined
                      : (opt as { label?: string } | undefined)?.label;
                    patchOutsource(record.uuid, {
                      outsourceSupplierId: v == null ? undefined : Number(v),
                      outsourceSupplierName: v == null ? undefined : String(label || ''),
                    });
                  }}
                />
              ),
            },
          ]
        : []),
      {
        title: t('app.master-data.operationSequence.overReport'),
        key: 'overReport',
        width: 200,
        render: (_: unknown, record: OperationItem) => (
          <div
            style={{
              display: 'flex',
              flexWrap: 'nowrap',
              alignItems: 'center',
              gap: 8,
              whiteSpace: 'nowrap',
            }}
          >
            <Select
              size="small"
              style={{ width: 100, flexShrink: 0 }}
              value={record.overReportMode ?? 'none'}
              options={[
                { label: t('field.operation.overReportModeNone'), value: 'none' },
                { label: t('field.operation.overReportModeFixed'), value: 'fixed' },
                { label: t('field.operation.overReportModePercent'), value: 'percent' },
              ]}
              {...selectPopupProps}
              onChange={(v) => {
                const mode = v as OperationItem['overReportMode'];
                const next: Partial<Pick<OperationItem, 'overReportMode' | 'overReportValue'>> = {
                  overReportMode: mode,
                };
                if (mode === 'none') next.overReportValue = 0;
                else if (mode === 'percent' && (record.overReportValue ?? 0) > 100) {
                  next.overReportValue = 100;
                }
                patchOverReport(record.uuid, next);
              }}
            />
            <InputNumber
              size="small"
              min={0}
              max={(record.overReportMode ?? 'none') === 'percent' ? 100 : undefined}
              style={{ width: 88, flexShrink: 0 }}
              value={record.overReportValue ?? 0}
              onChange={(v) => patchOverReport(record.uuid, { overReportValue: v ?? 0 })}
            />
          </div>
        ),
      },
      {
        title: t('common.action'),
        key: 'action',
        width: 100,
        fixed: 'right',
        render: (_: unknown, record: OperationItem) => (
          <div
            style={{
              display: 'flex',
              flexWrap: 'nowrap',
              alignItems: 'center',
              gap: 4,
              whiteSpace: 'nowrap',
            }}
          >
            <Button
              type="link"
              size="small"
              style={{ paddingInline: 4, flexShrink: 0 }}
              onClick={() => handleOpenReplaceModal(record.uuid)}
            >
              {t('app.master-data.operationSequence.replace')}
            </Button>
            <Button
              type="link"
              size="small"
              danger
              style={{ paddingInline: 4, flexShrink: 0 }}
              onClick={() => handleDeleteOperation(record.uuid)}
            >
              {t('common.delete')}
            </Button>
          </div>
        ),
      },
    ];

  const pickModals = (
    <>
      <Modal
        title={t('app.master-data.operationSequence.selectOperation')}
        open={addModalVisible}
        centered={false}
        style={{ top: OPERATION_PICK_MODAL_TOP }}
        width={OPERATION_PICK_MODAL_WIDTH}
        zIndex={effectivePickModalZIndex}
        getContainer={() => document.body}
        destroyOnHidden
        styles={operationPickModalStyles}
        maskProps={{ ...MODAL_ISOLATE_POINTER_PROPS }}
        wrapProps={{ ...MODAL_ISOLATE_POINTER_PROPS }}
        onOk={handleAddOperation}
        onCancel={() => {
          setAddModalVisible(false);
          setSelectedOperationUuids([]);
        }}
        okText={t('common.confirm') + SUBMIT_SHORTCUT_HINT}
        cancelText={t('common.cancel')}
        okButtonProps={{ disabled: !selectedOperationUuids?.length || pickListLoading }}
      >
        <OperationPickPanel
          key={addModalVisible ? 'add-open' : 'add-closed'}
          mode="multiple"
          operations={availableOperations}
          loading={pickListLoading}
          multipleValue={selectedOperationUuids}
          onMultipleChange={setSelectedOperationUuids}
          searchPlaceholder={t('app.master-data.operationSequence.pickSearchPlaceholder')}
          onQuickAdd={() => setOperationFormModalOpen(true)}
        />
        {availableOperations.length === 0 && !pickListLoading && (
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
            {t('app.master-data.operationSequence.createOperationFirst')}
          </Typography.Text>
        )}
      </Modal>

      <Modal
        title={t('app.master-data.operationSequence.replaceOperation')}
        open={replaceModalVisible}
        centered={false}
        style={{ top: OPERATION_PICK_MODAL_TOP }}
        width={OPERATION_PICK_MODAL_WIDTH}
        zIndex={effectivePickModalZIndex}
        getContainer={() => document.body}
        destroyOnHidden
        styles={operationPickModalStyles}
        maskProps={{ ...MODAL_ISOLATE_POINTER_PROPS }}
        wrapProps={{ ...MODAL_ISOLATE_POINTER_PROPS }}
        onOk={handleReplaceOperation}
        onCancel={() => {
          setReplaceModalVisible(false);
          setReplacingOperationUuid(null);
          setReplacementOperationUuid(undefined);
        }}
        okText={t('common.confirm') + SUBMIT_SHORTCUT_HINT}
        cancelText={t('common.cancel')}
        okButtonProps={{ disabled: !replacementOperationUuid || pickListLoading }}
      >
        <div style={{ marginBottom: 12 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {t('app.master-data.operationSequence.currentOperation')}
          </Typography.Text>
          <div style={{ marginTop: 4 }}>
            {replacingOperationUuid &&
              (() => {
                const currentOp = operations.find((op) => op.uuid === replacingOperationUuid);
                return currentOp ? (
                  <Tag color="blue">
                    {currentOp.code} - {currentOp.name}
                  </Tag>
                ) : null;
              })()}
          </div>
        </div>
        <OperationPickPanel
          key={replaceModalVisible ? 'replace-open' : 'replace-closed'}
          mode="single"
          operations={getAvailableForReplace(replacingOperationUuid)}
          loading={pickListLoading}
          singleValue={replacementOperationUuid}
          onSingleChange={setReplacementOperationUuid}
          searchPlaceholder={t('app.master-data.operationSequence.pickSearchPlaceholder')}
          onQuickAdd={() => setOperationFormModalOpen(true)}
        />
        {getAvailableForReplace(replacingOperationUuid).length === 0 && !pickListLoading && (
          <Typography.Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 8 }}>
            {t('app.master-data.operationSequence.createOperationFirst')}
          </Typography.Text>
        )}
      </Modal>

      <OperationFormModal
        open={operationFormModalOpen}
        onClose={() => setOperationFormModalOpen(false)}
        editUuid={null}
        onSuccess={handleOperationQuickCreateSuccess}
        zIndex={operationFormModalZIndex}
      />

      {inspectionPlanQuickAddOpen ? (
        <InspectionPlanFormModal
          open
          onClose={() => {
            setInspectionPlanQuickAddOpen(false);
            setInspectionPlanQuickAddTargetUuid(null);
          }}
          editId={null}
          defaultPlanType="process"
          lockPlanType
          onSuccess={handleInspectionPlanQuickCreated}
          zIndex={operationFormModalZIndex}
        />
      ) : null}
    </>
  );

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ color: token.colorTextSecondary, fontSize: 12 }}>{t('app.master-data.operationSequence.hint')}</span>
        {operations.length > 0 ? (
          <Button type="dashed" icon={<PlusOutlined />} onClick={() => setAddModalVisible(true)} size="small">
            {t('app.master-data.operationSequence.addOperation')}
          </Button>
        ) : null}
      </div>
      {operations.length > 0 ? (
        <div style={{ position: 'relative', width: '100%', margin: 0, padding: 0 }}>
          <Table
            className="operation-sequence-editor-table"
            columns={columns}
            dataSource={operations}
            rowKey="uuid"
            pagination={false}
            size="small"
            style={{ width: '100%' }}
            scroll={{ x: tableScrollX }}
            onRow={(record) => ({
              onDragOver: handleNativeRowDragOver,
              onDrop: (e) => handleNativeRowDrop(record.uuid, e),
            })}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.master-data.operationSequence.noData')} /> }}
          />
        </div>
      ) : (
        <div
          className="operation-sequence-editor-empty"
          style={{
            padding: 24,
            background: token.colorFillAlter,
            borderRadius: token.borderRadius,
            border: '1px dashed var(--river-border-color)',
            textAlign: 'center',
          }}
        >
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.master-data.operationSequence.noDataAddHint')} />
          <Button type="primary" ghost icon={<PlusOutlined />} onClick={() => setAddModalVisible(true)} style={{ marginTop: 12 }}>
            {t('app.master-data.operationSequence.addOperation')}
          </Button>
        </div>
      )}

      {typeof document !== 'undefined' ? createPortal(pickModals, document.body) : pickModals}
    </div>
  );
};
