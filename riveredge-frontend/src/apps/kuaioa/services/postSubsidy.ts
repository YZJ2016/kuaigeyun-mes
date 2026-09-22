import { kuaioaDelete, kuaioaGet, kuaioaList, kuaioaPost, kuaioaPut } from './kuaioaApi';

const BASE = '/apps/kuaioa/post-subsidies';

export const listPostSubsidies = (params?: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(BASE, params);

export const getPostSubsidy = (id: number) =>
  kuaioaGet<Record<string, unknown>>(`${BASE}/${id}`);

export const createPostSubsidy = (data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(BASE, data);

export const updatePostSubsidy = (id: number, data: Record<string, unknown>) =>
  kuaioaPut<Record<string, unknown>>(`${BASE}/${id}`, data);

export const deletePostSubsidy = (id: number) => kuaioaDelete(`${BASE}/${id}`);
