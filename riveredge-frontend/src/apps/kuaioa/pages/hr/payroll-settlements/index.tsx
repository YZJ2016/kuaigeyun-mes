import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, App } from 'antd';
import { useTranslation } from 'react-i18next';
import { runKuaioaListExport } from '../../../utils/kuaioaListExport';
import { loadOaWorkshopNameOptions } from '../../../utils/oaWorkshopOptions';
import {
  buildOaEmploymentTypeOptions,
  resolveOaEmploymentTypeLabel,
} from '../../../utils/oaFormEnums';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import {
  confirmPayrollSettlement,
  createPayrollSettlement,
  deletePayrollSettlement,
  getPayrollSettlement,
  listPayrollSettlements,
  reopenPayrollSettlement,
  updatePayrollSettlement,
} from '../../../services/payroll';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';

const PayrollSettlementsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const navigate = useNavigate();
  const perms = useResourcePermissions('kuaioa:payroll');
  const [workshopOptions, setWorkshopOptions] = useState<Array<{ label: string; value: string }>>(
    [],
  );

  useEffect(() => {
    void (async () => {
      setWorkshopOptions(await loadOaWorkshopNameOptions());
    })();
  }, []);

  const statusOptions = useMemo(
    () => [
      { label: t('app.kuaioa.payroll.status.draft'), value: 'draft' },
      { label: t('app.kuaioa.payroll.status.confirmed'), value: 'confirmed' },
    ],
    [t],
  );
  const employmentOptions = useMemo(() => buildOaEmploymentTypeOptions(t), [t]);

  const fields = useMemo(
    () => [
      { name: 'settlement_code', labelKey: 'app.kuaioa.payroll.code', width: 140 },
      {
        name: 'year_month',
        labelKey: 'app.kuaioa.payroll.yearMonth',
        type: 'month' as const,
        required: true,
        width: 100,
      },
      {
        name: 'workshop_name',
        labelKey: 'app.kuaioa.attendance.workshop',
        type: 'select' as const,
        options: workshopOptions,
        required: true,
        width: 140,
      },
      {
        name: 'employment_types',
        labelKey: 'app.kuaioa.employee.employmentTypeLabel',
        type: 'select' as const,
        mode: 'multiple' as const,
        options: employmentOptions,
        width: 160,
      },
      {
        name: 'ot_multiplier',
        labelKey: 'app.kuaioa.payroll.otMultiplier',
        type: 'number' as const,
        width: 100,
      },
      {
        name: 'status',
        labelKey: 'common.status',
        type: 'select' as const,
        options: statusOptions,
        width: 100,
        hideInForm: true,
      },
      { name: 'notes', labelKey: 'common.remark', type: 'textarea' as const, hideInTable: true },
    ],
    [employmentOptions, statusOptions, workshopOptions],
  );

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.payroll.registerButton"
      resource="kuaioa:payroll"
      codeField="settlement_code"
      nameField="workshop_name"
      autoGenerateCode
      statusPresentation="marker"
      detailVariant="master"
      getDetailFn={getPayrollSettlement}
      columnPersistenceId="apps.kuaioa.payroll.list-v4"
      autoOpenCreateQuery="register"
      listBanner={
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          title={t('app.kuaioa.payroll.listGuideTitle')}
          description={t('app.kuaioa.payroll.listGuideBody')}
        />
      }
      fields={fields}
      listFn={listPayrollSettlements}
      createFn={createPayrollSettlement}
      updateFn={updatePayrollSettlement}
      deleteFn={deletePayrollSettlement}
      mapFormValuesToPayload={(values) => {
        const raw = values.employment_types;
        const types = (
          Array.isArray(raw) ? raw : raw != null && raw !== '' ? [raw] : []
        )
          .map((v) => String(v).trim())
          .filter(Boolean);
        return {
          ...values,
          employment_types: types,
        };
      }}
      mapRecordToFormValues={(record) => {
        const raw = record.employment_types;
        const types = Array.isArray(raw)
          ? raw.map((v) => String(v))
          : raw != null && raw !== ''
            ? [String(raw)]
            : [];
        return {
          ...record,
          employment_types: types,
        };
      }}
      onCreateSuccess={(record) => {
        const id = Number(record.id);
        if (Number.isFinite(id) && id > 0) {
          navigate(`/apps/kuaioa/hr/payroll-settlements/${id}`);
        }
      }}
      showExportButton
      onExport={async (type, keys, pageData) => {
        const formatEmployment = (row: Record<string, unknown>) => {
          const arr = Array.isArray(row.employment_types) ? row.employment_types : [];
          if (arr.length === 0) return t('app.kuaioa.attendance.employmentTypesAll');
          return arr
            .map((code) => resolveOaEmploymentTypeLabel(String(code), t))
            .join('、');
        };
        const withLabels = (rows?: Record<string, unknown>[]) =>
          (rows ?? []).map((row) => ({
            ...row,
            employment_types_label: formatEmployment(row),
          }));
        await runKuaioaListExport({
          type,
          keys,
          pageData: withLabels(pageData),
          listFn: async (params) => {
            const res = await listPayrollSettlements(params);
            return { items: withLabels(res.items), total: res.total };
          },
          columns: [
            { key: 'settlement_code', title: t('app.kuaioa.payroll.code') },
            { key: 'year_month', title: t('app.kuaioa.payroll.yearMonth') },
            { key: 'workshop_name', title: t('app.kuaioa.attendance.workshop') },
            {
              key: 'employment_types_label',
              title: t('app.kuaioa.employee.employmentTypeLabel'),
            },
            { key: 'status', title: t('common.status') },
          ],
          filename: t('app.kuaioa.payroll.exportFileName'),
          messageApi,
          noDataText: t('common.exportNoData'),
        });
      }}
      extraActions={[
        {
          key: 'detail',
          labelKey: 'app.kuaioa.payroll.openLines',
          deferSuccess: true,
          onClick: (r) => navigate(`/apps/kuaioa/hr/payroll-settlements/${r.id}`),
        },
        {
          key: 'confirm',
          labelKey: 'app.kuaioa.payroll.confirm',
          visible: (r) => r.status === 'draft' && !!perms.canAction?.('submit'),
          onClick: async (r) => {
            await confirmPayrollSettlement(Number(r.id));
          },
        },
        {
          key: 'reopen',
          labelKey: 'app.kuaioa.payroll.reopen',
          requireUpdate: true,
          visible: (r) => r.status === 'confirmed',
          onClick: async (r) => {
            await reopenPayrollSettlement(Number(r.id));
          },
        },
      ]}
    />
  );
};

export default PayrollSettlementsPage;
