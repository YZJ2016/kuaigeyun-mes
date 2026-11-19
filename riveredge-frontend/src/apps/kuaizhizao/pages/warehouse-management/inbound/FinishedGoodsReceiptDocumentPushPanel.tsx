/**
 * 成品入库外推：DocumentPushBatchPanel（source=finished_goods_receipt → kingdee_im_otherinbill）。
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

export interface FinishedGoodsReceiptPushCandidate {
  id: number;
  receipt_code?: string;
  work_order_code?: string;
  warehouse_name?: string;
  status?: string;
}

export interface FinishedGoodsReceiptDocumentPushPanelProps {
  open: boolean;
  onClose: () => void;
  receiptIds?: number[];
  onComplete?: () => void;
  embedded?: boolean;
}

const FG_KINGDEE_PROFILES = ['kingdee_im_otherinbill'];
const FG_FORM_TOKENS = ['otherinbill', 'im_otherinbill', '其他入库', '成品入库', '生产完工入库'];
const FG_SAVE_API_HINTS = [
  'batch_add_im_otherinbill_finished_goods_receipt',
  '成品入库',
  '生产完工入库',
  'otherinbill',
  '其他入库',
  'im_otherinbill',
  'batchUnaudit',
  'batchUnsubmit',
  'batchDelete',
];

function isKingdeeImFinishedGoodsOtherinbillAddApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connectionMatchesApi(api, connection)) return false;
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  const hay = `${code} ${path} ${name}`;
  if (code.includes('batch_add_im_otherinbill_finished_goods_receipt')) {
    return true;
  }
  if (
    (name.includes('成品入库') || name.includes('生产完工入库')) &&
    (hay.includes('batchadd') || hay.includes('batch_add'))
  ) {
    return true;
  }
  return false;
}

function matchFinishedGoodsBindingApi(
  slot: string,
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  return matchImWarehouseBindingApi(
    slot,
    api,
    connection,
    FG_FORM_TOKENS,
    isKingdeeImFinishedGoodsOtherinbillAddApi,
  );
}

const PUSHABLE_STATUSES = new Set(['已入库', '已完成', 'processed', 'COMPLETED', 'POSTED']);

function preferFinishedGoodsOtherinbillApiUuid(items: API[]): string | undefined {
  const codeOf = (api: API) => String(api.code || '').toLowerCase();
  const preferred =
    items.find((api) => codeOf(api).includes('batch_add_im_otherinbill_finished_goods_receipt')) ||
    items.find(
      (api) =>
        String(api.name || '').includes('成品入库') || String(api.name || '').includes('生产完工入库'),
    ) ||
    items.find((api) => {
      const code = codeOf(api);
      return code.includes('batch_add_im_otherinbill') && !code.includes('finished_goods');
    }) ||
    items.find((api) => String(api.path || '').toLowerCase().includes('im_otherinbill')) ||
    items[0];
  return preferred?.uuid;
}

function isPushable(row: { status?: string }): boolean {
  const status = String(row.status || '').trim();
  return PUSHABLE_STATUSES.has(status) || PUSHABLE_STATUSES.has(status.toUpperCase());
}

function toCandidate(row: Record<string, unknown>): FinishedGoodsReceiptPushCandidate | null {
  const id = Number(row.id);
  if (!Number.isFinite(id) || id <= 0) return null;
  if (!isPushable({ status: String(row.status || '') })) return null;
  return {
    id,
    receipt_code: row.receipt_code != null ? String(row.receipt_code) : undefined,
    work_order_code: row.work_order_code != null ? String(row.work_order_code) : undefined,
    warehouse_name: row.warehouse_name != null ? String(row.warehouse_name) : undefined,
    status: row.status != null ? String(row.status) : undefined,
  };
}

export const FinishedGoodsReceiptDocumentPushPanel: React.FC<
  FinishedGoodsReceiptDocumentPushPanelProps
> = ({ open, onClose, receiptIds, onComplete, embedded = false }) => {
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
        title: t('app.kuaizhizao.warehouseInbound.col.workOrderCode'),
        dataIndex: 'work_order_code',
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
        confirm: FG_SAVE_API_HINTS,
        update: ['batchUpdate', 'batch_update', 'im_otherinbill', 'finished_goods'],
        withdraw: ['batchUnaudit', 'unaudit', 'im_otherinbill'],
        unsubmit: ['batchUnsubmit', 'unsubmit', 'im_otherinbill'],
        delete: ['batchDelete', 'delete', 'im_otherinbill'],
      },
      preferFinishedGoodsOtherinbillApiUuid,
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
      const res = await warehouseApi.finishedGoodsReceipt.list({
        keyword: keyword || undefined,
        status: '已入库',
        skip: (page - 1) * pageSize,
        limit: pageSize,
      });
      let data = ((res.items || []) as Record<string, unknown>[])
        .map(toCandidate)
        .filter((row): row is FinishedGoodsReceiptPushCandidate => !!row);

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

  const loadBinding = useCallback(() => warehouseApi.finishedGoodsReceipt.getPushBinding(), []);
  const saveBinding = useCallback(
    (payload: Parameters<typeof warehouseApi.finishedGoodsReceipt.savePushBinding>[0]) =>
      warehouseApi.finishedGoodsReceipt.savePushBinding(payload),
    [],
  );

  if (!open) return null;

  return (
    <DocumentPushBatchPanel<FinishedGoodsReceiptPushCandidate>
      open={open}
      onClose={onClose}
      onComplete={onComplete}
      embedded={embedded}
      preferIds={receiptIds}
      sourceType="finished_goods_receipt"
      defaultProfiles={[]}
      kingdeeProfiles={FG_KINGDEE_PROFILES}
      title={t('app.kuaizhizao.finishedGoods.documentPush.title')}
      hint={t('app.kuaizhizao.finishedGoods.documentPush.hint')}
      pipelineDesc={t('app.kuaizhizao.finishedGoods.documentPush.pipelineDesc')}
      searchPlaceholder={t('app.kuaizhizao.finishedGoods.documentPush.searchPlaceholder')}
      needSelectMessage={t('app.kuaizhizao.finishedGoods.documentPush.needSelect')}
      confirmText={t('app.kuaizhizao.documentPush.batch.confirm')}
      columns={columns}
      getRowLabel={(row) => row.receipt_code || String(row.id)}
      loadCandidates={loadCandidates}
      matchSaveApi={isKingdeeImFinishedGoodsOtherinbillAddApi}
      matchBindingApi={matchFinishedGoodsBindingApi}
      preferSaveApi={preferFinishedGoodsOtherinbillApiUuid}
      saveApiSearchHints={FG_SAVE_API_HINTS}
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

export default FinishedGoodsReceiptDocumentPushPanel;
