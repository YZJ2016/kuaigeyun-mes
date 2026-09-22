import { kuaioaDelete, kuaioaDownloadBlob, kuaioaGet, kuaioaList, kuaioaPost, kuaioaPut } from './kuaioaApi';

const BASE = '/apps/kuaioa/attendance';

export const listAttendanceSheets = (params?: Record<string, unknown>) =>
  kuaioaList<Record<string, unknown>>(`${BASE}/sheets`, params);

export const getAttendanceSheet = (id: number) =>
  kuaioaGet<Record<string, unknown>>(`${BASE}/sheets/${id}`);

export const createAttendanceSheet = (data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/sheets`, data);

export const updateAttendanceSheet = (id: number, data: Record<string, unknown>) =>
  kuaioaPut<Record<string, unknown>>(`${BASE}/sheets/${id}`, data);

export const deleteAttendanceSheet = (id: number) => kuaioaDelete(`${BASE}/sheets/${id}`);

export const refreshAttendanceRoster = (id: number) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/sheets/${id}/refresh-roster`, {});

export const updateAttendanceDay = (
  sheetId: number,
  dayId: number,
  data: Record<string, unknown>,
) => kuaioaPut<Record<string, unknown>>(`${BASE}/sheets/${sheetId}/days/${dayId}`, data);

export const batchMarkAttendance = (sheetId: number, data: Record<string, unknown>) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/sheets/${sheetId}/batch-mark`, data);

export const submitAttendanceSheet = (id: number) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/sheets/${id}/submit`, {});

export const reopenAttendanceSheet = (id: number) =>
  kuaioaPost<Record<string, unknown>>(`${BASE}/sheets/${id}/reopen`, {});

export const exportAttendanceSheet = (id: number, filename: string) =>
  kuaioaDownloadBlob(`${BASE}/sheets/${id}/export`, filename);
