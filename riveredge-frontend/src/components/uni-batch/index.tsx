/**
 * uni-batch：列表批量操作统一入口（不限于删除）。
 *
 * 推荐组合：
 * - `UniBatchDeleteButton` — 独立删除（带确认；工具栏文案统一「删除」，禁止「批量删除」）
 * - `UniBatchMenuButton` — 其它批量能力收拢到一个下拉按钮；保存/提交拆分页传
 *   `documentCommitAndSubmitReview` 即可自动出现「直接提交审核」（勿逐页手写该项）
 * - `UniAuditBatchMenuButton` — 审核流批量（提交/撤回/审核/反审），与行级 UniWorkflowActions 对称
 * - `UniBatchSplitToolbar` — 上述两者并排（兼容旧页，内部已按新形态拆分）
 *
 * 任意「依赖选中行」的批量能力可共用 `UniBatchButton` 基座。
 */

import React from 'react';
import { App, Button, Dropdown, Popconfirm, Space } from 'antd';
import type { ButtonProps, MenuProps, PopconfirmProps } from 'antd';
import { DeleteOutlined, DownOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { ActionConfirmPopconfirm } from '../action-confirm';
import {
  withDocumentSubmitCombinedItem,
  type DocumentCommitAndSubmitReviewOptions,
} from './commitAndSubmitReview';
import {
  getAuditDetailMenuOpener,
  isAuditToolbarMenu,
} from './auditDetailMenuBridge';

export type UniBatchButtonProps = Omit<ButtonProps, 'onClick' | 'disabled'> & {
  selectedRowKeys: React.Key[];
  /** 对当前选中行执行操作（确认后或点击后直接调用） */
  onAction: (keys: React.Key[]) => void | Promise<void>;
  /** 覆盖禁用态；未传时由 disableWhenEmpty 与选中行数决定 */
  disabled?: boolean;
  /** 未显式设置 disabled 时，是否在无选中行时禁用按钮，默认 true */
  disableWhenEmpty?: boolean;
  /** 是否在操作前弹出确认框 */
  requireConfirm?: boolean;
  confirmTitle?: React.ReactNode | ((count: number) => React.ReactNode);
  confirmDescription?: React.ReactNode | ((count: number) => React.ReactNode);
  okText?: string;
  cancelText?: string;
  okButtonProps?: PopconfirmProps['okButtonProps'];
  cancelButtonProps?: PopconfirmProps['cancelButtonProps'];
};

export const UniBatchButton: React.FC<UniBatchButtonProps> = ({
  selectedRowKeys,
  onAction,
  disabled: disabledProp,
  disableWhenEmpty = true,
  requireConfirm = false,
  confirmTitle,
  confirmDescription,
  okText,
  cancelText,
  okButtonProps,
  cancelButtonProps,
  children,
  ...buttonProps
}) => {
  const { t } = useTranslation();
  const count = selectedRowKeys.length;
  const emptyDisabled = disableWhenEmpty && count === 0;
  const disabled = disabledProp ?? emptyDisabled;

  const run = () => void onAction(selectedRowKeys);

  const title =
    typeof confirmTitle === 'function' ? confirmTitle(count) : confirmTitle;
  const description =
    typeof confirmDescription === 'function'
      ? confirmDescription(count)
      : confirmDescription;

  const button = (
    <Button
      {...buttonProps}
      disabled={disabled}
      onClick={requireConfirm ? undefined : run}
    >
      {children}
    </Button>
  );

  if (!requireConfirm) {
    return button;
  }

  return (
    <Popconfirm
      title={title}
      description={description}
      onConfirm={run}
      okText={okText ?? t('common.confirm')}
      cancelText={cancelText ?? t('common.cancel')}
      okButtonProps={okButtonProps}
      cancelButtonProps={cancelButtonProps}
      disabled={disabled}
    >
      {button}
    </Popconfirm>
  );
};

export interface UniBatchDeleteButtonProps {
  selectedRowKeys: React.Key[];
  onConfirm: (keys: React.Key[]) => void | Promise<void>;
  toolBarButtonSize?: ButtonProps['size'];
  buttonText?: string;
  confirmTitle?: string | ((count: number) => string);
  confirmDescription?: string | ((count: number) => string);
  /** 业务态不可删除时置灰（无选中行时仍由 disableWhenEmpty 处理） */
  disabled?: boolean;
}

export const UniBatchDeleteButton: React.FC<UniBatchDeleteButtonProps> = ({
  selectedRowKeys,
  onConfirm,
  toolBarButtonSize = 'middle',
  buttonText,
  confirmTitle,
  confirmDescription,
  disabled: disabledProp,
}) => {
  const { t } = useTranslation();
  const count = selectedRowKeys.length;
  return (
    <UniBatchButton
      selectedRowKeys={selectedRowKeys}
      onAction={onConfirm}
      type="default"
      danger
      icon={<DeleteOutlined />}
      size={toolBarButtonSize}
      disabled={disabledProp}
      requireConfirm
      confirmTitle={
        typeof confirmTitle === 'function'
          ? confirmTitle
          : (confirmTitle ?? t('common.confirmBatchDelete'))
      }
      confirmDescription={
        typeof confirmDescription === 'function'
          ? confirmDescription
          : (confirmDescription ??
            t('common.confirmBatchDeleteContent', { count }))
      }
      okButtonProps={{ danger: true }}
    >
      {buttonText ?? t('common.delete')}
    </UniBatchButton>
  );
};

export type UniBatchMenuItem = {
  key: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  /** 点击菜单项；默认传入当前 selectedRowKeys */
  onClick: (keys: React.Key[]) => void | Promise<void>;
  disabled?: boolean;
  requireConfirm?: boolean;
  confirmTitle?: React.ReactNode | ((count: number) => React.ReactNode);
  confirmDescription?: React.ReactNode | ((count: number) => React.ReactNode);
};

export type UniBatchDocumentCommitAndSubmitReviewProp<T extends { id?: number } = { id?: number }> =
  Omit<DocumentCommitAndSubmitReviewOptions<T>, 't' | 'message'>;

export interface UniBatchMenuButtonProps<T extends { id?: number } = { id?: number }> {
  selectedRowKeys: React.Key[];
  menuItems: UniBatchMenuItem[];
  toolBarButtonSize?: ButtonProps['size'];
  buttonText?: string;
  disabled?: boolean;
  /**
   * 保存/提交拆分页：传入后，若菜单已有 submit + submit-review，自动插入「直接提交审核」。
   * 合一步文案/次序只认 uni-batch 真源，页面禁止手写该项。
   */
  documentCommitAndSubmitReview?: UniBatchDocumentCommitAndSubmitReviewProp<T>;
}

/** 批量操作下拉：与 `UniBatchDeleteButton` 并列，承载除删除外的批量能力 */
export const UniBatchMenuButton = <T extends { id?: number } = { id?: number }>({
  selectedRowKeys,
  menuItems,
  toolBarButtonSize = 'middle',
  buttonText,
  disabled: disabledProp,
  documentCommitAndSubmitReview,
}: UniBatchMenuButtonProps<T>) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [open, setOpen] = React.useState(false);
  /** 需确认的菜单项：确认气泡挂在触发按钮上（Dropdown 内嵌 Popconfirm 会随菜单关闭被卸载 → 点了没反应） */
  const [pendingConfirm, setPendingConfirm] = React.useState<UniBatchMenuItem | null>(null);

  const resolvedMenuItems = React.useMemo(() => {
    let items = menuItems;
    if (documentCommitAndSubmitReview) {
      const hasSubmit = items.some((it) => it.key === 'submit');
      const hasSubmitReview = items.some((it) => it.key === 'submit-review');
      if (hasSubmit && hasSubmitReview) {
        items = withDocumentSubmitCombinedItem(items, {
          ...documentCommitAndSubmitReview,
          t,
          message,
        });
      }
    }
    // 审核工具栏：组件级追加「审核详情」（查看整体流程进度），页面禁止手写平行项
    if (isAuditToolbarMenu(items) && !items.some((it) => it.key === 'audit-detail')) {
      items = [
        ...items,
        {
          key: 'audit-detail',
          label: t('components.uniBatch.audit.detail'),
          disabled: selectedRowKeys.length !== 1,
          onClick: (keys) => {
            const opener = getAuditDetailMenuOpener();
            if (!opener) {
              message.warning(t('components.uniBatch.audit.detailUnavailable'));
              return;
            }
            opener.openFromKeys(keys);
          },
        },
      ];
    }
    return items;
  }, [documentCommitAndSubmitReview, menuItems, message, selectedRowKeys.length, t]);

  const count = selectedRowKeys.length;
  const emptyDisabled = count === 0 || resolvedMenuItems.length === 0;
  const disabled = disabledProp ?? emptyDisabled;

  // 批量成功后会清空选中 → Dropdown disabled；受控关闭，避免浮层挂住不消失
  React.useEffect(() => {
    if (disabled) {
      setOpen(false);
      setPendingConfirm(null);
    }
  }, [disabled]);

  const closeThenRun = React.useCallback((run: () => void) => {
    setOpen(false);
    run();
  }, []);

  const dropdownMenu: MenuProps = {
    items: resolvedMenuItems.map((it) => {
      const run = () => void it.onClick(selectedRowKeys);
      return {
        key: it.key,
        icon: it.icon,
        label: it.label,
        disabled: it.disabled ?? disabled,
        onClick: () => {
          if (it.requireConfirm) {
            setOpen(false);
            setPendingConfirm(it);
            return;
          }
          closeThenRun(run);
        },
      };
    }),
  };

  const pendingTitle =
    typeof pendingConfirm?.confirmTitle === 'function'
      ? pendingConfirm.confirmTitle(count)
      : pendingConfirm?.confirmTitle;
  const pendingDescription =
    typeof pendingConfirm?.confirmDescription === 'function'
      ? pendingConfirm.confirmDescription(count)
      : pendingConfirm?.confirmDescription;

  const triggerButton = (
    <Button type="default" disabled={disabled} size={toolBarButtonSize}>
      {buttonText ?? t('components.uniBatch.batchActions')}
      <DownOutlined style={{ fontSize: 10, marginLeft: 4, opacity: 0.75 }} />
    </Button>
  );

  return (
    <ActionConfirmPopconfirm
      open={pendingConfirm != null}
      title={pendingTitle}
      description={pendingDescription}
      onConfirm={() => {
        const item = pendingConfirm;
        setPendingConfirm(null);
        if (item) void item.onClick(selectedRowKeys);
      }}
      onCancel={() => setPendingConfirm(null)}
      onOpenChange={(next) => {
        if (!next) setPendingConfirm(null);
      }}
    >
      <Dropdown
        menu={dropdownMenu}
        trigger={['click']}
        disabled={disabled || pendingConfirm != null}
        open={open}
        onOpenChange={(next) => {
          if (disabled || pendingConfirm != null) {
            setOpen(false);
            return;
          }
          setOpen(next);
        }}
      >
        {/* Popconfirm 需要可点击子节点；Dropdown 触发器包一层 span 以免受控 open 冲突 */}
        <span style={{ display: 'inline-block' }}>{triggerButton}</span>
      </Dropdown>
    </ActionConfirmPopconfirm>
  );
};

/** @deprecated 请优先使用 `UniBatchDeleteButton` + `UniBatchMenuButton` 并列 */
export type UniBatchSplitMenuItem = UniBatchMenuItem;

export interface UniBatchSplitToolbarProps {
  selectedRowKeys: React.Key[];
  onDelete: (keys: React.Key[]) => void | Promise<void>;
  /** 下拉中的其它批量操作（不含删除） */
  menuItems?: UniBatchSplitMenuItem[];
  toolBarButtonSize?: ButtonProps['size'];
  deleteButtonText?: string;
  menuButtonText?: string;
  confirmTitle?: string | ((count: number) => string);
  confirmDescription?: string | ((count: number) => string);
}

/**
 * 批量操作工具条：左侧独立删除 + 右侧批量操作下拉（uni-batch 推荐形态）。
 */
export const UniBatchSplitToolbar: React.FC<UniBatchSplitToolbarProps> = ({
  selectedRowKeys,
  onDelete,
  menuItems = [],
  toolBarButtonSize = 'middle',
  deleteButtonText,
  menuButtonText,
  confirmTitle,
  confirmDescription,
}) => {
  return (
    <Space size={8}>
      <UniBatchDeleteButton
        selectedRowKeys={selectedRowKeys}
        onConfirm={onDelete}
        toolBarButtonSize={toolBarButtonSize}
        buttonText={deleteButtonText}
        confirmTitle={confirmTitle}
        confirmDescription={confirmDescription}
      />
      {menuItems.length > 0 ? (
        <UniBatchMenuButton
          selectedRowKeys={selectedRowKeys}
          menuItems={menuItems}
          toolBarButtonSize={toolBarButtonSize}
          buttonText={menuButtonText}
        />
      ) : null}
    </Space>
  );
};

export {
  createUniAuditBatchHandlers,
} from './createUniAuditBatchHandlers';
export {
  UniAuditBatchMenuButton,
  DEFAULT_AUDIT_BATCH_CAPABILITY_KEYS,
  DEFAULT_AUDIT_BATCH_PERMISSION_ACTIONS,
  buildAuditBatchMenuItems,
  defaultAuditBatchAllowed,
  pickCapability,
  useAuditBatchRunner,
} from './auditBatchMenu';
export type {
  AuditBatchAction,
  AuditBatchCapabilityKeys,
  AuditBatchHandlers,
  AuditBatchModalEntity,
  BulkAuditBatchHandlers,
  BulkAuditBatchResult,
  BuildAuditBatchMenuItemsOptions,
  UniAuditBatchMenuButtonProps,
} from './auditBatchMenu';
export {
  UniCapabilityBatchButton,
  runCapabilityBatchLoop,
  runCapabilityBatchBulk,
} from './capabilityBatchButton';
export type {
  BulkCapabilityResult,
  CapabilityBatchLabels,
  UniCapabilityBatchButtonProps,
} from './capabilityBatchButton';
export {
  buildCommitAndSubmitReviewMenuItem,
  buildDocumentSubmitMenuItems,
  insertCommitAndSubmitReviewMenuItem,
  runCommitThenSubmitReviewBatch,
  withDocumentSubmitCombinedItem,
} from './commitAndSubmitReview';
export type {
  BuildDocumentSubmitMenuItemsOptions,
  CommitAndSubmitReviewBatchOptions,
  DocumentCommitAndSubmitReviewOptions,
} from './commitAndSubmitReview';
