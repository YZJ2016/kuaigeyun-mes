/**
 * 其他入库外推：DocumentPushBatchPanel（source=other_inbound → kingdee_im_otherinbill）。
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
import { renderWarehouseReasonTypeMarkerTag } from '../shared/warehouseMarkerTags';

export interface OtherInboundPushCandidate {
  id: number;
  inbound_code?: string;
  reason_type?: string;
  warehouse_name?: string;
  status?: string;
  total_quantity?: number;
  receipt_time?: string;
}

export interface OtherInboundDocumentPushPanelProps {
  open: boolean;
  onClose: () => void;
  inboundIds?: number[];
  onComplete?: () => void;
  embedded?: boolean;
}

const OI_DEFAULT_PROFILES: string[] = [];
const OI_KINGDEE_PROFILES = ['kingdee_im_otherinbill'];
const OI_FORM_TOKENS = ['otherinbill', 'im_otherinbill', '其他入库'];
const OI_SAVE_API_HINTS = [
  'otherinbill',
  '其他入库',
  'im_otherinbill',
  'batch_add_im_otherinbill',
  'batchUnaudit',
  'batchUnsubmit',
  'batchDelete',
];

function isFinishedGoodsReceiptApi(api: API): boolean {
  const code = String(api.code || '').toLowerCase();
  return (
    code.includes('finished_goods') ||
    String(api.name || '').includes('成品入库') ||
    String(api.name || '').includes('生产完工入库')
  );
}

function isKingdeeImOtherinbillBatchAddApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connectionMatchesApi(api, connection)) return false;
  if (isFinishedGoodsReceiptApi(api)) return false;
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  const hay = `${code} ${path} ${name}`;
  if (code.includes('batch_add_im_otherinbill') || code.includes('push_im_otherinbill')) {
    return true;
  }
  const isBatchAdd =
    path.includes('/batchadd') || hay.includes('batchadd') || hay.includes('batch_add');
  const isOtherIn =
    hay.includes('otherinbill') || hay.includes('im_otherinbill') || name.includes('其他入库');
  return isBatchAdd && isOtherIn;
}

function matchOtherinbillBindingApi(
  slot: string,
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  return matchImWarehouseBindingApi(
    slot,
    api,
    connection,
    OI_FORM_TOKENS,
    isKingdeeImOtherinbillBatchAddApi,
    isFinishedGoodsReceiptApi,
  );
}

const PUSHABLE_STATUSES = new Set(['已入库', '已完成', 'processed', 'COMPLETED', 'POSTED']);

function preferOtherinbillApiUuid(items: API[]): string | undefined {
  const codeOf = (api: API) => String(api.code || '').toLowerCase();
  const preferred =
    items.find((api) => {
      const code = codeOf(api);
      return code.includes('batch_add_im_otherinbill') && !isFinishedGoodsReceiptApi(api);
    }) ||
    items.find((api) => codeOf(api).includes('push_im_otherinbill') && !isFinishedGoodsReceiptApi(api)) ||
    items.find(
      (api) =>
        String(api.path || '').toLowerCase().includes('im_otherinbill') &&
        !isFinishedGoodsReceiptApi(api),
    ) ||
    items.find(
      (api) => String(api.name || '').includes('其他入库') && !isFinishedGoodsReceiptApi(api),
    ) ||
    items[0];
  return preferred?.uuid;
}

function isPushableInbound(row: { status?: string }): boolean {
  const status = String(row.status || '').trim();
  return PUSHABLE_STATUSES.has(status) || PUSHABLE_STATUSES.has(status.toUpperCase());
}

function toCandidate(row: Record<string, unknown>): OtherInboundPushCandidate | null {
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  if (!isPushableInbound({ status: String(row.status || '') })) return null;
  return {
    id,
    inbound_code: row.inbound_code != null ? String(row.inbound_code) : undefined,
    reason_type: row.reason_type != null ? String(row.reason_type) : undefined,
    warehouse_name: row.warehouse_name != null ? String(row.warehouse_name) : undefined,
    status: row.status != null ? String(row.status) : undefined,
    total_quantity: row.total_quantity != null ? Number(row.total_quantity) : undefined,
    receipt_time: row.receipt_time != null ? String(row.receipt_time) : undefined,
  };
}

export const OtherInboundDocumentPushPanel: React.FC<OtherInboundDocumentPushPanelProps> = ({
  open,
  onClose,
  inboundIds,
  onComplete,
  embedded = false,
}) => {
  const { t } = useTranslation();

  const columns = useMemo(
    () => [
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.inboundCode'),
        dataIndex: 'inbound_code',
        width: 160,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.reasonType'),
        dataIndex: 'reason_type',
        width: 100,
        ellipsis: true,
        render: (v: string | undefined) => renderWarehouseReasonTypeMarkerTag(v || '-', v),
      },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.warehouse'),
        dataIndex: 'warehouse_name',
        width: 120,
        ellipsis: true,
      },
      {
        title: t('app.kuaizhizao.warehouseOtherInbound.col.lifecycle'),
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
        label: t('app.kuaizhizao.warehouseInbound.action.confirmInbound'),
        value: 'confirm',
        apiKeys: ['confirm'],
      },
      {
        label: t('app.kuaizhizao.documentPush.batch.bindAction.update'),
        value: 'update',
        apiKeys: ['update'],
      },
      {
        label: t('app.kuaizhizao.warehouseInbound.action.withdrawInbound'),
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
        confirm: OI_SAVE_API_HINTS,
        update: ['batchUpdate', 'batch_update', 'im_otherinbill'],
        withdraw: ['batchUnaudit', 'unaudit', 'im_otherinbill'],
        unsubmit: ['batchUnsubmit', 'unsubmit', 'im_otherinbill'],
        delete: ['batchDelete', 'delete', 'im_otherinbill'],
      },
      preferOtherinbillApiUuid,
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
      const res = await warehouseApi.otherInbound.list({
        keyword: keyword || undefined,
        status: '已入库',
        skip: Math.max(0, (page - 1) * pageSize),
        limit: pageSize,
      });
      const { data: rows, total } = normalizeWarehouseListResponse(res);
      let data = (rows as Record<string, unknown>[])
        .map(toCandidate)
        .filter((row): row is OtherInboundPushCandidate => !!row);

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

  const loadBinding = useCallback(() => warehouseApi.otherInbound.getPushBinding(), []);
  const saveBinding = useCallback(
    (payload: Parameters<typeof warehouseApi.otherInbound.savePushBinding>[0]) =>
      warehouseApi.otherInbound.savePushBinding(payload),
    [],
  );

  if (!open) return null;

  return (
    <DocumentPushBatchPanel<OtherInboundPushCandidate>
      open={open}
      onClose={onClose}
      onComplete={onComplete}
      embedded={embedded}
      preferIds={inboundIds}
      sourceType="other_inbound"
      defaultProfiles={OI_DEFAULT_PROFILES}
      kingdeeProfiles={OI_KINGDEE_PROFILES}
      title={t('app.kuaizhizao.warehouseOtherInbound.documentPush.title')}
      hint={t('app.kuaizhizao.warehouseOtherInbound.documentPush.hint')}
      pipelineDesc={t('app.kuaizhizao.warehouseOtherInbound.documentPush.pipelineDesc')}
      searchPlaceholder={t('app.kuaizhizao.warehouseOtherInbound.documentPush.searchPlaceholder')}
      needSelectMessage={t('app.kuaizhizao.warehouseOtherInbound.documentPush.needSelect')}
      confirmText={t('app.kuaizhizao.documentPush.batch.confirm')}
      columns={columns}
      getRowLabel={(row) => row.inbound_code || String(row.id)}
      loadCandidates={loadCandidates}
      matchSaveApi={isKingdeeImOtherinbillBatchAddApi}
      matchBindingApi={matchOtherinbillBindingApi}
      preferSaveApi={preferOtherinbillApiUuid}
      saveApiSearchHints={OI_SAVE_API_HINTS}
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

export default OtherInboundDocumentPushPanel;
