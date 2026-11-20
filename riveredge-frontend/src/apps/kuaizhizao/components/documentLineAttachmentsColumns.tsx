import React from 'react';
import type { ColumnsType } from 'antd/es/table';
import type { ProColumns } from '@ant-design/pro-components';
import { Form } from 'antd';
import type { TFunction } from 'i18next';
import DocumentLineAttachmentsCell from './DocumentLineAttachmentsCell';
import type { DocumentAttachmentFile } from '../utils/documentAttachments';

export const DOCUMENT_LINE_ATTACHMENT_UPLOAD_CATEGORY = {
  purchaseRequisition: 'purchase_requisition_attachments',
  purchaseOrder: 'purchase_order_attachments',
  purchaseReceipt: 'purchase_receipt_attachments',
  quotation: 'quotation_attachments',
  salesOrder: 'sales_order_attachments',
  salesDelivery: 'sales_delivery_attachments',
} as const;

type LineRow = {
  material_id?: number;
  attachments?: DocumentAttachmentFile[] | null;
};

export function buildDocumentLineAttachmentsFormColumn(
  t: TFunction,
  category: string,
): {
  title: string;
  dataIndex: string;
  width: number;
  render: (_: unknown, __: unknown, index: number) => React.ReactNode;
} {
  return {
    title: t('app.kuaizhizao.documentLineAttachments.columnTitle'),
    dataIndex: 'attachments',
    width: 208,
    render: (_: unknown, __: unknown, index: number) => (
      <Form.Item
        noStyle
        shouldUpdate={(p, c) => {
          const pi = p.items?.[index];
          const ci = c.items?.[index];
          return pi !== ci || pi?.material_id !== ci?.material_id;
        }}
      >
        {({ getFieldValue }) => (
          <Form.Item name={[index, 'attachments']} style={{ margin: 0 }}>
            <DocumentLineAttachmentsCell
              category={category}
              materialId={Number(getFieldValue(['items', index, 'material_id'])) || undefined}
            />
          </Form.Item>
        )}
      </Form.Item>
    ),
  };
}

export function buildDocumentLineAttachmentsDrawerColumn(
  t: TFunction,
  category: string,
): ColumnsType<LineRow>[number] {
  return {
    title: t('app.kuaizhizao.documentLineAttachments.columnTitle'),
    dataIndex: 'attachments',
    width: 140,
    render: (_: unknown, row: LineRow) => (
      <DocumentLineAttachmentsCell
        readOnly
        category={category}
        value={row.attachments}
        materialId={row.material_id}
      />
    ),
  };
}

export function buildDocumentLineAttachmentsReportColumn(
  t: TFunction,
  category: string,
): ProColumns {
  return {
    title: t('app.kuaizhizao.documentLineAttachments.columnTitle'),
    dataIndex: 'attachments',
    width: 140,
    hideInSearch: true,
    render: (_: unknown, record: LineRow) => (
      <DocumentLineAttachmentsCell
        readOnly
        category={category}
        value={record.attachments as DocumentAttachmentFile[] | null | undefined}
        materialId={record.material_id}
      />
    ),
  };
}
