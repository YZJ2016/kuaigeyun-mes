import React, { useEffect, useMemo, useState } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import { listEmployees } from '../../../services/employees';
import {
  createDailyAttendance,
  deleteDailyAttendance,
  getDailyAttendance,
  listDailyAttendance,
  updateDailyAttendance,
} from '../../../services/attendanceDaily';
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
import { buildOaAttendanceDailyResultOptions } from '../../../utils/oaFormEnums';

type EmpRow = {
  id: number;
  employee_code?: string | null;
  full_name?: string | null;
  department_name?: string | null;
};

const AttendanceDailyPage: React.FC = () => {
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

  const resultOptions = useMemo(() => buildOaAttendanceDailyResultOptions(t), [t]);

  const resultLabelByCode = useMemo(() => {
    const map = new Map<string, string>();
    for (const opt of resultOptions) map.set(opt.value, opt.label);
    return map;
  }, [resultOptions]);

  const resultCodeByLabel = useMemo(() => {
    const map = new Map<string, string>();
    for (const opt of resultOptions) {
      map.set(opt.label, opt.value);
      map.set(opt.value, opt.value);
    }
    return map;
  }, [resultOptions]);

  const departmentExtraOptions = useMemo(() => {
    const names = new Set<string>();
    for (const emp of employees) {
      const name = String(emp.department_name || '').trim();
      if (name) names.add(name);
    }
    return Array.from(names)
      .sort((a, b) => a.localeCompare(b, 'zh-CN'))
      .map((name) => ({ label: name, value: name }));
  }, [employees]);

  const fields = useMemo(
    () => [
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
        labelKey: 'app.kuaioa.attendanceDaily.employeeName',
        width: 100,
        hideInForm: true,
      },
      {
        name: 'employee_code',
        labelKey: 'app.kuaioa.attendanceDaily.employeeCode',
        width: 100,
        hideInForm: true,
      },
      {
        name: 'department_name',
        labelKey: 'app.kuaioa.common.department',
        type: 'department' as const,
        width: 120,
      },
      {
        name: 'work_date',
        labelKey: 'app.kuaioa.attendanceDaily.workDate',
        type: 'date' as const,
        required: true,
        width: 110,
      },
      {
        name: 'clock_in_1',
        labelKey: 'app.kuaioa.attendanceDaily.clockIn1',
        type: 'time' as const,
        width: 110,
      },
      {
        name: 'clock_out_1',
        labelKey: 'app.kuaioa.attendanceDaily.clockOut1',
        type: 'time' as const,
        width: 110,
      },
      {
        name: 'clock_in_2',
        labelKey: 'app.kuaioa.attendanceDaily.clockIn2',
        type: 'time' as const,
        width: 110,
      },
      {
        name: 'clock_out_2',
        labelKey: 'app.kuaioa.attendanceDaily.clockOut2',
        type: 'time' as const,
        width: 110,
      },
      {
        name: 'clock_in_3',
        labelKey: 'app.kuaioa.attendanceDaily.clockIn3',
        type: 'time' as const,
        width: 110,
      },
      {
        name: 'clock_out_3',
        labelKey: 'app.kuaioa.attendanceDaily.clockOut3',
        type: 'time' as const,
        width: 110,
      },
      {
        name: 'result',
        labelKey: 'app.kuaioa.attendanceDaily.result',
        type: 'select' as const,
        options: resultOptions,
        width: 100,
      },
      {
        name: 'expected_hours',
        labelKey: 'app.kuaioa.attendanceDaily.expectedHours',
        type: 'number' as const,
        width: 110,
      },
      {
        name: 'paid_hours',
        labelKey: 'app.kuaioa.attendanceDaily.paidHours',
        type: 'number' as const,
        width: 110,
      },
      {
        name: 'actual_hours',
        labelKey: 'app.kuaioa.attendanceDaily.actualHours',
        type: 'number' as const,
        width: 110,
      },
      {
        name: 'late_minutes',
        labelKey: 'app.kuaioa.attendanceDaily.lateMinutes',
        type: 'number' as const,
        width: 110,
      },
      {
        name: 'early_leave_minutes',
        labelKey: 'app.kuaioa.attendanceDaily.earlyLeaveMinutes',
        type: 'number' as const,
        width: 110,
      },
      {
        name: 'ot_hours',
        labelKey: 'app.kuaioa.attendanceDaily.otHours',
        type: 'number' as const,
        width: 110,
      },
      {
        name: 'notes',
        labelKey: 'common.remark',
        type: 'textarea' as const,
        hideInTable: true,
      },
    ],
    [employeeOptions, resultOptions],
  );

  const importTemplate = useMemo(
    () =>
      buildFactoryImportTemplate(
        t,
        [
          {
            field: 'employee_name',
            required: true,
            labelKey: 'app.kuaioa.attendanceDaily.employeeName',
            aliases: ['姓名'],
          },
          {
            field: 'employee_code',
            labelKey: 'app.kuaioa.attendanceDaily.employeeCode',
            aliases: ['工号', '员工编号'],
          },
          {
            field: 'department_name',
            labelKey: 'app.kuaioa.common.department',
            aliases: ['部门'],
          },
          {
            field: 'work_date',
            required: true,
            labelKey: 'app.kuaioa.attendanceDaily.workDate',
            aliases: ['日期'],
          },
          {
            field: 'clock_in_1',
            labelKey: 'app.kuaioa.attendanceDaily.clockIn1',
            aliases: ['上班1打卡时间'],
          },
          {
            field: 'clock_out_1',
            labelKey: 'app.kuaioa.attendanceDaily.clockOut1',
            aliases: ['下班1打卡时间'],
          },
          {
            field: 'clock_in_2',
            labelKey: 'app.kuaioa.attendanceDaily.clockIn2',
            aliases: ['上班2打卡时间'],
          },
          {
            field: 'clock_out_2',
            labelKey: 'app.kuaioa.attendanceDaily.clockOut2',
            aliases: ['下班2打卡时间'],
          },
          {
            field: 'clock_in_3',
            labelKey: 'app.kuaioa.attendanceDaily.clockIn3',
            aliases: ['上班3打卡时间'],
          },
          {
            field: 'clock_out_3',
            labelKey: 'app.kuaioa.attendanceDaily.clockOut3',
            aliases: ['下班3打卡时间'],
          },
          {
            field: 'result',
            labelKey: 'app.kuaioa.attendanceDaily.result',
            aliases: ['考勤结果'],
            options: resultOptions.map((o) => o.label),
          },
          {
            field: 'expected_hours',
            labelKey: 'app.kuaioa.attendanceDaily.expectedHours',
            aliases: ['应出勤 (小时)', '应出勤(小时)', '应出勤'],
          },
          {
            field: 'paid_hours',
            labelKey: 'app.kuaioa.attendanceDaily.paidHours',
            aliases: ['计薪时长 (小时)', '计薪时长(小时)', '计薪时长'],
          },
          {
            field: 'actual_hours',
            labelKey: 'app.kuaioa.attendanceDaily.actualHours',
            aliases: ['实际出勤 (小时)', '实际出勤(小时)', '实际出勤'],
          },
          {
            field: 'late_minutes',
            labelKey: 'app.kuaioa.attendanceDaily.lateMinutes',
            aliases: ['迟到时长 (分钟)', '迟到时长(分钟)', '迟到时长'],
          },
          {
            field: 'early_leave_minutes',
            labelKey: 'app.kuaioa.attendanceDaily.earlyLeaveMinutes',
            aliases: ['早退时长 (分钟)', '早退时长(分钟)', '早退时长'],
          },
          {
            field: 'ot_hours',
            labelKey: 'app.kuaioa.attendanceDaily.otHours',
            aliases: ['加班时长 (小时)', '加班时长(小时)', '加班时长'],
          },
        ],
        [
          '张三',
          'EMP001',
          '生产部',
          '2026-09-27',
          '08:00',
          '12:00',
          '13:00',
          '17:30',
          '',
          '',
          resultLabelByCode.get('normal') || '正常',
          '8',
          '8',
          '8',
          '0',
          '0',
          '0.5',
        ],
      ),
    [resultLabelByCode, resultOptions, t],
  );

  const normalizeResult = (raw: string | undefined): string | undefined => {
    if (!raw) return undefined;
    const text = raw.trim();
    if (!text) return undefined;
    return resultCodeByLabel.get(text) || text;
  };

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
    const errors: OaImportRowError[] = [];
    const items: Record<string, unknown>[] = [];

    parsed.rows.forEach((row, rowIndex) => {
      if (!Array.isArray(row)) return;
      const actualRowIndex = rowIndex + 3;
      const employeeName = cellOf(row, 'employee_name');
      const employeeCode = cellOf(row, 'employee_code');
      const workDate = cellOf(row, 'work_date');
      if (!employeeName && !employeeCode) {
        errors.push({
          row: actualRowIndex,
          message: t('app.kuaioa.attendanceDaily.importNeedEmployee'),
        });
        return;
      }
      if (!workDate) {
        errors.push({
          row: actualRowIndex,
          message: t('app.kuaioa.attendanceDaily.importNeedDate'),
        });
        return;
      }
      const empId = resolveOaEmployeeId(employeeCode, employeeName, employees);
      const emp = employees.find((e) => e.id === empId);
      items.push({
        employee_id: empId || undefined,
        employee_code: employeeCode || emp?.employee_code || undefined,
        employee_name: employeeName || emp?.full_name || undefined,
        department_name: cellOf(row, 'department_name') || emp?.department_name || undefined,
        work_date: workDate,
        clock_in_1: cellOf(row, 'clock_in_1') || undefined,
        clock_out_1: cellOf(row, 'clock_out_1') || undefined,
        clock_in_2: cellOf(row, 'clock_in_2') || undefined,
        clock_out_2: cellOf(row, 'clock_out_2') || undefined,
        clock_in_3: cellOf(row, 'clock_in_3') || undefined,
        clock_out_3: cellOf(row, 'clock_out_3') || undefined,
        result: normalizeResult(cellOf(row, 'result')),
        expected_hours: cellOf(row, 'expected_hours') || undefined,
        paid_hours: cellOf(row, 'paid_hours') || undefined,
        actual_hours: cellOf(row, 'actual_hours') || undefined,
        late_minutes: cellOf(row, 'late_minutes') || undefined,
        early_leave_minutes: cellOf(row, 'early_leave_minutes') || undefined,
        ot_hours: cellOf(row, 'ot_hours') || undefined,
      });
    });

    if (errors.length > 0) {
      showOaImportValidationErrors(t, errors);
      return false;
    }
    return runOaChunkedCreateImport({
      t,
      messageApi,
      items,
      createOne: createDailyAttendance,
      title: t('app.kuaioa.attendanceDaily.importTitle'),
      successKey: 'app.kuaioa.attendanceDaily.importSuccess',
    });
  };

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.attendanceDaily.createButton"
      resource="kuaioa:attendance-daily"
      nameField="employee_name"
      getDetailFn={getDailyAttendance}
      columnPersistenceId="apps.kuaioa.attendance-daily.list-v2"
      fields={fields}
      listFn={listDailyAttendance}
      departmentExtraOptions={departmentExtraOptions}
      onFormValuesChange={(changed, _all, form) => {
        if (!('employee_id' in changed)) return;
        const empId = Number(changed.employee_id);
        const emp = employees.find((e) => e.id === empId);
        if (!emp) return;
        form.setFieldsValue({
          employee_name: emp.full_name || undefined,
          employee_code: emp.employee_code || undefined,
          department_name: emp.department_name || undefined,
        });
      }}
      mapRecordToFormValues={(record) => {
        const rawResult = String(record.result ?? '').trim();
        return {
          ...record,
          employee_id: record.employee_id ?? undefined,
          work_date: record.work_date ?? undefined,
          // 兼容历史中文结果与 code
          result: normalizeResult(rawResult) || rawResult || undefined,
        };
      }}
      createFn={async (values) => {
        const empId = Number(values.employee_id);
        const emp = employees.find((e) => e.id === empId);
        return createDailyAttendance({
          ...values,
          employee_id: empId || undefined,
          employee_code: emp?.employee_code,
          employee_name: emp?.full_name || values.employee_name,
          department_name: values.department_name || emp?.department_name,
          result: normalizeResult(String(values.result ?? '')) || values.result,
        });
      }}
      updateFn={async (id, values) => {
        const empId = Number(values.employee_id);
        const emp = employees.find((e) => e.id === empId);
        return updateDailyAttendance(id, {
          ...values,
          employee_id: empId || undefined,
          employee_code: emp?.employee_code || values.employee_code,
          employee_name: emp?.full_name || values.employee_name,
          department_name: values.department_name || emp?.department_name,
          result: normalizeResult(String(values.result ?? '')) || values.result,
        });
      }}
      deleteFn={deleteDailyAttendance}
      showImportButton
      onImport={handleImport}
      importHeaders={importTemplate.importHeaders}
      importExampleRow={importTemplate.importExampleRow}
      importColumnOptions={importTemplate.importColumnOptions}
      importFieldMap={importTemplate.importHeaderMap}
      importTemplateName={t('app.kuaioa.attendanceDaily.exportFileName')}
      showExportButton
      onExport={async (type, keys, pageData) => {
        const mapResultLabel = (rows: Record<string, unknown>[]) =>
          rows.map((row) => ({
            ...row,
            result:
              resultLabelByCode.get(String(row.result ?? '')) ||
              row.result ||
              '',
          }));
        await runKuaioaListExport({
          type,
          keys,
          pageData: pageData ? mapResultLabel(pageData) : pageData,
          listFn: async (params) => {
            const res = await listDailyAttendance(params);
            return { ...res, items: mapResultLabel(res.items) };
          },
          columns: [
            { key: 'employee_name', title: t('app.kuaioa.attendanceDaily.employeeName') },
            { key: 'employee_code', title: t('app.kuaioa.attendanceDaily.employeeCode') },
            { key: 'department_name', title: t('app.kuaioa.common.department') },
            { key: 'work_date', title: t('app.kuaioa.attendanceDaily.workDate') },
            { key: 'clock_in_1', title: t('app.kuaioa.attendanceDaily.clockIn1') },
            { key: 'clock_out_1', title: t('app.kuaioa.attendanceDaily.clockOut1') },
            { key: 'clock_in_2', title: t('app.kuaioa.attendanceDaily.clockIn2') },
            { key: 'clock_out_2', title: t('app.kuaioa.attendanceDaily.clockOut2') },
            { key: 'clock_in_3', title: t('app.kuaioa.attendanceDaily.clockIn3') },
            { key: 'clock_out_3', title: t('app.kuaioa.attendanceDaily.clockOut3') },
            { key: 'result', title: t('app.kuaioa.attendanceDaily.result') },
            { key: 'expected_hours', title: t('app.kuaioa.attendanceDaily.expectedHours') },
            { key: 'paid_hours', title: t('app.kuaioa.attendanceDaily.paidHours') },
            { key: 'actual_hours', title: t('app.kuaioa.attendanceDaily.actualHours') },
            { key: 'late_minutes', title: t('app.kuaioa.attendanceDaily.lateMinutes') },
            { key: 'early_leave_minutes', title: t('app.kuaioa.attendanceDaily.earlyLeaveMinutes') },
            { key: 'ot_hours', title: t('app.kuaioa.attendanceDaily.otHours') },
          ],
          filename: t('app.kuaioa.attendanceDaily.exportFileName'),
          messageApi,
          noDataText: t('common.exportNoData'),
        });
      }}
    />
  );
};

export default AttendanceDailyPage;
