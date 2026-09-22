import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Input, Select, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { listEmployeeMovements } from '../../../services/employees';

type Row = Record<string, unknown>;

const EmployeeMovementsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const perms = useResourcePermissions('kuaioa:employee');
  const [yearMonth, setYearMonth] = useState('');
  const [workshop, setWorkshop] = useState('');
  const [movementType, setMovementType] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);

  const typeOptions = useMemo(
    () => [
      { label: t('app.kuaioa.movement.type.hire'), value: 'hire' },
      { label: t('app.kuaioa.movement.type.leave'), value: 'leave' },
    ],
    [t],
  );

  const load = useCallback(async () => {
    if (!/^\d{4}-\d{2}$/.test(yearMonth.trim())) {
      message.error(t('app.kuaioa.payroll.yearMonthInvalid'));
      return;
    }
    setLoading(true);
    try {
      const res = await listEmployeeMovements({
        year_month: yearMonth.trim(),
        workshop_name: workshop.trim() || undefined,
        movement_type: movementType,
      });
      setRows(res.items);
    } catch (error) {
      message.error(getApiErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [message, movementType, t, workshop, yearMonth]);

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
      render: (v) =>
        v === 'temp'
          ? t('app.kuaioa.employee.employmentType.temp')
          : t('app.kuaioa.employee.employmentType.formal'),
    },
  ];

  return (
    <ListPageTemplate
      title={t('app.kuaioa.movement.title')}
      toolbarExtra={
        <Space wrap>
          <Input
            placeholder={t('app.kuaioa.payroll.yearMonth')}
            value={yearMonth}
            onChange={(e) => setYearMonth(e.target.value)}
            style={{ width: 120 }}
          />
          <Input
            placeholder={t('app.kuaioa.attendance.workshop')}
            value={workshop}
            onChange={(e) => setWorkshop(e.target.value)}
            style={{ width: 140 }}
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
    </ListPageTemplate>
  );
};

export default EmployeeMovementsPage;
