import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, InputNumber, Select, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { listEmployees } from '../../../services/employees';
import { getPersonalPayrollStats } from '../../../services/payroll';

type MonthRow = {
  month: number;
  balance: number;
  living: number;
};

const PersonalPayrollPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const perms = useResourcePermissions('kuaioa:payroll');
  const [year, setYear] = useState<number | null>(new Date().getFullYear());
  const [employeeId, setEmployeeId] = useState<number | null>(null);
  const [employeeOptions, setEmployeeOptions] = useState<Array<{ label: string; value: number }>>(
    [],
  );
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<Record<string, unknown> | null>(null);
  const [monthRows, setMonthRows] = useState<MonthRow[]>([]);

  useEffect(() => {
    void (async () => {
      const res = await listEmployees();
      setEmployeeOptions(
        res.items.map((e) => ({
          label: `${e.employee_code || ''} ${e.full_name}`.trim(),
          value: Number(e.id),
        })),
      );
    })();
  }, []);

  const load = useCallback(async () => {
    if (!year || year < 2000 || !employeeId) {
      message.error(t('app.kuaioa.personalPayroll.needEmployee'));
      return;
    }
    setLoading(true);
    try {
      const data = await getPersonalPayrollStats({ employee_id: employeeId, year });
      setStats(data);
      const rows: MonthRow[] = [];
      for (let m = 1; m <= 12; m += 1) {
        const wageKey = `wage_m${String(m).padStart(2, '0')}`;
        const livingKey = `living_m${String(m).padStart(2, '0')}`;
        rows.push({
          month: m,
          balance: Number(data[wageKey] || 0),
          living: Number(data[livingKey] || 0),
        });
      }
      setMonthRows(rows);
    } catch (error) {
      message.error(getApiErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [employeeId, message, t, year]);

  const exportRows = useMemo(
    () =>
      monthRows.map((r) => ({
        month: r.month,
        balance: r.balance.toFixed(2),
        living: r.living.toFixed(2),
      })),
    [monthRows],
  );

  const columns: ColumnsType<MonthRow> = [
    {
      title: t('app.kuaioa.personalPayroll.month'),
      dataIndex: 'month',
      width: 80,
      render: (m) => t('app.kuaioa.annualStats.monthWage', { month: m }),
    },
    {
      title: t('app.kuaioa.personalPayroll.balance'),
      dataIndex: 'balance',
      width: 120,
      render: (v) => Number(v).toFixed(2),
    },
    {
      title: t('app.kuaioa.payroll.livingDeduct'),
      dataIndex: 'living',
      width: 120,
      render: (v) => Number(v).toFixed(2),
    },
  ];

  return (
    <ListPageTemplate
      title={t('app.kuaioa.personalPayroll.title')}
      toolbarExtra={
        <Space wrap className="no-print">
          <InputNumber
            min={2000}
            max={2100}
            value={year ?? undefined}
            onChange={(v) => setYear(typeof v === 'number' ? v : null)}
            style={{ width: 100 }}
          />
          <Select
            showSearch
            optionFilterProp="label"
            placeholder={t('app.kuaioa.employee.fullName')}
            options={employeeOptions}
            value={employeeId ?? undefined}
            onChange={setEmployeeId}
            style={{ width: 220 }}
          />
          <Button type="primary" loading={loading} onClick={() => void load()}>
            {t('common.search')}
          </Button>
          {perms.canExport && monthRows.length > 0 ? (
            <Button
              onClick={() =>
                void downloadRecordsAsXlsx(
                  exportRows,
                  [
                    { key: 'month', title: t('app.kuaioa.personalPayroll.month') },
                    { key: 'balance', title: t('app.kuaioa.personalPayroll.balance') },
                    { key: 'living', title: t('app.kuaioa.payroll.livingDeduct') },
                  ],
                  t('app.kuaioa.personalPayroll.exportFileName'),
                )
              }
            >
              {t('common.export')}
            </Button>
          ) : null}
          {monthRows.length > 0 ? (
            <Button onClick={() => window.print()}>{t('common.print')}</Button>
          ) : null}
        </Space>
      }
    >
      <Typography.Paragraph type="secondary">{t('app.kuaioa.personalPayroll.hint')}</Typography.Paragraph>
      {stats ? (
        <Typography.Paragraph>
          {String(stats.employee_name || '')} {year}{' '}
          {t('app.kuaioa.annualStats.annualWage')}: {Number(stats.annual_wage || 0).toFixed(2)}
        </Typography.Paragraph>
      ) : null}
      <Table<MonthRow>
        size="small"
        loading={loading}
        rowKey="month"
        columns={columns}
        dataSource={monthRows}
        pagination={false}
        bordered
      />
    </ListPageTemplate>
  );
};

export default PersonalPayrollPage;
