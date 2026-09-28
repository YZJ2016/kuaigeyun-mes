import React, { useEffect, useMemo, useState } from 'react';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import { listEmployees } from '../../../services/employees';
import {
  createLeaveRequest,
  deleteLeaveRequest,
  getLeaveRequest,
  listLeaveRequests,
  updateLeaveRequest,
} from '../../../services/leave';
import { buildLeaveTypeOptions, buildOaApprovalStatusEnum } from '../../../utils/oaFormEnums';
import { computeInclusiveCalendarDays } from '../../../utils/oaFormDateUtils';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import {
  loadOaProductionLineNameOptions,
  loadOaWorkshopNameOptions,
} from '../../../utils/oaWorkshopOptions';
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

function computeSameDayLeaveHours(startAt: unknown, endAt: unknown): number | null {
  if (!startAt || !endAt) return null;
  const start = dayjs(startAt as string | Date);
  const end = dayjs(endAt as string | Date);
  if (!start.isValid() || !end.isValid() || end.isBefore(start)) return null;
  if (!start.isSame(end, 'day')) return null;
  const hours = end.diff(start, 'minute') / 60;
  if (hours <= 0 || hours >= 8) return null;
  return Math.round(hours * 100) / 100;
}

function formatLeaveDateRange(startAt: unknown, endAt: unknown): string {
  const start = startAt ? dayjs(startAt as string | Date) : null;
  const end = endAt ? dayjs(endAt as string | Date) : null;
  if (!start?.isValid() || !end?.isValid()) return '';
  const sd = start.format('YYYY-MM-DD');
  const ed = end.format('YYYY-MM-DD');
  return sd === ed ? sd : `${sd}~${ed}`;
}

const LeavePage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const statusEnum = useMemo(() => buildOaApprovalStatusEnum(t), [t]);
  const leaveTypeOptions = useMemo(() => buildLeaveTypeOptions(t), [t]);
  const [employeeOptions, setEmployeeOptions] = useState<Array<{ label: string; value: number }>>(
    [],
  );
  const [employees, setEmployees] = useState<EmpRow[]>([]);
  const [employeeWorkshop, setEmployeeWorkshop] = useState<
    Record<number, { workshop?: string; line?: string; name?: string }>
  >({});
  const [workshopOptions, setWorkshopOptions] = useState<Array<{ label: string; value: string }>>(
    [],
  );
  const [lineOptions, setLineOptions] = useState<Array<{ label: string; value: string }>>([]);

  useEffect(() => {
    void (async () => {
      try {
        const [emps, workshops, lines] = await Promise.all([
          listEmployees({ status: 'active' }),
          loadOaWorkshopNameOptions(),
          loadOaProductionLineNameOptions(),
        ]);
        setEmployees(emps.items as EmpRow[]);
        setEmployeeOptions(
          emps.items.map((e) => ({
            label: `${e.employee_code || ''} ${e.full_name}`.trim(),
            value: Number(e.id),
          })),
        );
        const map: Record<number, { workshop?: string; line?: string; name?: string }> = {};
        for (const e of emps.items) {
          map[Number(e.id)] = {
            workshop: e.workshop_name ? String(e.workshop_name) : undefined,
            line: e.production_line_name ? String(e.production_line_name) : undefined,
            name: e.full_name ? String(e.full_name) : undefined,
          };
        }
        setEmployeeWorkshop(map);
        setWorkshopOptions(workshops);
        setLineOptions(lines.map(({ label, value }) => ({ label, value })));
      } catch (error) {
        message.error(getApiErrorMessage(error));
        setEmployeeOptions([]);
        setEmployees([]);
        setEmployeeWorkshop({});
        setWorkshopOptions([]);
        setLineOptions([]);
      }
    })();
  }, [message]);

  const fields = useMemo(
    () => [
      { name: 'request_code', labelKey: 'app.kuaioa.leave.code', width: 150 },
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
        name: 'workshop_name',
        labelKey: 'app.kuaioa.attendance.workshop',
        type: 'select' as const,
        options: workshopOptions,
        width: 120,
      },
      {
        name: 'production_line_name',
        labelKey: 'app.kuaioa.attendance.productionLine',
        type: 'select' as const,
        options: lineOptions,
        width: 120,
      },
      {
        name: 'leave_type',
        labelKey: 'app.kuaioa.leave.type',
        width: 100,
        required: true,
        type: 'select' as const,
        options: leaveTypeOptions,
      },
      {
        name: 'title',
        labelKey: 'app.kuaioa.leave.title',
        width: 200,
        hideInForm: true,
      },
      {
        name: 'start_at',
        labelKey: 'app.kuaioa.leave.startAt',
        type: 'datetime' as const,
        width: 160,
        required: true,
      },
      {
        name: 'end_at',
        labelKey: 'app.kuaioa.leave.endAt',
        type: 'datetime' as const,
        width: 160,
        required: true,
      },
      { name: 'days', labelKey: 'app.kuaioa.leave.days', width: 80, type: 'number' as const },
      {
        name: 'leave_hours',
        labelKey: 'app.kuaioa.leave.leaveHours',
        width: 100,
        type: 'number' as const,
        hideInTable: true,
      },
      {
        name: 'deduct_enabled',
        labelKey: 'app.kuaioa.leave.deductEnabled',
        type: 'switch' as const,
        hideInTable: true,
      },
      {
        name: 'deduct_amount',
        labelKey: 'app.kuaioa.leave.deductAmount',
        type: 'number' as const,
        hideInTable: true,
      },
      { name: 'applicant_name', labelKey: 'app.kuaioa.common.applicant', width: 100, hideInForm: true },
      { name: 'department_name', labelKey: 'app.kuaioa.common.department', hideInTable: true },
      { name: 'destination', labelKey: 'app.kuaioa.leave.destination', hideInTable: true },
      { name: 'reason', labelKey: 'app.kuaioa.leave.reason', hideInTable: true, type: 'textarea' as const },
      { name: 'status', labelKey: 'common.status', width: 100 },
      { name: 'notes', labelKey: 'common.remark', hideInTable: true, type: 'textarea' as const },
    ],
    [employeeOptions, leaveTypeOptions, lineOptions, workshopOptions],
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
            field: 'leave_type',
            required: true,
            labelKey: 'app.kuaioa.leave.type',
            aliases: ['请假类型', '类型'],
            options: leaveTypeOptions.map((o) => o.label),
          },
          {
            field: 'start_at',
            required: true,
            labelKey: 'app.kuaioa.leave.startAt',
            aliases: ['开始时间'],
          },
          {
            field: 'end_at',
            required: true,
            labelKey: 'app.kuaioa.leave.endAt',
            aliases: ['结束时间'],
          },
          {
            field: 'workshop_name',
            labelKey: 'app.kuaioa.attendance.workshop',
            aliases: ['车间', '所属车间'],
          },
          {
            field: 'production_line_name',
            labelKey: 'app.kuaioa.attendance.productionLine',
            aliases: ['产线'],
          },
          {
            field: 'deduct_enabled',
            labelKey: 'app.kuaioa.leave.deductEnabled',
            aliases: ['是否扣款', '是否扣钱'],
            options: [t('common.yes'), t('common.no')],
          },
          {
            field: 'deduct_amount',
            labelKey: 'app.kuaioa.leave.deductAmount',
            aliases: ['扣款金额', '扣钱金额'],
          },
          { field: 'reason', labelKey: 'app.kuaioa.leave.reason', aliases: ['事由'] },
          { field: 'notes', labelKey: 'common.remark', aliases: ['备注'] },
        ],
        [
          t('app.kuaioa.leave.importExample.employeeCode'),
          t('app.kuaioa.leave.importExample.employeeName'),
          leaveTypeOptions[0]?.label || '',
          '2026-09-01 08:00:00',
          '2026-09-01 17:00:00',
          '',
          '',
          t('common.no'),
          '',
          '',
          '',
        ],
      ),
    [leaveTypeOptions, t],
  );

  const handleImport = async (data: unknown[][]) => {
    const parsed = collectOaImportNonEmptyRows(data);
    if (!parsed) {
      message.warning(t('app.kuaioa.import.empty'));
      return false;
    }
    if (parsed.rows.length === 0) {
      message.warning(t('app.kuaioa.import.noRows'));
      return false;
    }
    const cellOf = buildOaImportCellReader(parsed.headers, importTemplate.importHeaderMap);
    const importData: Record<string, unknown>[] = [];
    const errors: OaImportRowError[] = [];
    parsed.rows.forEach((row, rowIndex) => {
      if (!Array.isArray(row)) return;
      const actualRowIndex = rowIndex + 3;
      const employeeId = resolveOaEmployeeId(
        cellOf(row, 'employee_code'),
        cellOf(row, 'employee_name'),
        employees,
      );
      if (!employeeId) {
        errors.push({ row: actualRowIndex, message: t('app.kuaioa.import.employeeNotFound') });
        return;
      }
      const leaveTypeRaw = cellOf(row, 'leave_type');
      const leaveType = resolveOaOptionValue(leaveTypeRaw, leaveTypeOptions);
      if (!leaveType) {
        errors.push({
          row: actualRowIndex,
          message: t('app.kuaioa.import.missingField', { field: t('app.kuaioa.leave.type') }),
        });
        return;
      }
      const startAt = cellOf(row, 'start_at');
      const endAt = cellOf(row, 'end_at');
      if (!startAt || !endAt) {
        errors.push({
          row: actualRowIndex,
          message: t('app.kuaioa.import.missingField', {
            field: `${t('app.kuaioa.leave.startAt')}/${t('app.kuaioa.leave.endAt')}`,
          }),
        });
        return;
      }
      const deductRaw = cellOf(row, 'deduct_enabled');
      const deductEnabled =
        deductRaw === t('common.yes') ||
        deductRaw === '1' ||
        deductRaw.toLowerCase() === 'true' ||
        deductRaw === '是';
      const deductAmountRaw = cellOf(row, 'deduct_amount');
      const deductAmount =
        deductEnabled && deductAmountRaw ? Number(deductAmountRaw) : null;
      importData.push({
        employee_id: employeeId,
        leave_type: leaveType,
        start_at: startAt,
        end_at: endAt,
        workshop_name: cellOf(row, 'workshop_name') || undefined,
        production_line_name: cellOf(row, 'production_line_name') || undefined,
        deduct_enabled: deductEnabled,
        deduct_amount: deductAmount,
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
      messageApi: message,
      items: importData,
      createOne: (item) => createLeaveRequest(item),
      title: t('app.kuaioa.leave.importTitle'),
      successKey: 'app.kuaioa.leave.importSuccess',
    });
  };

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.leave.createButton"
      resource="kuaioa:leave"
      codeField="request_code"
      nameField="title"
      autoGenerateCode
      statusEnum={statusEnum}
      statusPresentation="lifecycle"
      detailVariant="approval"
      getDetailFn={getLeaveRequest}
      columnPersistenceId="apps.kuaioa.leave.list-v4"
      auditWorkflow={{
        entityType: 'kuaioa_leave',
        resourcePrefix: 'kuaioa:leave',
        auditNodeKey: 'kuaioa_leave',
        entityNameKey: 'app.kuaioa.leave.entityName',
      }}
      onFormValuesChange={(changed, allValues, form) => {
        if ('start_at' in changed || 'end_at' in changed) {
          const days = computeInclusiveCalendarDays(allValues.start_at, allValues.end_at);
          if (days != null && days > 0) {
            form.setFieldValue('days', days);
          }
          const hours = computeSameDayLeaveHours(allValues.start_at, allValues.end_at);
          if (hours != null) {
            form.setFieldValue('leave_hours', hours);
            form.setFieldValue('days', Math.round((hours / 8) * 100) / 100);
          }
        }
        if ('employee_id' in changed) {
          const snap = employeeWorkshop[Number(changed.employee_id)];
          if (snap?.workshop) form.setFieldValue('workshop_name', snap.workshop);
          if (snap?.line) form.setFieldValue('production_line_name', snap.line);
        }
        if ('deduct_enabled' in changed && !changed.deduct_enabled) {
          form.setFieldValue('deduct_amount', undefined);
        }
      }}
      mapFormValuesToPayload={(values) => {
        const {
          employee_name: _n,
          applicant_name: _a,
          title: _title,
          ...rest
        } = values;
        const empId = Number(values.employee_id);
        const snap = Number.isFinite(empId) ? employeeWorkshop[empId] : undefined;
        const typeLabel =
          leaveTypeOptions.find((o) => o.value === values.leave_type)?.label ||
          String(values.leave_type ?? '');
        const empName = snap?.name || String(values.employee_name ?? '').trim();
        const range = formatLeaveDateRange(values.start_at, values.end_at);
        const title = [typeLabel, empName, range].filter(Boolean).join(' ').slice(0, 200);
        const deductEnabled = Boolean(values.deduct_enabled);
        return {
          ...rest,
          title,
          deduct_enabled: deductEnabled,
          deduct_amount: deductEnabled ? values.deduct_amount ?? null : null,
        };
      }}
      fields={fields}
      listFn={listLeaveRequests}
      createFn={createLeaveRequest}
      updateFn={updateLeaveRequest}
      deleteFn={deleteLeaveRequest}
      showExportButton
      onExport={async (type, keys, pageData) => {
        await runKuaioaListExport({
          type,
          keys,
          pageData,
          listFn: listLeaveRequests,
          columns: [
            { key: 'request_code', title: t('app.kuaioa.leave.code') },
            { key: 'employee_name', title: t('app.kuaioa.employee.fullName') },
            { key: 'workshop_name', title: t('app.kuaioa.attendance.workshop') },
            { key: 'production_line_name', title: t('app.kuaioa.attendance.productionLine') },
            { key: 'leave_type', title: t('app.kuaioa.leave.type') },
            { key: 'title', title: t('app.kuaioa.leave.title') },
            { key: 'start_at', title: t('app.kuaioa.leave.startAt') },
            { key: 'end_at', title: t('app.kuaioa.leave.endAt') },
            { key: 'days', title: t('app.kuaioa.leave.days') },
            { key: 'status', title: t('common.status') },
          ],
          filename: t('app.kuaioa.leave.exportFileName'),
          messageApi: message,
          noDataText: t('common.exportNoData'),
        });
      }}
      showImportButton
      onImport={handleImport}
      importHeaders={importTemplate.importHeaders}
      importExampleRow={importTemplate.importExampleRow}
      importColumnOptions={importTemplate.importColumnOptions}
      importFieldMap={importTemplate.importHeaderMap}
      importTemplateName={t('app.kuaioa.leave.exportFileName')}
    />
  );
};

export default LeavePage;
