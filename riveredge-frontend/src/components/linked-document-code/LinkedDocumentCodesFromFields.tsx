/**
 * 多来源单号列：按约定 *_code 字段逐个挂链（有 *_id 则可点；否则纯文案）。
 * 仓储出入库 Hub「来源单号」等聚合列用本组件，禁止再拼 plain string。
 */

import React from 'react';
import { LinkedDocumentAutoCell } from './LinkedDocumentAutoCell';
import {
  resolveLinkedDocumentColumn,
  toCamelField,
  toSnakeField,
} from '../../apps/kuaizhizao/utils/linkedDocumentAutoLink';

function readCodeField(
  record: Record<string, unknown>,
  codeField: string,
): string {
  const snake = toSnakeField(codeField);
  const camel = toCamelField(snake);
  for (const key of [codeField, snake, camel]) {
    const v = record[key];
    if (v != null && String(v).trim() !== '') return String(v).trim();
  }
  return '';
}

export function LinkedDocumentCodesFromFields({
  record,
  codeFields,
  emptyText = '-',
  separator = ' / ',
}: {
  record: Record<string, unknown> | null | undefined;
  /** 按展示优先级排列的 *_code 字段（如 sales_order_code） */
  codeFields: readonly string[];
  emptyText?: string;
  separator?: string;
}): React.ReactNode {
  if (!record) return emptyText;

  const nodes: React.ReactNode[] = [];
  for (const field of codeFields) {
    const code = readCodeField(record, field);
    if (!code) continue;

    const binding = resolveLinkedDocumentColumn(field);
    if (nodes.length > 0) {
      nodes.push(
        <span key={`${field}-sep`} style={{ whiteSpace: 'pre' }}>
          {separator}
        </span>,
      );
    }
    if (binding) {
      nodes.push(
        <LinkedDocumentAutoCell
          key={field}
          binding={binding}
          record={record}
          emptyText={code}
          ellipsis
        />,
      );
    } else {
      nodes.push(<span key={field}>{code}</span>);
    }
  }

  if (nodes.length === 0) return emptyText;
  return (
    <span
      style={{
        display: 'inline-flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        maxWidth: '100%',
        minWidth: 0,
        verticalAlign: 'middle',
      }}
    >
      {nodes}
    </span>
  );
}
