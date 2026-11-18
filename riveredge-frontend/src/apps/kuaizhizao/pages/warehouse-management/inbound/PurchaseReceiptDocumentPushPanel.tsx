/**
 * 采购入库外推：DocumentPushBatchPanel（source=purchase_receipt → kingdee_im_purinbill）。
 */
import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { ApplicationConnection } from '../../../../../services/applicationConnection';
import type { API } from '../../../../../services/apiManagement';
import { DocumentPushBatchPanel } from '../../../components/DocumentPushBatchPanel';
import { warehouseApi } from '../../../services/production';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';

export interface PurchaseReceiptPushCandidate {
  id: number;
  receipt_code?: string;
  supplier_name?: string;
  warehouse_name?: string;
  status?: string;
  total_quantity?: number;
  receipt_time?: string;
}

export interface PurchaseReceiptDocumentPushPanelProps {
  open: boolean;
  onClose: () => void;
  receiptIds?: number[];
  onComplete?: () => void;
  embedded?: boolean;
}

const PR_DEFAULT_PROFILES: string[] = [];
const PR_KINGDEE_PROFILES = ['kingdee_im_purinbill'];
const PR_SAVE_API_HINTS = ['purinbill', '采购入库', 'im_purinbill', 'add_im_purinbill'];

const PUSHABLE_STATUSES = new Set(['已入库', '已完成', 'processed', 'COMPLETED', 'POSTED']);

function isKingdeeImPurinbillAddApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connection) return false;
  if (api.connection_uuid && api.connection_uuid !== connection.uuid) return false;
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  const hay = `${code} ${path} ${name}`;
  if (code.includes('add_im_purinbill') || code.includes('push_im_purinbill')) return true;
  const isAdd = path.includes('/add') || hay.includes('add');
  const isPurIn =
    hay.includes('purinbill') ||
    hay.includes('im_purinbill') ||
    name.includes('采购入库');
  return isAdd && isPurIn;
}

function preferPurinbillApiUuid(items: API[]): string | undefined {
  const preferred =
    items.find((api) => String(api.code || '').toLowerCase().includes('add_im_purinbill')) ||
    items.find((api) => String(api.code || '').toLowerCase().includes('push_im_purinbill')) ||
    items.find((api) => String(api.path || '').toLowerCase().includes('im_purinbill')) ||
    items.find((api) => String(api.name || '').includes('采购入库')) ||
    items[0];
  return preferred?.uuid;
}

function isPushableReceipt(row: { status?: string }): boolean {
  const status = String(row.status || '').trim();
  return PUSHABLE_STATUSES.has(status) || PUSHABLE_STATUSES.has(status.toUpperCase());
}

function toCandidate(row: Record<string, unknown>): PurchaseReceiptPushCandidate | null {
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  if (!isPushableReceipt({ status: String(row.status || '') })) return null;
  return {
    id,
    receipt_code: row.receipt_code != null ? String(row.receipt_code) : undefined,
    supplier_name: row.supplier_name != null ? String(row.supplier_name) : undefined,
    warehouse_name: row.warehouse_name != null ? String(row.warehouse_name) : undefined,
    status: row.status != null ? String(row.status) : undefined,
    total_quantity: row.total_quantity != null ? Number(row.total_quantity) : undefined,
    receipt_time: row.receipt_time != null ? String(row.receipt_time) : undefined,
  };
}

export const PurchaseReceiptDocumentPushPanel: React.FC<PurchaseReceiptDocumentPushPanelProps> = ({
  open,
  onClose,
  receiptIds,
  onComplete,
  embedded = false,
}) => {
  const { t } = useTranslation();

  const columns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.warehouseInbound.col.docNo'),
        dataIndex: 'receipt_code',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.supplier'),
        dataIndex: 'supplier_name',
        width: 140,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.warehouse'),
        dataIndex: 'warehouse_name',
        width: 120,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.warehouseInbound.col.lifecycle'),
        dataIndex: 'status',
        width: 100,
        render: (v: string | undefined) => renderDocumentStatusTag(v),
      },
    ],
    [t],
  );

  const loadCandidates = useCallback(
    async ({
      keyword,
      page,
      pageSize,
      preferIds,
    }: {
      keyword: string;
      page: number;
      pageSize: number;
      preferIds: number[];
    }) => {
      const res = await warehouseApi.purchaseReceipt.list({
        keyword: keyword || undefined,
        status: '已入库',
        skip: Math.max(0, (page - 1) * pageSize),
        limit: pageSize,
      });
      let data = ((res.items || []) as Record<string, unknown>[])
        .map(toCandidate)
        .filter((row): row is PurchaseReceiptPushCandidate => !!row);

      if (preferIds.length && page === 1) {
        const preferSet = new Set(preferIds);
        const preferred = data.filter((row) => preferSet.has(row.id));
        const rest = data.filter((row) => !preferSet.has(row.id));
        data = [...preferred, ...rest];
      }

      return { data, total: res.total || data.length };
    },
    [],
  );

  if (!open) return null;

  return (
    <DocumentPushBatchPanel<PurchaseReceiptPushCandidate>
      open={open}
      onClose={onClose}
      onComplete={onComplete}
      embedded={embedded}
      preferIds={receiptIds}
      sourceType="purchase_receipt"
      defaultProfiles={PR_DEFAULT_PROFILES}
      kingdeeProfiles={PR_KINGDEE_PROFILES}
      title={t('app.kuaizhizao.warehouseInbound.documentPush.title')}
      hint={t('app.kuaizhizao.warehouseInbound.documentPush.hint')}
      pipelineDesc={t('app.kuaizhizao.warehouseInbound.documentPush.pipelineDesc')}
      searchPlaceholder={t('app.kuaizhizao.warehouseInbound.documentPush.searchPlaceholder')}
      needSelectMessage={t('app.kuaizhizao.warehouseInbound.documentPush.needSelect')}
      confirmText={t('app.kuaizhizao.documentPush.batch.confirm')}
      columns={columns}
      getRowLabel={(row) => row.receipt_code || String(row.id)}
      loadCandidates={loadCandidates}
      matchSaveApi={isKingdeeImPurinbillAddApi}
      preferSaveApi={preferPurinbillApiUuid}
      saveApiSearchHints={PR_SAVE_API_HINTS}
      showScheduleControls={false}
      successCountKey="app.kuaizhizao.documentPush.batch.success"
      partialCountKey="app.kuaizhizao.documentPush.batch.partial"
      failedTitleKey="app.kuaizhizao.documentPush.pushFailed"
      skippedHintKey="app.kuaizhizao.documentPush.batch.skippedHint"
    />
  );
};

export default PurchaseReceiptDocumentPushPanel;
