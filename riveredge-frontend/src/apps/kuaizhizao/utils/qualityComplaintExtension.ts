/**
 * 质量投诉 extension_payload（R-11 模板对齐字段）。
 */

import type { QualityComplaint } from '../services/quality-complaint';

export const QUALITY_COMPLAINT_EXTENSION_KEYS = [
  'inspection_qty',
  'defect_qty',
  'defect_rate_pct',
  'used_qty',
  'root_cause_analysis',
  'corrective_action',
  'containment_action',
] as const;

export type QualityComplaintExtensionKey = (typeof QUALITY_COMPLAINT_EXTENSION_KEYS)[number];

export function flattenComplaintForForm(
  row: QualityComplaint | null | undefined,
): Record<string, unknown> {
  if (!row) return {};
  const base: Record<string, unknown> = { ...row };
  const payload = row.extension_payload || {};
  for (const key of QUALITY_COMPLAINT_EXTENSION_KEYS) {
    if (base[key] === undefined && payload[key] !== undefined) {
      base[key] = payload[key];
    }
  }
  return base;
}

export function buildComplaintExtensionPayload(
  values: Record<string, unknown>,
): Record<string, unknown> | null {
  const payload: Record<string, unknown> = {};
  for (const key of QUALITY_COMPLAINT_EXTENSION_KEYS) {
    if (key === 'defect_rate_pct') continue;
    const value = values[key];
    if (value !== undefined && value !== null && value !== '') {
      payload[key] = value;
    }
  }
  const inspectionQty = payload.inspection_qty;
  const defectQty = payload.defect_qty;
  if (inspectionQty != null && defectQty != null) {
    const iq = Number(inspectionQty);
    const dq = Number(defectQty);
    if (Number.isFinite(iq) && iq > 0 && Number.isFinite(dq)) {
      payload.defect_rate_pct = Math.round((dq / iq) * 10000) / 100;
    }
  }
  return Object.keys(payload).length ? payload : null;
}

export function getComplaintExtensionValue(
  row: QualityComplaint | Record<string, unknown> | null | undefined,
  key: QualityComplaintExtensionKey,
): unknown {
  if (!row) return undefined;
  const record = row as Record<string, unknown>;
  if (record[key] !== undefined && record[key] !== null && record[key] !== '') {
    return record[key];
  }
  const payload = record.extension_payload as Record<string, unknown> | undefined;
  return payload?.[key];
}
