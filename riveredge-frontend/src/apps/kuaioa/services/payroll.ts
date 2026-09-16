import { apiRequest } from '../../../services/api';
import { kuaioaDelete, kuaioaGet, kuaioaList, kuaioaPost, kuaioaPut } from './kuaioaApi';

const BASE = '/apps/kuaioa/payroll';

export const listLivingAdvances = (params?: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(`${BASE}/living-advances`, params);

export const getLivingAdvance = (id: number) =>
  kuaioaGet<Record<string, unknown>>(`${BASE}/living-advances/${id}`);

export const createLivingAdvance = (data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/living-advances`, data);

export const updateLivingAdvance = (id: number, data: Record<string, unknown>) =>
  kuaioaPut<Record<string, unknown>>(`${BASE}/living-advances/${id}`, data);

export const deleteLivingAdvance = (id: number) =>
  kuaioaDelete(`${BASE}/living-advances/${id}`);

export const listRewards = (params?: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(`${BASE}/rewards`, params);

export const getReward = (id: number) =>
  kuaioaGet<Record<string, unknown>>(`${BASE}/rewards/${id}`);

export const createReward = (data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/rewards`, data);

export const updateReward = (id: number, data: Record<string, unknown>) =>
  kuaioaPut<Record<string, unknown>>(`${BASE}/rewards/${id}`, data);

export const deleteReward = (id: number) => kuaioaDelete(`${BASE}/rewards/${id}`);

export const listPayrollSettlements = (params?: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(`${BASE}/settlements`, params);

export const getPayrollSettlement = (id: number) =>
  kuaioaGet<Record<string, unknown>>(`${BASE}/settlements/${id}`);

export const createPayrollSettlement = (data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/settlements`, data);

export const updatePayrollSettlement = (id: number, data: Record<string, unknown>) =>
  kuaioaPut<Record<string, unknown>>(`${BASE}/settlements/${id}`, data);

export const deletePayrollSettlement = (id: number) =>
  kuaioaDelete(`${BASE}/settlements/${id}`);

export const rebuildPayrollSettlement = (id: number) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/settlements/${id}/rebuild`, {});

export const updatePayrollLine = (
  settlementId: number,
  lineId: number,
  data: Record<string, unknown>,
) =>
  kuaioaPut<Record<string, unknown>>(
    `${BASE}/settlements/${settlementId}/lines/${lineId}`,
    data,
  );

export const confirmPayrollSettlement = (id: number) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/settlements/${id}/confirm`, {});

export const reopenPayrollSettlement = (id: number) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/settlements/${id}/reopen`, {});

export const listLivingPayout = (params: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(`${BASE}/living-payout`, params);

export const listAnnualPayrollStats = (params: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(`${BASE}/annual-stats`, params);

export const getPersonalPayrollStats = async (params: Record<string, unknown>) => {
  const res = await apiRequest(`${BASE}/personal-stats`, { method: 'GET', params });
  return ((res as Record<string, unknown>)?.data ?? res) as Record<string, unknown>;
};

export const importPayrollLines = (settlementId: number, data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/settlements/${settlementId}/import-lines`, data);
