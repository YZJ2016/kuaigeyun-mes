/**
 * 销售出库外推：DocumentPushBatchPanel（source=sales_delivery → kingdee_im_saloutbill）。
 */
import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { ApplicationConnection } from '../../../../../services/applicationConnection';
import type { API } from '../../../../../services/apiManagement';
import { DocumentPushBatchPanel } from '../../../components/DocumentPushBatchPanel';
import { warehouseApi } from '../../../services/production';
import { normalizeWarehouseListResponse } from '../../../utils/warehouseListCore';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';

export interface SalesDeliveryPushCandidate {
  id: number;
  delivery_code?: string;
  customer_name?: string;
  warehouse_name?: string;
  status?: string;
  total_quantity?: number;
  delivery_time?: string;
}

export interface SalesDeliveryDocumentPushPanelProps {
  open: boolean;
  onClose: () => void;
  deliveryIds?: number[];
  onComplete?: () => void;
  embedded?: boolean;
}

const SD_DEFAULT_PROFILES: string[] = [];
const SD_KINGDEE_PROFILES = ['kingdee_im_saloutbill'];
const SD_SAVE_API_HINTS = ['saloutbill', '销售出库', 'im_saloutbill', 'batch_add_im_saloutbill'];

const PUSHABLE_STATUSES = new Set(['已出库', '已完成', 'processed', 'COMPLETED', 'POSTED']);

function isKingdeeImSaloutbillBatchAddApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connection) return false;
  if (api.connection_uuid && api.connection_uuid !== connection.uuid) return false;
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  const hay = `${code} ${path} ${name}`;
  if (code.includes('batch_add_im_saloutbill') || code.includes('push_im_saloutbill')) return true;
  const isBatchAdd = path.includes('/batchadd') || hay.includes('batchadd') || hay.includes('batch_add');
  const isSalOut =
    hay.includes('saloutbill') ||
    hay.includes('im_saloutbill') ||
    name.includes('销售出库');
  return isBatchAdd && isSalOut;
}

function preferSaloutbillApiUuid(items: API[]): string | undefined {
  const preferred =
    items.find((api) => String(api.code || '').toLowerCase().includes('batch_add_im_saloutbill')) ||
    items.find((api) => String(api.code || '').toLowerCase().includes('push_im_saloutbill')) ||
    items.find((api) => String(api.path || '').toLowerCase().includes('im_saloutbill')) ||
    items.find((api) => String(api.name || '').includes('销售出库')) ||
    items[0];
  return preferred?.uuid;
}

function isPushableDelivery(row: { status?: string }): boolean {
  const status = String(row.status || '').trim();
  return PUSHABLE_STATUSES.has(status) || PUSHABLE_STATUSES.has(status.toUpperCase());
}

function toCandidate(row: Record<string, unknown>): SalesDeliveryPushCandidate | null {
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  if (!isPushableDelivery({ status: String(row.status || '') })) return null;
  return {
    id,
    delivery_code: row.delivery_code != null ? String(row.delivery_code) : undefined,
    customer_name: row.customer_name != null ? String(row.customer_name) : undefined,
    warehouse_name: row.warehouse_name != null ? String(row.warehouse_name) : undefined,
    status: row.status != null ? String(row.status) : undefined,
    total_quantity: row.total_quantity != null ? Number(row.total_quantity) : undefined,
    delivery_time: row.delivery_time != null ? String(row.delivery_time) : undefined,
  };
}

export const SalesDeliveryDocumentPushPanel: React.FC<SalesDeliveryDocumentPushPanelProps> = ({
  open,
  onClose,
  deliveryIds,
  onComplete,
  embedded = false,
}) => {
  const { t } = useTranslation();

  const columns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.outboundCode'),
        dataIndex: 'delivery_code',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.customer'),
        dataIndex: 'customer_name',
        width: 140,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.warehouse'),
        dataIndex: 'warehouse_name',
        width: 120,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.lifecycle'),
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
      const res = await warehouseApi.salesDelivery.list({
        keyword: keyword || undefined,
        status: '已出库',
        skip: Math.max(0, (page - 1) * pageSize),
        limit: pageSize,
      });
      const { data: rows, total } = normalizeWarehouseListResponse(res);
      let data = (rows as Record<string, unknown>[])
        .map(toCandidate)
        .filter((row): row is SalesDeliveryPushCandidate => !!row);

      if (preferIds.length && page === 1) {
        const preferSet = new Set(preferIds);
        const preferred = data.filter((row) => preferSet.has(row.id));
        const rest = data.filter((row) => !preferSet.has(row.id));
        data = [...preferred, ...rest];
      }

      return { data, total: total || data.length };
    },
    [],
  );

  if (!open) return null;

  return (
    <DocumentPushBatchPanel<SalesDeliveryPushCandidate>
      open={open}
      onClose={onClose}
      onComplete={onComplete}
      embedded={embedded}
      preferIds={deliveryIds}
      sourceType="sales_delivery"
      defaultProfiles={SD_DEFAULT_PROFILES}
      kingdeeProfiles={SD_KINGDEE_PROFILES}
      title={t('app.kuaizhizao.warehouseOutbound.documentPush.title')}
      hint={t('app.kuaizhizao.warehouseOutbound.documentPush.hint')}
      pipelineDesc={t('app.kuaizhizao.warehouseOutbound.documentPush.pipelineDesc')}
      searchPlaceholder={t('app.kuaizhizao.warehouseOutbound.documentPush.searchPlaceholder')}
      needSelectMessage={t('app.kuaizhizao.warehouseOutbound.documentPush.needSelect')}
      confirmText={t('app.kuaizhizao.documentPush.batch.confirm')}
      columns={columns}
      getRowLabel={(row) => row.delivery_code || String(row.id)}
      loadCandidates={loadCandidates}
      matchSaveApi={isKingdeeImSaloutbillBatchAddApi}
      preferSaveApi={preferSaloutbillApiUuid}
      saveApiSearchHints={SD_SAVE_API_HINTS}
      showScheduleControls={false}
      successCountKey="app.kuaizhizao.documentPush.batch.success"
      partialCountKey="app.kuaizhizao.documentPush.batch.partial"
      failedTitleKey="app.kuaizhizao.documentPush.pushFailed"
      skippedHintKey="app.kuaizhizao.documentPush.batch.skippedHint"
    />
  );
};

export default SalesDeliveryDocumentPushPanel;
