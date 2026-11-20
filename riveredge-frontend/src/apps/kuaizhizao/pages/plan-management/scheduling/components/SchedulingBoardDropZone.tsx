import React from 'react';
import { SCHEDULING_DRAG_WORK_ORDER } from '../schedulingDropUtils';

export type SchedulingBoardDropMeta = {
  clientX: number;
  clientY: number;
};

interface SchedulingBoardDropZoneProps {
  canUpdate?: boolean;
  onDropWorkOrder: (workOrderId: number, meta?: SchedulingBoardDropMeta) => void;
  children: React.ReactNode;
}

const SchedulingBoardDropZone: React.FC<SchedulingBoardDropZoneProps> = ({
  canUpdate = false,
  onDropWorkOrder,
  children,
}) => {
  const [dragOver, setDragOver] = React.useState(false);

  const handleDragOver = (e: React.DragEvent) => {
    if (!canUpdate) return;
    if (e.dataTransfer.types.includes(SCHEDULING_DRAG_WORK_ORDER)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      setDragOver(true);
    }
  };

  const handleDragLeave = () => setDragOver(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (!canUpdate) return;
    const raw = e.dataTransfer.getData(SCHEDULING_DRAG_WORK_ORDER);
    const workOrderId = Number(raw);
    if (!Number.isInteger(workOrderId) || workOrderId <= 0) return;
    onDropWorkOrder(workOrderId, { clientX: e.clientX, clientY: e.clientY });
  };

  return (
    <div
      className={`scheduling-board-drop-zone${dragOver ? ' scheduling-board-drop-zone--active' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {children}
    </div>
  );
};

export default SchedulingBoardDropZone;
