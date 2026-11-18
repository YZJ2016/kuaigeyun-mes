/**
 * 盘点外推：DocumentPushBatchPanel
 * （source=stocktaking → kingdee_im_surplusbill / kingdee_im_deficitbill）。
 */
import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { ApplicationConnection } from '../../../../../services/applicationConnection';
import type { API } from '../../../../../services/apiManagement';
import { DocumentPushBatchPanel } from '../../../components/DocumentPushBatchPanel';
import { stocktakingApi } from '../../../services/stocktaking';
import { normalizeWarehouseListResponse } from '../../../utils/warehouseListCore';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';

export interface StocktakingSurplusPushCandidate {
  id: number;
  code?: string;
  warehouse_name?: string;
  stocktaking_type?: string;
  status?: string;
  stocktaking_date?: string;
  total_differences?: number;
}

export interface StocktakingSurplusDocumentPushPanelProps {
  open: boolean;
  onClose: () => void;
  stocktakingIds?: number[];
  onComplete?: () => void;
  embedded?: boolean;
}

const ST_DEFAULT_PROFILES: string[] = [];
const ST_KINGDEE_PROFILES = ['kingdee_im_surplusbill', 'kingdee_im_deficitbill'];
const ST_SAVE_API_HINTS = [
  'surplusbill',
  'deficitbill',
  '盘盈',
  '盘亏',
  'im_surplusbill',
  'im_deficitbill',
  'batch_add_im_surplusbill',
  'batch_add_im_deficitbill',
];

const PUSHABLE_STATUSES = new Set(['completed', 'COMPLETED', '已完成']);

function isKingdeeStocktakingAdjustApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connection) return false;
  if (api.connection_uuid && api.connection_uuid !== connection.uuid) return false;
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  const hay = `${code} ${path} ${name}`;
  if (
    code.includes('batch_add_im_surplusbill') ||
    code.includes('push_im_surplusbill') ||
    code.includes('batch_add_im_deficitbill') ||
    code.includes('push_im_deficitbill')
  ) {
    return true;
  }
  const isBatchAdd = path.includes('/batchadd') || hay.includes('batchadd') || hay.includes('batch_add');
  const isSurplus =
    hay.includes('surplusbill') || hay.includes('im_surplusbill') || name.includes('盘盈');
  const isDeficit =
    hay.includes('deficitbill') || hay.includes('im_deficitbill') || name.includes('盘亏');
  return isBatchAdd && (isSurplus || isDeficit);
}

function preferStocktakingAdjustApiUuid(items: API[]): string | undefined {
  const preferred =
    items.find((api) => String(api.code || '').toLowerCase().includes('batch_add_im_surplusbill')) ||
    items.find((api) => String(api.code || '').toLowerCase().includes('batch_add_im_deficitbill')) ||
    items.find((api) => String(api.path || '').toLowerCase().includes('im_surplusbill')) ||
    items.find((api) => String(api.path || '').toLowerCase().includes('im_deficitbill')) ||
    items.find((api) => String(api.name || '').includes('盘盈')) ||
    items.find((api) => String(api.name || '').includes('盘亏')) ||
    items[0];
  return preferred?.uuid;
}

function resolveSaveApiForStocktakingProfile(profile: string, items: API[]): string | undefined {
  const isDeficit = profile === 'kingdee_im_deficitbill';
  const preferred = isDeficit
    ? items.find((api) => String(api.code || '').toLowerCase().includes('batch_add_im_deficitbill')) ||
      items.find((api) => String(api.path || '').toLowerCase().includes('im_deficitbill')) ||
      items.find((api) => String(api.name || '').includes('盘亏'))
    : items.find((api) => String(api.code || '').toLowerCase().includes('batch_add_im_surplusbill')) ||
      items.find((api) => String(api.path || '').toLowerCase().includes('im_surplusbill')) ||
      items.find((api) => String(api.name || '').includes('盘盈'));
  return preferred?.uuid;
}

function isPushableStocktaking(row: { status?: string }): boolean {
  const status = String(row.status || '').trim();
  return PUSHABLE_STATUSES.has(status) || PUSHABLE_STATUSES.has(status.toUpperCase());
}

function toCandidate(row: Record<string, unknown>): StocktakingSurplusPushCandidate | null {
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  if (!isPushableStocktaking({ status: String(row.status || '') })) return null;
  return {
    id,
    code: row.code != null ? String(row.code) : undefined,
    warehouse_name: row.warehouse_name != null ? String(row.warehouse_name) : undefined,
    stocktaking_type: row.stocktaking_type != null ? String(row.stocktaking_type) : undefined,
    status: row.status != null ? String(row.status) : undefined,
    stocktaking_date: row.stocktaking_date != null ? String(row.stocktaking_date) : undefined,
    total_differences: row.total_differences != null ? Number(row.total_differences) : undefined,
  };
}

export const StocktakingSurplusDocumentPushPanel: React.FC<StocktakingSurplusDocumentPushPanelProps> = ({
  open,
  onClose,
  stocktakingIds,
  onComplete,
  embedded = false,
}) => {
  const { t } = useTranslation();

  const columns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.stocktaking.documentPush.colCode'),
        dataIndex: 'code',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.warehouseReports.colWarehouse'),
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
      const res = await stocktakingApi.list({
        keyword: keyword || undefined,
        status: 'completed',
        skip: Math.max(0, (page - 1) * pageSize),
        limit: pageSize,
      });
      const { data: rows, total } = normalizeWarehouseListResponse(res);
      let data = (rows as Record<string, unknown>[])
        .map(toCandidate)
        .filter((row): row is StocktakingSurplusPushCandidate => !!row);

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
    <DocumentPushBatchPanel<StocktakingSurplusPushCandidate>
      open={open}
      onClose={onClose}
      onComplete={onComplete}
      embedded={embedded}
      preferIds={stocktakingIds}
      sourceType="stocktaking"
      defaultProfiles={ST_DEFAULT_PROFILES}
      kingdeeProfiles={ST_KINGDEE_PROFILES}
      title={t('app.kuaizhizao.stocktaking.documentPush.title')}
      hint={t('app.kuaizhizao.stocktaking.documentPush.hint')}
      pipelineDesc={t('app.kuaizhizao.stocktaking.documentPush.pipelineDesc')}
      searchPlaceholder={t('app.kuaizhizao.stocktaking.documentPush.searchPlaceholder')}
      needSelectMessage={t('app.kuaizhizao.stocktaking.documentPush.needSelect')}
      confirmText={t('app.kuaizhizao.documentPush.batch.confirm')}
      columns={columns}
      getRowLabel={(row) => row.code || String(row.id)}
      loadCandidates={loadCandidates}
      matchSaveApi={isKingdeeStocktakingAdjustApi}
      preferSaveApi={preferStocktakingAdjustApiUuid}
      resolveSaveApiForProfile={resolveSaveApiForStocktakingProfile}
      saveApiSearchHints={ST_SAVE_API_HINTS}
      showScheduleControls={false}
      successCountKey="app.kuaizhizao.documentPush.batch.success"
      partialCountKey="app.kuaizhizao.documentPush.batch.partial"
      failedTitleKey="app.kuaizhizao.documentPush.pushFailed"
      skippedHintKey="app.kuaizhizao.documentPush.batch.skippedHint"
    />
  );
};

export default StocktakingSurplusDocumentPushPanel;
