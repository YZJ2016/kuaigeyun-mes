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
import { SourceDocumentCode } from '../../../../../components/linked-document-code/SourceDocumentCode';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import { formatDateTime } from '../../../../../utils/format';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import {
  AFTER_SALES_CUSTOMER_NAME_COLUMN_DEFAULTS,
  AFTER_SALES_DISPATCH_STATUS_COLOR,
  renderAfterSalesStatusTag,
} from '../shared/afterSalesListPresentation';
import { serviceDispatchApi, type ServiceDispatchOrder } from '../../../services/after-sales-service';
import DispatchOrderFormModal from './DispatchOrderFormModal';
import { DispatchOrderDetailDrawer } from './components/DispatchOrderDetailDrawer';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';

const RESOURCE = 'kuaizhizao:service-dispatch';
const CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_service_dispatch_orders';

const DispatchOrdersPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions(RESOURCE);
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ServiceDispatchOrder | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<ServiceDispatchOrder | null>(null);
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
  } = useCustomFieldsForList<ServiceDispatchOrder>({
    tableName: CUSTOM_FIELD_TABLE,
    hostResource: RESOURCE,
  });
  const customFieldColumns = generateCustomFieldColumns();
  const showDetailCustomFields = hasCustomFieldsDetailContent(
    listCustomFields,
    detailCustomFieldValues,
  );

  const canAssign = perms.canAction?.('assign') ?? false;
  const canExecute = perms.canAction?.('execute') ?? false;
  const canClose = perms.canAction?.('close') ?? false;

  const loadDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    setDetailError(null);
    resetDetailFieldValues();
    try {
      setDetail(await serviceDispatchApi.get(id));
      await loadFieldValuesForDetail(id);
    } catch (error) {
      setDetail(null);
      setDetailError(getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.detail.loadFailed')));
    } finally {
      setDetailLoading(false);
    }
  }, [loadFieldValuesForDetail, resetDetailFieldValues, t]);

  const openDetail = (row: ServiceDispatchOrder) => {
    detailRetryIdRef.current = row.id;
    setDetailOpen(true);
    setDetail(null);
    setDetailError(null);
    void loadDetail(row.id);
  };

  const openEdit = async (row: ServiceDispatchOrder) => {
    setEditing(await serviceDispatchApi.get(row.id));
    setModalOpen(true);
  };

  const refreshOpenDetail = useCallback(
    async (id: number) => {
      if (detail?.id !== id) return;
      setDetail(await serviceDispatchApi.get(id));
    },
    [detail?.id],
  );

  const afterAction = useCallback(
    async (row: ServiceDispatchOrder, successKey: string) => {
      messageApi.success(t(successKey));
      actionRef.current?.reload();
      await refreshOpenDetail(row.id);
    },
    [messageApi, refreshOpenDetail, t],
  );

  const canAssignRow = useCallback(
    (row: ServiceDispatchOrder) =>
      canAssign && row.status === '待接单' && Number(row.engineer_id) > 0,
    [canAssign],
  );

  const canAcceptRow = useCallback(
    (row: ServiceDispatchOrder) => canAssign && row.status === '待接单',
    [canAssign],
  );

  const canCheckinRow = useCallback(
    (row: ServiceDispatchOrder) => canExecute && row.status === '已接单',
    [canExecute],
  );

  const canCompleteRow = useCallback(
    (row: ServiceDispatchOrder) => canExecute && row.status === '到场',
    [canExecute],
  );

  const canCancelRow = useCallback(
    (row: ServiceDispatchOrder) =>
      canClose && row.status !== '完工' && row.status !== '已取消',
    [canClose],
  );

  const executeAssign = useCallback(
    async (row: ServiceDispatchOrder) => {
      const engineerId = Number(row.engineer_id);
      if (!Number.isFinite(engineerId) || engineerId <= 0) {
        messageApi.warning(t('app.kuaizhizao.afterSalesService.dispatchOrder.assignNeedEngineer'));
        void openEdit(row);
        return;
      }
      try {
        await serviceDispatchApi.assign(row.id, {
          engineer_id: engineerId,
          engineer_name: row.engineer_name ?? undefined,
          planned_start_at: row.planned_start_at,
          planned_end_at: row.planned_end_at,
        });
        await afterAction(row, 'app.kuaizhizao.afterSalesService.dispatchOrder.assignSuccess');
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.dispatchOrder.actionFailed')),
        );
        throw error;
      }
    },
    [afterAction, messageApi, t],
  );

  const executeAccept = useCallback(
    async (row: ServiceDispatchOrder) => {
      try {
        await serviceDispatchApi.accept(row.id);
        await afterAction(row, 'app.kuaizhizao.afterSalesService.dispatchOrder.acceptSuccess');
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.dispatchOrder.actionFailed')),
        );
        throw error;
      }
    },
    [afterAction, messageApi, t],
  );

  const executeCheckin = useCallback(
    async (row: ServiceDispatchOrder) => {
      try {
        await serviceDispatchApi.checkin(row.id);
        await afterAction(row, 'app.kuaizhizao.afterSalesService.dispatchOrder.checkinSuccess');
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.dispatchOrder.actionFailed')),
        );
        throw error;
      }
    },
    [afterAction, messageApi, t],
  );

  const executeComplete = useCallback(
    async (row: ServiceDispatchOrder) => {
      try {
        await serviceDispatchApi.complete(row.id);
        await afterAction(row, 'app.kuaizhizao.afterSalesService.dispatchOrder.completeSuccess');
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.dispatchOrder.actionFailed')),
        );
        throw error;
      }
    },
    [afterAction, messageApi, t],
  );

  const executeCancel = useCallback(
    async (row: ServiceDispatchOrder) => {
      try {
        await serviceDispatchApi.cancel(row.id);
        await afterAction(row, 'app.kuaizhizao.afterSalesService.dispatchOrder.cancelSuccess');
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.dispatchOrder.actionFailed')),
        );
        throw error;
      }
    },
    [afterAction, messageApi, t],
  );

  const columns: ProColumns<ServiceDispatchOrder>[] = useMemo(
    () =>
      alignProColumns<ServiceDispatchOrder>(
        [
          {
            title: t('app.kuaizhizao.afterSalesService.dispatchOrder.field.dispatchCode'),
            dataIndex: 'dispatch_code',
            width: 188,
            minWidth: 188,
            uniTableKeepWidth: true,
            resizable: false,
            fixed: 'left',
            copyable: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.dispatchOrder.field.customerName'),
            dataIndex: 'customer_name',
            ...AFTER_SALES_CUSTOMER_NAME_COLUMN_DEFAULTS,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.dispatchOrder.field.sourceCode'),
            dataIndex: 'source_code',
            width: 188,
            minWidth: 188,
            uniTableKeepWidth: true,
            resizable: false,
            render: (_, row) => (
              <SourceDocumentCode
                sourceType={row.source_type}
                sourceId={row.source_id}
                sourceCode={row.source_code}
              />
            ),
          },
          {
            title: t('app.kuaizhizao.afterSalesService.dispatchOrder.field.engineerName'),
            dataIndex: 'engineer_name',
            width: 100,
            minWidth: 100,
            uniTableKeepWidth: true,
            resizable: false,
            render: (_, row) => row.engineer_name || '-',
          },
          {
            title: t('app.kuaizhizao.afterSalesService.dispatchOrder.field.siteAddress'),
            dataIndex: 'site_address',
            minWidth: 160,
            uniTableRemainderFlex: true,
            uniTablePrimaryFlex: true,
            resizable: false,
            ellipsis: true,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.dispatchOrder.field.plannedStartAt'),
            dataIndex: 'planned_start_at',
            width: 148,
            minWidth: 148,
            uniTableKeepWidth: true,
            resizable: false,
            render: (_, row) => (row.planned_start_at ? formatDateTime(row.planned_start_at) : '-'),
          },
          {
            title: t('common.status'),
            key: 'lifecycle',
            dataIndex: 'status',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) =>
              renderAfterSalesStatusTag(row.status, AFTER_SALES_DISPATCH_STATUS_COLOR),
          },
          ...customFieldColumns,
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => {
              const parts: React.ReactNode[] = [
                <Button {...rowActionKind('read')} key="read" onClick={() => openDetail(row)} />,
              ];
              if (perms.canUpdate && row.status !== '已取消' && row.status !== '完工') {
                parts.push(
                  <Button
                    {...rowActionKind('update')}
                    key="edit"
                    onClick={() => void openEdit(row)}
                  />,
                );
              }
              if (canAssignRow(row)) {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="assign"
                    title={t('app.kuaizhizao.afterSalesService.dispatchOrder.actionAssign')}
                    description={t('app.kuaizhizao.afterSalesService.dispatchOrder.assignConfirm', {
                      code: row.dispatch_code,
                      engineer: row.engineer_name || '—',
                    })}
                    onConfirm={() => executeAssign(row)}
                  >
                    <Button
                      {...rowActionKind('assign')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('app.kuaizhizao.afterSalesService.dispatchOrder.actionAssign')}
                    </Button>
                  </ActionConfirmPopconfirm>,
                );
              } else if (canAcceptRow(row)) {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="accept"
                    title={t('app.kuaizhizao.afterSalesService.dispatchOrder.actionAccept')}
                    description={t('app.kuaizhizao.afterSalesService.dispatchOrder.acceptConfirm', {
                      code: row.dispatch_code,
                    })}
                    onConfirm={() => executeAccept(row)}
                  >
                    <Button
                      {...rowActionKind('assign')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('app.kuaizhizao.afterSalesService.dispatchOrder.actionAccept')}
                    </Button>
                  </ActionConfirmPopconfirm>,
                );
              }
              if (canCheckinRow(row)) {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="checkin"
                    title={t('app.kuaizhizao.afterSalesService.dispatchOrder.actionCheckin')}
                    description={t('app.kuaizhizao.afterSalesService.dispatchOrder.checkinConfirm', {
                      code: row.dispatch_code,
                    })}
                    onConfirm={() => executeCheckin(row)}
                  >
                    <Button
                      {...rowActionKind('execute')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('app.kuaizhizao.afterSalesService.dispatchOrder.actionCheckin')}
                    </Button>
                  </ActionConfirmPopconfirm>,
                );
              }
              if (canCompleteRow(row)) {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="complete"
                    title={t('app.kuaizhizao.afterSalesService.dispatchOrder.actionComplete')}
                    description={t('app.kuaizhizao.afterSalesService.dispatchOrder.completeConfirm', {
                      code: row.dispatch_code,
                    })}
                    onConfirm={() => executeComplete(row)}
                  >
                    <Button
                      {...rowActionKind('complete')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('app.kuaizhizao.afterSalesService.dispatchOrder.actionComplete')}
                    </Button>
                  </ActionConfirmPopconfirm>,
                );
              }
              if (canCancelRow(row)) {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="cancel"
                    title={t('app.kuaizhizao.afterSalesService.dispatchOrder.actionCancel')}
                    description={t('app.kuaizhizao.afterSalesService.dispatchOrder.cancelConfirm', {
                      code: row.dispatch_code,
                    })}
                    onConfirm={() => executeCancel(row)}
                  >
                    <Button
                      {...rowActionKind('close')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('app.kuaizhizao.afterSalesService.dispatchOrder.actionCancel')}
                    </Button>
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
      canAcceptRow,
      canAssignRow,
      canCancelRow,
      canCheckinRow,
      canCompleteRow,
      customFieldColumns,
      executeAccept,
      executeAssign,
      executeCancel,
      executeCheckin,
      executeComplete,
      perms.canUpdate,
      t,
    ],
  );

  return (
    <ListPageTemplate>
      <UniTable<ServiceDispatchOrder>
        viewTypes={['table', 'help']}
        helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.afterSalesDispatch)}
        actionRef={actionRef}
        columns={columns}
        columnPersistenceId="apps.kuaizhizao.pages.after-sales-service.dispatch-orders.v9-row-flow"
        showAdvancedSearch
        skipFuzzyPinyinClientFilter
        rowKey="id"
        headerTitle={t('app.kuaizhizao.menu.after-sales-service.dispatch-orders')}
        request={async (params, _sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
          const res = await serviceDispatchApi.list({
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
        showCreateButton={perms.canCreate}
        createButtonText={t('app.kuaizhizao.afterSalesService.dispatchOrder.createTitle')}
        onCreate={() => {
          setEditing(null);
          setModalOpen(true);
        }}
        enableRowSelection={perms.canDelete}
        showDeleteButton={perms.canDelete}
        deleteButtonText={t('common.delete')}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => serviceDispatchApi.delete(Number(key))));
          messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
          actionRef.current?.reload();
        }}
      />

      <DispatchOrderFormModal
        open={modalOpen}
        editing={editing}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSuccess={() => {
          actionRef.current?.reload();
          if (editing && detail?.id === editing.id) {
            void loadDetail(editing.id);
          }
        }}
      />

      <DispatchOrderDetailDrawer
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
                visible: Boolean(
                  detail &&
                    perms.canUpdate &&
                    detail.status !== '已取消' &&
                    detail.status !== '完工',
                ),
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
                key: 'assign',
                visible: Boolean(detail && canAssignRow(detail)),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('app.kuaizhizao.afterSalesService.dispatchOrder.actionAssign')}
                    description={t('app.kuaizhizao.afterSalesService.dispatchOrder.assignConfirm', {
                      code: detail?.dispatch_code,
                      engineer: detail?.engineer_name || '—',
                    })}
                    onConfirm={() => executeAssign(detail!)}
                  >
                    <Button onClick={(e) => e.stopPropagation()}>
                      {t('app.kuaizhizao.afterSalesService.dispatchOrder.actionAssign')}
                    </Button>
                  </ActionConfirmPopconfirm>
                ),
              },
              {
                key: 'accept',
                visible: Boolean(detail && !canAssignRow(detail) && canAcceptRow(detail)),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('app.kuaizhizao.afterSalesService.dispatchOrder.actionAccept')}
                    description={t('app.kuaizhizao.afterSalesService.dispatchOrder.acceptConfirm', {
                      code: detail?.dispatch_code,
                    })}
                    onConfirm={() => executeAccept(detail!)}
                  >
                    <Button onClick={(e) => e.stopPropagation()}>
                      {t('app.kuaizhizao.afterSalesService.dispatchOrder.actionAccept')}
                    </Button>
                  </ActionConfirmPopconfirm>
                ),
              },
              {
                key: 'checkin',
                visible: Boolean(detail && canCheckinRow(detail)),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('app.kuaizhizao.afterSalesService.dispatchOrder.actionCheckin')}
                    description={t('app.kuaizhizao.afterSalesService.dispatchOrder.checkinConfirm', {
                      code: detail?.dispatch_code,
                    })}
                    onConfirm={() => executeCheckin(detail!)}
                  >
                    <Button onClick={(e) => e.stopPropagation()}>
                      {t('app.kuaizhizao.afterSalesService.dispatchOrder.actionCheckin')}
                    </Button>
                  </ActionConfirmPopconfirm>
                ),
              },
              {
                key: 'complete',
                visible: Boolean(detail && canCompleteRow(detail)),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('app.kuaizhizao.afterSalesService.dispatchOrder.actionComplete')}
                    description={t('app.kuaizhizao.afterSalesService.dispatchOrder.completeConfirm', {
                      code: detail?.dispatch_code,
                    })}
                    onConfirm={() => executeComplete(detail!)}
                  >
                    <Button type="primary" onClick={(e) => e.stopPropagation()}>
                      {t('app.kuaizhizao.afterSalesService.dispatchOrder.actionComplete')}
                    </Button>
                  </ActionConfirmPopconfirm>
                ),
              },
              {
                key: 'cancel',
                visible: Boolean(detail && canCancelRow(detail)),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('app.kuaizhizao.afterSalesService.dispatchOrder.actionCancel')}
                    description={t('app.kuaizhizao.afterSalesService.dispatchOrder.cancelConfirm', {
                      code: detail?.dispatch_code,
                    })}
                    onConfirm={() => executeCancel(detail!)}
                  >
                    <Button danger onClick={(e) => e.stopPropagation()}>
                      {t('app.kuaizhizao.afterSalesService.dispatchOrder.actionCancel')}
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

export default DispatchOrdersPage;
