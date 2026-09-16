import { kuaioaDelete, kuaioaGet, kuaioaList, kuaioaPost, kuaioaPut } from './kuaioaApi';

const BASE = '/apps/kuaioa/welfare';

export const listWelfareBatches = (params?: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(`${BASE}/batches`, params);

export const getWelfareBatch = (id: number) =>
  kuaioaGet<Record<string, unknown>>(`${BASE}/batches/${id}`);

export const createWelfareBatch = (data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/batches`, data);

export const updateWelfareBatch = (id: number, data: Record<string, unknown>) =>
  kuaioaPut<Record<string, unknown>>(`${BASE}/batches/${id}`, data);

export const deleteWelfareBatch = (id: number) => kuaioaDelete(`${BASE}/batches/${id}`);

export const rebuildWelfareBatch = (id: number) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/batches/${id}/rebuild`, {});

export const updateWelfareLine = (
  batchId: number,
  lineId: number,
  data: Record<string, unknown>,
) => kuaioaPut<Record<string, unknown>>(`${BASE}/batches/${batchId}/lines/${lineId}`, data);

export const confirmWelfareBatch = (id: number) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/batches/${id}/confirm`, {});

export const reopenWelfareBatch = (id: number) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/batches/${id}/reopen`, {});
