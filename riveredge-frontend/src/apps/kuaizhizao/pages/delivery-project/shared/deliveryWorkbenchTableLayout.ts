import { useLayoutEffect, useMemo, useState } from 'react';
import type { RefObject } from 'react';
import type { ColumnsType } from 'antd/es/table';
import { ROW_ACTIONS_STRIP_CLASS } from '../../../../../components/uni-action/overflow';
import { isUniTableOperationColumn } from '../../../../../components/uni-action/operationColumn';
import { resolveLayoutPlan } from '../../../../../components/uni-table/uniTableLayoutEngine';
import {
  resolveUniTableEmptyOperationColumnWidth,
  resolveUniTableOperationColumnWidth,
  resolveUniTableOperationWidthFromContent,
} from '../../../../../utils/uniTableLayoutColumns';

export function workbenchKeepWidth(width: number) {
  return {
    width,
    minWidth: width,
    uniTableKeepWidth: true,
    resizable: false,
    ellipsis: true,
  } as const;
}

export function workbenchRemainderFlex(minWidth = 120) {
  return {
    minWidth,
    uniTableRemainderFlex: true,
    uniTablePrimaryFlex: true,
    resizable: false,
    ellipsis: true,
  } as const;
}

function wrapWorkbenchOperationColumnOnCell(
  col: Record<string, unknown>,
  opColKey: string,
): Record<string, unknown> {
  const baseOnCell = col.onCell;
  const mergedOnCell =
    baseOnCell && typeof baseOnCell === 'function'
      ? (record: unknown, rowIndex?: number) => {
          const base = (baseOnCell as (r: unknown, i?: number) => Record<string, unknown>)(
            record,
            rowIndex,
          );
          return {
            ...base,
            className: `uni-table-operation-cell ${base?.className || ''}`.trim(),
            style: { whiteSpace: 'nowrap', ...(base?.style || {}) },
            'data-uni-op-col': opColKey,
          };
        }
      : () => ({
          className: 'uni-table-operation-cell',
          style: { whiteSpace: 'nowrap' },
          'data-uni-op-col': opColKey,
        });
  return { ...col, onCell: mergedOnCell, resizable: false, ellipsis: false };
}

function resolveWorkbenchOperationColumnWidth(
  col: Record<string, unknown>,
  measuredWidths: Record<string, number>,
  rowCount: number,
): number {
  const opColKey = String(col.key ?? 'option');
  const measured = measuredWidths[opColKey];
  if (measured != null && measured > 0) return measured;
  if (rowCount === 0) return resolveUniTableEmptyOperationColumnWidth();
  return (
    resolveUniTableOperationColumnWidth({
      fixed: col.fixed,
      uniActionRenderOptions: col.uniActionRenderOptions,
    }) ?? resolveUniTableEmptyOperationColumnWidth()
  );
}

function prepareWorkbenchTableColumns<T>(
  columns: ColumnsType<T>,
  measuredOperationWidths: Record<string, number>,
  rowCount: number,
): ColumnsType<T> {
  return columns.map((col) => {
    if (!isUniTableOperationColumn(col)) return col;
    const raw = col as Record<string, unknown>;
    const opColKey = String(raw.key ?? 'option');
    const width = resolveWorkbenchOperationColumnWidth(raw, measuredOperationWidths, rowCount);
    return wrapWorkbenchOperationColumnOnCell(
      {
        ...raw,
        width,
        minWidth: width,
        uniTableKeepWidth: true,
      },
      opColKey,
    ) as (typeof columns)[number];
  });
}

export function useDeliveryWorkbenchTableLayout<T>(
  columns: ColumnsType<T>,
  containerRef: RefObject<HTMLElement | null>,
  rowCount: number,
): { columns: ColumnsType<T>; scrollX: number | undefined } {
  const [layoutWidth, setLayoutWidth] = useState(0);
  const [measuredOperationWidths, setMeasuredOperationWidths] = useState<Record<string, number>>({});

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const sync = () => setLayoutWidth(el.clientWidth);
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, [containerRef]);

  useLayoutEffect(() => {
    const root = containerRef.current;
    if (!root) return;

    const measure = () => {
      const operationWidths: Record<string, number> = {};
      root.querySelectorAll<HTMLElement>('td[data-uni-op-col]').forEach((cell) => {
        const colKey = cell.dataset.uniOpCol;
        if (!colKey) return;
        const strip = cell.querySelector<HTMLElement>(`.${ROW_ACTIONS_STRIP_CLASS}`);
        if (!strip) return;
        const contentPx = Math.max(strip.scrollWidth, strip.getBoundingClientRect().width);
        const width = resolveUniTableOperationWidthFromContent(contentPx);
        if (!(width > 0)) return;
        operationWidths[colKey] = Math.max(operationWidths[colKey] ?? 0, width);
      });
      if (rowCount === 0) {
        setMeasuredOperationWidths((prev) => (Object.keys(prev).length === 0 ? prev : {}));
        return;
      }
      setMeasuredOperationWidths((prev) => {
        const changed = Object.keys(operationWidths).some((k) => prev[k] !== operationWidths[k]);
        return changed ? { ...prev, ...operationWidths } : prev;
      });
    };

    measure();
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => measure()) : null;
    const tbody = root.querySelector('.ant-table-tbody');
    if (ro && tbody) ro.observe(tbody);
    return () => ro?.disconnect();
  }, [containerRef, rowCount, columns]);

  return useMemo(() => {
    const prepared = prepareWorkbenchTableColumns(columns, measuredOperationWidths, rowCount);
    if (layoutWidth <= 0) {
      return { columns: prepared, scrollX: undefined };
    }
    const plan = resolveLayoutPlan({
      columns: prepared as Record<string, unknown>[],
      containerWidth: layoutWidth,
      includeSelection: false,
      includeExpandable: false,
      scrollYEnabled: false,
      layoutWidthIsScrollHost: true,
    });
    const scrollX = plan.scrollX > layoutWidth ? plan.scrollX : undefined;
    return {
      columns: plan.columns as ColumnsType<T>,
      scrollX,
    };
  }, [columns, layoutWidth, measuredOperationWidths, rowCount]);
}
