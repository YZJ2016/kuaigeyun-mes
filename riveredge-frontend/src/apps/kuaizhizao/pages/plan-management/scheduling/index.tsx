/**
 * 可视排产页面
 *
 * 基于甘特图拖拽调整工单/工序计划时间；待排工单区展示全部可排工单及排产问题。
 * MRP/LRP 运算请前往「需求计算」页面。
 */

import React, { useRef, useState, useCallback, lazy, Suspense, useMemo, useEffect } from 'react';
import { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button, Tag, Space, Card, Modal, Switch, Spin, Typography, Alert, InputNumber, Divider, Tour, ConfigProvider, Tooltip, Table, Select } from 'antd';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import type { ThemeConfig } from 'antd';
import { useRequest } from 'ahooks';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { UniTable } from '../../../../../components/uni-table';
import { renderInlineMarkerTagGroup } from '../../../../../components/inline-marker-tag-preview';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import {
  workOrderApi,
  schedulingConfigApi,
  visualSchedulingApi,
  SchedulingConstraints,
  VisualSchedulingBoardScan,
  VisualSchedulingMissingSetting,
} from '../../../services/production';
import { mesDashboardService } from '../../../services/dashboard';
import { rollingSchedulingApi } from '../../../services/rolling-scheduling';
import type {
  ViewMode,
  WorkOrderForGantt,
  WorkstationResource,
  GanttTaskLevel,
} from '../../../components/GanttSchedulingChart/types';
import type { GanttOperationAssignmentUpdate } from '../../../components/GanttSchedulingChart';
import { stationResourceId } from '../../../components/GanttSchedulingChart/stationResourceUtils';
import { resolveWorkerIdsForOperation } from '../../../components/GanttSchedulingChart/workerResourceUtils';
import {
  factoryListItems,
  productionLineApi,
  workstationApi,
  workCenterApi,
} from '../../../../master-data/services/factory';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { ROUTES } from '../../../constants/routes';
import dayjs from 'dayjs';
import {formatDateTime, formatQuantity} from '../../../../../utils/format';
import { apiRequest } from '../../../../../services/api';
import SchedulingHeaderBand from './components/SchedulingHeaderBand';
import SchedulingBoardDropZone from './components/SchedulingBoardDropZone';
import { collectWorkOrderDiagnosticIssues } from './components/schedulingPoolDiagnostics';
import SchedulingPoolToolbar from './components/SchedulingPoolToolbar';
import SchedulingWorkOrderPrepModal, {
  type SchedulingWorkOrderPrepValues,
} from './components/SchedulingWorkOrderPrepModal';
import SchedulingOperationEditDrawer, {
  type SchedulingOperationEditContext,
} from './components/SchedulingOperationEditDrawer';
import { convertEngineProposalToAiProposal } from './convertEngineProposal';
import { applySchedulingAiProposal } from './applySchedulingAiProposal';
import buildSchedulingGanttToolbar, { type SchedulingBoardMainView } from './components/SchedulingGanttToolbar';
import SchedulingLoadTable from './components/SchedulingLoadTable';
import SchedulingCardBoard from './components/SchedulingCardBoard';
import SchedulingPoolCardGrid from './components/SchedulingPoolCardGrid';
import SchedulingPinManagerModal from './components/SchedulingPinManagerModal';
import SchedulingRescheduleWizardModal, {
  type SchedulingEngineProposalPayload,
} from './components/SchedulingRescheduleWizardModal';
import SchedulingAlertsPanel from './components/SchedulingAlertsPanel';
import SchedulingDueEstimateDrawer from './components/SchedulingDueEstimateDrawer';
import { buildSchedulingPoolCardItems, type SchedulingCardResourceMove } from './schedulingCardViewUtils';
import {
  filterSchedulingEquipments,
  filterSchedulingWorkers,
  resolveUserRoles,
  type SchedulingEquipmentResource,
  type SchedulingResourceFilterValue,
  type SchedulingWorkerResource,
} from './schedulingResourceFilters';
import {
  SchedulingAiAssistantDrawer,
  SchedulingAiAssistantTrigger,
} from './components/SchedulingAiAssistantDrawer';
import {
  buildScheduleWorkOrderDrop,
  countScheduledOperations,
  countWorkOrderOperations,
  getWorkOrderSchedulingPrepContext,
  getOperationsForStationPrep,
  isWorkOrderScheduledOnBoard,
  mapOperationForGantt,
  mergeApiWorkOrderWithScheduled,
  mergeScheduledWorkOrderIntoBoard,
  pickFocusOperationTaskId,
  resolveGanttStationResourceIdFromPoint,
  stampProductionLineOnWorkOrder,
  workOrderNeedsSchedulingPrep,
  SCHEDULING_DRAG_WORK_ORDER,
  type OperationNeedingStation,
  type WorkOrderSchedulingMissingField,
} from './schedulingDropUtils';
import {
  buildMaterialGateConfirmDescription,
  filterWorkOrderIdsByMaterialGate,
  getMaterialIssueForWorkOrder,
  resolveMaterialGateDecision,
} from './schedulingMaterialGate';
import {
  loadSchedulingPinnedResources,
  pinnedIdsForLevel,
  saveSchedulingPinnedResources,
  type SchedulingPinnedResources,
} from './schedulingPinnedResources';
import {
  loadSchedulingBoardPreferences,
  saveSchedulingBoardPreferences,
} from './schedulingBoardPreferences';
import {
  buildFreezeAnchor,
  canShiftWorkOrder,
  isWorkOrderSchedulingLocked,
} from './freezeUtils';
import { ensureBatchUpdatesPersisted, reportBatchUpdateResult } from './batchResultUtils';
import {
  isSchedulableWorkOrderStatus,
  matchesPoolKeyword,
  type PoolStatusFilter,
} from './schedulingPoolUtils';
import './delfoi-style.less';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { searchUserDisplay } from '../../../../../services/user';
import { getEquipmentList } from '../../../../../services/equipment';
import { getMoldList } from '../../../../../services/mold';
import { toApiDateTimeString } from '../../../../../utils/formDate';
const GANTT_WORK_ORDER_LIMIT = 500;

/** 待排表格统一字号；行高沿用改字体前的 Table token（与甘特图 32px 行对齐） */
const SCHEDULING_POOL_FONT_SIZE = 13;
const SCHEDULING_POOL_ROW_HEIGHT = 32;

const SCHEDULING_POOL_TABLE_THEME: ThemeConfig = {
  components: {
    Table: {
      cellFontSizeSM: SCHEDULING_POOL_FONT_SIZE,
      cellPaddingBlockSM: Math.floor((SCHEDULING_POOL_ROW_HEIGHT - 20) / 2),
      cellPaddingInlineSM: 8,
    },
    Tag: {
      fontSizeSM: SCHEDULING_POOL_FONT_SIZE,
    },
    Typography: {
      fontSize: SCHEDULING_POOL_FONT_SIZE,
    },
    Pagination: {
      fontSize: SCHEDULING_POOL_FONT_SIZE,
    },
    Badge: {
      fontSize: SCHEDULING_POOL_FONT_SIZE,
      textFontSize: SCHEDULING_POOL_FONT_SIZE,
      textFontSizeSM: SCHEDULING_POOL_FONT_SIZE,
    },
    Segmented: {
      fontSize: SCHEDULING_POOL_FONT_SIZE,
    },
    Input: {
      fontSize: SCHEDULING_POOL_FONT_SIZE,
    },
    Button: {
      fontSize: SCHEDULING_POOL_FONT_SIZE,
    },
  },
};

const GanttSchedulingChart = lazy(() => import('../../../components/GanttSchedulingChart'));

const DEFAULT_SCHEDULING_CONSTRAINTS: SchedulingConstraints = {
  consider_human: true,
  consider_equipment: true,
  consider_material: true,
  consider_mold_tool: true,
  freeze_horizon_days: 2,
  rolling_horizon_days: 14,
  setup_changeover_hours: 1,
  schedule_mode: 'forward',
  material_hard_constraint: false,
  resource_mode: 'workstation',
  line_exclusive: true,
};

function pickVisualSchedulingConstraints(constraints: SchedulingConstraints): SchedulingConstraints {
  return {
    consider_human: constraints.consider_human,
    consider_equipment: constraints.consider_equipment,
    consider_material: constraints.consider_material,
    consider_mold_tool: constraints.consider_mold_tool,
    freeze_horizon_days: constraints.freeze_horizon_days ?? 2,
    rolling_horizon_days: constraints.rolling_horizon_days ?? 14,
    setup_changeover_hours: constraints.setup_changeover_hours ?? 1,
    schedule_mode: constraints.schedule_mode === 'backward' ? 'backward' : 'forward',
    material_hard_constraint: Boolean(constraints.material_hard_constraint),
    resource_mode: constraints.resource_mode === 'production_line' ? 'production_line' : 'workstation',
    line_exclusive: constraints.line_exclusive !== false,
  };
}

const SCHEDULING_FULLSCREEN_TIP_SESSION_KEY = 'kuaizhizao.scheduling.fullscreen.tip.tour.v3.shown';

function applyWorkOrderDateUpdates(
  list: WorkOrderForGantt[],
  updates: Array<{ work_order_id: number; planned_start_date: string; planned_end_date: string }>
): WorkOrderForGantt[] {
  if (updates.length === 0) return list;
  const byId = new Map(updates.map((u) => [u.work_order_id, u]));
  return list.map((wo) => {
    const patch = byId.get(wo.id);
    if (!patch) return wo;
    return { ...wo, planned_start_date: patch.planned_start_date, planned_end_date: patch.planned_end_date };
  });
}

function applyOperationDateUpdates(
  list: WorkOrderForGantt[],
  updates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }>
): WorkOrderForGantt[] {
  if (updates.length === 0) return list;
  const byOpId = new Map(updates.map((u) => [u.operation_id, u]));
  return list.map((wo) => {
    if (!wo.operations?.length) return wo;
    let changed = false;
    const operations = wo.operations.map((op) => {
      const opId = op.id;
      if (opId == null) return op;
      const patch = byOpId.get(opId);
      if (!patch) return op;
      changed = true;
      return { ...op, planned_start_date: patch.planned_start_date, planned_end_date: patch.planned_end_date };
    });
    return changed ? { ...wo, operations } : wo;
  });
}

function applyOperationStationUpdates(
  list: WorkOrderForGantt[],
  updates: Array<{ operation_id: number; assigned_station_id: number }>,
  options?: { asProductionLine?: boolean }
): WorkOrderForGantt[] {
  if (updates.length === 0) return list;
  const byOpId = new Map(updates.map((u) => [u.operation_id, u.assigned_station_id]));
  const asLine = Boolean(options?.asProductionLine);
  return list.map((wo) => {
    if (!wo.operations?.length) return wo;
    let changed = false;
    const operations = wo.operations.map((op) => {
      const opId = op.id;
      if (opId == null) return op;
      const stationId = byOpId.get(opId);
      if (stationId == null) return op;
      changed = true;
      return {
        ...op,
        assigned_station_id: stationId,
        ...(asLine ? { assigned_production_line_id: stationId } : {}),
      };
    });
    return changed ? { ...wo, operations } : wo;
  });
}

const SchedulingPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi, modal } = App.useApp();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const filterWorkOrderIds = useMemo(() => {
    const raw = searchParams.get('work_order_ids');
    if (!raw) return undefined;
    const ids = raw.split(',').map((s) => Number(s.trim())).filter((n) => !Number.isNaN(n) && n > 0);
    return ids.length > 0 ? ids : undefined;
  }, [searchParams]);
  const filterPlanDate = useMemo(() => {
    const raw = searchParams.get('plan_date')?.trim();
    return raw || undefined;
  }, [searchParams]);

  const actionRef = useRef<ActionType>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [ganttViewMode, setGanttViewMode] = useState<ViewMode>('week');
  const [boardMainView, setBoardMainView] = useState<SchedulingBoardMainView>(
    () => loadSchedulingBoardPreferences().boardMainView
  );
  const [ganttTaskLevel, setGanttTaskLevel] = useState<GanttTaskLevel>(
    () => loadSchedulingBoardPreferences().taskLevel
  );
  const [fullscreenTourOpen, setFullscreenTourOpen] = useState(false);
  const [configDrawerOpen, setConfigDrawerOpen] = useState(false);
  const [schedulingConstraints, setSchedulingConstraints] = useState(DEFAULT_SCHEDULING_CONSTRAINTS);
  const [configSaving, setConfigSaving] = useState(false);
  const [poolKeyword, setPoolKeyword] = useState('');
  const [poolAppliedKeyword, setPoolAppliedKeyword] = useState('');
  const [poolStatusFilter, setPoolStatusFilter] = useState<PoolStatusFilter>('all');
  const [poolOverdueOnly, setPoolOverdueOnly] = useState(false);
  const [lastBlockedTaskId, setLastBlockedTaskId] = useState<string>('');
  const [shiftDays, setShiftDays] = useState(1);
  const [batchActionLoading, setBatchActionLoading] = useState(false);
  const [quickActionLoading, setQuickActionLoading] = useState(false);
  const [boardScan, setBoardScan] = useState<VisualSchedulingBoardScan | null>(null);
  const [focusTaskId, setFocusTaskId] = useState<string | null>(null);
  const [scrollToTodayToken, setScrollToTodayToken] = useState(0);
  const [draftMode, setDraftMode] = useState(false);
  const [draftPendingCount, setDraftPendingCount] = useState(0);
  const [prepModalOpen, setPrepModalOpen] = useState(false);
  const [prepModalWorkOrder, setPrepModalWorkOrder] = useState<WorkOrderForGantt | null>(null);
  const [prepModalMissing, setPrepModalMissing] = useState<WorkOrderSchedulingMissingField[]>([]);
  const [prepModalOperationsNeedingStation, setPrepModalOperationsNeedingStation] = useState<
    OperationNeedingStation[]
  >([]);
  const [prepModalSaving, setPrepModalSaving] = useState(false);
  const [prepModalLoading, setPrepModalLoading] = useState(false);
  const [aiDrawerOpen, setAiDrawerOpen] = useState(false);
  const [aiSuggestedPoolOrderIds, setAiSuggestedPoolOrderIds] = useState<number[]>([]);
  const [autoRescheduleLoading, setAutoRescheduleLoading] = useState(false);
  const [rescheduleWizardOpen, setRescheduleWizardOpen] = useState(false);
  const [rescheduleWizardIds, setRescheduleWizardIds] = useState<number[]>([]);
  const [dueEstimateOpen, setDueEstimateOpen] = useState(false);
  const [missingSettingsModalOpen, setMissingSettingsModalOpen] = useState(false);
  /** 补齐弹窗：来自 boardScan gaps 的 product_id（甘特未加载工单时兜底） */
  const [missingSettingsProductByWo, setMissingSettingsProductByWo] = useState<Map<number, number>>(
    () => new Map()
  );
  const [missingSettingsRows, setMissingSettingsRows] = useState<
    Array<{
      operation_id: number;
      work_order_id: number;
      work_order_code: string;
      operation_name: string;
      work_center_id?: number | null;
      needHours: boolean;
      needStation: boolean;
      /** 产线模式：缺节拍/日产能，不可在本弹窗回写 */
      needCapacity: boolean;
      setup_time: number | null;
      standard_time: number | null;
      assigned_station_id: number | null;
    }>
  >([]);
  const [missingSettingsSaving, setMissingSettingsSaving] = useState(false);
  const [pendingAutoRescheduleIds, setPendingAutoRescheduleIds] = useState<number[] | null>(null);
  const [operationEditContext, setOperationEditContext] = useState<SchedulingOperationEditContext | null>(null);
  const [operationEditOpen, setOperationEditOpen] = useState(false);
  const [schedulingWorkers, setSchedulingWorkers] = useState<SchedulingWorkerResource[]>([]);
  const [schedulingEquipments, setSchedulingEquipments] = useState<SchedulingEquipmentResource[]>([]);
  const [equipmentTypeFilter, setEquipmentTypeFilter] = useState<SchedulingResourceFilterValue>('all');
  const [workerRoleFilter, setWorkerRoleFilter] = useState<SchedulingResourceFilterValue>('all');
  const [pinnedResources, setPinnedResources] = useState<SchedulingPinnedResources>(() =>
    loadSchedulingPinnedResources()
  );
  const [showPinnedOnly, setShowPinnedOnly] = useState(false);
  const [pinManagerOpen, setPinManagerOpen] = useState(false);
  const [poolViewMode, setPoolViewMode] = useState<'table' | 'card'>('table');
  const [schedulingMolds, setSchedulingMolds] = useState<Array<{ id: number; name: string; code?: string }>>([]);
  const draftWoUpdatesRef = useRef(
    new Map<number, { work_order_id: number; planned_start_date: string; planned_end_date: string }>()
  );
  const draftOpUpdatesRef = useRef(
    new Map<number, { operation_id: number; planned_start_date: string; planned_end_date: string }>()
  );
  const draftStationUpdatesRef = useRef(
    new Map<number, { operation_id: number; assigned_station_id: number }>()
  );
  const undoStackRef = useRef<WorkOrderForGantt[][]>([]);
  const schedulingPerms = useResourcePermissions('kuaizhizao:plan-management-scheduling');
  const canScheduleUpdate = schedulingPerms.canUpdate;

  useEffect(() => {
    saveSchedulingBoardPreferences({ boardMainView, taskLevel: ganttTaskLevel });
  }, [boardMainView, ganttTaskLevel]);

  const syncDraftPendingCount = useCallback(() => {
    setDraftPendingCount(
      draftWoUpdatesRef.current.size + draftOpUpdatesRef.current.size + draftStationUpdatesRef.current.size
    );
  }, []);

  const selectedWorkOrderIds = useMemo(
    () => selectedRowKeys.map((k) => Number(k)).filter((n) => !Number.isNaN(n) && n > 0),
    [selectedRowKeys]
  );

  const buildWorkOrderParams = useCallback(
    (query: Record<string, any>, paging?: { skip?: number; limit: number }) => ({
      skip: paging?.skip ?? 0,
      limit: paging?.limit ?? 500,
      status: query.status,
      keyword: query.keyword,
      include_operations: true,
      include_scores: false,
      include_readiness: false,
    }),
    []
  );

  useEffect(() => {
    actionRef.current?.reload();
  }, [poolAppliedKeyword, poolStatusFilter, poolOverdueOnly]);

  useEffect(() => {
    let cancelled = false;
    const loadResources = async () => {
      try {
        const [usersRes, equipmentRes, moldsRes] = await Promise.all([
          searchUserDisplay({ is_active: true, page_size: 200 }).catch(() => ({ items: [] })),
          getEquipmentList({ is_active: true, limit: 200 }).catch(() => ({ items: [] })),
          getMoldList({ is_active: true, limit: 200 }).catch(() => ({ items: [] })),
        ]);
        if (cancelled) return;
        const userItems = usersRes?.items || [];
        setSchedulingWorkers(
          userItems.map((u) => {
            const roles = resolveUserRoles(u.roles);
            return {
              id: Number(u.id),
              name: String((u.full_name || '').trim() || u.username || u.id),
              code: u.username,
              roles,
              roleUuids: roles.map((role) => role.uuid),
            };
          })
        );
        setSchedulingEquipments(
          (equipmentRes?.items || []).map((item: { id?: number; name?: string; code?: string; type?: string }) => ({
            id: Number(item.id),
            name: String(item.name || item.id),
            code: item.code,
            type: item.type ? String(item.type) : undefined,
          }))
        );
        setSchedulingMolds(
          (moldsRes?.items || []).map((item: any) => ({
            id: Number(item.id),
            name: String(item.name || item.id),
            code: item.code,
          }))
        );
      } catch {
        if (!cancelled) {
          setSchedulingWorkers([]);
          setSchedulingEquipments([]);
          setSchedulingMolds([]);
        }
      }
    };
    void loadResources();
    return () => {
      cancelled = true;
    };
  }, []);

  const handlePoolSearch = useCallback(() => {
    setPoolAppliedKeyword(poolKeyword.trim());
  }, [poolKeyword]);

  const handlePoolReset = useCallback(() => {
    setPoolKeyword('');
    setPoolAppliedKeyword('');
    setPoolStatusFilter('all');
    setPoolOverdueOnly(false);
  }, []);

  const {
    data: ganttWorkOrders = [] as WorkOrderForGantt[],
    loading: ganttLoading,
    run: refreshGantt,
    mutate: mutateGanttWorkOrders,
  } = useRequest(
    async () => {
      const res = await workOrderApi.list(buildWorkOrderParams({}, { limit: GANTT_WORK_ORDER_LIMIT }));
      let list = Array.isArray(res) ? res : (res?.data ?? []);
      list = list.filter((wo: WorkOrderForGantt) => isSchedulableWorkOrderStatus(wo.status));
      if (filterWorkOrderIds?.length) {
        const idSet = new Set(filterWorkOrderIds);
        list = list.filter((wo: WorkOrderForGantt) => idSet.has(wo.id));
      } else if (filterPlanDate) {
        list = list.filter(
          (wo: WorkOrderForGantt) =>
            wo.planned_start_date &&
            formatDateTime(wo.planned_start_date, 'YYYY-MM-DD') === filterPlanDate,
        );
      }
      return list as WorkOrderForGantt[];
    },
    { refreshDeps: [filterWorkOrderIds, filterPlanDate, buildWorkOrderParams] }
  );

  const ganttBoardWorkOrders = useMemo(
    () => ganttWorkOrders.filter((wo) => isWorkOrderScheduledOnBoard(wo)),
    [ganttWorkOrders]
  );

  const scheduledBoardWorkOrderIdsKey = useMemo(
    () =>
      ganttBoardWorkOrders
        .map((wo) => wo.id)
        .sort((a, b) => a - b)
        .join(','),
    [ganttBoardWorkOrders]
  );

  const poolWorkOrders = useMemo(
    () =>
      ganttWorkOrders.filter((wo) => {
        if (poolStatusFilter !== 'all' && wo.status !== poolStatusFilter) return false;
        if (poolOverdueOnly) {
          if (!wo.planned_end_date || !dayjs(wo.planned_end_date).isBefore(dayjs())) return false;
        }
        return matchesPoolKeyword(wo, poolAppliedKeyword);
      }),
    [ganttWorkOrders, poolAppliedKeyword, poolOverdueOnly, poolStatusFilter]
  );

  const workOrderDiagnosticsById = useMemo(() => {
    const map = new Map<number, ReturnType<typeof collectWorkOrderDiagnosticIssues>>();
    for (const wo of ganttWorkOrders) {
      const issues = collectWorkOrderDiagnosticIssues(wo, boardScan, t, {
        materialHardConstraint: Boolean(schedulingConstraints.material_hard_constraint),
        resourceMode: schedulingConstraints.resource_mode,
      });
      if (issues.length > 0) map.set(wo.id, issues);
    }
    return map;
  }, [
    boardScan,
    ganttWorkOrders,
    schedulingConstraints.material_hard_constraint,
    schedulingConstraints.resource_mode,
    t,
  ]);

  const poolWorkOrderIds = useMemo(
    () => poolWorkOrders.map((wo) => wo.id),
    [poolWorkOrders]
  );

  const aiSuggestedPoolRankById = useMemo(() => {
    const map = new Map<number, number>();
    aiSuggestedPoolOrderIds.forEach((id, index) => map.set(id, index + 1));
    return map;
  }, [aiSuggestedPoolOrderIds]);

  const materialIssueWorkOrderIds = useMemo(
    () => (boardScan?.material_issues ?? []).map((item) => item.work_order_id),
    [boardScan?.material_issues]
  );

  const poolDiagnosticLabelsById = useMemo(() => {
    const map = new Map<number, string[]>();
    for (const wo of ganttWorkOrders) {
      const issues = workOrderDiagnosticsById.get(wo.id);
      if (issues?.length) {
        map.set(
          wo.id,
          issues.map((issue) => issue.label)
        );
      }
    }
    return map;
  }, [ganttWorkOrders, workOrderDiagnosticsById]);

  const poolCardItems = useMemo(
    () =>
      buildSchedulingPoolCardItems(
        poolWorkOrders,
        new Set(materialIssueWorkOrderIds),
        poolDiagnosticLabelsById,
        aiSuggestedPoolRankById
      ),
    [aiSuggestedPoolRankById, materialIssueWorkOrderIds, poolDiagnosticLabelsById, poolWorkOrders]
  );

  const handleCardBoardSelectWorkOrder = useCallback((workOrderId: number) => {
    setSelectedRowKeys([workOrderId]);
  }, []);

  const handleAiSelectSuggested = useCallback((order: number[]) => {
    setSelectedRowKeys(order);
    setAiSuggestedPoolOrderIds(order);
    setFocusTaskId(null);
  }, []);

  const handleAiSelectOverdue = useCallback(() => {
    const overdueIds = poolWorkOrders
      .filter((wo) => wo.planned_end_date && dayjs(wo.planned_end_date).isBefore(dayjs()))
      .map((wo) => wo.id);
    setSelectedRowKeys(overdueIds);
    setFocusTaskId(null);
    if (overdueIds.length === 0) {
      messageApi.info(t('app.kuaizhizao.scheduling.aiAssist.noOverdueInPool'));
    }
  }, [messageApi, poolWorkOrders, t]);

  const poolWorkOrdersRef = useRef(poolWorkOrders);
  poolWorkOrdersRef.current = poolWorkOrders;

  const handleAiPoolReorder = useCallback((order: number[]) => {
    setAiSuggestedPoolOrderIds(order);
  }, []);

  useEffect(() => {
    actionRef.current?.reload();
  }, [scheduledBoardWorkOrderIdsKey, poolAppliedKeyword, poolStatusFilter]);

  const pushUndoSnapshot = useCallback(() => {
    undoStackRef.current.push(JSON.parse(JSON.stringify(ganttWorkOrders)) as WorkOrderForGantt[]);
    if (undoStackRef.current.length > 15) undoStackRef.current.shift();
  }, [ganttWorkOrders]);

  const scanBoardWorkOrderIds = useMemo(() => {
    const ids = new Set<number>();
    if (filterWorkOrderIds?.length) {
      filterWorkOrderIds.forEach((id) => ids.add(id));
    } else {
      (ganttWorkOrders ?? []).forEach((wo) => ids.add(wo.id));
    }
    return ids.size > 0 ? [...ids] : undefined;
  }, [filterWorkOrderIds, ganttWorkOrders]);

  const scanBoardWorkOrderIdsKey = useMemo(
    () => (scanBoardWorkOrderIds ?? []).slice().sort((a, b) => a - b).join(','),
    [scanBoardWorkOrderIds]
  );

  const { run: refreshBoardScan } = useRequest(
    async () => {
      const res = await visualSchedulingApi.boardScan({
        horizon_days: schedulingConstraints.rolling_horizon_days || 14,
        work_order_ids: scanBoardWorkOrderIds,
        plan_date: filterPlanDate,
      });
      setBoardScan(res);
      return res;
    },
    {
      refreshDeps: [schedulingConstraints.rolling_horizon_days, scanBoardWorkOrderIdsKey, filterPlanDate],
    }
  );

  useEffect(() => {
    if (filterWorkOrderIds?.length) setSelectedRowKeys(filterWorkOrderIds);
  }, [filterWorkOrderIds]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null;
    let attempts = 0;
    try {
      if (sessionStorage.getItem(SCHEDULING_FULLSCREEN_TIP_SESSION_KEY) === '1') return undefined;
      timer = setInterval(() => {
        attempts += 1;
        const el = document.querySelector('.uni-tabs-fullscreen-button');
        if (el) {
          setFullscreenTourOpen(true);
          if (timer) clearInterval(timer);
        } else if (attempts >= 60 && timer) clearInterval(timer);
      }, 200);
    } catch {
      // ignore
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, []);

  useRequest(
    async () => {
      // apiRequest 已解包 { success, data } → 直接得到配置对象
      const config = await schedulingConfigApi.getDefault();
      if (config?.constraints) {
        setSchedulingConstraints((prev) => ({
          ...prev,
          ...pickVisualSchedulingConstraints(config.constraints as SchedulingConstraints),
        }));
      }
      return config;
    },
    { refreshDeps: [] }
  );

  const { data: planReliability, loading: planReliabilityLoading, run: refreshPlanReliability } = useRequest(
    async () => mesDashboardService.getPlanReliability(),
    { refreshDeps: [] }
  );

  const { data: stationCatalog = [] as Array<{
    id: number;
    name: string;
    code?: string;
    production_line_id: number;
    production_line_name?: string;
  }> } = useRequest(async () => {
    const res = await workstationApi.list({ is_active: true, limit: 1000 });
    const items = factoryListItems(res);
    return items
      .map(
        (s: {
          id?: number;
          name?: string;
          code?: string;
          production_line_id?: number;
          productionLineId?: number;
          production_line_name?: string;
          productionLineName?: string;
        }) => ({
          id: Number(s.id),
          name: String(s.name || s.code || s.id),
          code: s.code ? String(s.code) : undefined,
          production_line_id: Number(s.production_line_id ?? s.productionLineId ?? 0),
          production_line_name: String(
            s.production_line_name || s.productionLineName || ''
          ).trim() || undefined,
        })
      )
      .filter((s) => Number.isInteger(s.id) && s.id > 0);
  });

  const { data: productionLineCatalog = [] as WorkstationResource[] } = useRequest(async () => {
    const res = await productionLineApi.list({ is_active: true, limit: 1000 });
    return factoryListItems(res)
      .map((line: { id?: number; name?: string; code?: string }) => ({
        id: Number(line.id),
        name: String(line.name || line.code || line.id),
        code: line.code ? String(line.code) : undefined,
      }))
      .filter((line) => Number.isInteger(line.id) && line.id > 0) as WorkstationResource[];
  });

  type RelayLineCapacityRow = {
    production_line_id: number;
    takt_seconds: number;
    daily_capacity_qty: number;
    product_ids: number[];
  };

  const {
    data: lineCapacities = [] as RelayLineCapacityRow[],
    error: lineCapacitiesError,
  } = useRequest(async () => {
    const rows = await apiRequest<RelayLineCapacityRow[]>('/apps/ind-relay/line-capacities', {
      method: 'GET',
    });
    const list = Array.isArray(rows) ? rows : [];
    // 旧 API / 未部署行业包字段时禁止把「缺字段」伪装成「空绑定」
    if (
      list.length > 0 &&
      list.every((row) => !Object.prototype.hasOwnProperty.call(row, 'product_ids'))
    ) {
      throw new Error('LINE_PRODUCT_IDS_MISSING');
    }
    return list.map((row) => ({
      production_line_id: Number(row.production_line_id || 0),
      takt_seconds: Number(row.takt_seconds || 0),
      daily_capacity_qty: Number(row.daily_capacity_qty || 0),
      product_ids: Array.isArray(row.product_ids)
        ? row.product_ids.map((x) => Number(x)).filter((x) => x > 0)
        : [],
    }));
  });

  const taktSecondsByLineId = useMemo(() => {
    const m = new Map<number, number>();
    lineCapacities.forEach((row) => {
      if (row.production_line_id > 0 && row.takt_seconds > 0) {
        m.set(row.production_line_id, row.takt_seconds);
      }
    });
    return m;
  }, [lineCapacities]);

  const dailyCapacityByLineId = useMemo(() => {
    const m = new Map<number, number>();
    lineCapacities.forEach((row) => {
      if (row.production_line_id > 0 && row.daily_capacity_qty > 0) {
        m.set(row.production_line_id, row.daily_capacity_qty);
      }
    });
    return m;
  }, [lineCapacities]);

  const linesMissingTakt = useMemo(
    () =>
      productionLineCatalog
        .filter((line) => {
          const takt = taktSecondsByLineId.get(line.id) ?? 0;
          const daily = dailyCapacityByLineId.get(line.id) ?? 0;
          return takt <= 0 || daily <= 0;
        })
        .map((line) => line.id),
    [dailyCapacityByLineId, productionLineCatalog, taktSecondsByLineId]
  );

  /** 产线 → 可生产自制件；空绑定 = 不可承接 */
  const lineAllowedProductIds = useMemo(() => {
    const m = new Map<number, Set<number>>();
    lineCapacities.forEach((row) => {
      if (row.production_line_id > 0) {
        m.set(row.production_line_id, new Set(row.product_ids));
      }
    });
    return m;
  }, [lineCapacities]);

  const lineAcceptsProduct = useCallback(
    (lineId: number, productId: number) => {
      if (!(lineId > 0) || !(productId > 0)) return false;
      const allowed = lineAllowedProductIds.get(lineId);
      return !!allowed && allowed.has(productId);
    },
    [lineAllowedProductIds]
  );

  const eligibleConfiguredLineIdsForProduct = useCallback(
    (productId: number) => {
      if (!(productId > 0)) return [] as number[];
      return productionLineCatalog
        .filter((line) => {
          if (linesMissingTakt.includes(line.id)) return false;
          return lineAcceptsProduct(line.id, productId);
        })
        .map((line) => line.id);
    },
    [lineAcceptsProduct, linesMissingTakt, productionLineCatalog]
  );

  const workstationResources = useMemo(() => {
    if (schedulingConstraints.resource_mode !== 'production_line') {
      return stationCatalog.map((s) => ({
        id: s.id,
        name: s.name,
        code: s.code,
      })) as WorkstationResource[];
    }
    // 按产线：主数据产线为泳道真源；不依赖工位
    return productionLineCatalog.map((line) => ({
      id: line.id,
      name: line.name,
      code: line.code,
    })) as WorkstationResource[];
  }, [productionLineCatalog, schedulingConstraints.resource_mode, stationCatalog]);

  const ganttDisplayWorkOrders = useMemo(() => {
    if (schedulingConstraints.resource_mode !== 'production_line') return ganttWorkOrders;
    return ganttWorkOrders.map((wo) => ({
      ...wo,
      operations: (wo.operations || []).map((op) => {
        const lineId =
          op.assigned_production_line_id != null && Number(op.assigned_production_line_id) > 0
            ? Number(op.assigned_production_line_id)
            : 0;
        if (!lineId) return op;
        return {
          ...op,
          // 甘特泳道仍按 assigned_station_id 挂资源行；产线模式下写入产线 ID
          assigned_station_id: lineId,
          assigned_station_name:
            workstationResources.find((r) => r.id === lineId)?.name ||
            op.assigned_production_line_name ||
            op.assigned_station_name,
        };
      }),
    }));
  }, [ganttWorkOrders, schedulingConstraints.resource_mode, workstationResources]);

  const ganttBoardDisplayWorkOrders = useMemo(
    () => ganttDisplayWorkOrders.filter((wo) => isWorkOrderScheduledOnBoard(wo)),
    [ganttDisplayWorkOrders]
  );

  const { data: schedulingWorkCenters = [] } = useRequest(async () => {
    const res = await workCenterApi.list({ is_active: true, limit: 500 });
    return factoryListItems(res)
      .map(
        (wc: { id?: number; name?: string; code?: string; workstationIds?: number[] }) => ({
          id: Number(wc.id),
          name: String(wc.name || wc.code || wc.id),
          code: wc.code ? String(wc.code) : undefined,
          workstationIds: (wc.workstationIds ?? []).map(Number).filter((id) => id > 0),
        })
      )
      .filter((wc) => Number.isInteger(wc.id) && wc.id > 0);
  });

  const freezeAnchor = useMemo(
    () => buildFreezeAnchor(schedulingConstraints.freeze_horizon_days || 0),
    [schedulingConstraints.freeze_horizon_days]
  );

  const selectedOperationCount = useMemo(() => {
    if (selectedWorkOrderIds.length === 0) return 0;
    const idSet = new Set(selectedWorkOrderIds);
    let count = 0;
    (ganttWorkOrders ?? []).forEach((wo) => {
      if (!idSet.has(wo.id)) return;
      count += (wo.operations || []).filter((o) => o.id != null).length;
    });
    return count;
  }, [ganttWorkOrders, selectedWorkOrderIds]);

  const selectedWorkOrders = useMemo(() => {
    const idSet = new Set(selectedWorkOrderIds);
    return ganttWorkOrders.filter((wo) => idSet.has(wo.id));
  }, [ganttWorkOrders, selectedWorkOrderIds]);

  const nonDraggableTaskIds = useMemo(() => {
    const stationIdsWithOps = new Set<number>();
    (ganttBoardWorkOrders ?? []).forEach((wo) => {
      (wo.operations || []).forEach((op) => {
        if (op.assigned_station_id != null && Number(op.assigned_station_id) > 0) {
          stationIdsWithOps.add(Number(op.assigned_station_id));
        }
        if (
          schedulingConstraints.resource_mode === 'production_line' &&
          op.assigned_production_line_id != null &&
          Number(op.assigned_production_line_id) > 0
        ) {
          stationIdsWithOps.add(Number(op.assigned_production_line_id));
        }
      });
    });
    const ids: Array<number | string> = workstationResources
      .filter((s) => !stationIdsWithOps.has(s.id))
      .map((s) => stationResourceId(s.id));
    (ganttBoardWorkOrders ?? []).forEach((wo) => {
      if (!isWorkOrderSchedulingLocked(wo, schedulingConstraints.freeze_horizon_days || 0, freezeAnchor)) {
        return;
      }
      ids.push(`wo-${wo.id}`);
      (wo.operations || []).forEach((op) => {
        if (op.id != null) ids.push(`op-${op.id}`);
      });
    });
    return ids;
  }, [
    freezeAnchor,
    ganttBoardWorkOrders,
    schedulingConstraints.freeze_horizon_days,
    schedulingConstraints.resource_mode,
    workstationResources,
  ]);

  const topLegendMetrics = useMemo(() => {
    const manualFrozenCount = ganttBoardWorkOrders.filter((wo) => Boolean(wo.is_frozen)).length;
    const freezeWindowLockedCount = ganttBoardWorkOrders.filter((wo) => {
      if (wo.is_frozen || !wo.planned_start_date) return false;
      return (
        dayjs(wo.planned_start_date).isBefore(freezeAnchor) ||
        dayjs(wo.planned_start_date).isSame(freezeAnchor)
      );
    }).length;
    const totalLockedCount = new Set(
      ganttBoardWorkOrders
        .filter((wo) => isWorkOrderSchedulingLocked(wo, schedulingConstraints.freeze_horizon_days || 0, freezeAnchor))
        .map((wo) => wo.id)
    ).size;
    return {
      totalLockedCount,
      manualFrozenCount,
      freezeWindowLockedCount,
      executableCount: Math.max(0, ganttBoardWorkOrders.length - totalLockedCount),
      conflictCount: boardScan?.conflict_count ?? 0,
    };
  }, [boardScan, freezeAnchor, ganttBoardWorkOrders, schedulingConstraints.freeze_horizon_days]);

  const buildMissingSettingsRows = useCallback(
    (gaps: VisualSchedulingMissingSetting[]) => {
      const byOp = new Map<
        number,
        {
          operation_id: number;
          work_order_id: number;
          work_order_code: string;
          operation_name: string;
          work_center_id?: number | null;
          needHours: boolean;
          needStation: boolean;
          needCapacity: boolean;
          setup_time: number | null;
          standard_time: number | null;
          assigned_station_id: number | null;
        }
      >();
      for (const gap of gaps) {
        const existing = byOp.get(gap.operation_id) ?? {
          operation_id: gap.operation_id,
          work_order_id: gap.work_order_id,
          work_order_code: gap.work_order_code,
          operation_name: gap.operation_name || String(gap.operation_id),
          work_center_id: gap.work_center_id,
          needHours: false,
          needStation: false,
          needCapacity: false,
          setup_time: null as number | null,
          standard_time: null as number | null,
          assigned_station_id: null as number | null,
        };
        if (gap.field === 'setup_time' || gap.field === 'standard_time') {
          existing.needHours = true;
          if (gap.field === 'setup_time') {
            existing.setup_time =
              gap.suggested != null && gap.suggested !== '' ? Number(gap.suggested) : 0;
          }
          if (gap.field === 'standard_time') {
            existing.standard_time =
              gap.suggested != null && gap.suggested !== '' ? Number(gap.suggested) : 1;
          }
        }
        if (gap.field === 'assigned_station_id' || gap.field === 'assigned_production_line_id') {
          existing.needStation = true;
          const suggestedId =
            gap.suggested != null && gap.suggested !== '' ? Number(gap.suggested) : 0;
          if (suggestedId > 0 && !(existing.assigned_station_id != null && existing.assigned_station_id > 0)) {
            existing.assigned_station_id = suggestedId;
          }
        }
        if (gap.field === 'takt_seconds' || gap.field === 'daily_capacity_qty') {
          existing.needCapacity = true;
        }
        byOp.set(gap.operation_id, existing);
      }
      return Array.from(byOp.values());
    },
    [],
  );

  const productIdByWorkOrderId = useMemo(() => {
    const m = new Map<number, number>();
    for (const wo of ganttWorkOrders) {
      const pid = Number(wo.product_id || 0);
      if (pid > 0) m.set(wo.id, pid);
    }
    return m;
  }, [ganttWorkOrders]);

  const openMissingSettingsModal = useCallback(
    (gaps: VisualSchedulingMissingSetting[], continueAutoRescheduleIds?: number[]) => {
      // gap 上的 product_id 补齐甘特未加载工单的自制件映射
      const productFromGaps = new Map<number, number>();
      for (const gap of gaps) {
        const pid = Number(gap.product_id || 0);
        if (pid > 0 && gap.work_order_id > 0) {
          productFromGaps.set(gap.work_order_id, pid);
        }
      }
      const resolveProductId = (workOrderId: number) =>
        productIdByWorkOrderId.get(workOrderId) || productFromGaps.get(workOrderId) || 0;

      let rows = buildMissingSettingsRows(gaps);
      // 产线模式：预填推荐产线 = 已配节拍 ∩ 绑定含本工单自制件
      if (schedulingConstraints.resource_mode === 'production_line') {
        rows = rows.map((row) => {
          if (!row.needStation) return row;
          const productId = resolveProductId(row.work_order_id);
          const eligible = new Set(eligibleConfiguredLineIdsForProduct(productId));
          if (
            row.assigned_station_id != null &&
            row.assigned_station_id > 0 &&
            !eligible.has(row.assigned_station_id)
          ) {
            return { ...row, assigned_station_id: null };
          }
          if (row.assigned_station_id != null && row.assigned_station_id > 0) {
            return row;
          }
          if (eligible.size === 1) {
            return { ...row, assigned_station_id: [...eligible][0] };
          }
          return row;
        });
        // 同工单已有推荐产线的行，把空行补齐为同一条（整单产线，且须在 eligible）
        const byWo = new Map<number, number>();
        for (const row of rows) {
          if (row.assigned_station_id != null && row.assigned_station_id > 0) {
            byWo.set(row.work_order_id, row.assigned_station_id);
          }
        }
        if (byWo.size > 0) {
          rows = rows.map((row) => {
            if (!row.needStation || (row.assigned_station_id != null && row.assigned_station_id > 0)) {
              return row;
            }
            const shared = byWo.get(row.work_order_id);
            if (shared == null) return row;
            const productId = resolveProductId(row.work_order_id);
            const eligible = new Set(eligibleConfiguredLineIdsForProduct(productId));
            return eligible.has(shared) ? { ...row, assigned_station_id: shared } : row;
          });
        }
      }
      setMissingSettingsProductByWo(productFromGaps);
      setMissingSettingsRows(rows);
      setPendingAutoRescheduleIds(continueAutoRescheduleIds ?? null);
      setMissingSettingsModalOpen(true);
    },
    [
      buildMissingSettingsRows,
      eligibleConfiguredLineIdsForProduct,
      productIdByWorkOrderId,
      schedulingConstraints.resource_mode,
    ],
  );

  const filteredSchedulingEquipments = useMemo(
    () => filterSchedulingEquipments(schedulingEquipments, equipmentTypeFilter),
    [equipmentTypeFilter, schedulingEquipments]
  );

  const filteredSchedulingWorkers = useMemo(
    () => filterSchedulingWorkers(schedulingWorkers, workerRoleFilter),
    [schedulingWorkers, workerRoleFilter]
  );

  const pinnedResourceIds = useMemo(
    () => pinnedIdsForLevel(pinnedResources, ganttTaskLevel),
    [ganttTaskLevel, pinnedResources]
  );

  const visibleWorkstationResources = useMemo(() => {
    if (!showPinnedOnly || pinnedResourceIds.length === 0) return workstationResources;
    const pinned = new Set(pinnedResourceIds);
    return workstationResources.filter((station) => pinned.has(station.id));
  }, [pinnedResourceIds, showPinnedOnly, workstationResources]);

  const visibleSchedulingEquipments = useMemo(() => {
    if (!showPinnedOnly || pinnedResourceIds.length === 0) return filteredSchedulingEquipments;
    const pinned = new Set(pinnedResourceIds);
    return filteredSchedulingEquipments.filter((equipment) => pinned.has(equipment.id));
  }, [filteredSchedulingEquipments, pinnedResourceIds, showPinnedOnly]);

  const visibleSchedulingWorkers = useMemo(() => {
    if (!showPinnedOnly || pinnedResourceIds.length === 0) return filteredSchedulingWorkers;
    const pinned = new Set(pinnedResourceIds);
    return filteredSchedulingWorkers.filter((worker) => pinned.has(worker.id));
  }, [filteredSchedulingWorkers, pinnedResourceIds, showPinnedOnly]);

  const handlePinnedResourcesChange = useCallback((next: SchedulingPinnedResources) => {
    setPinnedResources(next);
    saveSchedulingPinnedResources(next);
  }, []);

  const resourceViewStats = useMemo(() => {
    let scheduledOpCount = 0;
    (ganttBoardWorkOrders ?? []).forEach((wo) => {
      scheduledOpCount += (wo.operations || []).filter((o) => o.id != null).length;
    });
    return {
      taskLevel: ganttTaskLevel,
      stationCount: visibleWorkstationResources.length,
      equipmentCount: visibleSchedulingEquipments.length,
      workerCount: visibleSchedulingWorkers.length,
      taskCount: scheduledOpCount,
    };
  }, [
    ganttBoardWorkOrders,
    ganttTaskLevel,
    visibleSchedulingEquipments.length,
    visibleSchedulingWorkers.length,
    visibleWorkstationResources.length,
  ]);

  const confirmAndPersist = useCallback(
    async (
      woUpdates: Array<{ work_order_id: number; planned_start_date: string; planned_end_date: string }>,
      opUpdates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }>
    ) => {
      const validation = await visualSchedulingApi.validateAdjustments({
        work_order_updates: woUpdates,
        operation_updates: opUpdates,
      });
      const doSave = async () => {
        const woLabel = t('app.kuaizhizao.scheduling.batch.label.workOrderDates');
        const opLabel = t('app.kuaizhizao.scheduling.batch.label.operationDates');
        if (woUpdates.length > 0) {
          const woResult = await workOrderApi.batchUpdateDates(woUpdates);
          ensureBatchUpdatesPersisted(woResult, woUpdates.length, woLabel, t);
          reportBatchUpdateResult(messageApi, woLabel, woResult, t);
          mutateGanttWorkOrders((prev) => applyWorkOrderDateUpdates(prev ?? [], woUpdates));
        }
        if (opUpdates.length > 0) {
          const opResult = await workOrderApi.batchUpdateOperationDates(opUpdates);
          ensureBatchUpdatesPersisted(opResult, opUpdates.length, opLabel, t);
          reportBatchUpdateResult(messageApi, opLabel, opResult, t);
          mutateGanttWorkOrders((prev) => applyOperationDateUpdates(prev ?? [], opUpdates));
        }
        if (filterPlanDate) {
          const woIds = new Set<number>(woUpdates.map((u) => u.work_order_id));
          if (opUpdates.length > 0) {
            (ganttWorkOrders || []).forEach((wo) => {
              const opIds = new Set((wo.operations || []).map((o) => o.id));
              if (opUpdates.some((u) => opIds.has(u.operation_id))) {
                woIds.add(wo.id);
              }
            });
          }
          if (woIds.size > 0) {
            await rollingSchedulingApi.syncFromAps({
              plan_date: filterPlanDate,
              work_order_ids: [...woIds],
            });
          }
        }
    actionRef.current?.reload();
        refreshBoardScan();
        refreshPlanReliability();
      };
      if (validation.valid) {
        await doSave();
        return;
      }
      const preview = (validation.conflicts || []).slice(0, 5).map((c) => c.message).join('\n');
      await new Promise<void>((resolve, reject) => {
        modal.confirm({
          title: t('app.kuaizhizao.scheduling.msg.conflictTitle'),
          content: (
            <div>
              <p>{t('app.kuaizhizao.scheduling.msg.conflictContent', { count: validation.conflict_count })}</p>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{preview}</pre>
            </div>
          ),
          okText: t('app.kuaizhizao.scheduling.msg.saveAnyway'),
          cancelText: t('common.cancel'),
          onOk: async () => {
            try {
              await doSave();
              resolve();
            } catch (e) {
              reject(e);
            }
          },
          onCancel: () => reject(new Error('cancelled')),
        });
      });
    },
    [
      filterPlanDate,
      ganttWorkOrders,
      messageApi,
      modal,
      mutateGanttWorkOrders,
      refreshBoardScan,
      refreshPlanReliability,
      t,
    ]
  );

  const handleApplyDraft = useCallback(async () => {
    const woUpdates = [...draftWoUpdatesRef.current.values()];
    const opUpdates = [...draftOpUpdatesRef.current.values()];
    const stationUpdates = [...draftStationUpdatesRef.current.values()];
    if (woUpdates.length === 0 && opUpdates.length === 0 && stationUpdates.length === 0) {
      messageApi.info(t('app.kuaizhizao.scheduling.msg.noDraftChanges'));
      return;
    }
    const persistDraft = async () => {
      const isLineMode = schedulingConstraints.resource_mode === 'production_line';
      const woLabel = t('app.kuaizhizao.scheduling.batch.label.workOrderDates');
      const opLabel = t('app.kuaizhizao.scheduling.batch.label.operationDates');
      const stationLabel = isLineMode
        ? t('app.kuaizhizao.scheduling.batch.label.operationProductionLines')
        : t('app.kuaizhizao.scheduling.batch.label.operationStations');
      if (woUpdates.length > 0) {
        const woResult = await workOrderApi.batchUpdateDates(woUpdates);
        ensureBatchUpdatesPersisted(woResult, woUpdates.length, woLabel, t);
        reportBatchUpdateResult(messageApi, woLabel, woResult, t);
        mutateGanttWorkOrders((prev) => applyWorkOrderDateUpdates(prev ?? [], woUpdates));
      }
      if (opUpdates.length > 0) {
        const opResult = await workOrderApi.batchUpdateOperationDates(opUpdates);
        ensureBatchUpdatesPersisted(opResult, opUpdates.length, opLabel, t);
        reportBatchUpdateResult(messageApi, opLabel, opResult, t);
        mutateGanttWorkOrders((prev) => applyOperationDateUpdates(prev ?? [], opUpdates));
      }
      if (stationUpdates.length > 0) {
        if (isLineMode) {
          const lineUpdates = stationUpdates.map((u) => ({
            operation_id: u.operation_id,
            assigned_production_line_id: Number(u.assigned_station_id),
          }));
          const result = await workOrderApi.batchUpdateOperationProductionLines(lineUpdates);
          reportBatchUpdateResult(messageApi, stationLabel, {
            updated: result.updated,
            skipped_frozen: result.skipped_frozen,
            skipped_freeze_window: [],
            failed: result.failed,
          }, t);
        } else {
          const result = await workOrderApi.batchUpdateOperationStations(stationUpdates);
          reportBatchUpdateResult(messageApi, stationLabel, {
            updated: result.updated,
            skipped_frozen: result.skipped_frozen,
            skipped_freeze_window: [],
            failed: result.failed,
          }, t);
        }
        mutateGanttWorkOrders((prev) =>
          applyOperationStationUpdates(prev ?? [], stationUpdates, {
            asProductionLine: isLineMode,
          })
        );
      }
      if (filterPlanDate) {
        const woIds = new Set<number>(woUpdates.map((u) => u.work_order_id));
        if (opUpdates.length > 0 || stationUpdates.length > 0) {
          const opIdSet = new Set([
            ...opUpdates.map((u) => u.operation_id),
            ...stationUpdates.map((u) => u.operation_id),
          ]);
          (ganttWorkOrders || []).forEach((wo) => {
            if ((wo.operations || []).some((o) => o.id != null && opIdSet.has(o.id))) {
              woIds.add(wo.id);
            }
          });
        }
        if (woIds.size > 0) {
          await rollingSchedulingApi.syncFromAps({
            plan_date: filterPlanDate,
            work_order_ids: [...woIds],
          });
        }
      }
      actionRef.current?.reload();
      refreshBoardScan();
      refreshPlanReliability();
    };
    try {
      const isLineMode = schedulingConstraints.resource_mode === 'production_line';
      const validation = await visualSchedulingApi.validateAdjustments({
        work_order_updates: woUpdates,
        operation_updates: opUpdates,
        ...(isLineMode
          ? {
              operation_production_line_updates: stationUpdates.map((u) => ({
                operation_id: u.operation_id,
                assigned_production_line_id: Number(u.assigned_station_id),
              })),
            }
          : { operation_station_updates: stationUpdates }),
      });
      if (validation.valid) {
        await persistDraft();
      } else {
        const preview = (validation.conflicts || []).slice(0, 5).map((c) => c.message).join('\n');
        await new Promise<void>((resolve, reject) => {
          modal.confirm({
            title: t('app.kuaizhizao.scheduling.msg.conflictTitle'),
            content: (
              <div>
                <p>{t('app.kuaizhizao.scheduling.msg.conflictContent', { count: validation.conflict_count })}</p>
                <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{preview}</pre>
              </div>
            ),
            okText: t('app.kuaizhizao.scheduling.msg.saveAnyway'),
            cancelText: t('common.cancel'),
            onOk: async () => {
              try {
                await persistDraft();
                resolve();
              } catch (e) {
                reject(e);
              }
            },
            onCancel: () => reject(new Error('cancelled')),
          });
        });
      }
      draftWoUpdatesRef.current.clear();
      draftOpUpdatesRef.current.clear();
      draftStationUpdatesRef.current.clear();
      undoStackRef.current = [];
      syncDraftPendingCount();
      refreshGantt();
    } catch (e: any) {
      if (e?.message !== 'cancelled') {
        messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.applyFailed'));
        refreshGantt();
      }
    }
  }, [
    filterPlanDate,
    ganttWorkOrders,
    messageApi,
    modal,
    mutateGanttWorkOrders,
    refreshBoardScan,
    refreshGantt,
    refreshPlanReliability,
    schedulingConstraints.resource_mode,
    syncDraftPendingCount,
    t,
  ]);

  const handleUndoDraft = useCallback(() => {
    const prev = undoStackRef.current.pop();
    if (!prev) {
      messageApi.info(t('app.kuaizhizao.scheduling.msg.noUndoStep'));
      return;
    }
    mutateGanttWorkOrders(prev);
    draftWoUpdatesRef.current.clear();
    draftOpUpdatesRef.current.clear();
    draftStationUpdatesRef.current.clear();
    syncDraftPendingCount();
    messageApi.success(t('app.kuaizhizao.scheduling.msg.undoSuccess'));
  }, [messageApi, mutateGanttWorkOrders, syncDraftPendingCount, t]);

  const handleGanttBatchUpdate = useCallback(
    async (updates: Array<{ work_order_id: number; planned_start_date: string; planned_end_date: string }>) => {
      const validUpdates = updates
        .map((u) => ({ ...u, work_order_id: Number((u as any).work_order_id) }))
        .filter((u) => Number.isInteger(u.work_order_id) && u.work_order_id > 0);
      if (validUpdates.length === 0) return;
      if (draftMode) {
        pushUndoSnapshot();
        mutateGanttWorkOrders((prev) => applyWorkOrderDateUpdates(prev ?? [], validUpdates));
        validUpdates.forEach((u) => draftWoUpdatesRef.current.set(u.work_order_id, u));
        syncDraftPendingCount();
        return;
      }
      try {
        await confirmAndPersist(validUpdates, []);
      } catch (e: any) {
        if (e?.message !== 'cancelled') {
          messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.scheduleUpdateFailed'));
          refreshGantt();
        }
        throw e;
      }
    },
    [
      confirmAndPersist,
      draftMode,
      messageApi,
      mutateGanttWorkOrders,
      pushUndoSnapshot,
      refreshGantt,
      syncDraftPendingCount,
      t,
    ]
  );

  const handleGanttBatchUpdateOperations = useCallback(
    async (updates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }>) => {
      const validUpdates = updates
        .map((u) => ({ ...u, operation_id: Number((u as any).operation_id) }))
        .filter((u) => Number.isInteger(u.operation_id) && u.operation_id > 0);
      if (validUpdates.length === 0) return;
      if (draftMode) {
        pushUndoSnapshot();
        mutateGanttWorkOrders((prev) => applyOperationDateUpdates(prev ?? [], validUpdates));
        validUpdates.forEach((u) => draftOpUpdatesRef.current.set(u.operation_id, u));
        syncDraftPendingCount();
        return;
      }
      try {
        await confirmAndPersist([], validUpdates);
      } catch (e: any) {
        if (e?.message !== 'cancelled') {
          messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.operationUpdateFailed'));
          refreshGantt();
        }
        throw e;
      }
    },
    [
      confirmAndPersist,
      draftMode,
      messageApi,
      mutateGanttWorkOrders,
      pushUndoSnapshot,
      refreshGantt,
      syncDraftPendingCount,
      t,
    ]
  );

  const handleCardBoardOperationUpdate = useCallback(
    async (updates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }>) => {
      await handleGanttBatchUpdateOperations(updates);
    },
    [handleGanttBatchUpdateOperations]
  );

  const handleBatchShift = useCallback(
    async (days: number) => {
      if (selectedWorkOrderIds.length === 0 || days === 0) return;
      const idSet = new Set(selectedWorkOrderIds);
      const updates = ganttWorkOrders
        .filter(
          (wo) =>
            idSet.has(wo.id) &&
            canShiftWorkOrder(wo, schedulingConstraints.freeze_horizon_days || 0, freezeAnchor)
        )
        .slice(0, 50)
        .map((wo) => ({
          work_order_id: wo.id,
          planned_start_date: toApiDateTimeString(dayjs(wo.planned_start_date).add(days, 'day')),
          planned_end_date: toApiDateTimeString(dayjs(wo.planned_end_date).add(days, 'day')),
        }));
      if (updates.length === 0) {
        messageApi.warning(t('app.kuaizhizao.scheduling.msg.batchShiftNoValid'));
        return;
      }
      setBatchActionLoading(true);
      try {
        await confirmAndPersist(updates, []);
        refreshGantt();
      } catch (e: any) {
        if (e?.message !== 'cancelled') messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.batchShiftFailed'));
      } finally {
        setBatchActionLoading(false);
      }
    },
    [confirmAndPersist, freezeAnchor, ganttWorkOrders, messageApi, refreshGantt, schedulingConstraints.freeze_horizon_days, selectedWorkOrderIds, t]
  );

  const handleGanttWorkOrderSelect = useCallback((workOrderId: number | null) => {
    if (workOrderId == null) {
      setSelectedRowKeys([]);
      return;
    }
    setSelectedRowKeys([workOrderId]);
  }, []);

  const handleFocusTaskConsumed = useCallback(() => {
    setFocusTaskId(null);
  }, []);

  const handleBatchUpdateOperationStations = useCallback(
    async (updates: Array<{ operation_id: number; assigned_station_id: number }>) => {
      if (!canScheduleUpdate || updates.length === 0) return;
      const isLineMode = schedulingConstraints.resource_mode === 'production_line';
      try {
        if (isLineMode) {
          const lineUpdates = updates.map((u) => ({
            operation_id: u.operation_id,
            assigned_production_line_id: Number(u.assigned_station_id),
          }));
          const validation = await visualSchedulingApi.validateAdjustments({
            operation_production_line_updates: lineUpdates,
          });
          if (!validation.valid) {
            const preview = (validation.conflicts || []).slice(0, 3).map((c) => c.message).join('\n');
            messageApi.error(
              preview || t('app.kuaizhizao.scheduling.msg.productionLineValidationFailed')
            );
            refreshGantt();
            return;
          }
          const result = await workOrderApi.batchUpdateOperationProductionLines(lineUpdates);
          const lineLabel = t('app.kuaizhizao.scheduling.batch.label.operationProductionLines');
          reportBatchUpdateResult(messageApi, lineLabel, {
            updated: result.updated,
            skipped_frozen: result.skipped_frozen,
            skipped_freeze_window: [],
            failed: result.failed,
          }, t);
        } else {
          const validation = await visualSchedulingApi.validateAdjustments({
            operation_station_updates: updates,
          });
          if (!validation.valid) {
            const preview = (validation.conflicts || []).slice(0, 3).map((c) => c.message).join('\n');
            messageApi.error(preview || t('app.kuaizhizao.scheduling.msg.stationValidationFailed'));
            refreshGantt();
            return;
          }
          const result = await workOrderApi.batchUpdateOperationStations(updates);
          const stationLabel = t('app.kuaizhizao.scheduling.batch.label.operationStations');
          reportBatchUpdateResult(messageApi, stationLabel, {
            updated: result.updated,
            skipped_frozen: result.skipped_frozen,
            skipped_freeze_window: [],
            failed: result.failed,
          }, t);
        }
        refreshGantt();
        refreshBoardScan();
      } catch (e: any) {
        messageApi.error(
          e?.message ||
            t(
              isLineMode
                ? 'app.kuaizhizao.scheduling.msg.productionLineReassignFailed'
                : 'app.kuaizhizao.scheduling.msg.stationReassignFailed'
            )
        );
        refreshGantt();
      }
    },
    [
      canScheduleUpdate,
      messageApi,
      refreshBoardScan,
      refreshGantt,
      schedulingConstraints.resource_mode,
      t,
    ]
  );

  const handleBatchUpdateOperationAssignments = useCallback(
    async (updates: GanttOperationAssignmentUpdate[]) => {
      if (!canScheduleUpdate || updates.length === 0) return;
      try {
        const result = await workOrderApi.batchUpdateOperationAssignments(updates);
        const assignmentLabel = t('app.kuaizhizao.scheduling.batch.label.operationAssignments');
        reportBatchUpdateResult(
          messageApi,
          assignmentLabel,
          {
            updated: result.updated,
            skipped_frozen: result.skipped_frozen,
            skipped_freeze_window: [],
            failed: result.failed,
          },
          t
        );
        refreshGantt();
        refreshBoardScan();
      } catch (e: any) {
        messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.assignmentReassignFailed'));
        refreshGantt();
      }
    },
    [canScheduleUpdate, messageApi, refreshBoardScan, refreshGantt, t]
  );

  const handleCardBoardResourceMove = useCallback(
    async (move: SchedulingCardResourceMove) => {
      const { operationId, fromResourceId, toResourceId } = move;
      if (fromResourceId === toResourceId || toResourceId <= 0) return;

      let op: NonNullable<WorkOrderForGantt['operations']>[number] | undefined;
      for (const wo of ganttBoardWorkOrders) {
        op = (wo.operations ?? []).find((item) => item.id === operationId);
        if (op) break;
      }
      if (!op) return;

      if (ganttTaskLevel === 'station') {
        await handleBatchUpdateOperationStations([
          { operation_id: operationId, assigned_station_id: toResourceId },
        ]);
        return;
      }

      if (ganttTaskLevel === 'equipment') {
        await handleBatchUpdateOperationAssignments([
          { operation_id: operationId, assigned_equipment_id: toResourceId },
        ]);
        return;
      }

      if (ganttTaskLevel === 'worker') {
        let nextIds = resolveWorkerIdsForOperation(op);
        nextIds = nextIds.filter((id) => id !== fromResourceId);
        if (!nextIds.includes(toResourceId)) {
          nextIds = [...nextIds, toResourceId];
        }
        await handleBatchUpdateOperationAssignments([
          { operation_id: operationId, assigned_worker_ids: nextIds },
        ]);
      }
    },
    [
      ganttBoardWorkOrders,
      ganttTaskLevel,
      handleBatchUpdateOperationAssignments,
      handleBatchUpdateOperationStations,
    ]
  );

  const handleSchedulingQuickAction = useCallback(
    async (
      action: 'confirm_delay' | 'to_exception' | 'apply_unfreeze',
      _title: string,
      reason: string,
      successPrefix: string,
    ) => {
      if (!canScheduleUpdate || selectedWorkOrderIds.length === 0) return;
      const ids = selectedWorkOrderIds.slice(0, 50);
      setQuickActionLoading(true);
      try {
        const result = await workOrderApi.schedulingQuickAction({
          work_order_ids: ids,
          action,
          reason,
          auto_move_out_of_freeze_window: action !== 'to_exception',
        });
        const failCount = result.failed?.length ?? 0;
        const skippedCount = result.skipped?.length ?? 0;
        const updatedCount = result.updated?.length ?? 0;
        const convertedCount = result.converted_to_exception?.length ?? 0;
        const unfreezedCount = result.unfreezed?.length ?? 0;
        messageApi.success(
          t('app.kuaizhizao.scheduling.msg.quickActionResult', {
            prefix: successPrefix,
            updated: updatedCount,
            converted: convertedCount,
            unfreezed: unfreezedCount,
            skipped: skippedCount,
            failedPart:
              failCount > 0
                ? t('app.kuaizhizao.scheduling.msg.quickActionResultFailed', { count: failCount })
                : '',
          })
        );
        refreshGantt();
        refreshBoardScan();
    actionRef.current?.reload();
      } catch (e: any) {
        messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.quickActionFailed'));
      } finally {
        setQuickActionLoading(false);
      }
    },
    [canScheduleUpdate, messageApi, refreshBoardScan, refreshGantt, selectedWorkOrderIds, t]
  );

  const handleConfirmDelay = useCallback(async () => {
    await handleSchedulingQuickAction(
      'confirm_delay',
      t('app.kuaizhizao.scheduling.msg.confirmDelayTitle'),
      t('app.kuaizhizao.scheduling.msg.confirmDelayReason'),
      t('app.kuaizhizao.scheduling.msg.confirmDelaySuccess')
    );
  }, [handleSchedulingQuickAction, t]);

  const handleToException = useCallback(async () => {
    await handleSchedulingQuickAction(
      'to_exception',
      t('app.kuaizhizao.scheduling.msg.toExceptionTitle'),
      t('app.kuaizhizao.scheduling.msg.toExceptionReason'),
      t('app.kuaizhizao.scheduling.msg.toExceptionSuccess')
    );
  }, [handleSchedulingQuickAction, t]);

  const handleApplyUnfreeze = useCallback(async () => {
    await handleSchedulingQuickAction(
      'apply_unfreeze',
      t('app.kuaizhizao.scheduling.msg.applyUnfreezeTitle'),
      t('app.kuaizhizao.scheduling.msg.applyUnfreezeReason'),
      t('app.kuaizhizao.scheduling.msg.applyUnfreezeSuccess')
    );
  }, [handleSchedulingQuickAction, t]);

  const applyEngineProposalPayloadToDraft = useCallback(
    async (engineProposal: SchedulingEngineProposalPayload) => {
      if (!canScheduleUpdate) return false;
      const proposal = convertEngineProposalToAiProposal(engineProposal);
      if ((engineProposal.unfreezed?.length ?? 0) > 0) {
        refreshGantt();
      }
      if (proposal.warnings.length > 0) {
        messageApi.info(proposal.warnings.slice(0, 3).join('；'));
      }
      if (proposal.confidenceNotes) {
        messageApi.info(proposal.confidenceNotes.slice(0, 200));
      }
      return applySchedulingAiProposal({
        proposal,
        draftWoUpdatesRef,
        draftOpUpdatesRef,
        draftStationUpdatesRef,
        mutateGanttWorkOrders,
        pushUndoSnapshot,
        syncDraftPendingCount,
        setDraftMode,
        resourceMode: schedulingConstraints.resource_mode,
        message: messageApi,
        t,
      });
    },
    [
      canScheduleUpdate,
      draftOpUpdatesRef,
      draftStationUpdatesRef,
      draftWoUpdatesRef,
      messageApi,
      mutateGanttWorkOrders,
      pushUndoSnapshot,
      refreshGantt,
      schedulingConstraints.resource_mode,
      syncDraftPendingCount,
      t,
    ]
  );

  const applyEngineProposalToDraft = useCallback(
    async (
      scope: 'selected' | 'overdue' | 'unscheduled' | 'local',
      workOrderIds: number[],
      opts?: { local_window_hours?: number; strategy?: string }
    ) => {
      if (!canScheduleUpdate || workOrderIds.length === 0) return false;
      setAutoRescheduleLoading(true);
      try {
        const res = await visualSchedulingApi.autoReschedule({
          work_order_ids: workOrderIds,
          scope,
          plan_date: filterPlanDate,
          local_window_hours: opts?.local_window_hours,
          strategy: opts?.strategy,
        });
        return applyEngineProposalPayloadToDraft(res.proposal);
      } catch (e: any) {
        messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.autoRescheduleFailed'));
        return false;
      } finally {
        setAutoRescheduleLoading(false);
      }
    },
    [
      applyEngineProposalPayloadToDraft,
      canScheduleUpdate,
      filterPlanDate,
      messageApi,
      t,
    ]
  );

  /** 自动/局部/逾期重排前：产线模式不走工位工时补齐；缺产线可补齐，缺节拍硬拦 */
  const guardEngineRescheduleGaps = useCallback(
    (ids: number[]): boolean => {
      const idSet = new Set(ids);
      const relatedGaps = (boardScan?.missing_settings ?? []).filter((g) =>
        idSet.has(g.work_order_id)
      );
      if (relatedGaps.length === 0) return true;
      const isLineMode = schedulingConstraints.resource_mode === 'production_line';
      if (isLineMode) {
        const capacityGaps = relatedGaps.filter(
          (g) => g.field === 'takt_seconds' || g.field === 'daily_capacity_qty'
        );
        if (capacityGaps.length > 0) {
          messageApi.error(t('app.kuaizhizao.scheduling.prep.missingTaktCapacity'));
          return false;
        }
        const lineGaps = relatedGaps.filter((g) => g.field === 'assigned_production_line_id');
        if (lineGaps.length > 0) {
          openMissingSettingsModal(lineGaps, ids);
          return false;
        }
        return true;
      }
      openMissingSettingsModal(relatedGaps, ids);
      return false;
    },
    [
      boardScan?.missing_settings,
      messageApi,
      openMissingSettingsModal,
      schedulingConstraints.resource_mode,
      t,
    ]
  );

  const handleAutoReschedule = useCallback(async () => {
    const ids = selectedWorkOrderIds.slice(0, 50);
    if (ids.length === 0) return;
    if (!guardEngineRescheduleGaps(ids)) return;

    const { allowedIds, blockedIds, warnIds } = filterWorkOrderIdsByMaterialGate(
      ids,
      schedulingConstraints,
      boardScan
    );
    if (blockedIds.length > 0 && allowedIds.length === 0 && warnIds.length === 0) {
      messageApi.error(
        t('app.kuaizhizao.scheduling.materialGate.blockAutoReschedule', { count: blockedIds.length })
      );
      return;
    }

    const targetIds = [...allowedIds, ...warnIds];
    if (targetIds.length === 0) return;

    const openWizard = () => {
      setRescheduleWizardIds(targetIds);
      setRescheduleWizardOpen(true);
    };

    const materialDescription = buildMaterialGateConfirmDescription(
      warnIds.length,
      blockedIds.length,
      t
    );
    if (materialDescription) {
      modal.confirm({
        title: t('app.kuaizhizao.scheduling.msg.autoRescheduleTitle'),
        content: materialDescription,
        okText: t('app.kuaizhizao.scheduling.common.confirm'),
        cancelText: t('common.cancel'),
        onOk: () => {
          openWizard();
        },
      });
      return;
    }

    openWizard();
  }, [
    boardScan,
    guardEngineRescheduleGaps,
    messageApi,
    schedulingConstraints,
    selectedWorkOrderIds,
    modal,
    t,
  ]);

  const handleLocalReschedule = useCallback(async () => {
    const ids = selectedWorkOrderIds.slice(0, 50);
    if (ids.length === 0) return;
    if (!guardEngineRescheduleGaps(ids)) return;
    await applyEngineProposalToDraft('local', ids, { local_window_hours: 24 });
  }, [applyEngineProposalToDraft, guardEngineRescheduleGaps, selectedWorkOrderIds]);

  const handleMissingSettingsBackfill = useCallback(async () => {
    if (!canScheduleUpdate) return;
    const isLineMode = schedulingConstraints.resource_mode === 'production_line';
    for (const row of missingSettingsRows) {
      if (!isLineMode && row.needHours) {
        const setup = Number(row.setup_time ?? 0);
        const std = Number(row.standard_time ?? 0);
        if (!(setup > 0 || std > 0)) {
          messageApi.warning(
            t('app.kuaizhizao.scheduling.msg.missingHoursRequired', {
              code: row.work_order_code,
              op: row.operation_name,
            }),
          );
          return;
        }
      }
      if (row.needCapacity) {
        messageApi.error(t('app.kuaizhizao.scheduling.prep.missingTaktCapacity'));
        return;
      }
      if (row.needStation && !(Number(row.assigned_station_id) > 0)) {
        messageApi.warning(
          t(
            isLineMode
              ? 'app.kuaizhizao.scheduling.msg.missingProductionLineRequired'
              : 'app.kuaizhizao.scheduling.msg.missingStationRequired',
            {
              code: row.work_order_code,
              op: row.operation_name,
            }
          )
        );
        return;
      }
    }
    setMissingSettingsSaving(true);
    try {
      if (isLineMode) {
        const lineUpdates = missingSettingsRows
          .filter((row) => row.needStation && Number(row.assigned_station_id) > 0)
          .map((row) => ({
            operation_id: row.operation_id,
            assigned_production_line_id: Number(row.assigned_station_id),
          }));
        if (lineUpdates.length > 0) {
          const lineResult = await workOrderApi.batchUpdateOperationProductionLines(lineUpdates);
          const lineLabel = t('app.kuaizhizao.scheduling.batch.label.operationProductionLines');
          ensureBatchUpdatesPersisted(
            {
              updated: lineResult.updated,
              skipped_frozen: lineResult.skipped_frozen,
              skipped_freeze_window: [],
              failed: lineResult.failed,
            },
            lineUpdates.length,
            lineLabel,
            t
          );
          reportBatchUpdateResult(messageApi, lineLabel, {
            updated: lineResult.updated,
            skipped_frozen: lineResult.skipped_frozen,
            skipped_freeze_window: [],
            failed: lineResult.failed,
          }, t);
        }
      } else {
        const items = missingSettingsRows.map((row) => {
          const patch: {
            operation_id: number;
            setup_time?: number;
            standard_time?: number;
            assigned_station_id?: number;
          } = { operation_id: row.operation_id };
          if (row.needHours) {
            patch.setup_time = Number(row.setup_time ?? 0);
            patch.standard_time = Number(row.standard_time ?? 0);
          }
          if (row.needStation && row.assigned_station_id) {
            patch.assigned_station_id = Number(row.assigned_station_id);
          }
          return patch;
        });
        await visualSchedulingApi.backfillOperationSettings(items);
      }
      messageApi.success(t('app.kuaizhizao.scheduling.msg.missingBackfillSuccess'));
      setMissingSettingsModalOpen(false);
      setMissingSettingsProductByWo(new Map());
      refreshGantt();
      refreshBoardScan();
      const continueIds = pendingAutoRescheduleIds;
      setPendingAutoRescheduleIds(null);
      if (continueIds?.length) {
        await applyEngineProposalToDraft('selected', continueIds);
      }
    } catch (e: any) {
      messageApi.error(e?.response?.data?.detail || e?.message || t('app.kuaizhizao.scheduling.msg.missingBackfillFailed'));
    } finally {
      setMissingSettingsSaving(false);
    }
  }, [
    applyEngineProposalToDraft,
    canScheduleUpdate,
    messageApi,
    missingSettingsRows,
    pendingAutoRescheduleIds,
    refreshBoardScan,
    refreshGantt,
    schedulingConstraints.resource_mode,
    t,
  ]);

  const handleRescheduleForward = useCallback(async () => {
    const ids = selectedWorkOrderIds.slice(0, 50);
    if (ids.length === 0) return;
    if (!guardEngineRescheduleGaps(ids)) return;
    await applyEngineProposalToDraft('overdue', ids);
  }, [applyEngineProposalToDraft, guardEngineRescheduleGaps, selectedWorkOrderIds]);

  const handleGanttOperationSelect = useCallback(
    (operationId: number, workOrderId: number | null) => {
      if (!workOrderId) return;
      const wo = ganttWorkOrders.find((item) => item.id === workOrderId);
      if (!wo) return;
      setOperationEditContext({ workOrder: wo, operationId });
    },
    [ganttWorkOrders]
  );

  const handleGanttOperationDoubleClick = useCallback(
    (operationId: number, workOrderId: number | null) => {
      if (!workOrderId) return;
      const wo = ganttBoardWorkOrders.find((item) => item.id === workOrderId)
        ?? ganttWorkOrders.find((item) => item.id === workOrderId);
      if (!wo) return;
      setOperationEditContext({ workOrder: wo, operationId });
      setOperationEditOpen(true);
    },
    [ganttBoardWorkOrders, ganttWorkOrders]
  );

  const persistOperationScheduling = useCallback(
    async (
      operationDateUpdates: Array<{ operation_id: number; planned_start_date: string; planned_end_date: string }>,
      operationStationUpdates: Array<{ operation_id: number; assigned_station_id: number }>
    ) => {
      const isLineMode = schedulingConstraints.resource_mode === 'production_line';
      if (operationStationUpdates.length > 0) {
        if (isLineMode) {
          const lineUpdates = operationStationUpdates.map((u) => ({
            operation_id: u.operation_id,
            assigned_production_line_id: Number(u.assigned_station_id),
          }));
          const validation = await visualSchedulingApi.validateAdjustments({
            operation_production_line_updates: lineUpdates,
            operation_updates: operationDateUpdates,
          });
          if (!validation.valid) {
            const preview = (validation.conflicts || []).slice(0, 3).map((c) => c.message).join('\n');
            throw new Error(preview || t('app.kuaizhizao.scheduling.msg.validationFailed'));
          }
          const lineResult = await workOrderApi.batchUpdateOperationProductionLines(lineUpdates);
          const lineLabel = t('app.kuaizhizao.scheduling.batch.label.operationProductionLines');
          ensureBatchUpdatesPersisted(
            {
              updated: lineResult.updated,
              skipped_frozen: lineResult.skipped_frozen,
              skipped_freeze_window: [],
              failed: lineResult.failed,
            },
            lineUpdates.length,
            lineLabel,
            t
          );
          reportBatchUpdateResult(messageApi, lineLabel, {
            updated: lineResult.updated,
            skipped_frozen: lineResult.skipped_frozen,
            skipped_freeze_window: [],
            failed: lineResult.failed,
          }, t);
        } else {
          const validation = await visualSchedulingApi.validateAdjustments({
            operation_station_updates: operationStationUpdates,
            operation_updates: operationDateUpdates,
          });
          if (!validation.valid) {
            const preview = (validation.conflicts || []).slice(0, 3).map((c) => c.message).join('\n');
            throw new Error(preview || t('app.kuaizhizao.scheduling.msg.validationFailed'));
          }
          const stationResult = await workOrderApi.batchUpdateOperationStations(operationStationUpdates);
          const stationLabel = t('app.kuaizhizao.scheduling.batch.label.operationStations');
          ensureBatchUpdatesPersisted(
            {
              updated: stationResult.updated,
              skipped_frozen: stationResult.skipped_frozen,
              skipped_freeze_window: [],
              failed: stationResult.failed,
            },
            operationStationUpdates.length,
            stationLabel,
            t
          );
          reportBatchUpdateResult(messageApi, stationLabel, {
            updated: stationResult.updated,
            skipped_frozen: stationResult.skipped_frozen,
            skipped_freeze_window: [],
            failed: stationResult.failed,
          }, t);
        }
      }
      if (operationDateUpdates.length > 0 && operationStationUpdates.length === 0) {
        const validation = await visualSchedulingApi.validateAdjustments({
          operation_updates: operationDateUpdates,
        });
        if (!validation.valid) {
          const preview = (validation.conflicts || []).slice(0, 3).map((c) => c.message).join('\n');
          throw new Error(preview || t('app.kuaizhizao.scheduling.msg.validationFailed'));
        }
        const opLabel = t('app.kuaizhizao.scheduling.batch.label.operationDates');
        const opResult = await workOrderApi.batchUpdateOperationDates(operationDateUpdates);
        ensureBatchUpdatesPersisted(opResult, operationDateUpdates.length, opLabel, t);
        reportBatchUpdateResult(messageApi, opLabel, opResult, t);
      } else if (operationDateUpdates.length > 0) {
        const opLabel = t('app.kuaizhizao.scheduling.batch.label.operationDates');
        const opResult = await workOrderApi.batchUpdateOperationDates(operationDateUpdates);
        ensureBatchUpdatesPersisted(opResult, operationDateUpdates.length, opLabel, t);
        reportBatchUpdateResult(messageApi, opLabel, opResult, t);
      }
    },
    [messageApi, schedulingConstraints.resource_mode, t]
  );

  const refreshGanttPreservingWorkOrder = useCallback(
    async (scheduledWo: WorkOrderForGantt) => {
      try {
        const res = await workOrderApi.list(buildWorkOrderParams({}, { limit: GANTT_WORK_ORDER_LIMIT }));
        let list = Array.isArray(res) ? res : (res?.data ?? []);
        list = list.filter((wo: WorkOrderForGantt) => isSchedulableWorkOrderStatus(wo.status));
        if (filterWorkOrderIds?.length) {
          const idSet = new Set(filterWorkOrderIds);
          list = list.filter((wo: WorkOrderForGantt) => idSet.has(wo.id));
        }
        const merged = (list as WorkOrderForGantt[]).map((item) =>
          item.id === scheduledWo.id ? mergeApiWorkOrderWithScheduled(item, scheduledWo) : item
        );
        mutateGanttWorkOrders(merged);
      } catch (e: unknown) {
        // 本地已合并结果仍保留；刷新失败须可见，禁止静默丢错
        const detail =
          e && typeof e === 'object' && 'message' in e
            ? String((e as { message?: unknown }).message || '')
            : '';
        messageApi.warning(
          detail || t('app.kuaizhizao.scheduling.msg.ganttRefreshFailedKeepLocal')
        );
      }
    },
    [buildWorkOrderParams, filterWorkOrderIds, messageApi, mutateGanttWorkOrders, t]
  );

  const completeDropWorkOrderToBoard = useCallback(
    async (wo: WorkOrderForGantt, options?: { productionLineId?: number | null }) => {
      const isLineMode = schedulingConstraints.resource_mode === 'production_line';
      if (isLineMode && lineCapacitiesError) {
        throw new Error(t('app.kuaizhizao.scheduling.msg.lineCapacityLoadFailed'));
      }
      let workingWo = wo;
      if (isLineMode && options?.productionLineId != null && Number(options.productionLineId) > 0) {
        const lineId = Number(options.productionLineId);
        if (linesMissingTakt.includes(lineId)) {
          throw new Error(t('app.kuaizhizao.scheduling.prep.missingTaktCapacity'));
        }
        const productId = Number(wo.product_id || 0);
        if (!lineAcceptsProduct(lineId, productId)) {
          throw new Error(t('app.kuaizhizao.scheduling.msg.lineProductNotAllowed'));
        }
        const lineName = workstationResources.find((r) => r.id === lineId)?.name;
        workingWo = stampProductionLineOnWorkOrder(wo, lineId, lineName);
      }
      const boardOrders = ganttWorkOrders.filter(
        (item) => isWorkOrderScheduledOnBoard(item) || item.id === workingWo.id
      );
      const mergedBoardOrders = boardOrders.map((item) =>
        item.id === workingWo.id ? { ...item, ...workingWo } : item
      );
      const result = buildScheduleWorkOrderDrop(workingWo, mergedBoardOrders, {
        resourceMode: schedulingConstraints.resource_mode,
        taktSecondsByLineId,
        dailyCapacityByLineId,
        defaultProductionLineId: options?.productionLineId,
      });
      if (result.errorCode === 'daily_capacity_exceeded') {
        throw new Error(t('app.kuaizhizao.scheduling.msg.dailyCapacityExceeded'));
      }
      if (result.errorCode === 'missing_takt') {
        throw new Error(t('app.kuaizhizao.scheduling.prep.missingTaktCapacity'));
      }
      if (isLineMode && result.pendingOperations.length > 0) {
        const stampedLine =
          options?.productionLineId != null && Number(options.productionLineId) > 0
            ? Number(options.productionLineId)
            : null;
        const missingTakt =
          stampedLine != null
            ? linesMissingTakt.includes(stampedLine)
            : (workingWo.operations ?? []).some((op) => {
                const lineId = Number(op.assigned_production_line_id ?? 0);
                return lineId > 0 && linesMissingTakt.includes(lineId);
              });
        throw new Error(
          t(
            missingTakt
              ? 'app.kuaizhizao.scheduling.prep.missingTaktCapacity'
              : 'app.kuaizhizao.scheduling.prep.selectProductionLineRequired'
          )
        );
      }
      await persistOperationScheduling(result.operationDateUpdates, result.operationStationUpdates);
      if (result.workOrderDateUpdate) {
        await workOrderApi.batchUpdateDates([
          {
            work_order_id: workingWo.id,
            planned_start_date: result.workOrderDateUpdate.planned_start_date,
            planned_end_date: result.workOrderDateUpdate.planned_end_date,
          },
        ]);
      }

      const stationNameById = new Map(
        workstationResources.map((station) => [station.id, station.name])
      );
      const scheduledWo = mergeScheduledWorkOrderIntoBoard(workingWo, result, stationNameById, {
        asProductionLine: isLineMode,
      });

      setSelectedRowKeys([scheduledWo.id]);

      const focusTask = pickFocusOperationTaskId(scheduledWo);
      if (focusTask) {
        setFocusTaskId(focusTask);
      }

      if (result.pendingOperations.length > 0) {
        messageApi.warning(
          t('app.kuaizhizao.scheduling.msg.stationsSavedPending', {
            pending: result.pendingOperations.length,
            scheduledPart:
              result.operationDateUpdates.length > 0
                ? t('app.kuaizhizao.scheduling.msg.stationsSavedScheduledPart', {
                    count: result.operationDateUpdates.length,
                  })
                : '',
          })
        );
      } else if (result.operationDateUpdates.length > 0) {
        messageApi.success(
          isLineMode
            ? t('app.kuaizhizao.scheduling.msg.savedWorkOrderToGantt')
            : t('app.kuaizhizao.scheduling.msg.savedToGantt', {
                count: result.operationDateUpdates.length,
              })
        );
      } else {
        messageApi.success(t('app.kuaizhizao.scheduling.msg.stationsSavedDisplay'));
      }

      refreshBoardScan();
      actionRef.current?.reload();
      await refreshGanttPreservingWorkOrder(scheduledWo);
    },
    [
      dailyCapacityByLineId,
      ganttWorkOrders,
      lineAcceptsProduct,
      lineCapacitiesError,
      linesMissingTakt,
      messageApi,
      persistOperationScheduling,
      refreshBoardScan,
      refreshGanttPreservingWorkOrder,
      schedulingConstraints.resource_mode,
      taktSecondsByLineId,
      workstationResources,
      t,
    ]
  );

  const openSchedulingPrepModal = useCallback(
    async (wo: WorkOrderForGantt) => {
      const resourceMode = schedulingConstraints.resource_mode;
      setPrepModalLoading(true);
      setPrepModalWorkOrder(wo);
      setPrepModalMissing(getWorkOrderSchedulingPrepContext(wo, resourceMode).missingFields);
      setPrepModalOperationsNeedingStation([]);
      try {
        const fetched = await workOrderApi.getOperations(String(wo.id));
        const rawOps = Array.isArray(fetched)
          ? fetched
          : ((fetched as { operations?: Record<string, unknown>[] })?.operations ?? []);
        const operations = rawOps.map((op) => mapOperationForGantt(op));
        const woWithOps: WorkOrderForGantt = { ...wo, operations };
        const ctx = getWorkOrderSchedulingPrepContext(woWithOps, resourceMode);
        setPrepModalWorkOrder(woWithOps);
        setPrepModalMissing(ctx.missingFields);
        // 产线模式只列厂内工序（委外不占产线）；工位模式列全部待补工序
        setPrepModalOperationsNeedingStation(getOperationsForStationPrep(woWithOps, resourceMode));
        setPrepModalOpen(true);
      } catch (e: any) {
        messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.loadOperationsFailed'));
        setPrepModalOpen(false);
        setPrepModalWorkOrder(null);
        setPrepModalMissing([]);
        setPrepModalOperationsNeedingStation([]);
      } finally {
        setPrepModalLoading(false);
      }
    },
    [messageApi, schedulingConstraints.resource_mode, t]
  );

  const handleDropWorkOrderToBoard = useCallback(
    async (
      workOrderId: number,
      meta?: { clientX: number; clientY: number }
    ) => {
      if (!canScheduleUpdate) return;
      const wo = ganttWorkOrders.find((item) => item.id === workOrderId);
      if (!wo) {
        messageApi.warning(t('app.kuaizhizao.scheduling.msg.workOrderNotFound'));
        return;
      }
      const resourceMode = schedulingConstraints.resource_mode;
      const isLineMode = resourceMode === 'production_line';
      if (isLineMode && lineCapacitiesError) {
        messageApi.error(t('app.kuaizhizao.scheduling.msg.lineCapacityLoadFailed'));
        return;
      }
      // 仅工位/产线泳道视图解析落点；设备/人员视图不误读 st-* 为产线（不改工位业务线）
      const dropLineId =
        isLineMode && ganttTaskLevel === 'station' && meta
          ? resolveGanttStationResourceIdFromPoint(meta.clientX, meta.clientY)
          : null;
      if (isLineMode && dropLineId != null && dropLineId > 0 && linesMissingTakt.includes(dropLineId)) {
        messageApi.error(t('app.kuaizhizao.scheduling.prep.missingTaktCapacity'));
        return;
      }
      const woProductId = Number(wo.product_id || 0);
      if (
        isLineMode &&
        dropLineId != null &&
        dropLineId > 0 &&
        !lineAcceptsProduct(dropLineId, woProductId)
      ) {
        messageApi.error(t('app.kuaizhizao.scheduling.msg.lineProductNotAllowed'));
        return;
      }
      // 行业包产线模式：拖到某条产线泳道则直接盖产线；仅一条兼容且已配节拍的产线时可默认
      const eligibleLineIds = isLineMode
        ? eligibleConfiguredLineIdsForProduct(woProductId)
        : workstationResources.map((l) => l.id).filter((id) => !linesMissingTakt.includes(id));
      const autoLineId =
        dropLineId && dropLineId > 0
          ? dropLineId
          : isLineMode && eligibleLineIds.length === 1
            ? eligibleLineIds[0]
            : null;

      const alreadyOnBoard = isWorkOrderScheduledOnBoard(wo);
      const needsPrep =
        autoLineId != null
          ? false
          : workOrderNeedsSchedulingPrep(wo, resourceMode);
      if (alreadyOnBoard && !needsPrep && autoLineId == null) {
        messageApi.info(t('app.kuaizhizao.scheduling.msg.alreadyOnBoard'));
        return;
      }

      const proceedDrop = async () => {
        if (needsPrep) {
          await openSchedulingPrepModal(wo);
          return;
        }
        try {
          await completeDropWorkOrderToBoard(wo, { productionLineId: autoLineId });
        } catch (e: any) {
          messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.dropFailed'));
          refreshGantt();
        }
      };

      const materialGate = resolveMaterialGateDecision(wo.id, schedulingConstraints, boardScan);
      if (materialGate === 'block') {
        const issue = getMaterialIssueForWorkOrder(wo.id, boardScan);
        messageApi.error(
          issue?.message || t('app.kuaizhizao.scheduling.materialGate.blockDrop')
        );
        return;
      }
      if (materialGate === 'warn') {
        const issue = getMaterialIssueForWorkOrder(wo.id, boardScan);
        modal.confirm({
          title: t('app.kuaizhizao.scheduling.materialGate.warnDropTitle'),
          content: issue?.message || t('app.kuaizhizao.scheduling.materialGate.warnDropContent'),
          okText: t('app.kuaizhizao.scheduling.materialGate.warnDropOk'),
          cancelText: t('common.cancel'),
          onOk: () => void proceedDrop(),
        });
        return;
      }

      await proceedDrop();
    },
    [
      boardScan,
      canScheduleUpdate,
      completeDropWorkOrderToBoard,
      eligibleConfiguredLineIdsForProduct,
      ganttTaskLevel,
      ganttWorkOrders,
      lineAcceptsProduct,
      lineCapacitiesError,
      linesMissingTakt,
      messageApi,
      modal,
      openSchedulingPrepModal,
      refreshGantt,
      schedulingConstraints,
      t,
      workstationResources,
    ]
  );

  const handlePrepModalSubmit = useCallback(
    async (values: SchedulingWorkOrderPrepValues) => {
      if (!prepModalWorkOrder) return;
      setPrepModalSaving(true);
      try {
        const isLineMode = schedulingConstraints.resource_mode === 'production_line';
        // 工位模式：缺头表计划日时先单条 update；产线/工位最终都以工序窗口同步头表（见下方 batchUpdateDates）
        const needsDateUpdate =
          !isLineMode &&
          (prepModalMissing.includes('planned_start_date') ||
            prepModalMissing.includes('planned_end_date'));
        if (needsDateUpdate && values.planned_start_date && values.planned_end_date) {
          await workOrderApi.update(String(prepModalWorkOrder.id), {
            planned_start_date: values.planned_start_date,
            planned_end_date: values.planned_end_date,
          });
        }

        const stationByOp = new Map(
          values.operationStations.map((item) => [item.operation_id, item.assigned_station_id])
        );
        const dateByOp = new Map(
          values.operationDates.map((item) => [item.operation_id, item])
        );
        const stationNameById = new Map(
          workstationResources.map((station) => [station.id, station.name])
        );
        const updatedOps = (prepModalWorkOrder.operations ?? []).map((op) => {
          if (op.id == null) return op;
          const stationId = stationByOp.get(op.id);
          const datePatch = dateByOp.get(op.id);
          let next = op;
          if (stationId != null) {
            next = isLineMode
              ? {
                  ...next,
                  assigned_production_line_id: stationId,
                  assigned_production_line_name:
                    stationNameById.get(stationId) ?? op.assigned_production_line_name,
                  assigned_station_id: stationId,
                  assigned_station_name: stationNameById.get(stationId) ?? op.assigned_station_name,
                }
              : {
                  ...next,
                  assigned_station_id: stationId,
                  assigned_station_name: stationNameById.get(stationId) ?? op.assigned_station_name,
                };
          }
          if (datePatch) {
            next = {
              ...next,
              planned_start_date: datePatch.planned_start_date,
              planned_end_date: datePatch.planned_end_date,
            };
          }
          return next;
        });

        const woDatesFromOps = values.operationDates;
        let woPlannedStart = values.planned_start_date ?? prepModalWorkOrder.planned_start_date;
        let woPlannedEnd = values.planned_end_date ?? prepModalWorkOrder.planned_end_date;
        if (woDatesFromOps.length > 0) {
          const starts = woDatesFromOps.map((item) => item.planned_start_date).sort();
          const ends = woDatesFromOps.map((item) => item.planned_end_date).sort();
          woPlannedStart = starts[0];
          woPlannedEnd = ends[ends.length - 1];
        }

        if (values.operationDates.length > 0 || values.operationStations.length > 0) {
          await persistOperationScheduling(values.operationDates, values.operationStations);
        }
        if (woPlannedStart && woPlannedEnd) {
          await workOrderApi.batchUpdateDates([
            {
              work_order_id: prepModalWorkOrder.id,
              planned_start_date: woPlannedStart,
              planned_end_date: woPlannedEnd,
            },
          ]);
        }
        if (values.operationAssignments.length > 0) {
          await workOrderApi.batchUpdateOperationAssignments(values.operationAssignments);
        }

        const assignmentByOp = new Map(values.operationAssignments.map((item) => [item.operation_id, item]));
        const workerNameById = new Map(schedulingWorkers.map((w) => [w.id, w.name]));
        const equipmentNameById = new Map(schedulingEquipments.map((e) => [e.id, e.name]));
        const moldNameById = new Map(schedulingMolds.map((m) => [m.id, m.name]));
        const updatedOpsWithAssignments = updatedOps.map((op) => {
          if (op.id == null) return op;
          const patch = assignmentByOp.get(op.id);
          if (!patch) return op;
          return {
            ...op,
            assigned_worker_id: patch.assigned_worker_id ?? op.assigned_worker_id,
            assigned_worker_name:
              patch.assigned_worker_id != null
                ? workerNameById.get(patch.assigned_worker_id) ?? op.assigned_worker_name
                : op.assigned_worker_name,
            assigned_equipment_id: patch.assigned_equipment_id ?? op.assigned_equipment_id,
            assigned_equipment_name:
              patch.assigned_equipment_id != null
                ? equipmentNameById.get(patch.assigned_equipment_id) ?? op.assigned_equipment_name
                : op.assigned_equipment_name,
            assigned_mold_id: patch.assigned_mold_id ?? op.assigned_mold_id,
            assigned_mold_name:
              patch.assigned_mold_id != null
                ? moldNameById.get(patch.assigned_mold_id) ?? op.assigned_mold_name
                : op.assigned_mold_name,
          };
        });

        const updatedWo: WorkOrderForGantt = {
          ...prepModalWorkOrder,
          planned_start_date: woPlannedStart,
          planned_end_date: woPlannedEnd,
          operations: updatedOpsWithAssignments,
        };

        setSelectedRowKeys([updatedWo.id]);
        const focusTask = pickFocusOperationTaskId(updatedWo);
        if (focusTask) {
          setFocusTaskId(focusTask);
        }
        messageApi.success(
          t('app.kuaizhizao.scheduling.msg.savedToGantt', {
            count: values.operationDates.length || updatedOps.length,
          })
        );
        refreshBoardScan();
    actionRef.current?.reload();
        await refreshGanttPreservingWorkOrder(updatedWo);

        setPrepModalOpen(false);
        setPrepModalWorkOrder(null);
        setPrepModalMissing([]);
        setPrepModalOperationsNeedingStation([]);
      } catch (e: any) {
        messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.savePrepFailed'));
      } finally {
        setPrepModalSaving(false);
      }
    },
    [
      messageApi,
      persistOperationScheduling,
      prepModalMissing,
      prepModalWorkOrder,
      refreshBoardScan,
      refreshGanttPreservingWorkOrder,
      schedulingConstraints.resource_mode,
      schedulingEquipments,
      schedulingMolds,
      schedulingWorkers,
      t,
      workstationResources,
    ]
  );

  const handleClearScheduling = useCallback(async () => {
    if (selectedWorkOrderIds.length === 0) return;
    setBatchActionLoading(true);
    try {
      const result = await workOrderApi.batchClearOperationScheduling({
        work_order_ids: selectedWorkOrderIds.slice(0, 50),
        resource_mode: schedulingConstraints.resource_mode,
        clear_header_dates: true,
      });
      const cleared = result.cleared_work_order_ids?.length ?? 0;
      const frozen = result.skipped_frozen?.length ?? 0;
      const freezeWindow = result.skipped_freeze_window?.length ?? 0;
      const failed = result.failed?.length ?? 0;
      if (cleared > 0) {
        messageApi.success(
          t('app.kuaizhizao.scheduling.msg.clearSchedulingSuccess', { count: cleared })
        );
      }
      if (frozen > 0) {
        messageApi.warning(
          t('app.kuaizhizao.scheduling.msg.clearSchedulingSkippedFrozen', { count: frozen })
        );
      }
      if (freezeWindow > 0) {
        messageApi.warning(
          t('app.kuaizhizao.scheduling.msg.clearSchedulingSkippedFreezeWindow', {
            count: freezeWindow,
          })
        );
      }
      if (failed > 0) {
        messageApi.error(
          t('app.kuaizhizao.scheduling.msg.clearSchedulingFailed', { count: failed })
        );
      }
      if (cleared === 0 && frozen === 0 && freezeWindow === 0 && failed === 0) {
        messageApi.info(t('app.kuaizhizao.scheduling.msg.clearSchedulingNothing'));
      }
      setSelectedRowKeys([]);
      refreshGantt();
      refreshBoardScan();
      actionRef.current?.reload();
    } catch (e: any) {
      messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.clearSchedulingError'));
    } finally {
      setBatchActionLoading(false);
    }
  }, [
    messageApi,
    refreshBoardScan,
    refreshGantt,
    schedulingConstraints.resource_mode,
    selectedWorkOrderIds,
    t,
  ]);

  const handleBatchFreeze = useCallback(async () => {
    if (selectedWorkOrderIds.length === 0) return;
    setBatchActionLoading(true);
    try {
      await Promise.all(
        selectedWorkOrderIds
          .slice(0, 50)
          .map((id) => workOrderApi.freeze(String(id), { freeze_reason: t('app.kuaizhizao.scheduling.msg.freezeReason') }))
      );
      messageApi.success(t('app.kuaizhizao.scheduling.msg.batchFreezeSuccess'));
      refreshGantt();
      actionRef.current?.reload();
    } catch (e: any) {
      messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.batchFreezeFailed'));
    } finally {
      setBatchActionLoading(false);
    }
  }, [messageApi, refreshGantt, selectedWorkOrderIds, t]);

  const handleBatchUnfreeze = useCallback(async () => {
    if (selectedWorkOrderIds.length === 0) return;
    setBatchActionLoading(true);
    try {
      await Promise.all(selectedWorkOrderIds.slice(0, 50).map((id) => workOrderApi.unfreeze(String(id))));
      messageApi.success(t('app.kuaizhizao.scheduling.msg.batchUnfreezeSuccess'));
      refreshGantt();
      actionRef.current?.reload();
    } catch (e: any) {
      messageApi.error(e?.message || t('app.kuaizhizao.scheduling.msg.batchUnfreezeFailed'));
    } finally {
      setBatchActionLoading(false);
    }
  }, [messageApi, refreshGantt, selectedWorkOrderIds, t]);

  const handleRefreshAll = useCallback(() => {
    refreshGantt();
    refreshBoardScan();
    refreshPlanReliability();
  }, [refreshBoardScan, refreshGantt, refreshPlanReliability]);

  const columns: ProColumns<WorkOrderForGantt>[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.scheduling.col.workOrderCode'),
        dataIndex: 'code',
        width: 130,
        ellipsis: true,
        fixed: 'left',
        render: (_: unknown, record) => {
          const rank = aiSuggestedPoolRankById.get(record.id);
          return (
            <Space size={4}>
              <span>{record.code}</span>
              {rank != null ? (
                <Tag color="processing" className="scheduling-pool-ai-rank">
                  {t('app.kuaizhizao.scheduling.aiAssist.poolRank', { rank })}
                </Tag>
              ) : null}
            </Space>
          );
        },
      },
      {
        title: t('app.kuaizhizao.scheduling.col.operationCount'),
        width: 64,
        align: 'center',
        render: (_: unknown, record) => {
          const count = countWorkOrderOperations(record);
          return count > 0 ? count : <Typography.Text type="secondary">0</Typography.Text>;
        },
      },
      {
        title: t('app.kuaizhizao.scheduling.col.scheduledOpCount'),
        width: 88,
        align: 'center',
        render: (_: unknown, record) => {
          const total = countWorkOrderOperations(record);
          const scheduled = countScheduledOperations(record);
          if (total <= 0) {
            return <Typography.Text type="secondary">0</Typography.Text>;
          }
          const label = String(scheduled);
          const tooltip = t('app.kuaizhizao.scheduling.col.scheduledOpsTooltip', { scheduled, total });
          if (scheduled >= total) {
            return (
              <Tooltip title={tooltip}>
                <Typography.Text>{label}</Typography.Text>
              </Tooltip>
            );
          }
          return (
            <Tooltip title={tooltip}>
              <Typography.Text type={scheduled > 0 ? undefined : 'secondary'}>{label}</Typography.Text>
            </Tooltip>
          );
        },
      },
      { title: t('app.kuaizhizao.scheduling.col.productName'), dataIndex: 'product_name', width: 120, ellipsis: true },
      { title: t('common.quantity'), dataIndex: 'quantity', width: 72, align: 'right' , render: formatQuantity },
      { title: t('app.kuaizhizao.scheduling.col.plannedStart'), dataIndex: 'planned_start_date', valueType: 'dateTime', width: 148 },
      { title: t('app.kuaizhizao.scheduling.col.plannedEnd'), dataIndex: 'planned_end_date', valueType: 'dateTime', width: 148 },
      {
        title: t('app.kuaizhizao.scheduling.col.overdue'),
        width: 72,
        align: 'center',
        render: (_: unknown, record) => {
          if (!record.planned_end_date) {
            return <Typography.Text type="secondary">{t('app.kuaizhizao.scheduling.common.dash')}</Typography.Text>;
          }
          const overdue = dayjs(record.planned_end_date).isBefore(dayjs());
          return overdue ? (
            <Tag color="error">{t('app.kuaizhizao.scheduling.col.overdueTag')}</Tag>
          ) : (
            <Typography.Text type="secondary">{t('app.kuaizhizao.scheduling.common.dash')}</Typography.Text>
          );
        },
      },
      {
        title: t('app.kuaizhizao.scheduling.col.schedulingIssues'),
        width: 180,
        ellipsis: true,
        render: (_: unknown, record) => {
          const issues = workOrderDiagnosticsById.get(record.id);
          if (!issues?.length) {
            return <Typography.Text type="secondary">{t('app.kuaizhizao.scheduling.common.dash')}</Typography.Text>;
          }
          const visible = issues.slice(0, 2);
          const rest = issues.length - visible.length;
          const tooltip = issues.map((item) => item.label).join('；');
          return (
            <Tooltip title={tooltip}>
              <span style={{ display: 'inline-block', maxWidth: '100%', verticalAlign: 'middle' }}>
                {renderInlineMarkerTagGroup(
                  [
                    ...visible.map((item) => ({
                      key: item.key,
                      label: item.label,
                      color: item.severity === 'error' ? ('error' as const) : ('warning' as const),
                    })),
                    ...(rest > 0
                      ? [{ key: 'more', label: `+${rest}`, color: 'default' as const }]
                      : []),
                  ],
                  { empty: null },
                )}
              </span>
            </Tooltip>
          );
        },
      },
      {
        title: t('app.kuaizhizao.scheduling.col.frozen'),
        dataIndex: 'is_frozen',
        width: 72,
        align: 'center',
        render: (_: unknown, record: { is_frozen?: boolean }) =>
          record.is_frozen ? (
            <Tag color="purple">{t('app.kuaizhizao.scheduling.col.frozenTag')}</Tag>
          ) : (
            <Typography.Text type="secondary">{t('app.kuaizhizao.scheduling.common.dash')}</Typography.Text>
          ),
      },
      {
        title: t('app.kuaizhizao.scheduling.col.priority'),
        dataIndex: 'priority',
        width: 80,
        align: 'center',
        render: (priority: any) => {
          const val = String(priority || '');
          const colorMap: Record<string, string> = { urgent: 'red', high: 'orange', normal: 'blue', low: 'default' };
          const textMap: Record<string, string> = {
            urgent: t('app.kuaizhizao.scheduling.priority.urgent'),
            high: t('app.kuaizhizao.scheduling.priority.high'),
            normal: t('app.kuaizhizao.scheduling.priority.normal'),
            low: t('app.kuaizhizao.scheduling.priority.low'),
          };
          return <Tag color={colorMap[val] || 'default'}>{textMap[val] || val}</Tag>;
        },
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 100,
        valueEnum: {
          draft: { text: t('app.kuaizhizao.scheduling.status.draft'), status: 'default' },
          released: { text: t('app.kuaizhizao.scheduling.status.released'), status: 'processing' },
          in_progress: { text: t('app.kuaizhizao.scheduling.status.inProgress'), status: 'processing' },
        },
      },
    ],
    [aiSuggestedPoolRankById, t, workOrderDiagnosticsById]
  );

  const discardDraftAndClose = useCallback(() => {
    draftWoUpdatesRef.current.clear();
    draftOpUpdatesRef.current.clear();
    draftStationUpdatesRef.current.clear();
    undoStackRef.current = [];
    syncDraftPendingCount();
    setDraftMode(false);
    refreshGantt();
  }, [refreshGantt, syncDraftPendingCount]);

  const schedulingActionCount = Math.min(selectedWorkOrderIds.length, 50);
  const schedulingOverdueCount = useMemo(
    () =>
      selectedWorkOrders.filter(
        (wo) => wo.planned_end_date && dayjs(wo.planned_end_date).isBefore(dayjs()),
      ).length,
    [selectedWorkOrders],
  );
  const poolQuickActionDescription = useMemo(
    () =>
      schedulingOverdueCount > 0
        ? t('app.kuaizhizao.scheduling.msg.quickActionConfirmOverdue', {
            count: schedulingActionCount,
            overdue: schedulingOverdueCount,
          })
        : t('app.kuaizhizao.scheduling.msg.quickActionConfirm', { count: schedulingActionCount }),
    [schedulingActionCount, schedulingOverdueCount, t],
  );
  const schedulingConfirmOkText = t('app.kuaizhizao.scheduling.common.confirm');

  const lockedOperationIds = useMemo(() => {
    const ids: number[] = [];
    ganttBoardWorkOrders.forEach((wo) => {
      if (!isWorkOrderSchedulingLocked(wo, schedulingConstraints.freeze_horizon_days || 0, freezeAnchor)) {
        return;
      }
      (wo.operations ?? []).forEach((op) => {
        if (op.id != null) ids.push(op.id);
      });
    });
    return ids;
  }, [freezeAnchor, ganttBoardWorkOrders, schedulingConstraints.freeze_horizon_days]);

  const poolToolbarNode = (
    <SchedulingPoolToolbar
      keyword={poolKeyword}
      statusFilter={poolStatusFilter}
      selectedCount={selectedWorkOrderIds.length}
      canUpdate={canScheduleUpdate}
      actionLoading={quickActionLoading}
      onKeywordChange={setPoolKeyword}
      onStatusFilterChange={setPoolStatusFilter}
      onSearch={handlePoolSearch}
      onReset={handlePoolReset}
      onConfirmDelay={handleConfirmDelay}
      onToException={handleToException}
      onApplyUnfreeze={handleApplyUnfreeze}
      onRescheduleForward={handleRescheduleForward}
      confirmDelayConfirm={{
        title: t('app.kuaizhizao.scheduling.msg.confirmDelayTitle'),
        description: poolQuickActionDescription,
        okText: schedulingConfirmOkText,
      }}
      toExceptionConfirm={{
        title: t('app.kuaizhizao.scheduling.msg.toExceptionTitle'),
        description: poolQuickActionDescription,
        okText: schedulingConfirmOkText,
      }}
      applyUnfreezeConfirm={{
        title: t('app.kuaizhizao.scheduling.msg.applyUnfreezeTitle'),
        description: poolQuickActionDescription,
        okText: schedulingConfirmOkText,
      }}
      rescheduleForwardConfirm={{
        title: t('app.kuaizhizao.scheduling.msg.rescheduleForwardTitle'),
        description: t('app.kuaizhizao.scheduling.msg.rescheduleForwardConfirm', {
          count: schedulingActionCount,
        }),
        okText: schedulingConfirmOkText,
      }}
      overdueOnly={poolOverdueOnly}
      onOverdueOnlyChange={setPoolOverdueOnly}
    />
  );

  const ganttToolbarNodes = buildSchedulingGanttToolbar({
    t,
    boardMainView,
    onBoardMainViewChange: setBoardMainView,
    ganttViewMode,
    ganttTaskLevel,
    resourceMode: schedulingConstraints.resource_mode,
    onGanttTaskLevelChange: setGanttTaskLevel,
    pinnedResourceCount: pinnedResourceIds.length,
    showPinnedOnly,
    onShowPinnedOnlyChange: setShowPinnedOnly,
    onOpenPinManager: () => setPinManagerOpen(true),
    equipmentTypeFilter,
    onEquipmentTypeFilterChange: setEquipmentTypeFilter,
    workerRoleFilter,
    onWorkerRoleFilterChange: setWorkerRoleFilter,
    schedulingWorkers,
    shiftDays,
    selectedWorkOrderCount: selectedWorkOrderIds.length,
    batchActionLoading,
    canUpdate: canScheduleUpdate,
    draftMode,
    draftPendingCount,
    onDraftModeChange: setDraftMode,
    draftCloseConfirm: {
      title: t('app.kuaizhizao.scheduling.draft.closeTitle'),
      description: t('app.kuaizhizao.scheduling.draft.closeContent', { count: draftPendingCount }),
      okText: t('app.kuaizhizao.scheduling.draft.discardAndClose'),
      onConfirm: discardDraftAndClose,
    },
    onApplyDraft: handleApplyDraft,
    onUndoDraft: handleUndoDraft,
    onRefresh: handleRefreshAll,
    onOpenConfig: () => setConfigDrawerOpen(true),
    onBatchFreeze: handleBatchFreeze,
    onBatchUnfreeze: handleBatchUnfreeze,
    onClearScheduling: handleClearScheduling,
    clearSchedulingConfirm: {
      title: t('app.kuaizhizao.scheduling.msg.clearSchedulingTitle'),
      description: t('app.kuaizhizao.scheduling.msg.clearSchedulingConfirm', {
        count: selectedWorkOrderIds.length,
      }),
      okText: t('app.kuaizhizao.scheduling.ganttToolbar.clearScheduling'),
    },
    onBatchShift: handleBatchShift,
    onShiftDaysChange: setShiftDays,
    onViewModeChange: (mode) => {
      setGanttViewMode(mode);
      setScrollToTodayToken((n) => n + 1);
    },
    onScrollToToday: () => setScrollToTodayToken((n) => n + 1),
    onAutoReschedule: handleAutoReschedule,
    onOpenDueEstimate: () => setDueEstimateOpen(true),
    onLocalReschedule: handleLocalReschedule,
    localRescheduleConfirm: {
      title: t('app.kuaizhizao.scheduling.msg.localRescheduleTitle'),
      description: t('app.kuaizhizao.scheduling.msg.localRescheduleConfirm', {
        count: schedulingActionCount,
      }),
      okText: schedulingConfirmOkText,
    },
    onEditOperation: () => {
      if (!operationEditContext) return;
      setOperationEditOpen(true);
    },
    autoRescheduleLoading,
    canEditOperation: operationEditContext != null,
  });

  return (
    <ListPageTemplate>
      <Tour
        open={fullscreenTourOpen}
        onClose={() => {
          setFullscreenTourOpen(false);
          try {
            sessionStorage.setItem(SCHEDULING_FULLSCREEN_TIP_SESSION_KEY, '1');
          } catch {
            // ignore
          }
        }}
        placement="left"
        steps={[
          {
            title: t('app.kuaizhizao.scheduling.tour.fullscreenTitle'),
            description: t('app.kuaizhizao.scheduling.tour.fullscreenDescription'),
            target: () => document.querySelector('.uni-tabs-fullscreen-button') as HTMLElement,
          },
        ]}
      />
      <SchedulingHeaderBand
        constraints={schedulingConstraints}
        resourceMode={schedulingConstraints.resource_mode}
        selectedWorkOrderCount={selectedWorkOrderIds.length}
        selectedOperationCount={selectedOperationCount}
        ganttTaskLevel={ganttTaskLevel}
        resourceViewStats={resourceViewStats}
        legendMetrics={topLegendMetrics}
        planReliabilityLoading={planReliabilityLoading}
        planReliability={planReliability}
        missingSettingsCount={
          boardScan?.missing_settings_count ?? boardScan?.missing_settings?.length ?? 0
        }
        missingSettingsActionDisabled={!canScheduleUpdate}
        onMissingSettingsClick={() => openMissingSettingsModal(boardScan?.missing_settings ?? [])}
        extra={<SchedulingAiAssistantTrigger onOpen={() => setAiDrawerOpen(true)} />}
      />
      {schedulingConstraints.resource_mode === 'production_line' && lineCapacitiesError ? (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          title={
            <span>
              {String((lineCapacitiesError as { message?: string })?.message || '') ===
              'LINE_PRODUCT_IDS_MISSING'
                ? t('app.kuaizhizao.scheduling.msg.lineProductIdsMissing')
                : t('app.kuaizhizao.scheduling.msg.lineCapacityLoadFailed')}{' '}
              <Link to="/apps/ind-relay/line-capacity">
                {t('app.kuaizhizao.scheduling.prep.gotoLineCapacity')}
              </Link>
            </span>
          }
        />
      ) : null}
      {filterWorkOrderIds?.length ? (
        <Alert
          type="info"
          showIcon
          closable
          style={{ marginBottom: 12 }}
          title={t('app.kuaizhizao.scheduling.alert.fromCoordinationCenter', { count: filterWorkOrderIds.length })}
          action={
            <Button size="small" onClick={() => navigate('/apps/kuaizhizao/plan-management/dashboard')}>
              {t('app.kuaizhizao.scheduling.alert.returnCoordinationCenter')}
            </Button>
          }
        />
      ) : null}
      {filterPlanDate ? (
        <Alert
          type="info"
          showIcon
          closable
          style={{ marginBottom: 12 }}
          title={t('app.kuaizhizao.scheduling.alert.filterByPlanDate', { date: filterPlanDate })}
          action={
            <Button
              size="small"
              onClick={() => navigate(`/apps/kuaizhizao/plan-management/rolling-scheduling?plan_date=${filterPlanDate}`)}
            >
              {t('app.kuaizhizao.scheduling.alert.returnRollingPlan')}
            </Button>
          }
        />
      ) : null}
      {ganttWorkOrders.length >= GANTT_WORK_ORDER_LIMIT && !filterWorkOrderIds?.length ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('app.kuaizhizao.scheduling.alert.ganttLimitWarning', { limit: GANTT_WORK_ORDER_LIMIT })}
        />
      ) : null}
      <div className="aps-main-layout">
        <div className="aps-block aps-block-gantt">
          <Card className="aps-gantt-card-compact scheduling-gantt-card" style={{ marginTop: 8 }} title={ganttToolbarNodes.toolbar}>
            <SchedulingBoardDropZone canUpdate={canScheduleUpdate} onDropWorkOrder={handleDropWorkOrderToBoard}>
              {boardMainView === 'loadTable' ? (
                <SchedulingLoadTable
                  t={t}
                  boardScan={boardScan}
                  taskLevel={ganttTaskLevel}
                  horizonDays={schedulingConstraints.rolling_horizon_days || 14}
                  workOrders={ganttBoardDisplayWorkOrders}
                  pinnedResourceIds={pinnedResourceIds}
                  showPinnedOnly={showPinnedOnly}
                  loading={ganttLoading}
                  productionLineOptions={
                    schedulingConstraints.resource_mode === 'production_line'
                      ? {
                          lines: workstationResources,
                          taktSecondsByLineId,
                          dailyCapacityByLineId,
                          horizonDays: schedulingConstraints.rolling_horizon_days || 14,
                          workOrders: ganttBoardDisplayWorkOrders,
                        }
                      : null
                  }
                />
              ) : boardMainView === 'alerts' ? (
                <SchedulingAlertsPanel
                  boardScan={boardScan}
                  onOpenWorkOrder={(workOrderId) => {
                    setSelectedRowKeys([workOrderId]);
                    setBoardMainView('gantt');
                  }}
                />
              ) : boardMainView === 'cardView' ? (
                <SchedulingCardBoard
                  t={t}
                  loading={ganttLoading}
                  workOrders={ganttBoardDisplayWorkOrders}
                  taskLevel={ganttTaskLevel}
                  stations={visibleWorkstationResources}
                  equipments={visibleSchedulingEquipments}
                  workers={visibleSchedulingWorkers}
                  boardScan={boardScan}
                  horizonDays={schedulingConstraints.rolling_horizon_days || 14}
                  materialIssueWorkOrderIds={materialIssueWorkOrderIds}
                  selectedWorkOrderIds={selectedWorkOrderIds}
                  canUpdate={canScheduleUpdate}
                  onSelectWorkOrder={handleCardBoardSelectWorkOrder}
                  onOperationUpdate={canScheduleUpdate ? handleCardBoardOperationUpdate : undefined}
                  onOperationResourceMove={canScheduleUpdate ? handleCardBoardResourceMove : undefined}
                />
              ) : (
              <Suspense
                fallback={
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 48, gap: 16 }}>
                    <Spin size="large" />
                    <div style={{ color: 'var(--ant-color-primary)' }}>{t('app.kuaizhizao.scheduling.pool.loadingGantt')}</div>
                  </div>
                }
              >
                <GanttSchedulingChart
                  workOrders={ganttBoardDisplayWorkOrders}
                  workstations={visibleWorkstationResources}
                  equipments={visibleSchedulingEquipments}
                  workers={visibleSchedulingWorkers}
                  loading={ganttLoading}
                  viewMode={ganttViewMode}
                  taskLevel={ganttTaskLevel}
                  resourceMode={schedulingConstraints.resource_mode}
                  equipmentTypeFilter={equipmentTypeFilter}
                  workerRoleFilter={workerRoleFilter}
                  freezeHorizonDays={schedulingConstraints.freeze_horizon_days}
                  focusTaskId={focusTaskId}
                  onFocusTaskConsumed={handleFocusTaskConsumed}
                  scrollToTodayToken={scrollToTodayToken}
                  onViewModeChange={(mode) => {
                    setGanttViewMode(mode);
                    setScrollToTodayToken((n) => n + 1);
                  }}
                  onBatchUpdate={canScheduleUpdate ? handleGanttBatchUpdate : undefined}
                  onBatchUpdateOperations={canScheduleUpdate ? handleGanttBatchUpdateOperations : undefined}
                  onBatchUpdateOperationStations={
                    canScheduleUpdate ? handleBatchUpdateOperationStations : undefined
                  }
                  onBatchUpdateOperationAssignments={
                    canScheduleUpdate ? handleBatchUpdateOperationAssignments : undefined
                  }
                  onWorkOrderSelect={handleGanttWorkOrderSelect}
                  onOperationSelect={handleGanttOperationSelect}
                  onOperationDoubleClick={handleGanttOperationDoubleClick}
                  onRefresh={refreshGantt}
                  canUpdate={canScheduleUpdate}
                  nonDraggableTaskIds={nonDraggableTaskIds}
                  onBlockedDragAttempt={(taskId) => {
                    const text = String(taskId);
                    if (text === lastBlockedTaskId) return;
                    setLastBlockedTaskId(text);
                    messageApi.warning(t('app.kuaizhizao.scheduling.msg.freezeDragBlocked'));
                  }}
                />
              </Suspense>
              )}
            </SchedulingBoardDropZone>
            <div className="scheduling-pending-pool aps-pool-card-compact">
              <div className="scheduling-pending-pool__main">
                <span className="scheduling-pending-pool__title-wrap">
                  <Typography.Text strong className="scheduling-pending-pool__title">
                    {t('app.kuaizhizao.scheduling.pool.title')}
                  </Typography.Text>
                  <span
                    className="scheduling-pending-pool__count"
                    aria-label={t('app.kuaizhizao.scheduling.pool.countAriaLabel', { count: poolWorkOrders.length })}
                  >
                    {poolWorkOrders.length}
                  </span>
                </span>
                {canScheduleUpdate ? (
                  <>
                    <Typography.Text type="secondary" className="scheduling-pending-pool__hint">
                      {t('app.kuaizhizao.scheduling.pool.hint')}
                    </Typography.Text>
                    <span className="scheduling-pending-pool__sep" aria-hidden>
                      -
                    </span>
                  </>
                ) : null}
              </div>
              <div className="scheduling-pending-pool__view-toggle">
                <ThemedSegmented
                  size="small"
                  surfaceBackground
                  value={poolViewMode}
                  options={[
                    { label: t('app.kuaizhizao.scheduling.poolView.table'), value: 'table' },
                    { label: t('app.kuaizhizao.scheduling.poolView.card'), value: 'card' },
                  ]}
                  onChange={(value) => setPoolViewMode(value as 'table' | 'card')}
                />
              </div>
              {poolViewMode === 'card' ? (
                <>
                  <div className="scheduling-pending-pool__card-toolbar">{poolToolbarNode}</div>
                  <SchedulingPoolCardGrid
                    t={t}
                    items={poolCardItems}
                    selectedRowKeys={selectedRowKeys}
                    canUpdate={canScheduleUpdate}
                    onSelectionChange={(keys) => {
                      setSelectedRowKeys(keys);
                      setFocusTaskId(null);
                    }}
                  />
                </>
              ) : (
              <ConfigProvider theme={SCHEDULING_POOL_TABLE_THEME}>
                <UniTable
                  columnPersistenceId="apps.kuaizhizao.pages.plan-management.scheduling.pool"
                  embedded
                  bordered
                  actionRef={actionRef}
                  rowKey="id"
                  columns={
                    alignProColumns(
                      columns as unknown as ProColumns<Record<string, unknown>>[],
                      SALES_DOC_LIST_FIELD_RANK
                    ) as unknown as ProColumns<WorkOrderForGantt>[]
                  }
                  showFuzzySearch={false}
                  showAdvancedSearch={false}
                  viewTypes={['table']}
                  pagination={{ size: 'small' }}
                  headerActions={poolToolbarNode}
                  request={async (params: any) => {
                    const list = poolWorkOrdersRef.current;
                    const pageSize = params.pageSize ?? 20;
                    const skip = ((params.current ?? 1) - 1) * pageSize;
                    return {
                      data: list.slice(skip, skip + pageSize),
                      success: true,
                      total: list.length,
                    };
                  }}
                  rowSelection={{
                    selectedRowKeys,
                    onChange: (keys) => {
                      setSelectedRowKeys(keys);
                      setFocusTaskId(null);
                    },
                  }}
                  onRow={(record) => ({
                    draggable: canScheduleUpdate,
                    onDragStart: (e) => {
                      if (!canScheduleUpdate) return;
                      e.dataTransfer.setData(SCHEDULING_DRAG_WORK_ORDER, String(record.id));
                      e.dataTransfer.effectAllowed = 'move';
                    },
                  })}
                  rowClassName={(record) => {
                    const classes: string[] = [];
                    if (canScheduleUpdate) classes.push('scheduling-pool-row--draggable');
                    if (workOrderDiagnosticsById.has(record.id)) {
                      classes.push('scheduling-pool-row--has-issues');
                    }
                    if (aiSuggestedPoolRankById.has(record.id)) {
                      classes.push('scheduling-pool-row--ai-suggested');
                    }
                    const rate = record.readiness_rate;
                    if (rate != null && Number(rate) < 100 && schedulingConstraints.consider_material) {
                      classes.push('scheduling-row-material-risk');
                    }
                    return classes.join(' ');
                  }}
                />
              </ConfigProvider>
              )}
            </div>
          </Card>
        </div>
      </div>

      <SchedulingWorkOrderPrepModal
        open={prepModalOpen}
        workOrder={prepModalWorkOrder}
        missingFields={prepModalMissing}
        operationsNeedingStation={prepModalOperationsNeedingStation}
        workstations={workstationResources}
        workCenters={schedulingWorkCenters}
        workers={schedulingWorkers}
        equipments={schedulingEquipments}
        molds={schedulingMolds}
        resourceMode={schedulingConstraints.resource_mode}
        linesMissingTakt={linesMissingTakt}
        eligibleProductionLineIds={
          schedulingConstraints.resource_mode === 'production_line'
            ? eligibleConfiguredLineIdsForProduct(Number(prepModalWorkOrder?.product_id || 0))
            : undefined
        }
        taktSecondsByLineId={taktSecondsByLineId}
        loading={prepModalSaving || prepModalLoading}
        onCancel={() => {
          setPrepModalOpen(false);
          setPrepModalWorkOrder(null);
          setPrepModalMissing([]);
          setPrepModalOperationsNeedingStation([]);
        }}
        onSubmit={handlePrepModalSubmit}
      />

      <Modal
        open={missingSettingsModalOpen}
        destroyOnHidden
        title={t('app.kuaizhizao.scheduling.msg.missingSettingsTitle')}
        width={960}
        onCancel={() => {
          setMissingSettingsModalOpen(false);
          setMissingSettingsProductByWo(new Map());
          setPendingAutoRescheduleIds(null);
        }}
        footer={[
          <Button
            key="cancel"
            onClick={() => {
              setMissingSettingsModalOpen(false);
              setMissingSettingsProductByWo(new Map());
              setPendingAutoRescheduleIds(null);
            }}
          >
            {t('common.cancel')}
          </Button>,
          <Button
            key="save"
            type="primary"
            loading={missingSettingsSaving}
            disabled={!canScheduleUpdate}
            onClick={() => void handleMissingSettingsBackfill()}
          >
            {pendingAutoRescheduleIds?.length
              ? t('app.kuaizhizao.scheduling.msg.missingBackfillAndReschedule')
              : t('app.kuaizhizao.scheduling.msg.missingBackfill')}
          </Button>,
        ]}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          title={t(
            schedulingConstraints.resource_mode === 'production_line'
              ? 'app.kuaizhizao.scheduling.msg.missingSettingsHintLine'
              : 'app.kuaizhizao.scheduling.msg.missingSettingsHint'
          )}
        />
        {schedulingConstraints.resource_mode === 'production_line' &&
        (missingSettingsRows.some((row) => row.needCapacity) ||
          (missingSettingsRows.some((row) => row.needStation) &&
            workstationResources.filter((s) => !linesMissingTakt.includes(s.id)).length === 0)) ? (
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 12 }}
            title={
              <span>
                {t('app.kuaizhizao.scheduling.prep.missingTaktCapacity')}{' '}
                <Link to="/apps/ind-relay/line-capacity">
                  {t('app.kuaizhizao.scheduling.prep.gotoLineCapacity')}
                </Link>
              </span>
            }
          />
        ) : null}
        <Table
          size="small"
          rowKey="operation_id"
          pagination={{ pageSize: 8, hideOnSinglePage: true }}
          dataSource={missingSettingsRows}
          columns={
            schedulingConstraints.resource_mode === 'production_line'
              ? [
                  {
                    title: t('app.kuaizhizao.scheduling.table.workOrderCode'),
                    dataIndex: 'work_order_code',
                    width: 140,
                  },
                  {
                    title: t('app.kuaizhizao.scheduling.table.operation'),
                    dataIndex: 'operation_name',
                    ellipsis: true,
                  },
                  {
                    title: t('app.kuaizhizao.scheduling.gantt.col.productionLine'),
                    width: 240,
                    render: (_, row) => {
                      if (row.needCapacity && !row.needStation) {
                        return t('app.kuaizhizao.scheduling.msg.missingCapacityGoConfig');
                      }
                      if (!row.needStation) return '—';
                      // 产线模式：候选 = 已配节拍 ∩ 绑定含本工单自制件
                      const productId =
                        productIdByWorkOrderId.get(row.work_order_id) ||
                        missingSettingsProductByWo.get(row.work_order_id) ||
                        0;
                      const eligibleIds = new Set(eligibleConfiguredLineIdsForProduct(productId));
                      const candidates = workstationResources.filter((s) => eligibleIds.has(s.id));
                      return (
                        <Select
                          style={{ width: '100%' }}
                          allowClear
                          placeholder={
                            candidates.length === 0
                              ? t('app.kuaizhizao.scheduling.msg.lineProductNoEligible')
                              : undefined
                          }
                          options={candidates.map((s) => ({
                            value: s.id,
                            label: s.code ? `${s.code} ${s.name}` : s.name,
                          }))}
                          value={row.assigned_station_id ?? undefined}
                          onChange={(v) => {
                            const nextId = v == null ? null : Number(v);
                            setMissingSettingsRows((prev) =>
                              prev.map((r) => {
                                // 产线模式整单共用产线：改一行同步同工单需补齐的其它工序
                                if (r.work_order_id === row.work_order_id && r.needStation) {
                                  return { ...r, assigned_station_id: nextId };
                                }
                                return r;
                              })
                            );
                          }}
                        />
                      );
                    },
                  },
                ]
              : [
                  {
                    title: t('app.kuaizhizao.scheduling.table.workOrderCode'),
                    dataIndex: 'work_order_code',
                    width: 140,
                  },
                  {
                    title: t('app.kuaizhizao.scheduling.table.operation'),
                    dataIndex: 'operation_name',
                    ellipsis: true,
                  },
                  {
                    title: t('app.kuaizhizao.scheduling.msg.setupHours'),
                    width: 120,
                    render: (_, row) =>
                      row.needHours ? (
                        <InputNumber
                          min={0}
                          step={0.01}
                          precision={2}
                          style={{ width: '100%' }}
                          value={row.setup_time}
                          onChange={(v) =>
                            setMissingSettingsRows((prev) =>
                              prev.map((r) =>
                                r.operation_id === row.operation_id
                                  ? { ...r, setup_time: v == null ? null : Number(v) }
                                  : r
                              )
                            )
                          }
                        />
                      ) : (
                        '—'
                      ),
                  },
                  {
                    title: t('app.kuaizhizao.scheduling.msg.standardHours'),
                    width: 120,
                    render: (_, row) =>
                      row.needHours ? (
                        <InputNumber
                          min={0}
                          step={0.01}
                          precision={2}
                          style={{ width: '100%' }}
                          value={row.standard_time}
                          onChange={(v) =>
                            setMissingSettingsRows((prev) =>
                              prev.map((r) =>
                                r.operation_id === row.operation_id
                                  ? { ...r, standard_time: v == null ? null : Number(v) }
                                  : r
                              )
                            )
                          }
                        />
                      ) : (
                        '—'
                      ),
                  },
                  {
                    title: t('app.kuaizhizao.scheduling.msg.station'),
                    width: 200,
                    render: (_, row) => {
                      if (!row.needStation) return '—';
                      const wcId =
                        row.work_center_id != null && Number(row.work_center_id) > 0
                          ? Number(row.work_center_id)
                          : null;
                      let candidates = workstationResources;
                      if (wcId != null) {
                        const wc = schedulingWorkCenters.find((item) => item.id === wcId);
                        const allowed = new Set(
                          (wc?.workstationIds ?? []).filter((id) => id > 0)
                        );
                        if (allowed.size > 0) {
                          candidates = workstationResources.filter((s) => allowed.has(s.id));
                        }
                      }
                      return (
                        <Select
                          style={{ width: '100%' }}
                          allowClear
                          options={candidates.map((s) => ({
                            value: s.id,
                            label: s.code ? `${s.code} ${s.name}` : s.name,
                          }))}
                          value={row.assigned_station_id ?? undefined}
                          onChange={(v) =>
                            setMissingSettingsRows((prev) =>
                              prev.map((r) =>
                                r.operation_id === row.operation_id
                                  ? { ...r, assigned_station_id: v == null ? null : Number(v) }
                                  : r
                              )
                            )
                          }
                        />
                      );
                    },
                  },
                ]
          }
        />
      </Modal>

      <SchedulingOperationEditDrawer
        open={operationEditOpen}
        context={operationEditContext}
        workstations={workstationResources}
        workers={schedulingWorkers}
        equipments={schedulingEquipments}
        molds={schedulingMolds}
        resourceMode={schedulingConstraints.resource_mode}
        canUpdate={canScheduleUpdate}
        onClose={() => setOperationEditOpen(false)}
        onSaved={() => {
          refreshGantt();
          refreshBoardScan();
    actionRef.current?.reload();
        }}
      />

      <Modal
        title={t('app.kuaizhizao.scheduling.config.title')}
        width={560}
        open={configDrawerOpen}
        onCancel={() => setConfigDrawerOpen(false)}
        footer={
          <Space>
            <Button
              onClick={() => {
                setSchedulingConstraints(DEFAULT_SCHEDULING_CONSTRAINTS);
              }}
            >
              {t('app.kuaizhizao.scheduling.config.restoreDefault')}
            </Button>
            <Button
              type="primary"
              loading={configSaving}
              disabled={!canScheduleUpdate}
              onClick={async () => {
                try {
                  setConfigSaving(true);
                  await schedulingConfigApi.upsertDefault(pickVisualSchedulingConstraints(schedulingConstraints));
                  messageApi.success(t('app.kuaizhizao.scheduling.msg.configSaved'));
                  setConfigDrawerOpen(false);
                  refreshBoardScan();
                } catch (e: any) {
                  messageApi.error(e?.message || t('common.saveFailed'));
                } finally {
                  setConfigSaving(false);
                }
              }}
            >
              {t('common.confirm')}
            </Button>
          </Space>
        }
      >
        <div style={{ padding: '12px 0' }}>
          <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{t('app.kuaizhizao.scheduling.config.freezeWindowDays')}</span>
              <InputNumber
                size="small"
                min={0}
                max={30}
                value={schedulingConstraints.freeze_horizon_days}
                onChange={(v) =>
                  setSchedulingConstraints((c) => ({ ...c, freeze_horizon_days: Number(v ?? 2) }))
                }
              />
            </div>
            <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: -8 }}>
              {t('app.kuaizhizao.scheduling.config.freezeWindowHint')}
            </Typography.Text>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{t('app.kuaizhizao.scheduling.config.scanHorizonDays')}</span>
              <InputNumber
                size="small"
                min={1}
                max={120}
                value={schedulingConstraints.rolling_horizon_days}
                onChange={(v) =>
                  setSchedulingConstraints((c) => ({ ...c, rolling_horizon_days: Number(v || 14) }))
                }
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{t('app.kuaizhizao.scheduling.config.changeoverHours')}</span>
              <InputNumber
                size="small"
                min={0}
                max={12}
                step={0.5}
                precision={2}
                value={schedulingConstraints.setup_changeover_hours}
                onChange={(v) =>
                  setSchedulingConstraints((c) => ({
                    ...c,
                    setup_changeover_hours: Number(v ?? 0),
                  }))
                }
              />
            </div>
            <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: -8 }}>
              {t('app.kuaizhizao.scheduling.config.changeoverHoursHint')}
            </Typography.Text>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{t('app.kuaizhizao.scheduling.config.scheduleMode')}</span>
              <Select
                size="small"
                style={{ width: 140 }}
                value={schedulingConstraints.schedule_mode || 'forward'}
                options={[
                  { value: 'forward', label: t('app.kuaizhizao.scheduling.config.scheduleModeForward') },
                  { value: 'backward', label: t('app.kuaizhizao.scheduling.config.scheduleModeBackward') },
                ]}
                onChange={(v) =>
                  setSchedulingConstraints((c) => ({
                    ...c,
                    schedule_mode: v === 'backward' ? 'backward' : 'forward',
                  }))
                }
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{t('app.kuaizhizao.scheduling.config.resourceMode')}</span>
              <Select
                size="small"
                style={{ width: 140 }}
                value={schedulingConstraints.resource_mode || 'workstation'}
                options={[
                  {
                    value: 'workstation',
                    label: t('app.kuaizhizao.scheduling.config.resourceModeWorkstation'),
                  },
                  {
                    value: 'production_line',
                    label: t('app.kuaizhizao.scheduling.config.resourceModeProductionLine'),
                  },
                ]}
                onChange={(v) =>
                  setSchedulingConstraints((c) => ({
                    ...c,
                    resource_mode: v === 'production_line' ? 'production_line' : 'workstation',
                  }))
                }
              />
            </div>
            {schedulingConstraints.resource_mode === 'production_line' && (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>{t('app.kuaizhizao.scheduling.config.lineExclusive')}</span>
                <Switch
                  checked={schedulingConstraints.line_exclusive !== false}
                  onChange={(v) =>
                    setSchedulingConstraints((c) => ({ ...c, line_exclusive: v }))
                  }
                />
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{t('app.kuaizhizao.scheduling.config.materialHardConstraint')}</span>
              <Switch
                checked={Boolean(schedulingConstraints.material_hard_constraint)}
                onChange={(v) =>
                  setSchedulingConstraints((c) => ({ ...c, material_hard_constraint: v }))
                }
              />
            </div>
            <Divider style={{ margin: '4px 0' }} />
            <div style={{ fontWeight: 500 }}>{t('app.kuaizhizao.scheduling.config.workHoursTitle')}</div>
            <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: -8 }}>
              {t('app.kuaizhizao.scheduling.config.workHoursHint')}
            </Typography.Text>
            <Button
              type="link"
              size="small"
              style={{ padding: 0, alignSelf: 'flex-start' }}
              onClick={() => {
                setConfigDrawerOpen(false);
                navigate(ROUTES.PERF_WORK_CALENDAR);
              }}
            >
              {t('app.kuaizhizao.scheduling.config.workHoursLink')}
            </Button>
            <Divider style={{ margin: '4px 0' }} />
            <div style={{ fontWeight: 500 }}>{t('app.kuaizhizao.scheduling.config.dragValidationTitle')}</div>
            {(['consider_human', 'consider_equipment', 'consider_material', 'consider_mold_tool'] as const).map((key) => (
              <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>
                  {key === 'consider_human' && t('app.kuaizhizao.scheduling.config.considerHuman')}
                  {key === 'consider_equipment' && t('app.kuaizhizao.scheduling.config.considerEquipment')}
                  {key === 'consider_material' && t('app.kuaizhizao.scheduling.config.considerMaterial')}
                  {key === 'consider_mold_tool' && t('app.kuaizhizao.scheduling.config.considerMoldTool')}
                </span>
                <Switch
                  checked={schedulingConstraints[key]}
                  onChange={(v) => setSchedulingConstraints((c) => ({ ...c, [key]: v }))}
                />
              </div>
            ))}
          </Space>
        </div>
      </Modal>

      <SchedulingRescheduleWizardModal
        open={rescheduleWizardOpen}
        workOrderIds={rescheduleWizardIds}
        planDate={filterPlanDate}
        scope="selected"
        onCancel={() => setRescheduleWizardOpen(false)}
        onApply={async (proposal) => {
          setAutoRescheduleLoading(true);
          try {
            return await applyEngineProposalPayloadToDraft(proposal);
          } finally {
            setAutoRescheduleLoading(false);
          }
        }}
      />

      <SchedulingDueEstimateDrawer
        open={dueEstimateOpen}
        workOrderIds={selectedWorkOrderIds.slice(0, 100)}
        onClose={() => setDueEstimateOpen(false)}
      />

      <SchedulingPinManagerModal
        open={pinManagerOpen}
        t={t}
        taskLevel={ganttTaskLevel}
        pinned={pinnedResources}
        stationOptions={workstationResources.map((station) => ({
          value: station.id,
          label: station.name,
        }))}
        equipmentOptions={schedulingEquipments.map((equipment) => ({
          value: equipment.id,
          label: equipment.name,
        }))}
        workerOptions={schedulingWorkers}
        onClose={() => setPinManagerOpen(false)}
        onChange={handlePinnedResourcesChange}
      />

      <SchedulingAiAssistantDrawer
        open={aiDrawerOpen}
        onClose={() => setAiDrawerOpen(false)}
        canUpdate={canScheduleUpdate}
        resourceMode={schedulingConstraints.resource_mode}
        context={{
          poolWorkOrderIds,
          selectedWorkOrderIds,
          planDate: filterPlanDate,
          boardScan,
          workOrders: ganttWorkOrders,
        }}
        draftWoUpdatesRef={draftWoUpdatesRef}
        draftOpUpdatesRef={draftOpUpdatesRef}
        draftStationUpdatesRef={draftStationUpdatesRef}
        mutateGanttWorkOrders={mutateGanttWorkOrders}
        pushUndoSnapshot={pushUndoSnapshot}
        syncDraftPendingCount={syncDraftPendingCount}
        setDraftMode={setDraftMode}
        onPoolReorder={handleAiPoolReorder}
        onSelectSuggested={handleAiSelectSuggested}
        onSelectOverdue={handleAiSelectOverdue}
      />
    </ListPageTemplate>
  );
};

export default SchedulingPage;
