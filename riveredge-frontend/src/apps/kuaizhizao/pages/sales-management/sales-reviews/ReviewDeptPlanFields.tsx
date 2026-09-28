/**
 * 订单评审 — 创建/编辑时选择评审部门与指定评审人（子表，对齐收款计划）
 */
import React, { useMemo } from 'react';
import { App, Button, Form, Select, Table, Typography } from 'antd';
import type { FormListFieldData, FormListOperation } from 'antd/es/form/FormList';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { UniUserSelect } from '../../../../../components/uni-user-select';
import {
  DOCUMENT_SUBLINE_ADD_BUTTON_CLASS,
  DOCUMENT_SUBLINE_TABLE_PROPS,
} from '../../../../../components/document-subline-table';
import { resolveUserDisplay } from '../../../../../services/user';
import { SALES_REVIEW_DEPT_CODES } from './DeptOpinionsPanel';

export type ReviewDeptPlanFormRow = {
  dept_code: string;
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
  return (plan || [])
    .filter((p) => p?.dept_code)
    .map((p) => ({
      dept_code: p.dept_code,
      assigned_reviewer_id: p.assigned_reviewer_id,
      assigned_reviewer_name: p.assigned_reviewer_name ?? undefined,
    }));
}

export function reviewDeptPlanRowsToPayload(rows: ReviewDeptPlanFormRow[]) {
  return (rows || [])
    .filter((r) => r.dept_code && r.assigned_reviewer_id)
    .map((r) => ({
      dept_code: r.dept_code,
      assigned_reviewer_id: Number(r.assigned_reviewer_id),
      assigned_reviewer_name: r.assigned_reviewer_name || undefined,
    }));
}

/** Form.List 内 UniUserSelect 用相对 name，onChange 的 useWatch 不可靠；提交前按 uuid 解析评审人 */
export async function resolveReviewDeptPlanPayload(rows: ReviewDeptPlanFormRow[]) {
  const list = (rows || []).filter((r) => r.dept_code && r.reviewer_uuid);
  if (!list.length) return [];
  const users = await resolveUserDisplay({
    user_uuids: list.map((r) => String(r.reviewer_uuid)),
  });
  const byUuid = new Map(users.map((u) => [u.uuid, u]));
  return list
    .map((r) => {
      const user = byUuid.get(String(r.reviewer_uuid));
      if (!user) return null;
      return {
        dept_code: r.dept_code,
        assigned_reviewer_id: user.id,
        assigned_reviewer_name: user.full_name || user.username || undefined,
      };
    })
    .filter(Boolean) as Array<{
    dept_code: string;
    assigned_reviewer_id: number;
    assigned_reviewer_name?: string;
  }>;
}

type ReviewDeptPlanListBodyProps = {
  fields: FormListFieldData[];
  add: FormListOperation['add'];
  remove: FormListOperation['remove'];
};

const ReviewDeptPlanListBody: React.FC<ReviewDeptPlanListBodyProps> = ({ fields, add, remove }) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const form = Form.useFormInstance();
  const rows = (Form.useWatch('review_dept_plan_rows', form) as ReviewDeptPlanFormRow[] | undefined) ?? [];

  const deptLabel = (code: string) =>
    t(`app.kuaizhizao.salesReview.dept.${code}`, { defaultValue: code });

  const usedCodes = useMemo(
    () => new Set((rows || []).map((r) => r?.dept_code).filter(Boolean) as string[]),
    [rows],
  );
  const availableCodes = useMemo(
    () => SALES_REVIEW_DEPT_CODES.filter((code) => !usedCodes.has(code)),
    [usedCodes],
  );

  const columns = [
    {
      title: t('app.kuaizhizao.salesReview.colDept'),
      width: 140,
      render: (_: unknown, field: FormListFieldData) => {
        const currentCode = rows[field.name]?.dept_code;
        return (
          <Form.Item
            name={[field.name, 'dept_code']}
            rules={[
              {
                required: true,
                message: t('app.kuaizhizao.salesReview.deptRequired'),
              },
            ]}
            style={{ margin: 0 }}
          >
            <Select
              allowClear={false}
              style={{ width: '100%' }}
              options={SALES_REVIEW_DEPT_CODES.map((code) => ({
                label: deptLabel(code),
                value: code,
                disabled: usedCodes.has(code) && code !== currentCode,
              }))}
            />
          </Form.Item>
        );
      },
    },
    {
      title: t('app.kuaizhizao.salesReview.colReviewedBy'),
      render: (_: unknown, field: FormListFieldData) => (
        <UniUserSelect
          name={[field.name, 'reviewer_uuid']}
          label={false}
          placeholder={t('app.kuaizhizao.salesReview.reviewerPlaceholder')}
          required
          rules={[
            {
              required: true,
              message: t('app.kuaizhizao.salesReview.reviewerRequired'),
            },
          ]}
          formItemProps={{ style: { margin: 0 } }}
        />
      ),
    },
    {
      title: t('common.action'),
      width: 48,
      align: 'center' as const,
      render: (_: unknown, field: FormListFieldData) => (
        <Button
          type="link"
          danger
          size="small"
          htmlType="button"
          icon={<DeleteOutlined />}
          onClick={() => remove(field.name)}
        />
      ),
    },
  ];

  return (
    <>
      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
        {t('app.kuaizhizao.salesReview.deptPlanHint')}
      </Typography.Text>
      {fields.length > 0 ? (
        <Table
          {...DOCUMENT_SUBLINE_TABLE_PROPS}
          rowKey="key"
          dataSource={fields}
          columns={columns}
          scroll={{ x: 'max-content' }}
        />
      ) : null}
      <Button
        type="dashed"
        block
        htmlType="button"
        icon={<PlusOutlined />}
        className={DOCUMENT_SUBLINE_ADD_BUTTON_CLASS}
        disabled={availableCodes.length === 0}
        style={{ marginTop: fields.length > 0 ? 8 : 0 }}
        onClick={() => {
          if (!availableCodes.length) {
            message.warning(t('app.kuaizhizao.salesReview.deptPlanAllAdded'));
            return;
          }
          add({ dept_code: availableCodes[0] });
        }}
      >
        {t('app.kuaizhizao.salesReview.addDeptPlanRow')}
      </Button>
      {fields.length === 0 ? (
        <Typography.Text type="danger" style={{ display: 'block', marginTop: 8 }}>
          {t('app.kuaizhizao.salesReview.deptPlanRequired')}
        </Typography.Text>
      ) : null}
    </>
  );
};

export const ReviewDeptPlanFormItem: React.FC = () => {
  const { t } = useTranslation();
  return (
    <Form.Item label={t('app.kuaizhizao.salesReview.deptPlanTitle')} required style={{ marginBottom: 16 }}>
      <Form.List name="review_dept_plan_rows">
        {(fields, { add, remove }) => (
          <ReviewDeptPlanListBody fields={fields} add={add} remove={remove} />
        )}
      </Form.List>
    </Form.Item>
  );
};
