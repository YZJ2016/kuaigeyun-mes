/**
 * 接口请求体字段勾选：start_/end_ 日期时间快捷与成对填充。
 * 「此刻」写入 __NOW__，由后端在每次调用时解析为站点墙钟。
 */

import dayjs, { type Dayjs } from '../../config/dayjs';
import { getTimezoneFromSiteSetting } from '../../utils/format';

/** 每次调用解析为当前站点墙钟的占位值 */
export const JSON_FIELD_NOW_TOKEN = '__NOW__';

function isNowToken(value: string): boolean {
  const text = value.trim();
  if (text === JSON_FIELD_NOW_TOKEN) return true;
  return text === '此刻（每次调用）' || text === '此刻(每次调用)' || text === '此刻';
}

/** 发送前把 __NOW__ 换成站点当前墙钟（与后端一致，双保险） */
export function resolveJsonRequestDynamicTokens(value: unknown, nowText?: string): unknown {
  const resolvedNow = nowText ?? formatJsonFieldDateValue(siteNowDayjs(), false);
  if (typeof value === 'string' && isNowToken(value)) return resolvedNow;
  if (Array.isArray(value)) {
    return value.map((item) => resolveJsonRequestDynamicTokens(item, resolvedNow));
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [
        key,
        resolveJsonRequestDynamicTokens(item, resolvedNow),
      ]),
    );
  }
  return value;
}

/**
 * 去掉空字符串 / null，避免苍穹 DateTime 收到 "" 报 NumberFormatException。
 * 禁止删空对象：苍穹 getList 契约要求顶层 data（可为空 {}），删掉会报「请求参数没有 data 数据」。
 */
export function omitEmptyJsonValues(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value
      .map((item) => omitEmptyJsonValues(item))
      .filter((item) => item !== undefined && item !== null && !(typeof item === 'string' && item.trim() === ''));
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      const next = omitEmptyJsonValues(item);
      if (next === undefined || next === null) continue;
      if (typeof next === 'string' && next.trim() === '') continue;
      out[key] = next;
    }
    return out;
  }
  return value;
}

export function prepareJsonRequestBody(value: unknown): unknown {
  return omitEmptyJsonValues(resolveJsonRequestDynamicTokens(value));
}

export type JsonDateRangeRole = 'start' | 'end';

export type JsonDateRangePair = {
  role: JsonDateRangeRole;
  suffix: string;
  startKey: string;
  endKey: string;
};

export type JsonDateRangePreset =
  | 'today'
  | 'last_3_days'
  | 'this_week'
  | 'this_month'
  | 'this_year';

const DATE_SUFFIX_RE =
  /^(?:biz|bill|audit|create|modify|update|close|change|deliver|plan|order|doc)?(?:date|time|datetime)$/i;

/** 是否为可走日期快捷的 start_/end_ 字段 */
export function isJsonDateRangeFieldKey(key: string): boolean {
  return parseJsonDateRangePair(key) != null;
}

export function parseJsonDateRangePair(key: string): JsonDateRangePair | null {
  const trimmed = key.trim();
  const match = /^(start|end)_(.+)$/i.exec(trimmed);
  if (!match) return null;
  const suffix = match[2];
  if (!DATE_SUFFIX_RE.test(suffix) && !/(date|time)/i.test(suffix)) return null;
  const role = match[1].toLowerCase() as JsonDateRangeRole;
  return {
    role,
    suffix,
    startKey: `start_${suffix}`,
    endKey: `end_${suffix}`,
  };
}

/** auditdate / bizdate 等偏日期；createtime / modifytime 等带时分秒 */
export function isJsonDateOnlyFieldKey(key: string): boolean {
  const pair = parseJsonDateRangePair(key);
  const suffix = (pair?.suffix ?? key).toLowerCase();
  if (suffix.includes('time') || suffix.includes('datetime')) return false;
  if (suffix.endsWith('date') || suffix.includes('date')) return true;
  return false;
}

/** 站点时区；未下发时返回 null（避免拖垮整表单，回退本地墙钟） */
function safeSiteTimezone(): string | null {
  try {
    return getTimezoneFromSiteSetting();
  } catch {
    return null;
  }
}

export function siteNowDayjs(): Dayjs {
  const tz = safeSiteTimezone();
  return tz ? dayjs().tz(tz) : dayjs();
}

export function formatJsonFieldDateValue(value: Dayjs, dateOnly: boolean): string {
  const tz = safeSiteTimezone();
  const wall = tz ? value.tz(tz) : value;
  return dateOnly ? wall.format('YYYY-MM-DD') : wall.format('YYYY-MM-DD HH:mm:ss');
}

export function parseJsonFieldDateValue(raw: string, dateOnly: boolean): Dayjs | null {
  const text = raw.trim();
  if (!text || text === JSON_FIELD_NOW_TOKEN) return null;
  const tz = safeSiteTimezone();
  if (dateOnly && /^\d{4}-\d{2}-\d{2}$/.test(text)) {
    const d = tz ? dayjs.tz(`${text} 00:00:00`, tz) : dayjs(`${text} 00:00:00`);
    return d.isValid() ? d : null;
  }
  if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(text)) {
    const normalized = text.replace('T', ' ');
    const d = tz ? dayjs.tz(normalized, tz) : dayjs(normalized);
    return d.isValid() ? d : null;
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    const d = tz ? dayjs.tz(`${text} 00:00:00`, tz) : dayjs(`${text} 00:00:00`);
    return d.isValid() ? d : null;
  }
  const d = dayjs(text);
  if (!d.isValid()) return null;
  return tz ? d.tz(tz) : d;
}

export function resolveJsonDateRangePreset(
  preset: JsonDateRangePreset,
): { start: Dayjs; end: Dayjs } {
  const now = siteNowDayjs();
  switch (preset) {
    case 'today':
      return { start: now.startOf('day'), end: now };
    case 'last_3_days':
      return { start: now.subtract(2, 'day').startOf('day'), end: now };
    case 'this_week': {
      // 周一为一周起始（与中文业务周 / 图示一致，不依赖 dayjs locale）
      const weekday = now.day(); // 0=周日 … 6=周六
      const daysFromMonday = weekday === 0 ? 6 : weekday - 1;
      const start = now.startOf('day').subtract(daysFromMonday, 'day');
      const end = start.add(6, 'day').endOf('day');
      return { start, end };
    }
    case 'this_month':
      return { start: now.startOf('month'), end: now.endOf('month') };
    case 'this_year':
      return { start: now.startOf('year'), end: now.endOf('year') };
    default:
      return { start: now.startOf('day'), end: now };
  }
}

export function formatJsonDateRangePreview(
  start: Dayjs,
  end: Dayjs,
  dateOnly: boolean,
): string {
  if (dateOnly) {
    return `${start.format('MM-DD')} ~ ${end.format('MM-DD')}`;
  }
  return `${start.format('MM-DD HH:mm')} ~ ${end.format('MM-DD HH:mm')}`;
}

export type JsonDateShortcutMenuKey =
  | 'now'
  | JsonDateRangePreset
  | 'clear';

export type JsonDateShortcutMenuItem = {
  key: JsonDateShortcutMenuKey;
  label: string;
};

export function buildJsonDateShortcutMenuItems(dateOnly: boolean): JsonDateShortcutMenuItem[] {
  const presets: JsonDateRangePreset[] = [
    'today',
    'last_3_days',
    'this_week',
    'this_month',
    'this_year',
  ];
  const labels: Record<JsonDateRangePreset, string> = {
    today: '当天',
    last_3_days: '最近三天',
    this_week: '本周',
    this_month: '本月',
    this_year: '本年',
  };
  return [
    { key: 'now', label: '此刻 (每次调用) [动态]' },
    ...presets.map((preset) => {
      const { start, end } = resolveJsonDateRangePreset(preset);
      const range = formatJsonDateRangePreview(start, end, dateOnly);
      return {
        key: preset,
        label: `${labels[preset]} (${range}) · 成对填充`,
      };
    }),
    { key: 'clear', label: '清空' },
  ];
}
