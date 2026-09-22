/**
 * 试流 form-profile 消费：头字段、工序链预览、extension_payload。
 */

import type { TFunction } from 'i18next';
import type { TrialFlowBusinessType, TrialFlowFormProfile } from '../services/trial-flow';

export type TrialFlowProfileHeaderField = {
  key: string;
  label: string;
  sort?: number;
  type?: string;
  options?: Array<{ value: string; label: string }>;
};

export type TrialFlowProfileStep = {
  step_key: string;
  step_name: string;
  dept_code?: string;
  sort?: number;
  phase?: string;
};

export function sortedHeaderFields(
  profile: TrialFlowFormProfile | null,
  industryActive = false,
): TrialFlowProfileHeaderField[] {
  if (!industryActive) return [];
  const raw = profile?.header_fields || [];
  return [...raw]
    .filter((f) => f?.key)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
    .map((f) => ({
      key: String(f.key),
      label: String(f.label || f.key),
      sort: f.sort,
      type: f.type,
      options: Array.isArray(f.options)
        ? f.options.map((o) => ({
            value: String(o.value),
            label: String(o.label ?? o.value),
          }))
        : undefined,
    }));
}

export function stepsForBusinessType(
  profile: TrialFlowFormProfile | null,
  businessType: TrialFlowBusinessType | string,
  industryActive = false,
): TrialFlowProfileStep[] {
  if (!industryActive) return [];
  const items = profile?.step_templates?.[businessType] || [];
  return [...items]
    .filter((s) => s?.step_key)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
    .map((s) => ({
      step_key: String(s.step_key),
      step_name: String(s.step_name || s.step_key),
      dept_code: s.dept_code ? String(s.dept_code) : undefined,
      sort: s.sort,
      phase: s.phase ? String(s.phase) : undefined,
    }));
}

export function resolveTrialFlowFieldLabel(
  profile: TrialFlowFormProfile | null,
  fieldKey: string,
  fallback: string,
): string {
  return profile?.field_labels?.[fieldKey] || fallback;
}

export function buildHeaderExtensionPayload(
  values: Record<string, unknown>,
  profile: TrialFlowFormProfile | null,
  industryActive = false,
): Record<string, unknown> | null {
  if (!industryActive) return null;
  const fields = sortedHeaderFields(profile, true);
  if (!fields.length) return null;
  const payload: Record<string, unknown> = {};
  for (const field of fields) {
    const value = values[field.key];
    if (value !== undefined && value !== null && value !== '') {
      payload[field.key] = value;
    }
  }
  return Object.keys(payload).length ? payload : null;
}

export function mergeHeaderExtensionIntoForm(
  editing: { extension_payload?: Record<string, unknown> | null } | null | undefined,
): Record<string, unknown> {
  return { ...(editing?.extension_payload || {}) };
}

export function formatHeaderFieldDisplayValue(
  field: TrialFlowProfileHeaderField,
  raw: unknown,
  t: TFunction,
): string {
  if (raw === undefined || raw === null || raw === '') return '-';
  if (field.type === 'boolean') {
    return raw ? t('common.yes') : t('common.no');
  }
  if (field.type === 'select' && field.options?.length) {
    const hit = field.options.find((o) => o.value === String(raw));
    if (hit) return hit.label;
  }
  return String(raw);
}
