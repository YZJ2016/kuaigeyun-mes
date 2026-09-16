import React, { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { App, Button, Input, Space, Table, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import { downloadRecordsAsXlsx } from '../../../../../utils/exportRecordsXlsx';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { listLivingPayout } from '../../../services/payroll';

type Row = Record<string, unknown>;

const LivingPayoutPage: React.FC = () => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const perms = useResourcePermissions('kuaioa:living-advance');
  const [yearMonth, setYearMonth] = useState('');
  const [workshop, setWorkshop] = useState('');
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<Row[]>([]);

  const load = useCallback(async () => {
    if (!/^\d{4}-\d{2}$/.test(yearMonth.trim())) {
      message.error(t('app.kuaioa.payroll.yearMonthInvalid'));
      return;
    }
    setLoading(true);
    try {
      const res = await listLivingPayout({
        year_month: yearMonth.trim(),
        workshop_name: workshop.trim() || undefined,
      });
      setRows(res.items);
    } catch (error) {
      message.error(getApiErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [message, t, workshop, yearMonth]);

  const columns: ColumnsType<Row> = [
    { title: t('app.kuaioa.employee.bankName'), dataIndex: 'bank_name', width: 120 },
    { title: t('app.kuaioa.attendance.workshop'), dataIndex: 'workshop_name', width: 120 },
    { title: t('app.kuaioa.employee.fullName'), dataIndex: 'employee_name', width: 120 },
    { title: t('app.kuaioa.employee.bankAccount'), dataIndex: 'bank_account', width: 160 },
    {
      title: t('app.kuaioa.livingAdvance.baseLiving'),
      dataIndex: 'base_living',
      width: 110,
      render: (v) => Number(v || 0).toFixed(2),
    },
    {
      title: t('app.kuaioa.livingAdvance.amount'),
      dataIndex: 'advance_amount',
      width: 110,
      render: (v) => Number(v || 0).toFixed(2),
    },
    {
      title: t('app.kuaioa.livingPayout.payout'),
      dataIndex: 'payout_amount',
      width: 110,
      render: (v) => Number(v || 0).toFixed(2),
    },
  ];

  return (
    <ListPageTemplate
      title={t('app.kuaioa.livingPayout.title')}
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
          <Button type="primary" loading={loading} onClick={() => void load()}>
            {t('common.search')}
          </Button>
          {perms.canExport && rows.length > 0 ? (
            <Button
              onClick={() =>
                void downloadRecordsAsXlsx(
                  rows,
                  [
                    { key: 'bank_name', title: t('app.kuaioa.employee.bankName') },
                    { key: 'employee_name', title: t('app.kuaioa.employee.fullName') },
                    { key: 'bank_account', title: t('app.kuaioa.employee.bankAccount') },
                    { key: 'base_living', title: t('app.kuaioa.livingAdvance.baseLiving') },
                    { key: 'advance_amount', title: t('app.kuaioa.livingAdvance.amount') },
                    { key: 'payout_amount', title: t('app.kuaioa.livingPayout.payout') },
                    { key: 'workshop_name', title: t('app.kuaioa.attendance.workshop') },
                  ],
                  t('app.kuaioa.livingPayout.exportFileName'),
                )
              }
            >
              {t('common.export')}
            </Button>
          ) : null}
        </Space>
      }
    >
      <Typography.Paragraph type="secondary">
        {t('app.kuaioa.livingPayout.hint')}
      </Typography.Paragraph>
      <Table<Row>
        size="small"
        loading={loading}
        rowKey={(r) => String(r.employee_id)}
        columns={columns}
        dataSource={rows}
        pagination={false}
        bordered
      />
    </ListPageTemplate>
  );
};

export default LivingPayoutPage;
