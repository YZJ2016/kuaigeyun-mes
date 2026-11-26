/**
 * 采购对账报表订单展开明细
 */
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { App, Spin, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useTranslation } from 'react-i18next';
import { formatCurrencyAmount, formatDateBySiteSetting } from '../../../../../utils/format';
import {
  getPurchaseReconciliationOrderDetail,
  type PurchaseReconciliationOrderDetailResponse,
} from '../../../services/reports';
import { LinkedDocumentAutoCell } from '../../../../../components/linked-document-code/LinkedDocumentAutoCell';
import type { LinkedCodeBinding } from '../../../utils/linkedDocumentAutoLink';

const PS = 'app.kuaizhizao.purchaseReports.reconciliationDetail';

export type PurchaseReconRow = {
  id: number;
  order_code: string;
};

type DetailCacheEntry = {
  loading?: boolean;
  data?: PurchaseReconciliationOrderDetailResponse;
};

function detailCacheKey(id: number): string {
  return `po-${id}`;
}

const money = (v: number | null | undefined) =>
  v == null ? '—' : formatCurrencyAmount(v);

const RECEIPT_BINDING: LinkedCodeBinding = {
  documentType: 'purchase_receipt',
  idField: 'doc_id',
  codeField: 'doc_code',
};

export function usePurchaseReconciliationOrderDetail() {
  const { t } = useTranslation();
  const { message } = App.useApp();
  const [cache, setCache] = useState<Record<string, DetailCacheEntry>>({});
  const inflightRef = useRef<Map<string, Promise<void>>>(new Map());

  const clearCache = useCallback(() => {
    inflightRef.current.clear();
    setCache({});
  }, []);

  const loadOrderDetail = useCallback(
    async (row: PurchaseReconRow) => {
      const key = detailCacheKey(row.id);
      const inflight = inflightRef.current.get(key);
      if (inflight) {
        await inflight;
        return;
      }

      let alreadyLoaded = false;
      setCache((prev) => {
        if (prev[key]?.data) {
          alreadyLoaded = true;
          return prev;
        }
        return { ...prev, [key]: { loading: true } };
      });
      if (alreadyLoaded) return;

      const task = (async () => {
        try {
          const data = await getPurchaseReconciliationOrderDetail(row.id);
          setCache((prev) => ({ ...prev, [key]: { data } }));
        } catch (e: unknown) {
          const err = e as { message?: string };
          message.error(err?.message || t(`${PS}.loadFailed`));
          setCache((prev) => ({
            ...prev,
            [key]: { data: { items: [], related_documents: [] } },
          }));
        } finally {
          inflightRef.current.delete(key);
        }
      })();

      inflightRef.current.set(key, task);
      await task;
    },
    [message, t],
  );

  return { cache, loadOrderDetail, clearCache };
}

function useMaterialLineColumns(): ColumnsType<PurchaseReconciliationOrderDetailResponse['items'][number]> {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { title: t('app.kuaizhizao.reports.materialCode'), dataIndex: 'material_code', width: 120 },
      { title: t('app.kuaizhizao.reports.materialName'), dataIndex: 'material_name', ellipsis: true },
      {
        title: t('app.kuaizhizao.reports.materialSpec'),
        dataIndex: 'material_spec',
        width: 120,
        ellipsis: true,
        render: (v: string) => (v && String(v).trim() ? v : '—'),
      },
      { title: t('common.unit'), dataIndex: 'unit', width: 64 },
      {
        title: t('app.kuaizhizao.purchaseReports.colOrderQty'),
        dataIndex: 'quantity',
        width: 96,
        align: 'right',
      },
      {
        title: t('app.kuaizhizao.purchaseReports.colReceiptQty'),
        dataIndex: 'received_quantity',
        width: 96,
        align: 'right',
      },
      {
        title: t('app.kuaizhizao.reports.unitPrice'),
        dataIndex: 'unit_price',
        width: 100,
        align: 'right',
        render: (_, r) => money(r.unit_price),
      },
      {
        title: t('app.kuaizhizao.reports.amount'),
        dataIndex: 'amount',
        width: 110,
        align: 'right',
        render: (_, r) => money(r.amount),
      },
    ],
    [t],
  );
}

function useRelatedDocColumns(): ColumnsType<PurchaseReconciliationOrderDetailResponse['related_documents'][number]> {
  const { t } = useTranslation();
  return useMemo(
    () => [
      {
        title: t(`${PS}.docKind`),
        dataIndex: 'doc_kind',
        width: 100,
        render: (kind: string) => t(`${PS}.docKind.${kind}`, { defaultValue: kind }),
      },
      {
        title: t(`${PS}.docCode`),
        dataIndex: 'doc_code',
        width: 140,
        render: (code: string, record) => {
          if (record.doc_kind === 'purchase_receipt') {
            return (
              <LinkedDocumentAutoCell
                binding={RECEIPT_BINDING}
                record={record as unknown as Record<string, unknown>}
                ellipsis={false}
              />
            );
          }
          return code || '—';
        },
      },
      {
        title: t(`${PS}.docDate`),
        dataIndex: 'doc_date',
        width: 110,
        render: (v: string | null) => (v ? formatDateBySiteSetting(v) : '—'),
      },
      {
        title: t(`${PS}.amount`),
        dataIndex: 'amount',
        width: 110,
        align: 'right',
        render: (_, r) => money(r.amount),
      },
      {
        title: t('app.kuaizhizao.purchaseReports.colPaidAmount'),
        dataIndex: 'paid_amount',
        width: 110,
        align: 'right',
        render: (v: number | undefined, r) =>
          r.doc_kind === 'payable' ? money(v) : '—',
      },
    ],
    [t],
  );
}

type ExpandedProps = {
  row: PurchaseReconRow;
  entry?: DetailCacheEntry;
};

export const PurchaseReconciliationExpandedRow: React.FC<ExpandedProps> = ({ row, entry }) => {
  const { t } = useTranslation();
  const materialColumns = useMaterialLineColumns();
  const relatedColumns = useRelatedDocColumns();

  if (entry?.loading && !entry.data) {
    return <Spin size="small" />;
  }

  const items = entry?.data?.items ?? [];
  const related = entry?.data?.related_documents ?? [];

  return (
    <div style={{ padding: '8px 0 12px' }}>
      <DetailSection title={t(`${PS}.materialLinesTitle`)}>
        <Table
          size="small"
          rowKey={(_r, idx) => `${row.id}-mat-${idx}`}
          pagination={false}
          dataSource={items}
          columns={materialColumns}
          scroll={{ x: 900 }}
          locale={{ emptyText: t(`${PS}.emptyLines`) }}
        />
      </DetailSection>
      {related.length > 0 ? (
        <DetailSection title={t(`${PS}.relatedDocsTitle`)} style={{ marginTop: 12 }}>
          <Table
            size="small"
            rowKey={(r) => `${r.doc_kind}-${r.doc_id}`}
            pagination={false}
            dataSource={related}
            columns={relatedColumns}
            scroll={{ x: 640 }}
          />
        </DetailSection>
      ) : null}
    </div>
  );
};

function DetailSection({
  title,
  children,
  style,
}: {
  title: string;
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div style={style}>
      <div style={{ marginBottom: 6, fontWeight: 500, color: 'rgba(0,0,0,0.85)' }}>{title}</div>
      {children}
    </div>
  );
}

export function purchaseReconciliationExpandableProps(
  cache: Record<string, DetailCacheEntry>,
  loadOrderDetail: (row: PurchaseReconRow) => void | Promise<void>,
) {
  return {
    rowExpandable: (record: PurchaseReconRow) => Number(record.id) > 0,
    onExpand: (expanded: boolean, record: PurchaseReconRow) => {
      if (expanded) void loadOrderDetail(record);
    },
    expandedRowRender: (record: PurchaseReconRow) => {
      const key = detailCacheKey(record.id);
      return (
        <PurchaseReconciliationExpandedRow row={record} entry={key ? cache[key] : undefined} />
      );
    },
  };
}