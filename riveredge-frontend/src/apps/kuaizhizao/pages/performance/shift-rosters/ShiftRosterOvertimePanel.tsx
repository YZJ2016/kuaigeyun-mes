/**
 * 班次排班页 - 厂级加班管理
 */

import React, { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button, DatePicker, Form, Input, Modal, Popconfirm, Space, Switch, TimePicker, Typography } from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { UniTable } from '../../../../../components/uni-table';
import {
  UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
  UniTableStackedPrimaryCell,
} from '../../../../../components/uni-table/stackedPrimaryColumn';
import { rowActionKind } from '../../../../../components/uni-action';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { overtimeApi } from '../../../services/performance';
import type { OvertimePlan, PerformanceScopeType } from '../../../types/performance';
import {
  PerformanceScopeFormFields,
  renderPerformanceScopeLabel,
} from '../components/PerformanceScopeFormFields';
import { renderActiveTag } from '../components/performanceMeta';
import { normalizePerformanceListResponse } from '../../../utils/performanceListCore';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';

const OVERTIME_RESOURCE = 'kuaizhizao:performance-overtimes';

type OvertimeForm = {
  overtimeDate: Dayjs;
  timeRange: [Dayjs, Dayjs];
  name?: string;
  reason?: string;
  scopeType: PerformanceScopeType;
  departmentId?: number;
  employeeId?: number;
  isActive: boolean;
};

export type ShiftRosterOvertimePanelProps = {
  periodStart: string;
  periodEnd: string;
};

export const ShiftRosterOvertimePanel: React.FC<ShiftRosterOvertimePanelProps> = ({
  periodStart,
  periodEnd,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const overtimePerms = useResourcePermissions(OVERTIME_RESOURCE);
  const actionRef = useRef<ActionType>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<OvertimePlan | null>(null);
  const [saving, setSaving] = useState(false);
  const [otForm] = Form.useForm<OvertimeForm>();

  const openCreate = () => {
    setEditing(null);
    otForm.setFieldsValue({
      overtimeDate: dayjs(periodStart),
      timeRange: [dayjs('18:00', 'HH:mm'), dayjs('20:00', 'HH:mm')],
      name: undefined,
      reason: undefined,
      scopeType: 'plant',
      departmentId: undefined,
      employeeId: undefined,
      isActive: true,
    });
    setModalOpen(true);
  };

  const openEdit = (row: OvertimePlan) => {
    setEditing(row);
    otForm.setFieldsValue({
      overtimeDate: dayjs(row.overtimeDate),
      timeRange: [
        dayjs(row.startTime.slice(0, 5), 'HH:mm'),
        dayjs(row.endTime.slice(0, 5), 'HH:mm'),
      ],
      name: row.name || undefined,
      reason: row.reason || undefined,
      scopeType: row.scopeType || 'plant',
      departmentId: row.departmentId ?? undefined,
      employeeId: row.employeeId ?? undefined,
      isActive: row.isActive,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    try {
      const values = await otForm.validateFields();
      setSaving(true);
      const payload = {
        overtimeDate: values.overtimeDate.format('YYYY-MM-DD'),
        startTime: values.timeRange[0].format('HH:mm'),
        endTime: values.timeRange[1].format('HH:mm'),
        name: values.name?.trim() || undefined,
        reason: values.reason?.trim() || undefined,
        scopeType: values.scopeType,
        departmentId: values.scopeType === 'department' ? values.departmentId : undefined,
        employeeId: values.scopeType === 'employee' ? values.employeeId : undefined,
        isActive: values.isActive,
      };
      if (editing) {
        await overtimeApi.update(editing.uuid, payload);
      } else {
        await overtimeApi.create(payload);
      }
      messageApi.success(t('app.kuaizhizao.performance.workCalendar.messages.overtimeSaved'));
      setModalOpen(false);
      actionRef.current?.reload();
    } catch (e: any) {
      if (e?.errorFields) return;
      messageApi.error(e?.message || t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const columns: ProColumns<OvertimePlan>[] = useMemo(
    () =>
      alignProColumns<OvertimePlan>(
        [
          {
            title: t('common.name'),
            key: 'performance_holiday_stacked',
            dataIndex: 'name',
            ...UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
            fixed: 'left',
            hideInSearch: true,
            render: (_, r) => (
              <UniTableStackedPrimaryCell
                primary={String(r.name ?? '').trim() || '-'}
                secondary={renderPerformanceScopeLabel(t, r.scopeType || 'plant', r)}
                secondaryCopyable={false}
              />
            ),
          },
          {
            title: t('app.kuaizhizao.performance.scope.label'),
            dataIndex: 'scopeType',
            width: 112,
            minWidth: 112,
            uniTableKeepWidth: true,
            hideInTable: true,
            render: (_, r) => renderPerformanceScopeLabel(t, r.scopeType || 'plant', r),
          },
          {
            title: t('app.kuaizhizao.performance.workCalendar.columns.overtimeDate'),
            dataIndex: 'overtimeDate',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
          },
          {
            title: t('app.kuaizhizao.performance.workCalendar.columns.timeRange'),
            key: 'timeRange',
            dataIndex: 'startTime',
            hideInSearch: true,
            width: 140,
            minWidth: 140,
            uniTableKeepWidth: true,
            resizable: false,
            render: (_, r) =>
              `${(r.startTime || '').slice(0, 5)} ~ ${(r.endTime || '').slice(0, 5)}`,
          },
          {
            title: t('app.kuaizhizao.performance.workCalendar.columns.reason'),
            dataIndex: 'reason',
            ellipsis: true,
            minWidth: 160,
            uniTableRemainderFlex: true,
            hideInSearch: true,
            render: (_, r) => String(r.reason ?? '').trim() || '-',
          },
          {
            title: t('common.status'),
            dataIndex: 'isActive',
            hideInSearch: true,
            width: 88,
            minWidth: 88,
            uniTableKeepWidth: true,
            resizable: false,
            render: (_, r) => renderActiveTag(t, r.isActive, 'inactive'),
          },
          {
            title: t('common.actions'),
            key: 'action',
            valueType: 'option',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => (
              <Space>
                {overtimePerms.canUpdate ? (
                  <Button key="edit" {...rowActionKind('update')} onClick={() => openEdit(row)}>
                    {t('common.edit')}
                  </Button>
                ) : null}
                {overtimePerms.canDelete ? (
                  <Popconfirm
                    key="delete"
                    {...rowActionKind('delete')}
                    title={t('app.kuaizhizao.performance.workCalendar.messages.deleteConfirm')}
                    onConfirm={async () => {
                      try {
                        await overtimeApi.delete(row.uuid);
                        messageApi.success(
                          t('app.kuaizhizao.performance.workCalendar.messages.overtimeDeleted'),
                        );
                        actionRef.current?.reload();
                      } catch (e: any) {
                        messageApi.error(e?.message || t('common.saveFailed'));
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
    [messageApi, overtimePerms.canDelete, overtimePerms.canUpdate, t],
  );

  return (
    <>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('app.kuaizhizao.performance.rosters.overtime.hint', { start: periodStart, end: periodEnd })}
      </Typography.Paragraph>
      <UniTable<OvertimePlan>
        headerTitle={t('app.kuaizhizao.performance.workCalendar.overtimeTableTitle')}
        columnPersistenceId="apps.kuaizhizao.pages.performance.shift-rosters.overtime.v2"
        permissionResource={OVERTIME_RESOURCE}
        actionRef={actionRef}
        columns={columns}
        rowKey="uuid"
        viewTypes={['table']}
        showFuzzySearch={false}
        showAdvancedSearch={false}
        showCreateButton={overtimePerms.canCreate}
        createButtonText={t('app.kuaizhizao.performance.workCalendar.createOvertime')}
        onCreate={openCreate}
        request={async (params) => {
          try {
            const pageSize = params.pageSize || 20;
            const skip = ((params.current || 1) - 1) * pageSize;
            const res = await overtimeApi.list({
              skip,
              limit: pageSize,
              dateFrom: periodStart,
              dateTo: periodEnd,
            });
            const { data, total } = normalizePerformanceListResponse(res);
            return { data: data as OvertimePlan[], success: true, total };
          } catch (e: any) {
            messageApi.error(
              e?.message || t('app.kuaizhizao.performance.workCalendar.messages.loadFailed'),
            );
            return { data: [], success: false, total: 0 };
          }
        }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        enableRowSelection={overtimePerms.canDelete}
        showDeleteButton={overtimePerms.canDelete}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => overtimeApi.delete(String(key))));
          messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
          actionRef.current?.reload();
        }}
      />

      <Modal
        title={
          editing
            ? t('app.kuaizhizao.performance.workCalendar.editOvertime')
            : t('app.kuaizhizao.performance.workCalendar.createOvertime')
        }
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => void handleSave()}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form form={otForm} layout="vertical">
          <PerformanceScopeFormFields form={otForm} defaultScope="plant" />
          <Form.Item
            name="overtimeDate"
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
          <Form.Item name="name" label={t('common.name')}>
            <Input maxLength={200} />
          </Form.Item>
          <Form.Item name="reason" label={t('app.kuaizhizao.performance.workCalendar.columns.reason')}>
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
