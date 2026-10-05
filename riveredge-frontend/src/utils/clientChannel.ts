/**
 * 客户端渠道身份（与后端 core.utils.client_channel 对齐）
 *
 * 各端在请求头携带 X-Client-Channel，供登录日志「登录设备」与报工来源落库。
 */

export const CLIENT_CHANNEL_HEADER = 'X-Client-Channel';

export type ClientChannel =
  | 'pc'
  | 'station'
  | 'android'
  | 'ios'
  | 'mobile_h5'
  | 'miniprogram';

export type ReportingReportMode = 'self' | 'proxy' | 'team';

/** 工位入口。办公室页面与这一路径不共用渠道。 */
export const STATION_ENTRY_PATH = '/apps/kuaizhizao/production-execution/station';

/** 当前地址是否落在工位入口（含其子路径）。标签工位、已下线 terminal 不在此列。 */
export function isStationEntryPath(pathname: string): boolean {
  const path = String(pathname || '').split('?')[0].split('#')[0].replace(/\/+$/, '') || '/';
  return path === STATION_ENTRY_PATH || path.startsWith(`${STATION_ENTRY_PATH}/`);
}

function readDebugEnvChannel(): 'station' | 'pc' | null {
  const fromEnv = String(import.meta.env.VITE_CLIENT_CHANNEL || '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_');
  if (fromEnv === 'station' || fromEnv === 'pc') return fromEnv;
  return null;
}

function hasInjectedStationShell(): boolean {
  if (typeof window === 'undefined') return false;
  const shell = (window as Window & { stationShell?: unknown }).stationShell;
  return !!shell && typeof shell === 'object';
}

/**
 * 生产构建只有一份。判断顺序：
 * 开发模式若显式设置了 VITE_CLIENT_CHANNEL，仅用于本地整站调试，生产构建不看该变量。
 * 其后若页面里已有壳注入的 window.stationShell，渠道为 station。
 * 再按当前 location：工位入口为 station，其余页面为 pc。
 */
export function resolveWebClientChannel(): ClientChannel {
  if (import.meta.env.DEV) {
    const debug = readDebugEnvChannel();
    if (debug) return debug;
  }
  if (hasInjectedStationShell()) return 'station';
  const pathname = typeof window !== 'undefined' ? window.location.pathname : '';
  if (isStationEntryPath(pathname)) return 'station';
  return 'pc';
}

export function webClientChannelHeaders(): Record<string, string> {
  return { [CLIENT_CHANNEL_HEADER]: resolveWebClientChannel() };
}

/** 报工来源口语聚合（与后端 REPORTING_CLIENT_CHANNEL_SOURCE_LABELS 一致） */
export function reportingClientChannelSourceKey(
  channel: string | null | undefined,
): 'miniprogram' | 'app' | 'station' | 'pc' | 'auto' | null {
  const code = String(channel ?? '')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_');
  if (!code) return null;
  if (code === 'auto' || code === 'auto_report' || code === 'ind_relay_auto_report') {
    return 'auto';
  }
  if (code === 'miniprogram' || code === 'wechat' || code === 'weixin' || code === 'mp') {
    return 'miniprogram';
  }
  if (code === 'station' || code === 'touch' || code === 'kiosk') return 'station';
  if (code === 'pc' || code === 'web' || code === 'desktop') return 'pc';
  if (
    code === 'android' ||
    code === 'ios' ||
    code === 'mobile_h5' ||
    code === 'mobile' ||
    code === 'h5'
  ) {
    return 'app';
  }
  return null;
}

/** 报工来源 i18n key（无码时返回 null，禁止猜） */
export function reportingClientChannelSourceI18nKey(
  channel: string | null | undefined,
): string | null {
  const sourceKey = reportingClientChannelSourceKey(channel);
  if (!sourceKey) return null;
  return `app.kuaizhizao.workReporting.clientChannel.${sourceKey}`;
}
