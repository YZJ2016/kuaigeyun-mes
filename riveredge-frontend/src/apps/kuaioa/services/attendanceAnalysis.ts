import { apiRequest } from '../../../services/api';

const BASE = '/apps/kuaioa/attendance-analysis';

export type AttendanceAnalysisSummary = {
  record_count: number;
  employee_count: number;
  normal_count: number;
  late_count: number;
  early_count: number;
  absent_count: number;
  leave_count: number;
  rest_count: number;
  other_count: number;
  late_minutes: number;
  early_leave_minutes: number;
  ot_hours: number;
  actual_hours: number;
  expected_hours: number;
  paid_hours: number;
  attendance_rate: number;
};

export type AttendanceAnalysisSeriesItem = {
  key: string;
  label: string;
  record_count: number;
  late_minutes: number;
  early_leave_minutes: number;
  ot_hours: number;
  actual_hours: number;
  expected_hours: number;
  normal_count: number;
  late_count: number;
  early_count: number;
  absent_count: number;
  leave_count: number;
  rest_count: number;
  other_count: number;
};

export type AttendanceAnalysisPayload = {
  granularity: 'day' | 'month';
  date_from: string;
  date_to: string;
  summary: AttendanceAnalysisSummary;
  series: AttendanceAnalysisSeriesItem[];
  result_distribution: Array<{ result: string; count: number }>;
  by_department: Array<AttendanceAnalysisSeriesItem & { label: string }>;
  by_employee: Array<
    AttendanceAnalysisSeriesItem & {
      label: string;
      employee_name?: string | null;
      employee_code?: string | null;
      department_name?: string | null;
    }
  >;
};

export async function getAttendanceAnalysis(params?: {
  granularity?: 'day' | 'month';
  date_from?: string;
  date_to?: string;
  department_name?: string;
  keyword?: string;
}): Promise<AttendanceAnalysisPayload> {
  const res = await apiRequest(BASE, { method: 'GET', params });
  return ((res as Record<string, unknown>)?.data ?? res) as AttendanceAnalysisPayload;
}
