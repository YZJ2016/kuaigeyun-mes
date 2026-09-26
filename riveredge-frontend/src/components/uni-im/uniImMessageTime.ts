/**
 * 会话气泡时间分隔：仿微信——首条或与上一条间隔大于 30 分钟才居中显示。
 */

import dayjs from '../../config/dayjs';
import { getTimezoneFromSiteSetting } from '../../utils/format';

/** 连续发言不打断，与上一条间隔大于 30 分钟再出时间条 */
export const IM_MESSAGE_TIME_GAP_MS = 30 * 60 * 1000;

function parseMessageTime(value: string | null | undefined) {
  if (!value) {
    return null;
  }
  const tz = getTimezoneFromSiteSetting();
  const text = String(value).trim();
  const d = /Z|[+-]\d{2}:?\d{2}$/i.test(text)
    ? dayjs(text).tz(tz)
    : dayjs.tz(text.replace(' ', 'T'), tz);
  return d.isValid() ? d : null;
}

export function shouldShowImMessageTimeDivider(
  previousCreatedAt: string | null | undefined,
  currentCreatedAt: string | null | undefined,
): boolean {
  const current = parseMessageTime(currentCreatedAt);
  if (!current) {
    return false;
  }
  const previous = parseMessageTime(previousCreatedAt);
  if (!previous) {
    return true;
  }
  return current.valueOf() - previous.valueOf() > IM_MESSAGE_TIME_GAP_MS;
}

/**
 * 居中时间条文案（站点时区）：
 * 当天 HH:mm；昨天「昨天 HH:mm」；同年 M月D日 HH:mm；跨年 YYYY年M月D日 HH:mm。
 */
export function formatImMessageTimeDivider(
  value: string | null | undefined,
  yesterdayLabel: string,
): string {
  const d = parseMessageTime(value);
  if (!d) {
    return '';
  }
  const tz = getTimezoneFromSiteSetting();
  const now = dayjs().tz(tz);
  const clock = d.format('HH:mm');
  if (d.isSame(now, 'day')) {
    return clock;
  }
  if (d.isSame(now.subtract(1, 'day'), 'day')) {
    return `${yesterdayLabel} ${clock}`;
  }
  if (d.isSame(now, 'year')) {
    return `${d.format('M')}月${d.format('D')}日 ${clock}`;
  }
  return `${d.format('YYYY')}年${d.format('M')}月${d.format('D')}日 ${clock}`;
}
