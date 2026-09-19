import React, { useCallback, useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { App, Button, Input, Modal } from 'antd';
import { CheckOutlined, CloseOutlined, RollbackOutlined, SendOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { rowActionKind } from '../../../../../components/uni-action';
import { ActionConfirmPopconfirm } from '../../../../../components/action-confirm';
import { DetailDrawerActions, ListPageTemplate } from '../../../../../components/layout-templates';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';
import { UniTable } from '../../../../../components/uni-table';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import { hasReviewPermission } from '../../../../../utils/permissionContract';
import { useCurrentUser } from '../../../../../hooks/useCurrentUser';
import { MarkerTag, StatusTag } from '../../../../../constants/statusBadges';
import { formatBusinessDateOnly } from '../../../../../utils/format';
import { alignProColumns, GLOBAL_DOC_LIST_FIELD_RANK } from '../../sales-management/shared/documentFieldAlignment';
import {
  DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
  renderDocumentLineMaterialsPreview,
} from '../../sales-management/shared/documentLineMaterialsPreview';
import {
  outsourceSettlementApi,
  type OutsourceSettlement,
} from '../../../services/outsource-settlement';
import OutsourceSettlementFormModal from './OutsourceSettlementFormModal';
import { OutsourceSettlementDetailDrawer } from './components/OutsourceSettlementDetailDrawer';

const RESOURCE = 'kuaizhizao:outsource-settlement';

const REVIEW_STATUS_COLOR: Record<string, string> = {
  草稿: 'default',
  待审核: 'processing',
  已审核: 'success',
};

const OutsourceSettlementsPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const perms = useResourcePermissions(RESOURCE);
  const currentUser = useCurrentUser();
  const canReview = hasReviewPermission(currentUser ?? undefined, RESOURCE);
  const actionRef = useRef<ActionType>();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<OutsourceSettlement | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<OutsourceSettlement | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRetryIdRef = useRef<number | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectRemarks, setRejectRemarks] = useState('');

  const loadDetail = useCallback(async (id: number) => {
    setDetailLoading(true);
    setDetailError(null);
    try {
      setDetail(await outsourceSettlementApi.get(id));
    } catch (error) {
      setDetail(null);
      setDetailError(getApiErrorMessage(error, t('common.loadFailed')));
    } finally {
      setDetailLoading(false);
    }
  }, [t]);

  const openDetail = (row: OutsourceSettlement) => {
    detailRetryIdRef.current = row.id;
    setDetailOpen(true);
    setDetail(null);
    setDetailError(null);
    void loadDetail(row.id);
  };

  const refreshDetail = async (id: number) => {
    setDetail(await outsourceSettlementApi.get(id));
    actionRef.current?.reload();
  };

  const openEdit = async (row: OutsourceSettlement) => {
    setEditing(await outsourceSettlementApi.get(row.id));
    setModalOpen(true);
  };

  const executeDelete = async (row: OutsourceSettlement) => {
    await outsourceSettlementApi.delete(row.id);
    messageApi.success(t('common.deleteSuccess'));
    if (detail?.id === row.id) {
      setDetailOpen(false);
      setDetail(null);
    }
    actionRef.current?.reload();
  };

  const columns: ProColumns<OutsourceSettlement>[] = useMemo(
    () =>
      alignProColumns<OutsourceSettlement>(
        [
          {
            title: t('app.kuaizhizao.outsourceManagement.settlement.field.settlementCode'),
            dataIndex: 'settlement_code',
            width: 188,
            minWidth: 188,
            uniTableKeepWidth: true,
            resizable: false,
            fixed: 'left',
            copyable: true,
          },
          {
            title: t('app.kuaizhizao.outsourceManagement.settlement.field.supplierName'),
            dataIndex: 'supplier_name',
            width: 160,
            minWidth: 160,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
          },
          {
            title: t('app.kuaizhizao.outsourceManagement.settlement.field.settlementKind'),
            dataIndex: 'settlement_kind',
            width: 88,
            minWidth: 88,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) =>
              row.settlement_kind === 'credit' ? (
                <MarkerTag>{t('app.kuaizhizao.outsourceManagement.settlement.kindCredit')}</MarkerTag>
              ) : (
                <MarkerTag>{t('app.kuaizhizao.outsourceManagement.settlement.kindNormal')}</MarkerTag>
              ),
          },
          {
            title: t('app.kuaizhizao.outsourceManagement.settlement.field.invoiceStatus'),
            dataIndex: 'invoice_status',
            width: 96,
            minWidth: 96,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
          },
          {
            title: t('app.kuaizhizao.outsourceManagement.settlement.field.businessDate'),
            dataIndex: 'business_date',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            hideInSearch: true,
            render: (_, row) =>
              row.business_date ? formatBusinessDateOnly(String(row.business_date)) : '-',
          },
          {
            title: t('app.kuaizhizao.common.colLineMaterials'),
            ...DOCUMENT_LINE_MATERIALS_COLUMN_WIDTH_FLAGS,
            render: (_, row) =>
              renderDocumentLineMaterialsPreview(
                (row.items || []).map((it) => ({ material_name: it.product_name })),
                t,
              ),
          },
          {
            title: t('app.kuaizhizao.outsourceManagement.settlement.field.totalAmount'),
            dataIndex: 'total_amount',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            align: 'right',
            hideInSearch: true,
            render: (_, row) => (row.total_amount != null ? row.total_amount : '-'),
          },
          {
            title: t('common.status'),
            key: 'lifecycle',
            dataIndex: 'status',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => (
              <StatusTag color={REVIEW_STATUS_COLOR[row.status] ?? 'default'}>{row.status}</StatusTag>
            ),
          },
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right',
            hideInSearch: true,
            render: (_, row) => [
              <Button {...rowActionKind('read')} key="read" onClick={() => openDetail(row)} />,
              perms.canUpdate && row.status === '草稿' ? (
                <Button
                  {...rowActionKind('update')}
                  key="edit"
                  onClick={() => void openEdit(row)}
                />
              ) : null,
              perms.canAction?.('submit') && row.status === '草稿' ? (
                <Button
                  key="submit"
                  {...rowActionKind('submit')}
                  onClick={async () => {
                    await outsourceSettlementApi.submit(row.id);
                    messageApi.success(t('app.kuaizhizao.outsourceManagement.settlement.submitSuccess'));
                    actionRef.current?.reload();
                  }}
                />
              ) : null,
              perms.canDelete && row.status === '草稿' ? (
                <ActionConfirmPopconfirm
                  title={t('common.confirmDelete')}
                  onConfirm={() => executeDelete(row)}
                >
                  <Button
                    {...rowActionKind('delete')}
                    key="delete"
                    onClick={(e) => e.stopPropagation()}
                  />
                </ActionConfirmPopconfirm>
              ) : null,
            ],
          },
        ],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [messageApi, perms, t],
  );

  return (
    <ListPageTemplate>
      <UniTable<OutsourceSettlement>
        actionRef={actionRef}
        columns={columns}
        columnPersistenceId="apps.kuaizhizao.pages.outsource-management.settlements.v2"
        rowKey="id"
        headerTitle={t('app.kuaizhizao.menu.outsource-management.settlements')}
        request={async (params) => {
          const res = await outsourceSettlementApi.list({
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize,
            keyword: params.keyword as string | undefined,
            status: params.status as string | undefined,
          });
          return { data: res.items, total: res.total, success: true };
        }}
        showCreateButton={perms.canCreate}
        createButtonText={t('app.kuaizhizao.outsourceManagement.settlement.createTitle')}
        onCreate={() => {
          setEditing(null);
          setModalOpen(true);
        }}
      />

      <OutsourceSettlementFormModal
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

      <OutsourceSettlementDetailDrawer
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
                visible: Boolean(detail && perms.canUpdate && detail.status === '草稿'),
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
                visible: Boolean(detail && perms.canAction?.('submit') && detail.status === '草稿'),
                render: (
                  <Button
                    icon={<SendOutlined />}
                    onClick={async () => {
                      if (!detail) return;
                      await outsourceSettlementApi.submit(detail.id);
                      await refreshDetail(detail.id);
                      messageApi.success(t('app.kuaizhizao.outsourceManagement.settlement.submitSuccess'));
                    }}
                  >
                    {t('components.uniAction.submit')}
                  </Button>
                ),
              },
              {
                key: 'audit',
                visible: Boolean(detail && detail.status === '待审核' && canReview),
                render: (
                  <Button
                    type="primary"
                    icon={<CheckOutlined />}
                    onClick={async () => {
                      if (!detail) return;
                      await outsourceSettlementApi.audit(detail.id);
                      await refreshDetail(detail.id);
                      messageApi.success(t('app.kuaizhizao.outsourceManagement.settlement.auditSuccess'));
                    }}
                  >
                    {t('components.uniAction.audit')}
                  </Button>
                ),
              },
              {
                key: 'reject',
                visible: Boolean(detail && detail.status === '待审核' && canReview),
                render: (
                  <Button
                    danger
                    icon={<CloseOutlined />}
                    onClick={() => {
                      setRejectRemarks('');
                      setRejectOpen(true);
                    }}
                  >
                    {t('components.uniAction.reject')}
                  </Button>
                ),
              },
              {
                key: 'revoke',
                visible: Boolean(detail && detail.status === '已审核' && canReview),
                render: (
                  <Button
                    icon={<RollbackOutlined />}
                    onClick={async () => {
                      if (!detail) return;
                      await outsourceSettlementApi.revoke(detail.id);
                      await refreshDetail(detail.id);
                      messageApi.success(t('app.kuaizhizao.outsourceManagement.settlement.revokeSuccess'));
                    }}
                  >
                    {t('components.uniAction.revoke')}
                  </Button>
                ),
              },
            ]}
          />
        }
      />

      <Modal
        open={rejectOpen}
        title={t('app.kuaizhizao.outsourceManagement.settlement.rejectTitle')}
        onCancel={() => setRejectOpen(false)}
        destroyOnHidden
        onOk={async () => {
          if (!detail) return;
          if (!rejectRemarks.trim()) {
            messageApi.warning(t('app.kuaizhizao.outsourceManagement.settlement.rejectPlaceholder'));
            return;
          }
          await outsourceSettlementApi.reject(detail.id, { review_remarks: rejectRemarks });
          setRejectOpen(false);
          await refreshDetail(detail.id);
          messageApi.success(t('app.kuaizhizao.outsourceManagement.settlement.rejectSuccess'));
        }}
      >
        <Input.TextArea
          rows={3}
          value={rejectRemarks}
          onChange={(e) => setRejectRemarks(e.target.value)}
          placeholder={t('app.kuaizhizao.outsourceManagement.settlement.rejectPlaceholder')}
        />
      </Modal>
    </ListPageTemplate>
  );
};

export default OutsourceSettlementsPage;
