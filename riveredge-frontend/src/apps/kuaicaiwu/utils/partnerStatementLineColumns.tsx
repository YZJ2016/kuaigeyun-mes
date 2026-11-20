import React, { useMemo, useState } from 'react';
import { Input, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';
import { formatBusinessDateOnly } from '../../../utils/format';
import type { PartnerStatementLine } from '../services/finance/partnerStatement';
import { renderFinanceHierarchyDocType } from './partnerStatementLineDisplay';
import { partnerStatementMoney } from './partnerStatementAmountUtils';
import { isPartnerStatementFinanceVoucherLine } from './financeVoucherDocType';

const PS = 'app.kuaicaiwu.partnerStatement';

export type PartnerStatementLineColumnOptions = {
  t: TFunction;
  balanceLabel: string;
  editable?: boolean;
  onStatementAmountChange?: (lineKey: string, amount: number) => void;
  lineKey?: (line: PartnerStatementLine, index: number) => string;
  onDocCodeClick?: (line: PartnerStatementLine) => void;
};

function formatAmountSeed(value: number): string {
  if (!Number.isFinite(value)) return '';
  return String(value);
}

/**
 * 未聚焦：展示值唯一来自 props（行上的 statement_amount）。
 * 聚焦：仅草稿字符串；失焦交回父级 patch + recalc。禁止 useEffect 从父级回写子 state。
 */
function PartnerStatementAmountInput({
  value,
  onCommit,
}: {
  value: number;
  onCommit: (amount: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  const displayValue = editing ? draft : formatAmountSeed(value);

  const finishEdit = (raw: string) => {
    setEditing(false);
    const next = Number(String(raw).replace(/,/g, '').trim());
    if (!Number.isFinite(next) || next <= 0) {
      return;
    }
    if (Math.abs(next - value) > 1e-9) {
      onCommit(next);
    }
  };

  return (
    <Input
      size="small"
      inputMode="decimal"
      value={displayValue}
      style={{ width: '100%', textAlign: 'right' }}
      onClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      onFocus={(e) => {
        setDraft(formatAmountSeed(value));
        setEditing(true);
        e.target.select();
      }}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={(e) => finishEdit(e.target.value)}
      onPressEnter={(e) => {
        (e.target as HTMLInputElement).blur();
      }}
    />
  );
}

export function usePartnerStatementLineColumns(
  options: PartnerStatementLineColumnOptions,
): ColumnsType<PartnerStatementLine> {
  const { t, balanceLabel, editable, onStatementAmountChange, lineKey, onDocCodeClick } = options;

  return useMemo(
    () => [
      { title: t(`${PS}.col.date`), dataIndex: 'date', width: 110 },
      {
        title: t(`${PS}.col.docType`),
        dataIndex: 'doc_type',
        width: 120,
        render: (v: string, record: PartnerStatementLine) => renderFinanceHierarchyDocType(v, record),
      },
      {
        title: t(`${PS}.col.docCode`),
        dataIndex: 'doc_code',
        width: 140,
        ellipsis: true,
        render: (value: string, record: PartnerStatementLine) => {
          if (onDocCodeClick && isPartnerStatementFinanceVoucherLine(record)) {
            return (
              <Typography.Link onClick={() => onDocCodeClick(record)}>
                {value || '—'}
              </Typography.Link>
            );
          }
          return value || '—';
        },
      },
      { title: t(`${PS}.col.summary`), dataIndex: 'summary', ellipsis: true },
      {
        title: t(`${PS}.col.invoiceDate`),
        dataIndex: 'invoice_date',
        width: 110,
        render: (v: string | null | undefined) => formatBusinessDateOnly(v, '—'),
      },
      {
        title: t(`${PS}.col.docAmount`),
        dataIndex: 'doc_amount',
        width: 110,
        align: 'right' as const,
        render: (_: unknown, row: PartnerStatementLine) =>
          partnerStatementMoney(row.doc_amount ?? row.debit ?? row.credit),
      },
      {
        title: t(`${PS}.col.priorStatedAmount`),
        dataIndex: 'prior_stated_amount',
        width: 110,
        align: 'right' as const,
        render: (v: unknown) => partnerStatementMoney(v as number),
      },
      {
        title: t(`${PS}.col.remainingAmount`),
        dataIndex: 'remaining_amount',
        width: 110,
        align: 'right' as const,
        render: (v: unknown) => partnerStatementMoney(v as number),
      },
      {
        title: t(`${PS}.col.statementAmount`),
        dataIndex: 'statement_amount',
        width: 140,
        align: 'right' as const,
        onCell: () => ({
          onClick: (e: React.MouseEvent) => e.stopPropagation(),
        }),
        render: (_: unknown, row: PartnerStatementLine, index: number) => {
          const value = Number(row.statement_amount ?? row.debit ?? row.credit ?? 0);
          if (!editable) {
            return partnerStatementMoney(value);
          }
          const key = lineKey ? lineKey(row, index) : `${row.doc_code}-${index}`;
          return (
            <PartnerStatementAmountInput
              value={value}
              onCommit={(amount) => onStatementAmountChange?.(key, amount)}
            />
          );
        },
      },
      {
        title: t(`${PS}.col.debit`),
        dataIndex: 'debit',
        width: 100,
        align: 'right' as const,
        render: (v: unknown) => (v ? partnerStatementMoney(v as number) : '—'),
      },
      {
        title: t(`${PS}.col.credit`),
        dataIndex: 'credit',
        width: 100,
        align: 'right' as const,
        render: (v: unknown) => (v ? partnerStatementMoney(v as number) : '—'),
      },
      {
        title: balanceLabel,
        dataIndex: 'balance',
        width: 110,
        align: 'right' as const,
        render: (v: unknown) => partnerStatementMoney(v as number),
      },
    ],
    [balanceLabel, editable, lineKey, onDocCodeClick, onStatementAmountChange, t],
  );
}