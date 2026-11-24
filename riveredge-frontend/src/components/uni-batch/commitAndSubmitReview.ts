/**
 * 保存/提交/审核拆分页：提交下拉「直接提交审核」——先 commit 再 submit_review。
 *
 * 真源：本文件 + UniBatchMenuButton.documentCommitAndSubmitReview。
 * 页面只传 commit / submitReview / 可提交行；勿手写合一项，勿把两个菜单 onClick 串起来
 * （草稿时 submit_review 行集为空）。
 */

import type { TFunction } from 'i18next';
import type React from 'react';
import { getApiErrorMessage } from '../../utils/errorHandler';
import { isSubmitReviewUserCancelled } from '../../utils/submitReviewUserCancelled';
import type { UniBatchMenuItem } from './index';

export type CommitAndSubmitReviewBatchOptions<T extends { id?: number }> = {
  keys: React.Key[];
  /** 可「提交」的行（草稿/已驳回等） */
  commitRecords: T[];
  permAllowed: boolean;
  resolveId?: (key: React.Key, record: T | undefined) => number | null;
  commit: (id: number) => Promise<unknown>;
  submitReview: (id: number) => Promise<unknown>;
  notAllowedMessage?: string;
  onSuccess?: () => void;
  message: { success: (content: string) => void; warning: (content: string) => void };
  t: TFunction;
};

export type DocumentCommitAndSubmitReviewOptions<T extends { id?: number }> = {
  t: TFunction;
  message: CommitAndSubmitReviewBatchOptions<T>['message'];
  /** 与「提交」项 disabled 对齐：有选中且无可提交行时禁用合一步 */
  disabled: boolean;
  commitRecords: T[];
  permAllowed: boolean;
  commit: (id: number) => Promise<unknown>;
  submitReview: (id: number) => Promise<unknown>;
  resolveId?: (key: React.Key, record: T | undefined) => number | null;
  onSuccess?: () => void;
  notAllowedMessage?: string;
};

/**
 * 对可提交行：逐条 commit → submit_review。
 * 已是已提交、仅缺送审的行请继续用「提交审核」，不要走本合一步。
 */
export async function runCommitThenSubmitReviewBatch<T extends { id?: number }>(
  options: CommitAndSubmitReviewBatchOptions<T>,
): Promise<void> {
  const {
    keys,
    commitRecords,
    permAllowed,
    resolveId,
    commit,
    submitReview,
    notAllowedMessage,
    onSuccess,
    message,
    t,
  } = options;

  const eligibleIds: number[] = [];
  const seen = new Set<number>();
  for (const key of keys) {
    // 与 runCapabilityBatchLoop 一致：先 resolve 复合 rowKey，再按业务 id 命中可提交行
    const resolved = resolveId
      ? resolveId(key, commitRecords.find((r) => String(r.id) === String(key)))
      : Number(key);
    const id = resolved == null ? NaN : Number(resolved);
    if (!Number.isFinite(id) || id <= 0 || seen.has(id)) continue;
    const record = commitRecords.find((r) => Number(r.id) === id);
    if (!record || !permAllowed) continue;
    seen.add(id);
    eligibleIds.push(id);
  }

  if (eligibleIds.length === 0) {
    message.warning(
      notAllowedMessage ?? t('common.submitDocumentAndSubmitReviewNotAllowed'),
    );
    return;
  }

  let success = 0;
  let failed = 0;
  let cancelled = 0;
  let lastError: unknown = null;
  for (const id of eligibleIds) {
    try {
      await commit(id);
      await submitReview(id);
      success += 1;
    } catch (error) {
      if (isSubmitReviewUserCancelled(error)) {
        cancelled += 1;
      } else {
        failed += 1;
        lastError = error;
      }
    }
  }

  if (success > 0) {
    message.success(t('common.submitDocumentAndSubmitReviewSuccess', { count: success }));
  }
  if (failed > 0) {
    const reason = getApiErrorMessage(lastError, '');
    if (reason) {
      message.warning(
        t('common.submitDocumentAndSubmitReviewPartialWithReason', {
          success,
          failed,
          reason,
        }),
      );
    } else {
      message.warning(
        t('common.submitDocumentAndSubmitReviewPartial', { success, failed }),
      );
    }
  } else if (cancelled > 0) {
    if (success > 0) {
      message.info(
        t('components.uniBatch.submitReviewCancelledPartial', { success, cancelled }),
      );
    } else {
      message.info(t('components.uniBatch.submitReviewCancelled'));
    }
  }
  if (success > 0 || failed > 0) {
    onSuccess?.();
  }
}

export function buildCommitAndSubmitReviewMenuItem(options: {
  t: TFunction;
  disabled: boolean;
  onClick: (keys: React.Key[]) => void | Promise<void>;
}): UniBatchMenuItem {
  const { t, disabled, onClick } = options;
  return {
    key: 'submit-document-and-review',
    label: t('common.submitDocumentAndSubmitReview'),
    disabled,
    onClick,
  };
}

/** 插在「提交」之后、「撤销提交」之前；已有合一项则不重复插入 */
export function insertCommitAndSubmitReviewMenuItem(
  items: UniBatchMenuItem[],
  combined: UniBatchMenuItem,
): UniBatchMenuItem[] {
  if (items.some((it) => it.key === combined.key)) {
    return items;
  }
  const submitIdx = items.findIndex((it) => it.key === 'submit');
  if (submitIdx < 0) {
    return [combined, ...items];
  }
  const next = [...items];
  next.splice(submitIdx + 1, 0, combined);
  return next;
}

/**
 * 统一挂载：在既有提交下拉（提交 / 撤销提交 / 提交审核）上插入合一步。
 * 列表页应走本函数或 UniBatchMenuButton 的 documentCommitAndSubmitReview，禁止手写合一项。
 */
export function withDocumentSubmitCombinedItem<T extends { id?: number }>(
  items: UniBatchMenuItem[],
  options: DocumentCommitAndSubmitReviewOptions<T>,
): UniBatchMenuItem[] {
  const {
    t,
    message,
    disabled,
    commitRecords,
    permAllowed,
    commit,
    submitReview,
    resolveId,
    onSuccess,
    notAllowedMessage,
  } = options;
  return insertCommitAndSubmitReviewMenuItem(
    items,
    buildCommitAndSubmitReviewMenuItem({
      t,
      disabled,
      onClick: (keys) =>
        runCommitThenSubmitReviewBatch({
          keys,
          commitRecords,
          permAllowed,
          resolveId,
          commit,
          submitReview,
          notAllowedMessage,
          onSuccess,
          message,
          t,
        }),
    }),
  );
}

export type BuildDocumentSubmitMenuItemsOptions<T extends { id?: number }> = {
  t: TFunction;
  message: CommitAndSubmitReviewBatchOptions<T>['message'];
  hasSelection: boolean;
  canSubmit: boolean;
  submitRows: T[];
  withdrawSubmitRows: T[];
  submitReviewRows: T[];
  labels: {
    withdrawSubmit: React.ReactNode;
    submitReview: React.ReactNode;
    submitReviewNotAllowed?: string;
  };
  commit: (id: number) => Promise<unknown>;
  withdrawSubmit: (id: number) => Promise<unknown>;
  submitReview: (id: number) => Promise<unknown>;
  /** 单动作批量；不传则按 records 的 id 逐条 onRun */
  runBatch?: (
    records: T[],
    capabilityKey: string,
    permAllowed: boolean,
    onRun: (id: number) => Promise<unknown>,
    notAllowedMessage?: string,
  ) => void | Promise<void>;
  resolveId?: (key: React.Key, record: T | undefined) => number | null;
  onSuccess?: () => void;
};

/**
 * 提交下拉完整四项真源：提交、直接提交审核、撤销提交、提交审核。
 */
export function buildDocumentSubmitMenuItems<T extends { id?: number }>(
  options: BuildDocumentSubmitMenuItemsOptions<T>,
): UniBatchMenuItem[] {
  const {
    t,
    message,
    hasSelection,
    canSubmit,
    submitRows,
    withdrawSubmitRows,
    submitReviewRows,
    labels,
    commit,
    withdrawSubmit,
    submitReview,
    runBatch,
    resolveId,
    onSuccess,
  } = options;

  const submitDisabled = hasSelection && !(canSubmit && submitRows.length > 0);
  const defaultRun = (
    records: T[],
    _capabilityKey: string,
    permAllowed: boolean,
    onRun: (id: number) => Promise<unknown>,
    notAllowedMessage?: string,
  ) => {
    void (async () => {
      if (!permAllowed || records.length === 0) {
        message.warning(notAllowedMessage ?? t('common.submitDocumentAndSubmitReviewNotAllowed'));
        return;
      }
      let success = 0;
      let failed = 0;
      let cancelled = 0;
      for (const row of records) {
        const id = Number(row.id);
        if (!Number.isFinite(id) || id <= 0) continue;
        try {
          await onRun(id);
          success += 1;
        } catch (error) {
          if (isSubmitReviewUserCancelled(error)) {
            cancelled += 1;
          } else {
            failed += 1;
          }
        }
      }
      if (success > 0 && failed === 0 && cancelled === 0) {
        message.success(t('common.operationSuccess'));
      } else if (failed > 0) {
        message.warning(
          t('common.submitDocumentAndSubmitReviewPartial', { success, failed }),
        );
      } else if (cancelled > 0) {
        if (success > 0) {
          message.info(
            t('components.uniBatch.submitReviewCancelledPartial', { success, cancelled }),
          );
        } else {
          message.info(t('components.uniBatch.submitReviewCancelled'));
        }
      }
      if (success > 0 || failed > 0) {
        onSuccess?.();
      }
    })();
  };
  const run = runBatch ?? defaultRun;

  return withDocumentSubmitCombinedItem(
    [
      {
        key: 'submit',
        label: t('common.submit'),
        disabled: submitDisabled,
        onClick: () => run(submitRows, 'submit', canSubmit, commit),
      },
      {
        key: 'withdraw-submit',
        label: labels.withdrawSubmit,
        disabled: hasSelection && withdrawSubmitRows.length === 0,
        onClick: () => run(withdrawSubmitRows, 'withdraw_submit', canSubmit, withdrawSubmit),
      },
      {
        key: 'submit-review',
        label: labels.submitReview,
        disabled: hasSelection && !(canSubmit && submitReviewRows.length > 0),
        onClick: () =>
          run(
            submitReviewRows,
            'submit_review',
            canSubmit,
            submitReview,
            labels.submitReviewNotAllowed,
          ),
      },
    ],
    {
      t,
      message,
      disabled: submitDisabled,
      commitRecords: submitRows,
      permAllowed: canSubmit,
      commit,
      submitReview,
      resolveId,
      onSuccess,
      notAllowedMessage: t('common.submitDocumentAndSubmitReviewNotAllowed'),
    },
  );
}
