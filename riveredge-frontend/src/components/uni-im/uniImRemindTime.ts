/**
 * 从 IM 对话正文识别时间表达，渲染为下划线链接并预填「加入提醒」。
 * 按站点时区解释相对日/钟点（configs.timezone）。
 */
import type { Dayjs } from 'dayjs';
import dayjs from '../../config/dayjs';
import { getTimezoneFromSiteSetting } from '../../utils/format';

export type ImRemindTimeHit = {
  /** 正文是否含时间相关表达 */
  matched: boolean;
  /** 能解析出的提醒时刻（站点墙钟）；解析失败则为 null，弹窗可回退默认值 */
  remindAt: Dayjs | null;
};

export type ImTextSegment =
  | { kind: 'text'; text: string }
  | { kind: 'time'; text: string; remindAt: Dayjs | null }
  | { kind: 'document'; text: string };

/**
 * 单据编号形态：字母前缀 + 较长数字段（如 XS202609150004）。
 * 要求含日期长度数字，避免手机号/短码误链；不做类型前缀猜测。
 */
const DOCUMENT_CODE_RE = /[A-Za-z][A-Za-z0-9]{0,7}\d{10,18}/g;

const WEEKDAY_MAP: Record<string, number> = {
  日: 0,
  天: 0,
  一: 1,
  二: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
};

/** 钟点/分钟：阿拉伯或中文数字（八、十二、二十三） */
const CLOCK_NUM = String.raw`(?:\d{1,2}|[零〇一二两三四五六七八九十]{1,3})`;

const CN_DIGIT: Record<string, number> = {
  零: 0,
  〇: 0,
  一: 1,
  二: 2,
  两: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
};

/**
 * 匹配可点击的时间片段（长模式优先；要求日期有分隔符，避免单号如 XS202609150004 误链）。
 */
const TIME_SPAN_RE = new RegExp(
  String.raw`(?:大后天|明天|后天|今天|今晚|明早|今早)?(?:上午|下午|晚上|中午|凌晨|早上|早晨)?\s*(?:\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}[日号]?(?:\s*[T\s]?\d{1,2}[:：]\d{2}(?::\d{2})?)?|\d{1,2}\s*月\s*\d{1,2}\s*[日号]?(?:\s*(?:上午|下午|晚上|中午|凌晨)?\s*${CLOCK_NUM}\s*(?:点半|[:：]\d{2}|点\s*${CLOCK_NUM}\s*分?|点))?|(?:下?周|本周|这周|星期|礼拜)[一二三四五六日天](?:\s*(?:上午|下午|晚上|中午|凌晨)?\s*${CLOCK_NUM}\s*(?:点半|[:：]\d{2}|点))?|(?:上午|下午|晚上|中午|凌晨|早上|早晨)\s*${CLOCK_NUM}\s*(?:点半|[:：]\d{2}|点\s*${CLOCK_NUM}\s*分?|点)|${CLOCK_NUM}[:：]\d{2}|${CLOCK_NUM}\s*点半|${CLOCK_NUM}\s*点(?:\s*${CLOCK_NUM}\s*分?)?|大后天|明天|后天|今晚|明早|今早|今天|(?:下?周|本周|这周|星期|礼拜)[一二三四五六日天])`,
  'g',
);

/** 粗检：是否像在谈时间 */
const TIME_HINT_RE =
  /(?:\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}|[一二三四五六七八九十\d]{1,2}\s*月\s*[一二三四五六七八九十\d]{1,3}\s*[日号]?|\d{1,2}[:：]\d{2}|[上下午晚凌晨中午早上早晨]*\s*[零〇一二两三四五六七八九十\d]{1,3}\s*点|\d{1,2}\s*点半|明天|后天|大后天|今晚|明早|今早|今天|下周|本周|周一|周二|周三|周四|周五|周六|周日|星期|礼拜|上午|下午|晚上|中午|凌晨)/;

function parseCnOrArabicNumber(raw: string): number | null {
  const s = String(raw || '').trim();
  if (!s) {
    return null;
  }
  if (/^\d{1,2}$/.test(s)) {
    return Number(s);
  }
  if (s === '十') {
    return 10;
  }
  if (s.length === 2 && s[0] === '十') {
    const ones = CN_DIGIT[s[1]];
    return ones != null ? 10 + ones : null;
  }
  const tensMatch = s.match(/^([一二三四五六七八九两])十([一二三四五六七八九])?$/);
  if (tensMatch) {
    const tens = CN_DIGIT[tensMatch[1]];
    if (tens == null) {
      return null;
    }
    return tens * 10 + (tensMatch[2] ? CN_DIGIT[tensMatch[2]] ?? 0 : 0);
  }
  if (s.length === 1 && CN_DIGIT[s] != null) {
    return CN_DIGIT[s];
  }
  return null;
}

function nowInSiteTz(): Dayjs {
  const tz = getTimezoneFromSiteSetting();
  return dayjs().tz(tz);
}

function applyClock(
  base: Dayjs,
  hour: number,
  minute: number,
  meridiem?: 'am' | 'pm' | 'night' | 'noon' | 'morning' | null,
): Dayjs {
  let h = hour;
  if (meridiem === 'pm' || meridiem === 'night') {
    if (h < 12) {
      h += 12;
    }
  } else if (meridiem === 'am' || meridiem === 'morning') {
    if (h === 12) {
      h = 0;
    }
  } else if (meridiem === 'noon') {
    if (h < 12) {
      h = 12;
    }
  } else if (h >= 0 && h <= 6 && !meridiem) {
    // 「3点」无上下午时：凌晨像的保持；其余按字面小时
  }
  return base.hour(h).minute(minute).second(0).millisecond(0);
}

function parseMeridiem(chunk: string): 'am' | 'pm' | 'night' | 'noon' | 'morning' | null {
  if (/凌晨|早上|早晨|上午|今早|明早/.test(chunk)) {
    return /凌晨/.test(chunk) ? 'am' : 'morning';
  }
  if (/中午/.test(chunk)) {
    return 'noon';
  }
  if (/下午/.test(chunk)) {
    return 'pm';
  }
  if (/晚上|今晚|傍晚/.test(chunk)) {
    return 'night';
  }
  return null;
}

function nextWeekday(from: Dayjs, targetDow: number, weekOffset: number): Dayjs {
  const current = from.day();
  let delta = (targetDow - current + 7) % 7;
  if (delta === 0 && weekOffset === 0) {
    delta = 7;
  }
  return from.add(weekOffset * 7 + delta, 'day').startOf('day');
}

function tryParseAbsolute(text: string, tz: string): Dayjs | null {
  const iso = text.match(
    /(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})[日号]??(?:\s*[T\s]?(\d{1,2})[:：](\d{2})(?::(\d{2}))?)?/,
  );
  if (iso) {
    const y = Number(iso[1]);
    const m = Number(iso[2]);
    const d = Number(iso[3]);
    const hh = iso[4] != null ? Number(iso[4]) : 9;
    const mm = iso[5] != null ? Number(iso[5]) : 0;
    const ss = iso[6] != null ? Number(iso[6]) : 0;
    const stamp = `${String(y).padStart(4, '0')}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')} ${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
    const parsed = dayjs.tz(stamp, tz);
    return parsed.isValid() ? parsed : null;
  }

  const md = text.match(
    /(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?(?:\s*(上午|下午|晚上|中午|凌晨)?\s*(\d{1,2})\s*[:：点](\d{1,2})?\s*分?)?/,
  );
  if (md) {
    const now = dayjs().tz(tz);
    let year = now.year();
    const month = Number(md[1]);
    const day = Number(md[2]);
    let candidate = dayjs.tz(
      `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')} 09:00:00`,
      tz,
    );
    if (candidate.isBefore(now.startOf('day'))) {
      year += 1;
      candidate = dayjs.tz(
        `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')} 09:00:00`,
        tz,
      );
    }
    if (md[4]) {
      const meridiem = parseMeridiem(md[3] || text);
      const minute = md[5] != null ? Number(md[5]) : /点半/.test(text) ? 30 : 0;
      return applyClock(candidate, Number(md[4]), minute, meridiem);
    }
    return candidate;
  }

  return null;
}

function tryParseRelative(text: string, now: Dayjs): Dayjs | null {
  let base = now.startOf('day');
  let dayShifted = false;

  if (/大后天/.test(text)) {
    base = base.add(3, 'day');
    dayShifted = true;
  } else if (/后天/.test(text)) {
    base = base.add(2, 'day');
    dayShifted = true;
  } else if (/明天|明早/.test(text)) {
    base = base.add(1, 'day');
    dayShifted = true;
  } else if (/今天|今早|今晚/.test(text)) {
    dayShifted = true;
  }

  const week = text.match(/(下?周|本周|这周|星期|礼拜)([一二三四五六日天])/);
  if (week) {
    const target = WEEKDAY_MAP[week[2]];
    if (target != null) {
      const weekOffset = /下周/.test(week[1]) ? 1 : 0;
      base = nextWeekday(now, target, weekOffset);
      dayShifted = true;
    }
  }

  const clock = text.match(
    new RegExp(
      String.raw`(上午|下午|晚上|中午|凌晨|早上|早晨)?\s*(${CLOCK_NUM})\s*(?:点半|[:：](\d{2})|点\s*(${CLOCK_NUM})\s*分?|点)`,
    ),
  );
  const hm = text.match(/(?:^|[^\d零〇一二两三四五六七八九十])(\d{1,2})[:：](\d{2})(?:[^\d]|$)/);

  if (clock) {
    const meridiem = parseMeridiem((clock[1] || '') + text);
    const hour = parseCnOrArabicNumber(clock[2]);
    if (hour == null || hour > 23) {
      // 无法解析钟点时继续走下方仅日期默认
    } else {
      const minute = clock[0].includes('点半')
        ? 30
        : clock[3] != null
          ? Number(clock[3])
          : clock[4] != null
            ? (parseCnOrArabicNumber(clock[4]) ?? 0)
            : 0;
      const at = applyClock(dayShifted ? base : now.startOf('day'), hour, minute, meridiem);
      if (!dayShifted && at.isBefore(now)) {
        return at.add(1, 'day');
      }
      return at;
    }
  }

  if (hm) {
    const hour = Number(hm[1]);
    const minute = Number(hm[2]);
    const meridiem = parseMeridiem(text);
    const at = applyClock(dayShifted ? base : now.startOf('day'), hour, minute, meridiem);
    if (!dayShifted && at.isBefore(now)) {
      return at.add(1, 'day');
    }
    return at;
  }

  if (dayShifted) {
    // 只有「明天」等日期：默认上午 9 点
    const meridiem = parseMeridiem(text);
    if (meridiem === 'night' || /今晚/.test(text)) {
      return applyClock(base, 20, 0, 'night');
    }
    if (meridiem === 'noon') {
      return applyClock(base, 12, 0, 'noon');
    }
    if (meridiem === 'pm') {
      return applyClock(base, 14, 0, 'pm');
    }
    return applyClock(base, 9, 0, 'morning');
  }

  return null;
}

/**
 * 从消息正文提取提醒时间。
 * 无站点时区时不做猜测（不匹配），避免第二套时区逻辑。
 */
export function extractImRemindAtFromText(text: string): ImRemindTimeHit {
  const raw = String(text || '').trim();
  if (!raw || !TIME_HINT_RE.test(raw)) {
    return { matched: false, remindAt: null };
  }

  let now: Dayjs;
  let tz: string;
  try {
    tz = getTimezoneFromSiteSetting();
    now = nowInSiteTz();
  } catch {
    return { matched: false, remindAt: null };
  }

  const absolute = tryParseAbsolute(raw, tz);
  if (absolute) {
    return { matched: true, remindAt: absolute };
  }

  const relative = tryParseRelative(raw, now);
  if (relative) {
    return { matched: true, remindAt: relative };
  }

  return { matched: true, remindAt: null };
}

/** 将正文拆成普通文本 + 时间链接 + 单据编号链接 */
export function splitImTextByTimeLinks(text: string): ImTextSegment[] {
  return splitImMessageBodyLinks(text);
}

export function splitImMessageBodyLinks(text: string): ImTextSegment[] {
  const raw = String(text ?? '');
  if (!raw) {
    return [];
  }

  type RawHit = { start: number; end: number; segment: ImTextSegment };
  const hits: RawHit[] = [];

  const docRe = new RegExp(DOCUMENT_CODE_RE.source, 'g');
  let docMatch: RegExpExecArray | null = docRe.exec(raw);
  while (docMatch) {
    const span = docMatch[0];
    hits.push({
      start: docMatch.index,
      end: docMatch.index + span.length,
      segment: { kind: 'document', text: span },
    });
    docMatch = docRe.exec(raw);
  }

  if (TIME_HINT_RE.test(raw)) {
    const timeRe = new RegExp(TIME_SPAN_RE.source, 'g');
    let timeMatch: RegExpExecArray | null = timeRe.exec(raw);
    while (timeMatch) {
      const span = timeMatch[0];
      if (span.trim()) {
        const hit = extractImRemindAtFromText(span);
        hits.push({
          start: timeMatch.index,
          end: timeMatch.index + span.length,
          segment: { kind: 'time', text: span, remindAt: hit.remindAt },
        });
      }
      timeMatch = timeRe.exec(raw);
    }
  }

  if (hits.length === 0) {
    return [{ kind: 'text', text: raw }];
  }

  hits.sort((a, b) => a.start - b.start || b.end - a.end);
  const accepted: RawHit[] = [];
  for (const hit of hits) {
    const overlaps = accepted.some((prev) => hit.start < prev.end && hit.end > prev.start);
    if (!overlaps) {
      accepted.push(hit);
    }
  }
  accepted.sort((a, b) => a.start - b.start);

  const segments: ImTextSegment[] = [];
  let lastIndex = 0;
  for (const hit of accepted) {
    if (hit.start > lastIndex) {
      segments.push({ kind: 'text', text: raw.slice(lastIndex, hit.start) });
    }
    segments.push(hit.segment);
    lastIndex = hit.end;
  }
  if (lastIndex < raw.length) {
    segments.push({ kind: 'text', text: raw.slice(lastIndex) });
  }
  return segments.length > 0 ? segments : [{ kind: 'text', text: raw }];
}

export function defaultImRemindAtFallback(): Dayjs {
  try {
    return nowInSiteTz().add(1, 'hour').startOf('minute');
  } catch {
    return dayjs().add(1, 'hour').startOf('minute');
  }
}
