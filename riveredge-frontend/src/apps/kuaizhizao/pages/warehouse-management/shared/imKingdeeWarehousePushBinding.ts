import type { ApplicationConnection } from '../../../../../services/applicationConnection';
import type { API } from '../../../../../services/apiManagement';
import { sortApisByPreferredHints } from '../../../../../utils/activeApiSelectOptions';

export function apiHaystack(api: API): string {
  const code = String(api.code || '').toLowerCase();
  const path = String(api.path || '').toLowerCase();
  const name = String(api.name || '').toLowerCase();
  return `${code} ${path} ${name}`.replace(/_/g, '');
}

export function connectionMatchesApi(
  api: API,
  connection: ApplicationConnection | undefined,
): boolean {
  if (!connection) return false;
  if (api.connection_uuid && api.connection_uuid !== connection.uuid) return false;
  return true;
}

function isImFormHaystack(hay: string, formTokens: string[]): boolean {
  return formTokens.some((token) => {
    const normalized = token.toLowerCase().replace(/_/g, '');
    return hay.includes(normalized);
  });
}

export function isImWarehouseOperateApi(
  api: API,
  formTokens: string[],
  marker: string,
  exclude?: (api: API) => boolean,
): boolean {
  if (exclude?.(api)) return false;
  const hay = apiHaystack(api);
  if (!isImFormHaystack(hay, formTokens)) return false;
  return hay.includes(marker.toLowerCase().replace(/_/g, ''));
}

export function matchImWarehouseBindingApi(
  slot: string,
  api: API,
  connection: ApplicationConnection | undefined,
  formTokens: string[],
  isAddApi: (api: API, connection: ApplicationConnection | undefined) => boolean,
  exclude?: (api: API) => boolean,
): boolean {
  if (!connectionMatchesApi(api, connection)) return false;
  const key = String(slot || '').trim();
  if (key === 'confirm') return isAddApi(api, connection);
  if (key === 'update') return isImWarehouseOperateApi(api, formTokens, 'batchupdate', exclude);
  if (key === 'withdraw') return isImWarehouseOperateApi(api, formTokens, 'batchunaudit', exclude);
  if (key === 'unsubmit') return isImWarehouseOperateApi(api, formTokens, 'batchunsubmit', exclude);
  if (key === 'delete') return isImWarehouseOperateApi(api, formTokens, 'batchdelete', exclude);
  return false;
}

export function createResolveActionApiUuid(
  hintsBySlot: Record<string, string[]>,
  preferConfirm?: (items: API[]) => string | undefined,
): (slot: string, items: API[]) => string | undefined {
  return (slot: string, items: API[]) => {
    const sorted = sortApisByPreferredHints(items, hintsBySlot[slot] || []);
    if (slot === 'confirm' && preferConfirm) {
      return preferConfirm(sorted);
    }
    const markers = hintsBySlot[slot] || [];
    const hayMatch = (api: API) => {
      const hay = `${api.code || ''} ${api.path || ''} ${api.name || ''}`.toLowerCase();
      return markers.some((m) => hay.includes(m.toLowerCase()));
    };
    const preferred = sorted.find(hayMatch);
    return preferred?.uuid || sorted[0]?.uuid;
  };
}
