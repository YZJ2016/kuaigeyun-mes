import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { App } from 'antd';
import { useTranslation } from 'react-i18next';
import KuaioaCrudListPage from '../../../components/KuaioaCrudListPage';
import {
  createAttendanceSheet,
  deleteAttendanceSheet,
  getAttendanceSheet,
  listAttendanceSheets,
  reopenAttendanceSheet,
  submitAttendanceSheet,
  updateAttendanceSheet,
} from '../../../services/attendance';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import {
  loadOaProductionLineNameOptions,
  loadOaWorkshopNameOptions,
} from '../../../utils/oaWorkshopOptions';
import { runKuaioaListExport } from '../../../utils/kuaioaListExport';

const AttendanceListPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const navigate = useNavigate();
  const perms = useResourcePermissions('kuaioa:attendance');
  const [workshopOptions, setWorkshopOptions] = useState<Array<{ label: string; value: string }>>(
    [],
  );
  const [lineOptions, setLineOptions] = useState<Array<{ label: string; value: string }>>([]);

  useEffect(() => {
    void (async () => {
      const [workshops, lines] = await Promise.all([
        loadOaWorkshopNameOptions(),
        loadOaProductionLineNameOptions(),
      ]);
      setWorkshopOptions(workshops);
      setLineOptions(lines.map(({ label, value }) => ({ label, value })));
    })();
  }, []);

  const statusOptions = useMemo(
    () => [
      { label: t('app.kuaioa.attendance.status.draft'), value: 'draft' },
      { label: t('app.kuaioa.attendance.status.submitted'), value: 'submitted' },
    ],
    [t],
  );

  const fields = useMemo(
    () => [
      { name: 'sheet_code', labelKey: 'app.kuaioa.attendance.code', width: 140 },
      {
        name: 'year_month',
        labelKey: 'app.kuaioa.attendance.yearMonth',
        type: 'month' as const,
        required: true,
        width: 110,
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
        name: 'production_line_name',
        labelKey: 'app.kuaioa.attendance.productionLine',
        type: 'select' as const,
        options: lineOptions,
        width: 120,
      },
      {
        name: 'has_night',
        labelKey: 'app.kuaioa.attendance.hasNight',
        type: 'switch' as const,
        width: 100,
      },
      {
        name: 'standard_hours',
        labelKey: 'app.kuaioa.attendance.standardHours',
        type: 'number' as const,
        hideInTable: true,
      },
      {
        name: 'status',
        labelKey: 'common.status',
        type: 'select' as const,
        options: statusOptions,
        width: 100,
      },
      {
        name: 'notes',
        labelKey: 'common.remark',
        type: 'textarea' as const,
        hideInTable: true,
      },
    ],
    [lineOptions, statusOptions, workshopOptions],
  );

  return (
    <KuaioaCrudListPage
      createButtonKey="app.kuaioa.attendance.createButton"
      resource="kuaioa:attendance"
      codeField="sheet_code"
      nameField="workshop_name"
      autoGenerateCode
      statusPresentation="marker"
      detailVariant="master"
      getDetailFn={getAttendanceSheet}
      columnPersistenceId="apps.kuaioa.attendance.list-v2"
      fields={fields}
      listFn={listAttendanceSheets}
      createFn={createAttendanceSheet}
      updateFn={updateAttendanceSheet}
      deleteFn={deleteAttendanceSheet}
      showExportButton
      onExport={async (type, keys, pageData) => {
        await runKuaioaListExport({
          type,
          keys,
          pageData,
          listFn: listAttendanceSheets,
          columns: [
            { key: 'sheet_code', title: t('app.kuaioa.attendance.code') },
            { key: 'year_month', title: t('app.kuaioa.attendance.yearMonth') },
            { key: 'workshop_name', title: t('app.kuaioa.attendance.workshop') },
            { key: 'production_line_name', title: t('app.kuaioa.attendance.productionLine') },
            { key: 'has_night', title: t('app.kuaioa.attendance.hasNight') },
            { key: 'status', title: t('common.status') },
          ],
          filename: t('app.kuaioa.attendance.exportFileName'),
          messageApi,
          noDataText: t('common.exportNoData'),
        });
      }}
      extraActions={[
        {
          key: 'fill',
          labelKey: 'app.kuaioa.attendance.fill',
          deferSuccess: true,
          onClick: (record) => {
            navigate(`/apps/kuaioa/hr/attendance/${record.id}`);
          },
        },
        {
          key: 'submit',
          labelKey: 'app.kuaioa.attendance.submit',
          visible: (r) => r.status === 'draft' && !!perms.canAction?.('submit'),
          onClick: async (r) => {
            await submitAttendanceSheet(Number(r.id));
          },
        },
        {
          key: 'reopen',
          labelKey: 'app.kuaioa.attendance.reopen',
          requireUpdate: true,
          visible: (r) => r.status === 'submitted',
          onClick: async (r) => {
            await reopenAttendanceSheet(Number(r.id));
          },
        },
      ]}
    />
  );
};

export default AttendanceListPage;
