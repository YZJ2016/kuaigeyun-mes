/**
 * KU-AI 运营层纯函数（spec 184：调用分析日期补齐 / 能力标签 / 审计状态分档）。
 *
 * 全部为纯函数，供 pages/insights、pages/trust 复用；
 * 单测：node --experimental-strip-types --test src/apps/kuaiai/opsData.test.ts
 */

export interface DayPoint {
  day: string;
  count: number;
}

/** 站点时区（Asia/Shanghai）当日 YYYY-MM-DD；可由参数覆盖便于测试。 */
export function siteTodayISO(now: Date = new Date()): string {
  // Intl en-CA 直接产出 YYYY-MM-DD，规避手拼月份/时区误差
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now);
}

function isoDayAdd(isoDay: string, delta: number): string {
  // 以 UTC 正午为锚点加减天数，避免 DST/时区边界误差
  const [y, m, d] = isoDay.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d, 12));
  dt.setUTCDate(dt.getUTCDate() + delta);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${dt.getUTCFullYear()}-${pad(dt.getUTCMonth() + 1)}-${pad(dt.getUTCDate())}`;
}

/**
 * by_day 缺失日期补 0：返回 [endDay-days+1 .. endDay] 连续序列。
 * days 兜底为 >=1；非法 day 字符串的项忽略。
 */
export function fillMissingDays(
  byDay: DayPoint[] | null | undefined,
  days: number,
  endDay?: string,
): DayPoint[] {
  const span = Math.max(1, Math.floor(days) || 1);
  const end = endDay || siteTodayISO();
  const countMap = new Map<string, number>();
  for (const p of byDay ?? []) {
    if (p && /^\d{4}-\d{2}-\d{2}$/.test(p.day)) {
      countMap.set(p.day, (countMap.get(p.day) ?? 0) + (p.count ?? 0));
    }
  }
  const out: DayPoint[] = [];
  for (let i = span - 1; i >= 0; i -= 1) {
    const day = isoDayAdd(end, -i);
    out.push({ day, count: countMap.get(day) ?? 0 });
  }
  return out;
}

/** 能力标签：null/空串/后端归一的 unknown → 未分类（参数化文案）。 */
export function capabilityLabel(
  capability: string | null | undefined,
  uncategorized = '未分类',
): string {
  const v = (capability ?? '').trim();
  if (!v || v.toLowerCase() === 'unknown') return uncategorized;
  return v;
}

/** 审计状态码 → Tag 色：2xx 绿 / 4xx 橙 / 5xx 红 / 其它 default。 */
export function auditStatusTone(
  statusCode: number | null | undefined,
): 'success' | 'warning' | 'error' | 'default' {
  const code = Number(statusCode);
  if (!Number.isFinite(code) || code <= 0) return 'default';
  if (code >= 200 && code < 300) return 'success';
  if (code >= 400 && code < 500) return 'warning';
  if (code >= 500) return 'error';
  return 'default';
}
