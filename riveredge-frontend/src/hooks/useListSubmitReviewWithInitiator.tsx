/**
 * 列表「提交审核」：逐条拉 submit-initiator-nodes，需要时弹 UniAuditInitiatorSubmitModal 再 submit_review。
 */
import { useCallback, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App } from 'antd';
import UniAuditInitiatorSubmitModal from '../components/uni-audit/UniAuditInitiatorSubmitModal';
import {
  fetchSubmitInitiatorRequirements,
  postSubmitReview,
  type HierarchyDepartmentOption,
  type SubmitInitiatorBranchHint,
  type SubmitInitiatorNodeHint,
} from '../services/uniAudit';
import { getApiErrorMessage } from '../utils/errorHandler';
import {
  SubmitReviewUserCancelledError,
} from '../utils/submitReviewUserCancelled';

export { SubmitReviewUserCancelledError } from '../utils/submitReviewUserCancelled';

export type ListSubmitReviewWithInitiatorOptions = {
  entityType: string;
  entityLabel: string;
  submitTitle: string;
  submitReview?: (id: number, payload?: Record<string, unknown>) => Promise<unknown>;
};

export function useListSubmitReviewWithInitiator(options: ListSubmitReviewWithInitiatorOptions) {
  const { message: messageApi } = App.useApp();
  const { t } = useTranslation();
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const pendingIdRef = useRef<number | null>(null);
  const modalWaiterRef = useRef<((outcome: 'confirmed' | 'cancelled') => void) | null>(null);
  const modalOutcomeRef = useRef<{ ok: boolean; value?: unknown; error?: unknown } | null>(null);

  const [initiatorOpen, setInitiatorOpen] = useState(false);
  const [initiatorLoading, setInitiatorLoading] = useState(false);
  const [initiatorNodes, setInitiatorNodes] = useState<SubmitInitiatorNodeHint[]>([]);
  const [initiatorBranches, setInitiatorBranches] = useState<SubmitInitiatorBranchHint[]>([]);
  const [hierarchyRequired, setHierarchyRequired] = useState(false);
  const [hierarchyOptions, setHierarchyOptions] = useState<HierarchyDepartmentOption[]>([]);
  const [defaultHierarchyUuid, setDefaultHierarchyUuid] = useState<string | null>(null);

  const runSubmitReviewWithInitiator = useCallback(async (id: number): Promise<unknown> => {
    const { entityType, submitReview } = optionsRef.current;
    if (!Number.isFinite(id) || id <= 0) {
      throw new Error('invalid entity id');
    }
    const requirements = await fetchSubmitInitiatorRequirements(entityType, id);
    const nodes = requirements.nodes ?? [];
    const branchConditions = requirements.branch_conditions ?? [];
    const hierarchyRequiredFlag = Boolean(requirements.hierarchy_department_required);
    const hierarchyOpts = requirements.hierarchy_department_options ?? [];
    const needsHierarchy = hierarchyRequiredFlag && hierarchyOpts.length >= 2;

    const review =
      submitReview ?? ((reviewId, payload) => postSubmitReview(entityType, reviewId, payload));

    if (nodes.length === 0 && branchConditions.length === 0 && !needsHierarchy) {
      return review(id);
    }

    pendingIdRef.current = id;
    setInitiatorNodes(nodes);
    setInitiatorBranches(branchConditions);
    setHierarchyRequired(hierarchyRequiredFlag);
    setHierarchyOptions(hierarchyOpts);
    setDefaultHierarchyUuid(requirements.default_hierarchy_department_uuid ?? null);
    setInitiatorOpen(true);

    const modalOutcome = await new Promise<'confirmed' | 'cancelled'>((resolve) => {
      modalWaiterRef.current = resolve;
    });

    if (modalOutcome === 'cancelled') {
      throw new SubmitReviewUserCancelledError();
    }

    const outcome = modalOutcomeRef.current;
    modalOutcomeRef.current = null;
    if (!outcome?.ok) {
      throw outcome?.error ?? new Error('submit_review_failed');
    }
    return outcome.value;
  }, []);

  const closeInitiatorModal = useCallback(() => {
    setInitiatorOpen(false);
    pendingIdRef.current = null;
    setInitiatorLoading(false);
  }, []);

  const listInitiatorModal = (
    <UniAuditInitiatorSubmitModal
      open={initiatorOpen}
      entityName={options.entityLabel}
      submitTitle={options.submitTitle}
      nodes={initiatorNodes}
      branchConditions={initiatorBranches}
      hierarchyDepartmentRequired={hierarchyRequired}
      hierarchyDepartmentOptions={hierarchyOptions}
      defaultHierarchyDepartmentUuid={defaultHierarchyUuid}
      loading={initiatorLoading}
      onCancel={() => {
        closeInitiatorModal();
        modalWaiterRef.current?.('cancelled');
        modalWaiterRef.current = null;
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
        const { entityType, submitReview } = optionsRef.current;
        const review =
          submitReview ?? ((reviewId, payload) => postSubmitReview(entityType, reviewId, payload));
        setInitiatorLoading(true);
        try {
          const record = await review(docId, extra);
          modalOutcomeRef.current = { ok: true, value: record };
          closeInitiatorModal();
          modalWaiterRef.current?.('confirmed');
          modalWaiterRef.current = null;
        } catch (error: unknown) {
          modalOutcomeRef.current = { ok: false, error };
          messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
          modalWaiterRef.current?.('confirmed');
          modalWaiterRef.current = null;
        } finally {
          setInitiatorLoading(false);
        }
      }}
    />
  );

  return { runSubmitReviewWithInitiator, listInitiatorModal };
}