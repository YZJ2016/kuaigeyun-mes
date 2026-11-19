/**
 * 同步/推送组合弹窗：页内 Tabs 为「入站方向」「出站方向」「同步对比」「同步记录」。
 *
 * 面板内容故意放在 Tabs 外：antd Tabs 的 items 每次父级重渲染都会换新引用，
 * 若把 DocumentPushBatchPanel / SyncFromSource 放进 items[].children，
 * 会在 Hub 打开期间反复挂载 → profiles + /core/apis 请求风暴。
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Modal, Tabs } from 'antd';
import { useTranslation } from 'react-i18next';
import { SyncRunHistoryPanel } from './SyncRunHistoryPanel';
import { SyncReconcilePanel } from './SyncReconcilePanel';
import { supportsDocumentPushReconcile } from './reconcileSourceTypes';

export type SyncPushHubTabKey = 'sync' | 'push' | 'reconcile' | 'history';

export interface SyncPushHubPanelContext {
  active: boolean;
  close: () => void;
}

export interface SyncPushHubModalProps {
  open: boolean;
  onClose: () => void;
  syncEnabled?: boolean;
  pushEnabled?: boolean;
  /** 传入 sourceType 即展示「同步记录」Tab（内置 SyncRunHistoryPanel） */
  historySourceType?: string;
  historyTargetProfiles?: string[];
  historyEnabled?: boolean;
  /**
   * 同步对比：返回当前页或勾选的本地单据 ID。
   * 页签是否出现由 historySourceType 是否支持组件级对比决定；本函数只负责供数。
   */
  getReconcileDocumentIds?: () => number[];
  reconcileEnabled?: boolean;
  syncTitle?: React.ReactNode;
  pushTitle?: React.ReactNode;
  reconcileTitle?: React.ReactNode;
  historyTitle?: React.ReactNode;
  title?: React.ReactNode;
  width?: number | string;
  zIndex?: number;
  defaultTab?: SyncPushHubTabKey;
  renderSyncPanel?: (ctx: SyncPushHubPanelContext) => React.ReactNode;
  renderPushPanel?: (ctx: SyncPushHubPanelContext) => React.ReactNode;
  renderReconcilePanel?: (ctx: SyncPushHubPanelContext) => React.ReactNode;
  renderHistoryPanel?: (ctx: SyncPushHubPanelContext) => React.ReactNode;
  syncPanel?: React.ReactNode;
  pushPanel?: React.ReactNode;
  reconcilePanel?: React.ReactNode;
  historyPanel?: React.ReactNode;
}

export const SyncPushHubModal: React.FC<SyncPushHubModalProps> = ({
  open,
  onClose,
  syncEnabled = true,
  pushEnabled = true,
  historySourceType,
  historyTargetProfiles,
  historyEnabled = true,
  getReconcileDocumentIds,
  reconcileEnabled = true,
  syncTitle,
  pushTitle,
  reconcileTitle,
  historyTitle,
  title,
  width = 1100,
  zIndex,
  defaultTab,
  renderSyncPanel,
  renderPushPanel,
  renderReconcilePanel,
  renderHistoryPanel,
  syncPanel,
  pushPanel,
  reconcilePanel,
  historyPanel,
}) => {
  const { t } = useTranslation();
  // 无面板内容时不展示对应 Tab，避免配置误开 push 后出现空页
  const showSync = Boolean(syncEnabled) && Boolean(renderSyncPanel || syncPanel);
  const showPush = Boolean(pushEnabled) && Boolean(renderPushPanel || pushPanel);
  const historySource = String(historySourceType || '').trim();
  const builtInHistory = Boolean(historyEnabled) && Boolean(historySource);
  const showHistory =
    Boolean(historyEnabled) &&
    Boolean(renderHistoryPanel || historyPanel || builtInHistory);
  const builtInReconcile =
    Boolean(reconcileEnabled) && supportsDocumentPushReconcile(historySource);
  const showReconcile =
    Boolean(reconcileEnabled) &&
    Boolean(renderReconcilePanel || reconcilePanel || builtInReconcile);
  const resolveReconcileIds =
    typeof getReconcileDocumentIds === 'function'
      ? getReconcileDocumentIds
      : () => [] as number[];

  const initialTab = useMemo<SyncPushHubTabKey>(() => {
    if (defaultTab === 'sync' && showSync) return 'sync';
    if (defaultTab === 'push' && showPush) return 'push';
    if (defaultTab === 'reconcile' && showReconcile) return 'reconcile';
    if (defaultTab === 'history' && showHistory) return 'history';
    if (showSync) return 'sync';
    if (showPush) return 'push';
    if (showReconcile) return 'reconcile';
    return 'history';
  }, [defaultTab, showHistory, showPush, showReconcile, showSync]);

  const [activeKey, setActiveKey] = useState<SyncPushHubTabKey>(initialTab);
  // 默认 false：配合 Button「仅 open 时挂载 Modal」，首开帧 openingEdge=true，避免沿用错误 Tab
  const [lastOpen, setLastOpen] = useState(false);
  const openingEdge = open && !lastOpen;

  // 打开边沿：在子树 commit 前重置 activeKey。
  // 若仅用 useEffect，首帧会沿用上次 Tab（常为 push），导致 DocumentPushBatchPanel
  // 与 SyncFromSource 同帧挂载，打出 profiles + /core/apis 请求风暴。
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setActiveKey(initialTab);
    }
  }

  useEffect(() => {
    if (!open) return;
    if (activeKey === 'sync' && !showSync) {
      setActiveKey(showPush ? 'push' : showReconcile ? 'reconcile' : 'history');
    } else if (activeKey === 'push' && !showPush) {
      setActiveKey(showSync ? 'sync' : showReconcile ? 'reconcile' : 'history');
    } else if (activeKey === 'reconcile' && !showReconcile) {
      setActiveKey(showSync ? 'sync' : showPush ? 'push' : 'history');
    } else if (activeKey === 'history' && !showHistory) {
      setActiveKey(showSync ? 'sync' : showPush ? 'push' : 'reconcile');
    }
  }, [activeKey, open, showHistory, showPush, showReconcile, showSync]);

  const tabItems = useMemo(
    () =>
      (
        [
          showSync
            ? {
                key: 'sync' as const,
                label: syncTitle ?? t('components.syncPushHub.tabSync'),
              }
            : null,
          showPush
            ? {
                key: 'push' as const,
                label: pushTitle ?? t('components.syncPushHub.tabPush'),
              }
            : null,
          showReconcile
            ? {
                key: 'reconcile' as const,
                label: reconcileTitle ?? t('components.syncPushHub.tabReconcile'),
              }
            : null,
          showHistory
            ? {
                key: 'history' as const,
                label: historyTitle ?? t('components.syncPushHub.tabHistory'),
              }
            : null,
        ] as Array<{ key: SyncPushHubTabKey; label: React.ReactNode } | null>
      ).filter(Boolean) as Array<{ key: SyncPushHubTabKey; label: React.ReactNode }>,
    [
      historyTitle,
      pushTitle,
      reconcileTitle,
      showHistory,
      showPush,
      showReconcile,
      showSync,
      syncTitle,
      t,
    ],
  );

  if (!showSync && !showPush && !showReconcile && !showHistory) return null;

  const close = () => {
    onClose();
  };

  // 打开边沿用 initialTab 挂载面板，避免与尚未 flush 的 activeKey 不一致
  const panelTab: SyncPushHubTabKey = openingEdge ? initialTab : activeKey;
  const syncActive = open && panelTab === 'sync';
  const pushActive = open && panelTab === 'push';
  const reconcileActive = open && panelTab === 'reconcile';
  const historyActive = open && panelTab === 'history';

  return (
    <Modal
      title={title ?? t('components.syncPushHub.title')}
      open={open}
      onCancel={close}
      footer={null}
      width={width}
      zIndex={zIndex}
      destroyOnHidden
      styles={{ body: { paddingTop: 8 } }}
    >
      {/* open=false 时不创建面板（含 render* 调用），防止列表页/关闭态误打 profiles/apis */}
      {open ? (
        <>
          <Tabs
            activeKey={panelTab}
            onChange={(key) => setActiveKey(key as SyncPushHubTabKey)}
            items={tabItems}
          />
          <div style={{ marginTop: 4 }}>
            {/* 仅挂载当前 Tab；active 必须反映真实状态，禁止写死 true */}
            {syncActive
              ? renderSyncPanel
                ? renderSyncPanel({ active: syncActive, close })
                : syncPanel
              : null}
            {pushActive
              ? renderPushPanel
                ? renderPushPanel({ active: pushActive, close })
                : pushPanel
              : null}
            {reconcileActive
              ? renderReconcilePanel
                ? renderReconcilePanel({ active: reconcileActive, close })
                : reconcilePanel
                  ? reconcilePanel
                  : builtInReconcile
                    ? (
                        <SyncReconcilePanel
                          active={reconcileActive}
                          sourceType={historySource}
                          getDocumentIds={resolveReconcileIds}
                        />
                      )
                    : null
              : null}
            {historyActive
              ? renderHistoryPanel
                ? renderHistoryPanel({ active: historyActive, close })
                : historyPanel
                  ? historyPanel
                  : builtInHistory
                    ? (
                        <SyncRunHistoryPanel
                          active={historyActive}
                          sourceType={historySource}
                          targetProfiles={historyTargetProfiles}
                        />
                      )
                    : null
              : null}
          </div>
        </>
      ) : null}
    </Modal>
  );
};

export default SyncPushHubModal;
