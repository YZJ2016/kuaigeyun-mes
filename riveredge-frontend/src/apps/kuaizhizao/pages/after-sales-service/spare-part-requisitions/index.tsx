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
import { SourceDocumentCode } from '../../../../../components/linked-document-code/SourceDocumentCode';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { useCustomFieldsForList } from '../../../../../hooks/useCustomFieldsForList';
import { hasReviewPermission } from '../../../../../utils/permissionContract';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import { alignProColumns, SALES_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../../sales-management/shared/documentLineMaterialsPreview';
import {
  AFTER_SALES_REVIEW_STATUS_COLOR,
  renderAfterSalesStatusTag,
} from '../shared/afterSalesListPresentation';
import { pickListSearchKeyword, pickSearchString } from '../../../../../utils/tableQueryKey';
import {
  afterSalesSparePartRequisitionApi,
  type AfterSalesSparePartRequisition,
} from '../../../services/after-sales-service';
import { SparePartRequisitionDetailDrawer } from './components/SparePartRequisitionDetailDrawer';
import SparePartRequisitionFormModal from './SparePartRequisitionFormModal';
import { buildDocumentListHelpViewConfig, DOCUMENT_LIST_HELP_KEYS } from '../../../../../components/page-help-wiki';

const RESOURCE = 'kuaizhizao:after-sales-spare-part-requisition';
const CUSTOM_FIELD_TABLE = 'apps_kuaizhizao_after_sales_spare_part_requisitions';

type DetailActionKey = 'submit' | 'audit' | 'reject';

const canEditStatus = (status?: string) => status === '草稿' || status === '已驳回';
const canSubmitStatus = (status?: string) => status === '草稿' || status === '已驳回';
const canReviewStatus = (status?: string) => status === '待审核';

const AfterSalesSparePartRequisitionsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions(RESOURCE);
  const currentUser = useCurrentUser();
  const canReview = hasReviewPermission(currentUser ?? undefined, RESOURCE);
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AfterSalesSparePartRequisition | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<AfterSalesSparePartRequisition | null>(null);
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
  } = useCustomFieldsForList<AfterSalesSparePartRequisition>({
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
      setDetail(await afterSalesSparePartRequisitionApi.get(id));
      await loadFieldValuesForDetail(id);
    } catch (error) {
      setDetail(null);
      setDetailError(getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.detail.loadFailed')));
    } finally {
      setDetailLoading(false);
    }
  }, [loadFieldValuesForDetail, resetDetailFieldValues, t]);

  const openDetail = (row: AfterSalesSparePartRequisition) => {
    detailRetryIdRef.current = row.id;
    setDetailOpen(true);
    setDetail(null);
    setDetailError(null);
    void loadDetail(row.id);
  };

  const refreshDetail = useCallback(async (id: number) => {
    setDetail(await afterSalesSparePartRequisitionApi.get(id));
    actionRef.current?.reload();
  }, []);

  const executeSubmit = useCallback(
    async (id: number) => {
      setDetailActionLoading('submit');
      try {
        await afterSalesSparePartRequisitionApi.submit(id);
        await refreshDetail(id);
        messageApi.success(t('app.kuaizhizao.afterSalesService.sparePartRequisition.submitSuccess'));
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.sparePartRequisition.submitFailed')),
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
        await afterSalesSparePartRequisitionApi.audit(id);
        await refreshDetail(id);
        messageApi.success(t('app.kuaizhizao.afterSalesService.sparePartRequisition.auditSuccess'));
      } catch (error) {
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.sparePartRequisition.auditFailed')),
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
        messageApi.error(t('app.kuaizhizao.afterSalesService.sparePartRequisition.rejectRemarksRequired'));
        throw new Error('reject_remarks_required');
      }
      setDetailActionLoading('reject');
      try {
        await afterSalesSparePartRequisitionApi.reject(id, { review_remarks: remarks });
        setRejectOpen(false);
        setRejectTargetId(null);
        setRejectRemarks('');
        await refreshDetail(id);
        messageApi.success(t('app.kuaizhizao.afterSalesService.sparePartRequisition.rejectSuccess'));
      } catch (error) {
        if (error instanceof Error && error.message === 'reject_remarks_required') {
          throw error;
        }
        messageApi.error(
          getApiErrorMessage(error, t('app.kuaizhizao.afterSalesService.sparePartRequisition.rejectFailed')),
        );
        throw error;
      } finally {
        setDetailActionLoading(null);
      }
    },
    [messageApi, refreshDetail, t],
  );

  const openEdit = async (row: AfterSalesSparePartRequisition) => {
    setEditing(await afterSalesSparePartRequisitionApi.get(row.id));
    setModalOpen(true);
  };

  const openReject = useCallback((id: number) => {
    setRejectTargetId(id);
    setRejectRemarks('');
    setRejectOpen(true);
  }, []);

  const columns: ProColumns<AfterSalesSparePartRequisition>[] = useMemo(
    () =>
      alignProColumns<AfterSalesSparePartRequisition>(
        [
          {
            title: t('app.kuaizhizao.afterSalesService.sparePartRequisition.field.requisitionCode'),
            dataIndex: 'requisition_code',
            width: 188,
            minWidth: 188,
            uniTableKeepWidth: true,
            resizable: false,
            fixed: 'left',
            copyable: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.sparePartRequisition.field.warehouseName'),
            dataIndex: 'warehouse_name',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
          },
          {
            title: t('app.kuaizhizao.afterSalesService.sparePartRequisition.field.sourceCode'),
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
            // 明细预览吃余量（采购/仓储同款）；短仓库列勿当 RemainderFlex
            title: t('app.kuaizhizao.common.colLineMaterials'),
            ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
            render: (_, row) => renderDocumentLineMaterialsPreview(row.items, t),
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
                      'app.kuaizhizao.afterSalesService.sparePartRequisition.submitConfirm',
                      { code: row.requisition_code },
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
                      'app.kuaizhizao.afterSalesService.sparePartRequisition.auditConfirm',
                      { code: row.requisition_code },
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
      <UniTable<AfterSalesSparePartRequisition>
        viewTypes={['table', 'help']}
          helpViewConfig={buildDocumentListHelpViewConfig(DOCUMENT_LIST_HELP_KEYS.afterSalesSpareRequisition)}
        actionRef={actionRef}
        columns={columns}
        columnPersistenceId="apps.kuaizhizao.pages.after-sales-service.spare-part-requisitions.v9-row-review"
        showAdvancedSearch
        skipFuzzyPinyinClientFilter
        rowKey="id"
        headerTitle={t('app.kuaizhizao.menu.after-sales-service.spare-part-requisitions')}
        request={async (params, _sort, _filter, searchFormValues, meta?: UniTableRequestMeta) => {
          const res = await afterSalesSparePartRequisitionApi.list({
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
        createButtonText={t('app.kuaizhizao.afterSalesService.sparePartRequisition.createTitle')}
        onCreate={() => {
          setEditing(null);
          setModalOpen(true);
        }}
        enableRowSelection={perms.canDelete}
        showDeleteButton={perms.canDelete}
        deleteButtonText={t('common.delete')}
        onDelete={async (keys) => {
          await Promise.all(keys.map((key) => afterSalesSparePartRequisitionApi.delete(Number(key))));
    messageApi.success(t('common.batchDeleteSuccess', { count: keys.length }));
    actionRef.current?.reload();
        }}
      />

      <SparePartRequisitionFormModal
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

      <SparePartRequisitionDetailDrawer
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
                      'app.kuaizhizao.afterSalesService.sparePartRequisition.submitConfirm',
                      { code: detail?.requisition_code },
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
                      'app.kuaizhizao.afterSalesService.sparePartRequisition.auditConfirm',
                      { code: detail?.requisition_code },
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
        title={t('app.kuaizhizao.afterSalesService.sparePartRequisition.rejectTitle')}
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
          placeholder={t('app.kuaizhizao.afterSalesService.sparePartRequisition.rejectPlaceholder')}
        />
      </Modal>
    </ListPageTemplate>
  );
};

export default AfterSalesSparePartRequisitionsPage;
