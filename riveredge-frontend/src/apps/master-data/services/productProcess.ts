import { api } from '../../../services/api';
import type {
  MaterialGroupProductProcess,
  MaterialGroupProductProcessSave,
  MaterialProductProcess,
  MaterialProductProcessSave,
} from '../types/productProcess';

export interface ProductProcessRouteAssignment {
  materialUuid: string;
  processRouteUuid: string;
}

export interface ProductProcessGroupRouteAssignment {
  materialGroupUuid: string;
  processRouteUuid: string;
}

export const productProcessApi = {
  get: async (materialUuid: string): Promise<MaterialProductProcess> => {
    return api.get(`/apps/master-data/process/materials/${materialUuid}/product-process`);
  },

  save: async (
    materialUuid: string,
    data: MaterialProductProcessSave,
  ): Promise<MaterialProductProcess> => {
    return api.put(`/apps/master-data/process/materials/${materialUuid}/product-process`, data);
  },

  getGroup: async (materialGroupUuid: string): Promise<MaterialGroupProductProcess> => {
    return api.get(
      `/apps/master-data/process/material-groups/${materialGroupUuid}/product-process`,
    );
  },

  saveGroup: async (
    materialGroupUuid: string,
    data: MaterialGroupProductProcessSave,
  ): Promise<MaterialGroupProductProcess> => {
    return api.put(
      `/apps/master-data/process/material-groups/${materialGroupUuid}/product-process`,
      data,
    );
  },

  listRouteAssignments: async (): Promise<ProductProcessRouteAssignment[]> => {
    const res = await api.get<{ items?: ProductProcessRouteAssignment[] }>(
      '/apps/master-data/process/product-process/route-assignments',
    );
    return res?.items ?? [];
  },

  listGroupRouteAssignments: async (): Promise<ProductProcessGroupRouteAssignment[]> => {
    const res = await api.get<{ items?: ProductProcessGroupRouteAssignment[] }>(
      '/apps/master-data/process/product-process/group-route-assignments',
    );
    return res?.items ?? [];
  },
};
