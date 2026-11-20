import React, { useCallback, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button, Input, Modal } from 'antd';
import { CheckOutlined, CloseOutlined, SendOutlined } from '@ant-design/icons';
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
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import { hasReviewPermission } from '../../../../../utils/permissionContract';
import { serviceSettlementApi, type ServiceSettlement } from '../../../services/after-sales-service';
import { ServiceSettlementDetailDrawer } from './components/ServiceSettlementDetailDrawer';
import ServiceSettlementFormModal from './ServiceSettlementFormModal';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../../sales-management/shared/documentLineMaterialsPreview';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';
import {
  AFTER_SALES_CUSTOMER_NAME_COLUMN_DEFAULTS,
  AFTER_SALES_REVIEW_STATUS_COLOR,
  renderAfterSalesStatusTag,
} from '../shared/afterSalesListPresentation';

const RESOURCE = 'kuaizhizao:service-settlement';
const CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_service_settlements';

type DetailActionKey = 'submit' | 'audit' | 'reject';

const canEditStatus = (status?: string) => status === '草稿';
const canSubmitStatus = (status?: string) => status === '草稿';
const canReviewStatus = (status?: string) => status === '待审核';

const ServiceSettlementsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions(RESOURCE);
  const currentUser = useCurrentUser();
  const canReview = hasReviewPermission(currentUser ?? undefined, RESOURCE);
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ServiceSettlement | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<ServiceSettlement | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRetryIdRef = useRef<number | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectTargetId, setRejectTargetId] = useState<number | null>(null);
  const [rejectRemarks, setRejectRemarks] = useState('');
  const [detailActionLoading, setDetailActionLoading] = useState<DetailActionKey | null>(null);
  const {
    customFields: listCustomFields,
    customFieldValues: detailCustomFieldValues,
    generateCustomFieldColumns,
    enrichRecordsWithCustomFields,
    loadFieldValuesForDetail,
    resetDetailFieldValues,
  } = useCustomFieldsForList<ServiceSettlement>({
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
      setDetail(await serviceSettlementApi.get(id));
      await loadFieldValuesForDetail(id);
    } catch (error) {
      setDetail(null);
      setDetailError(getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.detail.loadFailed')));
    } finally {
      setDetailLoading(false);
    }
  }, [loadFieldValuesForDetail, resetDetailFieldValues, t]);

  const openDetail = (row: ServiceSettlement) => {
    detailRetryIdRef.current = row.id;
    setDetailOpen(true);
    setDetail(null);
    setDetailError(null);
    void loadDetail(row.id);
  };

  const refreshDetail = useCallback(async (id: number) => {
    setDetail(await serviceSettlementApi.get(id));
    actionRef.current?.reload();
  }, []);

  const openEdit = async (row: ServiceSettlement) => {
    setEditing(await serviceSettlementApi.get(row.id));
    setModalOpen(true);
  };

  const openReject = useCallback((id: number) => {
    setRejectTargetId(id);
    setRejectRemarks('');
    setRejectOpen(true);
  }, []);

  const executeSubmit = useCallback(
    async (id: number) => {
      setDetailActionLoading('submit');
      try {
        await serviceSettlementApi.submit(id);
        await refreshDetail(id);
        messageApi.success(t('app.kuaizhizao.afterSalesService.serviceSettlement.submitSuccess'));
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.serviceSettlement.actionFailed')),
        );
        throw error;
      } finally {
        setDetailActionLoading(null);
      }
    },
    [messageApi, refreshDetail, t],
  );

  const executeAudit = useCallback(
    async (id: number) => {
      setDetailActionLoading('audit');
      try {
        await serviceSettlementApi.audit(id);
        await refreshDetail(id);
        messageApi.success(t('app.kuaizhizao.afterSalesService.serviceSettlement.auditSuccess'));
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.serviceSettlement.actionFailed')),
        );
        throw error;
      } finally {
        setDetailActionLoading(null);
      }
    },
    [messageApi, refreshDetail, t],
  );

  const executeReject = useCallback(
    async (id: number, reviewRemarks: string) => {
      const remarks = reviewRemarks.trim();
      if (!remarks) {
        messageApi.error(t('app.kuaizhizao.afterSalesService.serviceSettlement.rejectRemarksRequired'));
        throw new Error('reject_remarks_required');
      }
      setDetailActionLoading('reject');
      try {
        await serviceSettlementApi.reject(id, { review_remarks: remarks });
        setRejectOpen(false);
        setRejectTargetId(null);
        setRejectRemarks('');
        await refreshDetail(id);
        messageApi.success(t('app.kuaizhizao.afterSalesService.serviceSettlement.rejectSuccess'));
      } catch (error) {
        if (error instanceof Error && error.message === 'reject_remarks_required') {
          throw error;
        }
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.serviceSettlement.actionFailed')),
        );
        throw error;
      } finally {
        setDetailActionLoading(null);
      }
    },
    [messageApi, refreshDetail, t],
  );

  const columns: ProColumns<ServiceSettlement>[] = useMemo(
    () =>
      alignProColumns<ServiceSettlement>(
        [
          {
            title: t('app.kuaizhizao.afterSalesService.serviceSettlement.field.settlementCode'),
            dataIndex: 'settlement_code',
            width: 188,
            minWidth: 188,
            uniTableKeepWidth: true,
            resizable: false,
            fixed: 'left',
            copyable: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.serviceSettlement.field.customerName'),
            dataIndex: 'customer_name',
            ...AFTER_SALES_CUSTOMER_NAME_COLUMN_DEFAULTS,
          },
          {
            // 明细预览吃余量（备件申领同款）；客户名勿当 RemainderFlex
            title: t('app.kuaizhizao.common.colLineMaterials'),
            ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
            render: (_, row) =>
              renderDocumentLineMaterialsPreview(
                (row.items || []).map((it) => ({ material_name: it.source_code })),
                t,
              ),
          },
          {
            title: t('app.kuaizhizao.afterSalesService.serviceSettlement.field.totalAmount'),
            dataIndex: 'total_amount',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            align: 'right',
            render: (_, row) => (row.total_amount != null ? row.total_amount : '-'),
          },
          {
            title: t('common.status'),
            key: 'lifecycle',
            dataIndex: 'status',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) =>
              renderAfterSalesStatusTag(row.status, AFTER_SALES_REVIEW_STATUS_COLOR),
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
              if (perms.canUpdate && canEditStatus(row.status)) {
                parts.push(
                  <Button
                    {...rowActionKind('update')}
                    key="edit"
                    onClick={() => void openEdit(row)}
                  />,
                );
              }
              if (perms.canAction?.('submit') && canSubmitStatus(row.status)) {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="submit"
                    title={t('components.uniAction.submit')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.serviceSettlement.submitConfirm',
                      { code: row.settlement_code },
                    )}
                    onConfirm={() => executeSubmit(row.id)}
                  >
                    <Button
                      {...rowActionKind('submit')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('components.uniAction.submit')}
                    </Button>
                  </ActionConfirmPopconfirm>,
                );
              }
              if (canReview && canReviewStatus(row.status)) {
                parts.push(
                  <ActionConfirmPopconfirm
                    key="audit"
                    title={t('components.uniAction.audit')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.serviceSettlement.auditConfirm',
                      { code: row.settlement_code },
                    )}
                    onConfirm={() => executeAudit(row.id)}
                  >
                    <Button
                      {...rowActionKind('audit')}
                      {...rowActionLabelKeep()}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('components.uniAction.audit')}
                    </Button>
                  </ActionConfirmPopconfirm>,
                  <Button
                    key="reject"
                    {...rowActionKind('reject')}
                    {...rowActionLabelKeep()}
                    onClick={(e) => {
                      e.stopPropagation();
                      openReject(row.id);
                    }}
                  >
                    {t('components.uniAction.reject')}
                  </Button>,
                );
              }
              return parts;
            },
          },
        ],
        SALES_DOC_LIST_FIELD_RANK,
      ),
    [canReview, customFieldColumns, executeAudit, executeSubmit, openReject, perms, t],
  );

  return (
    <ListPageTemplate>
      <UniTable<ServiceSettlement>
        viewTypes={['table', 'help']}
        helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.afterSalesSettlement)}
        actionRef={actionRef}
        columns={columns}
        columnPersistenceId="apps.kuaizhizao.pages.after-sales-service.service-settlements.v9-row-review"
        showAdvancedSearch
        skipFuzzyPinyinClientFilter
        rowKey="id"
        headerTitle={t('app.kuaizhizao.menu.after-sales-service.service-settlements')}
        request={async (params, _sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
          const res = await serviceSettlementApi.list({
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
        createButtonText={t('app.kuaizhizao.afterSalesService.serviceSettlement.createTitle')}
        onCreate={() => {
          setEditing(null);
          setModalOpen(true);
        }}
        enableRowSelection={perms.canDelete}
        showDeleteButton={perms.canDelete}
        deleteButtonText={t('common.delete')}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => serviceSettlementApi.delete(Number(key))));
          messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
          actionRef.current?.reload();
        }}
      />

      <ServiceSettlementFormModal
        open={modalOpen}
        editing={editing}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        onSuccess={() => {
          actionRef.current?.reload();
          if (editing && detail?.id === editing.id) {
            void refreshDetail(editing.id);
          }
        }}
      />

      <ServiceSettlementDetailDrawer
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
                visible: Boolean(detail && perms.canUpdate && canEditStatus(detail.status)),
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
                key: 'submit',
                visible: Boolean(
                  detail && perms.canAction?.('submit') && canSubmitStatus(detail.status),
                ),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('components.uniAction.submit')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.serviceSettlement.submitConfirm',
                      { code: detail?.settlement_code },
                    )}
                    onConfirm={() => executeSubmit(detail!.id)}
                  >
                    <Button
                      icon={<SendOutlined />}
                      loading={detailActionLoading === 'submit'}
                      disabled={detailActionLoading != null}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('components.uniAction.submit')}
                    </Button>
                  </ActionConfirmPopconfirm>
                ),
              },
              {
                key: 'audit',
                visible: Boolean(detail && canReviewStatus(detail.status) && canReview),
                render: (
                  <ActionConfirmPopconfirm
                    title={t('components.uniAction.audit')}
                    description={t(
                      'app.kuaizhizao.afterSalesService.serviceSettlement.auditConfirm',
                      { code: detail?.settlement_code },
                    )}
                    onConfirm={() => executeAudit(detail!.id)}
                  >
                    <Button
                      type="primary"
                      icon={<CheckOutlined />}
                      loading={detailActionLoading === 'audit'}
                      disabled={detailActionLoading != null}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {t('components.uniAction.audit')}
                    </Button>
                  </ActionConfirmPopconfirm>
                ),
              },
              {
                key: 'reject',
                visible: Boolean(detail && canReviewStatus(detail.status) && canReview),
                render: (
                  <Button
                    danger
                    icon={<CloseOutlined />}
                    disabled={detailActionLoading != null}
                    onClick={() => {
                      if (!detail) return;
                      openReject(detail.id);
                    }}
                  >
                    {t('components.uniAction.reject')}
                  </Button>
                ),
              },
            ]}
          />
        }
      />

      <Modal
        open={rejectOpen}
        title={t('app.kuaizhizao.afterSalesService.serviceSettlement.rejectTitle')}
        onCancel={() => {
          setRejectOpen(false);
          setRejectTargetId(null);
        }}
        destroyOnHidden
        confirmLoading={detailActionLoading === 'reject'}
        onOk={async () => {
          if (rejectTargetId == null) return;
          await executeReject(rejectTargetId, rejectRemarks);
        }}
      >
        <Input.TextArea
          rows={3}
          value={rejectRemarks}
          onChange={(e) => setRejectRemarks(e.target.value)}
          placeholder={t('app.kuaizhizao.afterSalesService.serviceSettlement.rejectPlaceholder')}
        />
      </Modal>
    </ListPageTemplate>
  );
};

export default ServiceSettlementsPage;
