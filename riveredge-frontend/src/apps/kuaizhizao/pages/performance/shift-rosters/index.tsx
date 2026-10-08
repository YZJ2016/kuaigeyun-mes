import type { EmployeeOption } from '../../../services/performance';
/**
 * 排班管理页面（按工作小组或人员 + 周视图）
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  App,
  Button,
  DatePicker,
  Dropdown,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import type { MenuProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { DownOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import isoWeek from 'dayjs/plugin/isoWeek';
import { MultiTabListPageTemplate } from '../../../../../components/layout-templates';
import { ShiftRosterOvertimePanel } from './ShiftRosterOvertimePanel';
import { ShiftRosterTempAdjustmentPanel } from './ShiftRosterTempAdjustmentPanel';
import { ShiftRosterDowntimePanel } from './ShiftRosterDowntimePanel';
import {
  employeePerformanceApi,
  holidayApi,
  shiftApi,
  shiftRosterApi,
} from '../../../services/performance';
import type {
  Holiday,
  Shift,
  ShiftAssignment,
  ShiftRoster,
} from '../../../types/performance';
import { factoryListItems, workGroupApi } from '../../../../master-data/services/factory';
import type { WorkGroup } from '../../../../master-data/types/factory';
import { formatDateTime } from '../../../../../utils/format';
import { normalizePerformanceListResponse } from '../../../utils/performanceListCore';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { resolveUserDisplay } from '../../../../../services/user';
import { resolveShiftSelectTint } from '../components/performanceMeta';

dayjs.extend(isoWeek);

const ROSTER_RESOURCE = 'kuaizhizao:performance-shift-rosters';

type RosterScopeType = 'work_group' | 'employee';

type MatrixRow = {
  key: number;
  employeeId: number;
  employeeName: string;
  departmentId?: number;
  departmentName?: string;
  roleNames?: string;
  cells: Record<string, number | null | undefined>;
};

type RosterMember = {
  employeeId: number;
  employeeName: string;
  departmentId?: number;
  departmentName?: string;
  roleNames?: string;
};

const REST_VALUE = 0;

const WEEKDAY_KEYS = [
  'app.kuaizhizao.performance.common.weekday.mon',
  'app.kuaizhizao.performance.common.weekday.tue',
  'app.kuaizhizao.performance.common.weekday.wed',
  'app.kuaizhizao.performance.common.weekday.thu',
  'app.kuaizhizao.performance.common.weekday.fri',
  'app.kuaizhizao.performance.common.weekday.sat',
  'app.kuaizhizao.performance.common.weekday.sun',
] as const;

type ShiftRosterTabKey = 'roster' | 'overtime' | 'tempAdjust' | 'downtime';

const ROSTER_TAB_KEYS: ShiftRosterTabKey[] = ['roster', 'overtime', 'tempAdjust', 'downtime'];

function parseRosterTabKey(raw: string | null): ShiftRosterTabKey {
  if (raw && ROSTER_TAB_KEYS.includes(raw as ShiftRosterTabKey)) {
    return raw as ShiftRosterTabKey;
  }
  return 'roster';
}

const ShiftRostersPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const rosterPerms = useResourcePermissions(ROSTER_RESOURCE);
  const [activeTabKey, setActiveTabKey] = useState<ShiftRosterTabKey>(() =>
    parseRosterTabKey(searchParams.get('tab')),
  );
  const [scopeType, setScopeType] = useState<RosterScopeType>('work_group');
  const [workGroups, setWorkGroups] = useState<WorkGroup[]>([]);
  const [employees, setEmployees] = useState<EmployeeOption[]>([]);
  const [shifts, setShifts] = useState<Shift[]>([]);
  const [workGroupId, setWorkGroupId] = useState<number | undefined>();
  const [departments, setDepartments] = useState<Array<{ id: number; name: string }>>([]);
  /** 人员视图：按部门筛选（undefined 表示全部） */
  const [rosterDepartmentId, setRosterDepartmentId] = useState<number | undefined>();
  const [weekAnchor, setWeekAnchor] = useState<Dayjs>(dayjs().startOf('isoWeek'));
  const [roster, setRoster] = useState<ShiftRoster | null>(null);
  const [matrix, setMatrix] = useState<MatrixRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  /** 本周在假期设置中启用的休息日（YYYY-MM-DD）；null 表示尚未按假期表加载成功 */
  const [holidayRestDates, setHolidayRestDates] = useState<Set<string> | null>(null);

  const periodStart = useMemo(() => weekAnchor.startOf('isoWeek').format('YYYY-MM-DD'), [weekAnchor]);
  const weekDates = useMemo(() => {
    const start = weekAnchor.startOf('isoWeek');
    return Array.from({ length: 7 }, (_, i) => start.add(i, 'day').format('YYYY-MM-DD'));
  }, [weekAnchor]);
  const periodEnd = useMemo(() => weekDates[weekDates.length - 1] ?? periodStart, [weekDates, periodStart]);

  const rosterEmployeeIds = useMemo(() => matrix.map((row) => row.employeeId), [matrix]);

  const visibleMatrix = useMemo(() => {
    if (scopeType !== 'employee' || rosterDepartmentId == null) {
      return matrix;
    }
    return matrix.filter((row) => row.departmentId === rosterDepartmentId);
  }, [matrix, scopeType, rosterDepartmentId]);

  const rosterEmployeeOptions = useMemo(
    () =>
      matrix.map((row) => {
        const extra = [row.departmentName, row.roleNames].filter(Boolean).join(' / ');
        return {
          value: row.employeeId,
          label: extra ? `${row.employeeName} / ${extra}` : row.employeeName,
        };
      }),
    [matrix],
  );

  const tempAdjustEmployeeIds = useMemo(() => {
    const source =
      scopeType === 'employee' && rosterDepartmentId != null ? visibleMatrix : matrix;
    const ids = source.map((row) => row.employeeId);
    if (ids.length > 0) {
      return ids;
    }
    return undefined;
  }, [matrix, visibleMatrix, scopeType, rosterDepartmentId]);

  const activeShiftIds = useMemo(
    () => shifts.filter((s) => s.isActive).map((s) => s.id),
    [shifts],
  );

  const shiftOptions = useMemo(
    () => [
      { label: t('app.kuaizhizao.performance.common.form.rest'), value: REST_VALUE },
      ...shifts.filter((s) => s.isActive).map((s) => ({ label: s.name, value: s.id })),
    ],
    [shifts, t],
  );

  const scopeReady =
    scopeType === 'work_group' ? Boolean(workGroupId) : employees.length > 0;

  const loadBase = useCallback(async () => {
    try {
      const [wgRes, shiftRes, employeeRes, deptRes] = await Promise.all([
        workGroupApi.list({ limit: 500, is_active: true }),
        shiftApi.list({ limit: 200, is_active: true }),
        employeePerformanceApi.listEmployees({ limit: 500 }),
        employeePerformanceApi.listDepartments(),
      ]);
      const wgItems = factoryListItems(wgRes);
      const employeeItems = employeeRes.items ?? [];
      const shiftList = normalizePerformanceListResponse(shiftRes).data as Shift[];
      setWorkGroups(wgItems);
      setEmployees(employeeItems);
      setDepartments(deptRes.items ?? []);
      setShifts(shiftList);
      setWorkGroupId((prev) => prev ?? wgItems[0]?.id);
    } catch (e: any) {
      messageApi.error(e?.message || t('app.kuaizhizao.performance.rosters.messages.loadBaseFailed'));
    }
  }, [messageApi, t]);

  /** 本周假期设置中的休息日（周休/法定节假日等），供一键排班工作日使用 */
  const loadWeekHolidays = useCallback(async () => {
    setHolidayRestDates(null);
    try {
      const res = await holidayApi.list({
        start_date: periodStart,
        end_date: periodEnd,
        is_active: true,
        limit: 50,
      });
      const items = normalizePerformanceListResponse(res).data as Holiday[];
      const dates = new Set<string>();
      items.forEach((h) => {
        const raw = String(h.holidayDate ?? '').trim().slice(0, 10);
        if (raw) dates.add(raw);
      });
      setHolidayRestDates(dates);
    } catch (e: any) {
      messageApi.error(
        e?.message || t('app.kuaizhizao.performance.rosters.messages.loadWeekHolidaysFailed'),
      );
      setHolidayRestDates(null);
    }
  }, [periodStart, periodEnd, messageApi, t]);

  /** 用人员展示真源补部门/角色，不猜、不兜底假文案 */
  const enrichMembers = useCallback(
    async (members: RosterMember[]): Promise<RosterMember[]> => {
      if (members.length === 0) return members;
      try {
        const items = await resolveUserDisplay({
          user_ids: members.map((m) => m.employeeId),
        });
        const byId = new Map(items.map((item) => [item.id, item]));
        return members.map((m) => {
          const d = byId.get(m.employeeId);
          if (!d) return m;
          const roleNames = (d.roles ?? [])
            .map((r) => String(r.name ?? '').trim())
            .filter(Boolean)
            .join('、');
          return {
            employeeId: m.employeeId,
            employeeName: (d.full_name || m.employeeName || '').trim() || m.employeeName,
            departmentId: m.departmentId,
            departmentName: d.department_name?.trim() || undefined,
            roleNames: roleNames || undefined,
          };
        });
      } catch (e: any) {
        messageApi.error(
          e?.message || t('app.kuaizhizao.performance.rosters.messages.loadEmployeeDisplayFailed'),
        );
        return members;
      }
    },
    [messageApi, t],
  );

  const buildMatrix = useCallback(
    (members: RosterMember[], rosterData: ShiftRoster) => {
      const assignmentMap = new Map<string, number | null>();
      (rosterData.assignments ?? []).forEach((a: ShiftAssignment) => {
        assignmentMap.set(`${a.employeeId}_${a.workDate}`, a.shiftId ?? null);
      });
      const rows: MatrixRow[] = members.map((m) => {
        const cells: Record<string, number | null | undefined> = {};
        weekDates.forEach((d) => {
          const sid = assignmentMap.get(`${m.employeeId}_${d}`);
          cells[d] = sid === undefined ? undefined : sid === null ? REST_VALUE : sid;
        });
        return {
          key: m.employeeId,
          employeeId: m.employeeId,
          employeeName:
            m.employeeName || t('app.kuaizhizao.performance.rosters.employeeFallback', { id: m.employeeId }),
          departmentId: m.departmentId,
          departmentName: m.departmentName,
          roleNames: m.roleNames,
          cells,
        };
      });
      setMatrix(rows);
    },
    [weekDates, t],
  );

  const loadRoster = useCallback(async () => {
    if (!scopeReady) return;
    setLoading(true);
    try {
      if (scopeType === 'work_group') {
        const wgMeta = workGroups.find((w) => w.id === workGroupId);
        if (!wgMeta?.uuid) {
          messageApi.warning(t('app.kuaizhizao.performance.rosters.messages.selectWorkGroup'));
          return;
        }
        const wg = await workGroupApi.get(wgMeta.uuid);
        const rosterData = await shiftRosterApi.getByWeek({ workGroupId, periodStart });
        setRoster(rosterData);
        const members = await enrichMembers(
          (wg.members ?? []).map((m) => ({
            employeeId: m.employeeId,
            employeeName: m.employeeName || '',
          })),
        );
        buildMatrix(members, rosterData);
        return;
      }

      const rosterData = await shiftRosterApi.getByWeek({
        periodStart,
        scopeType: 'all_employees',
      });
      setRoster(rosterData);
      const members = await enrichMembers(
        employees.map((e) => ({
          employeeId: e.id,
          employeeName: e.full_name,
          departmentId: e.department_id ?? undefined,
        })),
      );
      buildMatrix(members, rosterData);
    } catch (e: any) {
      messageApi.error(e?.message || t('app.kuaizhizao.performance.rosters.messages.loadRosterFailed'));
      setRoster(null);
      setMatrix([]);
    } finally {
      setLoading(false);
    }
  }, [
    scopeReady,
    scopeType,
    workGroupId,
    periodStart,
    workGroups,
    employees,
    enrichMembers,
    buildMatrix,
    messageApi,
    t,
  ]);

  useEffect(() => {
    loadBase();
  }, [loadBase]);

  useEffect(() => {
    const tab = parseRosterTabKey(searchParams.get('tab'));
    setActiveTabKey(tab);
  }, [searchParams]);

  const handleTabChange = (key: string) => {
    const tab = key as ShiftRosterTabKey;
    setActiveTabKey(tab);
    const next = new URLSearchParams(searchParams);
    if (tab === 'roster') {
      next.delete('tab');
    } else {
      next.set('tab', tab);
    }
    setSearchParams(next, { replace: true });
  };

  useEffect(() => {
    void loadWeekHolidays();
  }, [loadWeekHolidays]);

  useEffect(() => {
    if (scopeReady) {
      loadRoster();
    } else {
      setRoster(null);
      setMatrix([]);
    }
  }, [scopeType, workGroupId, periodStart, scopeReady, employees.length, loadRoster]);

  const handleCellChange = (targetEmployeeId: number, workDate: string, value: number) => {
    setMatrix((prev) =>
      prev.map((row) =>
        row.employeeId === targetEmployeeId
          ? { ...row, cells: { ...row.cells, [workDate]: value === REST_VALUE ? null : value } }
          : row,
      ),
    );
  };

  /** 单行一键排班：整周 / 工作日（假期设置中的休息日除外） / 整周休息 */
  const fillRowSchedule = useCallback(
    (
      targetEmployeeId: number,
      employeeName: string,
      mode: 'week' | 'workdays',
      shiftId: number | null,
    ) => {
      if (mode === 'workdays' && holidayRestDates == null) {
        messageApi.error(t('app.kuaizhizao.performance.rosters.messages.loadWeekHolidaysFailed'));
        return;
      }
      const restDates = holidayRestDates ?? new Set<string>();
      setMatrix((prev) =>
        prev.map((row) => {
          if (row.employeeId !== targetEmployeeId) return row;
          const cells = { ...row.cells };
          weekDates.forEach((d) => {
            if (mode === 'workdays') {
              cells[d] = restDates.has(d) ? null : shiftId;
            } else {
              cells[d] = shiftId;
            }
          });
          return { ...row, cells };
        }),
      );
      const shiftLabel =
        shiftId == null
          ? t('app.kuaizhizao.performance.common.form.rest')
          : shifts.find((s) => s.id === shiftId)?.name || String(shiftId);
      messageApi.success(
        t('app.kuaizhizao.performance.rosters.messages.quickFillSuccess', {
          name: employeeName,
          shift: shiftLabel,
          mode:
            mode === 'workdays'
              ? t('app.kuaizhizao.performance.rosters.quickFill.modeWorkdays')
              : t('app.kuaizhizao.performance.rosters.quickFill.modeWeek'),
        }),
      );
    },
    [weekDates, holidayRestDates, shifts, messageApi, t],
  );

  const buildRowQuickFillMenu = useCallback(
    (record: MatrixRow): MenuProps['items'] => {
      const activeShifts = shifts.filter((s) => s.isActive);
      const items: NonNullable<MenuProps['items']> = [];
      if (activeShifts.length > 0) {
        items.push(
          {
            type: 'group',
            label: t('app.kuaizhizao.performance.rosters.quickFill.groupWeek'),
            children: activeShifts.map((s) => ({
              key: `week-${s.id}`,
              label: t('app.kuaizhizao.performance.rosters.quickFill.fillWeek', { shift: s.name }),
              onClick: () => fillRowSchedule(record.employeeId, record.employeeName, 'week', s.id),
            })),
          },
          {
            type: 'group',
            label: t('app.kuaizhizao.performance.rosters.quickFill.groupWorkdays'),
            children: activeShifts.map((s) => ({
              key: `workdays-${s.id}`,
              label: t('app.kuaizhizao.performance.rosters.quickFill.fillWorkdays', {
                shift: s.name,
              }),
              onClick: () =>
                fillRowSchedule(record.employeeId, record.employeeName, 'workdays', s.id),
            })),
          },
          { type: 'divider' },
        );
      }
      items.push({
        key: 'week-rest',
        label: t('app.kuaizhizao.performance.rosters.quickFill.fillWeekRest'),
        onClick: () => fillRowSchedule(record.employeeId, record.employeeName, 'week', null),
      });
      return items;
    },
    [shifts, fillRowSchedule, t],
  );

  const collectAssignments = () => {
    const list: Array<{ employeeId: number; workDate: string; shiftId: number | null }> = [];
    matrix.forEach((row) => {
      weekDates.forEach((d) => {
        const v = row.cells[d];
        if (v === undefined) return;
        list.push({
          employeeId: row.employeeId,
          workDate: d,
          shiftId: v === REST_VALUE || v === null ? null : (v as number),
        });
      });
    });
    return list;
  };

  const reloadMatrixFromRoster = useCallback(
    async (rosterData: ShiftRoster) => {
      if (scopeType === 'work_group' && workGroupId) {
        const wgUuid = workGroups.find((w) => w.id === workGroupId)?.uuid;
        if (wgUuid) {
          const wg = await workGroupApi.get(wgUuid);
          const members = await enrichMembers(
            (wg.members ?? []).map((m) => ({
              employeeId: m.employeeId,
              employeeName: m.employeeName || '',
            })),
          );
          buildMatrix(members, rosterData);
        }
        return;
      }
      if (scopeType === 'employee') {
        const members = await enrichMembers(
          employees.map((e) => ({
            employeeId: e.id,
            employeeName: e.full_name,
            departmentId: e.department_id ?? undefined,
          })),
        );
        buildMatrix(members, rosterData);
      }
    },
    [scopeType, workGroupId, workGroups, employees, enrichMembers, buildMatrix],
  );

  const handleSave = async () => {
    if (!roster?.uuid) return;
    try {
      setSaving(true);
      const updated = await shiftRosterApi.saveAssignments(roster.uuid, collectAssignments());
      setRoster(updated);
      messageApi.success(t('app.kuaizhizao.performance.rosters.messages.saveSuccess'));
    } catch (e: any) {
      messageApi.error(e?.message || t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handlePublish = async () => {
    if (!roster?.uuid) return;
    try {
      setSaving(true);
      const updated = await shiftRosterApi.publish(roster.uuid);
      setRoster(updated);
      messageApi.success(t('app.kuaizhizao.performance.rosters.messages.publishSuccess'));
    } catch (e: any) {
      messageApi.error(e?.message || t('app.kuaizhizao.performance.common.messages.publishFailed'));
    } finally {
      setSaving(false);
    }
  };

  const handleCopyPrevious = async () => {
    if (!roster?.uuid) return;
    try {
      setSaving(true);
      const updated = await shiftRosterApi.copyFromPreviousWeek(roster.uuid);
      setRoster(updated);
      await reloadMatrixFromRoster(updated);
      messageApi.success(t('app.kuaizhizao.performance.rosters.messages.copySuccess'));
    } catch (e: any) {
      messageApi.error(e?.message || t('common.copyFailed'));
    } finally {
      setSaving(false);
    }
  };

  const rowEditable = roster?.status !== 'published' && rosterPerms.canUpdate;

  const columns: ColumnsType<MatrixRow> = useMemo(() => {
    const base: ColumnsType<MatrixRow> = [
      {
        title: t('app.kuaizhizao.performance.common.columns.employee'),
        dataIndex: 'employeeName',
        fixed: 'left',
        width: 168,
        render: (_, record) => {
          const meta = [record.departmentName, record.roleNames].filter(Boolean).join(' / ');
          return (
            <div>
              <div>{record.employeeName}</div>
              {meta ? (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {meta}
                </Typography.Text>
              ) : null}
            </div>
          );
        },
      },
    ];
    weekDates.forEach((d) => {
      base.push({
        title: (
          <span>
            {formatDateTime(d, 'MM-DD')}
            <br />
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              {t(WEEKDAY_KEYS[dayjs(d).isoWeekday() - 1])}
            </Typography.Text>
          </span>
        ),
        dataIndex: d,
        width: 120,
        render: (_, record) => {
          const val = record.cells[d];
          const selectVal = val === undefined ? undefined : val === null ? REST_VALUE : val;
          const tint = resolveShiftSelectTint(selectVal, REST_VALUE, activeShiftIds);
          return (
            <Select
              size="small"
              style={{
                width: '100%',
                background: tint?.background,
                borderRadius: 6,
              }}
              styles={
                tint
                  ? {
                      root: {
                        background: tint.background,
                        borderColor: tint.borderColor,
                        color: tint.color,
                      },
                    }
                  : undefined
              }
              allowClear
              placeholder="—"
              disabled={!rowEditable}
              options={shiftOptions}
              value={selectVal}
              optionRender={(option) => {
                const optionTint = resolveShiftSelectTint(
                  option.value as number,
                  REST_VALUE,
                  activeShiftIds,
                );
                return (
                  <span style={{ color: optionTint?.color }}>{option.label}</span>
                );
              }}
              labelRender={(props) => {
                const labelTint = resolveShiftSelectTint(
                  props.value as number,
                  REST_VALUE,
                  activeShiftIds,
                );
                return (
                  <span style={{ color: labelTint?.color, fontWeight: 500 }}>{props.label}</span>
                );
              }}
              onChange={(v) => handleCellChange(record.employeeId, d, v ?? REST_VALUE)}
            />
          );
        },
      });
    });
    base.push({
      title: t('app.kuaizhizao.performance.common.columns.actions'),
      key: 'actions',
      fixed: 'right',
      width: 112,
      align: 'center',
      render: (_, record) => (
        <Dropdown disabled={!rowEditable} menu={{ items: buildRowQuickFillMenu(record) }}>
          <Button type="link" size="small" disabled={!rowEditable}>
            {t('app.kuaizhizao.performance.rosters.quickFill.action')}
            <DownOutlined />
          </Button>
        </Dropdown>
      ),
    });
    return base;
  }, [
    weekDates,
    shiftOptions,
    activeShiftIds,
    rowEditable,
    buildRowQuickFillMenu,
    t,
  ]);

  const subTabWeekBar = (
    <Space wrap style={{ marginBottom: 12, flexShrink: 0 }}>
      <span>{t('app.kuaizhizao.performance.rosters.label.rosterWeek')}</span>
      <DatePicker
        picker="week"
        value={weekAnchor}
        onChange={(v) => v && setWeekAnchor(v.startOf('isoWeek'))}
      />
      <Typography.Text type="secondary">
        {t('app.kuaizhizao.performance.rosters.hint.period', {
          start: periodStart,
          end: periodEnd,
        })}
      </Typography.Text>
    </Space>
  );

  const rosterMatrix = (
    <>
        <Space wrap style={{ marginBottom: 16, flexShrink: 0 }}>
          <Segmented<RosterScopeType>
            value={scopeType}
            onChange={(v) => {
              setScopeType(v);
              if (v === 'work_group') {
                setRosterDepartmentId(undefined);
              }
            }}
            options={[
              { label: t('app.kuaizhizao.performance.rosters.scope.workGroup'), value: 'work_group' },
              { label: t('app.kuaizhizao.performance.rosters.scope.employee'), value: 'employee' },
            ]}
          />
          {scopeType === 'work_group' ? (
            <>
              <span>{t('app.kuaizhizao.performance.rosters.label.workGroup')}</span>
              <Select
                style={{ minWidth: 200 }}
                placeholder={t('app.kuaizhizao.performance.rosters.placeholder.workGroup')}
                value={workGroupId}
                options={workGroups.map((w) => ({ label: `${w.code} - ${w.name}`, value: w.id }))}
                onChange={(v) => setWorkGroupId(v)}
              />
            </>
          ) : (
            <>
              <span>{t('app.kuaizhizao.performance.rosters.label.departmentFilter')}</span>
              <Select
                allowClear
                style={{ minWidth: 200 }}
                placeholder={t('app.kuaizhizao.performance.rosters.placeholder.allDepartments')}
                value={rosterDepartmentId}
                options={departments.map((d) => ({ label: d.name, value: d.id }))}
                onChange={(v) => setRosterDepartmentId(v)}
              />
              <Typography.Text type="secondary">
                {t('app.kuaizhizao.performance.rosters.hint.personnelRoster', {
                  shown: visibleMatrix.length,
                  total: matrix.length,
                })}
              </Typography.Text>
            </>
          )}
          <span>{t('app.kuaizhizao.performance.rosters.label.rosterWeek')}</span>
          <DatePicker
            picker="week"
            value={weekAnchor}
            onChange={(v) => v && setWeekAnchor(v.startOf('isoWeek'))}
          />
          {roster ? (
            <Tag color={roster.status === 'published' ? 'success' : 'processing'}>
              {roster.status === 'published'
                ? t('app.kuaizhizao.performance.common.rosterStatus.published')
                : t('app.kuaizhizao.performance.common.rosterStatus.draft')}
            </Tag>
          ) : null}
          {roster ? (
            <Typography.Text type="secondary">
              {roster.updatedByName || '-'}
              {' - '}
              {roster.updatedAt ? formatDateTime(roster.updatedAt, 'YYYY-MM-DD HH:mm') : '-'}
            </Typography.Text>
          ) : null}
          {rosterPerms.canUpdate ? (
            <Button
              type="primary"
              loading={saving}
              disabled={!scopeReady || roster?.status === 'published'}
              onClick={handleSave}
            >
              {t('app.kuaizhizao.performance.common.actions.saveDraft')}
            </Button>
          ) : null}
          {rosterPerms.canCreate ? (
            <Button
              loading={saving}
              disabled={!scopeReady || roster?.status === 'published'}
              onClick={handlePublish}
            >
              {t('app.kuaizhizao.performance.common.actions.publish')}
            </Button>
          ) : null}
          {rosterPerms.canCreate ? (
            <Button
              loading={saving}
              disabled={!scopeReady || roster?.status === 'published'}
              onClick={handleCopyPrevious}
            >
              {t('app.kuaizhizao.performance.common.actions.copyPreviousWeek')}
            </Button>
          ) : null}
          <Button onClick={loadRoster} disabled={!scopeReady}>
            {t('common.refresh')}
          </Button>
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          {t('app.kuaizhizao.performance.rosters.hint.period', {
            start: periodStart,
            end: weekAnchor.endOf('isoWeek').format('YYYY-MM-DD'),
          })}{' '}
          {t('app.kuaizhizao.performance.rosters.hint.quickFill')}
        </Typography.Paragraph>
        <Table<MatrixRow>
          size="small"
          bordered
          loading={loading}
          pagination={false}
          scroll={{ x: 'max-content' }}
          rowKey="key"
          columns={columns}
          dataSource={visibleMatrix}
        />
    </>
  );

  return (
    <MultiTabListPageTemplate
      activeTabKey={activeTabKey}
      onTabChange={handleTabChange}
      preserveMounted
      tabs={[
        {
          key: 'roster',
          label: t('app.kuaizhizao.menu.performance-management.shift-rosters'),
          children: rosterMatrix,
        },
        {
          key: 'overtime',
          label: t('app.kuaizhizao.performance.workCalendar.overtimeTitle'),
          children: (
            <>
              {subTabWeekBar}
              <ShiftRosterOvertimePanel periodStart={periodStart} periodEnd={periodEnd} />
            </>
          ),
        },
        {
          key: 'tempAdjust',
          label: t('app.kuaizhizao.performance.rosters.tempAdjust.tabTitle'),
          children: (
            <>
              {subTabWeekBar}
              <ShiftRosterTempAdjustmentPanel
                periodStart={periodStart}
                periodEnd={periodEnd}
                employeeOptions={rosterEmployeeOptions}
                employeeIds={tempAdjustEmployeeIds}
              />
            </>
          ),
        },
        {
          key: 'downtime',
          label: t('app.kuaizhizao.performance.workCalendar.downtimeTitle'),
          children: <ShiftRosterDowntimePanel />,
        },
      ]}
    />
  );
};

export default ShiftRostersPage;
