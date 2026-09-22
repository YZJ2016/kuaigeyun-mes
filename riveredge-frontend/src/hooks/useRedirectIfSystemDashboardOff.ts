import { useConfigStore } from '../stores/configStore';
import { TENANT_HOME_FALLBACK } from '../stores/configStore';
import { useTenantEffectiveHomePath } from './useTenantEffectiveHomePath';

/** 系统级仪表盘关闭时的兜底路径（与 effective-home 一致，不再使用应用中心） */
export const SYSTEM_DASHBOARD_FALLBACK_PATH = TENANT_HOME_FALLBACK;

/**
 * 站点设置「系统级仪表盘是否显示」关闭时，由 SystemDashboardRouteGate 一次性 Navigate 到有效首页。
 */
export function useRedirectIfSystemDashboardOff() {
  const initialized = useConfigStore((s) => s.initialized);
  const configs = useConfigStore((s) => s.configs);
  const enabled = configs.enable_system_dashboard !== false;
  const { path: redirectPath, ready: homeReady } = useTenantEffectiveHomePath();

  return {
    initialized: initialized && homeReady,
    enabled,
    redirectPath,
    homeReady,
  };
}
