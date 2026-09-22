import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  App,
  Button,
  DatePicker,
  InputNumber,
  Select,
  Space,
  Switch,
  Table,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ListPageTemplate } from '../../../../../components/layout-templates';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import {
  batchMarkAttendance,
  exportAttendanceSheet,
  getAttendanceSheet,
  refreshAttendanceRoster,
  reopenAttendanceSheet,
  submitAttendanceSheet,
  updateAttendanceDay,
} from '../../../services/attendance';

type DayCell = {
  id: number;
  employee_id: number;
  employee_name: string;
  employee_code?: string;
  work_date: string;
  regular_hours: number;
  ot_hours: number;
  mark: string;
  is_night: boolean;
};

type EmpRow = {
  key: string;
  employee_id: number;
  employee_name: string;
  employee_code?: string;
  ot_total: number;
  night_count: number;
  days: Record<string, DayCell>;
};

const AttendanceFillPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const sheetId = Number(id);
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const perms = useResourcePermissions('kuaioa:attendance');
  const [loading, setLoading] = useState(false);
  const [sheet, setSheet] = useState<Record<string, unknown> | null>(null);
  const [batchDate, setBatchDate] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!Number.isFinite(sheetId) || sheetId <= 0) return;
    setLoading(true);
    try {
      const data = await getAttendanceSheet(sheetId);
      setSheet(data);
    } catch (error) {
      message.error(getApiErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [message, sheetId]);

  useEffect(() => {
    void load();
  }, [load]);

  const locked = sheet?.status === 'submitted';
  const hasNight = Boolean(sheet?.has_night);

  const { dayKeys, rows } = useMemo(() => {
    const days = (sheet?.days as DayCell[] | undefined) || [];
    const keySet = new Set<string>();
    const byEmp = new Map<number, EmpRow>();
    for (const cell of days) {
      const dateKey = String(cell.work_date).slice(0, 10);
      keySet.add(dateKey);
      let row = byEmp.get(cell.employee_id);
      if (!row) {
        row = {
          key: String(cell.employee_id),
          employee_id: cell.employee_id,
          employee_name: cell.employee_name,
          employee_code: cell.employee_code,
          ot_total: 0,
          night_count: 0,
          days: {},
        };
        byEmp.set(cell.employee_id, row);
      }
      row.days[dateKey] = cell;
      if (cell.mark === 'normal') {
        row.ot_total += Number(cell.ot_hours || 0);
      }
      if (cell.is_night) row.night_count += 1;
    }
    const sortedKeys = Array.from(keySet).sort();
    return { dayKeys: sortedKeys, rows: Array.from(byEmp.values()) };
  }, [sheet]);

  const patchCell = async (cell: DayCell, patch: Record<string, unknown>) => {
    if (locked || !perms.canUpdate) return;
    try {
      await updateAttendanceDay(sheetId, cell.id, patch);
      await load();
    } catch (error) {
      message.error(getApiErrorMessage(error));
    }
  };

  const renderCell = (cell: DayCell | undefined) => {
    if (!cell) return '—';
    if (cell.mark === 'leave') return 'X';
    if (cell.mark === 'rest') return '√';
    const night = hasNight && cell.is_night ? ' ☆' : '';
    return (
      <Space orientation="vertical" size={2} style={{ width: '100%' }}>
        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
          {Number(cell.regular_hours)}h{night}
        </Typography.Text>
        <InputNumber
          size="small"
          min={0}
          step={0.5}
          changeOnBlur
          value={Number(cell.ot_hours)}
          disabled={locked || !perms.canUpdate}
          onChange={(value) => {
            if (value === null || value === undefined) return;
            if (Number(value) === Number(cell.ot_hours)) return;
            void patchCell(cell, { ot_hours: value, mark: 'normal' });
          }}
          style={{ width: 64 }}
        />
        <Select
          size="small"
          value={cell.mark}
          disabled={locked || !perms.canUpdate}
          style={{ width: 72 }}
          options={[
            { value: 'normal', label: t('app.kuaioa.attendance.mark.normal') },
            { value: 'leave', label: 'X' },
            { value: 'rest', label: '√' },
          ]}
          onChange={(value) => {
            void patchCell(cell, { mark: value });
          }}
        />
        {hasNight ? (
          <Switch
            size="small"
            checked={Boolean(cell.is_night)}
            disabled={locked || !perms.canUpdate}
            checkedChildren="☆"
            unCheckedChildren="—"
            onChange={(checked) => {
              void patchCell(cell, { is_night: checked });
            }}
          />
        ) : null}
      </Space>
    );
  };

  const columns: ColumnsType<EmpRow> = [
    {
      title: t('app.kuaioa.employee.fullName'),
      dataIndex: 'employee_name',
      fixed: 'left',
      width: 100,
    },
    {
      title: t('app.kuaioa.attendance.otTotal'),
      dataIndex: 'ot_total',
      fixed: 'left',
      width: 80,
      render: (v: number) => Number(v).toFixed(1),
    },
    ...(hasNight
      ? [
          {
            title: t('app.kuaioa.attendance.nightCount'),
            dataIndex: 'night_count',
            fixed: 'left' as const,
            width: 72,
          },
        ]
      : []),
    ...dayKeys.map((dk) => ({
      title: dk.slice(8),
      key: dk,
      width: 96,
      render: (_: unknown, row: EmpRow) => renderCell(row.days[dk]),
    })),
  ];

  return (
    <ListPageTemplate
      title={`${t('app.kuaioa.attendance.fillTitle')} ${sheet?.year_month || ''} ${sheet?.workshop_name || ''}`}
      toolbarExtra={
        <Space wrap>
          <Button onClick={() => navigate('/apps/kuaioa/hr/attendance')}>
            {t('common.back')}
          </Button>
          {perms.canExport ? (
            <Button
              onClick={async () => {
                try {
                  const ym = String(sheet?.year_month || 'month');
                  const ws = String(sheet?.workshop_name || 'workshop');
                  await exportAttendanceSheet(sheetId, `attendance_${ym}_${ws}.xlsx`);
                } catch (error) {
                  message.error(getApiErrorMessage(error));
                }
              }}
            >
              {t('common.export')}
            </Button>
          ) : null}
          <Button
            disabled={locked || !perms.canUpdate}
            loading={loading}
            onClick={async () => {
              try {
                await refreshAttendanceRoster(sheetId);
                message.success(t('app.kuaioa.attendance.rosterRefreshed'));
                await load();
              } catch (error) {
                message.error(getApiErrorMessage(error));
              }
            }}
          >
            {t('app.kuaioa.attendance.refreshRoster')}
          </Button>
          <DatePicker
            size="medium"
            disabled={locked || !perms.canUpdate}
            onChange={(v) => setBatchDate(v ? v.format('YYYY-MM-DD') : null)}
          />
          <Button
            disabled={!batchDate || locked || !perms.canUpdate}
            onClick={async () => {
              if (!batchDate) return;
              try {
                await batchMarkAttendance(sheetId, { work_date: batchDate, mark: 'rest' });
                message.success(t('common.success'));
                await load();
              } catch (error) {
                message.error(getApiErrorMessage(error));
              }
            }}
          >
            {t('app.kuaioa.attendance.batchRest')}
          </Button>
          {hasNight ? (
            <Button
              disabled={!batchDate || locked || !perms.canUpdate}
              onClick={async () => {
                if (!batchDate) return;
                try {
                  await batchMarkAttendance(sheetId, {
                    work_date: batchDate,
                    is_night: true,
                  });
                  message.success(t('common.success'));
                  await load();
                } catch (error) {
                  message.error(getApiErrorMessage(error));
                }
              }}
            >
              {t('app.kuaioa.attendance.batchNight')}
            </Button>
          ) : null}
          {sheet?.status === 'draft' && perms.canAction?.('submit') ? (
            <Button
              type="primary"
              onClick={async () => {
                try {
                  await submitAttendanceSheet(sheetId);
                  message.success(t('common.success'));
                  await load();
                } catch (error) {
                  message.error(getApiErrorMessage(error));
                }
              }}
            >
              {t('app.kuaioa.attendance.submit')}
            </Button>
          ) : null}
          {sheet?.status === 'submitted' && perms.canUpdate ? (
            <Button
              onClick={async () => {
                try {
                  await reopenAttendanceSheet(sheetId);
                  message.success(t('common.success'));
                  await load();
                } catch (error) {
                  message.error(getApiErrorMessage(error));
                }
              }}
            >
              {t('app.kuaioa.attendance.reopen')}
            </Button>
          ) : null}
        </Space>
      }
    >
      <Typography.Paragraph type="secondary">
        {t('app.kuaioa.attendance.fillHint')}
      </Typography.Paragraph>
      {(() => {
        const hints = sheet?.attendance_hints as Record<string, unknown[]> | undefined;
        const newHires = hints?.new_hires || [];
        const leftBlocked = hints?.left_blocked || [];
        if (newHires.length === 0 && leftBlocked.length === 0) return null;
        return (
          <Space orientation="vertical" style={{ width: '100%', marginBottom: 12 }}>
            {newHires.length > 0 ? (
              <Alert
                type="info"
                showIcon
                title={t('app.kuaioa.attendance.hintNewHires', {
                  names: newHires.map((h) => String((h as Record<string, unknown>).employee_name)).join('、'),
                })}
              />
            ) : null}
            {leftBlocked.length > 0 ? (
              <Alert
                type="warning"
                showIcon
                title={t('app.kuaioa.attendance.hintLeftBlocked', {
                  names: leftBlocked.map((h) => String((h as Record<string, unknown>).employee_name)).join('、'),
                })}
              />
            ) : null}
          </Space>
        );
      })()}
      <Table<EmpRow>
        size="small"
        loading={loading}
        rowKey="key"
        columns={columns}
        dataSource={rows}
        scroll={{ x: 120 + dayKeys.length * 96 }}
        pagination={false}
        bordered
      />
    </ListPageTemplate>
  );
};

export default AttendanceFillPage;
