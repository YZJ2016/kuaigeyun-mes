import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  JSON_FIELD_NOW_TOKEN,
  formatJsonFieldDateValue,
  isJsonDateOnlyFieldKey,
  isJsonDateRangeFieldKey,
  parseJsonDateRangePair,
  resolveJsonDateRangePreset,
} from './jsonFieldDateShortcuts';

vi.mock('../../utils/format', () => ({
  getTimezoneFromSiteSetting: () => 'Asia/Shanghai',
}));

describe('jsonFieldDateShortcuts', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-10-22T01:56:00+08:00'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('parses start_/end_ pair keys', () => {
    expect(parseJsonDateRangePair('start_createtime')).toEqual({
      role: 'start',
      suffix: 'createtime',
      startKey: 'start_createtime',
      endKey: 'end_createtime',
    });
    expect(parseJsonDateRangePair('end_auditdate')?.startKey).toBe('start_auditdate');
    expect(isJsonDateRangeFieldKey('billno')).toBe(false);
    expect(isJsonDateRangeFieldKey('start_createtime')).toBe(true);
  });

  it('detects date-only vs datetime fields', () => {
    expect(isJsonDateOnlyFieldKey('start_auditdate')).toBe(true);
    expect(isJsonDateOnlyFieldKey('start_bizdate')).toBe(true);
    expect(isJsonDateOnlyFieldKey('end_createtime')).toBe(false);
    expect(isJsonDateOnlyFieldKey('start_modifytime')).toBe(false);
  });

  it('resolves today / last 3 days ending at now', () => {
    const today = resolveJsonDateRangePreset('today');
    expect(formatJsonFieldDateValue(today.start, false)).toBe('2026-10-22 00:00:00');
    expect(formatJsonFieldDateValue(today.end, false)).toBe('2026-10-22 01:56:00');

    const last3 = resolveJsonDateRangePreset('last_3_days');
    expect(formatJsonFieldDateValue(last3.start, false)).toBe('2026-10-20 00:00:00');
    expect(formatJsonFieldDateValue(last3.end, false)).toBe('2026-10-22 01:56:00');
  });

  it('resolves calendar week / month / year bounds', () => {
    // 2026-10-22 周四 → 本周 10-19（周一）~ 10-25（周日）
    const week = resolveJsonDateRangePreset('this_week');
    expect(formatJsonFieldDateValue(week.start, false)).toBe('2026-10-19 00:00:00');
    expect(formatJsonFieldDateValue(week.end, false)).toBe('2026-10-25 23:59:59');

    const month = resolveJsonDateRangePreset('this_month');
    expect(formatJsonFieldDateValue(month.start, false)).toBe('2026-10-01 00:00:00');
    expect(formatJsonFieldDateValue(month.end, false)).toBe('2026-10-31 23:59:59');

    const year = resolveJsonDateRangePreset('this_year');
    expect(formatJsonFieldDateValue(year.start, true)).toBe('2026-01-01');
    expect(formatJsonFieldDateValue(year.end, true)).toBe('2026-12-31');
  });

  it('exposes now token constant', () => {
    expect(JSON_FIELD_NOW_TOKEN).toBe('__NOW__');
  });
});
