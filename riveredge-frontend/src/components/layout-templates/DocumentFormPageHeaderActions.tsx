/**
 * 单据独立新建/编辑页顶栏操作区（取消 - 保存草稿/保存 - 创建/保存并提交）。
 * 文案真源：components.layoutTemplates.documentFormPage.*
 */
import { Button, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { SUBMIT_SHORTCUT_HINT } from '../../utils/globalSubmitShortcut';

export interface DocumentFormPageHeaderActionsProps {
  onCancel: () => void;
  onSaveDraft: () => void;
  onPrimarySubmit: () => void;
  isCreatePage: boolean;
  /** 是否显示中间「保存为草稿/保存」按钮，默认 true */
  showSaveDraft?: boolean;
  /** 新建页恒为 true；编辑页通常仅草稿态为 true */
  canSubmitAfterSave?: boolean;
  saveDraftLabel?: string;
  primaryCreateLabel?: string;
  primarySubmitLabel?: string;
  primarySaveLabel?: string;
  primaryLoading?: boolean;
  saveDraftLoading?: boolean;
  /**
   * 保存草稿 + 保存并审核（commit → submit_review）。
   * onSaveAndAudit 优先；未传时沿用 onCommitSubmit。
   */
  showCommitSubmit?: boolean;
  /** @deprecated 使用 onSaveAndAudit */
  onCommitSubmit?: () => void;
  onSaveAndAudit?: () => void;
  commitSubmitLoading?: boolean;
  saveAndAuditLoading?: boolean;
}

export function DocumentFormPageHeaderActions({
  onCancel,
  onSaveDraft,
  onPrimarySubmit,
  isCreatePage,
  showSaveDraft = true,
  canSubmitAfterSave = true,
  saveDraftLabel,
  primaryCreateLabel,
  primarySubmitLabel,
  primarySaveLabel,
  primaryLoading = false,
  saveDraftLoading = false,
  showCommitSubmit = false,
  onCommitSubmit,
  onSaveAndAudit,
  commitSubmitLoading = false,
  saveAndAuditLoading,
}: DocumentFormPageHeaderActionsProps) {
  const { t } = useTranslation();
  const auditHandler = onSaveAndAudit ?? onCommitSubmit;
  const auditLoading = saveAndAuditLoading ?? commitSubmitLoading;

  const draftLabel =
    saveDraftLabel ?? t('components.layoutTemplates.documentFormPage.saveDraft');

  const primaryLabel = canSubmitAfterSave
    ? isCreatePage
      ? primaryCreateLabel ?? t('common.save')
      : primarySubmitLabel ?? t('components.layoutTemplates.documentFormPage.saveAndSubmit')
    : primarySaveLabel ?? t('common.save');

  if (showCommitSubmit) {
    return (
      <Space wrap>
        <Button onClick={onCancel}>{t('common.cancel')}</Button>
        <Button loading={saveDraftLoading} onClick={onSaveDraft}>
          {draftLabel}
          {SUBMIT_SHORTCUT_HINT}
        </Button>
        <Button type="primary" loading={auditLoading} onClick={auditHandler}>
          {t('components.layoutTemplates.documentFormPage.saveAndAudit')}
        </Button>
      </Space>
    );
  }

  return (
    <Space wrap>
      <Button onClick={onCancel}>{t('common.cancel')}</Button>
      {showSaveDraft ? (
        <Button loading={saveDraftLoading} onClick={onSaveDraft}>
          {draftLabel}
        </Button>
      ) : null}
      <Button type="primary" loading={primaryLoading} onClick={onPrimarySubmit}>
        {primaryLabel}
        {SUBMIT_SHORTCUT_HINT}
      </Button>
    </Space>
  );
}
