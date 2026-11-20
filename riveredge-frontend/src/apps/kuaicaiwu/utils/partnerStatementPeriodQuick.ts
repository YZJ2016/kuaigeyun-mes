import type { Dayjs } from 'dayjs';
import {
  detectReportPeriodPreset,
  resolveReportPeriodPreset,
  siteNow,
} from '../../../components/uni-report/reportPeriodUtils';

export type PartnerStatementPeriodPreset =
  | 'last_month'
  | 'this_month'
  | 'last_quarter'
  | 'this_quarter'
  | 'this_year';

export const PARTNER_STATEMENT_PERIOD_PRESETS: PartnerStatementPeriodPreset[] = [
  'last_month',
  'this_month',
  'last_quarter',
  'this_quarter',
  'this_year',
];

export function resolvePartnerStatementPeriodPreset(
  preset: PartnerStatementPeriodPreset,
): [Dayjs, Dayjs] {
  if (preset === 'last_quarter') {
    const now = siteNow();
    const month = now.month();
    const thisQStartMonth = Math.floor(month / 3) * 3;
    const thisQStart = now.month(thisQStartMonth).startOf('month');
    const lastQEnd = thisQStart.subtract(1, 'day');
    const lastQStartMonth = Math.floor(lastQEnd.month() / 3) * 3;
    const start = lastQEnd.month(lastQStartMonth).startOf('month');
    const end = start.add(2, 'month').endOf('month');
    return [start, end];
  }
  if (preset === 'this_month' || preset === 'this_quarter' || preset === 'this_year') {
    return resolveReportPeriodPreset(preset);
  }
  return resolveReportPeriodPreset('last_month');
}

export function defaultPartnerStatementPeriodRange(): [Dayjs, Dayjs] {
  return resolvePartnerStatementPeriodPreset('last_month');
}

export function detectPartnerStatementPeriodPreset(
  range: [Dayjs, Dayjs] | null | undefined,
): PartnerStatementPeriodPreset | 'custom' {
  if (!range?.[0]?.isValid?.() || !range?.[1]?.isValid?.()) {
    return 'last_month';
  }
  const start = range[0].format('YYYY-MM-DD');
  const end = range[1].format('YYYY-MM-DD');
  for (const preset of PARTNER_STATEMENT_PERIOD_PRESETS) {
    const [ps, pe] = resolvePartnerStatementPeriodPreset(preset);
    if (ps.format('YYYY-MM-DD') === start && pe.format('YYYY-MM-DD') === end) {
      return preset;
    }
  }
  const reportPreset = detectReportPeriodPreset(range);
  if (
    reportPreset === 'this_month' ||
    reportPreset === 'last_month' ||
    reportPreset === 'this_quarter' ||
    reportPreset === 'this_year'
  ) {
    return reportPreset;
  }
  return 'custom';
}