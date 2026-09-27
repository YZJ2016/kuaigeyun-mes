import React, { useEffect, useMemo, useState } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import { listEmployees } from '../../../services/employees';
import {
  createReward,
  deleteReward,
  getReward,
  listRewards,
  updateReward,
} from '../../../services/payroll';
import { runKuaioaListExport } from '../../../utils/kuaioaListExport';
import {
  buildFactoryImportTemplate,
} from '../../../../master-data/utils/factoryImportTemplate';
import {
  buildOaImportCellReader,
  collectOaImportNonEmptyRows,
  resolveOaEmployeeId,
  runOaChunkedCreateImport,
  showOaImportValidationErrors,
  type OaImportRowError,
} from '../../../utils/kuaioaSpreadsheetImport';

type EmpRow = { id: number; employee_code?: string | null; full_name?: string | null };

const RewardsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [employeeOptions, setEmployeeOptions] = useState<Array<{ label: string; value: number }>>(
    [],
  );
  const [employees, setEmployees] = useState<EmpRow[]>([]);

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
    })();
  }, []);

  const fields = useMemo(
    () => [
      { name: 'reward_code', labelKey: 'app.kuaioa.reward.code', width: 140 },
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
        name: 'amount',
        labelKey: 'app.kuaioa.reward.amount',
        type: 'number' as const,
        required: true,
        width: 110,
      },
      { name: 'reason', labelKey: 'app.kuaioa.reward.reason', width: 180 },
      { name: 'status', labelKey: 'common.status', width: 90, hideInForm: true },
      { name: 'notes', labelKey: 'common.remark', type: 'textarea' as const, hideInTable: true },
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
            aliases: ['姓名', '员工姓名'],
          },
          {
            field: 'year_month',
            required: true,
            labelKey: 'app.kuaioa.payroll.yearMonth',
            aliases: ['月份', '年月'],
          },
          {
            field: 'amount',
            required: true,
            labelKey: 'app.kuaioa.reward.amount',
            aliases: ['金额'],
          },
          { field: 'reason', labelKey: 'app.kuaioa.reward.reason', aliases: ['原因', '奖励原因'] },
          { field: 'notes', labelKey: 'common.remark', aliases: ['备注'] },
        ],
        ['EMP001', '张三', '2026-09', '100', '全勤奖', ''],
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
    if (
      parsed.headers.every(
        (h) => !importTemplate.importHeaderMap[h] && !importTemplate.importHeaderMap[h.replace(/^\*/, '')],
      )
    ) {
      messageApi.error(
        t('app.kuaioa.import.missingField', { field: t('app.kuaioa.payroll.yearMonth') }),
      );
      return false;
    }

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
      importData.push({
        year_month: yearMonth,
        employee_id: employeeId,
        amount,
        reason: cellOf(row, 'reason') || undefined,
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
      createOne: (item) => createReward(item),
      title: t('app.kuaioa.reward.importTitle'),
      successKey: 'app.kuaioa.reward.importSuccess',
    });
  };

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.reward.createButton"
      resource="kuaioa:reward"
      codeField="reward_code"
      nameField="employee_name"
      autoGenerateCode
      statusPresentation="marker"
      detailVariant="master"
      getDetailFn={getReward}
      columnPersistenceId="apps.kuaioa.reward.list-v2"
      fields={fields}
      listFn={listRewards}
      createFn={createReward}
      updateFn={updateReward}
      deleteFn={deleteReward}
      showExportButton
      onExport={async (type, keys, pageData) => {
        await runKuaioaListExport({
          type,
          keys,
          pageData,
          listFn: listRewards,
          columns: [
            { key: 'reward_code', title: t('app.kuaioa.reward.code') },
            { key: 'year_month', title: t('app.kuaioa.payroll.yearMonth') },
            { key: 'employee_name', title: t('app.kuaioa.employee.fullName') },
            { key: 'amount', title: t('app.kuaioa.reward.amount') },
            { key: 'reason', title: t('app.kuaioa.reward.reason') },
            { key: 'status', title: t('common.status') },
          ],
          filename: t('app.kuaioa.reward.exportFileName'),
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
      importTemplateName={t('app.kuaioa.reward.exportFileName')}
    />
  );
};

export default RewardsPage;
