import { kuaioaDelete, kuaioaGet, kuaioaList, kuaioaPost, kuaioaPut } from './kuaioaApi';

const BASE = '/apps/kuaioa/employees';

export const listEmployees = (params?: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(BASE, params);

export const getEmployee = (id: number) =>
  kuaioaGet<Record<string, unknown>>(`${BASE}/${id}`);

export const createEmployee = (data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(BASE, data);

export const updateEmployee = (id: number, data: Record<string, unknown>) =>
  kuaioaPut<Record<string, unknown>>(`${BASE}/${id}`, data);

export const deleteEmployee = (id: number) => kuaioaDelete(`${BASE}/${id}`);

export const listEmployeeMovements = (params: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(`${BASE}/movements`, params);
