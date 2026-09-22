import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import { listEmployees } from '../../../services/employees';
import {
  createLivingAdvance,
  deleteLivingAdvance,
  getLivingAdvance,
  listLivingAdvances,
  updateLivingAdvance,
} from '../../../services/payroll';

const LivingAdvancesPage: React.FC = () => {
  const { t } = useTranslation();
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
      { name: 'advance_code', labelKey: 'app.kuaioa.livingAdvance.code', width: 140 },
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
      { name: 'workshop_name', labelKey: 'app.kuaioa.attendance.workshop', width: 120, hideInForm: true },
      {
        name: 'base_living',
        labelKey: 'app.kuaioa.livingAdvance.baseLiving',
        type: 'number' as const,
        width: 110,
        hideInForm: true,
      },
      {
        name: 'amount',
        labelKey: 'app.kuaioa.livingAdvance.amount',
        type: 'number' as const,
        required: true,
        width: 110,
      },
      { name: 'reason', labelKey: 'app.kuaioa.livingAdvance.reason', width: 160 },
      { name: 'status', labelKey: 'common.status', width: 90, hideInForm: true },
      { name: 'notes', labelKey: 'common.remark', type: 'textarea' as const, hideInTable: true },
    ],
    [employeeOptions],
  );

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.livingAdvance.createButton"
      resource="kuaioa:living-advance"
      codeField="advance_code"
      nameField="employee_name"
      autoGenerateCode
      statusPresentation="marker"
      detailVariant="master"
      getDetailFn={getLivingAdvance}
      columnPersistenceId="apps.kuaioa.living-advance.list-v1"
      fields={fields}
      listFn={listLivingAdvances}
      createFn={createLivingAdvance}
      updateFn={updateLivingAdvance}
      deleteFn={deleteLivingAdvance}
    />
  );
};

export default LivingAdvancesPage;
