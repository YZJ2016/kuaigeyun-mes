/**
 * 班次排班页 - 员工临时加班 / 临时休息
 */

import React, { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button, DatePicker, Form, Input, Modal, Popconfirm, Select, Space, Switch, TimePicker, Typography } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { UniTable } from '../../../../../components/uni-table';
import { rowActionKind } from '../../../../../components/uni-action';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { rosterTimeAdjustmentApi } from '../../../services/performance';
import type {
  PerformanceScopeType,
  RosterTimeAdjustment,
  RosterTimeAdjustmentKind,
} from '../../../types/performance';
import {
  PerformanceScopeFormFields,
  renderPerformanceScopeLabel,
} from '../components/PerformanceScopeFormFields';
import { renderActiveTag } from '../components/performanceMeta';
import { normalizePerformanceListResponse } from '../../../utils/performanceListCore';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';

const ROSTER_RESOURCE = 'kuaizhizao:performance-shift-rosters';

type TempForm = {
  scopeType: PerformanceScopeType;
  departmentId?: number;
  employeeId?: number;
  workDate: Dayjs;
  kind: RosterTimeAdjustmentKind;
  timeRange: [Dayjs, Dayjs];
  reason: string;
  isActive: boolean;
};

export type ShiftRosterTempAdjustmentPanelProps = {
  periodStart: string;
  periodEnd: string;
  employeeOptions: Array<{ label: string; value: number }>;
  employeeIds?: number[];
};

function renderKindTag(t: (key: string) => string, kind: RosterTimeAdjustmentKind) {
  if (kind === 'temp_overtime') {
    return (
      <MarkerTag color="processing">{t('app.kuaizhizao.performance.rosters.tempAdjust.kindOvertime')}</MarkerTag>
    );
  }
  return (
    <MarkerTag color="default">{t('app.kuaizhizao.performance.rosters.tempAdjust.kindRest')}</MarkerTag>
  );
}

export const ShiftRosterTempAdjustmentPanel: React.FC<ShiftRosterTempAdjustmentPanelProps> = ({
  periodStart,
  periodEnd,
  employeeOptions,
  employeeIds,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const rosterPerms = useResourcePermissions(ROSTER_RESOURCE);
  const actionRef = useRef<ActionType>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<RosterTimeAdjustment | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<TempForm>();

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({
      scopeType: 'employee',
      departmentId: undefined,
      employeeId: employeeOptions[0]?.value,
      workDate: dayjs(periodStart),
      kind: 'temp_overtime',
      timeRange: [dayjs('18:00', 'HH:mm'), dayjs('20:00', 'HH:mm')],
      reason: '',
      isActive: true,
    });
    setModalOpen(true);
  };

  const openEdit = (row: RosterTimeAdjustment) => {
    setEditing(row);
    form.setFieldsValue({
      scopeType: row.scopeType || 'employee',
      departmentId: row.departmentId ?? undefined,
      employeeId: row.employeeId ?? undefined,
      workDate: dayjs(row.workDate),
      kind: row.kind,
      timeRange: [
        dayjs(row.startTime.slice(0, 5), 'HH:mm'),
        dayjs(row.endTime.slice(0, 5), 'HH:mm'),
      ],
      reason: row.reason,
      isActive: row.isActive,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const payload = {
        scopeType: values.scopeType,
        departmentId: values.scopeType === 'department' ? values.departmentId : undefined,
        employeeId: values.scopeType === 'employee' ? values.employeeId : undefined,
        workDate: values.workDate.format('YYYY-MM-DD'),
        kind: values.kind,
        startTime: values.timeRange[0].format('HH:mm'),
        endTime: values.timeRange[1].format('HH:mm'),
        reason: values.reason.trim(),
        isActive: values.isActive,
      };
      if (editing) {
        await rosterTimeAdjustmentApi.update(editing.uuid, payload);
      } else {
        await rosterTimeAdjustmentApi.create(payload);
      }
      messageApi.success(t('app.kuaizhizao.performance.rosters.tempAdjust.messages.saved'));
      setModalOpen(false);
      actionRef.current?.reload();
    } catch (e: any) {
      if (e?.errorFields) return;
      messageApi.error(e?.message || t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const columns: ProColumns<RosterTimeAdjustment>[] = useMemo(
    () =>
      alignProColumns<RosterTimeAdjustment>(
        [
          {
            title: t('app.kuaizhizao.performance.scope.label'),
            dataIndex: 'scopeType',
            fixed: 'left',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            render: (_, r) => renderPerformanceScopeLabel(t, r.scopeType || 'employee', r),
          },
          {
            title: t('app.kuaizhizao.performance.rosters.tempAdjust.columns.kind'),
            dataIndex: 'kind',
            width: 112,
            minWidth: 112,
            uniTableKeepWidth: true,
            render: (_, r) => renderKindTag(t, r.kind),
          },
          {
            title: t('app.kuaizhizao.performance.workCalendar.columns.overtimeDate'),
            dataIndex: 'workDate',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
          },
          {
            title: t('app.kuaizhizao.performance.workCalendar.columns.timeRange'),
            key: 'timeRange',
            dataIndex: 'startTime',
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            render: (_, r) =>
              `${(r.startTime || '').slice(0, 5)} ~ ${(r.endTime || '').slice(0, 5)}`,
          },
          {
            title: t('app.kuaizhizao.performance.workCalendar.columns.reason'),
            dataIndex: 'reason',
            ellipsis: true,
            minWidth: 160,
            uniTableRemainderFlex: true,
          },
          {
            title: t('common.status'),
            dataIndex: 'isActive',
            width: 88,
            minWidth: 88,
            uniTableKeepWidth: true,
            render: (_, r) => renderActiveTag(t, r.isActive, 'inactive'),
          },
          {
            title: t('common.actions'),
            key: 'action',
            valueType: 'option',
            fixed: 'right',
            render: (_, row) => (
              <Space>
                {rosterPerms.canUpdate ? (
                  <Button key="edit" {...rowActionKind('update')} onClick={() => openEdit(row)}>
                    {t('common.edit')}
                  </Button>
                ) : null}
                {rosterPerms.canDelete ? (
                  <Popconfirm
                    key="delete"
                    {...rowActionKind('delete')}
                    title={t('app.kuaizhizao.performance.workCalendar.messages.deleteConfirm')}
                    onConfirm={async () => {
                      try {
                        await rosterTimeAdjustmentApi.delete(row.uuid);
                        messageApi.success(t('common.deleteSuccess'));
                        actionRef.current?.reload();
                      } catch (e: any) {
                        messageApi.error(e?.message || t('common.deleteFailed'));
                      }
                    }}
                  >
                    <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                      {t('common.delete')}
                    </Button>
                  </Popconfirm>
                ) : null}
              </Space>
            ),
          },
        ],
        SALES_DOC_LIST_FIELD_RANK,
      ),
    [messageApi, rosterPerms.canDelete, rosterPerms.canUpdate, t],
  );

  const listEmployeeIds =
    employeeIds && employeeIds.length > 0 ? employeeIds : undefined;

  return (
    <>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('app.kuaizhizao.performance.rosters.tempAdjust.hint', { start: periodStart, end: periodEnd })}
      </Typography.Paragraph>
      <UniTable<RosterTimeAdjustment>
        headerTitle={t('app.kuaizhizao.performance.rosters.tempAdjust.tableTitle')}
        columnPersistenceId="apps.kuaizhizao.pages.performance.shift-rosters.temp-adjust.v2"
        permissionResource={ROSTER_RESOURCE}
        actionRef={actionRef}
        columns={columns}
        rowKey="uuid"
        viewTypes={['table']}
        showFuzzySearch={false}
        showAdvancedSearch={false}
        showCreateButton={rosterPerms.canCreate}
        createButtonText={t('app.kuaizhizao.performance.rosters.tempAdjust.createButton')}
        onCreate={openCreate}
        request={async (params) => {
          try {
            const pageSize = params.pageSize || 20;
            const skip = ((params.current || 1) - 1) * pageSize;
            const res = await rosterTimeAdjustmentApi.list({
              skip,
              limit: pageSize,
              dateFrom: periodStart,
              dateTo: periodEnd,
              employeeIds: listEmployeeIds,
            });
            const { data, total } = normalizePerformanceListResponse(res);
            return { data: data as RosterTimeAdjustment[], success: true, total };
          } catch (e: any) {
            messageApi.error(
              e?.message || t('app.kuaizhizao.performance.workCalendar.messages.loadFailed'),
            );
            return { data: [], success: false, total: 0 };
          }
        }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        enableRowSelection={rosterPerms.canDelete}
        showDeleteButton={rosterPerms.canDelete}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => rosterTimeAdjustmentApi.delete(String(key))));
          messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
          actionRef.current?.reload();
        }}
      />

      <Modal
        title={
          editing
            ? t('app.kuaizhizao.performance.rosters.tempAdjust.editTitle')
            : t('app.kuaizhizao.performance.rosters.tempAdjust.createTitle')
        }
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => void handleSave()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={form} layout="vertical">
          <PerformanceScopeFormFields form={form} defaultScope="employee" />
          <Form.Item
            name="kind"
            label={t('app.kuaizhizao.performance.rosters.tempAdjust.columns.kind')}
            rules={[{ required: true }]}
          >
            <Select
              options={[
                {
                  value: 'temp_overtime',
                  label: t('app.kuaizhizao.performance.rosters.tempAdjust.kindOvertime'),
                },
                {
                  value: 'temp_rest',
                  label: t('app.kuaizhizao.performance.rosters.tempAdjust.kindRest'),
                },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="workDate"
            label={t('app.kuaizhizao.performance.workCalendar.columns.overtimeDate')}
            rules={[{ required: true }]}
          >
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="timeRange"
            label={t('app.kuaizhizao.performance.workCalendar.columns.timeRange')}
            rules={[{ required: true }]}
          >
            <TimePicker.RangePicker format="HH:mm" needConfirm={false} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="reason"
            label={t('app.kuaizhizao.performance.workCalendar.columns.reason')}
            rules={[{ required: true, whitespace: true }]}
          >
            <Input.TextArea maxLength={500} rows={2} />
          </Form.Item>
          <Form.Item name="isActive" label={t('common.status')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};
