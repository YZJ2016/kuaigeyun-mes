import React from 'react';
import { Checkbox, Empty, Tag, Typography } from 'antd';
import type { TFunction } from 'react-i18next';
import type { SchedulingPoolCardItem } from '../schedulingCardViewUtils';
import { SCHEDULING_DRAG_WORK_ORDER } from '../schedulingDropUtils';
import { formatDateTime } from '../../../../../../utils/format';

interface SchedulingPoolCardGridProps {
  t: TFunction;
  items: SchedulingPoolCardItem[];
  selectedRowKeys: React.Key[];
  canUpdate?: boolean;
  onSelectionChange: (keys: React.Key[]) => void;
}

export default function SchedulingPoolCardGrid({
  t,
  items,
  selectedRowKeys,
  canUpdate = false,
  onSelectionChange,
}: SchedulingPoolCardGridProps) {
  const selectedSet = new Set(selectedRowKeys.map(String));

  if (items.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={t('app.kuaizhizao.scheduling.poolCard.empty')}
        style={{ padding: '24px 0' }}
      />
    );
  }

  const toggleSelect = (workOrderId: number) => {
    const key = workOrderId;
    if (selectedSet.has(String(workOrderId))) {
      onSelectionChange(selectedRowKeys.filter((k) => String(k) !== String(workOrderId)));
      return;
    }
    onSelectionChange([...selectedRowKeys, key]);
  };

  return (
    <div className="scheduling-pool-card-grid">
      {items.map((item) => {
        const checked = selectedSet.has(String(item.workOrderId));
        return (
          <div
            key={item.workOrderId}
            className={`scheduling-pool-card${checked ? ' scheduling-pool-card--selected' : ''}${item.isOverdue ? ' scheduling-pool-card--overdue' : ''}`}
            draggable={canUpdate}
            onDragStart={(e) => {
              if (!canUpdate) return;
              e.dataTransfer.setData(SCHEDULING_DRAG_WORK_ORDER, String(item.workOrderId));
              e.dataTransfer.effectAllowed = 'move';
            }}
            onClick={() => toggleSelect(item.workOrderId)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                toggleSelect(item.workOrderId);
              }
            }}
          >
            <div className="scheduling-pool-card__head">
              <Checkbox checked={checked} onClick={(e) => e.stopPropagation()} onChange={() => toggleSelect(item.workOrderId)} />
              <Typography.Text strong ellipsis className="scheduling-pool-card__code">
                {item.workOrderCode}
              </Typography.Text>
              {item.aiRank != null ? (
                <Tag color="blue" variant="filled">
                  AI #{item.aiRank}
                </Tag>
              ) : null}
            </div>
            <Typography.Text ellipsis className="scheduling-pool-card__product">
              {item.productName}
            </Typography.Text>
            <Typography.Text type="secondary" className="scheduling-pool-card__time">
              {item.plannedStart && item.plannedEnd
                ? `${formatDateTime(item.plannedStart, 'MM-DD HH:mm')} - ${formatDateTime(item.plannedEnd, 'MM-DD HH:mm')}`
                : t('app.kuaizhizao.scheduling.poolCard.noPlanTime')}
            </Typography.Text>
            <div className="scheduling-pool-card__tags">
              {item.hasMaterialIssue ? (
                <Tag color="warning" variant="filled">
                  {t('app.kuaizhizao.scheduling.poolCard.tagMaterial')}
                </Tag>
              ) : null}
              {item.isOverdue ? (
                <Tag color="error" variant="filled">
                  {t('app.kuaizhizao.scheduling.poolCard.tagOverdue')}
                </Tag>
              ) : null}
              {item.readinessRate != null && Number(item.readinessRate) < 100 ? (
                <Tag variant="filled">{`${Number(item.readinessRate).toFixed(0)}%`}</Tag>
              ) : null}
            </div>
            {item.diagnosticLabels.length > 0 ? (
              <Typography.Text type="secondary" ellipsis className="scheduling-pool-card__diagnostics">
                {item.diagnosticLabels.slice(0, 2).join('；')}
              </Typography.Text>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
