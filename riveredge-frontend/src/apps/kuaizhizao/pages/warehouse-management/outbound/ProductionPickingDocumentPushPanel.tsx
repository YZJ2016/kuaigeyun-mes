/**
 * 生产领料外推：DocumentPushBatchPanel（source=production_picking → kingdee_im_otheroutbill）。
 */
import React, { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { ApplicationConnection } from '../../../../../services/applicationConnection';
import type { API } from '../../../../../services/apiManagement';
import {
  DocumentPushBatchPanel,
  type DocumentPushBindActionOption,
} from '../../../components/DocumentPushBatchPanel';
import {
  connectionMatchesApi,
  createResolveActionApiUuid,
  matchImWarehouseBindingApi,
} from '../shared/imKingdeeWarehousePushBinding';
import { warehouseApi } from '../../../services/production';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';

export interface ProductionPickingPushCandidate {
  id: number;
  picking_code?: string;
  work_order_code?: string;
  status?: string;
}

export interface ProductionPickingDocumentPushPanelProps {
  open: boolean;
  onClose: () => void;
  pickingIds?: number[];
  onComplete?: () => void;
  embedded?: boolean;
}

const PP_KINGDEE_PROFILES = ['kingdee_im_otheroutbill'];
const PP_FORM_TOKENS = ['otheroutbill', 'im_otheroutbill', '其他出库', '生产领料'];
const PP_SAVE_API_HINTS = [
  'batch_add_im_otheroutbill_production_picking',
  '生产领料',
  'otheroutbill',
  '其他出库',
  'im_otheroutbill',
  'batchUnaudit',
  'batchUnsubmit',
  'batchDelete',
];

function isKingdeeImProductionPickingOtheroutbillAddApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connectionMatchesApi(api, connection)) return false;
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  const hay = `${code} ${path} ${name}`;
  if (code.includes('batch_add_im_otheroutbill_production_picking')) {
    return true;
  }
  if (name.includes('生产领料') && (hay.includes('batchadd') || hay.includes('batch_add'))) {
    return true;
  }
  return false;
}

function matchProductionPickingBindingApi(
  slot: string,
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  return matchImWarehouseBindingApi(
    slot,
    api,
    connection,
    PP_FORM_TOKENS,
    isKingdeeImProductionPickingOtheroutbillAddApi,
  );
}

const PUSHABLE_STATUSES = new Set(['已领料', '已确认', 'picked', 'confirmed', 'COMPLETED', 'POSTED']);

function preferProductionPickingOtheroutbillApiUuid(items: API[]): string | undefined {
  const codeOf = (api: API) => String(api.code || '').toLowerCase();
  const preferred =
    items.find((api) => codeOf(api).includes('batch_add_im_otheroutbill_production_picking')) ||
    items.find((api) => String(api.name || '').includes('生产领料')) ||
    items.find((api) => {
      const code = codeOf(api);
      return code.includes('batch_add_im_otheroutbill') && !code.includes('production_picking');
    }) ||
    items.find((api) => String(api.path || '').toLowerCase().includes('im_otheroutbill')) ||
    items[0];
  return preferred?.uuid;
}

function isPushable(row: { status?: string }): boolean {
  const status = String(row.status || '').trim();
  return PUSHABLE_STATUSES.has(status) || PUSHABLE_STATUSES.has(status.toUpperCase());
}

function toCandidate(row: Record<string, unknown>): ProductionPickingPushCandidate | null {
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  if (!isPushable({ status: String(row.status || '') })) return null;
  return {
    id,
    picking_code: row.picking_code != null ? String(row.picking_code) : undefined,
    work_order_code: row.work_order_code != null ? String(row.work_order_code) : undefined,
    status: row.status != null ? String(row.status) : undefined,
  };
}

export const ProductionPickingDocumentPushPanel: React.FC<ProductionPickingDocumentPushPanelProps> = ({
  open,
  onClose,
  pickingIds,
  onComplete,
  embedded = false,
}) => {
  const { t } = useTranslation();

  const columns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.outboundCode'),
        dataIndex: 'picking_code',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.warehouseOutbound.col.workOrderCode'),
        dataIndex: 'work_order_code',
        width: 160,
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

  const bindActionOptions = useMemo<DocumentPushBindActionOption[]>(
    () => [
      {
        label: t('app.kuaizhizao.warehouseOutbound.action.confirmPicking'),
        value: 'confirm',
        apiKeys: ['confirm'],
      },
      {
        label: t('app.kuaizhizao.documentPush.batch.bindAction.update'),
        value: 'update',
        apiKeys: ['update'],
      },
      {
        label: t('app.kuaizhizao.warehouseOutbound.action.withdraw'),
        value: 'withdraw',
        apiKeys: ['withdraw', 'unsubmit'],
      },
      {
        label: t('common.delete'),
        value: 'delete',
        apiKeys: ['delete'],
      },
    ],
    [t],
  );

  const resolveActionApiUuid = useCallback(
    createResolveActionApiUuid(
      {
        confirm: PP_SAVE_API_HINTS,
        update: ['batchUpdate', 'batch_update', 'im_otheroutbill', 'production_picking'],
        withdraw: ['batchUnaudit', 'unaudit', 'im_otheroutbill'],
        unsubmit: ['batchUnsubmit', 'unsubmit', 'im_otheroutbill'],
        delete: ['batchDelete', 'delete', 'im_otheroutbill'],
      },
      preferProductionPickingOtheroutbillApiUuid,
    ),
    [],
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
      const res = await warehouseApi.productionPicking.list({
        keyword: keyword || undefined,
        status: '已领料',
        skip: (page - 1) * pageSize,
        limit: pageSize,
      });
      let data = ((res.items || []) as Record<string, unknown>[])
        .map(toCandidate)
        .filter((row): row is ProductionPickingPushCandidate => !!row);

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

  const loadBinding = useCallback(() => warehouseApi.productionPicking.getPushBinding(), []);
  const saveBinding = useCallback(
    (payload: Parameters<typeof warehouseApi.productionPicking.savePushBinding>[0]) =>
      warehouseApi.productionPicking.savePushBinding(payload),
    [],
  );

  if (!open) return null;

  return (
    <DocumentPushBatchPanel<ProductionPickingPushCandidate>
      open={open}
      onClose={onClose}
      onComplete={onComplete}
      embedded={embedded}
      preferIds={pickingIds}
      sourceType="production_picking"
      defaultProfiles={[]}
      kingdeeProfiles={PP_KINGDEE_PROFILES}
      title={t('app.kuaizhizao.productionPicking.documentPush.title')}
      hint={t('app.kuaizhizao.productionPicking.documentPush.hint')}
      pipelineDesc={t('app.kuaizhizao.productionPicking.documentPush.pipelineDesc')}
      searchPlaceholder={t('app.kuaizhizao.productionPicking.documentPush.searchPlaceholder')}
      needSelectMessage={t('app.kuaizhizao.productionPicking.documentPush.needSelect')}
      confirmText={t('app.kuaizhizao.documentPush.batch.confirm')}
      columns={columns}
      getRowLabel={(row) => row.picking_code || String(row.id)}
      loadCandidates={loadCandidates}
      matchSaveApi={isKingdeeImProductionPickingOtheroutbillAddApi}
      matchBindingApi={matchProductionPickingBindingApi}
      preferSaveApi={preferProductionPickingOtheroutbillApiUuid}
      saveApiSearchHints={PP_SAVE_API_HINTS}
      loadBinding={loadBinding}
      saveBinding={saveBinding}
      bindActionOptions={bindActionOptions}
      multiApiTargetRows
      resolveActionApiUuid={resolveActionApiUuid}
      showScheduleControls={false}
      successCountKey="app.kuaizhizao.documentPush.batch.success"
      partialCountKey="app.kuaizhizao.documentPush.batch.partial"
      failedTitleKey="app.kuaizhizao.documentPush.pushFailed"
      skippedHintKey="app.kuaizhizao.documentPush.batch.skippedHint"
    />
  );
};

export default ProductionPickingDocumentPushPanel;
