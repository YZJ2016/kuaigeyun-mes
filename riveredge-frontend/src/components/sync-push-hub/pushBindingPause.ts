/**
 * 出站自动外推暂停：落库 push_enabled=false，无感外推跳过，本地确认不过账撤回。
 */
import type { DocumentPushBindingState, DocumentPushTargetBinding } from '../../apps/kuaizhizao/components/DocumentPushBatchPanel';
import { warehouseApi } from '../../apps/kuaizhizao/services/warehouse-execution';

export type PushBindingPauseApi = {
  load: () => Promise<DocumentPushBindingState | null | undefined>;
  save: (payload: DocumentPushBindingState) => Promise<unknown>;
};

type WarehousePushBindingClient = {
  getPushBinding: () => Promise<DocumentPushBindingState>;
  savePushBinding: (payload: DocumentPushBindingState) => Promise<unknown>;
};

const WAREHOUSE_PUSH_BINDING_BY_SOURCE: Record<string, WarehousePushBindingClient> = {
  purchase_receipt: warehouseApi.purchaseReceipt as WarehousePushBindingClient,
  finished_goods_receipt: warehouseApi.finishedGoodsReceipt as WarehousePushBindingClient,
  sales_delivery: warehouseApi.salesDelivery as WarehousePushBindingClient,
  production_picking: warehouseApi.productionPicking as WarehousePushBindingClient,
  other_outbound: warehouseApi.otherOutbound as WarehousePushBindingClient,
  other_inbound: warehouseApi.otherInbound as WarehousePushBindingClient,
};

export function resolvePushBindingPauseApi(
  historySourceType: string | undefined | null,
): PushBindingPauseApi | null {
  const key = String(historySourceType || '').trim();
  const client = WAREHOUSE_PUSH_BINDING_BY_SOURCE[key];
  if (!client) return null;
  return {
    load: () => client.getPushBinding(),
    save: (payload) => client.savePushBinding(payload),
  };
}

export function isPushBindingPaused(
  targets: DocumentPushTargetBinding[] | null | undefined,
): boolean {
  const rows = (targets || []).filter((row) => row && row.user_saved !== false && row.target_profile);
  if (!rows.length) return false;
  return rows.every((row) => row.push_enabled === false);
}

export function withPushEnabled(
  targets: DocumentPushTargetBinding[],
  enabled: boolean,
): DocumentPushTargetBinding[] {
  return targets.map((row) => ({
    ...row,
    user_saved: true,
    push_enabled: enabled,
  }));
}

export async function setPushBindingPaused(
  api: PushBindingPauseApi,
  paused: boolean,
): Promise<DocumentPushBindingState> {
  const binding = (await api.load()) || {};
  const targets = (binding.targets || []).filter(
    (row) => row && row.user_saved !== false && row.target_profile,
  );
  if (!targets.length) {
    throw new Error('NO_TARGETS');
  }
  const next: DocumentPushBindingState = {
    ...binding,
    targets: withPushEnabled(targets, !paused),
    trigger_actions: binding.trigger_actions || [
      ...new Set(targets.flatMap((row) => row.trigger_actions || [])),
    ],
  };
  await api.save(next);
  return next;
}
