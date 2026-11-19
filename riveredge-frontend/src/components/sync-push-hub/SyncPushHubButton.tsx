/**
 * 工具栏「同步/推送」统一入口按钮 + Hub 弹窗。
 */
import React, { useState } from 'react';
import { Button, Tooltip } from 'antd';
import type { ButtonProps } from 'antd';
import { SyncOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import {
  SyncPushHubModal,
  type SyncPushHubModalProps,
  type SyncPushHubTabKey,
} from './SyncPushHubModal';
import { useUniTableDataActionIconOnly } from '../uni-table/dataActionIconOnlyContext';

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
  syncTitle,
  pushTitle,
  historyTitle,
  title,
  width,
  zIndex,
  defaultTab,
  renderSyncPanel,
  renderPushPanel,
  renderHistoryPanel,
  syncPanel,
  pushPanel,
  historyPanel,
  buttonText,
  iconOnly = false,
  wrapButton,
  type = 'default',
  size,
  ...buttonRest
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const toolbarIconOnly = useUniTableDataActionIconOnly();
  const effectiveIconOnly = iconOnly || toolbarIconOnly;

  const showSync = Boolean(syncEnabled) && Boolean(renderSyncPanel || syncPanel);
  const showPush = Boolean(pushEnabled) && Boolean(renderPushPanel || pushPanel);
  const historySource = String(historySourceType || '').trim();
  const showHistory =
    Boolean(historyEnabled) &&
    Boolean(renderHistoryPanel || historyPanel || historySource);
  if (!showSync && !showPush && !showHistory) return null;

  const label = buttonText ?? t('components.syncPushHub.button');
  const ariaLabel = typeof label === 'string' ? label : t('components.syncPushHub.button');
  const btn = (
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

  const wrapped = wrapButton
    ? wrapButton(btn)
    : effectiveIconOnly
      ? <Tooltip title={ariaLabel}>{btn}</Tooltip>
      : btn;

  return (
    <>
      {wrapped}
      {/* 未打开不挂载 Hub：避免列表页就执行 renderPushPanel → profiles/apis */}
      {open ? (
        <SyncPushHubModal
          open={open}
          onClose={() => setOpen(false)}
          syncEnabled={showSync}
          pushEnabled={showPush}
          historyEnabled={showHistory}
          historySourceType={historySourceType}
          historyTargetProfiles={historyTargetProfiles}
          syncTitle={syncTitle}
          pushTitle={pushTitle}
          historyTitle={historyTitle}
          title={title}
          width={width}
          zIndex={zIndex}
          defaultTab={defaultTab}
          renderSyncPanel={renderSyncPanel}
          renderPushPanel={renderPushPanel}
          renderHistoryPanel={renderHistoryPanel}
          syncPanel={syncPanel}
          pushPanel={pushPanel}
          historyPanel={historyPanel}
        />
      ) : null}
    </>
  );
};

export default SyncPushHubButton;
