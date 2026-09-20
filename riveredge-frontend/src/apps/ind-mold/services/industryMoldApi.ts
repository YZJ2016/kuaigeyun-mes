import { apiRequest } from '../../../services/api';

export type MoldProgramSheet = {
  id: number;
  code: string;
  work_order_id: number;
  work_order_code: string;
  program_name: string;
  program_status: string;
  nc_file_path?: string | null;
  remarks?: string | null;
};

export type MoldMaterialArrival = {
  id: number;
  code: string;
  work_order_id?: number | null;
  work_order_code?: string | null;
  material_name: string;
  material_spec?: string | null;
  weight?: number | null;
  status: string;
  remarks?: string | null;
};

export const industryMoldApi = {
  listProgramSheets: () =>
    apiRequest<MoldProgramSheet[]>('/apps/ind-mold/program-sheets', { method: 'GET' }),
  createProgramSheet: (data: {
    work_order_id: number;
    work_order_code: string;
    program_name: string;
    nc_file_path?: string;
    remarks?: string;
  }) =>
    apiRequest<MoldProgramSheet>('/apps/ind-mold/program-sheets', { method: 'POST', data }),
  listMaterialArrivals: () =>
    apiRequest<MoldMaterialArrival[]>('/apps/ind-mold/material-arrivals', { method: 'GET' }),
  createMaterialArrival: (data: {
    work_order_id?: number;
    work_order_code?: string;
    material_name: string;
    material_spec?: string;
    weight?: number;
    remarks?: string;
  }) =>
    apiRequest<MoldMaterialArrival>('/apps/ind-mold/material-arrivals', { method: 'POST', data }),
  voidMaterialArrival: (id: number) =>
    apiRequest<MoldMaterialArrival>(`/apps/ind-mold/material-arrivals/${id}/void`, { method: 'POST' }),
};
