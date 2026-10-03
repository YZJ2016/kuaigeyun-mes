/**
 * 班次排班页 - 工位停机窗
 */

import React, { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ActionType, ProColumns } from '@ant-design/pro-components';
import {
  App,
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Typography,
} from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { UniTable } from '../../../../../components/uni-table';
import {
  UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
  UniTableStackedPrimaryCell,
} from '../../../../../components/uni-table/stackedPrimaryColumn';
import { rowActionKind } from '../../../../../components/uni-action';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { stationUnavailableApi } from '../../../services/performance';
import type { StationUnavailableWindow } from '../../../types/performance';
import { renderActiveTag } from '../components/performanceMeta';
import { normalizePerformanceListResponse } from '../../../utils/performanceListCore';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';

const CALENDAR_RESOURCE = 'kuaizhizao:performance-work-calendar';

export const ShiftRosterDowntimePanel: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const calendarPerms = useResourcePermissions(CALENDAR_RESOURCE);
  const actionRef = useRef<ActionType>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<StationUnavailableWindow | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<{
    stationId: number;
    range: [Dayjs, Dayjs];
    reason?: string;
    isActive: boolean;
  }>();

  const openCreate = () => {
    setEditing(null);
    form.setFieldsValue({
      stationId: undefined as unknown as number,
      range: [dayjs().startOf('hour'), dayjs().startOf('hour').add(2, 'hour')],
      reason: undefined,
      isActive: true,
    });
    setModalOpen(true);
  };

  const columns: ProColumns<StationUnavailableWindow>[] = useMemo(
    () =>
      alignProColumns<StationUnavailableWindow>(
        [
          {
            title: t('app.kuaizhizao.performance.workCalendar.columns.stationId'),
            dataIndex: 'stationId',
            ...UNI_TABLE_STACKED_PRIMARY_COLUMN_DEFAULTS,
            fixed: 'left',
            render: (_, r) => (
              <UniTableStackedPrimaryCell
                primary={String(r.stationId ?? '-')}
                secondary={String(r.reason ?? '').trim() || '-'}
                secondaryCopyable={false}
              />
            ),
          },
          {
            title: t('app.kuaizhizao.performance.workCalendar.columns.startAt'),
            dataIndex: 'startAt',
            width: 156,
            minWidth: 156,
            uniTableKeepWidth: true,
            render: (_, r) => dayjs(r.startAt).format('YYYY-MM-DD HH:mm'),
          },
          {
            title: t('app.kuaizhizao.performance.workCalendar.columns.endAt'),
            dataIndex: 'endAt',
            width: 156,
            minWidth: 156,
            uniTableKeepWidth: true,
            render: (_, r) => dayjs(r.endAt).format('YYYY-MM-DD HH:mm'),
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
                {calendarPerms.canUpdate ? (
                  <Button
                    key="edit"
                    {...rowActionKind('update')}
                    onClick={() => {
                      setEditing(row);
                      form.setFieldsValue({
                        stationId: row.stationId,
                        range: [dayjs(row.startAt), dayjs(row.endAt)],
                        reason: row.reason || undefined,
                        isActive: row.isActive,
                      });
                      setModalOpen(true);
                    }}
                  >
                    {t('common.edit')}
                  </Button>
                ) : null}
                {calendarPerms.canDelete ? (
                  <Popconfirm
                    key="delete"
                    {...rowActionKind('delete')}
                    title={t('app.kuaizhizao.performance.workCalendar.messages.downtimeDeleteConfirm')}
                    onConfirm={async () => {
                      try {
                        await stationUnavailableApi.delete(row.uuid);
                        messageApi.success(
                          t('app.kuaizhizao.performance.workCalendar.messages.downtimeDeleted'),
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
    [calendarPerms.canDelete, calendarPerms.canUpdate, form, messageApi, t],
  );

  return (
    <>
      <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
        {t('app.kuaizhizao.performance.workCalendar.downtimeHint')}
      </Typography.Paragraph>
      <UniTable<StationUnavailableWindow>
        headerTitle={t('app.kuaizhizao.performance.workCalendar.downtimeTableTitle')}
        columnPersistenceId="apps.kuaizhizao.pages.performance.shift-rosters.downtime.v1"
        permissionResource={CALENDAR_RESOURCE}
        actionRef={actionRef}
        rowKey="uuid"
        viewTypes={['table']}
        showFuzzySearch={false}
        showAdvancedSearch={false}
        columns={columns}
        showCreateButton={calendarPerms.canUpdate}
        createButtonText={t('app.kuaizhizao.performance.workCalendar.createDowntime')}
        onCreate={openCreate}
        request={async (params) => {
          try {
            const pageSize = params.pageSize || 20;
            const skip = ((params.current || 1) - 1) * pageSize;
            const res = await stationUnavailableApi.list({ skip, limit: pageSize });
            const { data, total } = normalizePerformanceListResponse(res);
            return { data: data as StationUnavailableWindow[], success: true, total };
          } catch (e: any) {
            messageApi.error(
              e?.message || t('app.kuaizhizao.performance.workCalendar.messages.loadFailed'),
            );
            return { data: [], success: false, total: 0 };
          }
        }}
        pagination={{ defaultPageSize: 20, showSizeChanger: true }}
        enableRowSelection={calendarPerms.canDelete}
        showDeleteButton={calendarPerms.canDelete}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => stationUnavailableApi.delete(String(key))));
          messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
          actionRef.current?.reload();
        }}
      />

      <Modal
        title={
          editing
            ? t('app.kuaizhizao.performance.workCalendar.editDowntime')
            : t('app.kuaizhizao.performance.workCalendar.createDowntime')
        }
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        destroyOnHidden
        onOk={async () => {
          try {
            const values = await form.validateFields();
            setSaving(true);
            const payload = {
              stationId: Number(values.stationId),
              startAt: values.range[0].toISOString(),
              endAt: values.range[1].toISOString(),
              reason: values.reason?.trim() || undefined,
              isActive: values.isActive,
            };
            if (editing) {
              await stationUnavailableApi.update(editing.uuid, payload);
            } else {
              await stationUnavailableApi.create(payload);
            }
            messageApi.success(t('app.kuaizhizao.performance.workCalendar.messages.downtimeSaved'));
            setModalOpen(false);
            actionRef.current?.reload();
          } catch (e: any) {
            if (e?.errorFields) return;
            messageApi.error(e?.message || t('common.saveFailed'));
          } finally {
            setSaving(false);
          }
        }}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="stationId"
            label={t('app.kuaizhizao.performance.workCalendar.columns.stationId')}
            rules={[{ required: true }]}
          >
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="range"
            label={t('app.kuaizhizao.performance.workCalendar.columns.timeRange')}
            rules={[{ required: true }]}
          >
            <DatePicker.RangePicker showTime format="YYYY-MM-DD HH:mm" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="reason" label={t('app.kuaizhizao.performance.workCalendar.columns.reason')}>
            <Input maxLength={200} />
          </Form.Item>
          <Form.Item name="isActive" label={t('common.status')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};
