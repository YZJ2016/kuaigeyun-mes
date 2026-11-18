import React from 'react';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import type { FormListFieldData } from 'antd/es/form/FormList';
import type { ColumnsType } from 'antd/es/table';
import type { GlobalToken } from 'antd/es/theme/interface';
import { SequenceIndexCell, StepDragHandleContext } from '../sequence-index-cell';

/** 拖拽手柄 + 序号徽章，与工艺路线序号列 88px 同口径 */
export const UNI_TABLE_DETAIL_DRAG_INDEX_COL_WIDTH = 88;

export function buildUniTableDetailDragIndexColumn(
  t: (key: string) => string,
  token: GlobalToken,
): ColumnsType<any>[number] {
  return {
    title: t('app.master-data.operationSequence.index'),
    key: '__uni_detail_drag_index',
    width: UNI_TABLE_DETAIL_DRAG_INDEX_COL_WIDTH,
    fixed: 'left',
    onHeaderCell: () => ({ className: 'uni-detail-drag-index-header' }),
    onCell: () => ({ className: 'uni-detail-drag-index-cell' }),
    render: (_: unknown, __: unknown, index: number) => (
      <SequenceIndexCell
        index={index}
        token={token}
        dragSortTitle={t('app.master-data.operationSequence.dragSort')}
      />
    ),
  };
}

function SortableFormListBodyRow({
  children,
  ...props
}: React.HTMLAttributes<HTMLTableRowElement> & { 'data-row-key'?: string | number }) {
  const rowKey = String(props['data-row-key'] ?? '');
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } =
    useSortable({
      id: rowKey,
      disabled: !rowKey,
    });
  const style: React.CSSProperties = {
    ...props.style,
    transform: CSS.Transform.toString(transform),
    transition: isDragging ? 'none' : transition,
    opacity: isDragging ? 0.45 : 1,
  };
  return (
    <StepDragHandleContext.Provider value={{ attributes, listeners, setActivatorNodeRef, isDragging }}>
      <tr {...props} ref={setNodeRef} style={style}>
        {children}
      </tr>
    </StepDragHandleContext.Provider>
  );
}

export type UniTableDetailSortableTableProps = {
  fields: FormListFieldData[];
  move: (from: number, to: number) => void;
  children: React.ReactNode;
};

/** Form.List 明细表：@dnd-kit 行拖拽，onDragEnd 调用 move */
export function UniTableDetailSortableTable({
  fields,
  move,
  children,
}: UniTableDetailSortableTableProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const sortableIds = fields.map((f) => String(f.key));

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = fields.findIndex((f) => String(f.key) === String(active.id));
    const newIndex = fields.findIndex((f) => String(f.key) === String(over.id));
    if (oldIndex < 0 || newIndex < 0) return;
    move(oldIndex, newIndex);
  };

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={sortableIds} strategy={verticalListSortingStrategy}>
        {children}
      </SortableContext>
    </DndContext>
  );
}

export const uniTableDetailSortableComponents = {
  body: {
    row: SortableFormListBodyRow,
  },
};
