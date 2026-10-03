/**
 * 加班/临时调整：整厂、按部门、按人员
 */

import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Form, Segmented, Select } from 'antd';
import type { FormInstance } from 'antd/es/form';
import { UniUserSelect } from '../../../../../components/uni-user-select';
import { employeePerformanceApi } from '../../../services/performance';
import type { PerformanceScopeType } from '../../../types/performance';

export type PerformanceScopeFormValues = {
  scopeType: PerformanceScopeType;
  departmentId?: number;
  employeeId?: number;
};

type PerformanceScopeFormFieldsProps = {
  form: FormInstance;
  /** 默认整厂（加班）或按人员（临时调整） */
  defaultScope?: PerformanceScopeType;
};

export function renderPerformanceScopeLabel(
  t: (key: string) => string,
  scopeType: PerformanceScopeType,
  row: {
    departmentName?: string | null;
    employeeName?: string | null;
  },
): string {
  if (scopeType === 'department') {
    return row.departmentName?.trim() || t('app.kuaizhizao.performance.scope.department');
  }
  if (scopeType === 'employee') {
    return row.employeeName?.trim() || t('app.kuaizhizao.performance.scope.employee');
  }
  return t('app.kuaizhizao.performance.scope.plant');
}

export const PerformanceScopeFormFields: React.FC<PerformanceScopeFormFieldsProps> = ({
  form,
  defaultScope = 'plant',
}) => {
  const { t } = useTranslation();
  const scopeType = Form.useWatch('scopeType', form) as PerformanceScopeType | undefined;
  const [departments, setDepartments] = useState<Array<{ label: string; value: number }>>([]);

  useEffect(() => {
    void employeePerformanceApi.listDepartments().then((res) => {
      setDepartments((res.items ?? []).map((d) => ({ label: d.name, value: d.id })));
    });
  }, []);

  return (
    <>
      <Form.Item
        name="scopeType"
        label={t('app.kuaizhizao.performance.scope.label')}
        initialValue={defaultScope}
        rules={[{ required: true }]}
      >
        <Segmented<PerformanceScopeType>
          options={[
            { label: t('app.kuaizhizao.performance.scope.plant'), value: 'plant' },
            { label: t('app.kuaizhizao.performance.scope.department'), value: 'department' },
            { label: t('app.kuaizhizao.performance.scope.employee'), value: 'employee' },
          ]}
        />
      </Form.Item>
      {scopeType === 'department' ? (
        <Form.Item
          name="departmentId"
          label={t('app.kuaizhizao.performance.scope.department')}
          rules={[{ required: true }]}
        >
          <Select showSearch optionFilterProp="label" options={departments} />
        </Form.Item>
      ) : null}
      {scopeType === 'employee' ? (
        <UniUserSelect
          name="employeeId"
          label={t('app.kuaizhizao.performance.common.columns.employee')}
          required
        />
      ) : null}
    </>
  );
};
