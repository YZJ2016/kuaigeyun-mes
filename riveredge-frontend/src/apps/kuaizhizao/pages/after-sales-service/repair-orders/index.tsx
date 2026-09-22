import React, { useCallback, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button } from 'antd';
import { useTranslation } from 'react-i18next';
import { rowActionKind } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { DetailDrawerActions, ListPageTemplate } from '../../../../../components/layout-templates';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { UniTable } from '../../../../../components/uni-table';
import {
  buildUniPushMenuItems,
  buildUniPushToolbarDisabledReason,
  UniPushToolbarButton,
} from '../../../../../components/uni-push';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
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
import RepairOrderFormModal from './RepairOrderFormModal';
import { RepairOrderDetailDrawer } from './components/RepairOrderDetailDrawer';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { getAntdModal } from '../../../../../utils/antdAppApis';

const RESOURCE = 'kuaizhizao:repair-order';

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

  const loadDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      setDetail(await repairOrderApi.get(id));
    } catch (error) {
      setDetail(null);
      setDetailError(getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.detail.loadFailed')));
    } finally {
      setDetailLoading(false);
    }
  }, [t]);

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

  const executeconfirmDelete = async (row: RepairOrder) => {
    await repairOrderApi.delete(row.id);
    messageApi.success(t('common.deleteSuccess'));
    if (detail?.id === row.id) {
      setDetailOpen(false);
      setDetail(null);
    }
    actionRef.current?.reload();
  };

  const selectedRepairForToolbar = useMemo(() => {
    if (selectedRowKeys.length !== 1) return null;
    const id = Number(selectedRowKeys[0]);
    return listRowsRef.current.find((row) => row.id === id) ?? null;
  }, [selectedRowKeys]);

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
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.repairOrder.pushFailed')),
        );
      }
    },
    [messageApi, t],
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
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.repairOrder.pushFailed')),
        );
      }
    },
    [messageApi, t],
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
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.repairOrder.pushFailed')),
        );
      }
    },
    [messageApi, t],
  );

  const confirmPush = useCallback(
    (title: string, onOk: () => void) => {
      getAntdModal().confirm({
        title,
        onOk,
      });
    },
    [],
  );

  const toolbarPushMenuItems = useMemo(() => {
    const record = selectedRepairForToolbar;
    const dispatchBlocked =
      !dispatchPerms.canCreate
        ? t('app.kuaizhizao.afterSalesService.repairOrder.push.dispatchNoPermission')
        : record && record.capabilities?.push_dispatch?.allowed !== true
          ? repairPushReason(record.capabilities?.push_dispatch?.reason, t)
          : undefined;
    const settlementBlocked =
      !settlementPerms.canCreate
        ? t('app.kuaizhizao.afterSalesService.repairOrder.push.settlementNoPermission')
        : record && record.capabilities?.push_settlement?.allowed !== true
          ? repairPushReason(record.capabilities?.push_settlement?.reason, t)
          : undefined;
    const visitBlocked =
      !visitPerms.canCreate
        ? t('app.kuaizhizao.afterSalesService.repairOrder.push.visitNoPermission')
        : record && record.capabilities?.push_return_visit?.allowed !== true
          ? repairPushReason(record.capabilities?.push_return_visit?.reason, t)
          : undefined;

    return buildUniPushMenuItems([
      {
        key: 'push-dispatch',
        label: t('app.kuaizhizao.afterSalesService.repairOrder.actionPushDispatch'),
        disabled: !!dispatchBlocked || !record,
        title: dispatchBlocked,
        onClick: () => {
          if (!record || dispatchBlocked) return;
          confirmPush(t('app.kuaizhizao.afterSalesService.repairOrder.actionPushDispatch'), () => {
            void pushDispatch(record);
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
          confirmPush(t('app.kuaizhizao.afterSalesService.repairOrder.actionPushSettlement'), () => {
            void pushSettlement(record);
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
          confirmPush(t('app.kuaizhizao.afterSalesService.repairOrder.actionPushReturnVisit'), () => {
            void pushReturnVisit(record);
          });
        },
        targetDocumentType: 'customer_return_visit',
      },
    ]);
  }, [
    confirmPush,
    dispatchPerms.canCreate,
    pushDispatch,
    pushReturnVisit,
    pushSettlement,
    selectedRepairForToolbar,
    settlementPerms.canCreate,
    t,
    visitPerms.canCreate,
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
            valueType: 'option',
            render: (_, row) => [
              rowActionKind('detail', {
                key: 'detail',
                onClick: () => openDetail(row),
              }),
              perms.canUpdate && row.status !== '已关闭'
                ? rowActionKind('edit', {
                    key: 'edit',
                    onClick: () => {
                      void openEdit(row);
                    },
                  })
                : null,
              perms.canDelete && row.status === '待派工' ? (
                <ActionConfirmPopconfirm
                  key="delete"
                  title={t('common.confirmDelete')}
                  onConfirm={() => executeconfirmDelete(row)}
                >
                  {rowActionKind('delete', { key: 'delete-trigger' })}
                </ActionConfirmPopconfirm>
              ) : null,
            ],
          },
        ],
        SALES_DOC_LIST_FIELD_RANK,
      ),
    [perms.canDelete, perms.canUpdate, t],
  );

  return (
    <ListPageTemplate>
      <UniTable<RepairOrder>
        viewTypes={['table', 'help']}
        helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.afterSalesRepair)}
        actionRef={actionRef}
        columns={columns}
        columnPersistenceId="apps.kuaizhizao.pages.after-sales-service.repair-orders.v7"
        rowKey="id"
        headerTitle={t('app.kuaizhizao.menu.after-sales-service.repair-orders')}
        request={async (params) => {
          const res = await repairOrderApi.list({
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize,
            keyword: params.keyword as string | undefined,
            status: params.status as string | undefined,
          });
          return { data: res.items, total: res.total, success: true };
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
        onSubmit={async (payload) => {
          if (editing) {
            await repairOrderApi.update(editing.id, payload);
            messageApi.success(t('common.saveSuccess'));
          } else {
            await repairOrderApi.create(payload);
            messageApi.success(t('common.createSuccess'));
          }
          actionRef.current?.reload();
        }}
      />

      <RepairOrderDetailDrawer
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setDetail(null);
          setDetailError(null);
        }}
        record={detail}
        loading={detailLoading}
        error={detailError}
        onRetry={() => {
          const id = detailRetryIdRef.current;
          if (id != null) void loadDetail(id);
        }}
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
                key: 'close',
                visible: Boolean(detail && perms.canAction?.('close') && detail.status !== '已关闭'),
                render: (
                  <Button
                    type="primary"
                    onClick={async () => {
                      if (!detail) return;
                      await repairOrderApi.close(detail.id);
                      setDetail(await repairOrderApi.get(detail.id));
                      actionRef.current?.reload();
                      messageApi.success(t('app.kuaizhizao.afterSalesService.repairOrder.closeSuccess'));
                    }}
                  >
                    {t('common.close')}
                  </Button>
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
