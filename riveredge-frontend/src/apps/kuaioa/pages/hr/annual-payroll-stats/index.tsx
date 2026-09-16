import React, { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Input, InputNumber, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { listAnnualPayrollStats } from '../../../services/payroll';

type Row = Record<string, unknown>;

const AnnualPayrollStatsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const perms = useResourcePermissions('kuaioa:payroll');
  const [year, setYear] = useState<number | null>(new Date().getFullYear());
  const [workshop, setWorkshop] = useState('');
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);

  const load = useCallback(async () => {
    if (!year || year < 2000 || year > 2100) {
      message.error(t('app.kuaioa.annualStats.yearInvalid'));
      return;
    }
    setLoading(true);
    try {
      const res = await listAnnualPayrollStats({
        year,
        workshop_name: workshop.trim() || undefined,
        keyword: keyword.trim() || undefined,
      });
      setRows(res.items);
    } catch (error) {
      message.error(getApiErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [keyword, message, t, workshop, year]);

  const money = (v: unknown) => Number(v || 0).toFixed(2);

  const columns: ColumnsType<Row> = useMemo(() => {
    const monthCols: ColumnsType<Row> = [];
    for (let m = 1; m <= 12; m += 1) {
      const key = `wage_m${String(m).padStart(2, '0')}`;
      monthCols.push({
        title: t('app.kuaioa.annualStats.monthWage', { month: m }),
        dataIndex: key,
        width: 96,
        render: money,
      });
    }
    const livingCols: ColumnsType<Row> = [];
    for (let m = 1; m <= 12; m += 1) {
      const key = `living_m${String(m).padStart(2, '0')}`;
      livingCols.push({
        title: t('app.kuaioa.annualStats.monthLiving', { month: m }),
        dataIndex: key,
        width: 96,
        render: money,
      });
    }
    return [
      {
        title: t('app.kuaioa.attendance.workshop'),
        dataIndex: 'workshop_name',
        width: 120,
        fixed: 'left',
      },
      {
        title: t('app.kuaioa.employee.fullName'),
        dataIndex: 'employee_name',
        width: 110,
        fixed: 'left',
      },
      ...monthCols,
      {
        title: t('app.kuaioa.annualStats.annualWage'),
        dataIndex: 'annual_wage',
        width: 110,
        render: money,
      },
      {
        title: t('app.kuaioa.payroll.taxDeduct'),
        dataIndex: 'tax_total',
        width: 90,
        render: money,
      },
      ...livingCols,
    ];
  }, [t]);

  return (
    <ListPageTemplate
      title={t('app.kuaioa.annualStats.title')}
      toolbarExtra={
        <Space wrap>
          <InputNumber
            placeholder={t('app.kuaioa.welfare.year')}
            value={year ?? undefined}
            min={2000}
            max={2100}
            onChange={(v) => setYear(typeof v === 'number' ? v : null)}
            style={{ width: 100 }}
          />
          <Input
            placeholder={t('app.kuaioa.attendance.workshop')}
            value={workshop}
            onChange={(e) => setWorkshop(e.target.value)}
            style={{ width: 140 }}
          />
          <Input
            placeholder={t('app.kuaioa.employee.fullName')}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            style={{ width: 140 }}
          />
          <Button type="primary" loading={loading} onClick={() => void load()}>
            {t('common.search')}
          </Button>
          {perms.canExport && rows.length > 0 ? (
            <Button
              onClick={() => {
                const exportCols = [
                  { key: 'workshop_name', title: t('app.kuaioa.attendance.workshop') },
                  { key: 'employee_name', title: t('app.kuaioa.employee.fullName') },
                  ...Array.from({ length: 12 }, (_, i) => {
                    const m = i + 1;
                    const key = `wage_m${String(m).padStart(2, '0')}`;
                    return { key, title: t('app.kuaioa.annualStats.monthWage', { month: m }) };
                  }),
                  { key: 'annual_wage', title: t('app.kuaioa.annualStats.annualWage') },
                ];
                void downloadRecordsAsXlsx(rows, exportCols, t('app.kuaioa.annualStats.exportFileName'));
              }}
            >
              {t('common.export')}
            </Button>
          ) : null}
        </Space>
      }
    >
      <Typography.Paragraph type="secondary">
        {t('app.kuaioa.annualStats.hint')}
      </Typography.Paragraph>
      <Table<Row>
        size="small"
        loading={loading}
        rowKey={(r) => String(r.employee_id)}
        columns={columns}
        dataSource={rows}
        pagination={false}
        bordered
        scroll={{ x: 2800 }}
      />
    </ListPageTemplate>
  );
};

export default AnnualPayrollStatsPage;
