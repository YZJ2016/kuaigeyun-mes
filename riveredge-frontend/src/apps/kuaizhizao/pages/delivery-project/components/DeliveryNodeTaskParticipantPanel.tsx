/**
 * 交付节点子任务：关联人员操作（会签 / 或签 / 分人操作）
 */

import React, { useMemo, useState } from 'react';
import { App, Button, Flex, Input, InputNumber, Select, Typography } from 'antd';
import { CheckOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { MarkerTag } from '../../../../../constants/statusBadges';
import {
  DELIVERY_KIT_STATUS,
  DELIVERY_TASK_PARTICIPANT_ACTION_STATUS,
  deliveryProjectApi,
  type DeliveryProjectNodeTask,
} from '../../../services/delivery-project';

interface DeliveryNodeTaskParticipantPanelProps {
  projectId: number;
  task: DeliveryProjectNodeTask;
  currentUserId?: number;
  canAct: boolean;
  onUpdated: () => void | Promise<void>;
}

const DeliveryNodeTaskParticipantPanel: React.FC<DeliveryNodeTaskParticipantPanelProps> = ({
  projectId,
  task,
  currentUserId,
  canAct,
  onUpdated,
}) => {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [remark, setRemark] = useState('');
  const [kitStatus, setKitStatus] = useState<string>('ready');
  const [progressPercent, setProgressPercent] = useState<number>(100);
  const [submitting, setSubmitting] = useState(false);

  const participantMode = task.participant_mode ?? 'solo';
  const actions = task.participant_actions ?? [];
  const myAction = useMemo(
    () => actions.find((item) => item.user_id === currentUserId),
    [actions, currentUserId],
  );

  if (participantMode === 'solo' || actions.length === 0) {
    return null;
  }

  const doneCount = actions.filter((item) => item.status === 'done').length;
  const actionType = myAction?.action ?? 'signoff';

  const submit = async () => {
    if (!myAction || myAction.status === 'done') {
      return;
    }
    setSubmitting(true);
    try {
      const payload: { remark?: string; kit_status?: string; progress_percent?: number } = {};
      if (remark.trim()) {
        payload.remark = remark.trim();
      }
      if (actionType === 'kit') {
        payload.kit_status = kitStatus;
      } else if (actionType === 'progress') {
        payload.progress_percent = progressPercent;
      }
      await deliveryProjectApi.submitNodeTaskParticipantAction(projectId, task.id, payload);
      message.success(t('app.kuaizhizao.deliveryProject.participantActionSuccess'));
      setRemark('');
      await onUpdated();
    } catch (e: unknown) {
      message.error((e as Error)?.message ?? t('common.operationFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ padding: '8px 0 0' }}>
      <Flex justify="space-between" align="center" wrap="wrap" gap={8} style={{ marginBottom: 8 }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {t('app.kuaizhizao.deliveryProject.participantProgress', {
            done: doneCount,
            total: actions.length,
          })}
        </Typography.Text>
        {myAction && myAction.status === 'pending' && canAct ? (
          <Flex gap={8} wrap="wrap" align="center">
            {actionType === 'kit' ? (
              <Select
                size="small"
                style={{ width: 96 }}
                value={kitStatus}
                options={Object.entries(DELIVERY_KIT_STATUS).map(([value, label]) => ({
                  value,
                  label,
                }))}
                onChange={setKitStatus}
              />
            ) : null}
            {actionType === 'progress' ? (
              <InputNumber
                size="small"
                min={0}
                max={100}
                value={progressPercent}
                onChange={(val) => setProgressPercent(Number(val ?? 0))}
              />
            ) : null}
            <Input
              size="small"
              style={{ width: 160 }}
              placeholder={t('app.kuaizhizao.deliveryProject.participantRemarkPlaceholder')}
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
            />
            <Button
              type="primary"
              size="small"
              icon={<CheckOutlined />}
              loading={submitting}
              onClick={() => void submit()}
            >
              {t('app.kuaizhizao.deliveryProject.participantConfirm')}
            </Button>
          </Flex>
        ) : null}
      </Flex>
      <Flex gap={6} wrap="wrap">
        {actions.map((item) => (
          <MarkerTag
            key={item.user_id}
            variant="filled"
            color={item.status === 'done' ? 'success' : 'default'}
          >
            {item.user_name} {DELIVERY_TASK_PARTICIPANT_ACTION_STATUS[item.status] ?? item.status}
          </MarkerTag>
        ))}
      </Flex>
    </div>
  );
};

export default DeliveryNodeTaskParticipantPanel;
