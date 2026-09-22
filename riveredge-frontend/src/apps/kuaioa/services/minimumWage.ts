import { kuaioaDelete, kuaioaGet, kuaioaList, kuaioaPost, kuaioaPut } from './kuaioaApi';

const BASE = '/apps/kuaioa/minimum-wage';

export const listMinimumWageConfigs = () =>
  kuaioaList<Record<string, unknown>>(BASE);

export const getMinimumWageConfig = (id: number) =>
  kuaioaGet<Record<string, unknown>>(`${BASE}/${id}`);

export const createMinimumWageConfig = (data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(BASE, data);

export const updateMinimumWageConfig = (id: number, data: Record<string, unknown>) =>
  kuaioaPut<Record<string, unknown>>(`${BASE}/${id}`, data);

export const deleteMinimumWageConfig = (id: number) => kuaioaDelete(`${BASE}/${id}`);
