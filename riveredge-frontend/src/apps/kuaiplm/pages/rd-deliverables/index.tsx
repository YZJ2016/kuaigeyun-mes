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
import {
  App,
  Button,
  Modal,
  Result,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
} from 'antd';
import { ActionConfirmPopconfirm } from '../../../../components/action-confirm';
import { UniTable } from '../../../../components/uni-table';
import {
  DetailDrawerTemplate,
  FormModalTemplate,
  ListPageTemplate,
} from '../../../../components/layout-templates';
import { useResourcePermissions } from '../../../../hooks/useResourcePermissions';
import { getApiErrorMessage } from '../../../../utils/errorHandler';
import { uploadFile } from '../../../../services/file';
import {
  extractUploadFileUuids,
  normalizeUploadFileList,
} from '../../../../components/custom-fields/customFieldFileUtils';
import { renderDocumentStatusTag } from '../../../../utils/documentLifecycleStatusTag';
import { NEW_SHORTCUT_HINT } from '../../../../utils/globalNewShortcut';
import { ThemedSegmented } from '../../../../components/themed-segmented';
import Phase2ProjectSelect from '../../components/Phase2ProjectSelect';
import { RdDeliverableTypeFormFields } from '../../components/RdDeliverableTypeFormFields';
import { getKuaiplmDeliverableStatusText } from '../../components/kuaiplmMeta';
import {
  needsMaterialCode,
  needsProjectCodeWithoutProject,
} from '../../utils/rdDeliverableTypes';
import type { RdProjectDeliverable } from '../../services/rd-project';
import {
  createRdDeliverable,
  deleteRdDeliverable,
  listRdDeliverableVersions,
  listRdDeliverables,
  reviseRdDeliverable,
  submitRdDeliverable,
  updateRdDeliverable,
} from '../../services/rd-deliverable';

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
  const perms = useResourcePermissions(RESOURCE);
  const canWrite =
    perms.canCreate || perms.canUpdate || Boolean(perms.canAction?.('upload-part-spec'));

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

  const scopeFilter = (searchParams.get('scope') as ScopeFilter) || 'all';

  const deliverableTypeOptions = useMemo(
    () => [
      { value: 'part_spec', label: t('app.kuaiplm.rdProjects.detail.deliverable.type.partSpec') },
      {
        value: 'software_spec',
        label: t('app.kuaiplm.rdProjects.detail.deliverable.type.softwareSpec'),
      },
      { value: 'schematic', label: t('app.kuaiplm.rdProjects.detail.deliverable.type.schematic') },
      { value: 'layout', label: t('app.kuaiplm.rdProjects.detail.deliverable.type.layout') },
      { value: 'gerber', label: t('app.kuaiplm.rdProjects.detail.deliverable.type.gerber') },
      {
        value: 'panelization',
        label: t('app.kuaiplm.rdProjects.detail.deliverable.type.panelization'),
      },
      {
        value: 'test_report_part',
        label: t('app.kuaiplm.rdProjects.detail.deliverable.type.testReportPart'),
      },
      {
        value: 'test_report_complete',
        label: t('app.kuaiplm.rdProjects.detail.deliverable.type.testReportComplete'),
      },
      {
        value: 'customer_spec',
        label: t('app.kuaiplm.rdProjects.detail.deliverable.type.customerSpec'),
      },
      {
        value: 'customer_approval',
        label: t('app.kuaiplm.rdProjects.detail.deliverable.type.customerApproval'),
      },
    ],
    [t],
  );

  const typeLabel = useCallback(
    (v?: string | null) => deliverableTypeOptions.find((o) => o.value === v)?.label || v || '—',
    [deliverableTypeOptions],
  );

  const columns = useMemo<ProColumns<RdProjectDeliverable>[]>(
    () => [
      {
        title: t('common.name'),
        dataIndex: 'name',
        ellipsis: true,
        width: 200,
      },
      {
        title: t('app.kuaiplm.common.columns.type'),
        dataIndex: 'deliverable_type',
        width: 140,
        render: (_, row) => typeLabel(row.deliverable_type),
      },
      {
        title: t('app.kuaiplm.rdDeliverables.columns.projectCode'),
        dataIndex: 'project_code',
        width: 120,
        render: (_, row) =>
          row.project_code?.trim() ||
          (row.project_id
            ? t('app.kuaiplm.rdDeliverables.columns.projectLinked')
            : t('app.kuaiplm.rdDeliverables.columns.noProject')),
      },
      {
        title: t('app.kuaiplm.rdProjects.detail.deliverable.catalogCode'),
        dataIndex: 'material_code',
        width: 120,
        ellipsis: true,
        render: (v) => v || '—',
      },
      {
        title: t('app.kuaiplm.rdProjects.detail.deliverable.version'),
        dataIndex: 'version',
        width: 72,
      },
      {
        title: t('common.status'),
        dataIndex: 'status',
        width: 100,
        render: (_, row) =>
          renderDocumentStatusTag(getKuaiplmDeliverableStatusText(t, row.status), row.status),
      },
      {
        title: t('common.actions'),
        key: 'actions',
        width: 220,
        fixed: 'right',
        render: (_, row) => (
          <Space size={4} wrap={false} onClick={(e) => e.stopPropagation()}>
            {canWrite ? (
              <Button type="link" size="small" onClick={() => openEdit(row)}>
                {t('common.edit')}
              </Button>
            ) : null}
            <Button
              type="link"
              size="small"
              onClick={async () => {
                setVersionOpen(true);
                setVersionLoading(true);
                try {
                  const res = await listRdDeliverableVersions(row.id!);
                  setVersionRows(res.items || []);
                  setVersionCanDownload(Boolean(res.can_download_history));
                } catch (error) {
                  messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
                } finally {
                  setVersionLoading(false);
                }
              }}
            >
              {t('app.kuaiplm.rdProjects.detail.deliverable.versions')}
            </Button>
            {canWrite && row.status === 'PENDING' ? (
              <Button
                type="link"
                size="small"
                onClick={async () => {
                  try {
                    await submitRdDeliverable(row.id!);
                    messageApi.success(
                      t('app.kuaiplm.rdProjects.detail.deliverable.submitSuccess'),
                    );
                    actionRef.current?.reload();
                  } catch (error) {
                    messageApi.error(getApiErrorMessage(error, t('common.operationFailed')));
                  }
                }}
              >
                {t('app.kuaiplm.common.deliverableStatus.submitted')}
              </Button>
            ) : null}
          </Space>
        ),
      },
    ],
    [t, typeLabel, canWrite, messageApi],
  );

  const openCreate = () => {
    setEditing(null);
    setModalOpen(true);
  };

  const openEdit = (row: RdProjectDeliverable) => {
    setEditing(row);
    setModalOpen(true);
  };

  const buildPayload = (values: Record<string, unknown>) => {
    const formUpload = formRef.current?.getFieldValue?.('file_upload');
    const uploadList = normalizeUploadFileList(formUpload ?? values.file_upload);
    const uploadedUuids = extractUploadFileUuids(uploadList);
    const fileUuid =
      uploadedUuids[0] ||
      String(formRef.current?.getFieldValue?.('file_uuid') ?? values.file_uuid ?? '').trim() ||
      undefined;
    const fileName =
      String(formRef.current?.getFieldValue?.('file_name') ?? values.file_name ?? '').trim() ||
      (uploadList[0]?.name as string | undefined) ||
      undefined;
    const dtype = String(values.deliverable_type || '').trim() || undefined;
    const projectIdRaw = values.project_id;
    const projectId =
      projectIdRaw != null && projectIdRaw !== ''
        ? Number(projectIdRaw)
        : editing?.project_id ?? undefined;
    return {
      name: String(values.name || '').trim(),
      deliverable_type: dtype,
      status: values.status || 'PENDING',
      description: values.description ? String(values.description) : undefined,
      file_uuid: fileUuid,
      file_name: fileName,
      material_code: needsMaterialCode(dtype)
        ? String(values.material_code || '').trim() || undefined
        : values.material_code
          ? String(values.material_code).trim() || undefined
          : undefined,
      legacy_material_code: values.legacy_material_code
        ? String(values.legacy_material_code).trim() || undefined
        : undefined,
      project_id: projectId ?? null,
      project_code:
        !projectId && values.project_code
          ? String(values.project_code).trim() || undefined
          : undefined,
    };
  };

  if (!perms.canRead) {
    return (
      <ListPageTemplate title={t('app.kuaiplm.menu.rd-deliverables')}>
        <Result status="403" title={t('common.noPermission')} />
      </ListPageTemplate>
    );
  }

  return (
    <ListPageTemplate title={t('app.kuaiplm.menu.rd-deliverables')}>
      <UniTable<RdProjectDeliverable>
        actionRef={actionRef}
        columnPersistenceId="apps.kuaiplm.pages.rd-deliverables.v1"
        rowKey="id"
        columns={columns}
        createButtonText={t('app.kuaiplm.rdDeliverables.createButton')}
        toolBarRender={() => [
          <ThemedSegmented
            key="scope"
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
          />,
        ]}
        onCreate={canWrite ? openCreate : undefined}
        newShortcutHint={NEW_SHORTCUT_HINT}
        request={async (params) => {
          const keyword = String(params.keyword || params.name || '').trim() || undefined;
          const res = await listRdDeliverables({
            skip: ((params.current || 1) - 1) * (params.pageSize || 20),
            limit: params.pageSize || 20,
            keyword,
            deliverable_type: params.deliverable_type as string | undefined,
            unlinked_only: scopeFilter === 'unlinked',
            linked_only: scopeFilter === 'linked',
          });
          return { data: res.items || [], success: true, total: res.total };
        }}
        onRow={(row) => ({
          onClick: () => {
            setDetailRow(row);
            setDetailOpen(true);
          },
        })}
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
          const payload = buildPayload(values);
          const dtype = payload.deliverable_type;
          if (needsMaterialCode(dtype) && !payload.material_code) {
            messageApi.error(t('app.kuaiplm.rdProjects.detail.deliverable.materialCodeRequired'));
            return;
          }
          if (
            needsProjectCodeWithoutProject(dtype, payload.project_id ?? undefined) &&
            !payload.project_code
          ) {
            messageApi.error(t('app.kuaiplm.rdDeliverables.form.projectCodeRequired'));
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
          </Space>
        ) : null}
      </DetailDrawerTemplate>

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
