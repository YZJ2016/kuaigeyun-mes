/**
 * 开口行取单：单据数量 / 已转 / 可取 + 并列副数量列（无数据也占位显示）。
 */

import type { TFunction } from 'i18next';
import type { ProColumns } from '@ant-design/pro-components';
import React from 'react';
import { QuantityWithUnitDisplay } from '../quantity-with-unit';
import { renderPullQueryEmptyValue } from './renderPullQueryEmptyValue';
import {
  readPullOpenLineAuxPushedQty,
  readPullOpenLineAuxRemainingQty,
  readPullOpenLineAuxSuggestedQty,
  readPullOpenLinePushedQty,
  readPullOpenLineRemainingQty,
  readPullOpenLineSuggestedQty,
  type PullOpenLineQtyRow,
} from './pullOpenLine';

export type PullOpenLineQtyPart = 'suggested' | 'pushed' | 'remaining';

type PullOpenLineQtyRecord = PullOpenLineQtyRow & {
  unit?: string | null;
  material_unit?: string | null;
  aux_unit?: string | null;
};

function resolveUnit(record: PullOpenLineQtyRecord): string | undefined {
  const u = record.unit ?? record.material_unit;
  return u && String(u).trim() ? String(u).trim() : undefined;
}

function resolveAuxUnit(record: PullOpenLineQtyRecord): string | null {
  const u = record.aux_unit;
  return u && String(u).trim() ? String(u).trim() : null;
}

function readPrimary(record: PullOpenLineQtyRecord, part: PullOpenLineQtyPart): number {
  if (part === 'suggested') return readPullOpenLineSuggestedQty(record);
  if (part === 'pushed') return readPullOpenLinePushedQty(record);
  return readPullOpenLineRemainingQty(record);
}

function readAux(record: PullOpenLineQtyRecord, part: PullOpenLineQtyPart): number | null {
  if (part === 'suggested') return readPullOpenLineAuxSuggestedQty(record);
  if (part === 'pushed') return readPullOpenLineAuxPushedQty(record);
  return readPullOpenLineAuxRemainingQty(record);
}

function auxDataIndex(part: PullOpenLineQtyPart): string {
  if (part === 'suggested') return 'suggested_aux_quantity';
  if (part === 'pushed') return 'pushed_aux_quantity';
  return 'remaining_aux_quantity';
}

/** 主数量：单列 */
export function renderPullOpenLinePrimaryQtyCell(
  record: PullOpenLineQtyRecord,
  part: PullOpenLineQtyPart,
): React.ReactNode {
  const unit = resolveUnit(record);
  const primary = readPrimary(record, part);
  return <QuantityWithUnitDisplay quantity={primary} unit={unit} />;
}

/** 副数量列：始终渲染；无副单位走全站空值占位 */
export function renderPullOpenLineAuxQtyCell(
  record: PullOpenLineQtyRecord,
  part: PullOpenLineQtyPart,
): React.ReactNode {
  const auxUnit = resolveAuxUnit(record);
  if (!auxUnit) {
    return renderPullQueryEmptyValue();
  }
  const aux = readAux(record, part);
  return <QuantityWithUnitDisplay quantity={aux ?? 0} unit={auxUnit} style={{ opacity: 0.92 }} />;
}

/** @deprecated 取单默认改并列副列；保留叠显供极少数自定义列 */
export function renderPullOpenLineDualQtyCell(
  record: PullOpenLineQtyRecord,
  part: PullOpenLineQtyPart,
): React.ReactNode {
  const unit = resolveUnit(record);
  const auxUnit = resolveAuxUnit(record);
  const primary = readPrimary(record, part);
  const aux = auxUnit ? readAux(record, part) : null;
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
      <QuantityWithUnitDisplay quantity={primary} unit={unit} />
      {auxUnit ? (
        <QuantityWithUnitDisplay quantity={aux ?? 0} unit={auxUnit} style={{ opacity: 0.88 }} />
      ) : null}
    </span>
  );
}

export type BuildPullOpenLineQtyColumnOptions = {
  part: PullOpenLineQtyPart;
  title: string;
  width?: number;
  dataIndex?: string;
};

export function buildPullOpenLinePrimaryQtyColumn<T extends PullOpenLineQtyRecord>(
  opts: BuildPullOpenLineQtyColumnOptions,
): ProColumns<T> {
  const dataIndex =
    opts.dataIndex ??
    (opts.part === 'suggested'
      ? 'suggested_quantity'
      : opts.part === 'pushed'
        ? 'pushed_quantity'
        : 'remaining_quantity');
  return {
    title: opts.title,
    dataIndex,
    key: dataIndex,
    width: opts.width ?? 112,
    align: 'right',
    render: (_: unknown, record: T) => renderPullOpenLinePrimaryQtyCell(record, opts.part),
  };
}

export function buildPullOpenLineAuxQtyColumn<T extends PullOpenLineQtyRecord>(
  opts: BuildPullOpenLineQtyColumnOptions,
): ProColumns<T> {
  const dataIndex = opts.dataIndex ?? auxDataIndex(opts.part);
  return {
    title: opts.title,
    dataIndex,
    key: `aux_${dataIndex}`,
    width: opts.width ?? 104,
    align: 'right',
    render: (_: unknown, record: T) => renderPullOpenLineAuxQtyCell(record, opts.part),
  };
}

/** @deprecated 使用 buildPullOpenLinePrimaryQtyColumn */
export function buildPullOpenLineQtyColumn<T extends PullOpenLineQtyRecord>(
  opts: BuildPullOpenLineQtyColumnOptions,
): ProColumns<T> {
  return buildPullOpenLinePrimaryQtyColumn(opts);
}

export const PULL_OPEN_LINE_QTY_COLUMN_KEYS = {
  suggested: 'components.uniPullQuery.openLineQty.suggested',
  pushed: 'components.uniPullQuery.openLineQty.pushed',
  remaining: 'components.uniPullQuery.openLineQty.remaining',
} as const;

export const PULL_OPEN_LINE_AUX_QTY_COLUMN_KEYS = {
  suggested: 'components.uniPullQuery.openLineQty.auxSuggested',
  pushed: 'components.uniPullQuery.openLineQty.auxPushed',
  remaining: 'components.uniPullQuery.openLineQty.auxRemaining',
} as const;

export function buildDefaultPullOpenLineQtyColumns(
  t: TFunction,
  options?: {
    keys?: Partial<Record<'suggested' | 'pushed' | 'remaining', string>>;
    auxKeys?: Partial<Record<'suggested' | 'pushed' | 'remaining', string>>;
    includeRemaining?: boolean;
    widths?: Partial<Record<PullOpenLineQtyPart, number>>;
    auxWidths?: Partial<Record<PullOpenLineQtyPart, number>>;
  },
): ProColumns<PullOpenLineQtyRecord>[] {
  return buildPullOpenLineQtyColumns(
    t,
    {
      suggested: options?.keys?.suggested ?? PULL_OPEN_LINE_QTY_COLUMN_KEYS.suggested,
      pushed: options?.keys?.pushed ?? PULL_OPEN_LINE_QTY_COLUMN_KEYS.pushed,
      remaining: options?.keys?.remaining ?? PULL_OPEN_LINE_QTY_COLUMN_KEYS.remaining,
    },
    {
      includeRemaining: options?.includeRemaining,
      widths: options?.widths,
      auxKeys: options?.auxKeys,
      auxWidths: options?.auxWidths,
    },
  );
}

export function buildPullOpenLineQtyColumns(
  t: TFunction,
  keys: {
    suggested: string;
    pushed: string;
    remaining?: string;
  },
  options?: {
    includeRemaining?: boolean;
    widths?: Partial<Record<PullOpenLineQtyPart, number>>;
    auxKeys?: Partial<Record<'suggested' | 'pushed' | 'remaining', string>>;
    auxWidths?: Partial<Record<PullOpenLineQtyPart, number>>;
  },
): ProColumns<PullOpenLineQtyRecord>[] {
  const auxKeys = {
    suggested: options?.auxKeys?.suggested ?? PULL_OPEN_LINE_AUX_QTY_COLUMN_KEYS.suggested,
    pushed: options?.auxKeys?.pushed ?? PULL_OPEN_LINE_AUX_QTY_COLUMN_KEYS.pushed,
    remaining: options?.auxKeys?.remaining ?? PULL_OPEN_LINE_AUX_QTY_COLUMN_KEYS.remaining,
  };

  const includeRemaining = options?.includeRemaining !== false && Boolean(keys.remaining);
  const parts: PullOpenLineQtyPart[] = ['suggested', 'pushed'];
  if (includeRemaining && keys.remaining) {
    parts.push('remaining');
  }
  const titleByPart: Record<PullOpenLineQtyPart, { primary: string; aux: string }> = {
    suggested: { primary: t(keys.suggested), aux: t(auxKeys.suggested) },
    pushed: { primary: t(keys.pushed), aux: t(auxKeys.pushed) },
    remaining: {
      primary: keys.remaining ? t(keys.remaining) : '',
      aux: t(auxKeys.remaining),
    },
  };
  const cols: ProColumns<PullOpenLineQtyRecord>[] = [];
  for (const part of parts) {
    cols.push(
      buildPullOpenLinePrimaryQtyColumn({
        part,
        title: titleByPart[part].primary,
        width: options?.widths?.[part] ?? 112,
      }),
    );
    cols.push(
      buildPullOpenLineAuxQtyColumn({
        part,
        title: titleByPart[part].aux,
        width: options?.auxWidths?.[part] ?? 104,
      }),
    );
  }
  return cols;
}