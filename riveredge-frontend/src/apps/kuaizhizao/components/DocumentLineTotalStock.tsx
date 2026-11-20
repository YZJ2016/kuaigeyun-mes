/**
 * 单据明细：选料后展示总库存；hover 展开各仓在库结存。
 */
import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Popover, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER } from './document-detail-table/documentDetailTable';
import { formatQuantity } from '../../../utils/format';
import { getMaterialLineWarehouseStock } from '../services/material-line-stock';

export type DocumentLineWarehouseStockLine = { warehouse_name: string; quantity: number };

type StockContextValue = {
  loadingIds: ReadonlySet<number>;
  errorIds: ReadonlySet<number>;
  byMaterial: Record<number, DocumentLineWarehouseStockLine[]>;
};

const DocumentLineTotalStockContext = createContext<StockContextValue | null>(null);

function WarehouseStockPopoverContent({ lines }: { lines: DocumentLineWarehouseStockLine[] }) {
  return (
    <div style={{ maxWidth: 320, fontSize: 12 }}>
      {lines.map((line, idx) => (
        <div
          key={`${line.warehouse_name}-${idx}`}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            gap: 16,
            marginBottom: idx < lines.length - 1 ? 6 : 0,
          }}
        >
          <span>{line.warehouse_name}</span>
          <Typography.Text strong>{formatQuantity(line.quantity)}</Typography.Text>
        </div>
      ))}
    </div>
  );
}

function DocumentLineTotalStockCellStandalone({ materialId }: { materialId: number | null | undefined }) {
  const { t } = useTranslation();
  const mid = materialId != null ? Number(materialId) : 0;
  const [lines, setLines] = useState<DocumentLineWarehouseStockLine[] | undefined>(undefined);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!mid) {
      setLines(undefined);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void getMaterialLineWarehouseStock([mid])
      .then((res) => {
        if (cancelled) return;
        const raw = res.by_material?.[String(mid)] ?? res.by_material?.[mid as unknown as string];
        setLines(parseStockLines(raw));
      })
      .catch(() => {
        if (!cancelled) setLines([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mid]);

  if (!mid) return <span>{DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER}</span>;
  if (loading) {
    return (
      <Typography.Text type="secondary">{t('app.kuaizhizao.documentDetail.stockLoading')}</Typography.Text>
    );
  }
  if (!lines?.length) {
    return (
      <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap' }}>
        {t('app.kuaizhizao.documentDetail.stockEmpty')}
      </Typography.Text>
    );
  }
  const total = lines.reduce((sum, line) => sum + (Number(line.quantity) || 0), 0);
  return (
    <Popover
      title={t('app.kuaizhizao.documentDetail.warehouseStock')}
      content={<WarehouseStockPopoverContent lines={lines} />}
      trigger="hover"
      mouseEnterDelay={0.2}
    >
      <span style={{ cursor: 'help', borderBottom: '1px dashed rgba(0, 0, 0, 0.22)' }}>
        {formatQuantity(total)}
      </span>
    </Popover>
  );
}

function parseMaterialIds(idsKey: string): number[] {
  return idsKey
    .split(',')
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((id) => Number.isFinite(id) && id > 0);
}

function parseStockLines(
  lines: Array<{ warehouse_name?: string; quantity?: number }> | undefined,
): DocumentLineWarehouseStockLine[] {
  return (lines ?? []).map((line) => ({
    warehouse_name: String(line.warehouse_name ?? '').trim() || DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER,
    quantity: Number(line.quantity) || 0,
  }));
}

export function DocumentLineTotalStockProvider({
  materialIds,
  children,
}: {
  materialIds: number[];
  children: React.ReactNode;
}) {
  const idsKey = useMemo(
    () =>
      [...new Set(materialIds.filter((id) => Number.isFinite(id) && id > 0))]
        .sort((a, b) => a - b)
        .join(','),
    [materialIds],
  );
  const [byMaterial, setByMaterial] = useState<Record<number, DocumentLineWarehouseStockLine[]>>({});
  const [loadingIds, setLoadingIds] = useState<ReadonlySet<number>>(() => new Set());
  const [errorIds, setErrorIds] = useState<ReadonlySet<number>>(() => new Set());
  const loadedRef = useRef<Set<number>>(new Set());
  const inflightRef = useRef<Set<number>>(new Set());
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const mids = parseMaterialIds(idsKey);
    const missing = mids.filter((id) => !loadedRef.current.has(id) && !inflightRef.current.has(id));
    if (!missing.length) return;
    missing.forEach((id) => inflightRef.current.add(id));
    setLoadingIds((prev) => {
      const next = new Set(prev);
      missing.forEach((id) => next.add(id));
      return next;
    });
    setErrorIds((prev) => {
      if (!missing.some((id) => prev.has(id))) return prev;
      const next = new Set(prev);
      missing.forEach((id) => next.delete(id));
      return next;
    });
    void getMaterialLineWarehouseStock(missing)
      .then((res) => {
        if (!mountedRef.current) return;
        const parsed: Record<number, DocumentLineWarehouseStockLine[]> = {};
        for (const id of missing) parsed[id] = [];
        const raw = res.by_material ?? {};
        for (const [key, lines] of Object.entries(raw)) {
          const mid = Number(key);
          if (!Number.isFinite(mid) || mid <= 0) continue;
          parsed[mid] = parseStockLines(lines);
        }
        missing.forEach((id) => loadedRef.current.add(id));
        setByMaterial((prev) => ({ ...prev, ...parsed }));
      })
      .catch(() => {
        if (!mountedRef.current) return;
        setErrorIds((prev) => {
          const next = new Set(prev);
          missing.forEach((id) => next.add(id));
          return next;
        });
      })
      .finally(() => {
        missing.forEach((id) => inflightRef.current.delete(id));
        if (!mountedRef.current) return;
        setLoadingIds((prev) => {
          const next = new Set(prev);
          missing.forEach((id) => next.delete(id));
          return next;
        });
      });
  }, [idsKey]);

  const value = useMemo(() => ({ loadingIds, errorIds, byMaterial }), [loadingIds, errorIds, byMaterial]);

  return (
    <DocumentLineTotalStockContext.Provider value={value}>{children}</DocumentLineTotalStockContext.Provider>
  );
}

export function DocumentLineTotalStockCell({ materialId }: { materialId: number | null | undefined }) {
  const ctx = useContext(DocumentLineTotalStockContext);
  if (!ctx) {
    return <DocumentLineTotalStockCellStandalone materialId={materialId} />;
  }
  const { t } = useTranslation();
  const { loadingIds, errorIds, byMaterial } = ctx;
  const mid = materialId != null ? Number(materialId) : 0;
  if (!mid) return <span>{DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER}</span>;

  const lines = byMaterial[mid];
  if (lines === undefined && loadingIds.has(mid)) {
    return (
      <Typography.Text type="secondary">{t('app.kuaizhizao.documentDetail.stockLoading')}</Typography.Text>
    );
  }
  if (lines === undefined && errorIds.has(mid)) {
    return <Typography.Text type="secondary">{DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER}</Typography.Text>;
  }
  if (lines === undefined) {
    return <span>{DOCUMENT_DETAIL_LINE_EMPTY_PLACEHOLDER}</span>;
  }
  if (!lines.length) {
    return (
      <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap' }}>
        {t('app.kuaizhizao.documentDetail.stockEmpty')}
      </Typography.Text>
    );
  }

  const total = lines.reduce((sum, line) => sum + (Number(line.quantity) || 0), 0);

  return (
    <Popover
      title={t('app.kuaizhizao.documentDetail.warehouseStock')}
      content={<WarehouseStockPopoverContent lines={lines} />}
      trigger="hover"
      mouseEnterDelay={0.2}
    >
      <span style={{ cursor: 'help', borderBottom: '1px dashed rgba(0, 0, 0, 0.22)' }}>
        {formatQuantity(total)}
      </span>
    </Popover>
  );
}