/**
 * 交付节点子任务操作（完成 / 会签确认，类似报工）
 */

import React, { useEffect, useMemo, useState } from 'react';
import { App, Button, InputNumber, Modal, Select } from 'antd';
import { ProForm } from '@ant-design/pro-components';
import { useTranslation } from 'react-i18next';
import DocumentAttachmentsField from '../../../components/DocumentAttachmentsField';
import {
  mapAttachmentsToUploadList,
  normalizeDocumentAttachments,
} from '../../../utils/documentAttachments';
import DeliveryNodeTaskParticipantPanel from './DeliveryNodeTaskParticipantPanel';
import {
  DELIVERY_KIT_STATUS,
  deliveryProjectApi,
  type DeliveryProjectNodeTask,
} from '../../../services/delivery-project';

interface DeliveryNodeTaskOperateModalProps {
  open: boolean;
  projectId: number;
  task: DeliveryProjectNodeTask | null;
  currentUserId?: number;
  canAct: boolean;
  onClose: () => void;
  onUpdated: () => void | Promise<void>;
}

const DeliveryNodeTaskOperateModal: React.FC<DeliveryNodeTaskOperateModalProps> = ({
  open,
  projectId,
  task,
  currentUserId,
  canAct,
  onClose,
  onUpdated,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [form] = ProForm.useForm();
  const [submitting, setSubmitting] = useState(false);

  const participantMode = task?.participant_mode ?? 'solo';
  const isCollaborative = participantMode !== 'solo';
  const trackMode = task?.track_mode ?? 'progress';

  const myPendingAction = useMemo(() => {
    if (!task || !isCollaborative) return false;
    const action = (task.participant_actions ?? []).find((item) => item.user_id === currentUserId);
    return Boolean(action && action.status === 'pending');
  }, [task, isCollaborative, currentUserId]);

  useEffect(() => {
    if (!open || !task || isCollaborative) {
      form.resetFields();
      return;
    }
    form.setFieldsValue({
      progress_percent: Number(task.progress_percent ?? 100) || 100,
      kit_status: task.kit_status === 'ready' || task.kit_status === 'na' ? task.kit_status : 'ready',
      attachments: mapAttachmentsToUploadList(task.attachments),
    });
  }, [open, task, isCollaborative, form]);

  const submitSolo = async () => {
    if (!task) return;
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      const attachments = normalizeDocumentAttachments(values.attachments);
      if (trackMode === 'kit') {
        await deliveryProjectApi.updateNodeTask(projectId, task.id, {
          kit_status: values.kit_status as string,
          attachments,
        });
      } else {
        await deliveryProjectApi.updateNodeTask(projectId, task.id, {
          status: 'done',
          progress_percent: values.progress_percent as number,
          attachments,
        });
      }
      message.success(t('app.kuaizhizao.deliveryProject.nodeTaskOperateSuccess'));
      onClose();
      await onUpdated();
    } catch (e: unknown) {
      message.error((e as Error)?.message ?? t('common.operationFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const taskDone = task?.status === 'done' || task?.status === 'cancelled';

  return (
    <Modal
      title={
        task
          ? `${t('app.kuaizhizao.deliveryProject.nodeTaskOperate')}${task.task_name ? ` - ${task.task_name}` : ''}`
          : t('app.kuaizhizao.deliveryProject.nodeTaskOperate')
      }
      open={open}
      onCancel={onClose}
      onOk={isCollaborative ? undefined : () => void submitSolo()}
      okButtonProps={{
        loading: submitting,
        disabled: !canAct || taskDone,
      }}
      cancelButtonProps={{ disabled: submitting }}
      footer={
        isCollaborative
          ? [
              <Button key="close" onClick={onClose}>
                {t('common.close')}
              </Button>,
            ]
          : undefined
      }
      destroyOnHidden
    >
      {!task ? null : isCollaborative ? (
        <DeliveryNodeTaskParticipantPanel
          projectId={projectId}
          task={task}
          currentUserId={currentUserId}
          canAct={canAct && myPendingAction}
          onUpdated={async () => {
            await onUpdated();
            onClose();
          }}
        />
      ) : (
        <ProForm form={form} layout="vertical" submitter={false}>
          {trackMode === 'kit' ? (
            <ProForm.Item
              name="kit_status"
              label={t('app.kuaizhizao.deliveryProject.fields.kitStatus')}
              rules={[{ required: true }]}
            >
              <Select
                options={Object.entries(DELIVERY_KIT_STATUS)
                  .filter(([value]) => value === 'ready' || value === 'na')
                  .map(([value, label]) => ({ value, label }))}
              />
            </ProForm.Item>
          ) : (
            <ProForm.Item
              name="progress_percent"
              label={t('app.kuaizhizao.deliveryProject.fields.progress')}
              rules={[{ required: true }]}
            >
              <InputNumber min={0} max={100} style={{ width: '100%' }} suffix="%" />
            </ProForm.Item>
          )}
          <DocumentAttachmentsField category="delivery_node_task_attachments" />
        </ProForm>
      )}
    </Modal>
  );
};

export default DeliveryNodeTaskOperateModal;
