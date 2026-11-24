import React, { useMemo, useState, useCallback } from 'react';
import { App, Button, Space } from 'antd';
import { AuditOutlined, RollbackOutlined, SendOutlined } from '@ant-design/icons';
import { apiRequest } from '../../services/api';
import { prepareRowActionButton, rowActionKind, type RowActionPermissionKind } from '../uni-action';
import { rowActionLabel } from '../uni-action/actionCatalog';
import { useAuditRequired } from '../../hooks/useAuditRequired';
import { isManualAuditEnabled, resolveAuditActionVisibility } from '../../utils/auditMode';
import {
  readAuditViewerActions,
  resolveAuditFlowExecutePermission,
} from '../../utils/auditFlowViewerGate';
import { useGlobalStore } from '../../stores';
import { hasModulePermission, hasReviewPermission } from '../../utils/permissionContract';
import { isAdminBypass, resolveUserForMenuPermission } from '../../utils/permission';
import { useAdminRevokeAllDocuments } from '../../hooks/useAdminRevokeAllDocuments';
import UniAuditModal, { type UniAuditHubAction } from './UniAuditModal';
import UniAuditInitiatorSubmitModal from './UniAuditInitiatorSubmitModal';
import { resolveRecordDocumentCode } from './resolveRecordDocumentCode';
import {
  fetchSubmitInitiatorRequirements,
  type HierarchyDepartmentOption,
  type SubmitInitiatorBranchHint,
  type SubmitInitiatorNodeHint,
} from '../../services/uniAudit';
import { getApprovalStatus } from '../../services/approvalInstance';
import type { UniAuditAction, UniAuditActionsMap, UniAuditEndpointMap, WorkflowStatus } from './types';
import { useCurrentUser } from '../../hooks/useCurrentUser';

const DEFAULT_ENDPOINTS: Partial<Record<UniAuditAction, string>> = {
  submit: 'submit',
  submit_review: 'submit_review',
  withdraw: 'withdraw',
  approve: 'approve',
  reject: 'reject',
  revoke: 'unapprove',
  recall_own: 'recall_own',
};

export interface UniAuditActionsProps {
  record: any;
  rowKey?: string;
  apiPrefix?: string;
  actions?: UniAuditActionsMap;
  endpointMap?: UniAuditEndpointMap;
  entityName?: string;
  entityType?: string;
  statusField?: string;
  reviewStatusField?: string;
  draftStatuses?: string[];
  pendingStatuses?: string[];
  approvedStatuses?: string[];
  rejectedStatuses?: string[];
  /** @deprecated 由 record.audit.mode 决定，无需传入 */
  autoApproveWhenSubmit?: boolean;
  /** @deprecated 由 record.audit.enabled/mode 决定，无需传入 */
  workflowAuditEnabled?: boolean;
  auditNodeKey?: string;
  submitActionLabel?: string;
  onSuccess?: () => void;
  theme?: 'default' | 'link';
  size?: 'small' | 'medium' | 'large';
  confirmMessages?: Partial<Record<UniAuditAction, string>>;
  resourcePrefix?: string;
  unifiedAudit?: boolean;
  /** 返回错误文案则中断；用于业务单据提交前同口径预检 */
  beforeAction?: (
    action: UniAuditAction,
    record: any,
  ) => string | null | undefined | Promise<string | null | undefined>;
}

function inferAuditNodeKey(apiPrefix?: string): string {
  const prefix = (apiPrefix ?? '').toLowerCase();
  if (prefix.includes('/sales/contracts')) return 'sales_contract';
  if (prefix.includes('/sales/orders')) return 'sales_order';
  if (prefix.includes('/sales/forecasts') || prefix.includes('/sales-forecasts')) return 'sales_forecast';
  if (prefix.includes('/purchase/orders')) return 'purchase_order';
  if (prefix.includes('/purchase/requisitions')) return 'purchase_request';
  if (prefix.includes('/purchase/inquiries')) return 'purchase_inquiry';
  if (prefix.includes('/purchase/order-changes')) return 'purchase_order_change';
  if (prefix.includes('/sales/order-changes')) return 'sales_order_change';
  if (prefix.includes('/quality/oqc-inspection')) return 'oqc_inspection';
  if (prefix.includes('/quality/incoming-inspection')) return 'incoming_inspection';
  if (prefix.includes('/quality/process-inspection')) return 'process_inspection';
  if (prefix.includes('/quality/finished-goods-inspection')) return 'finished_goods_inspection';
  if (prefix.includes('/productions/reporting') || prefix.includes('/reporting')) return 'reporting_record';
  if (prefix.includes('/rework-orders') || prefix.includes('/rework')) return 'rework_order';
  if (prefix.includes('/demands')) return 'demand';

  if (prefix.includes('/quotation')) return 'quotation';
  if (prefix.includes('/shipment-notices')) return 'shipment_notice';
  if (prefix.includes('/payment-applications')) return 'payment_application';
  return '';
}

function inferResourcePrefix(apiPrefix?: string): string {
  const prefix = (apiPrefix ?? '').toLowerCase();
  if (!prefix) return '';
  if (prefix.includes('/apps/kuaizhizao/sales/contracts')) return 'kuaizhizao:sales-contract';
  if (prefix.includes('/apps/kuaizhizao/sales/orders')) return 'kuaizhizao:sales-order';
  if (
    prefix.includes('/apps/kuaizhizao/sales/forecasts')
    || prefix.includes('/apps/kuaizhizao/sales-forecasts')
  ) {
    return 'kuaizhizao:sales-forecast';
  }
  if (prefix.includes('/apps/kuaizhizao/sales/order-changes')) return 'kuaizhizao:sales-order-change';
  if (prefix.includes('/apps/kuaizhizao/purchase/orders')) return 'kuaizhizao:purchase-order';
  if (prefix.includes('/apps/kuaizhizao/purchase/requisitions')) return 'kuaizhizao:purchase-requisition';
  if (prefix.includes('/apps/kuaizhizao/purchase/inquiries')) return 'kuaizhizao:purchase-inquiry';
  if (prefix.includes('/apps/kuaizhizao/purchase/order-changes')) return 'kuaizhizao:purchase-order-change';
  if (prefix.includes('/apps/kuaizhizao/plan/demands')) return 'kuaizhizao:demand';
  if (prefix.includes('/apps/kuaizhizao/productions/reporting')) return 'kuaizhizao:reporting-record';
  if (prefix.includes('/apps/kuaizhizao/quality/oqc-inspection')) return 'kuaizhizao:oqc-inspection';
  if (prefix.includes('/apps/kuaizhizao/quality/incoming-inspection')) return 'kuaizhizao:incoming-inspection';
  if (prefix.includes('/apps/kuaizhizao/quality/process-inspection')) return 'kuaizhizao:process-inspection';
  if (prefix.includes('/apps/kuaizhizao/quality/finished-goods-inspection')) return 'kuaizhizao:finished-goods-inspection';
  if (prefix.includes('/apps/kuaizhizao/shipment-notices')) return 'kuaizhizao:shipment-notice';
  if (prefix.includes('/apps/kuaicaiwu/receivables')) return 'kuaicaiwu:receivable';
  if (prefix.includes('/apps/kuaicaiwu/payables')) return 'kuaicaiwu:payable';
  if (prefix.includes('/apps/kuaicaiwu/purchase-invoices')) return 'kuaicaiwu:purchase-invoice';
  if (prefix.includes('/apps/kuaicaiwu/finance/receivables')) return 'kuaicaiwu:receivable';
  if (prefix.includes('/apps/kuaicaiwu/finance/payables')) return 'kuaicaiwu:payable';
  if (prefix.includes('/apps/kuaicaiwu/finance/purchase-invoices')) return 'kuaicaiwu:purchase-invoice';
  if (prefix.includes('/apps/kuaizhizao/payment-applications')) return 'kuaizhizao:payment-application';
  return '';
}

function inferResourceByNodeKey(nodeKey?: string): string {
  const node = (nodeKey || '').trim().toLowerCase();
  if (!node) return '';
  const map: Record<string, string> = {
    sales_contract: 'kuaizhizao:sales-contract',
    sales_order: 'kuaizhizao:sales-order',
    sales_forecast: 'kuaizhizao:sales-forecast',
    sales_order_change: 'kuaizhizao:sales-order-change',
    purchase_order: 'kuaizhizao:purchase-order',
    purchase_request: 'kuaizhizao:purchase-requisition',
    purchase_inquiry: 'kuaizhizao:purchase-inquiry',
    purchase_order_change: 'kuaizhizao:purchase-order-change',
    demand: 'kuaizhizao:demand',
    reporting_record: 'kuaizhizao:production-execution-reporting',
    rework_order: 'kuaizhizao:rework-order',
    quotation: 'kuaizhizao:quotation',

    incoming_inspection: 'kuaizhizao:incoming-inspection',
    process_inspection: 'kuaizhizao:process-inspection',
    finished_goods_inspection: 'kuaizhizao:finished-goods-inspection',
    quality_inspection: 'kuaizhizao:quality-inspection',
    oqc_inspection: 'kuaizhizao:oqc-inspection',
    shipment_notice: 'kuaizhizao:shipment-notice',
    sales_delivery: 'kuaizhizao:outbound',
    production_picking: 'kuaizhizao:outbound',
    work_order: 'kuaizhizao:work-order',
    sales_return: 'kuaizhizao:sales-return',
    receivable: 'kuaicaiwu:receivable',
    payable: 'kuaicaiwu:payable',
    purchase_invoice: 'kuaicaiwu:purchase-invoice',
    partner_statement: 'kuaicaiwu:partner-statement',
    fund_transfer: 'kuaicaiwu:fund-transfer',
    other_income: 'kuaicaiwu:other-income',
    other_expense: 'kuaicaiwu:other-expense',
    other_expense_application: 'kuaicaiwu:other-expense-application',
    payment_application: 'kuaizhizao:payment-application',
    bom_change: 'kuaiplm:change',
    process_route_change: 'kuaiplm:change',
  };
  return map[node] || '';
}

function normalizeStatusValue(value: unknown): string {
  return String(value ?? '').trim().toLowerCase();
}

function matchesAnyStatus(value: unknown, candidates: string[]): boolean {
  const current = normalizeStatusValue(value);
  if (!current) return false;
  return candidates.some((candidate) => normalizeStatusValue(candidate) === current);
}

function usesUnifiedAuditForAction(
  action: UniAuditAction,
  opts: {
    unifiedAudit: boolean;
    resolvedEntityType: string;
    actions: UniAuditActionsMap;
    apiPrefix?: string;
  },
): boolean {
  if (opts.unifiedAudit) return true;
  if (!opts.resolvedEntityType || opts.apiPrefix) return false;
  return !opts.actions[action];
}

export const UniAuditActions: React.FC<UniAuditActionsProps> = ({
  record,
  rowKey = 'id',
  apiPrefix,
  actions = {},
  endpointMap,
  entityName = '单据',
  entityType,
  statusField = 'status',
  reviewStatusField = 'review_status',
  draftStatuses = ['draft', '草稿'],
  pendingStatuses = ['pending_approval', 'pending_review', '待审核'],
  approvedStatuses = ['approved', 'audited', 'confirmed', '已审核', '已确认', '审核通过'],
  rejectedStatuses = ['rejected', '已驳回', '审核驳回', '驳回'],
  workflowAuditEnabled,
  auditNodeKey,
  submitActionLabel = '提交',
  onSuccess,
  theme = 'link',
  size,
  confirmMessages = {},
  resourcePrefix,
  unifiedAudit = false,
  beforeAction,
}) => {
  const { message } = App.useApp();
  const [loadingAction, setLoadingAction] = useState<UniAuditAction | null>(null);
  const [activeAction, setActiveAction] = useState<UniAuditAction | null>(null);
  const [auditHubOpen, setAuditHubOpen] = useState(false);
  const [initiatorSubmitOpen, setInitiatorSubmitOpen] = useState(false);
  const [initiatorAction, setInitiatorAction] = useState<UniAuditAction>('submit');
  const [initiatorNodes, setInitiatorNodes] = useState<SubmitInitiatorNodeHint[]>([]);
  const [initiatorBranchConditions, setInitiatorBranchConditions] = useState<SubmitInitiatorBranchHint[]>(
    [],
  );
  const [hierarchyDepartmentRequired, setHierarchyDepartmentRequired] = useState(false);
  const [hierarchyDepartmentOptions, setHierarchyDepartmentOptions] = useState<HierarchyDepartmentOption[]>(
    [],
  );
  const [defaultHierarchyDepartmentUuid, setDefaultHierarchyDepartmentUuid] = useState<string | null>(null);
  const [initiatorLoading, setInitiatorLoading] = useState(false);
  const rawCurrentUser = useCurrentUser();
  const currentUser = useMemo(() => resolveUserForMenuPermission(rawCurrentUser), [rawCurrentUser]);
  const adminOpen = isAdminBypass(currentUser);
  const adminRevokeAll = useAdminRevokeAllDocuments(false);
  const adminRevokeOpen = adminOpen && adminRevokeAll;
  const documentCode = useMemo(() => resolveRecordDocumentCode(record), [record]);

  const inferredNodeKey = useMemo(() => auditNodeKey || inferAuditNodeKey(apiPrefix), [auditNodeKey, apiPrefix]);

  const auditState =
    record?.audit && typeof record.audit === 'object' && typeof record.audit.phase === 'string'
      ? (record.audit as {
          phase: string;
          enabled?: boolean;
          allowed_actions?: string[];
          entity_type?: string;
          viewer_can_revoke?: boolean;
          viewer_can_withdraw_submit?: boolean;
          viewer_can_recall_own?: boolean;
        })
      : null;
  const auditEntityType = (auditState?.entity_type || '').trim();
  const resolvedEntityType = (entityType || inferredNodeKey || auditEntityType || '').trim();

  // 列表行可能无 record.audit：须用 entityType / nodeKey 查业务配置，禁止空 key → false 误跳过发起人自选
  const inferredAuditEnabled = useAuditRequired(
    inferredNodeKey || (entityType || '').trim() || auditEntityType,
    false,
  );
  const fallbackManualAuditEnabled = workflowAuditEnabled ?? (resolvedEntityType ? inferredAuditEnabled : false);
  const resolvedResource = (
    resourcePrefix
    || inferResourcePrefix(apiPrefix)
    || inferResourceByNodeKey(resolvedEntityType)
  ).trim();
  const hasActionResource = Boolean(resolvedResource);

  const canSubmit = adminOpen || (hasActionResource && hasModulePermission(currentUser ?? undefined, resolvedResource, 'submit'));
  const canReview = adminOpen || (hasActionResource && hasReviewPermission(currentUser ?? undefined, resolvedResource));
  const canRevoke =
    adminRevokeOpen
    || (hasActionResource && hasModulePermission(currentUser ?? undefined, resolvedResource, 'revoke'));

  const status = (record?.[statusField] ?? undefined) as WorkflowStatus;
  const reviewStatus = (record?.[reviewStatusField] ?? undefined) as WorkflowStatus;
  const recordId = (record?.[rowKey] ?? 0) as number;

  const auditAuthoritative = Boolean(auditState);

  const isDraft = matchesAnyStatus(status, draftStatuses) || matchesAnyStatus(reviewStatus, draftStatuses);
  const isPending = matchesAnyStatus(status, pendingStatuses) || matchesAnyStatus(reviewStatus, pendingStatuses);
  const isApproved = matchesAnyStatus(status, approvedStatuses) || matchesAnyStatus(reviewStatus, approvedStatuses);
  const isRejected = matchesAnyStatus(status, rejectedStatuses) || matchesAnyStatus(reviewStatus, rejectedStatuses);

  const actionVisibility = resolveAuditActionVisibility(auditState, {
    isDraft,
    isPending,
    isApproved,
    isRejected,
    manualAuditEnabled: auditState
      ? isManualAuditEnabled(auditState)
      : fallbackManualAuditEnabled,
  });

  const {
    allowedActions,
    manualAuditEnabled: auditFeatureEnabled,
    showSubmit,
    showSubmitReview,
    showWithdraw,
    showApprove,
    showReject,
    showRevoke,
    showRecallOwn,
    showAuditHub,
  } = actionVisibility;

  const unifiedOpts = {
    unifiedAudit,
    resolvedEntityType,
    actions,
    apiPrefix,
  };
  const routeViaUnified = (action: UniAuditAction) =>
    usesUnifiedAuditForAction(action, unifiedOpts);

  const channelByAction: Record<UniAuditAction, boolean> = {
    submit:
      routeViaUnified('submit')
      || (auditAuthoritative && Boolean(resolvedEntityType))
      || Boolean(actions.submit)
      || Boolean(apiPrefix),
    submit_review:
      routeViaUnified('submit_review')
      || (auditAuthoritative && Boolean(resolvedEntityType)),
    withdraw:
      routeViaUnified('withdraw')
      || (auditAuthoritative && Boolean(resolvedEntityType))
      || Boolean(actions.withdraw)
      || Boolean(endpointMap?.withdraw),
    approve:
      routeViaUnified('approve')
      || (auditAuthoritative && Boolean(resolvedEntityType))
      || Boolean(actions.approve)
      || Boolean(apiPrefix),
    reject:
      routeViaUnified('reject')
      || (auditAuthoritative && Boolean(resolvedEntityType))
      || Boolean(actions.reject)
      || Boolean(apiPrefix),
    revoke:
      routeViaUnified('revoke')
      || (auditAuthoritative && Boolean(resolvedEntityType))
      || Boolean(actions.revoke)
      || Boolean(apiPrefix),
    recall_own:
      routeViaUnified('recall_own')
      || (auditAuthoritative && Boolean(resolvedEntityType)),
    transfer: false,
    add_sign: false,
    delegate: false,
    urge: false,
    edit: false,
  };
  const recordViewerActions = readAuditViewerActions(auditState);
  const flowApprove = resolveAuditFlowExecutePermission('approve', {
    adminBypass: adminOpen,
    rbacAllowed: canReview,
    audit: auditState,
    liveViewerActions: recordViewerActions,
  });
  const flowReject = resolveAuditFlowExecutePermission('reject', {
    adminBypass: adminOpen,
    rbacAllowed: canReview,
    audit: auditState,
    liveViewerActions: recordViewerActions,
  });

  const viewerCanRevoke = auditState?.viewer_can_revoke;
  const viewerCanWithdraw = auditState?.viewer_can_withdraw_submit;

  const canExecuteByAction: Record<UniAuditAction, boolean> = {
    submit: canSubmit,
    submit_review: canSubmit,
    withdraw:
      canSubmit
      && (typeof viewerCanWithdraw === 'boolean' ? viewerCanWithdraw : true),
    approve: flowApprove.canExecute,
    reject: flowReject.canExecute,
    revoke:
      canRevoke
      && (typeof viewerCanRevoke === 'boolean' ? viewerCanRevoke : true),
    recall_own:
      canReview
      && (typeof auditState?.viewer_can_recall_own === 'boolean'
        ? Boolean(auditState.viewer_can_recall_own)
        : true),
    transfer: canReview,
    add_sign: canReview,
    delegate: canReview,
    urge: canSubmit,
    edit: canReview,
  };

  const enabledForLabels = auditFeatureEnabled;
  const approveLabel = enabledForLabels ? '审核' : '确认';
  const migratedSaveSubmitCopy =
    resolvedEntityType === 'purchase_order'
    || resolvedEntityType === 'sales_contract'
    || resolvedEntityType === 'quotation'
    || resolvedEntityType === 'sales_forecast'
    || resolvedEntityType === 'sales_order'
    || resolvedEntityType === 'sales_order_change'
    || resolvedEntityType === 'purchase_request'
    || resolvedEntityType === 'purchase_inquiry'
    || resolvedEntityType === 'payment_application'
    || resolvedEntityType === 'purchase_order_change'
    || resolvedEntityType === 'purchase_return'
    || resolvedEntityType === 'sales_return'
    || resolvedEntityType === 'demand'
    || resolvedEntityType === 'purchase_receipt'
    || resolvedEntityType === 'receipt_notice'
    || resolvedEntityType === 'shipment_notice'
    || resolvedEntityType === 'sales_delivery'
    || resolvedEntityType === 'purchase_arrival_delay'
    || resolvedEntityType === 'work_order'
    || resolvedEntityType === 'reporting_record'
    || resolvedEntityType === 'rework_order'
    || resolvedEntityType === 'receivable'
    || resolvedEntityType === 'payable'
    || resolvedEntityType === 'receipt'
    || resolvedEntityType === 'receipt_refund'
    || resolvedEntityType === 'payment'
    || resolvedEntityType === 'payment_refund'
    || resolvedEntityType === 'sales_invoice'
    || resolvedEntityType === 'other_income'
    || resolvedEntityType === 'other_expense'
    || resolvedEntityType === 'notes_receivable'
    || resolvedEntityType === 'notes_payable'
    || resolvedEntityType === 'purchase_invoice'
    || resolvedEntityType === 'other_expense_application'
    || resolvedEntityType === 'partner_statement'
    || resolvedEntityType === 'fund_transfer';
  const effectiveSubmitLabel = (() => {
    if (
      isRejected &&
      !migratedSaveSubmitCopy &&
      (!submitActionLabel || submitActionLabel === '提交')
    ) {
      return '重新提交';
    }
    if (!enabledForLabels && submitActionLabel.includes('审核')) {
      return submitActionLabel.replace(/审核/g, '').trim() || '提交';
    }
    return submitActionLabel;
  })();

  const purchaseOrderPhase = auditState?.phase;
  const withdrawActionTitle = (() => {
    if (migratedSaveSubmitCopy) {
      if (purchaseOrderPhase === 'pending') return '撤回审核';
      if (resolvedEntityType === 'partner_statement') {
        const biz = String(record?.[statusField] ?? '').trim();
        if (biz === 'Confirmed') return '撤销确认';
      }
      return '撤销提交';
    }
    return '撤回提交';
  })();
  const revokeActionTitle = migratedSaveSubmitCopy ? '反审核' : rowActionLabel('revoke');
  const recallActionTitle = migratedSaveSubmitCopy ? '撤回审核' : '撤销审核';

  const resolvedEndpoints = {
    ...DEFAULT_ENDPOINTS,
    ...(endpointMap || {}),
  };

  const hubActions = useMemo((): UniAuditHubAction[] => {
    const items: UniAuditHubAction[] = [];
    // 撤回提交（发起人）与撤销审核（recall_own / revoke）分轨，禁止混用文案或互相顶替
    if (showWithdraw && channelByAction.withdraw) {
      items.push({ action: 'withdraw', title: withdrawActionTitle, canExecute: canExecuteByAction.withdraw });
    }
    if (showRecallOwn && channelByAction.recall_own) {
      items.push({
        action: 'recall_own',
        title: recallActionTitle,
        canExecute: canExecuteByAction.recall_own,
        rbacAllowed: canReview,
      });
    }
    // revoke 以行内按钮为主；hub 仍带上以便弹窗 live 在实例已通过时能立刻展示「撤销审核」
    if (showRevoke && channelByAction.revoke) {
      items.push({
        action: 'revoke',
        title: revokeActionTitle,
        canExecute: canExecuteByAction.revoke,
        rbacAllowed: canRevoke,
        danger: true,
      });
    }
    if (showApprove && channelByAction.approve) {
      items.push({
        action: 'approve',
        title: approveLabel,
        // 列表态可能尚无待办；弹窗 getApprovalStatus 会补齐并用 live viewer_actions 再裁
        canExecute: canExecuteByAction.approve,
        rbacAllowed: canReview,
        disabledReason: flowApprove.blockReason,
        primary: true,
      });
    }
    if (showReject && channelByAction.reject) {
      items.push({
        action: 'reject',
        title: '驳回',
        canExecute: canExecuteByAction.reject,
        rbacAllowed: canReview,
        disabledReason: flowReject.blockReason,
        danger: true,
      });
    }
    return items;
  }, [
    showWithdraw,
    showRecallOwn,
    showRevoke,
    showApprove,
    showReject,
    channelByAction.withdraw,
    channelByAction.recall_own,
    channelByAction.revoke,
    channelByAction.approve,
    channelByAction.reject,
    canExecuteByAction.withdraw,
    canExecuteByAction.recall_own,
    canExecuteByAction.revoke,
    canExecuteByAction.approve,
    canExecuteByAction.reject,
    canReview,
    canRevoke,
    flowApprove.blockReason,
    flowReject.blockReason,
    approveLabel,
    withdrawActionTitle,
    recallActionTitle,
    revokeActionTitle,
  ]);

  const doApiCall = async (
    actionType: UniAuditAction,
    reason?: string,
    payload?: Record<string, unknown>,
  ) => {
    if (
      routeViaUnified(actionType)
      || (auditAuthoritative && Boolean(resolvedEntityType))
    ) {
      if (!resolvedEntityType) {
        throw new Error('统一执行入口需要 entityType 或 auditNodeKey');
      }
      const data = { ...(payload || {}), ...(reason ? { reason } : {}) };
      return apiRequest(`/core/uni-audit/${resolvedEntityType}/${recordId}/${actionType}`, {
        method: 'POST',
        data,
      });
    }
    if (actions[actionType]) {
      const fn = actions[actionType] as (...args: unknown[]) => Promise<unknown>;
      if (payload && (actionType === 'transfer' || actionType === 'add_sign' || actionType === 'delegate')) {
        return fn(recordId, payload, reason);
      }
      return fn(recordId, reason);
    }
    if (!apiPrefix) {
      throw new Error(`未配置 ${actionType} 操作对应的 API`);
    }
    const endpoint = resolvedEndpoints[actionType];
    return apiRequest(`${apiPrefix}/${recordId}/${endpoint}`, {
      method: 'POST',
      params: reason ? { rejection_reason: reason } : undefined,
    });
  };

  const openActionModal = (action: UniAuditAction) => setActiveAction(action);

  const beginInitiatorSubmit = useCallback(async (action: 'submit' | 'submit_review') => {
    setInitiatorAction(action);
    if (!auditFeatureEnabled || !resolvedEntityType) {
      openActionModal(action);
      return;
    }
    setInitiatorLoading(true);
    try {
      const requirements = await fetchSubmitInitiatorRequirements(resolvedEntityType, recordId);
      const { nodes, branch_conditions: branchConditions } = requirements;
      const hierarchyRequired = Boolean(requirements.hierarchy_department_required);
      const hierarchyOptions = requirements.hierarchy_department_options ?? [];
      const needsHierarchyPicker = hierarchyRequired && hierarchyOptions.length >= 2;
      if (nodes.length > 0 || branchConditions.length > 0 || needsHierarchyPicker) {
        setInitiatorNodes(nodes);
        setInitiatorBranchConditions(branchConditions);
        setHierarchyDepartmentRequired(hierarchyRequired);
        setHierarchyDepartmentOptions(hierarchyOptions);
        setDefaultHierarchyDepartmentUuid(requirements.default_hierarchy_department_uuid ?? null);
        setInitiatorSubmitOpen(true);
      } else if (action === 'submit_review') {
        setLoadingAction('submit_review');
        try {
          if (!adminOpen && !canSubmit) {
            message.warning('您没有该操作权限，仅可查看审核流程');
            return;
          }
          if (beforeAction) {
            const blocked = await beforeAction(action, record);
            if (blocked) {
              message.error(blocked);
              return;
            }
          }
          const res = await doApiCall('submit_review', undefined, {});
          if (res?.demand_synced) {
            message.success('提交审核成功，已同步关联需求。');
          } else {
            message.success('提交审核成功');
          }
          onSuccess?.();
        } catch (error: unknown) {
          const errMsg = error instanceof Error ? error.message : String(error);
          message.error(`提交审核失败: ${errMsg || '未知错误'}`);
        } finally {
          setLoadingAction(null);
        }
      } else {
        openActionModal(action);
      }
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : String(error);
      message.error(`加载提交审批选项失败: ${errMsg}`);
    } finally {
      setInitiatorLoading(false);
    }
  }, [
    adminOpen,
    auditFeatureEnabled,
    resolvedEntityType,
    message,
    recordId,
    canSubmit,
    beforeAction,
    record,
    doApiCall,
    onSuccess,
  ]);

  const beginSubmit = useCallback(async () => {
    if (
      resolvedEntityType === 'purchase_order'
      || resolvedEntityType === 'sales_contract'
      || resolvedEntityType === 'quotation'
      || resolvedEntityType === 'sales_forecast'
      || resolvedEntityType === 'sales_order'
      || resolvedEntityType === 'sales_order_change'
      || resolvedEntityType === 'purchase_request'
      || resolvedEntityType === 'purchase_inquiry'
      || resolvedEntityType === 'payment_application'
      || resolvedEntityType === 'purchase_order_change'
      || resolvedEntityType === 'purchase_return'
      || resolvedEntityType === 'sales_return'
      || resolvedEntityType === 'demand'
      || resolvedEntityType === 'purchase_receipt'
      || resolvedEntityType === 'receipt_notice'
      || resolvedEntityType === 'shipment_notice'
      || resolvedEntityType === 'sales_delivery'
      || resolvedEntityType === 'purchase_arrival_delay'
      || resolvedEntityType === 'work_order'
      || resolvedEntityType === 'reporting_record'
      || resolvedEntityType === 'rework_order'
      || resolvedEntityType === 'receivable'
      || resolvedEntityType === 'payable'
      || resolvedEntityType === 'receipt'
      || resolvedEntityType === 'receipt_refund'
      || resolvedEntityType === 'payment'
      || resolvedEntityType === 'payment_refund'
      || resolvedEntityType === 'sales_invoice'
      || resolvedEntityType === 'other_income'
      || resolvedEntityType === 'other_expense'
      || resolvedEntityType === 'notes_receivable'
      || resolvedEntityType === 'notes_payable'
      || resolvedEntityType === 'purchase_invoice'
      || resolvedEntityType === 'other_expense_application'
      || resolvedEntityType === 'partner_statement'
      || resolvedEntityType === 'fund_transfer'
    ) {
      openActionModal('submit');
      return;
    }
    await beginInitiatorSubmit('submit');
  }, [beginInitiatorSubmit, resolvedEntityType]);

  const beginSubmitReview = useCallback(async () => {
    await beginInitiatorSubmit('submit_review');
  }, [beginInitiatorSubmit]);

  const getActionTitle = (action: UniAuditAction): string => {
    if (action === 'submit') return effectiveSubmitLabel;
    if (action === 'submit_review') return '提交审核';
    if (action === 'approve') return approveLabel;
    if (action === 'reject') return '驳回';
    if (action === 'revoke') return revokeActionTitle;
    if (action === 'transfer') return '转交';
    if (action === 'add_sign') return '加签';
    if (action === 'delegate') return '委托';
    if (action === 'urge') return '催办';
    if (action === 'withdraw') return withdrawActionTitle;
    if (action === 'recall_own') return recallActionTitle;
    return '操作';
  };

  const canRunAction = (action: UniAuditAction): boolean => {
    if (adminOpen) return true;
    if (action === 'urge') return canSubmit;
    if (action === 'transfer' || action === 'add_sign' || action === 'delegate') return canReview;
    // approve/reject/recall_own/revoke：此处只验 RBAC。列表态 viewer_can_* 可能滞后于弹窗 live；
    // 按钮可见性由 UniAuditModal live 裁剪，后端 assert_* / recall_own / revoke 仍做身份门禁。
    if (action === 'approve' || action === 'reject' || action === 'recall_own') return canReview;
    if (action === 'revoke') return canRevoke;
    if (action === 'submit_review' || action === 'withdraw') return canSubmit;
    return Boolean(canExecuteByAction[action as keyof typeof canExecuteByAction]);
  };

  const runAction = async (
    action: UniAuditAction,
    reason?: string,
    payload?: Record<string, unknown>,
  ): Promise<boolean> => {
    if (!canRunAction(action)) {
      message.warning(
        action === 'approve' || action === 'reject'
          ? '您的角色未开通本单据的审核权限'
          : '您没有该操作权限，仅可查看审核流程',
      );
      return false;
    }
    if (beforeAction) {
      try {
        const blocked = await beforeAction(action, record);
        if (blocked) {
          message.error(blocked);
          return false;
        }
      } catch (error: any) {
        message.error(error?.message || '提交前校验失败');
        return false;
      }
    }
    setLoadingAction(action);
    try {
      const res = await doApiCall(action, reason, payload);
      if (res?.demand_synced) {
        message.success(`${getActionTitle(action)}成功，已同步关联需求。`);
      } else {
        message.success(`${getActionTitle(action)}成功`);
      }
      onSuccess?.();

      // 多级审核：本级通过 / 撤回本级后若仍 pending，保持弹窗并刷新节点图
      if (
        auditHubOpen
        && (action === 'approve' || action === 'reject' || action === 'recall_own')
        && resolvedEntityType
      ) {
        try {
          const status = await getApprovalStatus(resolvedEntityType, recordId, {
            nodeKey: inferredNodeKey,
          });
          const stillPending = status?.has_instance && status.status === 'pending';
          if (action === 'recall_own' && stillPending) {
            return true;
          }
          const stillMine =
            Boolean(status?.viewer_actions?.has_my_pending_task)
            || Boolean(status?.has_my_pending_task)
            || Boolean(status?.viewer_actions?.approve);
          if (stillPending && (stillMine || adminOpen)) {
            return true;
          }
        } catch {
          // 状态刷新失败则按原路径关闭弹窗
        }
      }

      setActiveAction(null);
      setAuditHubOpen(false);
      return false;
    } catch (error: any) {
      message.error(`${getActionTitle(action)}失败: ${error.message || '未知错误'}`);
      return false;
    } finally {
      setLoadingAction(null);
    }
  };

  const handleConfirm = async (reason?: string, payload?: Record<string, unknown>) => {
    if (!activeAction) return;
    await runAction(activeAction, reason, payload);
  };

  const handleHubAction = async (
    action: UniAuditAction,
    reason?: string,
    payload?: Record<string, unknown>,
  ): Promise<boolean> => {
    return runAction(action, reason, payload);
  };

  const isBusy = !!loadingAction;
  const submitUsesCustomLabel = effectiveSubmitLabel !== '提交';

  const isToolbarTheme = theme === 'default';
  const btnSize = size ?? (isToolbarTheme ? 'medium' : 'small');

  const renderActionButton = (
    kind: RowActionPermissionKind,
    config: {
      key: string;
      label?: string;
      labelKeep?: boolean;
      loading?: boolean;
      disabled?: boolean;
      title?: string;
      keepVisibleWhenDisabled?: boolean;
      onClick: () => void;
      danger?: boolean;
    },
  ) => {
    const visibleWhenDisabled = config.keepVisibleWhenDisabled
      ? { 'data-row-action-visible-when-disabled': true as const }
      : {};
    if (!isToolbarTheme) {
      return prepareRowActionButton(kind, {
        key: config.key,
        labelKeep: config.labelKeep,
        loading: config.loading,
        disabled: config.disabled,
        title: config.title,
        onClick: config.onClick,
        children: config.label,
        ...visibleWhenDisabled,
      });
    }
    const iconByKind: Partial<Record<RowActionPermissionKind, React.ReactNode>> = {
      submit: <SendOutlined />,
      audit: <AuditOutlined />,
      revoke: <RollbackOutlined />,
    };
    const text =
      config.labelKeep && config.label
        ? config.label
        : config.label ?? rowActionLabel(kind);
    return (
      <Button
        key={config.key}
        {...rowActionKind(kind)}
        size={btnSize}
        type="default"
        danger={config.danger}
        icon={iconByKind[kind]}
        loading={config.loading}
        disabled={config.disabled}
        title={config.title}
        onClick={config.onClick}
        {...visibleWhenDisabled}
      >
        {text}
      </Button>
    );
  };

  if (!record || !record[rowKey]) return null;

  const inlineButtons: React.ReactNode[] = [];

  if (showSubmit && channelByAction.submit) {
    inlineButtons.push(
      renderActionButton('submit', {
        key: 'audit-submit',
        label: effectiveSubmitLabel,
        labelKeep: submitUsesCustomLabel,
        loading: loadingAction === 'submit' || initiatorLoading,
        disabled: (isBusy && loadingAction !== 'submit') || initiatorLoading,
        onClick: () => void beginSubmit(),
      }),
    );
  }

  if (showWithdraw && channelByAction.withdraw) {
    inlineButtons.push(
      renderActionButton('revoke', {
        key: 'audit-withdraw',
        label: withdrawActionTitle,
        labelKeep: migratedSaveSubmitCopy,
        loading: loadingAction === 'withdraw',
        disabled: isBusy && loadingAction !== 'withdraw',
        onClick: () => openActionModal('withdraw'),
      }),
    );
  }

  if (showSubmitReview && channelByAction.submit_review) {
    inlineButtons.push(
      renderActionButton('submit', {
        key: 'audit-submit-review',
        label: '提交审核',
        labelKeep: true,
        loading: loadingAction === 'submit_review' || initiatorLoading,
        disabled: (isBusy && loadingAction !== 'submit_review') || initiatorLoading,
        onClick: () => void beginSubmitReview(),
      }),
    );
  }

  if (showAuditHub) {
    const mine = flowApprove.canExecute;
    const acted = Boolean(recordViewerActions?.my_acted) && !mine;
    const waitingReason = recordViewerActions?.block_reason
      || flowApprove.blockReason
      || undefined;
    // 已审过：按钮改文案，仍可打开弹窗（提交人撤回/查看进度）
    // 未轮到我且没有其它入口：置灰并保留，悬停说明当前待办人
    const grayBecauseNotMine = !mine && !acted && !showWithdraw;
    inlineButtons.push(
      renderActionButton('audit', {
        key: 'audit-hub',
        label: acted ? '您已审核' : approveLabel,
        labelKeep: acted || approveLabel !== '审核',
        loading: isBusy && auditHubOpen,
        disabled: grayBecauseNotMine || (isBusy && !auditHubOpen),
        keepVisibleWhenDisabled: grayBecauseNotMine,
        title: !mine ? waitingReason : undefined,
        onClick: () => setAuditHubOpen(true),
      }),
    );
  }

  if (showRevoke && channelByAction.revoke) {
    inlineButtons.push(
      renderActionButton('revoke', {
        key: 'audit-revoke',
        label: migratedSaveSubmitCopy ? revokeActionTitle : undefined,
        labelKeep: migratedSaveSubmitCopy,
        loading: loadingAction === 'revoke',
        disabled: isBusy && loadingAction !== 'revoke',
        onClick: () => openActionModal('revoke'),
      }),
    );
  }

  if (inlineButtons.length === 0) return null;

  /**
   * 行内（link）单按钮直接直出，避免再包 Space 与 UniTable
   * `.uni-table-operation-actions` 实测抢布局。多按钮时才用 Space 保间距。
   * 工具栏（default）始终 Space。
   */
  const actionNodes = isToolbarTheme ? (
    <Space size={8} align="center">
      {inlineButtons}
    </Space>
  ) : inlineButtons.length === 1 ? (
    inlineButtons[0]
  ) : (
    <Space size={4} align="center">
      {inlineButtons}
    </Space>
  );

  return (
    <>
      {actionNodes}

      {auditHubOpen && (
        <UniAuditModal
          open
          mode="hub"
          hubTitle="审核"
          entityName={entityName}
          documentCode={documentCode}
          entityType={resolvedEntityType || undefined}
          entityId={recordId}
          auditNodeKey={inferredNodeKey || undefined}
          hubActions={hubActions}
          rbacAllowed={canReview}
          onCancel={() => setAuditHubOpen(false)}
          onAction={handleHubAction}
        />
      )}

      {activeAction && (
        <UniAuditModal
          open
          action={activeAction}
          entityName={entityName}
          documentCode={documentCode}
          actionTitle={getActionTitle(activeAction)}
          actionDescription={
            confirmMessages[activeAction]
              || `确定要${getActionTitle(activeAction)}这个${entityName}吗？`
          }
          entityType={resolvedEntityType || undefined}
          entityId={recordId}
          auditNodeKey={inferredNodeKey || undefined}
          canExecute={canExecuteByAction[activeAction]}
          onCancel={() => setActiveAction(null)}
          onConfirm={handleConfirm}
        />
      )}

      {initiatorSubmitOpen && (
        <UniAuditInitiatorSubmitModal
          open
          entityName={entityName}
          submitTitle={initiatorAction === 'submit_review' ? '提交审核' : effectiveSubmitLabel}
          nodes={initiatorNodes}
          branchConditions={initiatorBranchConditions}
          hierarchyDepartmentRequired={hierarchyDepartmentRequired}
          hierarchyDepartmentOptions={hierarchyDepartmentOptions}
          defaultHierarchyDepartmentUuid={defaultHierarchyDepartmentUuid}
          loading={loadingAction === initiatorAction}
          onCancel={() => setInitiatorSubmitOpen(false)}
          onConfirm={async (selectedByNode, branchByCondition, hierarchyDepartmentUuid) => {
            const extra: Record<string, unknown> = {
              selected_approver_by_node: selectedByNode,
              initiator_branch_by_node: branchByCondition,
            };
            if (hierarchyDepartmentUuid) {
              extra.hierarchy_department_uuid = hierarchyDepartmentUuid;
            }
            await runAction(initiatorAction, undefined, extra);
            setInitiatorSubmitOpen(false);
          }}
        />
      )}
    </>
  );
};

UniAuditActions.displayName = 'UniWorkflowActions';

export type { WorkflowStatus, UniAuditAction, UniAuditActionsMap, UniAuditEndpointMap } from './types';
export default UniAuditActions;
