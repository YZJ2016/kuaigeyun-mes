/**
 * 订单评审 — 创建/编辑时选择评审部门与指定评审人
 */
import React, { useMemo } from 'react';
import { Checkbox, Col, Form, Row, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { UniUserSelect } from '../../../../../components/uni-user-select';
import { SALES_REVIEW_DEPT_CODES } from './DeptOpinionsPanel';

export type ReviewDeptPlanFormRow = {
  dept_code: string;
  enabled: boolean;
  reviewer_uuid?: string;
  assigned_reviewer_id?: number;
  assigned_reviewer_name?: string;
};

export function buildReviewDeptPlanFormRows(
  plan?: Array<{
    dept_code: string;
    assigned_reviewer_id?: number;
    assigned_reviewer_name?: string | null;
  }> | null,
): ReviewDeptPlanFormRow[] {
  const byCode = new Map((plan || []).map((p) => [p.dept_code, p]));
  return SALES_REVIEW_DEPT_CODES.map((code) => {
    const hit = byCode.get(code);
    return {
      dept_code: code,
      enabled: Boolean(hit),
      assigned_reviewer_id: hit?.assigned_reviewer_id,
      assigned_reviewer_name: hit?.assigned_reviewer_name ?? undefined,
    };
  });
}

export function reviewDeptPlanRowsToPayload(rows: ReviewDeptPlanFormRow[]) {
  return (rows || [])
    .filter((r) => r.enabled && r.assigned_reviewer_id)
    .map((r) => ({
      dept_code: r.dept_code,
      assigned_reviewer_id: Number(r.assigned_reviewer_id),
      assigned_reviewer_name: r.assigned_reviewer_name || undefined,
    }));
}

export const ReviewDeptPlanSection: React.FC = () => {
  const { t } = useTranslation();
  const form = Form.useFormInstance();
  const rows = (Form.useWatch('review_dept_plan_rows', form) as ReviewDeptPlanFormRow[] | undefined) ?? [];

  const deptLabel = (code: string) =>
    t(`app.kuaizhizao.salesReview.dept.${code}`, { defaultValue: code });

  const enabledCount = useMemo(() => rows.filter((r) => r.enabled).length, [rows]);

  return (
    <>
      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
        {t('app.kuaizhizao.salesReview.deptPlanHint')}
      </Typography.Text>
      {SALES_REVIEW_DEPT_CODES.map((code, index) => {
        const row = rows[index];
        const enabled = Boolean(row?.enabled);
        return (
          <Row key={code} gutter={16} align="top" style={{ marginBottom: 12 }}>
            <Col flex="120px">
              <Form.Item name={['review_dept_plan_rows', index, 'dept_code']} initialValue={code} hidden>
                <input type="hidden" />
              </Form.Item>
              <Form.Item name={['review_dept_plan_rows', index, 'enabled']} valuePropName="checked">
                <Checkbox>{deptLabel(code)}</Checkbox>
              </Form.Item>
            </Col>
            <Col flex="auto">
              {enabled ? (
                <>
                  <Form.Item name={['review_dept_plan_rows', index, 'assigned_reviewer_id']} hidden>
                    <input type="hidden" />
                  </Form.Item>
                  <Form.Item name={['review_dept_plan_rows', index, 'assigned_reviewer_name']} hidden>
                    <input type="hidden" />
                  </Form.Item>
                  <UniUserSelect
                    name={['review_dept_plan_rows', index, 'reviewer_uuid']}
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
                        form.setFieldValue(
                          ['review_dept_plan_rows', index, 'assigned_reviewer_id'],
                          user.id,
                        );
                        form.setFieldValue(
                          ['review_dept_plan_rows', index, 'assigned_reviewer_name'],
                          user.full_name || user.username || '',
                        );
                      } else {
                        form.setFieldValue(['review_dept_plan_rows', index, 'assigned_reviewer_id'], undefined);
                        form.setFieldValue(['review_dept_plan_rows', index, 'assigned_reviewer_name'], undefined);
                      }
                    }}
                  />
                </>
              ) : null}
            </Col>
          </Row>
        );
      })}
      {enabledCount === 0 ? (
        <Typography.Text type="danger">{t('app.kuaizhizao.salesReview.deptPlanRequired')}</Typography.Text>
      ) : null}
    </>
  );
};

export const ReviewDeptPlanFormItem: React.FC = () => {
  const { t } = useTranslation();
  return (
    <Form.Item label={t('app.kuaizhizao.salesReview.deptPlanTitle')} required style={{ marginBottom: 16 }}>
      <ReviewDeptPlanSection />
    </Form.Item>
  );
};
