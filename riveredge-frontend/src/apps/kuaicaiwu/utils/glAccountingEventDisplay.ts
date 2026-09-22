import type { TFunction } from 'i18next';

const NS = 'app.kuaicaiwu.gl.vouchers.events';

function pascalToSnake(value: string): string {
  const text = String(value || '').trim();
  if (!text) return '';
  if (text.includes('_') || text === text.toLowerCase()) return text.toLowerCase();
  const out: string[] = [];
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch >= 'A' && ch <= 'Z' && i > 0) out.push('_');
    out.push(ch.toLowerCase());
  }
  return out.join('');
}

function lookupI18n(t: TFunction, group: 'sourceDocType' | 'eventType', raw: string): string {
  const key = String(raw || '').trim();
  if (!key) return '';
  const candidates = Array.from(new Set([key, key.toLowerCase(), pascalToSnake(key)]));
  for (const candidate of candidates) {
    const translated = t(`${NS}.${group}.${candidate}`, { defaultValue: '' });
    if (translated) return translated;
  }
  return '';
}

export function resolveGlSourceDocTypeLabel(
  raw: string | null | undefined,
  t: TFunction,
  apiLabel?: string | null,
): string {
  const fromApi = String(apiLabel ?? '').trim();
  if (fromApi && fromApi !== String(raw ?? '').trim()) return fromApi;
  const resolved = lookupI18n(t, 'sourceDocType', String(raw ?? ''));
  return resolved || fromApi || String(raw ?? '').trim();
}

export function resolveGlAccountingEventTypeLabel(
  raw: string | null | undefined,
  t: TFunction,
  apiLabel?: string | null,
): string {
  const fromApi = String(apiLabel ?? '').trim();
  if (fromApi && fromApi !== String(raw ?? '').trim()) return fromApi;
  const resolved = lookupI18n(t, 'eventType', String(raw ?? ''));
  return resolved || fromApi || String(raw ?? '').trim();
}

export function resolveGlAccountingEventSummary(
  row: {
    notes?: string | null;
    event_type?: string | null;
    event_type_label?: string | null;
  },
  t: TFunction,
): string {
  const eventLabel = resolveGlAccountingEventTypeLabel(row.event_type, t, row.event_type_label);
  const notes = String(row.notes ?? '').trim();
  const eventType = String(row.event_type ?? '').trim();
  if (!notes || notes === eventType || lookupI18n(t, 'eventType', notes)) {
    return eventLabel || '—';
  }
  return notes;
}

export function normalizeGlSourceDocTypeOptions(
  options: Array<{ value: string; label: string } | string> | undefined,
  t: TFunction,
): Array<{ value: string; label: string }> {
  return (options ?? []).map((item) => {
    if (typeof item === 'string') {
      return { value: item, label: resolveGlSourceDocTypeLabel(item, t) };
    }
    return {
      value: item.value,
      label: resolveGlSourceDocTypeLabel(item.value, t, item.label),
    };
  });
}
