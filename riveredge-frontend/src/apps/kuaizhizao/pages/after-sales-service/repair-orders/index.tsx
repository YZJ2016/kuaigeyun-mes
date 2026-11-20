import React, { useCallback, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button } from 'antd';
import { useTranslation } from 'react-i18next';
import { rowActionKind, rowActionLabelKeep } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { DetailDrawerActions, ListPageTemplate } from '../../../../../components/layout-templates';
import {
  CustomFieldsDetailSection,
  hasCustomFieldsDetailContent,
} from '../../../../../components/custom-fields';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { UniTable, type UniTableRequestMeta } from '../../../../../components/uni-table';
import {
  buildUniPushMenuItems,
  buildUniPushToolbarDisabledReason,
  UniPushToolbarButton,
} from '../../../../../components/uni-push';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import { formatDateTime } from '../../../../../utils/format';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import {
  AFTER_SALES_CUSTOMER_NAME_COLUMN_DEFAULTS,
  AFTER_SALES_REPAIR_STATUS_COLOR,
  renderAfterSalesStatusTag,
  renderAfterSalesTypeMarker,
} from '../shared/afterSalesListPresentation';
import { repairOrderApi, type RepairOrder } from '../../../services/after-sales-service';
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';
import RepairOrderFormModal from './RepairOrderFormModal';
import { RepairOrderDetailDrawer } from './components/RepairOrderDetailDrawer';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { getAntdModal } from '../../../../../utils/antdAppApis';

const RESOURCE = 'kuaizhizao:repair-order';
const CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_repair_orders';

function repairPushReason(
  reason: string | null | undefined,
  t: (key: string) => string,
): string {
  if (!reason) return '';
  const key = `app.kuaizhizao.afterSalesService.repairOrder.capability.${reason}`;
  const translated = t(key);
  return translated !== key ? translated : reason;
}

const RepairOrdersPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions(RESOURCE);
  const dispatchPerms = useResourcePermissions('kuaizhizao:service-dispatch');
  const settlementPerms = useResourcePermissions('kuaizhizao:service-settlement');
  const visitPerms = useResourcePermissions('kuaizhizao:customer-return-visit');
  const actionRef = useRef<ActionType>();
  const listRowsRef = useRef<RepairOrder[]>([]);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<RepairOrder | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<RepairOrder | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRetryIdRef = useRef<number | null>(null);
  const {
    customFields: listCustomFields,
    customFieldValues: detailCustomFieldValues,
    generateCustomFieldColumns,
    enrichRecordsWithCustomFields,
    loadFieldValuesForDetail,
    resetDetailFieldValues,
  } = useCustomFieldsForList<RepairOrder>({
    tableName: CUSTOM_FIELD_TABLE,
    hostResource: RESOURCE,
  });
  const customFieldColumns = generateCustomFieldColumns();
  const showDetailCustomFields = hasCustomFieldsDetailContent(
    listCustomFields,
    detailCustomFieldValues,
  );

  const loadDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    setDetailError(null);
    resetDetailFieldValues();
    try {
      setDetail(await repairOrderApi.get(id));
      await loadFieldValuesForDetail(id);
    } catch (error) {
      setDetail(null);
      setDetailError(getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.detail.loadFailed')));
    } finally {
      setDetailLoading(false);
    }
  }, [loadFieldValuesForDetail, resetDetailFieldValues, t]);

  const openDetail = (row: RepairOrder) => {
    detailRetryIdRef.current = row.id;
    setDetailOpen(true);
    setDetail(null);
    setDetailError(null);
    void loadDetail(row.id);
  };

  const openEdit = async (row: RepairOrder) => {
    setEditing(await repairOrderApi.get(row.id));
    setModalOpen(true);
  };

  const selectedRepairForToolbar = useMemo(() => {
    if (selectedRowKeys.length !== 1) return null;
    const id = Number(selectedRowKeys[0]);
    return listRowsRef.current.find((row) => row.id === id) ?? null;
  }, [selectedRowKeys]);

  const canClose = perms.canAction?.('close') ?? false;

  const refreshOpenDetail = useCallback(
    async (id: number) => {
      if (detail?.id !== id) return;
      setDetail(await repairOrderApi.get(id));
    },
    [detail?.id],
  );

  const pushDispatchDisabledReason = useCallback(
    (record: RepairOrder | null | undefined): string | undefined => {
      if (!record) return undefined;
      if (!dispatchPerms.canCreate) {
        return t('app.kuaizhizao.afterSalesService.repairOrder.push.dispatchNoPermission');
      }
      if (record.capabilities?.push_dispatch?.allowed !== true) {
        return (
          repairPushReason(record.capabilities?.push_dispatch?.reason, t) ||
          t('app.kuaizhizao.afterSalesService.repairOrder.pushFailed')
        );
      }
      return undefined;
    },
    [dispatchPerms.canCreate, t],
  );

  const pushSettlementDisabledReason = useCallback(
    (record: RepairOrder | null | undefined): string | undefined => {
      if (!record) return undefined;
      if (!settlementPerms.canCreate) {
        return t('app.kuaizhizao.afterSalesService.repairOrder.push.settlementNoPermission');
      }
      if (record.capabilities?.push_settlement?.allowed !== true) {
        return (
          repairPushReason(record.capabilities?.push_settlement?.reason, t) ||
          t('app.kuaizhizao.afterSalesService.repairOrder.pushFailed')
        );
      }
      return undefined;
    },
    [settlementPerms.canCreate, t],
  );

  const pushReturnVisitDisabledReason = useCallback(
    (record: RepairOrder | null | undefined): string | undefined => {
      if (!record) return undefined;
      if (!visitPerms.canCreate) {
        return t('app.kuaizhizao.afterSalesService.repairOrder.push.visitNoPermission');
      }
      if (record.capabilities?.push_return_visit?.allowed !== true) {
        return (
          repairPushReason(record.capabilities?.push_return_visit?.reason, t) ||
          t('app.kuaizhizao.afterSalesService.repairOrder.pushFailed')
        );
      }
      return undefined;
    },
    [t, visitPerms.canCreate],
  );

  const pushDispatch = useCallback(
    async (record: RepairOrder) => {
      try {
        const res = await repairOrderApi.pushToDispatch(record.id);
        messageApi.success(
          res.message ||
            t('app.kuaizhizao.afterSalesService.repairOrder.pushDispatchSuccess', {
              code: res.dispatch_code,
            }),
        );
        setSelectedRowKeys([]);
        actionRef.current?.reload();
        await refreshOpenDetail(record.id);
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.repairOrder.pushFailed')),
        );
        throw error;
      }
    },
    [messageApi, refreshOpenDetail, t],
  );

  const pushSettlement = useCallback(
    async (record: RepairOrder) => {
      try {
        const res = await repairOrderApi.pushToSettlement(record.id);
        messageApi.success(
          res.message ||
            t('app.kuaizhizao.afterSalesService.repairOrder.pushSettlementSuccess', {
              code: res.settlement_code,
            }),
        );
        setSelectedRowKeys([]);
        actionRef.current?.reload();
        await refreshOpenDetail(record.id);
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.repairOrder.pushFailed')),
        );
        throw error;
      }
    },
    [messageApi, refreshOpenDetail, t],
  );

  const pushReturnVisit = useCallback(
    async (record: RepairOrder) => {
      try {
        const res = await repairOrderApi.pushToReturnVisit(record.id);
        messageApi.success(
          res.message ||
            t('app.kuaizhizao.afterSalesService.repairOrder.pushVisitSuccess', {
              code: res.visit_code,
            }),
        );
        setSelectedRowKeys([]);
        actionRef.current?.reload();
        await refreshOpenDetail(record.id);
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.repairOrder.pushFailed')),
        );
        throw error;
      }
    },
    [messageApi, refreshOpenDetail, t],
  );

  const executeClose = useCallback(
    async (record: RepairOrder) => {
      await repairOrderApi.close(record.id);
      messageApi.success(t('app.kuaizhizao.afterSalesService.repairOrder.closeSuccess'));
      actionRef.current?.reload();
      await refreshOpenDetail(record.id);
    },
    [messageApi, refreshOpenDetail, t],
  );

  const toolbarPushMenuItems = useMemo(() => {
    const record = selectedRepairForToolbar;
    const dispatchBlocked = pushDispatchDisabledReason(record);
    const settlementBlocked = pushSettlementDisabledReason(record);
    const visitBlocked = pushReturnVisitDisabledReason(record);

    return buildUniPushMenuItems([
      {
        key: 'push-dispatch',
        label: t('app.kuaizhizao.afterSalesService.repairOrder.actionPushDispatch'),
        disabled: !!dispatchBlocked || !record,
        title: dispatchBlocked,
        onClick: () => {
          if (!record || dispatchBlocked) return;
          getAntdModal().confirm({
            title: t('app.kuaizhizao.afterSalesService.repairOrder.actionPushDispatch'),
            content: t('app.kuaizhizao.afterSalesService.repairOrder.pushDispatchConfirm', {
              code: record.order_code,
            }),
            onOk: () => pushDispatch(record),
          });
        },
        targetDocumentType: 'service_dispatch',
      },
      {
        key: 'push-settlement',
        label: t('app.kuaizhizao.afterSalesService.repairOrder.actionPushSettlement'),
        disabled: !!settlementBlocked || !record,
        title: settlementBlocked,
        onClick: () => {
          if (!record || settlementBlocked) return;
          getAntdModal().confirm({
            title: t('app.kuaizhizao.afterSalesService.repairOrder.actionPushSettlement'),
            content: t('app.kuaizhizao.afterSalesService.repairOrder.pushSettlementConfirm', {
              code: record.order_code,
            }),
            onOk: () => pushSettlement(record),
          });
        },
        targetDocumentType: 'service_settlement',
      },
      {
        key: 'push-return-visit',
        label: t('app.kuaizhizao.afterSalesService.repairOrder.actionPushReturnVisit'),
        disabled: !!visitBlocked || !record,
        title: visitBlocked,
        onClick: () => {
          if (!record || visitBlocked) return;
          getAntdModal().confirm({
            title: t('app.kuaizhizao.afterSalesService.repairOrder.actionPushReturnVisit'),
            content: t('app.kuaizhizao.afterSalesService.repairOrder.pushVisitConfirm', {
              code: record.order_code,
            }),
            onOk: () => pushReturnVisit(record),
          });
        },
        targetDocumentType: 'customer_return_visit',
      },
    ]);
  }, [
    pushDispatch,
    pushDispatchDisabledReason,
    pushReturnVisit,
    pushReturnVisitDisabledReason,
    pushSettlement,
    pushSettlementDisabledReason,
    selectedRepairForToolbar,
    t,
  ]);

  const toolbarPushDisabledReason = useMemo(
    () =>
      buildUniPushToolbarDisabledReason(t, {
        selectedCount: selectedRowKeys.length,
        hasSelectedRecord: !!selectedRepairForToolbar,
      }),
    [selectedRepairForToolbar, selectedRowKeys.length, t],
  );

  const columns: ProColumns<RepairOrder>[] = useMemo(
    () =>
      alignProColumns<RepairOrder>(
        [
          {
            title: t('app.kuaizhizao.afterSalesService.repairOrder.field.orderCode'),
            dataIndex: 'order_code',
            width: 180,
            minWidth: 180,
            uniTableKeepWidth: true,
            resizable: false,
            fixed: 'left',
            copyable: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.repairOrder.field.customerName'),
            dataIndex: 'customer_name',
            ...AFTER_SALES_CUSTOMER_NAME_COLUMN_DEFAULTS,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.repairOrder.field.repairMode'),
            dataIndex: 'repair_mode',
            ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
            render: (_, row) => renderAfterSalesTypeMarker(row.repair_mode),
          },
          {
            title: t('app.kuaizhizao.afterSalesService.repairOrder.field.faultDescription'),
            dataIndex: 'fault_description',
            minWidth: 160,
            uniTableRemainderFlex: true,
            uniTablePrimaryFlex: true,
            resizable: false,
            ellipsis: true,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.repairOrder.field.reportedAt'),
            dataIndex: 'reported_at',
            width: 148,
            minWidth: 148,
            uniTableKeepWidth: true,
            resizable: false,
            render: (_, row) => (row.reported_at ? formatDateTime(row.reported_at) : '-'),
          },
          ...customFieldColumns,
          {
            title: t('common.status'),
            key: 'lifecycle',
            dataIndex: 'status',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) =>
              renderAfterSalesStatusTag(row.status, AFTER_SALES_REPAIR_STATUS_COLOR),
          },
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => {
              const parts: React.ReactNode[] = [
                <Button
                  {...rowActionKind('read')}
                  key="read"
                  onClick={() => openDetail(row)}
                />,
              ];
              if (perms.canUpdate && row.status !== '已关闭') {
                parts.push(
                  <Button
                    {...rowActionKind('update')}
                    key="edit"
                    onClick={() => {
                      void openEdit(row);
                    }}
                  />,
                );
              }
              if (!pushDispatchDisabledReason(row)) {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="push-dispatch"
                    title={t('app.kuaizhizao.afterSalesService.repairOrder.actionPushDispatch')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.repairOrder.pushDispatchConfirm',
                      { code: row.order_code },
                    )}
                    onConfirm={() => pushDispatch(row)}
                  >
                    <Button
                      {...rowActionKind('execute')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('app.kuaizhizao.afterSalesService.repairOrder.actionPushDispatch')}
                    </Button>
                  </ActionConfirmPopconfirm>,
                );
              }
              if (!pushSettlementDisabledReason(row)) {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="push-settlement"
                    title={t('app.kuaizhizao.afterSalesService.repairOrder.actionPushSettlement')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.repairOrder.pushSettlementConfirm',
                      { code: row.order_code },
                    )}
                    onConfirm={() => pushSettlement(row)}
                  >
                    <Button
                      {...rowActionKind('execute')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('app.kuaizhizao.afterSalesService.repairOrder.actionPushSettlement')}
                    </Button>
                  </ActionConfirmPopconfirm>,
                );
              }
              if (!pushReturnVisitDisabledReason(row)) {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="push-return-visit"
                    title={t('app.kuaizhizao.afterSalesService.repairOrder.actionPushReturnVisit')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.repairOrder.pushVisitConfirm',
                      { code: row.order_code },
                    )}
                    onConfirm={() => pushReturnVisit(row)}
                  >
                    <Button
                      {...rowActionKind('execute')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('app.kuaizhizao.afterSalesService.repairOrder.actionPushReturnVisit')}
                    </Button>
                  </ActionConfirmPopconfirm>,
                );
              }
              if (canClose && row.capabilities?.close?.allowed !== false && row.status !== '已关闭') {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="close"
                    title={t('app.kuaizhizao.afterSalesService.repairOrder.closeConfirmTitle')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.repairOrder.closeConfirmContent',
                      { code: row.order_code },
                    )}
                    onConfirm={() => executeClose(row)}
                  >
                    <Button
                      {...rowActionKind('close')}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </ActionConfirmPopconfirm>,
                );
              }
              return parts;
            },
          },
        ],
        SALES_DOC_LIST_FIELD_RANK,
      ),
    [
      canClose,
      customFieldColumns,
      executeClose,
      perms.canUpdate,
      pushDispatch,
      pushDispatchDisabledReason,
      pushReturnVisit,
      pushReturnVisitDisabledReason,
      pushSettlement,
      pushSettlementDisabledReason,
      t,
    ],
  );

  return (
    <ListPageTemplate>
      <UniTable<RepairOrder>
        viewTypes={['table', 'help']}
        helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.afterSalesRepair)}
        actionRef={actionRef}
        columns={columns}
        columnPersistenceId="apps.kuaizhizao.pages.after-sales-service.repair-orders.v10-row-push"
        showAdvancedSearch
        skipFuzzyPinyinClientFilter
        rowKey="id"
        headerTitle={t('app.kuaizhizao.menu.after-sales-service.repair-orders')}
        request={async (params, _sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
          const res = await repairOrderApi.list({
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize,
            keyword: pickListSearchKeyword(searchFormValues),
            status: pickSearchString(searchFormValues, 'status'),
          });
          const data =
            meta?.purpose === 'prefetch'
              ? res.items
              : await enrichRecordsWithCustomFields(res.items);
          return { data, total: res.total, success: true };
        }}
        onTableDataChange={(rows) => {
          listRowsRef.current = rows;
        }}
        showCreateButton={perms.canCreate}
        createButtonText={t('app.kuaizhizao.afterSalesService.repairOrder.createTitle')}
        onCreate={() => {
          setEditing(null);
          setModalOpen(true);
        }}
        toolBarRender={() => [
          <UniPushToolbarButton
            key={`repair-push-${selectedRepairForToolbar?.id ?? 'none'}`}
            menuItems={toolbarPushMenuItems}
            disabled={selectedRowKeys.length !== 1 || !selectedRepairForToolbar}
            disabledReason={toolbarPushDisabledReason}
            sourceDocument={
              selectedRepairForToolbar?.id
                ? { type: 'repair_order', id: Number(selectedRepairForToolbar.id) }
                : null
            }
            pushTargets={{
              'push-dispatch': 'service_dispatch',
              'push-settlement': 'service_settlement',
              'push-return-visit': 'customer_return_visit',
            }}
          />,
        ]}
        enableRowSelection={
          perms.canDelete ||
          dispatchPerms.canCreate ||
          settlementPerms.canCreate ||
          visitPerms.canCreate
        }
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        showDeleteButton={perms.canDelete}
        deleteButtonText={t('common.delete')}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => repairOrderApi.delete(Number(key))));
          messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
          setSelectedRowKeys([]);
          actionRef.current?.reload();
        }}
      />

      <RepairOrderFormModal
        open={modalOpen}
        editing={editing}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSuccess={() => {
          actionRef.current?.reload();
        }}
      />

      <RepairOrderDetailDrawer
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setDetail(null);
          setDetailError(null);
          resetDetailFieldValues();
        }}
        record={detail}
        loading={detailLoading}
        error={detailError}
        onRetry={() => {
          const id = detailRetryIdRef.current;
          if (id != null) void loadDetail(id);
        }}
        supplementaryTitle={
          showDetailCustomFields
            ? t('app.master-data.customFields', { defaultValue: '自定义字段' })
            : undefined
        }
        supplementary={
          showDetailCustomFields ? (
            <CustomFieldsDetailSection
              customFields={listCustomFields}
              customFieldValues={detailCustomFieldValues}
            />
          ) : undefined
        }
        extra={
          <DetailDrawerActions
            items={[
              {
                key: 'edit',
                visible: Boolean(detail && perms.canUpdate && detail.status !== '已关闭'),
                render: (
                  <Button
                    onClick={() => {
                      if (!detail) return;
                      void openEdit(detail);
                    }}
                  >
                    {t('common.edit')}
                  </Button>
                ),
              },
              {
                key: 'push-dispatch',
                visible: Boolean(detail && !pushDispatchDisabledReason(detail)),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('app.kuaizhizao.afterSalesService.repairOrder.actionPushDispatch')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.repairOrder.pushDispatchConfirm',
                      { code: detail?.order_code },
                    )}
                    onConfirm={() => pushDispatch(detail!)}
                  >
                    <Button onClick={(e) => e.stopPropagation()}>
                      {t('app.kuaizhizao.afterSalesService.repairOrder.actionPushDispatch')}
                    </Button>
                  </ActionConfirmPopconfirm>
                ),
              },
              {
                key: 'push-settlement',
                visible: Boolean(detail && !pushSettlementDisabledReason(detail)),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('app.kuaizhizao.afterSalesService.repairOrder.actionPushSettlement')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.repairOrder.pushSettlementConfirm',
                      { code: detail?.order_code },
                    )}
                    onConfirm={() => pushSettlement(detail!)}
                  >
                    <Button onClick={(e) => e.stopPropagation()}>
                      {t('app.kuaizhizao.afterSalesService.repairOrder.actionPushSettlement')}
                    </Button>
                  </ActionConfirmPopconfirm>
                ),
              },
              {
                key: 'push-return-visit',
                visible: Boolean(detail && !pushReturnVisitDisabledReason(detail)),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('app.kuaizhizao.afterSalesService.repairOrder.actionPushReturnVisit')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.repairOrder.pushVisitConfirm',
                      { code: detail?.order_code },
                    )}
                    onConfirm={() => pushReturnVisit(detail!)}
                  >
                    <Button onClick={(e) => e.stopPropagation()}>
                      {t('app.kuaizhizao.afterSalesService.repairOrder.actionPushReturnVisit')}
                    </Button>
                  </ActionConfirmPopconfirm>
                ),
              },
              {
                key: 'close',
                visible: Boolean(
                  detail &&
                    canClose &&
                    detail.capabilities?.close?.allowed !== false &&
                    detail.status !== '已关闭',
                ),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('app.kuaizhizao.afterSalesService.repairOrder.closeConfirmTitle')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.repairOrder.closeConfirmContent',
                      { code: detail?.order_code },
                    )}
                    onConfirm={() => executeClose(detail!)}
                  >
                    <Button type="primary" onClick={(e) => e.stopPropagation()}>
                      {t('common.close')}
                    </Button>
                  </ActionConfirmPopconfirm>
                ),
              },
            ]}
          />
        }
      />
    </ListPageTemplate>
  );
};

export default RepairOrdersPage;
