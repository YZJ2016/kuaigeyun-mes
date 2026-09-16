/**
 * 实验委托 extension_payload（R-02 IQC 委托检测单对齐字段）。
 */

import type { LabRequest } from '../services/lab-request';

export const LAB_REQUEST_EXTENSION_KEYS = [
  'delegate_dept',
  'test_dept',
  'inspection_slip_no',
  'structure_special_test',
  'electronics_special_test',
  'structure_manager_approved',
  'electronics_manager_approved',
] as const;

export type LabRequestExtensionKey = (typeof LAB_REQUEST_EXTENSION_KEYS)[number];

export function flattenLabRequestForForm(
  row: LabRequest | null | undefined,
): Record<string, unknown> {
  if (!row) return {};
  const base: Record<string, unknown> = { ...row };
  const payload = row.extension_payload || {};
  for (const key of LAB_REQUEST_EXTENSION_KEYS) {
    if (base[key] === undefined && payload[key] !== undefined) {
      base[key] = payload[key];
    }
  }
  return base;
}

export function buildLabRequestExtensionPayload(
  values: Record<string, unknown>,
): Record<string, unknown> | null {
  const payload: Record<string, unknown> = {};
  for (const key of LAB_REQUEST_EXTENSION_KEYS) {
    const value = values[key];
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      payload[key] = String(value).trim();
    }
  }
  return Object.keys(payload).length ? payload : null;
}

export function getLabRequestExtensionValue(
  row: LabRequest | Record<string, unknown> | null | undefined,
  key: LabRequestExtensionKey,
): unknown {
  if (!row) return undefined;
  const record = row as Record<string, unknown>;
  if (record[key] !== undefined && record[key] !== null && record[key] !== '') {
    return record[key];
  }
  const payload = record.extension_payload as Record<string, unknown> | undefined;
  return payload?.[key];
}
