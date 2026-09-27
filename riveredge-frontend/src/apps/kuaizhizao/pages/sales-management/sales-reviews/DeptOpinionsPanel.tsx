/**
 * 订单评审 — 部门意见面板（详情协作区 / 评审 Modal 共用）
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Col, Descriptions, Form, Input, Row, Space, Tabs, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { ThemedSegmented } from '../../../../../components/themed-segmented';
import { UniUserSelect } from '../../../../../components/uni-user-select';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import { formatDateTime } from '../../../../../utils/format';
import type { SalesReview, SalesReviewDeptCode } from '../../../services/sales-review';
import { renderSalesReviewDeptOpinionResultTag } from '../../../utils/salesReviewPresentation';

/** 部门意见表单控件尺寸（antd 6：medium = 常规/normal） */
const DEPT_OPINION_CONTROL_SIZE = 'medium' as const;

export const SALES_REVIEW_DEPT_CODES: SalesReviewDeptCode[] = [
  'tech',
  'process',
  'purchase',
  'production',
  'quality',
];

/** 评审中：按本轮意见槽位；草稿/驳回：按头表计划 */
export function resolveSalesReviewActiveDeptCodes(review: SalesReview): string[] {
  if (review.dept_opinions?.length) {
    return review.dept_opinions.map((o) => o.dept_code).filter(Boolean);
  }
  if (review.review_dept_plan?.length) {
    return review.review_dept_plan.map((p) => p.dept_code).filter(Boolean);
  }
  return [];
}

export type DeptOpinionFormState = {
  result: 'pass' | 'fail';
  opinion: string;
  reviewed_by?: number | null;
  reviewed_by_name?: string | null;
  reviewed_by_uuid?: string | null;
};

export type SalesReviewDeptOpinionsPanelProps = {
  review: SalesReview;
  canApprove: boolean;
  opinionForms: Record<string, DeptOpinionFormState>;
  setOpinionForms: React.Dispatch<React.SetStateAction<Record<string, DeptOpinionFormState>>>;
  actionLoading?: boolean;
  onSubmitDept: (deptCode: string) => void | Promise<void>;
};

type DeptOpinionEditorProps = {
  deptCode: string;
  formState: DeptOpinionFormState;
  assignedReviewerId?: number | null;
  assignedReviewerName?: string | null;
  setOpinionForms: SalesReviewDeptOpinionsPanelProps['setOpinionForms'];
  actionLoading: boolean;
  onSubmitDept: (deptCode: string) => void | Promise<void>;
};

const DeptOpinionEditor: React.FC<DeptOpinionEditorProps> = ({
  deptCode,
  formState,
  assignedReviewerId,
  assignedReviewerName,
  setOpinionForms,
  actionLoading,
  onSubmitDept,
}) => {
  const { t } = useTranslation();
  const currentUser = useCurrentUser();
  const [form] = Form.useForm();
  const lockedAssignee = assignedReviewerId != null && Number(assignedReviewerId) > 0;
  const canSubmitAsAssignee =
    !lockedAssignee || Number(currentUser?.id) === Number(assignedReviewerId);

  useEffect(() => {
    if (lockedAssignee) {
      setOpinionForms((prev) => {
        const cur = prev[deptCode] || { result: 'pass' as const, opinion: '' };
        if (cur.reviewed_by === assignedReviewerId) return prev;
        return {
          ...prev,
          [deptCode]: {
            ...cur,
            reviewed_by: assignedReviewerId,
            reviewed_by_name: assignedReviewerName || cur.reviewed_by_name || '',
          },
        };
      });
      return;
    }
    if (formState.reviewed_by_uuid) {
      form.setFieldsValue({ reviewer_uuid: formState.reviewed_by_uuid });
      return;
    }
    if (!currentUser?.uuid || !currentUser.id) return;
    form.setFieldsValue({ reviewer_uuid: currentUser.uuid });
    setOpinionForms((prev) => {
      const cur = prev[deptCode] || { result: 'pass' as const, opinion: '' };
      if (cur.reviewed_by) return prev;
      return {
        ...prev,
        [deptCode]: {
          ...cur,
          reviewed_by: currentUser.id,
          reviewed_by_name: currentUser.full_name || currentUser.username || '',
          reviewed_by_uuid: currentUser.uuid,
        },
      };
    });
  }, [
    assignedReviewerId,
    assignedReviewerName,
    currentUser,
    deptCode,
    form,
    formState.reviewed_by_uuid,
    lockedAssignee,
    setOpinionForms,
  ]);

  return (
    <Form form={form} layout="vertical" size={DEPT_OPINION_CONTROL_SIZE}>
      <Row gutter={16}>
        <Col flex="none">
          <Form.Item label={t('app.kuaizhizao.salesReview.colOpinionResult')} required>
            <ThemedSegmented
              className="form-field-segmented"
              size={DEPT_OPINION_CONTROL_SIZE}
              value={formState.result}
              onChange={(v) =>
                setOpinionForms((prev) => ({
                  ...prev,
                  [deptCode]: { ...formState, result: v as 'pass' | 'fail' },
                }))
              }
              options={[
                { label: t('app.kuaizhizao.salesReview.opinionPass'), value: 'pass' },
                { label: t('app.kuaizhizao.salesReview.opinionFail'), value: 'fail' },
              ]}
            />
          </Form.Item>
        </Col>
        <Col span={12}>
          {lockedAssignee ? (
            <Form.Item label={t('app.kuaizhizao.salesReview.colReviewedBy')} required>
              <Typography.Text>{assignedReviewerName || '—'}</Typography.Text>
            </Form.Item>
          ) : (
            <UniUserSelect
              name="reviewer_uuid"
              label={t('app.kuaizhizao.salesReview.colReviewedBy')}
              placeholder={t('app.kuaizhizao.salesReview.reviewerPlaceholder')}
              required
              rules={[
                {
                  required: true,
                  message: t('app.kuaizhizao.salesReview.reviewerRequired'),
                },
              ]}
              onChange={(_uuid, user) => {
                if (user && !Array.isArray(user)) {
                  setOpinionForms((prev) => ({
                    ...prev,
                    [deptCode]: {
                      ...formState,
                      reviewed_by: user.id,
                      reviewed_by_name: user.full_name || user.username || '',
                      reviewed_by_uuid: user.uuid,
                    },
                  }));
                  return;
                }
                setOpinionForms((prev) => ({
                  ...prev,
                  [deptCode]: {
                    ...formState,
                    reviewed_by: null,
                    reviewed_by_name: null,
                    reviewed_by_uuid: null,
                  },
                }));
              }}
            />
          )}
        </Col>
      </Row>
      <Form.Item
        label={t('app.kuaizhizao.salesReview.colOpinion')}
        required={formState.result === 'fail'}
      >
        <Input.TextArea
          size={DEPT_OPINION_CONTROL_SIZE}
          rows={2}
          value={formState.opinion}
          onChange={(e) =>
            setOpinionForms((prev) => ({
              ...prev,
              [deptCode]: { ...formState, opinion: e.target.value },
            }))
          }
        />
      </Form.Item>
      {canSubmitAsAssignee ? (
        <Button type="primary" loading={actionLoading} onClick={() => void onSubmitDept(deptCode)}>
          {t('app.kuaizhizao.salesReview.submitDeptOpinion')}
        </Button>
      ) : (
        <Alert type="warning" showIcon title={t('app.kuaizhizao.salesReview.notAssignedReviewer')} />
      )}
    </Form>
  );
};

export const SalesReviewDeptOpinionsPanel: React.FC<SalesReviewDeptOpinionsPanelProps> = ({
  review,
  canApprove,
  opinionForms,
  setOpinionForms,
  actionLoading = false,
  onSubmitDept,
}) => {
  const { t } = useTranslation();

  const deptLabel = (code: string) =>
    t(`app.kuaizhizao.salesReview.dept.${code}`, { defaultValue: code });

  const opinionByDept = useMemo(() => {
    const map = new Map<string, NonNullable<SalesReview['dept_opinions']>[number]>();
    for (const op of review.dept_opinions || []) {
      if (op?.dept_code) map.set(op.dept_code, op);
    }
    return map;
  }, [review.dept_opinions]);

  const activeDeptCodes = useMemo(() => resolveSalesReviewActiveDeptCodes(review), [review]);

  const firstPendingDept = useMemo(
    () =>
      activeDeptCodes.find((code) => {
        const existing = opinionByDept.get(code);
        return !existing || existing.result === 'pending';
      }) ?? activeDeptCodes[0],
    [activeDeptCodes, opinionByDept],
  );

  const [activeDept, setActiveDept] = useState<string>(activeDeptCodes[0] || 'tech');

  useEffect(() => {
    if (firstPendingDept) setActiveDept(firstPendingDept);
  }, [review.id, firstPendingDept]);

  const tabItems = useMemo(
    () =>
      activeDeptCodes.map((code) => {
        const existing = opinionByDept.get(code);
        // 下达评审会 seed result=pending 行；仅 pass/fail 才算已提交
        const isAnswered = Boolean(existing && existing.result !== 'pending');
        const formState = opinionForms[code] || { result: 'pass' as const, opinion: '' };
        const canSubmitThis = canApprove && review.status === 'reviewing' && !isAnswered;
        const resultLabel = isAnswered && existing ? existing.result : 'pending';

        let content: React.ReactNode;
        if (isAnswered && existing) {
          content = (
            <Descriptions size="small" column={2}>
              <Descriptions.Item label={t('app.kuaizhizao.salesReview.colOpinionResult')}>
                {renderSalesReviewDeptOpinionResultTag(t, existing.result)}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.salesReview.colReviewedBy')}>
                {existing.reviewed_by_name || '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.salesReview.colReviewedAt')}>
                {existing.reviewed_at ? formatDateTime(existing.reviewed_at) : '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('app.kuaizhizao.salesReview.colOpinion')} span={2}>
                {existing.opinion?.trim() ? existing.opinion : '—'}
              </Descriptions.Item>
            </Descriptions>
          );
        } else if (canSubmitThis) {
          content = (
            <DeptOpinionEditor
              deptCode={code}
              formState={formState}
              assignedReviewerId={existing?.assigned_reviewer_id}
              assignedReviewerName={existing?.assigned_reviewer_name}
              setOpinionForms={setOpinionForms}
              actionLoading={actionLoading}
              onSubmitDept={onSubmitDept}
            />
          );
        } else if (review.status === 'draft' || review.status === 'rejected') {
          const plan = review.review_dept_plan?.find((p) => p.dept_code === code);
          content = plan ? (
            <Descriptions size="small" column={1}>
              <Descriptions.Item label={t('app.kuaizhizao.salesReview.colReviewedBy')}>
                {plan.assigned_reviewer_name || '—'}
              </Descriptions.Item>
            </Descriptions>
          ) : (
            renderSalesReviewDeptOpinionResultTag(t, 'pending')
          );
        } else {
          content = renderSalesReviewDeptOpinionResultTag(t, 'pending');
        }

        return {
          key: code,
          label: (
            <Space size={4}>
              <span>{deptLabel(code)}</span>
              {renderSalesReviewDeptOpinionResultTag(t, resultLabel)}
            </Space>
          ),
          children: <div style={{ paddingTop: 4 }}>{content}</div>,
        };
      }),
    [
      actionLoading,
      canApprove,
      onSubmitDept,
      opinionByDept,
      opinionForms,
      review.review_dept_plan,
      review.status,
      setOpinionForms,
      t,
    ],
  );

  return (
    <Space orientation="vertical" style={{ width: '100%' }} size="medium">
      {review.status === 'reviewing' && canApprove ? (
        <Alert type="info" showIcon title={t('app.kuaizhizao.salesReview.deptOpinionHint')} />
      ) : null}
      {activeDeptCodes.length ? (
        <Tabs activeKey={activeDept} onChange={setActiveDept} items={tabItems} />
      ) : (
        <Alert type="warning" showIcon title={t('app.kuaizhizao.salesReview.deptPlanEmptyHint')} />
      )}
    </Space>
  );
};

/** 提交前校验：不通过须填意见；须选择评审人 */
export function validateDeptOpinionForm(
  formState: DeptOpinionFormState,
  failMessage: string,
  reviewerRequiredMessage?: string,
): string | null {
  if (!formState.reviewed_by) {
    return reviewerRequiredMessage || failMessage;
  }
  if (formState.result === 'fail' && !String(formState.opinion || '').trim()) {
    return failMessage;
  }
  return null;
}
