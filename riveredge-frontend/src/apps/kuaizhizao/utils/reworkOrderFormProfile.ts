/**
 * 返工单 form-profile 消费：十段表单、排位列、extension_payload。
 */

import type { TFunction } from 'i18next';
import type { ReworkOrderFormProfile } from '../services/work-order';

export type ReworkProfileColumn = {
  key: string;
  label: string;
  sort?: number;
  required?: boolean;
  width?: number;
  type?: string;
};

export type ReworkProfileSection = {
  key: string;
  label: string;
  sort?: number;
  when_path_in?: string[];
  fields: string[];
};

/** profile 列 key → API 直接字段 */
export const REWORK_POSITION_DIRECT_KEYS = new Set([
  'line_no',
  'sequence',
  'station_name',
  'section_name',
  'station_code',
  'planned_headcount',
  'standard_minutes',
  'planned_start_at',
  'planned_end_at',
  'planned_qty',
  'owner_user_id',
  'owner_user_name',
  'remarks',
]);

/** profile 列 key → 落库字段名 */
export const REWORK_POSITION_KEY_ALIASES: Record<string, string> = {
  job_category: 'section_name',
  equipment_fixture: 'station_code',
  standard_unit_seconds: 'standard_minutes',
  theoretical_headcount: 'planned_headcount',
};

/** 头表已有静态字段，profile 段内跳过 */
export const REWORK_HEADER_STATIC_KEYS = new Set([
  'code',
  'original_work_order_id',
  'product_id',
  'product_code',
  'product_name',
  'quantity',
  'rework_type',
  'business_type',
  'product_line_code',
  'no_scrap_confirmed',
  'need_warehouse_in',
  'verify_month',
  'show_to_customer',
  'pqc_summary',
  'rework_reason',
  'planned_start_date',
  'planned_end_date',
  'start_work_order_operation_id',
  'route_id',
  'route_name',
  'work_center_id',
  'work_center_name',
  'operator_id',
  'operator_name',
  'remarks',
  'attachments',
  'rework_path_type',
]);

/** 头表 native 写入列（非 extension_payload） */
export const REWORK_HEADER_NATIVE_KEYS = new Set([
  'rework_reason',
  'product_code',
  'product_name',
  'quantity',
  'need_warehouse_in',
  'product_line_code',
  'planned_start_date',
  'planned_end_date',
]);

export const REWORK_HEADER_NATIVE_ALIASES: Record<string, string> = {
  planned_rework_at: 'planned_start_date',
};

const DEFAULT_POSITION_COLUMNS: ReworkProfileColumn[] = [
  { key: 'sequence', label: '序号', sort: 10, width: 60 },
  { key: 'station_name', label: '工序名称', sort: 20, width: 120, required: true },
  { key: 'section_name', label: '工段', sort: 30, width: 100 },
  { key: 'station_code', label: '工位', sort: 40, width: 100 },
  { key: 'planned_headcount', label: '计划人数', sort: 50, width: 90, type: 'decimal' },
  { key: 'standard_minutes', label: '标准工时(分)', sort: 60, width: 110, type: 'decimal' },
  { key: 'planned_qty', label: '计划产量', sort: 70, width: 90, type: 'decimal' },
  { key: 'owner_user_name', label: '责任人', sort: 80, width: 100 },
  { key: 'remarks', label: '备注', sort: 90, width: 120 },
];

export function sortedPositionPlanColumns(profile: ReworkOrderFormProfile | null): ReworkProfileColumn[] {
  const raw = profile?.position_plan_columns?.length
    ? profile.position_plan_columns
    : DEFAULT_POSITION_COLUMNS;
  return [...raw]
    .filter((c) => c?.key)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
    .map((c) => ({
      key: String(c.key),
      label: String(c.label || c.key),
      sort: c.sort,
      required: c.required,
      width: c.width,
      type: c.type,
    }));
}

export function sortedFormSections(profile: ReworkOrderFormProfile | null): ReworkProfileSection[] {
  const raw = profile?.form_sections || [];
  return [...raw]
    .filter((s) => s?.key && Array.isArray(s.fields))
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
    .map((s) => ({
      key: String(s.key),
      label: String(s.label || s.key),
      sort: s.sort,
      when_path_in: Array.isArray(s.when_path_in)
        ? s.when_path_in.map((v) => String(v).toLowerCase())
        : undefined,
      fields: (s.fields || []).map((f) => String(f)),
    }));
}

export function sectionsForPath(
  profile: ReworkOrderFormProfile | null,
  pathType?: string | null,
): ReworkProfileSection[] {
  const normalized = pathType ? String(pathType).toLowerCase() : '';
  return sortedFormSections(profile).filter((section) => {
    if (!section.when_path_in?.length) return true;
    if (!normalized) return false;
    return section.when_path_in.includes(normalized);
  });
}

export function resolvePositionStorageKey(columnKey: string): string {
  return REWORK_POSITION_KEY_ALIASES[columnKey] || columnKey;
}

export function resolveHeaderStorageKey(fieldKey: string): string {
  return REWORK_HEADER_NATIVE_ALIASES[fieldKey] || fieldKey;
}

export function resolveReworkFieldLabel(
  profile: ReworkOrderFormProfile | null,
  fieldKey: string,
  fallback: string,
): string {
  return profile?.field_labels?.[fieldKey] || fallback;
}

export function getPositionPlanCellValue(
  line: Record<string, unknown>,
  columnKey: string,
): unknown {
  const storageKey = resolvePositionStorageKey(columnKey);
  if (
    line[storageKey] !== undefined &&
    line[storageKey] !== null &&
    line[storageKey] !== ''
  ) {
    return line[storageKey];
  }
  if (columnKey !== storageKey && line[columnKey] !== undefined && line[columnKey] !== null) {
    return line[columnKey];
  }
  const payload = line.extension_payload as Record<string, unknown> | undefined;
  return payload?.[columnKey];
}

export function flattenPositionPlanForForm(line: Record<string, unknown>): Record<string, unknown> {
  const base: Record<string, unknown> = { ...line };
  const payload = (line.extension_payload as Record<string, unknown> | undefined) || {};
  for (const [key, value] of Object.entries(payload)) {
    if (base[key] === undefined || base[key] === null || base[key] === '') {
      base[key] = value;
    }
  }
  if (base.section_name != null && base.job_category == null) {
    base.job_category = base.section_name;
  }
  if (base.station_code != null && base.equipment_fixture == null) {
    base.equipment_fixture = base.station_code;
  }
  if (base.standard_minutes != null && base.standard_unit_seconds == null) {
    base.standard_unit_seconds = base.standard_minutes;
  }
  if (base.planned_headcount != null && base.theoretical_headcount == null) {
    base.theoretical_headcount = base.planned_headcount;
  }
  return base;
}

export function preparePositionPlanForApi(
  line: Record<string, unknown>,
  columns: ReworkProfileColumn[],
): Record<string, unknown> {
  const columnKeys = new Set(columns.map((c) => c.key));
  const direct: Record<string, unknown> = {};
  const overflow: Record<string, unknown> = {};

  for (const col of columns) {
    const rawKey = col.key;
    const storageKey = resolvePositionStorageKey(rawKey);
    const value = line[rawKey] ?? (rawKey !== storageKey ? line[storageKey] : undefined);
    if (value === undefined || value === '') continue;
    if (REWORK_POSITION_DIRECT_KEYS.has(storageKey)) {
      direct[storageKey] = value;
    } else if (columnKeys.has(rawKey)) {
      overflow[rawKey] = value;
    }
  }

  for (const key of REWORK_POSITION_DIRECT_KEYS) {
    if (line[key] !== undefined && line[key] !== '' && direct[key] === undefined) {
      direct[key] = line[key];
    }
  }

  return {
    line_no: direct.line_no,
    sequence: direct.sequence,
    station_name: String(direct.station_name || '').trim(),
    section_name: (direct.section_name as string | null | undefined) ?? null,
    station_code: (direct.station_code as string | null | undefined) ?? null,
    planned_headcount: direct.planned_headcount,
    standard_minutes: direct.standard_minutes,
    planned_start_at: direct.planned_start_at ?? null,
    planned_end_at: direct.planned_end_at ?? null,
    planned_qty: direct.planned_qty,
    owner_user_id: direct.owner_user_id,
    owner_user_name: (direct.owner_user_name as string | null | undefined) ?? null,
    remarks: (direct.remarks as string | null | undefined) ?? null,
    extension_payload: Object.keys(overflow).length ? overflow : null,
  };
}

export function buildEmptyPositionPlanRow(columns: ReworkProfileColumn[]): Record<string, unknown> {
  const row: Record<string, unknown> = { sequence: 1 };
  for (const col of columns) {
    if (col.type === 'decimal') row[col.key] = undefined;
  }
  return row;
}

export function collectProfileFieldKeys(profile: ReworkOrderFormProfile | null): string[] {
  const keys = new Set<string>(['rework_path_type']);
  for (const section of sortedFormSections(profile)) {
    for (const field of section.fields) {
      keys.add(field);
    }
  }
  return [...keys];
}

export function buildHeaderExtensionPayload(
  values: Record<string, unknown>,
  profile: ReworkOrderFormProfile | null,
  industryActive = false,
): Record<string, unknown> | null {
  if (!industryActive) return null;
  const keys = collectProfileFieldKeys(profile);
  const payload: Record<string, unknown> = {};
  for (const key of keys) {
    if (REWORK_HEADER_STATIC_KEYS.has(key) && key !== 'rework_path_type') {
      const storageKey = resolveHeaderStorageKey(key);
      if (REWORK_HEADER_NATIVE_KEYS.has(storageKey)) continue;
    }
    const storageKey = resolveHeaderStorageKey(key);
    if (REWORK_HEADER_NATIVE_KEYS.has(storageKey)) continue;
    const value = values[key];
    if (value !== undefined && value !== null && value !== '') {
      payload[key] = value;
    }
  }
  return Object.keys(payload).length ? payload : null;
}

export function mergeHeaderExtensionIntoForm(
  editing: { extension_payload?: Record<string, unknown> | null; planned_start_date?: string | null } | null | undefined,
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...(editing?.extension_payload || {}) };
  if (editing?.planned_start_date && merged.planned_rework_at == null) {
    merged.planned_rework_at = editing.planned_start_date;
  }
  return merged;
}

export function inferProfileFieldType(fieldKey: string, columnType?: string): string {
  if (columnType) return columnType;
  if (fieldKey.endsWith('_at') || fieldKey === 'planned_rework_at') return 'date';
  if (
    fieldKey.endsWith('_estimate') ||
    fieldKey.startsWith('estimated_') ||
    fieldKey.endsWith('_rmb')
  ) {
    return 'decimal';
  }
  if (
    fieldKey.endsWith('_notes') ||
    fieldKey.endsWith('_text') ||
    fieldKey.endsWith('_progress') ||
    fieldKey.endsWith('_record') ||
    fieldKey.endsWith('_diff') ||
    fieldKey === 'manufacturing_process_notes' ||
    fieldKey === 'quality_requirements_text'
  ) {
    return 'textarea';
  }
  return 'text';
}

export function formatProfileFieldDisplayValue(
  fieldKey: string,
  raw: unknown,
  t: TFunction,
  fieldType?: string,
): string {
  if (raw === undefined || raw === null || raw === '') return '-';
  const type = fieldType || inferProfileFieldType(fieldKey);
  if (type === 'boolean') {
    return raw ? t('common.yes') : t('common.no');
  }
  return String(raw);
}

export function buildPositionPlanDetailColumns(
  profile: ReworkOrderFormProfile | null,
  t: TFunction,
): Array<{ title: string; dataIndex: string; width?: number; render?: (v: unknown, row: Record<string, unknown>) => string }> {
  return sortedPositionPlanColumns(profile).map((col) => ({
    title: col.label,
    dataIndex: col.key,
    width: col.width,
    render: (_: unknown, row: Record<string, unknown>) => {
      const value = getPositionPlanCellValue(row, col.key);
      return formatProfileFieldDisplayValue(col.key, value, t, col.type);
    },
  }));
}
