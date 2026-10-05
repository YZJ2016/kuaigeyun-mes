import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { App, Button, DatePicker, Form, Select, Space, Table, Typography } from 'antd';
import {
  ProFormDatePicker,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
} from '@ant-design/pro-components';
import type { ColumnsType } from 'antd/es/table';
import type { Dayjs } from 'dayjs';
import dayjs from 'dayjs';
import {
  FormModalTemplate,
  ListPageTemplate,
  MODAL_CONFIG,
} from '../../../../../components/layout-templates';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { getDepartmentTree } from '../../../../../services/department';
import {
  createEmployee,
  listEmployeeMovements,
  listEmployees,
  updateEmployee,
} from '../../../services/employees';
import {
  buildOaEmploymentTypeOptions,
  resolveOaEmploymentTypeLabel,
} from '../../../utils/oaFormEnums';
import { flattenDepartmentOptions } from '../../../utils/oaLookupFields';
import { loadOaWorkshopNameOptions } from '../../../utils/oaWorkshopOptions';

type Row = Record<string, unknown>;

type RegisterKind = 'hire' | 'temp' | 'leave' | null;

const EmployeeMovementsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const perms = useResourcePermissions('kuaioa:employee');
  const [yearMonth, setYearMonth] = useState<Dayjs>(() => dayjs());
  const [workshop, setWorkshop] = useState<string | undefined>();
  const [movementType, setMovementType] = useState<string | undefined>();
  const [workshopOptions, setWorkshopOptions] = useState<{ label: string; value: string }[]>([]);
  const [activeEmployees, setActiveEmployees] = useState<Row[]>([]);
  const [departmentOptions, setDepartmentOptions] = useState<{ label: string; value: string }[]>(
    [],
  );
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);
  const [registerKind, setRegisterKind] = useState<RegisterKind>(null);
  const [hireForm] = Form.useForm();
  const [leaveForm] = Form.useForm();
  const deepLinkHandledRef = React.useRef<string | null>(null);

  const employmentOptions = useMemo(() => buildOaEmploymentTypeOptions(t), [t]);
  const payMethodOptions = useMemo(
    () => [
      { label: t('app.kuaioa.employee.payMethod.piece'), value: 'piece' },
      { label: t('app.kuaioa.employee.payMethod.time'), value: 'time' },
      { label: t('app.kuaioa.employee.payMethod.line'), value: 'line' },
    ],
    [t],
  );
  const typeOptions = useMemo(
    () => [
      { label: t('app.kuaioa.movement.type.hire'), value: 'hire' },
      { label: t('app.kuaioa.movement.type.leave'), value: 'leave' },
    ],
    [t],
  );
  const activeEmployeeOptions = useMemo(
    () =>
      activeEmployees.map((e) => ({
        value: Number(e.id),
        label: `${String(e.full_name ?? '')}（${String(e.employee_code ?? '')}）`.trim(),
      })),
    [activeEmployees],
  );

  const openRegister = useCallback(
    (kind: 'hire' | 'temp' | 'leave') => {
      if (kind === 'leave') {
        leaveForm.resetFields();
        leaveForm.setFieldsValue({ leave_date: dayjs() });
      } else {
        hireForm.resetFields();
        hireForm.setFieldsValue({
          hire_date: dayjs(),
          employment_type: kind === 'temp' ? 'temp' : 'formal',
          pay_method: 'time',
        });
      }
      setRegisterKind(kind);
    },
    [hireForm, leaveForm],
  );

  const closeRegister = useCallback(() => {
    setRegisterKind(null);
    deepLinkHandledRef.current = null;
    if (searchParams.get('register')) {
      const next = new URLSearchParams(searchParams);
      next.delete('register');
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    const reg = searchParams.get('register');
    if (reg !== 'hire' && reg !== 'temp' && reg !== 'leave') {
      deepLinkHandledRef.current = null;
      return;
    }
    if (deepLinkHandledRef.current === reg) return;
    if ((reg === 'hire' || reg === 'temp') && !perms.canCreate) return;
    if (reg === 'leave' && !perms.canUpdate) return;
    deepLinkHandledRef.current = reg;
    openRegister(reg);
  }, [openRegister, perms.canCreate, perms.canUpdate, searchParams]);

  const refreshEmployeeOptions = useCallback(async () => {
    const [empRes, workshops] = await Promise.all([
      listEmployees({ status: 'active' }),
      loadOaWorkshopNameOptions(),
    ]);
    setActiveEmployees(empRes.items);
    setWorkshopOptions(workshops);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [empRes, deptTree, workshops] = await Promise.all([
          listEmployees({ status: 'active' }),
          getDepartmentTree({ host_resource: 'kuaioa:employee' }),
          loadOaWorkshopNameOptions(),
        ]);
        if (cancelled) return;
        setActiveEmployees(empRes.items);
        setWorkshopOptions(workshops);
        setDepartmentOptions(flattenDepartmentOptions(deptTree.items || []));
      } catch {
        if (!cancelled) {
          setActiveEmployees([]);
          setWorkshopOptions([]);
          setDepartmentOptions([]);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async () => {
    if (!yearMonth?.isValid()) {
      message.error(t('app.kuaioa.payroll.yearMonthInvalid'));
      return;
    }
    const ym = yearMonth.format('YYYY-MM');
    setLoading(true);
    try {
      const res = await listEmployeeMovements({
        year_month: ym,
        workshop_name: workshop || undefined,
        movement_type: movementType,
      });
      setRows(res.items);
    } catch (error) {
      message.error(getApiErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [message, movementType, t, workshop, yearMonth]);

  useEffect(() => {
    void load();
  }, [load]);

  const exportColumns = useMemo(
    () => [
      { key: 'movement_type', title: t('app.kuaioa.movement.typeLabel') },
      { key: 'employee_name', title: t('app.kuaioa.employee.fullName') },
      { key: 'employee_code', title: t('app.kuaioa.employee.code') },
      { key: 'workshop_name', title: t('app.kuaioa.attendance.workshop') },
      { key: 'movement_date', title: t('app.kuaioa.movement.date') },
      { key: 'employment_type', title: t('app.kuaioa.employee.employmentTypeLabel') },
    ],
    [t],
  );

  const columns: ColumnsType<Row> = [
    {
      title: t('app.kuaioa.movement.typeLabel'),
      dataIndex: 'movement_type',
      width: 100,
      render: (v) =>
        v === 'hire' ? t('app.kuaioa.movement.type.hire') : t('app.kuaioa.movement.type.leave'),
    },
    { title: t('app.kuaioa.employee.fullName'), dataIndex: 'employee_name', width: 120 },
    { title: t('app.kuaioa.employee.code'), dataIndex: 'employee_code', width: 120 },
    { title: t('app.kuaioa.attendance.workshop'), dataIndex: 'workshop_name', width: 140 },
    { title: t('app.kuaioa.movement.date'), dataIndex: 'movement_date', width: 120 },
    {
      title: t('app.kuaioa.employee.employmentTypeLabel'),
      dataIndex: 'employment_type',
      width: 100,
      render: (v) => resolveOaEmploymentTypeLabel(v as string | undefined, t),
    },
  ];

  const handleHireFinish = async (values: Record<string, unknown>) => {
    const hireDay = values.hire_date ? dayjs(values.hire_date as string | Dayjs) : null;
    if (!hireDay?.isValid()) {
      message.error(t('app.kuaioa.movement.hireDateRequired'));
      return;
    }
    try {
      await createEmployee({
        full_name: String(values.full_name ?? '').trim(),
        department_name: values.department_name
          ? String(values.department_name).trim()
          : undefined,
        workshop_name: values.workshop_name ? String(values.workshop_name).trim() : undefined,
        employment_type:
          registerKind === 'temp' ? 'temp' : String(values.employment_type ?? 'formal'),
        pay_method: String(values.pay_method ?? 'time'),
        phone: values.phone ? String(values.phone).trim() : undefined,
        hire_date: hireDay.format('YYYY-MM-DD'),
        status: 'active',
        notes: values.notes ? String(values.notes).trim() : undefined,
      });
      message.success(
        registerKind === 'temp'
          ? t('app.kuaioa.movement.tempSuccess')
          : t('app.kuaioa.movement.hireSuccess'),
      );
      closeRegister();
      await Promise.all([load(), refreshEmployeeOptions()]);
    } catch (error) {
      message.error(getApiErrorMessage(error));
    }
  };

  const handleLeaveFinish = async (values: Record<string, unknown>) => {
    const employeeId = Number(values.employee_id);
    const leaveDay = values.leave_date ? dayjs(values.leave_date as string | Dayjs) : null;
    if (!Number.isFinite(employeeId) || employeeId <= 0) {
      message.error(t('app.kuaioa.movement.employeeRequired'));
      return;
    }
    if (!leaveDay?.isValid()) {
      message.error(t('app.kuaioa.movement.leaveDateRequired'));
      return;
    }
    try {
      const payload: Record<string, unknown> = {
        leave_date: leaveDay.format('YYYY-MM-DD'),
        status: 'left',
      };
      const notes = values.notes ? String(values.notes).trim() : '';
      if (notes) payload.notes = notes;
      await updateEmployee(employeeId, payload);
      message.success(t('app.kuaioa.movement.leaveSuccess'));
      closeRegister();
      await Promise.all([load(), refreshEmployeeOptions()]);
    } catch (error) {
      message.error(getApiErrorMessage(error));
    }
  };

  return (
    <ListPageTemplate
      toolbarExtra={
        <Space wrap>
          {perms.canCreate ? (
            <Button type="primary" onClick={() => openRegister('hire')}>
              {t('app.kuaioa.movement.registerHire')}
            </Button>
          ) : null}
          {perms.canCreate ? (
            <Button onClick={() => openRegister('temp')}>
              {t('app.kuaioa.movement.registerTemp')}
            </Button>
          ) : null}
          {perms.canUpdate ? (
            <Button onClick={() => openRegister('leave')}>
              {t('app.kuaioa.movement.registerLeave')}
            </Button>
          ) : null}
          <DatePicker
            picker="month"
            allowClear={false}
            value={yearMonth}
            onChange={(v) => {
              if (v) setYearMonth(v);
            }}
            style={{ width: 140 }}
            placeholder={t('app.kuaioa.payroll.yearMonth')}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaioa.attendance.workshop')}
            options={workshopOptions}
            value={workshop}
            onChange={setWorkshop}
            style={{ width: 160 }}
          />
          <Select
            allowClear
            placeholder={t('app.kuaioa.movement.typeLabel')}
            options={typeOptions}
            value={movementType}
            onChange={setMovementType}
            style={{ width: 120 }}
          />
          <Button type="primary" loading={loading} onClick={() => void load()}>
            {t('common.search')}
          </Button>
          {perms.canExport ? (
            <Button
              disabled={rows.length === 0}
              onClick={() =>
                void downloadRecordsAsXlsx(
                  rows,
                  exportColumns,
                  t('app.kuaioa.movement.exportFileName'),
                )
              }
            >
              {t('common.export')}
            </Button>
          ) : null}
        </Space>
      }
    >
      <Typography.Paragraph type="secondary">{t('app.kuaioa.movement.hint')}</Typography.Paragraph>
      <Table<Row>
        size="small"
        loading={loading}
        rowKey={(r, i) => `${String(r.employee_id)}-${String(r.movement_type)}-${i}`}
        columns={columns}
        dataSource={rows}
        pagination={false}
        bordered
      />

      <FormModalTemplate
        open={registerKind === 'hire' || registerKind === 'temp'}
        title={
          registerKind === 'temp'
            ? t('app.kuaioa.movement.registerTemp')
            : t('app.kuaioa.movement.registerHire')
        }
        onClose={closeRegister}
        onFinish={handleHireFinish}
        form={hireForm}
        grid
        width={MODAL_CONFIG.STANDARD_WIDTH}
        isEdit={false}
      >
        <ProFormText
          name="full_name"
          label={t('app.kuaioa.employee.fullName')}
          rules={[{ required: true, message: t('app.kuaioa.employee.importNameRequired') }]}
          colProps={{ span: 12 }}
        />
        <ProFormSelect
          name="department_name"
          label={t('app.kuaioa.common.department')}
          options={departmentOptions}
          showSearch
          colProps={{ span: 12 }}
          fieldProps={{ optionFilterProp: 'label' }}
        />
        <ProFormSelect
          name="workshop_name"
          label={t('app.kuaioa.employee.workshop')}
          options={workshopOptions}
          showSearch
          allowClear
          colProps={{ span: 12 }}
          fieldProps={{ optionFilterProp: 'label' }}
        />
        <ProFormText
          name="phone"
          label={t('app.kuaioa.employee.phone')}
          colProps={{ span: 12 }}
        />
        <ProFormSelect
          name="employment_type"
          label={t('app.kuaioa.employee.employmentType')}
          options={employmentOptions}
          rules={[{ required: true }]}
          colProps={{ span: 12 }}
          disabled={registerKind === 'temp'}
        />
        <ProFormSelect
          name="pay_method"
          label={t('app.kuaioa.employee.payMethod')}
          options={payMethodOptions}
          rules={[{ required: true }]}
          colProps={{ span: 12 }}
        />
        <ProFormDatePicker
          name="hire_date"
          label={t('app.kuaioa.employee.hireDate')}
          rules={[{ required: true, message: t('app.kuaioa.movement.hireDateRequired') }]}
          colProps={{ span: 12 }}
          fieldProps={{ style: { width: '100%' } }}
        />
        <ProFormTextArea name="notes" label={t('common.remark')} colProps={{ span: 24 }} />
      </FormModalTemplate>

      <FormModalTemplate
        open={registerKind === 'leave'}
        title={t('app.kuaioa.movement.registerLeave')}
        onClose={closeRegister}
        onFinish={handleLeaveFinish}
        form={leaveForm}
        grid
        width={MODAL_CONFIG.STANDARD_WIDTH}
        isEdit={false}
      >
        <ProFormSelect
          name="employee_id"
          label={t('app.kuaioa.employee.fullName')}
          options={activeEmployeeOptions}
          rules={[{ required: true, message: t('app.kuaioa.movement.employeeRequired') }]}
          showSearch
          colProps={{ span: 12 }}
          fieldProps={{ optionFilterProp: 'label' }}
        />
        <ProFormDatePicker
          name="leave_date"
          label={t('app.kuaioa.employee.leaveDate')}
          rules={[{ required: true, message: t('app.kuaioa.movement.leaveDateRequired') }]}
          colProps={{ span: 12 }}
          fieldProps={{ style: { width: '100%' } }}
        />
        <ProFormTextArea name="notes" label={t('common.remark')} colProps={{ span: 24 }} />
      </FormModalTemplate>
    </ListPageTemplate>
  );
};

export default EmployeeMovementsPage;
