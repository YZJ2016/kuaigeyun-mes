import { kuaioaDelete, kuaioaGet, kuaioaList, kuaioaPost, kuaioaPut } from './kuaioaApi';

const BASE = '/apps/kuaioa/attendance-daily';

export type DailyAttendanceRecord = Record<string, unknown> & {
  id: number;
  employee_id?: number | null;
  employee_code?: string | null;
  employee_name?: string | null;
  department_name?: string | null;
  work_date?: string | null;
};

export const listDailyAttendance = (params?: Record<string, unknown>) =>
  kuaioaList<DailyAttendanceRecord>(BASE, params);

export const getDailyAttendance = (id: number) =>
  kuaioaGet<DailyAttendanceRecord>(`${BASE}/${id}`);

export const createDailyAttendance = (data: Record<string, unknown>) =>
  kuaioaPost<DailyAttendanceRecord>(BASE, data);

export const updateDailyAttendance = (id: number, data: Record<string, unknown>) =>
  kuaioaPut<DailyAttendanceRecord>(`${BASE}/${id}`, data);

export const deleteDailyAttendance = (id: number) => kuaioaDelete(`${BASE}/${id}`);
