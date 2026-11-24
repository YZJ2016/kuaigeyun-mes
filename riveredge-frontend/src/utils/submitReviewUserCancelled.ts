/** 送审弹窗用户点取消（非接口失败） */
export const SUBMIT_REVIEW_USER_CANCELLED = 'submit_review_cancelled';

export class SubmitReviewUserCancelledError extends Error {
  constructor() {
    super(SUBMIT_REVIEW_USER_CANCELLED);
    this.name = 'SubmitReviewUserCancelledError';
  }
}

export function isSubmitReviewUserCancelled(error: unknown): boolean {
  if (error instanceof SubmitReviewUserCancelledError) return true;
  if (error instanceof Error) {
    return (
      error.name === 'SubmitReviewUserCancelledError'
      || error.message === SUBMIT_REVIEW_USER_CANCELLED
    );
  }
  return false;
}