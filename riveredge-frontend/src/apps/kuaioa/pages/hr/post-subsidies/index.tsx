import React, { useEffect, useMemo, useState } from 'react';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import { listEmployees } from '../../../services/employees';
import {
  createPostSubsidy,
  deletePostSubsidy,
  getPostSubsidy,
  listPostSubsidies,
  updatePostSubsidy,
} from '../../../services/postSubsidy';

const PostSubsidiesPage: React.FC = () => {
  const [employeeOptions, setEmployeeOptions] = useState<Array<{ label: string; value: number }>>(
    [],
  );

  useEffect(() => {
    void (async () => {
      const res = await listEmployees({ status: 'active' });
      setEmployeeOptions(
        res.items.map((e) => ({
          label: `${e.employee_code || ''} ${e.full_name}`.trim(),
          value: Number(e.id),
        })),
      );
    })();
  }, []);

  const fields = useMemo(
    () => [
      { name: 'subsidy_code', labelKey: 'app.kuaioa.postSubsidy.code', width: 140 },
      {
        name: 'year_month',
        labelKey: 'app.kuaioa.payroll.yearMonth',
        required: true,
        width: 100,
      },
      {
        name: 'employee_id',
        labelKey: 'app.kuaioa.employee.fullName',
        type: 'select' as const,
        options: employeeOptions,
        required: true,
        hideInTable: true,
      },
      { name: 'employee_name', labelKey: 'app.kuaioa.employee.fullName', width: 120, hideInForm: true },
      {
        name: 'item_name',
        labelKey: 'app.kuaioa.postSubsidy.itemName',
        required: true,
        width: 140,
      },
      {
        name: 'amount',
        labelKey: 'app.kuaioa.postSubsidy.amount',
        type: 'number' as const,
        required: true,
        width: 100,
      },
      { name: 'workshop_name', labelKey: 'app.kuaioa.attendance.workshop', width: 120, hideInForm: true },
      { name: 'notes', labelKey: 'common.remark', type: 'textarea' as const, hideInTable: true },
    ],
    [employeeOptions],
  );

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.postSubsidy.createButton"
      resource="kuaioa:post-subsidy"
      codeField="subsidy_code"
      nameField="employee_name"
      autoGenerateCode
      statusPresentation="marker"
      detailVariant="master"
      getDetailFn={getPostSubsidy}
      columnPersistenceId="apps.kuaioa.post-subsidy.list-v1"
      fields={fields}
      listFn={listPostSubsidies}
      createFn={createPostSubsidy}
      updateFn={updatePostSubsidy}
      deleteFn={deletePostSubsidy}
    />
  );
};

export default PostSubsidiesPage;
