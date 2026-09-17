import React from 'react';
import type { TFunction } from 'i18next';
import type { ColumnsType } from 'antd/es/table';
import { Button, Popconfirm, Space, Typography } from 'antd';
import { PaperClipOutlined } from '@ant-design/icons';
import { UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS } from '../../../../../utils/uniTableLayoutColumns';
import { DOCUMENT_PROGRESS_COLUMN_DEFAULTS } from '../../sales-management/shared/DocumentPushProgressBar';
import {
  DELIVERY_NODE_REPORT_STATUS,
  DELIVERY_NODE_TASK_STATUS,
  DELIVERY_TASK_PARTICIPANT_MODE,
  type DeliveryIssue,
  type DeliveryMember,
  type DeliveryNodeReport,
  type DeliveryProjectNode,
  type DeliveryProjectNodeTask,
} from '../../../services/delivery-project';
import { renderDeliveryIssuePriorityTag, renderDeliveryStatusTag } from './deliveryListPresentation';
import { formatBusinessDateOnly } from '../../../../../utils/format';
import { workbenchKeepWidth, workbenchRemainderFlex } from './deliveryWorkbenchTableLayout';

type NodeTaskColumnOptions = {
  t: TFunction;
  canUpdate: boolean;
  canParticipantAct: boolean;
  onEdit: (task: DeliveryProjectNodeTask) => void;
  onOperate: (task: DeliveryProjectNodeTask) => void;
  onDelete: (task: DeliveryProjectNodeTask) => void;
};

export function buildWorkbenchNodeTaskColumns({
  t,
  canUpdate,
  canParticipantAct,
  onEdit,
  onOperate,
  onDelete,
}: NodeTaskColumnOptions): ColumnsType<DeliveryProjectNodeTask> {
  return [
    {
      title: t('app.kuaizhizao.deliveryProject.fields.taskName'),
      dataIndex: 'task_name',
      key: 'task_name',
      ...workbenchKeepWidth(88),
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.coreTask'),
      dataIndex: 'core_task',
      key: 'core_task',
      ...workbenchRemainderFlex(120),
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.ownerName'),
      dataIndex: 'owner_name',
      key: 'owner_name',
      ...workbenchKeepWidth(80),
      render: (v) => v || '—',
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.members'),
      dataIndex: 'members',
      key: 'members',
      ...workbenchKeepWidth(160),
      ellipsis: { showTitle: false },
      render: (members: DeliveryMember[] | undefined) => {
        const text = members?.length
          ? members.map((m) => m.user_name || String(m.user_id)).join('、')
          : '—';
        if (text === '—') return text;
        return (
          <Typography.Text ellipsis={{ tooltip: text }} style={{ maxWidth: '100%' }}>
            {text}
          </Typography.Text>
        );
      },
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.plannedEndDate'),
      dataIndex: 'planned_end_date',
      key: 'planned_end_date',
      ...workbenchKeepWidth(96),
      render: (v) => formatBusinessDateOnly(v) || '—',
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.participantMode'),
      dataIndex: 'participant_mode',
      key: 'participant_mode',
      ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
      render: (v) => DELIVERY_TASK_PARTICIPANT_MODE[String(v || 'solo')] ?? String(v),
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.status'),
      dataIndex: 'status',
      key: 'lifecycle',
      fixed: 'right',
      render: (v, task) =>
        task.participant_mode && task.participant_mode !== 'solo' ? (
          <Typography.Text style={{ fontSize: 12 }}>
            {t('app.kuaizhizao.deliveryProject.participantProgressShort', {
              done: (task.participant_actions ?? []).filter((a) => a.status === 'done').length,
              total: (task.participant_actions ?? []).length,
            })}
          </Typography.Text>
        ) : (
          renderDeliveryStatusTag(String(v), DELIVERY_NODE_TASK_STATUS)
        ),
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.taskAttachments'),
      dataIndex: 'attachments',
      key: 'attachments',
      align: 'center',
      ...workbenchKeepWidth(56),
      render: (attachments: DeliveryProjectNodeTask['attachments']) => {
        const count = attachments?.length ?? 0;
        if (count <= 0) return '—';
        const names = (attachments ?? [])
          .map((file) => file.name?.trim())
          .filter(Boolean)
          .join('、');
        return (
          <Typography.Text
            style={{ fontSize: 12 }}
            ellipsis={{ tooltip: names || t('app.kuaizhizao.deliveryProject.taskAttachmentCount', { count }) }}
          >
            <PaperClipOutlined /> {count}
          </Typography.Text>
        );
      },
    },
    ...(canUpdate || canParticipantAct
      ? [
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right' as const,
            render: (_: unknown, task: DeliveryProjectNodeTask) => {
              const taskFinished = task.status === 'done' || task.status === 'cancelled';
              return (
                <Space size={0} className="uni-table-operation-actions">
                  {canUpdate ? (
                    <Button type="link" size="small" onClick={() => onEdit(task)}>
                      {t('common.edit')}
                    </Button>
                  ) : null}
                  {canParticipantAct && !taskFinished ? (
                    <Button type="link" size="small" onClick={() => onOperate(task)}>
                      {t('app.kuaizhizao.deliveryProject.nodeTaskOperate')}
                    </Button>
                  ) : null}
                  {canUpdate ? (
                    <Popconfirm
                      title={t('app.kuaizhizao.deliveryProject.deleteNodeTaskConfirm')}
                      onConfirm={() => onDelete(task)}
                    >
                      <Button type="link" size="small" danger>
                        {t('common.delete')}
                      </Button>
                    </Popconfirm>
                  ) : null}
                </Space>
              );
            },
          },
        ]
      : []),
  ];
}

type RecentReportColumnOptions = {
  t: TFunction;
  canRead: boolean;
  canUpdate: boolean;
  canDelete: boolean;
  onView: (report: DeliveryNodeReport) => void;
  onEdit: (report: DeliveryNodeReport) => void;
  onSubmit: (report: DeliveryNodeReport) => void;
  onDelete: (report: DeliveryNodeReport) => void;
};

export function buildWorkbenchRecentReportColumns({
  t,
  canRead,
  canUpdate,
  canDelete,
  onView,
  onEdit,
  onSubmit,
  onDelete,
}: RecentReportColumnOptions): ColumnsType<DeliveryNodeReport> {
  return [
    {
      title: t('app.kuaizhizao.deliveryProject.fields.reportCode'),
      dataIndex: 'report_code',
      key: 'report_code',
      ...workbenchKeepWidth(132),
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.nodeName'),
      dataIndex: 'node_name',
      key: 'node_name',
      ...workbenchRemainderFlex(88),
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.status'),
      dataIndex: 'status',
      key: 'lifecycle',
      fixed: 'right',
      render: (v) => renderDeliveryStatusTag(v, DELIVERY_NODE_REPORT_STATUS),
    },
    ...(canRead || canUpdate || canDelete
      ? [
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right' as const,
            render: (_: unknown, report: DeliveryNodeReport) => (
              <Space size={0} className="uni-table-operation-actions">
                {canRead ? (
                  <Button type="link" size="small" onClick={() => onView(report)}>
                    {t('common.view')}
                  </Button>
                ) : null}
                {report.status === 'draft' && canUpdate ? (
                  <Button type="link" size="small" onClick={() => onEdit(report)}>
                    {t('common.edit')}
                  </Button>
                ) : null}
                {report.status === 'draft' && canUpdate ? (
                  <Button type="link" size="small" onClick={() => onSubmit(report)}>
                    {t('common.submit')}
                  </Button>
                ) : null}
                {report.status === 'draft' && canDelete ? (
                  <Popconfirm
                    title={t('app.kuaizhizao.deliveryProject.deleteReportConfirm')}
                    onConfirm={() => onDelete(report)}
                  >
                    <Button type="link" size="small" danger>
                      {t('common.delete')}
                    </Button>
                  </Popconfirm>
                ) : null}
              </Space>
            ),
          },
        ]
      : []),
  ];
}

type RecentIssueColumnOptions = {
  t: TFunction;
  canRead: boolean;
  canUpdate: boolean;
  canDelete: boolean;
  onView: (issue: DeliveryIssue) => void;
  onEdit: (issue: DeliveryIssue) => void;
  onStart: (issue: DeliveryIssue) => void;
  onResolve: (issue: DeliveryIssue) => void;
  onClose: (issue: DeliveryIssue) => void;
  onDelete: (issue: DeliveryIssue) => void;
};

export function buildWorkbenchRecentIssueColumns({
  t,
  canRead,
  canUpdate,
  canDelete,
  onView,
  onEdit,
  onStart,
  onResolve,
  onClose,
  onDelete,
}: RecentIssueColumnOptions): ColumnsType<DeliveryIssue> {
  return [
    {
      title: t('app.kuaizhizao.deliveryProject.fields.issueCode'),
      dataIndex: 'issue_code',
      key: 'issue_code',
      ...workbenchKeepWidth(132),
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.title'),
      dataIndex: 'title',
      key: 'title',
      ...workbenchRemainderFlex(120),
    },
    {
      title: t('app.kuaizhizao.deliveryProject.fields.priority'),
      dataIndex: 'priority',
      key: 'priority',
      ...UNI_TABLE_MARKER_BADGE_COLUMN_DEFAULTS,
      render: (v) => renderDeliveryIssuePriorityTag(v),
    },
    ...(canRead || canUpdate || canDelete
      ? [
          {
            title: t('common.actions'),
            key: 'action',
            fixed: 'right' as const,
            render: (_: unknown, issue: DeliveryIssue) => (
              <Space size={0} className="uni-table-operation-actions">
                {canRead ? (
                  <Button type="link" size="small" onClick={() => onView(issue)}>
                    {t('common.view')}
                  </Button>
                ) : null}
                {issue.status === 'open' && canUpdate ? (
                  <Button type="link" size="small" onClick={() => void onEdit(issue)}>
                    {t('common.edit')}
                  </Button>
                ) : null}
                {issue.status === 'open' && canUpdate ? (
                  <Button type="link" size="small" onClick={() => onStart(issue)}>
                    {t('common.start')}
                  </Button>
                ) : null}
                {['open', 'in_progress'].includes(issue.status) && canUpdate ? (
                  <Button type="link" size="small" onClick={() => onResolve(issue)}>
                    {t('app.kuaizhizao.deliveryProject.resolveIssue')}
                  </Button>
                ) : null}
                {issue.status === 'resolved' && canUpdate ? (
                  <Button type="link" size="small" onClick={() => onClose(issue)}>
                    {t('common.close')}
                  </Button>
                ) : null}
                {issue.status === 'open' && canDelete ? (
                  <Popconfirm
                    title={t('app.kuaizhizao.deliveryProject.deleteIssueConfirm')}
                    onConfirm={() => onDelete(issue)}
                  >
                    <Button type="link" size="small" danger>
                      {t('common.delete')}
                    </Button>
                  </Popconfirm>
                ) : null}
              </Space>
            ),
          },
        ]
      : []),
  ];
}
