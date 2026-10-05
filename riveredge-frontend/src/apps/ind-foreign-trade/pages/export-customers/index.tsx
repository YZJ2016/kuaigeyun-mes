import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { App, Button } from 'antd';
import type { ActionType, ProColumns, ProFormInstance } from '@ant-design/pro-components';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ListPageTemplate } from '../../../../components/layout-templates';
import { UniTable } from '../../../../components/uni-table';
import { MarkerTag } from '../../../../constants/statusBadges';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../utils/uniTableLayoutColumns';
import { rowActionKind, rowActionAddFollowUpFromDocument } from '../../../../components/uni-action';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { formatDateTime } from '../../../../utils/format';
import { formDateRangeFormItemProps } from '../../../../utils/formDate';
import { downloadFile } from '../../../../utils';
import { getUserOptions } from '../../../master-data/services/supply-chain';
import { useImportDictionaryOptions } from '../../../../hooks/useImportDictionaryOptions';
import { CustomerFormModal } from '../../../master-data/components/CustomerFormModal';
import {
  CustomerFollowUpFormModal,
  type CustomerFollowUpPreset,
} from '../../../kuaizhizao/components/CustomerFollowUpFormModal';
import { resolveCustomerPoolListParams } from '../../../kuaizhizao/utils/customerPoolListCore';
import {
  foreignTradeApi,
  foreignTradeFollowUpPersistApi,
  type CustomerPoolItem,
} from '../../services/foreignTradeApi';
import type { Customer } from '../../../master-data/types/supply-chain';

export default function ExportCustomersPage() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const actionRef = useRef<ActionType>(null);
  const formRef = useRef<ProFormInstance>(undefined);
  const [searchParams] = useSearchParams();
  const urlKeyRef = useRef('');
  const lastListParamsRef = useRef<Record<string, string | number | boolean | undefined>>({});
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [customerModalOpen, setCustomerModalOpen] = useState(false);
  const [editUuid, setEditUuid] = useState<string | null>(null);
  const [followOpen, setFollowOpen] = useState(false);
  const [followPreset, setFollowPreset] = useState<CustomerFollowUpPreset | null>(null);
  const [salesmanOptions, setSalesmanOptions] = useState<{ label: string; value: number }[]>([]);
  const perms = useResourcePermissions('ind-foreign-trade:export-customer');
  const followPerms = useResourcePermissions('ind-foreign-trade:follow-up');
  const teamPerms = useResourcePermissions('ind-foreign-trade:sales-team');
  const poolDictOptions = useImportDictionaryOptions(['CUSTOMER_LEVEL']);
  const [inactiveAlertDays, setInactiveAlertDays] = useState(7);

  useEffect(() => {
    getUserOptions('ind-foreign-trade:export-customer')
      .then((opts) => setSalesmanOptions(opts.map((o) => ({ label: o.label, value: Number(o.value) }))))
      .catch(() => setSalesmanOptions([]));
  }, []);

  const persistApi = useMemo(
    () => ({
      get: foreignTradeApi.getExportCustomer,
      create: foreignTradeApi.createExportCustomer,
      update: foreignTradeApi.updateExportCustomer,
    }),
    [],
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
      countryCode: row.country_code ?? undefined,
      regionText: row.region_text ?? undefined,
      projectDescription: row.project_description ?? undefined,
      intentMaterialName: row.intent_material_name ?? undefined,
      marketScope: row.market_scope ?? undefined,
      campaignName: row.campaign_name ?? undefined,
      requiredCapacityText: row.required_capacity_text ?? undefined,
    }));
  }, []);

  const columns: ProColumns<CustomerPoolItem>[] = useMemo(
    () => [
      {
        title: t('field.customer.name'),
        dataIndex: 'name',
        ellipsis: true,
      },
      {
        title: t('field.customer.code'),
        dataIndex: 'code',
        width: 140,
      },
      {
        title: t('field.customer.salesman'),
        dataIndex: 'salesman_name',
        width: 100,
        hideInSearch: true,
        render: (_, row) => row.salesman_name || '—',
      },
      {
        title: t('field.customer.salesman'),
        dataIndex: 'salesmanId',
        hideInTable: true,
        hideInSearch: !teamPerms.canRead,
        valueType: 'select',
        fieldProps: {
          options: salesmanOptions,
          showSearch: true,
          optionFilterProp: 'label',
          allowClear: true,
        },
      },
      {
        title: t('field.customer.contactPerson'),
        dataIndex: 'contact_person',
        width: 120,
      },
      {
        title: t('field.customer.phone'),
        dataIndex: 'phone',
        width: 120,
      },
      {
        title: t('field.customer.email'),
        dataIndex: 'email',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.ind-foreign-trade.field.country'),
        dataIndex: 'country_code',
        width: 100,
        hideInSearch: true,
        render: (_, row) => row.country_code || '—',
      },
      {
        title: t('app.ind-foreign-trade.field.country'),
        dataIndex: 'countryCode',
        hideInTable: true,
        valueType: 'text',
        fieldProps: {
          placeholder: t('app.ind-foreign-trade.field.countryPlaceholder'),
        },
      },
      {
        title: t('field.customer.level'),
        dataIndex: 'customer_level_code',
        width: 88,
        hideInSearch: true,
        render: (_, row) => row.customer_level_code || '—',
      },
      {
        title: t('field.customer.level'),
        dataIndex: 'customerLevelCode',
        hideInTable: true,
        valueType: 'select',
        fieldProps: { allowClear: true, options: poolDictOptions.CUSTOMER_LEVEL },
      },
      {
        title: t('app.kuaizhizao.customerPool.intentMaterial'),
        dataIndex: 'intent_material_name',
        width: 140,
        ellipsis: true,
        hideInSearch: true,
        render: (_, row) => row.intent_material_name || '—',
      },
      {
        title: t('app.ind-foreign-trade.field.campaign'),
        dataIndex: 'campaign_name',
        width: 160,
        ellipsis: true,
        hideInSearch: true,
        render: (_, row) => row.campaign_name || '—',
      },
      {
        title: t('app.ind-foreign-trade.field.capacity'),
        dataIndex: 'required_capacity_text',
        width: 160,
        ellipsis: true,
        hideInSearch: true,
        render: (_, row) => row.required_capacity_text || '—',
      },
      {
        title: t('app.kuaizhizao.customerPool.intentMaterial'),
        dataIndex: 'intent_material_name',
        hideInTable: true,
      },
      {
        title: t('app.kuaizhizao.customerPool.followStatus'),
        dataIndex: 'follow_status',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        hideInSearch: true,
        render: (_, row) =>
          row.follow_status === 'followed' ? (
            <MarkerTag color="success">{t('app.kuaizhizao.customerPool.followStatusFollowed')}</MarkerTag>
          ) : (
            <MarkerTag color="warning">{t('app.kuaizhizao.customerPool.followStatusPending')}</MarkerTag>
          ),
      },
      {
        title: t('app.kuaizhizao.customerPool.followStatus'),
        dataIndex: 'follow_status',
        hideInTable: true,
        valueType: 'select',
        valueEnum: {
          pending: { text: t('app.kuaizhizao.customerPool.followStatusPending') },
          followed: { text: t('app.kuaizhizao.customerPool.followStatusFollowed') },
        },
        fieldProps: { allowClear: true },
      },
      {
        title: t('app.kuaizhizao.customerPool.followUpCount'),
        dataIndex: 'follow_up_count',
        width: 88,
        hideInSearch: true,
        render: (_, row) => String(row.follow_up_count ?? 0),
      },
      {
        title: t('app.kuaizhizao.customerPool.inactiveDays', { days: inactiveAlertDays }),
        dataIndex: 'inactive',
        ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
        hideInSearch: true,
        render: (_, row) =>
          row.inactive ? (
            <MarkerTag color="error">
              {t('app.kuaizhizao.customerPool.inactiveDaysTag', { days: inactiveAlertDays })}
            </MarkerTag>
          ) : (
            '—'
          ),
      },
      {
        title: t('app.kuaizhizao.customerPool.inactiveDays', { days: inactiveAlertDays }),
        dataIndex: 'inactive',
        hideInTable: true,
        valueType: 'select',
        valueEnum: {
          true: {
            text: t('app.kuaizhizao.customerPool.inactiveDaysOnly', { days: inactiveAlertDays }),
          },
        },
        fieldProps: { allowClear: true },
      },
      {
        title: t('field.customer.lastFollowUpAt'),
        dataIndex: 'last_follow_up_at',
        width: 140,
        hideInSearch: true,
        render: (_, row) =>
          row.last_follow_up_at ? formatDateTime(row.last_follow_up_at, 'YYYY-MM-DD HH:mm') : '—',
      },
      {
        title: t('field.customer.lastFollowUpAt'),
        dataIndex: 'last_follow_up_at_range',
        valueType: 'dateTimeRange',
        hideInTable: true,
        formItemProps: formDateRangeFormItemProps,
      },
      {
        title: t('common.createdAt'),
        dataIndex: 'created_at_range',
        valueType: 'dateRange',
        hideInTable: true,
        formItemProps: formDateRangeFormItemProps,
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
                  setEditUuid(record.uuid);
                  setCustomerModalOpen(true);
                }}
              />,
            );
          }
          if (followPerms.canCreate) {
            parts.push(
              <Button
                {...rowActionAddFollowUpFromDocument('create')}
                key="fu"
                onClick={() => {
                  setFollowPreset({ customer_id: record.id });
                  setFollowOpen(true);
                }}
              />,
            );
          }
          return parts;
        },
      },
    ],
    [
      followPerms.canCreate,
      inactiveAlertDays,
      perms.canUpdate,
      poolDictOptions.CUSTOMER_LEVEL,
      salesmanOptions,
      t,
      teamPerms.canRead,
    ],
  );

  const openCreate = useCallback(() => {
    setEditUuid(null);
    setCustomerModalOpen(true);
  }, []);

  const handleExport = useCallback(
    async (
      type: 'selected' | 'currentPage' | 'all',
      selectedKeys?: React.Key[],
      currentPageData?: CustomerPoolItem[],
    ) => {
      let exportData: CustomerPoolItem[] = [];
      if (type === 'selected' && selectedKeys?.length) {
        const selectedSet = new Set(selectedKeys.map((key) => String(key)));
        exportData = (currentPageData || []).filter((item) => selectedSet.has(String(item.id)));
      } else if (type === 'currentPage') {
        exportData = currentPageData || [];
      } else {
        const rows: CustomerPoolItem[] = [];
        const pageSize = 200;
        let skip = 0;
        let total = 0;
        do {
          const res = await foreignTradeApi.listExportCustomers({
            skip,
            limit: pageSize,
            ...lastListParamsRef.current,
          });
          rows.push(...(res.items || []));
          total = res.total || 0;
          skip += pageSize;
        } while (skip < total);
        exportData = rows;
      }
      if (exportData.length === 0) {
        message.warning(t('app.master-data.noExportData'));
        return;
      }
      const headers = [
        t('field.customer.code'),
        t('field.customer.name'),
        t('app.ind-foreign-trade.field.country'),
        t('field.customer.contactPerson'),
        t('field.customer.phone'),
        t('field.customer.email'),
        t('field.customer.level'),
        t('app.kuaizhizao.customerPool.intentMaterial'),
        t('app.ind-foreign-trade.field.campaign'),
        t('app.ind-foreign-trade.field.capacity'),
        t('app.kuaizhizao.customerPool.followStatus'),
        t('app.kuaizhizao.customerPool.followUpCount'),
        t('field.customer.salesman'),
        t('field.customer.lastFollowUpAt'),
      ];
      const csvRows = [headers.join(',')];
      for (const row of exportData) {
        const followStatus =
          row.follow_status === 'followed'
            ? t('app.kuaizhizao.customerPool.followStatusFollowed')
            : t('app.kuaizhizao.customerPool.followStatusPending');
        const cells = [
          row.code ?? '',
          row.name ?? '',
          row.country_code ?? '',
          row.contact_person ?? '',
          row.phone ?? '',
          row.email ?? '',
          row.customer_level_code ?? '',
          row.intent_material_name ?? '',
          row.campaign_name ?? '',
          row.required_capacity_text ?? '',
          followStatus,
          String(row.follow_up_count ?? 0),
          row.salesman_name ?? '',
          row.last_follow_up_at ? formatDateTime(row.last_follow_up_at, 'YYYY-MM-DD HH:mm:ss') : '',
        ];
        csvRows.push(cells.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','));
      }
      const blob = new Blob(['\ufeff' + csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
      downloadFile(
        blob,
        t('app.ind-foreign-trade.exportFileName', { date: formatDateTime(new Date(), 'YYYY-MM-DD') }),
      );
      message.success(t('common.exportSuccess', { count: exportData.length }));
    },
    [message, t],
  );

  return (
    <ListPageTemplate>
      <UniTable<CustomerPoolItem>
        actionRef={actionRef}
        rowKey="id"
        headerTitle={t('app.ind-foreign-trade.menu.exportCustomers')}
        columnPersistenceId="apps.ind-foreign-trade.pages.export-customers-v4"
        formRef={formRef}
        permissionResource="ind-foreign-trade:export-customer"
        columns={columns}
        enableRowSelection
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        showAdvancedSearch
        createButtonText={t('app.ind-foreign-trade.createExportCustomer')}
        showCreateButton
        onCreate={openCreate}
        onExport={perms.canExport ? handleExport : undefined}
        toolBarActionsBeforeCreate={
          perms.canImport
            ? [
                <Button key="import" type="primary" onClick={() => navigate('/apps/ind-foreign-trade/inquiry-import')}>
                  {t('app.ind-foreign-trade.import.button')}
                </Button>,
              ]
            : []
        }
        request={async (params, sort, _filter, search) => {
          const core = resolveCustomerPoolListParams(search, sort);
          let salesmanId = core.salesmanId as number | undefined;
          let inactive = core.inactive as boolean | undefined;
          const urlKey = `${searchParams.get('salesmanId') || ''}|${searchParams.get('inactive') || ''}`;
          if (urlKeyRef.current !== urlKey) {
            urlKeyRef.current = urlKey;
            const urlSalesman = Number(searchParams.get('salesmanId'));
            if (teamPerms.canRead && Number.isFinite(urlSalesman) && urlSalesman > 0) {
              salesmanId = urlSalesman;
              formRef.current?.setFieldsValue?.({ salesmanId: urlSalesman });
            }
            if (searchParams.get('inactive') === 'true') {
              inactive = true;
              formRef.current?.setFieldsValue?.({ inactive: 'true' });
            }
          }
          const listParams = {
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize || 20,
            keyword: core.keyword,
            salesmanId,
            followStatus: core.followStatus,
            inactive,
            customerLevelCode: core.customerLevelCode,
            intentMaterialName: core.intentMaterialName,
            countryCode: typeof search?.countryCode === 'string' ? search.countryCode.trim() : undefined,
            lastFollowUpFrom: core.last_follow_up_from,
            lastFollowUpTo: core.last_follow_up_to,
            createdStartDate: core.created_start_date,
            createdEndDate: core.created_end_date,
            order_by: core.order_by,
          };
          lastListParamsRef.current = {
            keyword: listParams.keyword,
            salesmanId: listParams.salesmanId,
            followStatus: listParams.followStatus,
            inactive: listParams.inactive,
            customerLevelCode: listParams.customerLevelCode,
            intentMaterialName: listParams.intentMaterialName,
            countryCode: listParams.countryCode,
            lastFollowUpFrom: listParams.lastFollowUpFrom,
            lastFollowUpTo: listParams.lastFollowUpTo,
            createdStartDate: listParams.createdStartDate,
            createdEndDate: listParams.createdEndDate,
            order_by: listParams.order_by,
          };
          const res = await foreignTradeApi.listExportCustomers(listParams);
          if (typeof res.inactive_alert_days === 'number' && res.inactive_alert_days >= 1) {
            setInactiveAlertDays(res.inactive_alert_days);
          }
          return { data: res.items || [], success: true, total: res.total || 0 };
        }}
      />
      <CustomerFormModal
        open={customerModalOpen}
        editUuid={editUuid}
        hostResource="ind-foreign-trade:export-customer"
        createDefaults={{ marketScope: 'export' }}
        persistApi={persistApi}
        onClose={() => {
          setCustomerModalOpen(false);
          setEditUuid(null);
        }}
        onSuccess={() => {
          actionRef.current?.reload();
        }}
      />
      <CustomerFollowUpFormModal
        open={followOpen}
        preset={followPreset}
        persistApi={foreignTradeFollowUpPersistApi}
        customerLoader={customerLoader}
        onClose={() => {
          setFollowOpen(false);
          setFollowPreset(null);
        }}
        onSuccess={() => actionRef.current?.reload()}
      />
    </ListPageTemplate>
  );
}
