import React, { useMemo } from 'react';
import { Empty, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import { formatDateTimeBySiteSetting, formatQuantity } from '../../../utils/format';
import { DetailDrawerSection } from '../../../components/layout-templates';

export type OutsourceOrderReceiptBatchRow = {
  id?: number;
  received_quantity?: number;
  qualified_quantity?: number;
  unqualified_quantity?: number;
  created_at?: string;
  created_by_name?: string;
};

type Props = {
  batches?: OutsourceOrderReceiptBatchRow[] | null;
  t: TFunction;
};

export function OutsourceOrderReceiptBatchesSection({ batches, t }: Props) {
  const rows = Array.isArray(batches) ? batches : [];
  const columns: ColumnsType<OutsourceOrderReceiptBatchRow> = useMemo(
    () => [
      {
        title: t('common.createdAt'),
        dataIndex: 'created_at',
        width: 168,
        ellipsis: true,
        render: (_, row) => formatDateTimeBySiteSetting(row.created_at),
      },
      {
        title: t('app.kuaizhizao.outsourceOrder.fieldBatchCompletedQty'),
        dataIndex: 'received_quantity',
        width: 112,
        align: 'right',
        render: (val) => formatQuantity(Number(val ?? 0)),
      },
      {
        title: t('app.kuaizhizao.outsourceOrder.fieldQualifiedQty'),
        dataIndex: 'qualified_quantity',
        width: 96,
        align: 'right',
        render: (val) => formatQuantity(Number(val ?? 0)),
      },
      {
        title: t('app.kuaizhizao.outsourceOrder.fieldUnqualifiedQty'),
        dataIndex: 'unqualified_quantity',
        width: 96,
        align: 'right',
        render: (val) => formatQuantity(Number(val ?? 0)),
      },
      {
        title: t('common.createdBy'),
        dataIndex: 'created_by_name',
        width: 96,
        ellipsis: true,
        render: (val) => val || '—',
      },
    ],
    [t],
  );

  if (!rows.length) {
    return (
      <DetailDrawerSection title={t('app.kuaizhizao.outsourceOrder.receiptBatchesTitle')}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('app.kuaizhizao.outsourceOrder.receiptBatchesEmpty')} />
      </DetailDrawerSection>
    );
  }

  return (
    <DetailDrawerSection title={t('app.kuaizhizao.outsourceOrder.receiptBatchesTitle')}>
      <Table<OutsourceOrderReceiptBatchRow>
        size="small"
        rowKey={(row) => String(row.id ?? `${row.created_at}`)}
        pagination={false}
        columns={columns}
        dataSource={rows}
        scroll={{ x: 'max-content' }}
      />
    </DetailDrawerSection>
  );
}