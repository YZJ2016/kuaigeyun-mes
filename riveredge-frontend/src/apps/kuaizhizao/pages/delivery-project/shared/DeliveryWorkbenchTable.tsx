import React, { useRef } from 'react';
import { Table } from 'antd';
import type { TableProps } from 'antd';
import { useDeliveryWorkbenchTableLayout } from './deliveryWorkbenchTableLayout';

export type DeliveryWorkbenchTableProps<T extends object> = Omit<TableProps<T>, 'scroll' | 'tableLayout'>;

export function DeliveryWorkbenchTable<T extends object>({
  columns,
  className,
  ...rest
}: DeliveryWorkbenchTableProps<T>) {
  const hostRef = useRef<HTMLDivElement>(null);
  const rowCount = Array.isArray(rest.dataSource) ? rest.dataSource.length : 0;
  const { columns: layoutColumns, scrollX } = useDeliveryWorkbenchTableLayout(
    columns ?? [],
    hostRef,
    rowCount,
  );

  return (
    <div ref={hostRef} className="delivery-workbench-table-host">
      <Table<T>
        {...rest}
        className={['delivery-workbench-table', className].filter(Boolean).join(' ') || undefined}
        tableLayout="fixed"
        columns={layoutColumns}
        scroll={scrollX ? { x: scrollX } : undefined}
      />
    </div>
  );
}

export default DeliveryWorkbenchTable;
