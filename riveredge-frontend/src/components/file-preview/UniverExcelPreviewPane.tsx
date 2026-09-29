import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Alert, Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { fetchCoreFileBytes } from '../../utils/fetchCoreFileBytes';
import type { FilePreviewSource } from '../../utils/filePreviewKind';
import {
  createUniverSheetInstance,
  relayoutUniverSheet,
  runAfterUniverSheetsRenderServiceInit,
  type UniverSheetInstance,
} from '../univer/bootstrap-sheet';

const EXCEL_PREVIEW_MAX_ROWS = 2000;

export interface UniverExcelPreviewPaneProps {
  fileUrl?: string;
  fileUuid?: string;
  fileSource: FilePreviewSource;
  height?: string | number;
}

type PreviewSheet = {
  id: string;
  name: string;
  cellData: Record<string, Record<string, { v: string; m: string }>>;
  rowCount: number;
  columnCount: number;
};

function toArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength);
  copy.set(bytes);
  return copy.buffer;
}

function trimTrailingEmptyRows(rows: unknown[][]): unknown[][] {
  let end = rows.length;
  while (end > 0) {
    const row = rows[end - 1];
    const hasValue = row?.some((cell) => String(cell ?? '').trim() !== '');
    if (hasValue) break;
    end -= 1;
  }
  return rows.slice(0, end);
}

function rowsToCellData(rows: string[][]): PreviewSheet['cellData'] {
  const cellData: PreviewSheet['cellData'] = {};
  rows.forEach((row, r) => {
    const rowCells: Record<string, { v: string; m: string }> = {};
    row.forEach((cell, c) => {
      rowCells[String(c)] = { v: cell, m: cell };
    });
    cellData[String(r)] = rowCells;
  });
  return cellData;
}

async function parseExcelWorkbook(buffer: ArrayBuffer): Promise<{ sheets: PreviewSheet[]; truncated: boolean }> {
  const XLSX = await import('xlsx');
  const workbook = XLSX.read(buffer, { type: 'array' });
  let truncated = false;
  const sheets: PreviewSheet[] = workbook.SheetNames.map((name, index) => {
    const sheet = workbook.Sheets[name];
    const raw = XLSX.utils.sheet_to_json(sheet, {
      header: 1,
      defval: '',
      raw: false,
    }) as unknown[][];
    const trimmed = trimTrailingEmptyRows(raw);
    if (trimmed.length > EXCEL_PREVIEW_MAX_ROWS) {
      truncated = true;
    }
    const limited = trimmed.slice(0, EXCEL_PREVIEW_MAX_ROWS);
    const dataColCount = limited.length
      ? Math.max(1, ...limited.map((row) => (Array.isArray(row) ? row.length : 0)))
      : 1;
    const rows = limited.map((row) => {
      const arr = Array.isArray(row) ? row : [];
      return Array.from({ length: dataColCount }, (_, i) => {
        const v = arr[i];
        return v === null || v === undefined ? '' : String(v);
      });
    });
    const rowCount = Math.max(rows.length, 1);
    const columnCount = Math.max(dataColCount, 1);
    return {
      id: `sheet-${index}`,
      name: name || `Sheet${index + 1}`,
      cellData: rowsToCellData(rows),
      rowCount,
      columnCount,
    };
  });
  return { sheets, truncated };
}

function safeDisposeUniver(instance: UniverSheetInstance | null | undefined) {
  if (!instance) return;
  try {
    instance.univer.dispose();
  } catch (error: unknown) {
    const msg = error instanceof Error ? error.message : String(error);
    if (
      msg.includes("Failed to execute 'removeChild' on 'Node'")
      || msg.includes('getSheetBySheetId')
    ) {
      return;
    }
    console.warn('univer dispose failed:', error);
  }
}

export const UniverExcelPreviewPane: React.FC<UniverExcelPreviewPaneProps> = ({
  fileUrl,
  fileUuid,
  fileSource,
  height = '100%',
}) => {
  const { t } = useTranslation();
  const resolvedHeight = typeof height === 'number' ? `${height}px` : height;
  const hostRef = useRef<HTMLDivElement>(null);
  const instanceRef = useRef<UniverSheetInstance | null>(null);
  const mountSeqRef = useRef(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [sheets, setSheets] = useState<PreviewSheet[]>([]);
  const [truncated, setTruncated] = useState(false);

  useEffect(() => {
    if (!fileUrl && !fileUuid) {
      setLoading(false);
      setError(t('pages.system.files.previewLoadFailed'));
      return;
    }

    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError('');
      setSheets([]);
      setTruncated(false);
      try {
        const bytes = await fetchCoreFileBytes({
          fileUrl,
          fileUuid,
          errorLabel: t('pages.system.files.previewLoadFailed'),
        });
        if (cancelled) return;
        const parsed = await parseExcelWorkbook(toArrayBuffer(bytes));
        if (cancelled) return;
        if (parsed.sheets.length === 0) {
          throw new Error(t('pages.system.files.previewSheetEmpty'));
        }
        setSheets(parsed.sheets);
        setTruncated(parsed.truncated);
      } catch (e: unknown) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : t('pages.system.files.previewLoadFailed');
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [fileUrl, fileUuid, fileSource, t]);

  useLayoutEffect(() => {
    const host = hostRef.current;
    if (!host || sheets.length === 0 || error) {
      return undefined;
    }

    let active = true;
    const mountToken = ++mountSeqRef.current;
    host.textContent = '';
    const mountEl = document.createElement('div');
    mountEl.style.width = '100%';
    mountEl.style.maxWidth = '100%';
    mountEl.style.minWidth = '0';
    mountEl.style.height = '100%';
    mountEl.style.minHeight = '0';
    mountEl.style.boxSizing = 'border-box';
    const containerId = `univer-excel-preview-${mountToken}`;
    mountEl.id = containerId;
    host.appendChild(mountEl);

    let pendingInstance: UniverSheetInstance | null = null;
    try {
      pendingInstance = createUniverSheetInstance({ containerId });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('pages.system.files.previewLoadFailed');
      setError(msg);
      return undefined;
    }

    runAfterUniverSheetsRenderServiceInit(() => {
      if (!active || mountSeqRef.current !== mountToken || !pendingInstance) {
        safeDisposeUniver(pendingInstance);
        return;
      }
      const instance = pendingInstance;
      try {
        const sheetOrder = sheets.map((s) => s.id);
        const sheetMap: Record<string, Record<string, unknown>> = {};
        sheets.forEach((s) => {
          sheetMap[s.id] = {
            id: s.id,
            name: s.name,
            cellData: s.cellData,
            rowCount: s.rowCount,
            columnCount: s.columnCount,
            defaultColumnWidth: 120,
          };
        });
        instance.univerAPI.createWorkbook({
          id: containerId,
          name: fileSource.fileName || 'Excel',
          sheetOrder,
          sheets: sheetMap,
        });
        if (!active || mountSeqRef.current !== mountToken) {
          safeDisposeUniver(instance);
          return;
        }
        instanceRef.current = instance;
        // Modal 打开动画后尺寸才稳；先按宿主裁剪盒排一次
        relayoutUniverSheet(instance, host);
      } catch (e: unknown) {
        if (active) {
          const msg = e instanceof Error ? e.message : t('pages.system.files.previewLoadFailed');
          setError(msg);
        }
        safeDisposeUniver(instance);
      }
    });

    const observer = new ResizeObserver(() => {
      if (mountSeqRef.current !== mountToken) return;
      const current = instanceRef.current;
      if (current) relayoutUniverSheet(current, host);
    });
    observer.observe(host);

    return () => {
      active = false;
      if (mountSeqRef.current === mountToken) {
        mountSeqRef.current += 1;
      }
      observer.disconnect();
      const instance = instanceRef.current ?? pendingInstance;
      instanceRef.current = null;
      safeDisposeUniver(instance);
      if (host.contains(mountEl)) {
        host.removeChild(mountEl);
      } else {
        host.textContent = '';
      }
    };
  }, [sheets, error, fileSource.fileName, t]);

  if (loading && sheets.length === 0) {
    return (
      <div
        style={{
          height: resolvedHeight,
          minHeight: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Spin description={t('pages.system.files.previewLoading')}>
          <div style={{ minHeight: 24 }} />
        </Spin>
      </div>
    );
  }

  if (error) {
    return <Alert type="error" title={error} showIcon style={{ margin: 16 }} />;
  }

  return (
    <div
      className="uni-excel-preview-root"
      style={{
        height: resolvedHeight,
        maxHeight: '100%',
        minHeight: 0,
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        overflow: 'hidden',
        flex: 1,
        background: '#fff',
      }}
    >
      {truncated ? (
        <Alert
          type="info"
          showIcon
          title={t('pages.system.files.previewRowsTruncated', { count: EXCEL_PREVIEW_MAX_ROWS })}
          style={{ margin: 12, marginBottom: 0, flexShrink: 0 }}
        />
      ) : null}
      <div
        className="uni-excel-preview-host"
        ref={hostRef}
        style={{
          flex: 1,
          height: '100%',
          maxHeight: '100%',
          minHeight: 0,
          minWidth: 0,
          width: '100%',
          maxWidth: '100%',
          overflow: 'hidden',
          boxSizing: 'border-box',
        }}
      />
    </div>
  );
};
