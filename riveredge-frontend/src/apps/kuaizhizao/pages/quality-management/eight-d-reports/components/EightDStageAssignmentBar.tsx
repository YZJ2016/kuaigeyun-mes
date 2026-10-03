import React, { useMemo, useState } from 'react';
import { App, Button, DatePicker, Input, Modal, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { MarkerTag } from '../../../../../../constants/statusBadges';
import { UniUserSelect } from '../../../../../../components/uni-user-select';
import {
  qualityImprovementApi,
  type Quality8DReport,
  type Quality8DStageAssignment,
} from '../../../../services/quality-improvement';
import { getEightDStatusText } from './eightDMeta';
import { hasModulePermission } from '../../../../../../utils/permissionContract';
import { useCurrentUser } from '../../../../../../hooks/useCurrentUser';

const RESOURCE = 'kuaizhizao:quality-management-eight-d-reports';

const STATUS_MARKER: Record<string, 'default' | 'processing' | 'success' | 'warning'> = {
  pending: 'default',
  in_progress: 'processing',
  submitted: 'warning',
  approved: 'success',
};

type Props = {
  report: Quality8DReport;
  activeStageKey: string;
  assignment?: Quality8DStageAssignment;
  onReload: () => Promise<void>;
};

export const EightDStageAssignmentBar: React.FC<Props> = ({
  report,
  activeStageKey,
  assignment,
  onReload,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const currentUser = useCurrentUser();
  const canAssign = hasModulePermission(currentUser ?? undefined, RESOURCE, 'assign');
  const canSubmit = hasModulePermission(currentUser ?? undefined, RESOURCE, 'submit');
  const canApprove = hasModulePermission(currentUser ?? undefined, RESOURCE, 'approve');

  const isCollaborative = report.coordination_mode === 'collaborative';
  const isChampion =
    (report.owner_id && currentUser?.id === report.owner_id) ||
    (!report.owner_id && report.created_by && currentUser?.id === report.created_by);

  const [assigneeId, setAssigneeId] = useState<number | undefined>(
    assignment?.assignee_user_id ?? undefined,
  );
  const [dueDate, setDueDate] = useState(
    assignment?.due_date ? dayjs(assignment.due_date) : undefined,
  );
  const [saving, setSaving] = useState(false);
  const [acting, setActing] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const status = assignment?.status ?? 'pending';
  const isStageOwner = assignment?.assignee_user_id === currentUser?.id;

  const statusLabel = useMemo(() => {
    const key = `app.kuaizhizao.eightD.collab.stageStatus.${status}`;
    const text = t(key);
    return text === key ? status : text;
  }, [status, t]);

  if (!isCollaborative || report.status === 'closed') {
    return null;
  }

  const saveAssignment = async () => {
    if (!report.id) return;
    setSaving(true);
    try {
      await qualityImprovementApi.eightD.upsertStageAssignments(report.id, [
        {
          stage_key: activeStageKey,
          assignee_user_id: assigneeId ?? null,
          due_date: dueDate ? dueDate.format('YYYY-MM-DD HH:mm:ss') : null,
        },
      ]);
      messageApi.success(t('app.kuaizhizao.eightD.collab.assignSaved'));
      await onReload();
    } catch (err: unknown) {
      messageApi.error((err as Error)?.message || t('common.saveFailed'));
    } finally {
      setSaving(false);
    }
  };

  const runStageAction = async (action: 'submit' | 'approve' | 'reject') => {
    if (!report.id) return;
    if (action === 'reject') {
      setRejectReason('');
      setRejectOpen(true);
      return;
    }
    setActing(true);
    try {
      if (action === 'submit') {
        await qualityImprovementApi.eightD.submitStage(report.id, activeStageKey);
        messageApi.success(t('app.kuaizhizao.eightD.collab.submitDone'));
      } else {
        await qualityImprovementApi.eightD.approveStage(report.id, activeStageKey);
        messageApi.success(t('app.kuaizhizao.eightD.collab.approveDone'));
      }
      await onReload();
    } catch (err: unknown) {
      messageApi.error((err as Error)?.message || t('common.operationFailed'));
    } finally {
      setActing(false);
    }
  };

  return (
    <div style={{ marginBottom: 16, padding: 12, border: '1px solid rgba(0,0,0,0.06)', borderRadius: 6 }}>
      <Space orientation="vertical" style={{ width: '100%' }} size="small">
        <Space wrap>
          <Typography.Text strong>{getEightDStatusText(t, activeStageKey)}</Typography.Text>
          <MarkerTag color={STATUS_MARKER[status] ?? 'default'}>{statusLabel}</MarkerTag>
          {assignment?.assignee_name ? (
            <Typography.Text type="secondary">
              {t('app.kuaizhizao.eightD.collab.assignee')}: {assignment.assignee_name}
            </Typography.Text>
          ) : null}
        </Space>
        {canAssign && isChampion ? (
          <Space wrap align="start">
            <UniUserSelect
              style={{ minWidth: 200 }}
              value={assigneeId}
              onChange={(v) => setAssigneeId(typeof v === 'number' ? v : undefined)}
              placeholder={t('app.kuaizhizao.eightD.collab.selectAssignee')}
            />
            <DatePicker
              showTime
              value={dueDate}
              onChange={(v) => setDueDate(v ?? undefined)}
              placeholder={t('app.kuaizhizao.eightD.collab.stageDue')}
            />
            <Button loading={saving} onClick={() => void saveAssignment()}>
              {t('app.kuaizhizao.eightD.collab.saveAssignment')}
            </Button>
          </Space>
        ) : null}
        <Space wrap>
          {canSubmit && isStageOwner && (status === 'pending' || status === 'in_progress') ? (
            <Button type="primary" loading={acting} onClick={() => void runStageAction('submit')}>
              {t('app.kuaizhizao.eightD.collab.submitStage')}
            </Button>
          ) : null}
          {canApprove && isChampion && status === 'submitted' ? (
            <>
              <Button type="primary" loading={acting} onClick={() => void runStageAction('approve')}>
                {t('app.kuaizhizao.eightD.collab.approveStage')}
              </Button>
              <Button danger loading={acting} onClick={() => void runStageAction('reject')}>
                {t('app.kuaizhizao.eightD.collab.rejectStage')}
              </Button>
            </>
          ) : null}
        </Space>
      </Space>
      <Modal
        title={t('app.kuaizhizao.eightD.collab.rejectStageTitle')}
        open={rejectOpen}
        confirmLoading={acting}
        onCancel={() => setRejectOpen(false)}
        onOk={async () => {
          const reason = rejectReason.trim();
          if (!reason) {
            messageApi.warning(t('app.kuaizhizao.eightD.collab.rejectReasonRequired'));
            return;
          }
          if (!report.id) return;
          setActing(true);
          try {
            await qualityImprovementApi.eightD.rejectStage(report.id, activeStageKey, reason);
            messageApi.success(t('app.kuaizhizao.eightD.collab.rejectDone'));
            setRejectOpen(false);
            await onReload();
          } catch (err: unknown) {
            messageApi.error((err as Error)?.message || t('common.operationFailed'));
          } finally {
            setActing(false);
          }
        }}
      >
        <Input.TextArea
          rows={3}
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder={t('app.kuaizhizao.eightD.collab.rejectReason')}
        />
      </Modal>
    </div>
  );
};
