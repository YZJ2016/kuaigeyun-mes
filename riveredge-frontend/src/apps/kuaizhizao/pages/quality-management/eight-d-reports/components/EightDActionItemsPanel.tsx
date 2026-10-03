import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ProFormInstance } from '@ant-design/pro-components';
import { App, Button, Form, Input, Space, Table } from 'antd';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { MarkerTag } from '../../../../../../constants/statusBadges';
import { FormModalTemplate } from '../../../../../../components/layout-templates';
import { UniUserSelect } from '../../../../../../components/uni-user-select';
import DocumentAttachmentsField from '../../../../components/DocumentAttachmentsField';
import {
  qualityImprovementApi,
  type Quality8DActionItem,
  type Quality8DReport,
} from '../../../../services/quality-improvement';
import { mapAttachmentsToUploadList, normalizeDocumentAttachments } from '../../../../utils/documentAttachments';
import { hasModulePermission } from '../../../../../../utils/permissionContract';
import { useCurrentUser } from '../../../../../../hooks/useCurrentUser';

const RESOURCE = 'kuaizhizao:quality-management-eight-d-reports';

const STAGE_DISCIPLINE: Record<string, string> = {
  d3_containment: 'd3_containment',
  d5_corrective_action: 'd5_corrective',
  d6_implement_result: 'd6_verification',
};

const STATUS_COLOR: Record<string, 'default' | 'processing' | 'success' | 'warning'> = {
  open: 'processing',
  done: 'warning',
  verified: 'success',
  cancelled: 'default',
};

type Props = {
  report: Quality8DReport;
  activeStageKey: string;
  onReload: () => Promise<void>;
};

export const EightDActionItemsPanel: React.FC<Props> = ({ report, activeStageKey, onReload }) => {
  const discipline = STAGE_DISCIPLINE[activeStageKey];
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const currentUser = useCurrentUser();
  const canAssign = hasModulePermission(currentUser ?? undefined, RESOURCE, 'assign');
  const canSubmit = hasModulePermission(currentUser ?? undefined, RESOURCE, 'submit');
  const canApprove = hasModulePermission(currentUser ?? undefined, RESOURCE, 'approve');
  const canUpdate = hasModulePermission(currentUser ?? undefined, RESOURCE, 'update');

  const [rows, setRows] = useState<Quality8DActionItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Quality8DActionItem | null>(null);
  const formRef = useRef<ProFormInstance>();

  const isCollaborative = report.coordination_mode === 'collaborative';

  const loadItems = useCallback(async () => {
    if (!report.id || !discipline) {
      setRows([]);
      return;
    }
    setLoading(true);
    try {
      const items = await qualityImprovementApi.eightD.listActionItems(report.id, discipline);
      setRows(items || []);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [discipline, report.id]);

  useEffect(() => {
    void loadItems();
  }, [loadItems]);

  const openCreate = () => {
    setEditing(null);
    formRef.current?.resetFields();
    setModalOpen(true);
  };

  const openEdit = (row: Quality8DActionItem) => {
    setEditing(row);
    setModalOpen(true);
  };

  const modalInitialValues = editing
    ? {
        ...editing,
        due_date: editing.due_date ? dayjs(editing.due_date) : undefined,
        evidence_attachments: mapAttachmentsToUploadList(editing.evidence_attachments),
      }
    : undefined;

  const handleSave = async (values: Record<string, unknown>) => {
    if (!report.id || !discipline) return;
    const payload = {
      discipline,
      title: String(values.title ?? ''),
      description: values.description ? String(values.description) : undefined,
      assignee_user_id: values.assignee_user_id as number | undefined,
      due_date:
        values.due_date && dayjs.isDayjs(values.due_date)
          ? values.due_date.format('YYYY-MM-DD HH:mm:ss')
          : undefined,
      evidence_attachments: normalizeDocumentAttachments(values.evidence_attachments),
    };
    if (editing?.id) {
      await qualityImprovementApi.eightD.updateActionItem(report.id, editing.id, payload);
    } else {
      await qualityImprovementApi.eightD.createActionItem(report.id, payload);
    }
    messageApi.success(t('common.saveSuccess'));
    setModalOpen(false);
    await loadItems();
    await onReload();
  };

  const columns = useMemo(
    () => [
      { title: t('app.kuaizhizao.eightD.collab.actionTitle'), dataIndex: 'title', ellipsis: true },
      {
        title: t('app.kuaizhizao.eightD.collab.actionAssignee'),
        dataIndex: 'assignee_name',
        width: 100,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.eightD.collab.actionStatus'),
        dataIndex: 'status',
        width: 88,
        render: (s: string) => {
          const key = `app.kuaizhizao.eightD.collab.actionStatus.${s}`;
          const label = t(key);
          return <MarkerTag color={STATUS_COLOR[s] ?? 'default'}>{label === key ? s : label}</MarkerTag>;
        },
      },
      {
        title: t('common.actions'),
        key: 'actions',
        width: 200,
        render: (_: unknown, row: Quality8DActionItem) => (
          <Space size="small" wrap>
            {(canUpdate || canAssign) && row.status === 'open' ? (
              <Button type="link" size="small" onClick={() => openEdit(row)}>
                {t('common.edit')}
              </Button>
            ) : null}
            {canSubmit && row.assignee_user_id === currentUser?.id && row.status === 'open' ? (
              <Button
                type="link"
                size="small"
                onClick={async () => {
                  await qualityImprovementApi.eightD.completeActionItem(report.id!, row.id);
                  messageApi.success(t('app.kuaizhizao.eightD.collab.actionCompleteDone'));
                  await loadItems();
                  await onReload();
                }}
              >
                {t('app.kuaizhizao.eightD.collab.actionComplete')}
              </Button>
            ) : null}
            {canApprove && row.status === 'done' ? (
              <Button
                type="link"
                size="small"
                onClick={async () => {
                  await qualityImprovementApi.eightD.verifyActionItem(report.id!, row.id);
                  messageApi.success(t('app.kuaizhizao.eightD.collab.actionVerifyDone'));
                  await loadItems();
                  await onReload();
                }}
              >
                {t('app.kuaizhizao.eightD.collab.actionVerify')}
              </Button>
            ) : null}
            {canAssign ? (
              <Button
                type="link"
                size="small"
                danger
                onClick={async () => {
                  await qualityImprovementApi.eightD.deleteActionItem(report.id!, row.id);
                  messageApi.success(t('common.deleteSuccess'));
                  await loadItems();
                  await onReload();
                }}
              >
                {t('common.delete')}
              </Button>
            ) : null}
          </Space>
        ),
      },
    ],
    [canApprove, canAssign, canSubmit, canUpdate, currentUser?.id, loadItems, messageApi, onReload, report.id, t],
  );

  if (!isCollaborative || !discipline || report.status === 'closed') {
    return null;
  }

  return (
    <>
      <div style={{ marginBottom: 16 }}>
        <Space style={{ marginBottom: 8 }}>
          <span>{t('app.kuaizhizao.eightD.collab.actionSection')}</span>
          {canUpdate || canAssign ? (
            <Button type="primary" size="small" onClick={openCreate}>
              {t('app.kuaizhizao.eightD.collab.createActionItem')}
            </Button>
          ) : null}
        </Space>
        <Table<Quality8DActionItem>
          size="small"
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={false}
        />
      </div>
      <FormModalTemplate
        key={editing?.id ?? 'new-action-item'}
        title={
          editing
            ? t('app.kuaizhizao.eightD.collab.editActionItem')
            : t('app.kuaizhizao.eightD.collab.createActionItem')
        }
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        formRef={formRef}
        initialValues={modalInitialValues}
        onFinish={handleSave}
        grid
      >
        <Form.Item name="title" label={t('app.kuaizhizao.eightD.collab.actionTitle')} rules={[{ required: true }]}>
          <Input />
        </Form.Item>
        <Form.Item name="assignee_user_id" label={t('app.kuaizhizao.eightD.collab.actionAssignee')}>
          <UniUserSelect />
        </Form.Item>
        <Form.Item name="description" label={t('common.description')} colProps={{ span: 24 }}>
          <Input.TextArea rows={3} />
        </Form.Item>
        <Form.Item name="evidence_attachments" label={t('common.attachments')} colProps={{ span: 24 }}>
          <DocumentAttachmentsField category="quality_8d_report_attachments" />
        </Form.Item>
      </FormModalTemplate>
    </>
  );
};
