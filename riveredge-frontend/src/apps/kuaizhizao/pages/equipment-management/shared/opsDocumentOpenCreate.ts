/** 运营单据深链：?open_create=1&mold_id|tool_id|mold_uuid|tool_uuid */

export const OPS_OPEN_CREATE_PARAM = 'open_create';

export function buildOpsOpenCreateQuery(
  asset: { mold_id?: number; tool_id?: number; mold_uuid?: string; tool_uuid?: string },
): string {
  const params = new URLSearchParams();
  params.set(OPS_OPEN_CREATE_PARAM, '1');
  if (asset.mold_id != null) params.set('mold_id', String(asset.mold_id));
  if (asset.tool_id != null) params.set('tool_id', String(asset.tool_id));
  if (asset.mold_uuid) params.set('mold_uuid', asset.mold_uuid);
  if (asset.tool_uuid) params.set('tool_uuid', asset.tool_uuid);
  return params.toString();
}

export function clearOpsOpenCreateParams(
  searchParams: URLSearchParams,
  keys: string[] = ['mold_id', 'tool_id', 'mold_uuid', 'tool_uuid'],
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  next.delete(OPS_OPEN_CREATE_PARAM);
  keys.forEach((k) => next.delete(k));
  return next;
}

export function openCreateQuerySignature(searchParams: URLSearchParams): string | null {
  if (searchParams.get(OPS_OPEN_CREATE_PARAM) !== '1') return null;
  return [
    searchParams.get('mold_id') ?? '',
    searchParams.get('tool_id') ?? '',
    searchParams.get('mold_uuid') ?? '',
    searchParams.get('tool_uuid') ?? '',
  ].join('|');
}
