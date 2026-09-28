import React, { useEffect, useMemo, useState } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import { listEmployees } from '../../../services/employees';
import { loadOaWorkshopNameOptions } from '../../../utils/oaWorkshopOptions';
import {
  createPostSubsidy,
  deletePostSubsidy,
  getPostSubsidy,
  listPostSubsidies,
  updatePostSubsidy,
} from '../../../services/postSubsidy';
import { runKuaioaListExport } from '../../../utils/kuaioaListExport';
import { buildFactoryImportTemplate } from '../../../../master-data/utils/factoryImportTemplate';
import {
  buildOaImportCellReader,
  collectOaImportNonEmptyRows,
  resolveOaEmployeeId,
  resolveOaOptionValue,
  runOaChunkedCreateImport,
  showOaImportValidationErrors,
  type OaImportRowError,
} from '../../../utils/kuaioaSpreadsheetImport';

type EmpRow = { id: number; employee_code?: string | null; full_name?: string | null };

const PostSubsidiesPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [employeeOptions, setEmployeeOptions] = useState<Array<{ label: string; value: number }>>(
    [],
  );
  const [employees, setEmployees] = useState<EmpRow[]>([]);
  const [workshopOptions, setWorkshopOptions] = useState<Array<{ label: string; value: string }>>(
    [],
  );
  const [employeeWorkshop, setEmployeeWorkshop] = useState<Record<number, string>>({});

  useEffect(() => {
    void (async () => {
      const [emps, workshops] = await Promise.all([
        listEmployees({ status: 'active' }),
        loadOaWorkshopNameOptions(),
      ]);
      setEmployees(emps.items as EmpRow[]);
      setWorkshopOptions(workshops);
      setEmployeeOptions(
        emps.items.map((e) => ({
          label: `${e.employee_code || ''} ${e.full_name}`.trim(),
          value: Number(e.id),
        })),
      );
      const map: Record<number, string> = {};
      for (const e of emps.items) {
        if (e.workshop_name) map[Number(e.id)] = String(e.workshop_name);
      }
      setEmployeeWorkshop(map);
    })();
  }, []);

  const itemOptions = useMemo(
    () => [
      {
        label: t('app.kuaioa.payroll.nightSubsidy'),
        value: t('app.kuaioa.payroll.nightSubsidy'),
      },
      {
        label: t('app.kuaioa.payroll.heatSubsidy'),
        value: t('app.kuaioa.payroll.heatSubsidy'),
      },
      {
        label: t('app.kuaioa.payroll.postAllowance'),
        value: t('app.kuaioa.payroll.postAllowance'),
      },
    ],
    [t],
  );

  const fields = useMemo(
    () => [
      { name: 'subsidy_code', labelKey: 'app.kuaioa.postSubsidy.code', width: 140 },
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
      { name: 'employee_name', labelKey: 'app.kuaioa.employee.fullName', width: 120, hideInForm: true },
      {
        name: 'workshop_name',
        labelKey: 'app.kuaioa.attendance.workshop',
        type: 'select' as const,
        options: workshopOptions,
        readonly: true,
        width: 120,
      },
      {
        name: 'item_name',
        labelKey: 'app.kuaioa.postSubsidy.itemName',
        type: 'select' as const,
        options: itemOptions,
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
      { name: 'notes', labelKey: 'common.remark', type: 'textarea' as const, hideInTable: true },
    ],
    [employeeOptions, itemOptions, workshopOptions],
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
            field: 'item_name',
            required: true,
            labelKey: 'app.kuaioa.postSubsidy.itemName',
            aliases: ['项目'],
            options: itemOptions.map((o) => o.label),
          },
          {
            field: 'amount',
            required: true,
            labelKey: 'app.kuaioa.postSubsidy.amount',
            aliases: ['金额'],
          },
          { field: 'notes', labelKey: 'common.remark', aliases: ['备注'] },
        ],
        [
          'EMP001',
          '张三',
          '2026-09',
          itemOptions[0]?.label || '',
          '50',
          '',
        ],
      ),
    [itemOptions, t],
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
      const itemName = resolveOaOptionValue(cellOf(row, 'item_name'), itemOptions);
      if (!itemName) {
        errors.push({
          row: actualRowIndex,
          message: t('app.kuaioa.import.missingField', {
            field: t('app.kuaioa.postSubsidy.itemName'),
          }),
        });
        return;
      }
      const amount = Number(cellOf(row, 'amount'));
      if (!Number.isFinite(amount)) {
        errors.push({ row: actualRowIndex, message: t('app.kuaioa.import.amountInvalid') });
        return;
      }
      importData.push({
        year_month: yearMonth,
        employee_id: employeeId,
        item_name: itemName,
        amount,
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
      createOne: (item) => createPostSubsidy(item),
      title: t('app.kuaioa.postSubsidy.importTitle'),
      successKey: 'app.kuaioa.postSubsidy.importSuccess',
    });
  };

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
      columnPersistenceId="apps.kuaioa.post-subsidy.list-v3"
      fields={fields}
      listFn={listPostSubsidies}
      createFn={createPostSubsidy}
      updateFn={updatePostSubsidy}
      deleteFn={deletePostSubsidy}
      onFormValuesChange={(changed, _all, form) => {
        if ('employee_id' in changed) {
          const ws = employeeWorkshop[Number(changed.employee_id)];
          form.setFieldValue('workshop_name', ws || undefined);
        }
      }}
      mapFormValuesToPayload={(values) => {
        const { workshop_name: _w, employee_name: _n, subsidy_code: _c, ...rest } = values;
        return rest;
      }}
      showExportButton
      onExport={async (type, keys, pageData) => {
        await runKuaioaListExport({
          type,
          keys,
          pageData,
          listFn: listPostSubsidies,
          columns: [
            { key: 'subsidy_code', title: t('app.kuaioa.postSubsidy.code') },
            { key: 'year_month', title: t('app.kuaioa.payroll.yearMonth') },
            { key: 'employee_name', title: t('app.kuaioa.employee.fullName') },
            { key: 'workshop_name', title: t('app.kuaioa.attendance.workshop') },
            { key: 'item_name', title: t('app.kuaioa.postSubsidy.itemName') },
            { key: 'amount', title: t('app.kuaioa.postSubsidy.amount') },
          ],
          filename: t('app.kuaioa.postSubsidy.exportFileName'),
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
      importTemplateName={t('app.kuaioa.postSubsidy.exportFileName')}
    />
  );
};

export default PostSubsidiesPage;
