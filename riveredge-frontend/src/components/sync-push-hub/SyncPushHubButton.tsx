/**
 * 工具栏「同步/推送」统一入口按钮 + Hub 弹窗。
 * 仓储出站绑定存在时，旁挂「暂停」：停自动无感外推，金蝶不通不撤回本地过账。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { App, Button, Space, Tooltip } from 'antd';
import type { ButtonProps } from 'antd';
import { PauseCircleOutlined, PlayCircleOutlined, SyncOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  SyncPushHubModal,
  type SyncPushHubModalProps,
  type SyncPushHubTabKey,
} from './SyncPushHubModal';
import {
  isPushBindingPaused,
  resolvePushBindingPauseApi,
  setPushBindingPaused,
} from './pushBindingPause';
import { supportsDocumentPushReconcile } from './reconcileSourceTypes';
import { useUniTableDataActionIconOnly } from '../uni-table/dataActionIconOnlyContext';
import { getApiErrorMessage } from '../../utils/errorHandler';

export interface SyncPushHubButtonProps
  extends Omit<SyncPushHubModalProps, 'open' | 'onClose'>,
    Omit<ButtonProps, 'onClick' | 'children' | 'icon'> {
  /** 覆盖默认按钮文案 */
  buttonText?: React.ReactNode;
  /** 仅图标（窄屏） */
  iconOnly?: boolean;
  /** 打开时默认 Tab */
  defaultTab?: SyncPushHubTabKey;
  /** 外层包装（如 SyncFreshnessBadge） */
  wrapButton?: (button: React.ReactElement) => React.ReactNode;
}

export const SyncPushHubButton: React.FC<SyncPushHubButtonProps> = ({
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
  width,
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
  buttonText,
  iconOnly = false,
  wrapButton,
  type = 'default',
  size,
  ...buttonRest
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [autoPushPaused, setAutoPushPaused] = useState(false);
  const [pauseLoading, setPauseLoading] = useState(false);
  const toolbarIconOnly = useUniTableDataActionIconOnly();
  const effectiveIconOnly = iconOnly || toolbarIconOnly;

  const showSync = Boolean(syncEnabled) && Boolean(renderSyncPanel || syncPanel);
  const showPush = Boolean(pushEnabled) && Boolean(renderPushPanel || pushPanel);
  const historySource = String(historySourceType || '').trim();
  const showHistory =
    Boolean(historyEnabled) &&
    Boolean(renderHistoryPanel || historyPanel || historySource);
  const showReconcile =
    Boolean(reconcileEnabled) &&
    Boolean(
      renderReconcilePanel ||
        reconcilePanel ||
        supportsDocumentPushReconcile(historySource),
    );
  const pauseApi = showPush ? resolvePushBindingPauseApi(historySource) : null;

  const reloadPauseState = useCallback(async () => {
    if (!pauseApi) {
      setAutoPushPaused(false);
      return;
    }
    try {
      const binding = await pauseApi.load();
      setAutoPushPaused(isPushBindingPaused(binding?.targets));
    } catch {
      setAutoPushPaused(false);
    }
  }, [pauseApi]);

  useEffect(() => {
    void reloadPauseState();
  }, [reloadPauseState]);

  if (!showSync && !showPush && !showReconcile && !showHistory) return null;

  const label = buttonText ?? t('components.syncPushHub.button');
  const ariaLabel = typeof label === 'string' ? label : t('components.syncPushHub.button');
  const syncBtn = (
    <Button
      type={type}
      size={size}
      icon={<SyncOutlined />}
      aria-label={ariaLabel}
      onClick={() => setOpen(true)}
      {...buttonRest}
    >
      {effectiveIconOnly ? null : label}
    </Button>
  );

  const onTogglePause = async () => {
    if (!pauseApi) return;
    setPauseLoading(true);
    try {
      const nextPaused = !autoPushPaused;
      await setPushBindingPaused(pauseApi, nextPaused);
      setAutoPushPaused(nextPaused);
      message.success(
        nextPaused
          ? t('components.syncPushHub.autoPushPaused')
          : t('components.syncPushHub.autoPushResumed'),
      );
    } catch (error: unknown) {
      if (error instanceof Error && error.message === 'NO_TARGETS') {
        message.warning(t('components.syncPushHub.autoPushPauseNeedTargets'));
      } else {
        message.error(
          getApiErrorMessage(error, t('components.syncPushHub.autoPushPauseFailed')),
        );
      }
    } finally {
      setPauseLoading(false);
    }
  };

  const pauseBtn = pauseApi ? (
    <Tooltip
      title={
        autoPushPaused
          ? t('components.syncPushHub.autoPushResumeHint')
          : t('components.syncPushHub.autoPushPauseHint')
      }
    >
      <Button
        type={autoPushPaused ? 'primary' : 'default'}
        danger={autoPushPaused}
        size={size}
        loading={pauseLoading}
        icon={autoPushPaused ? <PlayCircleOutlined /> : <PauseCircleOutlined />}
        aria-label={
          autoPushPaused
            ? t('components.syncPushHub.autoPushResume')
            : t('components.syncPushHub.autoPushPause')
        }
        onClick={() => {
          void onTogglePause();
        }}
      >
        {effectiveIconOnly
          ? null
          : autoPushPaused
            ? t('components.syncPushHub.autoPushResume')
            : t('components.syncPushHub.autoPushPause')}
      </Button>
    </Tooltip>
  ) : null;

  const group = pauseBtn ? (
    <Space.Compact size={size}>
      {effectiveIconOnly ? <Tooltip title={ariaLabel}>{syncBtn}</Tooltip> : syncBtn}
      {pauseBtn}
    </Space.Compact>
  ) : effectiveIconOnly ? (
    <Tooltip title={ariaLabel}>{syncBtn}</Tooltip>
  ) : (
    syncBtn
  );

  const wrapped = wrapButton ? wrapButton(group as React.ReactElement) : group;

  return (
    <>
      {wrapped}
      {open ? (
        <SyncPushHubModal
          open={open}
          onClose={() => {
            setOpen(false);
            void reloadPauseState();
          }}
          syncEnabled={showSync}
          pushEnabled={showPush}
          historyEnabled={showHistory}
          historySourceType={historySourceType}
          historyTargetProfiles={historyTargetProfiles}
          getReconcileDocumentIds={getReconcileDocumentIds}
          reconcileEnabled={showReconcile}
          syncTitle={syncTitle}
          pushTitle={pushTitle}
          reconcileTitle={reconcileTitle}
          historyTitle={historyTitle}
          title={title}
          width={width}
          zIndex={zIndex}
          defaultTab={defaultTab}
          renderSyncPanel={renderSyncPanel}
          renderPushPanel={renderPushPanel}
          renderReconcilePanel={renderReconcilePanel}
          renderHistoryPanel={renderHistoryPanel}
          syncPanel={syncPanel}
          pushPanel={pushPanel}
          reconcilePanel={reconcilePanel}
          historyPanel={historyPanel}
        />
      ) : null}
    </>
  );
};

export default SyncPushHubButton;
