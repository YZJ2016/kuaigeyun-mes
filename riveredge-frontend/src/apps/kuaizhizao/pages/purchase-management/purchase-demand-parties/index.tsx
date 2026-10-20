/**
 * 采购询价需方维护
 */
import React, { useMemo, useRef, useState } from 'react';
import type { ActionType, ProColumns } from '@ant-design/pro-components';
import { ProFormSwitch, ProFormText, ProFormTextArea } from '@ant-design/pro-components';
import { App, Button, Popconfirm } from 'antd';
import { useTranslation } from 'react-i18next';
import { FormModalTemplate, ListPageTemplate, MODAL_CONFIG } from '../../../../../components/layout-templates';
import { UniTable } from '../../../../../components/uni-table';
import { rowActionKind } from '../../../../../components/uni-action';
import { MarkerTag } from '../../../../../constants/statusBadges';
import { useResourcePermissions } from '../../../../../hooks/useResourcePermissions';
import {
  createPurchaseDemandParty,
  deletePurchaseDemandParty,
  listPurchaseDemandParties,
  updatePurchaseDemandParty,
  type PurchaseDemandParty,
} from '../../../services/purchase-demand-party';
import { getApiErrorMessage } from '../../../../../utils/errorHandler';

const RESOURCE = 'kuaizhizao:purchase-demand-party';
const NS = 'app.kuaizhizao.purchaseDemandParty';

const PurchaseDemandPartiesPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const actionRef = useRef<ActionType>();
  const tableRowsRef = useRef<PurchaseDemandParty[]>([]);
  const perms = useResourcePermissions(RESOURCE);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<PurchaseDemandParty | null>(null);

  const openCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const handleBatchDelete = async (keys: React.Key[]) => {
    for (const key of keys) {
      await deletePurchaseDemandParty(Number(key));
    }
    messageApi.success(t(`${NS}.batchDeleted`, { count: keys.length }));
    setSelectedRowKeys([]);
    actionRef.current?.reload();
  };

  const columns: ProColumns<PurchaseDemandParty>[] = useMemo(
    () => [
      {
        title: t(`${NS}.col.code`),
        dataIndex: 'code',
        width: 120,
        minWidth: 120,
        uniTableKeepWidth: true,
        resizable: false,
      },
      { title: t(`${NS}.col.name`), dataIndex: 'name', ellipsis: true },
      {
        title: t(`${NS}.col.contactName`),
        dataIndex: 'contact_name',
        width: 120,
        minWidth: 120,
        uniTableKeepWidth: true,
        ellipsis: true,
      },
      {
        title: t(`${NS}.col.contactPhone`),
        dataIndex: 'contact_phone',
        width: 130,
        minWidth: 130,
        uniTableKeepWidth: true,
        ellipsis: true,
        hideInSearch: true,
      },
      {
        title: t(`${NS}.col.contactEmail`),
        dataIndex: 'contact_email',
        width: 180,
        minWidth: 160,
        uniTableKeepWidth: true,
        ellipsis: true,
        hideInSearch: true,
      },
      {
        title: t(`${NS}.col.active`),
        dataIndex: 'is_active',
        width: 88,
        minWidth: 88,
        uniTableKeepWidth: true,
        resizable: false,
        hideInSearch: true,
        render: (_, r) =>
          r.is_active ? (
            <MarkerTag color="success">{t('common.enabled')}</MarkerTag>
          ) : (
            <MarkerTag>{t('common.disabled')}</MarkerTag>
          ),
      },
      {
        title: t('common.actions'),
        key: 'action',
        fixed: 'right',
        hideInSearch: true,
        render: (_, record) => {
          const actions: React.ReactNode[] = [];
          if (perms.canUpdate) {
            actions.push(
              <Button
                key="edit"
                type="link"
                size="small"
                {...rowActionKind('update')}
                onClick={() => {
                  setEditing(record);
                  setModalOpen(true);
                }}
              />,
            );
          }
          if (perms.canDelete) {
            actions.push(
              <Popconfirm
                key="del"
                title={t(`${NS}.confirmDelete`)}
                onConfirm={async () => {
                  try {
                    await deletePurchaseDemandParty(record.id);
                    messageApi.success(t('common.deleteSuccess'));
                    actionRef.current?.reload();
                  } catch (e) {
                    messageApi.error(getApiErrorMessage(e, t('common.deleteFailed')));
                  }
                }}
              >
                <Button type="link" size="small" {...rowActionKind('delete')} />
              </Popconfirm>,
            );
          }
          return actions;
        },
      },
    ],
    [messageApi, perms.canDelete, perms.canUpdate, t],
  );

  const modalInitialValues = useMemo(() => {
    if (!editing) {
      return { is_active: true };
    }
    return {
      code: editing.code,
      name: editing.name,
      contact_name: editing.contact_name ?? undefined,
      contact_phone: editing.contact_phone ?? undefined,
      contact_email: editing.contact_email ?? undefined,
      address: editing.address ?? undefined,
      tax_no: editing.tax_no ?? undefined,
      notes: editing.notes ?? undefined,
      is_active: editing.is_active,
    };
  }, [editing]);

  return (
    <ListPageTemplate>
      <UniTable<PurchaseDemandParty>
        actionRef={actionRef}
        rowKey="id"
        permissionResource={RESOURCE}
        columnPersistenceId="apps.kuaizhizao.pages.purchase-management.purchase-demand-parties.list-v1"
        columns={columns}
        showAdvancedSearch
        skipFuzzyPinyinClientFilter
        enableRowSelection={perms.canDelete}
        selectedRowKeys={selectedRowKeys}
        onRowSelectionChange={setSelectedRowKeys}
        onTableDataChange={(rows) => {
          tableRowsRef.current = rows;
        }}
        showCreateButton={perms.canCreate}
        createButtonText={t(`${NS}.createButton`)}
        onCreate={openCreate}
        showDeleteButton={perms.canDelete}
        onDelete={handleBatchDelete}
        deleteConfirmTitle={t('common.confirmBatchDelete')}
        deleteConfirmDescription={(count) => t(`${NS}.batchDeleteConfirm`, { count })}
        request={async (params) => {
          const keyword = String(params?.keyword ?? params?.name ?? '').trim() || undefined;
          const res = await listPurchaseDemandParties({
            keyword,
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize || 20,
          });
          return { data: res.data ?? [], success: true, total: res.total ?? 0 };
        }}
      />
      <FormModalTemplate
        open={modalOpen}
        title={editing ? t(`${NS}.editTitle`) : t(`${NS}.createTitle`)}
        onCancel={() => setModalOpen(false)}
        initialValues={modalInitialValues}
        modalProps={{ destroyOnHidden: true }}
        onFinish={async (values) => {
          try {
            if (editing) {
              await updatePurchaseDemandParty(editing.id, values);
              messageApi.success(t('common.updateSuccess'));
            } else {
              await createPurchaseDemandParty(values);
              messageApi.success(t('common.createSuccess'));
            }
            setModalOpen(false);
            actionRef.current?.reload();
            return true;
          } catch (e) {
            messageApi.error(getApiErrorMessage(e, t('common.saveFailed')));
            return false;
          }
        }}
        width={MODAL_CONFIG.STANDARD_WIDTH}
      >
        {!editing && (
          <ProFormText
            name="code"
            label={t(`${NS}.col.code`)}
            placeholder={t(`${NS}.codeAutoPlaceholder`)}
          />
        )}
        <ProFormText name="name" label={t(`${NS}.col.name`)} rules={[{ required: true }]} />
        <ProFormText name="contact_name" label={t(`${NS}.col.contactName`)} />
        <ProFormText name="contact_phone" label={t(`${NS}.col.contactPhone`)} />
        <ProFormText name="contact_email" label={t(`${NS}.col.contactEmail`)} />
        <ProFormText name="address" label={t(`${NS}.col.address`)} />
        <ProFormText name="tax_no" label={t(`${NS}.col.taxNo`)} />
        <ProFormTextArea name="notes" label={t('common.remark')} fieldProps={{ rows: 2 }} />
        <ProFormSwitch name="is_active" label={t(`${NS}.col.active`)} />
      </FormModalTemplate>
    </ListPageTemplate>
  );
};

export default PurchaseDemandPartiesPage;
