import React from 'react';
import { useDroppable } from '@dnd-kit/core';
import { SortableContext, horizontalListSortingStrategy } from '@dnd-kit/sortable';
import { Typography } from 'antd';
import type { TFunction } from 'i18next';
import { cardLaneDroppableId, type SchedulingCardOperationItem } from '../schedulingCardViewUtils';
import { SortableTaskCard, type CardOperationUpdateHandler } from './SchedulingCardTask';

interface SchedulingCardLaneProps {
  t: TFunction;
  resourceId: number;
  operations: SchedulingCardOperationItem[];
  canUpdate?: boolean;
  dropActive?: boolean;
  selectedWorkOrderIds: Set<number>;
  onSelectWorkOrder?: (workOrderId: number) => void;
  onOperationUpdate?: CardOperationUpdateHandler;
}

export default function SchedulingCardLane({
  t,
  resourceId,
  operations,
  canUpdate = false,
  dropActive = false,
  selectedWorkOrderIds,
  onSelectWorkOrder,
  onOperationUpdate,
}: SchedulingCardLaneProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: cardLaneDroppableId(resourceId),
    data: { type: 'lane', resourceId },
  });

  const highlight = dropActive || isOver;

  if (operations.length === 0) {
    return (
      <div
        ref={setNodeRef}
        className={`scheduling-card-board__cards scheduling-card-board__cards--empty${highlight ? ' scheduling-card-board__cards--drop-target' : ''}`}
        data-resource-id={resourceId}
      >
        <Typography.Text type="secondary" className="scheduling-card-board__empty-label">
          {t('app.kuaizhizao.scheduling.cardBoard.rowIdle')}
        </Typography.Text>
      </div>
    );
  }

  return (
    <SortableContext items={operations.map((op) => op.operationId)} strategy={horizontalListSortingStrategy}>
      <div
        ref={setNodeRef}
        className={`scheduling-card-board__cards${highlight ? ' scheduling-card-board__cards--drop-target' : ''}`}
        data-resource-id={resourceId}
      >
        {operations.map((item) => (
          <SortableTaskCard
            key={item.focusTaskId}
            t={t}
            item={item}
            resourceId={resourceId}
            selected={selectedWorkOrderIds.has(item.workOrderId)}
            canUpdate={canUpdate}
            onSelectWorkOrder={onSelectWorkOrder}
            onOperationUpdate={onOperationUpdate}
          />
        ))}
      </div>
    </SortableContext>
  );
}
