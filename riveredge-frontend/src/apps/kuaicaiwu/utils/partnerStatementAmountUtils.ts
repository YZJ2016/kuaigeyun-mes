import type { PartnerStatementLine } from '../services/finance/partnerStatement';
import type { Key } from 'react';
import { formatCurrencyAmount } from '../../../utils/format';

export const partnerStatementMoney = (v: number | string | undefined) => formatCurrencyAmount(v ?? 0, '¥0.00');

export function lineUsesDebitSide(line: PartnerStatementLine): boolean {
  if (Number(line.debit ?? 0) > 0) return true;
  if (Number(line.credit ?? 0) > 0) return false;
  return true;
}

export function patchLineStatementAmount(
  line: PartnerStatementLine,
  statementAmount: number,
): PartnerStatementLine {
  const amount = Math.max(0, Number(statementAmount) || 0);
  const isDebit = lineUsesDebitSide(line);
  return {
    ...line,
    statement_amount: amount,
    debit: isDebit ? amount : 0,
    credit: isDebit ? 0 : amount,
  };
}

export function recalcPartnerStatementLines(
  openingBalance: number,
  lines: PartnerStatementLine[],
): { lines: PartnerStatementLine[]; debitTotal: number; creditTotal: number; closingBalance: number } {
  let balance = Number(openingBalance) || 0;
  let debitTotal = 0;
  let creditTotal = 0;
  const next = lines.map((ln) => {
    const debit = Number(ln.debit ?? 0);
    const credit = Number(ln.credit ?? 0);
    debitTotal += debit;
    creditTotal += credit;
    balance += debit - credit;
    return { ...ln, balance };
  });
  return {
    lines: next,
    debitTotal,
    creditTotal,
    closingBalance: balance,
  };
}

/** 列表按单据头展示：优先 document_lines，历史快照从物料行合并 */
export function resolvePartnerStatementTableLines(
  details:
    | {
        document_lines?: PartnerStatementLine[];
        lines?: PartnerStatementLine[];
      }
    | null
    | undefined,
  fallbackLines: PartnerStatementLine[] = [],
): PartnerStatementLine[] {
  const doc = details?.document_lines;
  if (doc?.length) {
    return doc;
  }
  const raw = details?.lines ?? fallbackLines;
  if (!raw.length) {
    return [];
  }
  const hasMaterial = raw.some((ln) => String((ln as { line_kind?: string }).line_kind || '') === 'material');
  if (!hasMaterial) {
    return raw;
  }
  const groups = new Map<string, PartnerStatementLine>();
  const order: string[] = [];
  const passthrough: PartnerStatementLine[] = [];
  const materialKeys = new Set([
    'material_id',
    'material_code',
    'material_name',
    'material_spec',
    'unit',
    'quantity',
    'source_line_id',
    'line_kind',
  ]);
  for (const ln of raw) {
    if (String((ln as { line_kind?: string }).line_kind || '') !== 'material') {
      passthrough.push(ln);
      continue;
    }
    const docType = String(ln.doc_type || '').trim();
    const docId = ln.doc_id != null ? String(ln.doc_id) : '';
    const key = `${docType}-${docId}`;
    if (!docId) {
      passthrough.push(ln);
      continue;
    }
    const stmt = Number(ln.statement_amount ?? ln.debit ?? ln.credit ?? 0);
    const existing = groups.get(key);
    if (!existing) {
      const base = { ...ln };
      materialKeys.forEach((k) => delete (base as Record<string, unknown>)[k]);
      delete (base as { line_kind?: string }).line_kind;
      base.statement_amount = stmt;
      base.prior_stated_amount = Number(ln.prior_stated_amount ?? 0);
      base.remaining_amount = Number(ln.remaining_amount ?? 0);
      base.debit = Number(ln.debit ?? 0) > Number(ln.credit ?? 0) ? stmt : 0;
      base.credit = Number(ln.credit ?? 0) > Number(ln.debit ?? 0) ? stmt : 0;
      groups.set(key, base);
      order.push(key);
      continue;
    }
    existing.statement_amount = Number(existing.statement_amount ?? 0) + stmt;
    existing.prior_stated_amount =
      Number(existing.prior_stated_amount ?? 0) + Number(ln.prior_stated_amount ?? 0);
    existing.remaining_amount = Number(existing.remaining_amount ?? 0) + Number(ln.remaining_amount ?? 0);
    if (Number(ln.debit ?? 0) > Number(ln.credit ?? 0)) {
      existing.debit = Number(existing.debit ?? 0) + stmt;
    } else {
      existing.credit = Number(existing.credit ?? 0) + stmt;
    }
  }
  return [...passthrough, ...order.map((k) => groups.get(k)!)];
}

export function previewLineKey(line: PartnerStatementLine, _index?: number): string {
  // 勿用数组下标：Ant Design Table 分页时传入的是页内 index，会导致第 2 页勾选键
  // 与 allPreviewLineKeys（全量下标）不一致，表现为「第二页点不上去」。
  const docType = String(line.doc_type || '').trim();
  const docId = line.doc_id != null ? String(line.doc_id) : String(line.doc_code || '');
  return `${docType}-${docId}`;
}

export function allPreviewLineKeys(lines: PartnerStatementLine[]): string[] {
  return lines.map((ln, idx) => previewLineKey(ln, idx));
}

export function filterLinesBySelectedKeys(
  lines: PartnerStatementLine[],
  selectedKeys: Key[],
): PartnerStatementLine[] {
  const selected = new Set(selectedKeys.map(String));
  return lines.filter((ln, idx) => selected.has(previewLineKey(ln, idx)));
}

export function buildLineAmountPayload(lines: PartnerStatementLine[]) {
  return lines
    .filter((ln) => ln.doc_id != null && ln.doc_type)
    .map((ln) => ({
      doc_type: ln.doc_type,
      doc_id: Number(ln.doc_id),
      statement_amount: Number(ln.statement_amount ?? ln.debit ?? ln.credit ?? 0),
    }));
}
