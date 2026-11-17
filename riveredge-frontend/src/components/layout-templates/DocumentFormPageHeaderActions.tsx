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
  /** 保存只落草稿，另显示「提交」写成已提交。不影响未传入的页面。 */
  showCommitSubmit?: boolean;
  onCommitSubmit?: () => void;
  commitSubmitLoading?: boolean;
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
  commitSubmitLoading = false,
}: DocumentFormPageHeaderActionsProps) {
  const { t } = useTranslation();

  const draftLabel =
    saveDraftLabel ??
    (isCreatePage
      ? t('components.layoutTemplates.documentFormPage.saveDraft')
      : t('common.save'));

  const primaryLabel = canSubmitAfterSave
    ? isCreatePage
      ? primaryCreateLabel ?? t('common.save')
      : primarySubmitLabel ?? t('components.layoutTemplates.documentFormPage.saveAndSubmit')
    : primarySaveLabel ?? t('common.save');

  if (showCommitSubmit) {
    return (
      <Space wrap>
        <Button onClick={onCancel}>{t('common.cancel')}</Button>
        <Button type="primary" loading={saveDraftLoading} onClick={onSaveDraft}>
          {t('common.save')}
          {SUBMIT_SHORTCUT_HINT}
        </Button>
        <Button loading={commitSubmitLoading} onClick={onCommitSubmit}>
          {t('common.submit')}
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
