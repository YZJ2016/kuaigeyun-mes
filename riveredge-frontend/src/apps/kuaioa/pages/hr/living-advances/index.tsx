import React, { useEffect, useMemo, useState } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import { listEmployees } from '../../../services/employees';
import {
  createLivingAdvance,
  deleteLivingAdvance,
  getLivingAdvance,
  listLivingAdvances,
  updateLivingAdvance,
} from '../../../services/payroll';
import { runKuaioaListExport } from '../../../utils/kuaioaListExport';
import { buildFactoryImportTemplate } from '../../../../master-data/utils/factoryImportTemplate';
import {
  buildOaImportCellReader,
  collectOaImportNonEmptyRows,
  resolveOaEmployeeId,
  runOaChunkedCreateImport,
  showOaImportValidationErrors,
  type OaImportRowError,
} from '../../../utils/kuaioaSpreadsheetImport';

type EmpSnap = {
  bank_name: string;
  bank_account: string;
  workshop_name: string;
  base_living: number;
};

type EmpRow = { id: number; employee_code?: string | null; full_name?: string | null };

const LivingAdvancesPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const currentUser = useCurrentUser();
  const [employeeOptions, setEmployeeOptions] = useState<Array<{ label: string; value: number }>>(
    [],
  );
  const [employees, setEmployees] = useState<EmpRow[]>([]);
  const [empSnap, setEmpSnap] = useState<Record<number, EmpSnap>>({});

  const registrarName = useMemo(() => {
    if (!currentUser) return '';
    return String(currentUser.full_name || currentUser.username || '');
  }, [currentUser]);

  useEffect(() => {
    void (async () => {
      const res = await listEmployees({ status: 'active' });
      setEmployees(res.items as EmpRow[]);
      setEmployeeOptions(
        res.items.map((e) => ({
          label: `${e.employee_code || ''} ${e.full_name}`.trim(),
          value: Number(e.id),
        })),
      );
      const map: Record<number, EmpSnap> = {};
      for (const e of res.items) {
        map[Number(e.id)] = {
          bank_name: String(e.bank_name || ''),
          bank_account: String(e.bank_account || ''),
          workshop_name: String(e.workshop_name || ''),
          base_living: Number(e.living_allowance || 0),
        };
      }
      setEmpSnap(map);
    })();
  }, []);

  const fillExcelFields = (
    form: { setFieldsValue: (v: Record<string, unknown>) => void },
    eid: number,
    amount?: number,
  ) => {
    const snap = empSnap[eid];
    const fixed = snap?.base_living ?? 0;
    const adv = amount ?? 0;
    form.setFieldsValue({
      bank_name: snap?.bank_name || '',
      bank_account: snap?.bank_account || '',
      workshop_name: snap?.workshop_name || '',
      base_living: fixed,
      payout_amount: fixed + adv,
      registrar_name: registrarName,
    });
  };

  const fields = useMemo(
    () => [
      { name: 'advance_code', labelKey: 'app.kuaioa.livingAdvance.code', width: 140 },
      {
        name: 'year_month',
        labelKey: 'app.kuaioa.payroll.yearMonth',
        type: 'month' as const,
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
      {
        name: 'employee_name',
        labelKey: 'app.kuaioa.employee.fullName',
        width: 100,
        hideInForm: true,
      },
      {
        name: 'bank_name',
        labelKey: 'app.kuaioa.livingPayout.bank',
        hideInTable: true,
      },
      {
        name: 'bank_account',
        labelKey: 'app.kuaioa.employee.bankAccount',
        hideInTable: true,
      },
      {
        name: 'workshop_name',
        labelKey: 'app.kuaioa.attendance.workshop',
        width: 120,
      },
      {
        name: 'base_living',
        labelKey: 'app.kuaioa.livingPayout.fixedAmount',
        type: 'number' as const,
        width: 100,
      },
      {
        name: 'amount',
        labelKey: 'app.kuaioa.livingPayout.advanceAmount',
        type: 'number' as const,
        required: true,
        width: 100,
      },
      {
        name: 'payout_amount',
        labelKey: 'app.kuaioa.livingPayout.payout',
        type: 'number' as const,
        hideInTable: true,
      },
      {
        name: 'registrar_name',
        labelKey: 'app.kuaioa.livingAdvance.registrar',
        hideInTable: true,
      },
      {
        name: 'created_by_name',
        labelKey: 'app.kuaioa.livingAdvance.registrar',
        width: 100,
        hideInForm: true,
      },
      { name: 'status', labelKey: 'common.status', width: 90, hideInForm: true },
    ],
    [employeeOptions],
  );

  const importTemplate = useMemo(
    () =>
      buildFactoryImportTemplate(
        t,
        [
          {
            field: 'employee_code',
            labelKey: 'app.kuaioa.employee.code',
            aliases: ['员工编号', '工号'],
          },
          {
            field: 'employee_name',
            labelKey: 'app.kuaioa.employee.fullName',
            aliases: ['姓名'],
          },
          {
            field: 'year_month',
            required: true,
            labelKey: 'app.kuaioa.payroll.yearMonth',
            aliases: ['月份'],
          },
          {
            field: 'amount',
            required: true,
            labelKey: 'app.kuaioa.livingPayout.advanceAmount',
            aliases: ['预支金额', '金额'],
          },
          {
            field: 'workshop_name',
            labelKey: 'app.kuaioa.attendance.workshop',
            aliases: ['车间'],
          },
          { field: 'notes', labelKey: 'common.remark', aliases: ['备注'] },
        ],
        ['EMP001', '张三', '2026-09', '500', '', ''],
      ),
    [t],
  );

  const handleImport = async (data: unknown[][]) => {
    const parsed = collectOaImportNonEmptyRows(data);
    if (!parsed) {
      messageApi.warning(t('app.kuaioa.import.empty'));
      return false;
    }
    if (parsed.rows.length === 0) {
      messageApi.warning(t('app.kuaioa.import.noRows'));
      return false;
    }
    const cellOf = buildOaImportCellReader(parsed.headers, importTemplate.importHeaderMap);
    const importData: Record<string, unknown>[] = [];
    const errors: OaImportRowError[] = [];
    parsed.rows.forEach((row, rowIndex) => {
      if (!Array.isArray(row)) return;
      const actualRowIndex = rowIndex + 3;
      const yearMonth = cellOf(row, 'year_month');
      if (!/^\d{4}-\d{2}$/.test(yearMonth)) {
        errors.push({ row: actualRowIndex, message: t('app.kuaioa.import.yearMonthInvalid') });
        return;
      }
      const employeeId = resolveOaEmployeeId(
        cellOf(row, 'employee_code'),
        cellOf(row, 'employee_name'),
        employees,
      );
      if (!employeeId) {
        errors.push({ row: actualRowIndex, message: t('app.kuaioa.import.employeeNotFound') });
        return;
      }
      const amount = Number(cellOf(row, 'amount'));
      if (!Number.isFinite(amount)) {
        errors.push({ row: actualRowIndex, message: t('app.kuaioa.import.amountInvalid') });
        return;
      }
      const snap = empSnap[employeeId];
      importData.push({
        year_month: yearMonth,
        employee_id: employeeId,
        amount,
        workshop_name: cellOf(row, 'workshop_name') || snap?.workshop_name || undefined,
        base_living: snap?.base_living,
        bank_name: snap?.bank_name || undefined,
        bank_account: snap?.bank_account || undefined,
        notes: cellOf(row, 'notes') || undefined,
      });
    });
    if (errors.length > 0) {
      showOaImportValidationErrors(t, errors);
      return false;
    }
    return runOaChunkedCreateImport({
      t,
      messageApi,
      items: importData,
      createOne: (item) => createLivingAdvance(item),
      title: t('app.kuaioa.livingAdvance.importTitle'),
      successKey: 'app.kuaioa.livingAdvance.importSuccess',
    });
  };

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
      columnPersistenceId="apps.kuaioa.living-advance.list-v4"
      fields={fields}
      listFn={listLivingAdvances}
      createFn={createLivingAdvance}
      updateFn={updateLivingAdvance}
      deleteFn={deleteLivingAdvance}
      onFormValuesChange={(changed, allValues, form) => {
        if ('employee_id' in changed && changed.employee_id != null) {
          fillExcelFields(form, Number(changed.employee_id), Number(allValues.amount || 0));
          return;
        }
        if ('amount' in changed || 'base_living' in changed) {
          const fixed = Number(
            ('base_living' in changed ? changed.base_living : allValues.base_living) || 0,
          );
          const adv = Number(('amount' in changed ? changed.amount : allValues.amount) || 0);
          form.setFieldValue('payout_amount', fixed + adv);
        }
        if (!allValues.registrar_name && registrarName) {
          form.setFieldValue('registrar_name', registrarName);
        }
      }}
      mapRecordToFormValues={(record) => {
        const eid = Number(record.employee_id);
        const snap = empSnap[eid];
        const fixed = Number(record.base_living ?? snap?.base_living ?? 0);
        const adv = Number(record.amount || 0);
        return {
          ...record,
          bank_name: snap?.bank_name || '',
          bank_account: snap?.bank_account || '',
          workshop_name: record.workshop_name || snap?.workshop_name || '',
          base_living: fixed,
          payout_amount: fixed + adv,
          registrar_name: String(record.created_by_name || registrarName),
        };
      }}
      mapFormValuesToPayload={(values) => {
        const {
          payout_amount: _p,
          registrar_name: _r,
          employee_name: _n,
          created_by_name: _c,
          advance_code: _code,
          status: _s,
          ...rest
        } = values;
        return rest;
      }}
      showExportButton
      onExport={async (type, keys, pageData) => {
        await runKuaioaListExport({
          type,
          keys,
          pageData,
          listFn: listLivingAdvances,
          columns: [
            { key: 'advance_code', title: t('app.kuaioa.livingAdvance.code') },
            { key: 'year_month', title: t('app.kuaioa.payroll.yearMonth') },
            { key: 'employee_name', title: t('app.kuaioa.employee.fullName') },
            { key: 'workshop_name', title: t('app.kuaioa.attendance.workshop') },
            { key: 'base_living', title: t('app.kuaioa.livingPayout.fixedAmount') },
            { key: 'amount', title: t('app.kuaioa.livingPayout.advanceAmount') },
            { key: 'status', title: t('common.status') },
          ],
          filename: t('app.kuaioa.livingAdvance.exportFileName'),
          messageApi,
          noDataText: t('common.exportNoData'),
        });
      }}
      showImportButton
      onImport={handleImport}
      importHeaders={importTemplate.importHeaders}
      importExampleRow={importTemplate.importExampleRow}
      importColumnOptions={importTemplate.importColumnOptions}
      importFieldMap={importTemplate.importHeaderMap}
      importTemplateName={t('app.kuaioa.livingAdvance.exportFileName')}
    />
  );
};

export default LivingAdvancesPage;
