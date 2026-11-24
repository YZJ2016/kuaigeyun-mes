import React, { useMemo } from 'react';
import type { ProColumns } from '@ant-design/pro-components';
import { PaperClipOutlined } from '@ant-design/icons';
import { Tooltip, Typography } from 'antd';
import type { TFunction } from 'i18next';
import {
  countDocumentAttachments,
  type DocumentAttachmentFile,
} from '../utils/documentAttachments';
import { DocumentAttachmentsReadonly } from './DocumentAttachmentsReadonly';

export type DocumentAttachmentsListRecord = {
  attachments?: DocumentAttachmentFile[] | unknown;
  attachments_count?: number | null;
  header_attachments_count?: number | null;
  line_attachments_count?: number | null;
};

export function resolveDocumentAttachmentsListCount(
  record: DocumentAttachmentsListRecord | null | undefined,
): number {
  if (!record) return 0;
  if (typeof record.attachments_count === 'number' && Number.isFinite(record.attachments_count)) {
    return Math.max(0, record.attachments_count);
  }
  const header = record.header_attachments_count ?? 0;
  const line = record.line_attachments_count ?? 0;
  if (header > 0 || line > 0) {
    return header + line;
  }
  return countDocumentAttachments(record.attachments);
}

type BuildDocumentAttachmentsListColumnOptions = {
  width?: number;
  minWidth?: number;
  /** 若列表行带 attachments 数组，允许点击预览 */
  allowPreview?: boolean;
};

export function buildDocumentAttachmentsListColumn<T extends DocumentAttachmentsListRecord>(
  t: TFunction,
  options?: BuildDocumentAttachmentsListColumnOptions,
): ProColumns<T> {
  const width = options?.width ?? 72;
  const minWidth = options?.minWidth ?? 72;
  return {
    title: t('components.documentAttachments.label'),
    dataIndex: 'attachments_count',
    key: 'attachments',
    width,
    minWidth,
    uniTableKeepWidth: true,
    align: 'center',
    hideInSearch: true,
    render: (_: unknown, record: T) => (
      <DocumentAttachmentsListIndicator
        record={record}
        t={t}
        allowPreview={options?.allowPreview}
      />
    ),
  };
}

export function DocumentAttachmentsListIndicator({
  record,
  t,
  allowPreview = false,
}: {
  record: DocumentAttachmentsListRecord;
  t: TFunction;
  allowPreview?: boolean;
}) {
  const count = resolveDocumentAttachmentsListCount(record);
  const headerCount = record.header_attachments_count ?? 0;
  const lineCount = record.line_attachments_count ?? 0;
  const attachments = useMemo(() => {
    return Array.isArray(record.attachments)
      ? (record.attachments as DocumentAttachmentFile[])
      : null;
  }, [record.attachments]);

  if (count <= 0) {
    return <Typography.Text type="secondary">—</Typography.Text>;
  }

  const tooltip =
    headerCount > 0 || lineCount > 0
      ? t('components.documentAttachments.listHeaderLineBreakdown', {
          header: headerCount,
          line: lineCount,
          total: count,
        })
      : t('components.documentAttachments.count', { count });

  if (allowPreview && attachments && attachments.length > 0) {
    return (
      <Tooltip title={tooltip}>
        <span onClick={(e) => e.stopPropagation()}>
          <DocumentAttachmentsReadonly attachments={attachments} variant="count" />
        </span>
      </Tooltip>
    );
  }

  return (
    <Tooltip title={tooltip}>
      <Typography.Text style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
        <PaperClipOutlined /> {count}
      </Typography.Text>
    </Tooltip>
  );
}