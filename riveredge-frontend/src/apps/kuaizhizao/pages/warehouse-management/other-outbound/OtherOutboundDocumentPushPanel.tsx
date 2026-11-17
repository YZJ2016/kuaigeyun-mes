/**
 * 其他出库外推：DocumentPushBatchPanel（source=other_outbound → kingdee_im_otheroutbill）。
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
import { normalizeWarehouseListResponse } from '../../../utils/warehouseListCore';
import { renderDocumentStatusTag } from '../../../../../utils/documentLifecycleStatusTag';
import { translateOtherOutboundReasonTypeLabel } from './otherOutboundReasonTypeLabels';
import { renderWarehouseReasonTypeMarkerTag } from '../shared/warehouseMarkerTags';

export interface OtherOutboundPushCandidate {
  id: number;
  outbound_code?: string;
  reason_type?: string;
  warehouse_name?: string;
  status?: string;
  total_quantity?: number;
  delivery_time?: string;
}

export interface OtherOutboundDocumentPushPanelProps {
  open: boolean;
  onClose: () => void;
  outboundIds?: number[];
  onComplete?: () => void;
  embedded?: boolean;
}

const OO_DEFAULT_PROFILES: string[] = [];
const OO_KINGDEE_PROFILES = ['kingdee_im_otheroutbill'];
const OO_FORM_TOKENS = ['otheroutbill', 'im_otheroutbill', '其他出库'];
const OO_SAVE_API_HINTS = [
  'add3_im_otheroutbill',
  'batch_add_im_otheroutbill',
  'otheroutbill',
  '其他出库',
  'im_otheroutbill',
  'batchUnaudit',
  'batchUnsubmit',
  'batchDelete',
];

function isProductionPickingApi(api: API): boolean {
  const code = String(api.code || '').toLowerCase();
  return code.includes('production_picking') || String(api.name || '').includes('生产领料');
}

function isKingdeeImOtheroutbillBatchAddApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connectionMatchesApi(api, connection)) return false;
  if (isProductionPickingApi(api)) return false;
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  const hay = `${code} ${path} ${name}`;
  if (
    code.includes('add3_im_otheroutbill') ||
    code.includes('batch_add_im_otheroutbill') ||
    code.includes('push_im_otheroutbill')
  ) {
    return true;
  }
  const isBatchAdd =
    path.includes('/batchadd') ||
    path.includes('/add3') ||
    hay.includes('batchadd') ||
    hay.includes('batch_add');
  const isOtherOut =
    hay.includes('otheroutbill') ||
    hay.includes('im_otheroutbill') ||
    name.includes('其他出库');
  return isBatchAdd && isOtherOut;
}

function matchOtheroutbillBindingApi(
  slot: string,
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  return matchImWarehouseBindingApi(
    slot,
    api,
    connection,
    OO_FORM_TOKENS,
    isKingdeeImOtheroutbillBatchAddApi,
    isProductionPickingApi,
  );
}

const PUSHABLE_STATUSES = new Set(['已出库', '已完成', 'processed', 'COMPLETED', 'POSTED']);

function preferOtheroutbillApiUuid(items: API[]): string | undefined {
  const codeOf = (api: API) => String(api.code || '').toLowerCase();
  const pathOf = (api: API) => String(api.path || '').toLowerCase();
  const preferred =
    items.find((api) => {
      const code = codeOf(api);
      return (
        (code.includes('add3_im_otheroutbill') || pathOf(api).includes('/add3')) &&
        !isProductionPickingApi(api)
      );
    }) ||
    items.find((api) => {
      const code = codeOf(api);
      return code.includes('batch_add_im_otheroutbill') && !isProductionPickingApi(api);
    }) ||
    items.find((api) => codeOf(api).includes('push_im_otheroutbill') && !isProductionPickingApi(api)) ||
    items.find(
      (api) => pathOf(api).includes('im_otheroutbill') && !isProductionPickingApi(api),
    ) ||
    items.find((api) => String(api.name || '').includes('其他出库') && !isProductionPickingApi(api)) ||
    items[0];
  return preferred?.uuid;
}

function isPushableOutbound(row: { status?: string }): boolean {
  const status = String(row.status || '').trim();
  return PUSHABLE_STATUSES.has(status) || PUSHABLE_STATUSES.has(status.toUpperCase());
}

function toCandidate(row: Record<string, unknown>): OtherOutboundPushCandidate | null {
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  if (!isPushableOutbound({ status: String(row.status || '') })) return null;
  return {
    id,
    outbound_code: row.outbound_code != null ? String(row.outbound_code) : undefined,
    reason_type: row.reason_type != null ? String(row.reason_type) : undefined,
    warehouse_name: row.warehouse_name != null ? String(row.warehouse_name) : undefined,
    status: row.status != null ? String(row.status) : undefined,
    total_quantity: row.total_quantity != null ? Number(row.total_quantity) : undefined,
    delivery_time: row.delivery_time != null ? String(row.delivery_time) : undefined,
  };
}

export const OtherOutboundDocumentPushPanel: React.FC<OtherOutboundDocumentPushPanelProps> = ({
  open,
  onClose,
  outboundIds,
  onComplete,
  embedded = false,
}) => {
  const { t } = useTranslation();

  const columns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.otherOutbound.col.outboundCode'),
        dataIndex: 'outbound_code',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.otherOutbound.col.reasonType'),
        dataIndex: 'reason_type',
        width: 100,
        ellipsis: true,
        render: (v: string | undefined) =>
          renderWarehouseReasonTypeMarkerTag(
            translateOtherOutboundReasonTypeLabel(t, v),
            v,
          ),
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

  const bindActionOptions = useMemo<DocumentPushBindActionOption[]>(
    () => [
      {
        label: t('app.kuaizhizao.warehouseOutbound.action.confirmOutbound'),
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
        confirm: OO_SAVE_API_HINTS,
        update: ['batchUpdate', 'batch_update', 'im_otheroutbill'],
        withdraw: ['batchUnaudit', 'unaudit', 'im_otheroutbill'],
        unsubmit: ['batchUnsubmit', 'unsubmit', 'im_otheroutbill'],
        delete: ['batchDelete', 'delete', 'im_otheroutbill'],
      },
      preferOtheroutbillApiUuid,
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
      const res = await warehouseApi.otherOutbound.list({
        keyword: keyword || undefined,
        status: '已出库',
        skip: Math.max(0, (page - 1) * pageSize),
        limit: pageSize,
      });
      const { data: rows, total } = normalizeWarehouseListResponse(res);
      let data = (rows as Record<string, unknown>[])
        .map(toCandidate)
        .filter((row): row is OtherOutboundPushCandidate => !!row);

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

  const loadBinding = useCallback(() => warehouseApi.otherOutbound.getPushBinding(), []);
  const saveBinding = useCallback(
    (payload: Parameters<typeof warehouseApi.otherOutbound.savePushBinding>[0]) =>
      warehouseApi.otherOutbound.savePushBinding(payload),
    [],
  );

  if (!open) return null;

  return (
    <DocumentPushBatchPanel<OtherOutboundPushCandidate>
      open={open}
      onClose={onClose}
      onComplete={onComplete}
      embedded={embedded}
      preferIds={outboundIds}
      sourceType="other_outbound"
      defaultProfiles={OO_DEFAULT_PROFILES}
      kingdeeProfiles={OO_KINGDEE_PROFILES}
      title={t('app.kuaizhizao.otherOutbound.documentPush.title')}
      hint={t('app.kuaizhizao.otherOutbound.documentPush.hint')}
      pipelineDesc={t('app.kuaizhizao.otherOutbound.documentPush.pipelineDesc')}
      searchPlaceholder={t('app.kuaizhizao.otherOutbound.documentPush.searchPlaceholder')}
      needSelectMessage={t('app.kuaizhizao.otherOutbound.documentPush.needSelect')}
      confirmText={t('app.kuaizhizao.documentPush.batch.confirm')}
      columns={columns}
      getRowLabel={(row) => row.outbound_code || String(row.id)}
      loadCandidates={loadCandidates}
      matchSaveApi={isKingdeeImOtheroutbillBatchAddApi}
      matchBindingApi={matchOtheroutbillBindingApi}
      preferSaveApi={preferOtheroutbillApiUuid}
      saveApiSearchHints={OO_SAVE_API_HINTS}
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

export default OtherOutboundDocumentPushPanel;
