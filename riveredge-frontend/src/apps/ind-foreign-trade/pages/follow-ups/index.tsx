import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button, Space, Typography } from 'antd';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate, DetailDrawerTemplate, DRAWER_CONFIG } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { ActionConfirmPopconfirm } from '../../../../components/action-confirm';
import { rowActionKind } from '../../../../components/uni-action';
import { MarkerTag } from '../../../../constants/statusBadges';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../utils/uniTableLayoutColumns';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { formatDateTime } from '../../../../utils/format';
import { formDateRangeFormItemProps } from '../../../../utils/formDate';
import {
  extractProTableSort,
  pickListSearchKeyword,
  pickSearchDateTimeRange,
  pickSearchString,
} from '../../../../utils/tableQueryKey';
import {
  getDictionaryOptions,
  getDictionaryOptionsSync,
} from '../../../master-data/services/supply-chain';
import {
  CustomerFollowUpFormModal,
  type CustomerFollowUpPreset,
} from '../../../kuaizhizao/components/CustomerFollowUpFormModal';
import { CustomerFollowUpAttachments } from '../../../kuaizhizao/components/CustomerFollowUpAttachments';
import {
  foreignTradeApi,
  foreignTradeFollowUpPersistApi,
  type CustomerFollowUp,
  type CustomerPoolItem,
} from '../../services/foreignTradeApi';
import type { Customer } from '../../../master-data/types/supply-chain';

const DICT_CODE = 'SALES_FOLLOW_UP_TYPE';

export default function ExportFollowUpsPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const actionRef = useRef<ActionType>(null);
  const perms = useResourcePermissions('ind-foreign-trade:follow-up');
  const [activityOptions, setActivityOptions] = useState<{ label: string; value: string }[]>(
    () => getDictionaryOptionsSync(DICT_CODE) ?? [],
  );
  const [customers, setCustomers] = useState<CustomerPoolItem[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<CustomerFollowUp | null>(null);
  const [preset, setPreset] = useState<CustomerFollowUpPreset | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRecord, setDetailRecord] = useState<CustomerFollowUp | null>(null);

  useEffect(() => {
    getDictionaryOptions(DICT_CODE)
      .then((opts) => setActivityOptions(opts || []))
      .catch(() => setActivityOptions([]));
    foreignTradeApi
      .listExportCustomers({ skip: 0, limit: 200 })
      .then((res) => setCustomers(res.items || []))
      .catch(() => setCustomers([]));
  }, []);

  const activityLabel = useCallback(
    (code?: string) => activityOptions.find((o) => o.value === code)?.label || code || '—',
    [activityOptions],
  );

  const customerSearchOptions = useMemo(
    () =>
      customers.map((c) => ({
        value: c.id,
        label: `${c.code} ${c.name}`.trim(),
      })),
    [customers],
  );

  const customerLoader = useCallback(async (): Promise<Customer[]> => {
    const res = await foreignTradeApi.listExportCustomers({ skip: 0, limit: 200 });
    return (res.items || []).map((row) => ({
      id: row.id,
      uuid: row.uuid,
      code: row.code,
      name: row.name,
      isActive: true,
      createdAt: row.created_at,
      updatedAt: row.updated_at,
    }));
  }, []);

  const handleDelete = useCallback(
    async (record: CustomerFollowUp) => {
      await foreignTradeApi.deleteFollowUp(record.id);
      message.success(t('common.deleteSuccess'));
      actionRef.current?.reload();
      if (detailRecord?.id === record.id) {
        setDetailOpen(false);
        setDetailRecord(null);
      }
    },
    [detailRecord?.id, message, t],
  );

  const columns: ProColumns<CustomerFollowUp>[] = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.customerFollowUp.colCustomer'),
        dataIndex: 'customer_id',
        hideInTable: true,
        valueType: 'select',
        fieldProps: {
          showSearch: true,
          optionFilterProp: 'label',
          options: customerSearchOptions,
        },
      },
      {
        title: t('app.kuaizhizao.customerFollowUp.colCustomer'),
        dataIndex: 'customer_name',
        ellipsis: true,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.customerFollowUp.colActivityType'),
        dataIndex: 'activity_type_code',
        hideInTable: true,
        valueType: 'select',
        fieldProps: {
          options: activityOptions,
          allowClear: true,
        },
      },
      {
        title: t('app.kuaizhizao.customerFollowUp.colActivityType'),
        dataIndex: 'activity_type_code',
        hideInSearch: true,
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        render: (_, row) => <MarkerTag color="processing">{activityLabel(row.activity_type_code)}</MarkerTag>,
      },
      {
        title: t('app.kuaizhizao.customerFollowUp.colContent'),
        dataIndex: 'content',
        ellipsis: true,
        hideInSearch: true,
      },
      {
        title: t('app.kuaizhizao.customerFollowUp.colOccurredAt'),
        dataIndex: 'occurred_at',
        width: 160,
        hideInSearch: true,
        render: (_, row) =>
          row.occurred_at ? formatDateTime(row.occurred_at, 'YYYY-MM-DD HH:mm') : '—',
      },
      {
        title: t('app.kuaizhizao.customerFollowUp.colOccurredAt'),
        dataIndex: 'occurred_at_range',
        valueType: 'dateTimeRange',
        hideInTable: true,
        formItemProps: formDateRangeFormItemProps,
      },
      {
        title: t('app.kuaizhizao.customerFollowUp.colFollowUpCount'),
        dataIndex: 'follow_up_count',
        width: 88,
        hideInSearch: true,
        render: (_, row) => String(row.follow_up_count ?? 0),
      },
      {
        title: t('app.kuaizhizao.customerFollowUp.colFollowUpPerson'),
        dataIndex: 'created_by_name',
        width: 100,
        hideInSearch: true,
        render: (_, row) => row.created_by_name || '—',
      },
      {
        title: t('common.actions'),
        key: 'action',
        hideInSearch: true,
        fixed: 'right',
        render: (_, record) => {
          const parts: React.ReactNode[] = [];
          if (perms.canUpdate) {
            parts.push(
              <Button
                {...rowActionKind('update')}
                key="e"
                onClick={() => {
                  setEditing(record);
                  setPreset(null);
                  setModalOpen(true);
                }}
              />,
            );
          }
          if (perms.canDelete) {
            parts.push(
              <ActionConfirmPopconfirm
                key="del"
                title={t('app.kuaizhizao.customerFollowUp.deleteConfirm')}
                onConfirm={() => void handleDelete(record)}
              >
                <Button {...rowActionKind('delete')} onClick={(e) => e.stopPropagation()} />
              </ActionConfirmPopconfirm>,
            );
          }
          return parts;
        },
      },
    ],
    [activityLabel, activityOptions, customerSearchOptions, handleDelete, perms.canDelete, perms.canUpdate, t],
  );

  const openCreate = useCallback(() => {
    setEditing(null);
    setPreset(null);
    setModalOpen(true);
  }, []);

  return (
    <ListPageTemplate>
      <UniTable<CustomerFollowUp>
        actionRef={actionRef}
        rowKey="id"
        headerTitle={t('app.ind-foreign-trade.menu.followUps')}
        columnPersistenceId="apps.ind-foreign-trade.pages.follow-ups-v2"
        permissionResource="ind-foreign-trade:follow-up"
        columns={columns}
        createButtonText={t('app.kuaizhizao.customerFollowUp.new')}
        showCreateButton
        onCreate={openCreate}
        onRow={(record) => ({
          onClick: () => {
            setDetailRecord(record);
            setDetailOpen(true);
          },
        })}
        request={async (params, sort, _filter, searchFormValues) => {
          const { sortBy, sortOrder } = extractProTableSort(sort);
          const orderBy =
            sortBy && sortOrder ? (sortOrder === 'desc' ? `-${sortBy}` : sortBy) : undefined;
          const { from: occurredFrom, to: occurredTo } = pickSearchDateTimeRange(
            searchFormValues,
            'occurred_from',
            'occurred_to',
            'occurred_at_range',
          );
          const customerIdRaw = pickSearchString(searchFormValues, 'customer_id');
          const res = await foreignTradeApi.listFollowUps({
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize || 20,
            keyword: pickListSearchKeyword(searchFormValues),
            customerId:
              customerIdRaw != null && Number.isFinite(Number(customerIdRaw))
                ? Number(customerIdRaw)
                : undefined,
            activityTypeCode: pickSearchString(searchFormValues, 'activity_type_code'),
            occurredFrom,
            occurredTo,
            orderBy,
          });
          return { data: res.items || [], success: true, total: res.total || 0 };
        }}
      />
      <CustomerFollowUpFormModal
        open={modalOpen}
        editing={editing}
        preset={preset}
        persistApi={foreignTradeFollowUpPersistApi}
        customerLoader={customerLoader}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
          setPreset(null);
        }}
        onSuccess={() => actionRef.current?.reload()}
      />
      <DetailDrawerTemplate
        title={t('app.kuaizhizao.customerFollowUp.detailTitle', {
          suffix: detailRecord?.customer_name ? ` - ${detailRecord.customer_name}` : '',
        })}
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setDetailRecord(null);
        }}
        size={DRAWER_CONFIG.HALF_WIDTH}
        linesTitle={t('app.kuaizhizao.customerFollowUp.colContent')}
        lines={
          detailRecord ? (
            <Space orientation="vertical" size={12} style={{ width: '100%' }}>
              <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                {detailRecord.content?.trim() ? detailRecord.content : '—'}
              </Typography.Paragraph>
              <CustomerFollowUpAttachments
                uuids={
                  Array.isArray(detailRecord.attachment_uuids)
                    ? detailRecord.attachment_uuids.map(String).filter(Boolean)
                    : []
                }
              />
            </Space>
          ) : undefined
        }
      />
    </ListPageTemplate>
  );
}
