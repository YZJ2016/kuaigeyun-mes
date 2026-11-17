/**
 * 审核类单据批量操作统一入口（与行级 UniWorkflowActions / UniAuditActions 对称）。
 *
 * 门控：capabilities（业务态）+ useResourcePermissions（RBAC）。
 * 执行：提交/撤回/反审可逐条 API；「审核」须打开 UniAuditModal（与行级审核 hub 一致），禁止直调 approve 跳过弹窗。
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { App } from 'antd';
import type { ButtonProps } from 'antd';
import {
  CheckOutlined,
  RollbackOutlined,
  SendOutlined,
  UndoOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ResourcePermissionGates } from '../../hooks/useResourcePermissions';
import { batchSomeCapabilityAllowed } from '../../hooks/useDocumentCapabilities';
import { auditFlowCapabilityOverride } from '../../utils/auditFlowViewerGate';
import { apiRequest } from '../../services/api';
import { getApprovalStatus } from '../../services/approvalInstance';
import UniAuditModal, { type UniAuditHubAction } from '../uni-audit/UniAuditModal';
import type { UniAuditAction } from '../uni-audit/types';
import { resolveRecordDocumentCode } from '../uni-audit/resolveRecordDocumentCode';
import { registerAuditDetailMenuOpener } from './auditDetailMenuBridge';
import { UniBatchMenuButton, type UniBatchMenuItem } from './index';

type ActionCapability = { allowed: boolean; reason?: string | null };

export type AuditBatchAction = 'submit' | 'withdraw' | 'approve' | 'revoke';

export type AuditBatchCapabilityKeys = Record<AuditBatchAction, string>;

export const DEFAULT_AUDIT_BATCH_CAPABILITY_KEYS: AuditBatchCapabilityKeys = {
  submit: 'submit',
  withdraw: 'withdraw_submit',
  approve: 'approve',
  revoke: 'revoke_approval',
};

export const DEFAULT_AUDIT_BATCH_PERMISSION_ACTIONS: Record<
  AuditBatchAction,
  'submit' | 'revoke' | 'audit'
> = {
  submit: 'submit',
  withdraw: 'revoke',
  approve: 'audit',
  revoke: 'revoke',
};

export type AuditBatchHandlers = Partial<
  Record<AuditBatchAction, (id: number) => Promise<unknown>>
>;

export type BulkAuditBatchResult = {
  success_count?: number;
  failed_count?: number;
  failed_items?: Array<{ reason?: string }>;
};

export type BulkAuditBatchHandlers = Partial<
  Record<AuditBatchAction, (ids: number[]) => Promise<BulkAuditBatchResult>>
>;

export type CapabilitiesRecord = Record<string, ActionCapability | undefined>;

const AUDIT_BATCH_ACTION_BY_CAPABILITY_KEY: Partial<Record<string, AuditBatchAction>> = {
  submit: 'submit',
  withdraw_submit: 'withdraw',
  approve: 'approve',
  revoke_approval: 'revoke',
};

export function resolveBatchRecordId(
  key: React.Key,
  records: { id?: number }[],
  resolveIdFromKey?: (key: React.Key) => number | null,
): number | null {
  if (resolveIdFromKey) {
    const id = resolveIdFromKey(key);
    if (id != null && Number.isFinite(id) && id > 0) return id;
  }
  const id = Number(key);
  if (!Number.isFinite(id) || id <= 0) return null;
  if (records.some((r) => Number(r.id) === id)) return id;
  return id;
}

export function pickCapability(
  record: {
    capabilities?: CapabilitiesRecord | null;
    audit?: { allowed_actions?: string[]; phase?: string; enabled?: boolean; mode?: string; viewer_actions?: unknown } | null;
  },
  key: string,
): ActionCapability | undefined {
  const flowOverride = auditFlowCapabilityOverride(record, key);
  if (flowOverride !== undefined) {
    return {
      allowed: flowOverride.allowed,
      reason: flowOverride.reason ?? undefined,
    };
  }

  const cap = record.capabilities?.[key];
  if (cap != null) return cap;

  const auditAction = AUDIT_BATCH_ACTION_BY_CAPABILITY_KEY[key];
  const allowedActions = record.audit?.allowed_actions;
  if (Array.isArray(allowedActions) && allowedActions.includes(key)) {
    return { allowed: true };
  }
  if (!auditAction || !allowedActions) return undefined;

  return { allowed: allowedActions.includes(auditAction) };
}

export function defaultAuditBatchAllowed<T>(
  records: T[],
  permAllowed: boolean,
  capabilityKey: string,
  pickRecord: (r: T) => {
    capabilities?: CapabilitiesRecord | null;
    audit?: { allowed_actions?: string[]; phase?: string; enabled?: boolean; mode?: string; viewer_actions?: unknown } | null;
  },
): boolean {
  return batchSomeCapabilityAllowed(records, permAllowed, (r) =>
    pickCapability(pickRecord(r), capabilityKey),
  );
}

/** 工具栏「审核」打开 UniAuditModal 所需的单据身份（与行级 hub 同源） */
export type AuditBatchModalEntity = {
  entityType: string;
  entityName: string;
};

export interface BuildAuditBatchMenuItemsOptions<T> {
  /** 当前勾选行；工具栏「审核详情」用于回显单号；自定义菜单页可不传 */
  selectedRecords?: T[];
  permGates: ResourcePermissionGates;
  /** @deprecated 不再用于隐藏菜单项；保留以兼容既有页面传参 */
  auditEnabled?: boolean;
  handlers?: AuditBatchHandlers;
  bulkHandlers?: BulkAuditBatchHandlers;
  extraMenuItems?: UniBatchMenuItem[];
  onBatchComplete?: () => void;
  resolveIdFromKey?: (key: React.Key) => number | null;
  /** i18n 前缀，默认 components.uniBatch.audit */
  i18nPrefix?: string;
  /**
   * 工具栏点「审核」时打开 UniAuditModal hub（与行内审核一致）。
   * 有 approve handler 时必须传入，禁止直调 approve 跳过弹窗。
   */
  auditEntity?: AuditBatchModalEntity;
}

export function useAuditBatchRunner<T extends { id?: number }>(
  options: BuildAuditBatchMenuItemsOptions<T>,
) {
  const { message } = App.useApp();
  const { t } = useTranslation();
  const {
    permGates,
    handlers = {},
    bulkHandlers = {},
    onBatchComplete,
    resolveIdFromKey,
    i18nPrefix = 'components.uniBatch.audit',
    auditEntity,
  } = options;

  const [hubSession, setHubSession] = useState<{
    id: number;
    record: T;
    /** approve=执行审核；detail=查看流程进度（仍可在 live 门控下操作） */
    intent: 'approve' | 'detail';
  } | null>(null);

  const canReview = permGates.canAction?.('audit') ?? false;
  const canSubmit = permGates.canAction?.('submit') ?? false;
  const canRevoke = permGates.canAction?.('revoke') ?? false;
  const selectedRecords = options.selectedRecords ?? [];

  const hubActions: UniAuditHubAction[] = useMemo(
    () => [
      {
        action: 'approve',
        title: t('components.uniAction.audit'),
        canExecute: true,
        rbacAllowed: canReview,
        primary: true,
      },
      {
        action: 'reject',
        title: t('components.uniAction.reject'),
        canExecute: true,
        rbacAllowed: canReview,
        danger: true,
      },
      {
        action: 'withdraw',
        title: t('components.uniAudit.withdrawSubmitAction'),
        canExecute: true,
        rbacAllowed: canSubmit,
      },
      {
        action: 'recall_own',
        title: t('components.uniAudit.recallOwnAction'),
        canExecute: true,
        rbacAllowed: canReview,
      },
      {
        action: 'revoke',
        title: t('components.uniAudit.revokeAction'),
        canExecute: true,
        rbacAllowed: canRevoke,
        danger: true,
      },
    ],
    [canReview, canRevoke, canSubmit, t],
  );

  const closeHub = useCallback(() => setHubSession(null), []);

  /** 打开审核弹窗查看整体流程进度（不要求当前可点「审核」） */
  const openAuditDetail = useCallback(
    (keys: React.Key[], records: T[] = selectedRecords) => {
      if (!auditEntity?.entityType) {
        message.error(t(`${i18nPrefix}.approveModalMisconfigured`));
        return;
      }
      if (keys.length !== 1) {
        message.warning(t(`${i18nPrefix}.detailSelectOne`));
        return;
      }
      const id = resolveBatchRecordId(keys[0], records, resolveIdFromKey);
      if (id == null) {
        message.warning(t(`${i18nPrefix}.detailSelectOne`));
        return;
      }
      const record = records.find((r) => Number(r.id) === id) ?? ({ id } as T);
      setHubSession({ id, record, intent: 'detail' });
    },
    [auditEntity?.entityType, i18nPrefix, message, resolveIdFromKey, selectedRecords, t],
  );

  useEffect(() => {
    if (!auditEntity?.entityType) return undefined;
    return registerAuditDetailMenuOpener({
      openFromKeys: (keys) => openAuditDetail(keys),
    });
  }, [auditEntity?.entityType, openAuditDetail]);

  const handleHubAction = useCallback(
    async (
      action: UniAuditAction,
      reason?: string,
      payload?: Record<string, unknown>,
    ): Promise<boolean> => {
      if (!hubSession || !auditEntity?.entityType) return false;
      const entityType = auditEntity.entityType;
      const entityId = hubSession.id;
      const data = { ...(payload || {}), ...(reason ? { reason } : {}) };
      try {
        await apiRequest(
          `/core/uni-audit/${encodeURIComponent(entityType)}/${entityId}/${action}`,
          { method: 'POST', data },
        );
        message.success(
          t(`${i18nPrefix}.hubActionSuccess`, {
            action: t(`components.uniBatch.auditHub.${action}`),
          }),
        );
      } catch (e: unknown) {
        const err = e as { message?: string };
        message.error(err?.message || t(`${i18nPrefix}.failed`, { action: t('components.uniAction.audit') }));
        return false;
      }

      // 多级审核：本级通过后若仍待办本人，保持弹窗
      if (action === 'approve' || action === 'reject' || action === 'recall_own') {
        try {
          const status = await getApprovalStatus(entityType, entityId);
          const stillPending = Boolean(status?.has_instance && status.status === 'pending');
          const stillMine =
            Boolean(status?.viewer_actions?.has_my_pending_task)
            || Boolean(status?.has_my_pending_task)
            || Boolean(status?.viewer_actions?.approve);
          if (stillPending && stillMine) {
            return true;
          }
        } catch {
          // 状态刷新失败则关闭弹窗
        }
      }

      closeHub();
      onBatchComplete?.();
      return false;
    },
    [auditEntity?.entityType, closeHub, hubSession, i18nPrefix, message, onBatchComplete, t],
  );

  const runAction = useCallback(
    async (
      action: AuditBatchAction,
      keys: React.Key[],
      records: T[],
      _auditEnabled: boolean,
    ) => {
      const handler = handlers[action];
      const bulkHandler = bulkHandlers[action];
      if (!handler && !bulkHandler) return;

      const capKey = DEFAULT_AUDIT_BATCH_CAPABILITY_KEYS[action];
      const permAction = DEFAULT_AUDIT_BATCH_PERMISSION_ACTIONS[action];
      const canPerm = permGates.canAction?.(permAction) ?? false;

      if (
        records.length > 0 &&
        !defaultAuditBatchAllowed(records, canPerm, capKey, (r) => r)
      ) {
        message.warning(t(`${i18nPrefix}.${action}NotAllowed`));
        return;
      }

      const eligibleIds: number[] = [];
      const eligibleRecords: T[] = [];
      const seen = new Set<number>();
      for (const key of keys) {
        const id = resolveBatchRecordId(key, records, resolveIdFromKey);
        if (id == null || seen.has(id)) continue;
        const record = records.find((r) => Number(r.id) === id);
        if (!record || !canPerm) continue;
        if (pickCapability(record, capKey)?.allowed !== true) continue;
        seen.add(id);
        eligibleIds.push(id);
        eligibleRecords.push(record);
      }

      if (eligibleIds.length === 0) {
        message.warning(t(`${i18nPrefix}.${action}NotAllowed`));
        return;
      }

      // 工具栏「审核」：打开 UniAuditModal hub，与行级审核同一路径
      if (action === 'approve') {
        if (!auditEntity?.entityType) {
          message.error(t(`${i18nPrefix}.approveModalMisconfigured`));
          return;
        }
        if (eligibleIds.length !== 1) {
          message.warning(t(`${i18nPrefix}.approveSelectOne`));
          return;
        }
        setHubSession({ id: eligibleIds[0], record: eligibleRecords[0], intent: 'approve' });
        return;
      }

      const actionLabel = t(`${i18nPrefix}.${action}`);

      if (bulkHandler) {
        try {
          const res = await bulkHandler(eligibleIds);
          const success = res.success_count ?? 0;
          const failed = res.failed_count ?? 0;
          if (failed === 0 && success > 0) {
            message.success(t(`${i18nPrefix}.success`, { action: actionLabel, count: success }));
          } else if (success > 0 || failed > 0) {
            const reason = res.failed_items?.[0]?.reason;
            if (reason) {
              message.warning(
                t(`${i18nPrefix}.partialWithReason`, { action: actionLabel, success, failed, reason }),
              );
            } else {
              message.warning(
                t(`${i18nPrefix}.partial`, { action: actionLabel, success, failed }),
              );
            }
          }
          onBatchComplete?.();
        } catch (e: unknown) {
          const err = e as { message?: string };
          message.error(err?.message || t(`${i18nPrefix}.failed`, { action: actionLabel }));
        }
        return;
      }

      let success = 0;
      let failed = 0;

      for (const id of eligibleIds) {
        try {
          await handler!(id);
          success += 1;
        } catch {
          failed += 1;
        }
      }

      if (success > 0) {
        message.success(t(`${i18nPrefix}.success`, { action: actionLabel, count: success }));
      }
      if (failed > 0) {
        message.warning(
          t(`${i18nPrefix}.partial`, { action: actionLabel, success, failed }),
        );
      }

      onBatchComplete?.();
    },
    [
      auditEntity?.entityType,
      bulkHandlers,
      handlers,
      i18nPrefix,
      message,
      onBatchComplete,
      permGates,
      resolveIdFromKey,
      t,
    ],
  );

  const auditModal = hubSession && auditEntity ? (
    <UniAuditModal
      open
      mode="hub"
      hubTitle={
        hubSession.intent === 'detail'
          ? t(`${i18nPrefix}.detail`)
          : t('components.uniAction.audit')
      }
      entityName={auditEntity.entityName}
      documentCode={resolveRecordDocumentCode(hubSession.record)}
      entityType={auditEntity.entityType}
      entityId={hubSession.id}
      hubActions={hubActions}
      rbacAllowed={canReview}
      onCancel={closeHub}
      onAction={handleHubAction}
    />
  ) : null;

  return { runAction, auditModal, openAuditDetail };
}

export function buildAuditBatchMenuItems<T extends { id?: number }>(
  options: BuildAuditBatchMenuItemsOptions<T> & {
    selectedRowKeys: React.Key[];
    auditEnabled?: boolean;
    runAction: (
      action: AuditBatchAction,
      keys: React.Key[],
      records: T[],
      auditEnabled: boolean,
    ) => Promise<void>;
    t: (key: string) => string;
  },
): UniBatchMenuItem[] {
  const {
    selectedRecords = [],
    auditEnabled = false,
    permGates,
    handlers = {},
    bulkHandlers = {},
    extraMenuItems = [],
    i18nPrefix = 'components.uniBatch.audit',
    runAction,
    t,
  } = options;

  const iconByAction: Record<AuditBatchAction, React.ReactNode> = {
    submit: <SendOutlined />,
    withdraw: <RollbackOutlined />,
    approve: <CheckOutlined />,
    revoke: <UndoOutlined />,
  };

  // 固定四项菜单（与 document-action-contract / 行级 UniWorkflowActions 对称）；
  // 是否展示由 handlers 声明，是否可点由 capabilities + RBAC 门控，禁止用 auditEnabled 隐藏菜单项。
  const actionsToBuild: AuditBatchAction[] = ['submit', 'withdraw', 'approve', 'revoke'];

  const items: UniBatchMenuItem[] = [];

  for (const action of actionsToBuild) {
    const handler = handlers[action];
    const bulkHandler = bulkHandlers?.[action];
    if (!handler && !bulkHandler) continue;

    const capKey = DEFAULT_AUDIT_BATCH_CAPABILITY_KEYS[action];
    const permAction = DEFAULT_AUDIT_BATCH_PERMISSION_ACTIONS[action];
    const canPerm = permGates.canAction?.(permAction) ?? false;

    const disabled =
      selectedRecords.length > 0 &&
      !defaultAuditBatchAllowed(selectedRecords, canPerm, capKey, (r) => r);

    items.push({
      key: action,
      label: t(`${i18nPrefix}.${action}`),
      icon: iconByAction[action],
      disabled,
      onClick: (keys) => runAction(action, keys, selectedRecords, auditEnabled),
    });
  }

  return [...items, ...extraMenuItems];
}

export interface UniAuditBatchMenuButtonProps<T extends { id?: number }>
  extends Omit<BuildAuditBatchMenuItemsOptions<T>, 'onBatchComplete'> {
  selectedRowKeys: React.Key[];
  selectedRecords: T[];
  /** @deprecated 不再用于隐藏菜单项；保留以兼容既有页面传参 */
  auditEnabled?: boolean;
  onSuccess?: () => void;
  toolBarButtonSize?: ButtonProps['size'];
  /** 有 approve handler 时必传；工具栏「审核」打开 UniAuditModal */
  auditEntity?: AuditBatchModalEntity;
}

/** 审核流批量菜单：capabilities + RBAC；挂在 UniBatchMenuButton 上 */
export function UniAuditBatchMenuButton<T extends { id?: number }>({
  selectedRowKeys,
  selectedRecords,
  auditEnabled = false,
  permGates,
  handlers,
  bulkHandlers,
  extraMenuItems,
  resolveIdFromKey,
  i18nPrefix,
  onSuccess,
  toolBarButtonSize = 'middle',
  auditEntity,
}: UniAuditBatchMenuButtonProps<T>) {
  const { t } = useTranslation();
  // 有 approve handler 却未挂 auditEntity：开发态暴露配置错误（运行时仍由 useAuditBatchRunner 拦截）
  if (
    import.meta.env.DEV
    && (handlers?.approve || bulkHandlers?.approve)
    && !auditEntity?.entityType
  ) {
    // eslint-disable-next-line no-console
    console.error(
      '[UniAuditBatchMenuButton] handlers.approve 须同时传 auditEntity，否则工具栏审核无法打开 UniAuditModal',
    );
  }
  const { runAction, auditModal } = useAuditBatchRunner<T>({
    permGates,
    handlers,
    bulkHandlers,
    resolveIdFromKey,
    i18nPrefix,
    onBatchComplete: onSuccess,
    selectedRecords,
    auditEntity,
  });

  const menuItems = useMemo(
    () =>
      buildAuditBatchMenuItems({
        selectedRowKeys,
        selectedRecords,
        auditEnabled,
        permGates,
        handlers,
        bulkHandlers,
        extraMenuItems,
        i18nPrefix,
        runAction,
        t,
        auditEntity,
      }),
    [
      selectedRowKeys,
      selectedRecords,
      auditEnabled,
      permGates,
      handlers,
      bulkHandlers,
      extraMenuItems,
      i18nPrefix,
      runAction,
      t,
      auditEntity,
    ],
  );

  if (menuItems.length === 0) {
    return null;
  }

  return (
    <>
      <UniBatchMenuButton
        selectedRowKeys={selectedRowKeys}
        menuItems={menuItems}
        toolBarButtonSize={toolBarButtonSize}
      />
      {auditModal}
    </>
  );
}
