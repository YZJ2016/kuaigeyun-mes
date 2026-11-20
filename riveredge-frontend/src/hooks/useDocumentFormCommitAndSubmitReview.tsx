/**
 * 表单保存并审核：persist 后 commit →（ initiator 选人）→ submit_review。
 * 免审且无 initiator 时直送审，不弹二次确认（由 uni-audit / 本 hook 保证）。
 */
import { useCallback, useRef, useState } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import UniAuditInitiatorSubmitModal from '../components/uni-audit/UniAuditInitiatorSubmitModal';
import {
  fetchSubmitInitiatorRequirements,
  postSubmitReview,
  type HierarchyDepartmentOption,
  type SubmitInitiatorBranchHint,
  type SubmitInitiatorNodeHint,
} from '../services/uniAudit';
import { getApiErrorMessage } from '../utils/errorHandler';

export type DocumentFormCommitAndSubmitReviewOptions = {
  entityType: string;
  entityLabel: string;
  commit: (id: number) => Promise<unknown>;
  /** 缺省走 uni-audit submit_review */
  submitReview?: (id: number, payload?: Record<string, unknown>) => Promise<unknown>;
  /** 送审成功（含免审通过） */
  onSuccess?: (record?: unknown) => void;
  successMessageKey?: string;
  failMessageKey?: string;
};

export function useDocumentFormCommitAndSubmitReview(
  options: DocumentFormCommitAndSubmitReviewOptions,
) {
  const { message: messageApi } = App.useApp();
  const { t } = useTranslation();
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const pendingIdRef = useRef<number | null>(null);
  const [initiatorOpen, setInitiatorOpen] = useState(false);
  const [initiatorLoading, setInitiatorLoading] = useState(false);
  const [initiatorNodes, setInitiatorNodes] = useState<SubmitInitiatorNodeHint[]>([]);
  const [initiatorBranches, setInitiatorBranches] = useState<SubmitInitiatorBranchHint[]>([]);
  const [hierarchyRequired, setHierarchyRequired] = useState(false);
  const [hierarchyOptions, setHierarchyOptions] = useState<HierarchyDepartmentOption[]>([]);
  const [defaultHierarchyUuid, setDefaultHierarchyUuid] = useState<string | null>(null);

  const runAfterPersist = useCallback(async (id: number): Promise<{ completed: boolean }> => {
    const {
      entityType,
      commit,
      submitReview,
      onSuccess,
      successMessageKey,
      failMessageKey,
    } = optionsRef.current;
    if (!Number.isFinite(id) || id <= 0) return { completed: true };
    try {
      await commit(id);
      const requirements = await fetchSubmitInitiatorRequirements(entityType, id);
      const nodes = requirements.nodes ?? [];
      const branchConditions = requirements.branch_conditions ?? [];
      const hierarchyRequiredFlag = Boolean(requirements.hierarchy_department_required);
      const hierarchyOpts = requirements.hierarchy_department_options ?? [];
      const needsHierarchy =
        hierarchyRequiredFlag && hierarchyOpts.length >= 2;
      if (nodes.length > 0 || branchConditions.length > 0 || needsHierarchy) {
        pendingIdRef.current = id;
        setInitiatorNodes(nodes);
        setInitiatorBranches(branchConditions);
        setHierarchyRequired(hierarchyRequiredFlag);
        setHierarchyOptions(hierarchyOpts);
        setDefaultHierarchyUuid(requirements.default_hierarchy_department_uuid ?? null);
        setInitiatorOpen(true);
        return { completed: false };
      }
      const review =
        submitReview ?? ((reviewId, payload) => postSubmitReview(entityType, reviewId, payload));
      await review(id);
      if (successMessageKey) {
        messageApi.success(t(successMessageKey));
      } else {
        messageApi.success(t('components.layoutTemplates.documentFormPage.saveAndAuditSuccess'));
      }
      onSuccess?.();
      return { completed: true };
    } catch (error: unknown) {
      messageApi.error(
        getApiErrorMessage(
          error,
          failMessageKey ? t(failMessageKey) : t('components.layoutTemplates.documentFormPage.saveAndAuditFailed'),
        ),
      );
      throw error;
    }
  }, [messageApi, t]);

  const initiatorModal = (
    <UniAuditInitiatorSubmitModal
      open={initiatorOpen}
      entityName={options.entityLabel}
      submitTitle={t('components.layoutTemplates.documentFormPage.saveAndAudit')}
      nodes={initiatorNodes}
      branchConditions={initiatorBranches}
      hierarchyDepartmentRequired={hierarchyRequired}
      hierarchyDepartmentOptions={hierarchyOptions}
      defaultHierarchyDepartmentUuid={defaultHierarchyUuid}
      loading={initiatorLoading}
      onCancel={() => {
        setInitiatorOpen(false);
        pendingIdRef.current = null;
      }}
      onConfirm={async (selectedByNode, branchByCondition, hierarchyDepartmentUuid) => {
        const docId = pendingIdRef.current;
        if (docId == null) return;
        const extra: Record<string, unknown> = {
          selected_approver_by_node: selectedByNode,
          initiator_branch_by_node: branchByCondition,
        };
        if (hierarchyDepartmentUuid) {
          extra.hierarchy_department_uuid = hierarchyDepartmentUuid;
        }
        setInitiatorLoading(true);
        try {
          const { entityType, submitReview } = optionsRef.current;
          const review =
            submitReview ?? ((reviewId, payload) => postSubmitReview(entityType, reviewId, payload));
          const record = await review(docId, extra);
          setInitiatorOpen(false);
          pendingIdRef.current = null;
          const { successMessageKey, onSuccess } = optionsRef.current;
          if (successMessageKey) {
            messageApi.success(t(successMessageKey));
          } else {
            messageApi.success(t('components.layoutTemplates.documentFormPage.saveAndAuditSuccess'));
          }
          onSuccess?.(record);
        } catch (error: unknown) {
          messageApi.error(
            getApiErrorMessage(
              error,
              optionsRef.current.failMessageKey
                ? t(optionsRef.current.failMessageKey)
                : t('components.layoutTemplates.documentFormPage.saveAndAuditFailed'),
            ),
          );
        } finally {
          setInitiatorLoading(false);
        }
      }}
    />
  );

  return { runAfterPersist, initiatorModal };
}
