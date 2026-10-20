/**
 * 详情抽屉「审批记录」Tab：时间线 + 流程图（只读，切 Tab 后才请求）。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { App, Button, Empty, Result, Spin, Timeline, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import ApprovalFlowPreview from '../../../components/uni-audit/ApprovalFlowPreview';
import { formatApprovalExecutionComment } from '../../../components/uni-audit/formatApprovalExecutionComment';
import { MarkerTag, StatusTag } from '../../../constants/statusBadges';
import {
  getApprovalStatus,
  type ApprovalNodeOverview,
  type ApprovalStatusResponse,
} from '../../../services/approvalInstance';
import { formatDateTime } from '../../../utils/format';
import { getApiErrorMessage } from '../../../utils/errorHandler';

export type DocumentApprovalRecordsPaneProps = {
  entityType: string;
  entityId: number;
  active?: boolean;
  refreshKey?: number;
};

function isSolidAction(action?: string, label?: string): boolean {
  const raw = String(action || label || '').toLowerCase();
  return (
    raw.includes('approve') ||
    raw.includes('reject') ||
    raw.includes('通过') ||
    raw.includes('驳回') ||
    raw.includes('拒绝')
  );
}

function actionTagColor(action?: string, label?: string): string {
  const raw = String(action || label || '').toLowerCase();
  if (raw.includes('reject') || raw.includes('驳回') || raw.includes('拒绝')) return 'error';
  if (raw.includes('approve') || raw.includes('通过') || raw.includes('同意')) return 'success';
  return 'default';
}

function formatAction(action?: string, label?: string): string {
  return String(label || action || '—').trim() || '—';
}

function flattenExecutions(nodes: ApprovalNodeOverview[]) {
  const rows: Array<{
    key: string;
    actor: string;
    action?: string;
    actionLabel?: string;
    at?: string | null;
    comment?: string | null;
    nodeLabel: string;
  }> = [];
  for (const node of nodes) {
    for (let i = 0; i < (node.executions?.length ?? 0); i += 1) {
      const ex = node.executions[i];
      rows.push({
        key: `${node.node_id}-${i}`,
        actor: String(ex.action_by_name || ex.action_by || '系统'),
        action: ex.action,
        actionLabel: ex.action_label,
        at: ex.action_at,
        comment: ex.comment,
        nodeLabel: node.label,
      });
    }
  }
  return rows;
}

export const DocumentApprovalRecordsPane: React.FC<DocumentApprovalRecordsPaneProps> = ({
  entityType,
  entityId,
  active = true,
  refreshKey = 0,
}) => {
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<ApprovalStatusResponse | null>(null);

  const load = useCallback(async () => {
    if (!entityType || !entityId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getApprovalStatus(entityType, entityId);
      setStatus(res);
    } catch (e) {
      const msg = getApiErrorMessage(e, t('app.kuaizhizao.purchaseInquiry.approvalLoadFailed'));
      setError(msg);
      setStatus(null);
      messageApi.error(msg);
    } finally {
      setLoading(false);
    }
  }, [entityId, entityType, messageApi, t]);

  useEffect(() => {
    if (!active) return;
    void load();
  }, [active, load, refreshKey]);

  if (!active) return null;

  if (loading && !status) {
    return (
      <div style={{ minHeight: 160, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin />
      </div>
    );
  }

  if (error && !status) {
    return (
      <Result
        status="error"
        title={error}
        extra={
          <Button type="primary" onClick={() => void load()}>
            {t('common.retry')}
          </Button>
        }
      />
    );
  }

  if (!status?.has_flow && !status?.has_instance) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t('app.kuaizhizao.purchaseInquiry.emptyApprovalRecords')}
      />
    );
  }

  const nodes = status?.nodes_overview ?? [];
  const executions = flattenExecutions(nodes);
  const instance = status?.instance;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {instance ? (
        <Typography.Text type="secondary">
          {t('app.kuaizhizao.purchaseInquiry.approvalSubmitter', {
            name: instance.submitter_name || instance.submitter_id,
          })}
          {instance.submitted_at ? ` · ${formatDateTime(instance.submitted_at)}` : ''}
        </Typography.Text>
      ) : null}

      {executions.length > 0 ? (
        <Timeline
          items={executions.map((row) => {
            const comment = formatApprovalExecutionComment(row.comment);
            const solid = isSolidAction(row.action, row.actionLabel);
            const color = actionTagColor(row.action, row.actionLabel);
            const label = formatAction(row.action, row.actionLabel);
            return {
              key: row.key,
              children: (
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <Typography.Text strong>{row.actor}</Typography.Text>
                    {solid ? (
                      <StatusTag color={color}>{label}</StatusTag>
                    ) : (
                      <MarkerTag color={color}>{label}</MarkerTag>
                    )}
                    <Typography.Text type="secondary">{row.nodeLabel}</Typography.Text>
                    <Typography.Text type="secondary" style={{ marginLeft: 'auto' }}>
                      {row.at ? formatDateTime(row.at) : '—'}
                    </Typography.Text>
                  </div>
                  {comment ? (
                    <Typography.Text type="secondary" style={{ display: 'block', marginTop: 4 }}>
                      {comment}
                    </Typography.Text>
                  ) : null}
                </div>
              ),
            };
          })}
        />
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={t('app.kuaizhizao.purchaseInquiry.emptyApprovalRecords')}
        />
      )}

      {status?.process?.nodes ? (
        <div style={{ height: 320, border: '1px solid rgba(0,0,0,0.06)', borderRadius: 6, overflow: 'hidden' }}>
          <ApprovalFlowPreview
            graph={status.process.nodes}
            nodesOverview={nodes}
            height="100%"
          />
        </div>
      ) : null}
    </div>
  );
};

export default DocumentApprovalRecordsPane;
