/**
 * 样品加工 form-profile：种类校验与必填字段。
 */

import type { SampleProcessFormProfile } from '../services/sample-process';

export function requiredFieldsForKind(
  profile: SampleProcessFormProfile | null,
  kind: string | undefined,
  industryActive: boolean,
): string[] {
  if (!industryActive || !kind) return [];
  const rules = profile?.validation_rules || [];
  for (const rule of rules) {
    const kinds = rule.when_kind_in || [];
    if (kinds.includes(kind)) {
      return Array.isArray(rule.require) ? rule.require.map(String) : [];
    }
  }
  return [];
}

export function validationMessageForKind(
  profile: SampleProcessFormProfile | null,
  kind: string | undefined,
  industryActive: boolean,
): string | undefined {
  if (!industryActive || !kind) return undefined;
  const rules = profile?.validation_rules || [];
  for (const rule of rules) {
    const kinds = rule.when_kind_in || [];
    if (kinds.includes(kind) && rule.message) {
      return String(rule.message);
    }
  }
  return undefined;
}

export function isFieldRequiredForKind(
  profile: SampleProcessFormProfile | null,
  kind: string | undefined,
  fieldKey: string,
  industryActive: boolean,
): boolean {
  return requiredFieldsForKind(profile, kind, industryActive).includes(fieldKey);
}
