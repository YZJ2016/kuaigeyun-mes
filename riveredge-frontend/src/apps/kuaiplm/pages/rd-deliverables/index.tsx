/**
 * 研发交付物（支持无项目直管）
 */

import { InboxOutlined } from '@ant-design/icons';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import type { ProColumns, ProFormInstance } from '@ant-design/pro-components';
import {
  ActionType,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProFormUploadDragger,
} from '@ant-design/pro-components';
import { Alert, App, Button, Modal, Result, Space, Spin, Table, Tag, Typography } from 'antd';
import { ActionConfirmPopconfirm } from '../../../../components/action-confirm';
import { MarkerTag } from '../../../../constants/statusBadges';
import { rowActionKind, rowActionViewHistory } from '../../../../components/uni-action';
import { UniTable } from '../../../../components/uni-table';
import {
  alignProColumns,
  GLOBAL_DOC_LIST_FIELD_RANK,
} from '../../../kuaizhizao/pages/sales-management/shared/documentFieldAlignment';
import { buildDocumentAuditColumns } from '../../../kuaizhizao/pages/shared/documentAuditColumns';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../utils/uniTableLayoutColumns';
import {
  DetailDrawerTemplate,
  FormModalTemplate,
  ListPageTemplate,
} from '../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { getApiErrorMessage } from '../../../../utils/errorHandler';
import { uploadFile } from '../../../../services/file';
import { renderDocumentStatusTag } from '../../../../utils/documentLifecycleStatusTag';
import { NEW_SHORTCUT_HINT } from '../../../../utils/globalNewShortcut';
import { ThemedSegmented } from '../../../../components/themed-segmented';
import Phase2ProjectSelect from '../../components/Phase2ProjectSelect';
import { RdDeliverableTypeFormFields } from '../../components/RdDeliverableTypeFormFields';
import { getKuaiplmDeliverableStatusText } from '../../components/kuaiplmMeta';
import {
  buildRdDeliverablePayload,
  validateRdDeliverablePayloadClient,
} from '../../utils/rdDeliverablePayload';
import {
  parseRdDeliverableDeptPreset,
  rdDeliverableTypesForPreset,
  rdDeliverableTypesQueryParam,
} from '../../utils/rdDeliverableDepartmentPresets';
import {
  buildRdDeliverableTypeSelectOptions,
  RD_DELIVERABLE_TYPE_COLUMN_WIDTH,
  resolveRdDeliverableTypeLabel,
} from '../../utils/rdDeliverableTypePresentation';
import type { RdProjectDeliverable } from '../../services/rd-project';
import {
  approveRdDeliverable,
  createRdDeliverable,
  deleteRdDeliverable,
  getRdDeliverable,
  issueRdDeliverable,
  listRdDeliverableVersions,
  listRdDeliverables,
  rejectRdDeliverable,
  reviseRdDeliverable,
  submitRdDeliverable,
  updateRdDeliverable,
} from '../../services/rd-deliverable';
import { useAuditRequired } from '../../../../hooks/useAuditRequired';
import { getRoleList } from '../../../../services/role';
import { RdDeliverableCapabilitiesTags } from '../../components/RdDeliverableCapabilitiesTags';
import { UniUserSelect } from '../../../../components/uni-user-select';
import { isRdDeliverableIssueScopedType } from '../../utils/rdDeliverableIssueScopedTypes';

const RESOURCE = 'kuaiplm:project';
const DELIVERABLE_FILE_CATEGORY = 'rd_deliverable';

const DELIVERABLE_STATUS_COLOR: Record<string, string> = {
  PENDING: 'default',
  SUBMITTED: 'processing',
  APPROVED: 'success',
  REJECTED: 'error',
};

type ScopeFilter = 'all' | 'unlinked' | 'linked';

const RdDeliverablesPage: React.FC = () => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const actionRef = useRef<ActionType>();
  const formRef = useRef<ProFormInstance>();
  const tableRowsRef = useRef<RdProjectDeliverable[]>([]);
  const perms = useResourcePermissions(RESOURCE);
  const deliverableAuditEnabled = useAuditRequired('rd_deliverable');
  const canApprove = !!perms.canAction?.('approve');

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<RdProjectDeliverable | null>(null);
  const linkedProjectCode = editing?.project_code ?? null;
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailRow, setDetailRow] = useState<RdProjectDeliverable | null>(null);
  const [versionOpen, setVersionOpen] = useState(false);
  const [versionLoading, setVersionLoading] = useState(false);
  const [versionRows, setVersionRows] = useState<any[]>([]);
  const [versionCanDownload, setVersionCanDownload] = useState(false);
  const [reviseOpen, setReviseOpen] = useState(false);
  const [reviseTarget, setReviseTarget] = useState<RdProjectDeliverable | null>(null);
  const reviseFormRef = useRef<ProFormInstance>();
  const [issueOpen, setIssueOpen] = useState(false);
  const [issueTarget, setIssueTarget] = useState<RdProjectDeliverable | null>(null);
  const issueFormRef = useRef<ProFormInstance>();

  const scopeFilter = (searchParams.get('scope') as ScopeFilter) || 'all';
  const deptPreset = parseRdDeliverableDeptPreset(searchParams.get('preset'));
  const isCustomerDocPreset = deptPreset === 'customer';
  const presetTypeCodes = useMemo(() => rdDeliverableTypesForPreset(deptPreset), [deptPreset]);
  const typesQuery = useMemo(
    () => rdDeliverableTypesQueryParam(presetTypeCodes),
    [presetTypeCodes],
  );

  const deliverableTypeOptions = useMemo(() => {
    const all = buildRdDeliverableTypeSelectOptions(t);
    if (!presetTypeCodes?.length) return all;
    const allowed = new Set(presetTypeCodes);
    return all.filter((o) => allowed.has(o.value));
  }, [t, presetTypeCodes]);

  const typeLabel = useCallback(
    (v?: string | null) => resolveRdDeliverableTypeLabel(t, v),
    [t],
  );

  const reload = useCallback(() => {
    actionRef.current?.reload();
  }, []);

  const openCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const openEdit = (row: RdProjectDeliverable) => {
    setEditing(row);
    setModalOpen(true);
  };

  const openDetail = (row: RdProjectDeliverable) => {
    setDetailRow(row);
    setDetailOpen(true);
    if (row.id != null) {
      void getRdDeliverable(row.id)
        .then(setDetailRow)
        .catch(() => undefined);
    }
  };

  const openVersions = useCallback(
    async (row: RdProjectDeliverable) => {
      if (row.id == null) return;
      setVersionOpen(true);
      setVersionLoading(true);
      try {
        const res = await listRdDeliverableVersions(row.id);
        setVersionRows(res.items || []);
        setVersionCanDownload(Boolean(res.can_download_history));
      } catch (error) {
        messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
      } finally {
        setVersionLoading(false);
      }
    },
    [messageApi, t],
  );

  const isDeliverableDeletable = (row: RdProjectDeliverable) => {
    const status = (row.status || '').toUpperCase();
    return status === 'PENDING' || status === 'REJECTED';
  };

  const columns = useMemo(
    () =>
      alignProColumns(
        [
          {
            title: t('common.name'),
            dataIndex: 'name',
            key: 'title',
            minWidth: 160,
            uniTablePrimaryFlex: true,
            uniTableRemainderFlex: true,
            ellipsis: true,
          },
          {
            title: t('app.kuaiplm.common.columns.type'),
            dataIndex: 'deliverable_type',
            key: 'document_type',
            width: RD_DELIVERABLE_TYPE_COLUMN_WIDTH,
            minWidth: RD_DELIVERABLE_TYPE_COLUMN_WIDTH,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: false,
            render: (_, row) => {
              const label = typeLabel(row.deliverable_type);
              return label ? <MarkerTag>{label}</MarkerTag> : null;
            },
          },
          {
            title: t('app.kuaiplm.rdDeliverables.columns.capabilities'),
            key: 'capabilities',
            width: 280,
            minWidth: 240,
            uniTableKeepWidth: true,
            hideInSearch: true,
            render: (_, row) => <RdDeliverableCapabilitiesTags capabilities={row.capabilities} />,
          },
          {
            title: t('app.kuaiplm.rdDeliverables.columns.projectCode'),
            dataIndex: 'project_code',
            key: 'project_code',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
            render: (_, row) =>
              row.project_code?.trim() ||
              (row.project_id
                ? t('app.kuaiplm.rdDeliverables.columns.projectLinked')
                : t('app.kuaiplm.rdDeliverables.columns.noProject')),
          },
          {
            title: t('app.kuaiplm.rdProjects.detail.deliverable.catalogCode'),
            dataIndex: 'material_code',
            key: 'material_code',
            width: 120,
            minWidth: 120,
            uniTableKeepWidth: true,
            resizable: false,
            ellipsis: true,
          },
          {
            title: t('app.kuaiplm.rdProjects.detail.deliverable.version'),
            dataIndex: 'version',
            key: 'version',
            width: 72,
            minWidth: 72,
            uniTableKeepWidth: true,
            resizable: false,
          },
          {
            ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
            title: t('common.status'),
            dataIndex: 'status',
            key: 'lifecycle',
            fixed: 'right',
            render: (_, row) =>
              renderDocumentStatusTag(getKuaiplmDeliverableStatusText(t, row.status), row.status),
          },
          ...buildDocumentAuditColumns(t),
          {
            title: t('common.action'),
            valueType: 'option',
            key: 'option',
            fixed: 'right',
            render: (_, row) => {
              const actions: React.ReactNode[] = [
                <Button
                  key="detail"
                  type="link"
                  size="small"
                  {...rowActionKind('read')}
                  onClick={(e) => {
                    e.stopPropagation();
                    openDetail(row);
                  }}
                />,
              ];
              if (
                isDeliverableDeletable(row) &&
                perms.canUpdate &&
                row.id != null
              ) {
                actions.push(
                  <Button
                    key="edit"
                    type="link"
                    size="small"
                    {...rowActionKind('update')}
                    onClick={(e) => {
                      e.stopPropagation();
                      openEdit(row);
                    }}
                  />,
                );
              }
              if (row.id != null) {
                actions.push(
                  <Button
                    key="versions"
                    type="link"
                    size="small"
                    {...rowActionViewHistory()}
                    onClick={(e) => {
                      e.stopPropagation();
                      void openVersions(row);
                    }}
                  />,
                );
              }
              if (
                row.status === 'PENDING' &&
                perms.canAction?.('submit') &&
                row.id != null
              ) {
                actions.push(
                  <Button
                    key="submit"
                    type="link"
                    size="small"
                    {...rowActionKind('submit')}
                    onClick={async (e) => {
                      e.stopPropagation();
                      try {
                        await submitRdDeliverable(row.id!);
                        messageApi.success(
                          t('app.kuaiplm.rdProjects.detail.deliverable.submitSuccess'),
                        );
                        reload();
                      } catch (error) {
                        messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
                      }
                    }}
                  />,
                );
              }
              if (
                row.status === 'SUBMITTED' &&
                canApprove &&
                !deliverableAuditEnabled &&
                row.id != null
              ) {
                actions.push(
                  <Button
                    key="approve"
                    type="link"
                    size="small"
                    {...rowActionKind('approve')}
                    onClick={async (e) => {
                      e.stopPropagation();
                      try {
                        await approveRdDeliverable(row.id!);
                        messageApi.success(
                          t('app.kuaiplm.rdProjects.detail.deliverable.approveSuccess'),
                        );
                        reload();
                      } catch (error) {
                        messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
                      }
                    }}
                  />,
                );
              }
              if (row.status === 'SUBMITTED' && canApprove && row.id != null) {
                actions.push(
                  <Button
                    key="reject"
                    type="link"
                    size="small"
                    danger
                    {...rowActionKind('reject')}
                    onClick={async (e) => {
                      e.stopPropagation();
                      try {
                        await rejectRdDeliverable(row.id!, t('common.rejected'));
                        messageApi.success(
                          t('app.kuaiplm.rdProjects.detail.deliverable.rejectSuccess'),
                        );
                        reload();
                      } catch (error) {
                        messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
                      }
                    }}
                  />,
                );
              }
              if (
                row.status === 'APPROVED' &&
                isRdDeliverableIssueScopedType(row.deliverable_type) &&
                perms.canUpdate &&
                row.id != null
              ) {
                actions.push(
                  <Button
                    key="issue"
                    type="link"
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      setIssueTarget(row);
                      setIssueOpen(true);
                    }}
                  >
                    {t('app.kuaiplm.rdDeliverables.actions.issue')}
                  </Button>,
                );
              }
              if (isDeliverableDeletable(row) && perms.canDelete && row.id != null) {
                actions.push(
                  <ActionConfirmPopconfirm
                    key="delete"
                    title={t('app.kuaiplm.rdProjects.detail.deliverable.deleteConfirm')}
                    onConfirm={async () => {
                      try {
                        await deleteRdDeliverable(row.id!);
                        messageApi.success(t('common.deleteSuccess'));
                        reload();
                      } catch (error) {
                        messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
                      }
                    }}
                  >
                    <Button
                      type="link"
                      size="small"
                      {...rowActionKind('delete')}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </ActionConfirmPopconfirm>,
                );
              }
              return actions;
            },
          },
        ] as ProColumns<RdProjectDeliverable>[],
        GLOBAL_DOC_LIST_FIELD_RANK,
      ),
    [t, typeLabel, perms, messageApi, openVersions, reload, canApprove, deliverableAuditEnabled],
  );

  if (!perms.canRead) {
    return (
      <ListPageTemplate>
        <Result status="403" title={t('common.noPermission')} />
      </ListPageTemplate>
    );
  }

  return (
    <ListPageTemplate>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        title={
          isCustomerDocPreset
            ? t('app.kuaiplm.rdDeliverables.pageHintCustomer')
            : t('app.kuaiplm.rdDeliverables.pageHint')
        }
      />
      <UniTable<RdProjectDeliverable>
        actionRef={actionRef}
        permissionResource={RESOURCE}
        columnPersistenceId="apps.kuaiplm.pages.rd-deliverables.rank-v4"
        rowKey="id"
        columns={columns}
        enableRowSelection
        onTableDataChange={(rows) => {
          tableRowsRef.current = rows;
        }}
        showDeleteButton={perms.canDelete}
        onDelete={async (keys) => {
          const rows = tableRowsRef.current.filter((r) => r.id != null && keys.includes(r.id));
          const deletable = rows.filter(isDeliverableDeletable);
          if (!deletable.length) {
            messageApi.warning(t('app.kuaiplm.rdDeliverables.messages.deleteOnlyPending'));
            return;
          }
          await Promise.all(deletable.map((r) => deleteRdDeliverable(r.id!)));
          messageApi.success(t('common.deleteSuccess'));
          reload();
        }}
        beforeSearchButtons={
          <ThemedSegmented
            surfaceBackground
            size="medium"
            value={scopeFilter}
            options={[
              { label: t('app.kuaiplm.rdDeliverables.scope.all'), value: 'all' },
              { label: t('app.kuaiplm.rdDeliverables.scope.unlinked'), value: 'unlinked' },
              { label: t('app.kuaiplm.rdDeliverables.scope.linked'), value: 'linked' },
            ]}
            onChange={(v) => {
              const next = new URLSearchParams(searchParams);
              if (v === 'all') next.delete('scope');
              else next.set('scope', String(v));
              setSearchParams(next, { replace: true });
              actionRef.current?.reload();
            }}
          />
        }
        showCreateButton={perms.canCreate}
        createButtonText={
          isCustomerDocPreset
            ? t('app.kuaiplm.rdDeliverables.createButtonCustomer')
            : t('app.kuaiplm.rdDeliverables.createButton')
        }
        onCreate={openCreate}
        newShortcutHint={NEW_SHORTCUT_HINT}
        params={{ scope: scopeFilter }}
        request={async (params) => {
          const keyword = String(params.keyword || params.name || '').trim() || undefined;
          const res = await listRdDeliverables({
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize || 20,
            keyword,
            deliverable_type: params.deliverable_type as string | undefined,
            types: typesQuery,
            unlinked_only: scopeFilter === 'unlinked',
            linked_only: scopeFilter === 'linked',
          });
          return { data: res.items || [], success: true, total: res.total };
        }}
      />

      <FormModalTemplate
        title={
          editing
            ? t('app.kuaiplm.rdDeliverables.editTitle')
            : t('app.kuaiplm.rdDeliverables.createTitle')
        }
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditing(null);
        }}
        formRef={formRef}
        initialValues={
          editing
            ? {
                ...editing,
                project_id: editing.project_id ?? undefined,
              }
            : { status: 'PENDING' }
        }
        onFinish={async (values) => {
          const payload = buildRdDeliverablePayload(values, { formRef });
          const clientErr = validateRdDeliverablePayloadClient(payload, t);
          if (clientErr) {
            messageApi.error(clientErr);
            return;
          }
          try {
            if (editing?.id) {
              await updateRdDeliverable(editing.id, payload);
              messageApi.success(t('app.kuaiplm.rdProjects.detail.deliverable.updateSuccess'));
            } else {
              await createRdDeliverable(payload);
              messageApi.success(t('app.kuaiplm.rdProjects.detail.deliverable.createSuccess'));
            }
            setModalOpen(false);
            setEditing(null);
            actionRef.current?.reload();
          } catch (error) {
            messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
          }
        }}
      >
        <ProFormText
          name="name"
          label={t('app.kuaiplm.rdProjects.detail.deliverable.name')}
          rules={[{ required: true }]}
        />
        <ProFormSelect
          name="deliverable_type"
          label={t('app.kuaiplm.common.columns.type')}
          options={deliverableTypeOptions}
          showSearch
          rules={[{ required: true }]}
        />
        <Phase2ProjectSelect
          name="project_id"
          label={t('app.kuaiplm.rdDeliverables.form.projectOptional')}
        />
        <RdDeliverableTypeFormFields
          linkedProjectCode={linkedProjectCode}
          showStandaloneProjectCode
        />
        <ProFormSelect
          name="status"
          label={t('common.status')}
          initialValue="PENDING"
          options={[
            { value: 'PENDING', label: getKuaiplmDeliverableStatusText(t, 'PENDING') },
            { value: 'REJECTED', label: getKuaiplmDeliverableStatusText(t, 'REJECTED') },
          ]}
        />
        <ProFormText name="file_uuid" hidden />
        <ProFormText name="file_name" hidden />
        <ProFormUploadDragger
          name="file_upload"
          label={t('app.kuaiplm.rdProjects.detail.deliverable.file')}
          max={1}
          icon={<InboxOutlined />}
          title={t('app.kuaiplm.rdProjects.detail.deliverable.fileUploadHint')}
          description={t('app.kuaiplm.rdProjects.detail.deliverable.fileUploadSubHint')}
          fieldProps={{
            multiple: false,
            maxCount: 1,
            customRequest: async (options) => {
              try {
                const raw = options.file as File;
                const res = await uploadFile(raw, { category: DELIVERABLE_FILE_CATEGORY });
                const uuid = String(res?.uuid || '').trim();
                if (!uuid) {
                  throw new Error(t('app.kuaiplm.rdProjects.detail.deliverable.fileRequired'));
                }
                const fileName = res.original_name || res.name || raw.name;
                formRef.current?.setFieldsValue?.({ file_uuid: uuid, file_name: fileName });
                options.onSuccess?.(
                  { uuid, original_name: fileName, name: res.name || fileName },
                  raw as never,
                );
              } catch (err) {
                options.onError?.(err as Error);
              }
            },
            onRemove: () => {
              formRef.current?.setFieldsValue?.({ file_uuid: undefined, file_name: undefined });
              return true;
            },
          }}
        />
        <ProFormTextArea
          name="description"
          label={t('common.remark')}
          placeholder={t('app.kuaiplm.rdProjects.detail.deliverable.changeDetailPlaceholder')}
        />
      </FormModalTemplate>

      <DetailDrawerTemplate
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        title={detailRow?.name || t('app.kuaiplm.menu.rd-deliverables')}
      >
        {detailRow ? (
          <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Typography.Text type="secondary">{t('app.kuaiplm.common.columns.type')}</Typography.Text>
              <div>{typeLabel(detailRow.deliverable_type)}</div>
            </div>
            <div>
              <Typography.Text type="secondary">
                {t('app.kuaiplm.rdDeliverables.columns.projectCode')}
              </Typography.Text>
              <div>
                {detailRow.project_code ||
                  (detailRow.project_id ? (
                    <Button
                      type="link"
                      size="small"
                      onClick={() =>
                        navigate(`/apps/kuaiplm/rd-projects/detail/${detailRow.project_id}`)
                      }
                    >
                      {t('app.kuaiplm.rdDeliverables.openProject')}
                    </Button>
                  ) : (
                    t('app.kuaiplm.rdDeliverables.columns.noProject')
                  ))}
              </div>
            </div>
            <div>
              <Typography.Text type="secondary">{t('common.status')}</Typography.Text>
              <div>
                <Tag color={DELIVERABLE_STATUS_COLOR[detailRow.status || ''] ?? 'default'}>
                  {getKuaiplmDeliverableStatusText(t, detailRow.status)}
                </Tag>
              </div>
            </div>
            {detailRow.file_name ? (
              <div>
                <Typography.Text type="secondary">{t('common.file')}</Typography.Text>
                <div>{detailRow.file_name}</div>
              </div>
            ) : null}
            <RdDeliverableCapabilitiesTags capabilities={detailRow.capabilities} />
            {detailRow.issue_grants?.length ? (
              <div>
                <Typography.Text type="secondary">
                  {t('app.kuaiplm.rdDeliverables.issueTargets')}
                </Typography.Text>
                <div>
                  {detailRow.issue_grants.map((g) => g.target_label || g.target_id).join('、')}
                </div>
              </div>
            ) : null}
          </Space>
        ) : null}
      </DetailDrawerTemplate>

      <FormModalTemplate
        title={t('app.kuaiplm.rdDeliverables.issueTitle')}
        open={issueOpen}
        onClose={() => {
          setIssueOpen(false);
          setIssueTarget(null);
        }}
        formRef={issueFormRef}
        onFinish={async (values) => {
          if (!issueTarget?.id) return;
          const userIds = (values.issue_user_ids as number[] | undefined) ?? [];
          const roleUuids = (values.issue_role_uuids as string[] | undefined) ?? [];
          if (!userIds.length && !roleUuids.length) {
            messageApi.warning(t('app.kuaiplm.rdDeliverables.issueNeedTargets'));
            return;
          }
          try {
            await issueRdDeliverable(issueTarget.id, {
              user_ids: userIds,
              role_uuids: roleUuids,
            });
            messageApi.success(t('app.kuaiplm.rdDeliverables.issueSuccess'));
            setIssueOpen(false);
            setIssueTarget(null);
            reload();
          } catch (error) {
            messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
          }
        }}
      >
        <UniUserSelect
          name="issue_user_ids"
          label={t('app.kuaiplm.rdDeliverables.issueUsers')}
          mode="multiple"
        />
        <ProFormSelect
          name="issue_role_uuids"
          label={t('app.kuaiplm.rdDeliverables.issueRoles')}
          mode="multiple"
          showSearch
          request={async () => {
            const res = await getRoleList({ page_size: 200, is_active: true });
            return (res.items ?? []).map((r) => ({
              value: r.uuid,
              label: r.name,
            }));
          }}
        />
      </FormModalTemplate>

      <Modal
        title={t('app.kuaiplm.rdProjects.detail.deliverable.versionsTitle')}
        open={versionOpen}
        footer={null}
        onCancel={() => setVersionOpen(false)}
        destroyOnHidden
        width={820}
      >
        {!versionCanDownload ? (
          <Typography.Paragraph type="secondary">
            {t('app.kuaiplm.rdProjects.detail.deliverable.historyDownloadDenied')}
          </Typography.Paragraph>
        ) : null}
        <Spin spinning={versionLoading}>
          <Table
            rowKey="id"
            size="small"
            pagination={false}
            dataSource={versionRows}
            columns={[
              { title: t('app.kuaiplm.rdProjects.detail.deliverable.version'), dataIndex: 'version' },
              { title: t('common.status'), dataIndex: 'status' },
              { title: t('common.name'), dataIndex: 'name', ellipsis: true },
              { title: t('common.file'), dataIndex: 'file_name', ellipsis: true },
            ]}
          />
        </Spin>
      </Modal>

      <FormModalTemplate
        title={t('app.kuaiplm.rdProjects.detail.deliverable.reviseTitle')}
        open={reviseOpen}
        onClose={() => {
          setReviseOpen(false);
          setReviseTarget(null);
        }}
        formRef={reviseFormRef}
        onFinish={async (values) => {
          if (!reviseTarget?.id) return;
          try {
            await reviseRdDeliverable(reviseTarget.id, {
              change_summary: values.change_summary,
              file_uuid: values.file_uuid,
              file_name: values.file_name,
            });
            messageApi.success(t('app.kuaiplm.rdProjects.detail.deliverable.reviseSuccess'));
            setReviseOpen(false);
            actionRef.current?.reload();
          } catch (error) {
            messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
          }
        }}
      >
        <ProFormTextArea
          name="change_summary"
          label={t('app.kuaiplm.rdProjects.detail.deliverable.changeSummary')}
        />
      </FormModalTemplate>
    </ListPageTemplate>
  );
};

export default RdDeliverablesPage;
